'use strict';

const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const count = value => Number(value || 0).toLocaleString('zh-CN');
const bytes = value => {
    let size = Number(value) || 0, unit = 0;
    const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
    while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit++; }
    return `${size.toLocaleString('zh-CN', {maximumFractionDigits: unit ? 2 : 0})} ${units[unit]}`;
};
const timeText = value => value ? new Date(value).toLocaleString('zh-CN', {hour12: false}) : '—';
const stateNames = {running:'运行中', complete:'已完成', partial:'部分完成', failed:'失败', interrupted:'已中断'};
const pageNames = {download:'下载整理', compare:'相似审阅', library:'视频库', maintenance:'维护与记录'};
const AUDIO_STATE_KEY = 'video-similarity-audio-state-v1';
const PLAYER_SINGLE_CLICK_DELAY_MS = 420;
let artA = null, artB = null, syncManager = null;
let applyingAudioState = false, audioState = loadAudioState();
let currentPair = null, currentIndex = 0, totalGroups = 0;
let downloadStatus = null, libraryStatus = null;
let activePage = 'download', connected = false, submitting = false, pairLoading = false;
let tasks = [], activeTask = null, serverId = null, pollInFlight = null, pollTimer = null;
let latestKey = null, detailTask = null, pairRequest = 0, downloadRequest = 0, libraryRequest = 0;
let historyKey = null;
let cacheStatusInFlight = null;

function notice(message, success = false) {
    $('notice').className = 'notice' + (success ? ' success' : '');
    $('notice').replaceChildren();
    const text = document.createElement('span'); text.textContent = message;
    const close = document.createElement('button'); close.textContent = '关闭';
    close.onclick = () => { $('notice').hidden = true; };
    $('notice').append(text, close); $('notice').hidden = false;
}

async function api(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
        const response = await fetch(url, {...options, signal: controller.signal, cache: 'no-store',
            headers: {'Content-Type':'application/json', ...options.headers}});
        let data;
        try { data = await response.json(); } catch (_) { throw new Error(`服务返回了无法读取的响应（${response.status}）`); }
        if (!response.ok || data.success === false) {
            const errors = (data.errors || []).map(e => typeof e === 'string' ? e : e.error).join('；');
            throw new Error(data.error || errors || `操作失败（${response.status}）`);
        }
        return data;
    } catch (error) {
        if (error.name === 'AbortError' || error instanceof TypeError) {
            setConnection(false);
            throw new Error(options.method === 'POST'
                ? '未收到操作回执。任务可能已提交，请等待自动重连并核对任务记录后再操作。'
                : '暂时无法连接本机服务。请运行 start_web.bat，页面会自动重连。');
        }
        throw error;
    } finally { clearTimeout(timeout); }
}

function setConnection(value) {
    connected = value;
    $('connection-dot').className = 'status-dot ' + (value ? 'online' : 'offline');
    $('connection-label').textContent = value ? '本机服务已连接' : '本机服务已断开';
    $('connection-banner').hidden = value;
    if (value) $('connection-time').textContent = '最近连接 ' + new Date().toLocaleTimeString('zh-CN', {hour12:false});
    $('global-task-status').textContent = !value ? '连接中断 · 等待重连' : activeTask ? '1 个任务运行中' : '服务就绪';
    updateLatestReviewStatus();
    updateButtons();
}

function updateButtons() {
    const locked = !connected || Boolean(activeTask) || submitting;
    document.querySelectorAll('[data-mutation]').forEach(button => { button.disabled = locked; });
    const totals = downloadStatus?.totals;
    $('clear-history-btn').disabled = locked || !tasks.length;
    $('cache-preview-btn').disabled = locked || Boolean(cacheStatusInFlight);
    $('classify-btn').disabled = locked || !totals?.uncategorized_count;
    $('rename-btn').disabled = locked || !totals?.classified_count;
    $('migrate-btn').disabled = locked || !totals?.classified_count;
    const cannotScan = locked || !totals?.download_total_count || !totals?.archive_count;
    ['scan-btn','compare-scan-btn'].forEach(id => {
        $(id).disabled = cannotScan;
        $(id).title = !totals?.download_total_count ? '下载区暂无视频' : !totals?.archive_count ? '视频库为空，请先将首批视频入库' : '';
    });
    $('full-scan-btn').disabled = locked || !(totals?.archive_count >= 2);
    ['delete-a', 'delete-b', 'keep-both'].forEach(id => { $(id).disabled = locked || pairLoading || !currentPair; });
    $('prev-pair').disabled = pairLoading || currentIndex <= 0 || !connected;
    $('next-pair').disabled = pairLoading || currentIndex >= totalGroups - 1 || !connected;
    $('jump-pair').disabled = pairLoading || !totalGroups || !connected;
}

function switchTab(page, updateHash = true) {
    if (!(page in pageNames)) page = 'download';
    if (page !== 'compare') [artA, artB].forEach(art => { if (art?.video) art.video.pause(); });
    activePage = page;
    document.querySelectorAll('.page-view').forEach(view => { view.hidden = view.id !== page + '-page'; });
    document.querySelectorAll('.nav-tab').forEach(button => {
        const selected = button.dataset.tab === page;
        button.classList.toggle('active', selected);
        if (selected) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
    });
    $('page-breadcrumb').textContent = '工作空间 / ' + pageNames[page];
    if (updateHash) history.replaceState(null, '', '#' + page);
    if (connected && page === 'library') refreshLibrary();
    if (connected && page === 'download') refreshDownloads();
    if (connected && page === 'maintenance') refreshCacheStatus();
    if (connected && page === 'compare' && (!currentPair || totalGroups === 0)) loadPair(currentIndex);
}

function metric(label, value, description) {
    return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(description)}</small></div>`;
}

async function refreshDownloads() {
    const request = ++downloadRequest;
    try {
        const data = await api('/api/download-library/status');
        if (request !== downloadRequest) return;
        downloadStatus = data;
        updateVideoSources();
        const t = data.totals;
        $('download-count').textContent = count(t.download_total_count);
        renderDownloadWorkflow();
        $('download-summary').classList.remove('skeleton');
        $('download-summary').setAttribute('aria-busy', 'false');
        $('download-summary').innerHTML = metric('待分类', count(t.uncategorized_count), bytes(t.uncategorized_bytes ?? t.uncategorized_mb * 1048576))
            + metric('已分类 / 待入库', count(t.classified_count), bytes(t.classified_bytes ?? t.classified_mb * 1048576))
            + metric('下载区总量', bytes(t.download_total_bytes ?? t.download_total_mb * 1048576), count(t.download_total_count) + ' 个视频')
            + metric('已归档', count(t.archive_count), bytes(t.archive_bytes ?? t.archive_mb * 1048576));
        $('download-rows').innerHTML = `<tr><td>待分类<small>下载根目录</small></td><td>${count(t.uncategorized_count)}</td><td>${bytes(data.uncategorized.total_bytes)}</td><td class="muted">按大小自动分区</td></tr>`
            + data.categories.map(cat => `<tr><td>${escapeHtml(cat.name)}<small>${escapeHtml(cat.label)}</small></td><td>${count(cat.count)}</td><td>${bytes(cat.total_bytes)}</td><td class="muted">${escapeHtml(cat.archive_subdir)}</td></tr>`).join('');
        $('download-paths').innerHTML = [['下载目录',data.config.download_dir],['视频库',data.config.archive_base],['特征缓存',data.config.cache_dir]]
            .map(([label,value]) => `<dt>${label}</dt><dd>${escapeHtml(value)}</dd>`).join('');
        $('download-updated').textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN', {hour12:false});
        updateButtons();
        return data;
    } catch (error) {
        $('download-updated').textContent = '读取失败 · 保留上次数据';
        $('download-summary').classList.remove('skeleton');
        $('download-summary').setAttribute('aria-busy','false');
        if (!downloadStatus) $('download-rows').innerHTML = '<tr><td colspan="4">无法读取目录，请检查服务连接后刷新。</td></tr>';
        if (connected) notice(error.message);
    }
}

function renderDownloadWorkflow() {
    const t = downloadStatus?.totals;
    if (!t) return;
    $('classify-description').textContent = t.uncategorized_count
        ? `下载根目录有 ${count(t.uncategorized_count)} 个视频，按大小分组、按创建时间命名。`
        : '下载根目录暂无待分组视频。';
    $('scan-description').textContent = totalGroups
        ? `当前有 ${count(totalGroups)} 组待审阅。重新比对会替换这份列表。`
        : !t.archive_count ? '视频库为空，可先将首批视频移动到库内。'
        : t.download_total_count ? `${count(t.download_total_count)} 个下载视频可与视频库比对。`
        : '下载区暂无视频可比对。';
    $('migrate-description').textContent = t.classified_count
        ? `移动下载区已分组的 ${count(t.classified_count)} 个视频，下载区不再保留这些文件。`
        : '下载区暂无已分组视频可移动。';
    $('compare-empty-description').textContent = t.download_total_count
        ? `下载区仍有 ${count(t.download_total_count)} 个视频，可返回下载整理继续处理。`
        : '下载区暂无视频。';
}

async function refreshLibrary() {
    const request = ++libraryRequest;
    try {
        const data = await api('/api/video-library/status');
        if (request !== libraryRequest) return;
        libraryStatus = data;
        const t = data.totals;
        $('library-summary').classList.remove('skeleton');
        $('library-summary').setAttribute('aria-busy','false');
        $('library-summary').innerHTML = metric('归档视频', count(t.count), '所有规格目录')
            + metric('总容量', bytes(t.total_bytes), '视频原始文件')
            + metric('平均大小', bytes(t.average_bytes), '按视频数量计算')
            + metric('特征缓存', count(t.cache_count), bytes(t.cache_mb * 1048576) + ' · 数量不等于覆盖率');
        WorkspaceCharts.render(data);
        $('library-categories').innerHTML = data.categories.map(cat => `<tr><td>${escapeHtml(cat.label)}</td><td>${count(cat.count)}</td><td>${cat.count_percent}%</td><td>${bytes(cat.total_bytes)}</td><td>${cat.size_percent}%</td></tr>`).join('');
        $('library-histogram').innerHTML = data.size_histogram.map(row => `<tr><td>${escapeHtml(row.label)}</td><td>${count(row.count)}</td><td>${row.count_percent}%</td></tr>`).join('');
        $('library-updated').textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN', {hour12:false});
    } catch (error) {
        $('library-updated').textContent = '读取失败 · 保留上次数据';
        $('library-chart-status').textContent = libraryStatus ? '连接失败，图表保留上次成功读取的数据。' : '分布数据读取失败，请检查本机服务后刷新。';
        $('library-summary').classList.remove('skeleton');
        $('library-summary').setAttribute('aria-busy','false');
        if (connected) notice(error.message);
    }
}

async function refreshCacheStatus() {
    if (cacheStatusInFlight) return cacheStatusInFlight;
    if (!connected || activeTask) {
        $('cache-orphan-status').textContent = activeTask ? '任务结束后更新数量' : '连接恢复后更新数量';
        return;
    }
    $('cache-orphan-status').textContent = '正在检查…';
    cacheStatusInFlight = (async () => {
        try {
            const data = await api('/api/cache/orphans/status');
            $('cache-orphan-count').textContent = count(data.count) + ' 个';
            $('cache-orphan-bytes').textContent = bytes(data.bytes);
            $('cache-orphan-status').textContent = data.error_count
                ? `有 ${count(data.error_count)} 个缓存无法检查，数量可能不完整`
                : '检查于 ' + timeText(data.checked_at);
        } catch (error) {
            $('cache-orphan-status').textContent = '检查失败，显示值未更新。' + error.message;
        }
    })();
    updateButtons();
    try { await cacheStatusInFlight; }
    finally { cacheStatusInFlight = null; updateButtons(); }
}

async function clearHistory() {
    if (!connected || submitting || activeTask || !tasks.length) return;
    if (!await confirmAction('清空任务记录？', '清空全部任务历史记录，不影响视频、特征缓存和当前比对结果。', '清空记录', true)) return;
    if (!connected || submitting || activeTask) return;
    submitting = true; updateButtons();
    try {
        await api('/api/tasks/clear', {method:'POST', body:'{}'});
        detailTask = null;
        if ($('detail-dialog').open) $('detail-dialog').close();
        await pollTasks();
        notice('任务记录已清空。', true);
    } catch (error) { notice(error.message); }
    finally { submitting = false; updateButtons(); }
}

function distribution(label, value, percent, description) {
    return `<div class="distribution-row"><div class="distribution-label"><span>${escapeHtml(label)}</span><span>${escapeHtml(value)}</span></div><div class="bar-track"><div class="bar-fill" style="width:${Math.min(100,Math.max(0,percent))}%"></div></div><small>${escapeHtml(description)}</small></div>`;
}

async function pollTasks() {
    if (pollInFlight) return pollInFlight;
    pollInFlight = (async () => {
        try {
            const data = await api('/api/tasks');
            const reconnect = !connected || serverId !== data.server_id;
            const previousTotal = totalGroups;
            serverId = data.server_id;
            tasks = data.tasks;
            activeTask = tasks.find(task => task.id === data.active_id) || null;
            totalGroups = data.active_pairs;
            setConnection(true);
            renderTasks();
            updatePairCount();
            const latest = tasks[0];
            const key = latest ? latest.id + ':' + latest.state : 'empty';
            const changed = latestKey !== null && latestKey !== key;
            const finished = latest && latest.state !== 'running';
            if (key !== latestKey) {
                latestKey = key;
                if (!latest) $('latest-result').innerHTML = '<p class="muted">暂无任务记录。</p>';
                if (finished) await renderLatestResult(latest.id);
                if (changed && finished) {
                    notice(`${latest.label}：${stateNames[latest.state]}。${latest.state === 'complete' ? '可查看操作结果并继续下一步。' : '请查看任务详情，核对失败或中断的项目。'}`, latest.state === 'complete');
                }
            }
            if (reconnect || (changed && finished)) {
                refreshDownloads();
                if (libraryStatus || activePage === 'library') refreshLibrary();
                if (activePage === 'maintenance') refreshCacheStatus();
                if (activePage === 'compare') loadPair(Math.min(currentIndex, Math.max(0,totalGroups-1)));
                else { currentPair = null; destroyPlayers(); }
            } else if (previousTotal !== totalGroups && activePage === 'compare' && !pairLoading && !submitting) {
                loadPair(Math.min(currentIndex, Math.max(0,totalGroups-1)));
            }
        } catch (_) { setConnection(false); }
    })();
    try { await pollInFlight; } finally {
        pollInFlight = null;
        clearTimeout(pollTimer);
        pollTimer = setTimeout(pollTasks, activeTask ? 1500 : 5000);
    }
}

function renderTasks() {
    $('task-strip').hidden = !activeTask;
    if (activeTask) {
        $('task-title').textContent = activeTask.label;
        $('task-message').textContent = activeTask.message;
        $('task-message').title = activeTask.message;
        const progress = $('task-progress');
        if (activeTask.total > 0) { progress.max = activeTask.total; progress.value = activeTask.completed; }
        else progress.removeAttribute('value');
        $('task-progress-text').textContent = activeTask.stage + (activeTask.total > 0 ? ` · ${count(activeTask.completed)} / ${count(activeTask.total)}` : ' · 正在处理');
    }
    const nextHistoryKey = tasks.map(task => task.id + task.state).join(',');
    if (nextHistoryKey !== historyKey) {
        historyKey = nextHistoryKey;
        $('task-history').innerHTML = tasks.map(task => `<div class="history-row"><div><strong>${escapeHtml(task.label)}</strong><span class="state-label ${task.state}">${stateNames[task.state]}</span><small>${timeText(task.started_at)}</small></div><button class="text-button" data-task="${task.id}">查看详情</button></div>`).join('') || '<p class="muted">暂无任务记录。完成一次分类、扫描或迁移后，结果会保存在这里。</p>';
    }
}

function resultSummary(result = {}) {
    const isScan = ['incremental_downloads','full_library'].includes(result.mode) || result.active_count !== undefined;
    const labels = {moved_count:'分类', renamed_count:'命名', skipped_count:'已规范', migrated_count:'迁移', cached_count:'缓存写入', indexed_count:'索引就绪', valid_count:'可复用缓存', rebuilt_count:'恢复路径', missing_count:isScan ? '扫描时失效组' : '当时缺失特征', active_count:'扫描完成时待审阅组'};
    const parts = Object.entries(labels).filter(([key]) => result[key] !== undefined).map(([key,label]) => `${label} ${count(result[key])}`);
    if (result.cache_result) {
        const c = result.cache_result;
        parts.push(`${result.dry_run ? '可清理' : '已清理'} ${count(c.deleted_count)} 个缓存`, `${result.dry_run ? '预计释放' : '释放'} ${bytes(c.freed_bytes)}`);
    }
    if (result.errors?.length) parts.push(`${count(result.errors.length)} 项失败`);
    return parts.join(' · ') || '查看详情了解执行结果';
}

function updateLatestReviewStatus() {
    const status = $('latest-review-status');
    if (status) status.textContent = !connected ? '当前待审阅数量暂不可用，正在重新连接'
        : totalGroups ? `当前待审阅 ${count(totalGroups)} 组` : '当前待审阅 0 组 · 暂无待审阅相似项';
}

async function renderLatestResult(id) {
    try {
        const {task} = await api('/api/tasks/' + id);
        const isScan = ['incremental_downloads','full_library'].includes(task.kind);
        const summary = isScan
            ? '<p id="latest-review-status" role="status" aria-live="polite"></p>'
            : `<p>${escapeHtml(resultSummary(task.result || {}))}</p>`;
        $('latest-result').innerHTML = `<span class="state-label ${task.state}" style="margin:0">${stateNames[task.state]}</span><p style="color:var(--text)">${escapeHtml(task.label)}</p>${summary}<small>${timeText(task.finished_at)}</small><br><button class="text-button" data-task="${task.id}">查看完整结果</button>`;
        if (isScan) {
            $('latest-result').innerHTML += '<div><button class="btn" data-tab="compare">查看当前审阅列表</button></div>';
            updateLatestReviewStatus();
        }
        if (task.state === 'complete') {
            if (['classify','rename'].includes(task.kind)) $('latest-result').innerHTML += '<div><button class="btn" data-next="scan">下一步：比对下载区</button></div>';
            if (task.kind === 'migrate') $('latest-result').innerHTML += '<div><button class="btn" data-tab="library">查看入库后的分布</button></div>';
        }
    } catch (error) { $('latest-result').textContent = error.message; }
}

async function showTask(id) {
    try {
        const {task} = await api('/api/tasks/' + id);
        detailTask = task;
        $('detail-title').textContent = task.label + ' · ' + stateNames[task.state];
        const result = task.result || {};
        $('detail-body').innerHTML = `<p>${escapeHtml(task.message)}</p><p class="muted">${timeText(task.started_at)} → ${timeText(task.finished_at)}</p><p>${escapeHtml(resultSummary(result))}</p>`;
        if (result.errors?.length) $('detail-body').innerHTML += '<h3>需要处理的项目</h3><pre class="error-text">' + escapeHtml(JSON.stringify(result.errors,null,2)) + '</pre>';
        const records = result.records || [];
        if (records.length) $('detail-body').innerHTML += `<details><summary>文件操作明细（${count(records.length)} 条）</summary>${records.map(record => `<div class="detail-record"><strong>${escapeHtml(record.action || '')} ${escapeHtml(record.file || record.from || '')}</strong><small>${escapeHtml(record.from || '')}</small><small>${record.to ? '→ ' + escapeHtml(record.to) : ''}</small>${record.error || record.cache_error ? `<small class="error-text">${escapeHtml(record.error || record.cache_error)}</small>` : ''}</div>`).join('')}</details>`;
        if (result.cache_result) $('detail-body').innerHTML += '<pre>' + escapeHtml(JSON.stringify(result.cache_result,null,2)) + '</pre>';
        if (!$('detail-dialog').open) $('detail-dialog').showModal();
    } catch (error) { notice(error.message); }
}

function confirmAction(title, message, label = '确认执行', destructive = false) {
    const dialog = $('confirm-dialog');
    if (dialog.open) return Promise.resolve(false);
    [artA, artB].forEach(art => { if (art?.video) art.video.pause(); });
    $('confirm-title').textContent = title;
    $('confirm-message').textContent = message;
    $('confirm-submit').textContent = label;
    $('confirm-submit').classList.toggle('btn-danger', destructive);
    $('confirm-submit').classList.toggle('btn-primary', !destructive);
    dialog.returnValue = 'cancel';
    dialog.showModal();
    return new Promise(resolve => dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), {once:true}));
}

async function submitTask(route, body = {}) {
    if (submitting || activeTask || !connected) return;
    submitting = true; updateButtons();
    try {
        const data = await api(route, {method:'POST', body:JSON.stringify(body)});
        activeTask = data.task;
        tasks = [activeTask, ...tasks.filter(task => task.id !== activeTask.id)];
        renderTasks();
        $('notice').hidden = true;
    } catch (error) { notice(error.message); }
    finally { submitting = false; updateButtons(); await pollTasks(); }
}

async function classify() {
    if (!await refreshDownloads()) return;
    const total = downloadStatus?.totals.uncategorized_count || 0;
    if (!total || !connected) return;
    if (await confirmAction('按大小分组并重命名', `将下载根目录的 ${count(total)} 个视频移到大小分组目录，并用创建时间替换文件名。`, '分组并重命名'))
        await submitTask('/api/download-library/classify');
}

async function scanDownloads() {
    if (!await refreshDownloads()) return;
    if (!connected || !downloadStatus) return;
    const t = downloadStatus.totals;
    if (!t.download_total_count) { notice('下载区暂无视频，请先下载视频到配置的下载目录。'); switchTab('download'); return; }
    if (!t.archive_count) { notice('视频库为空，请先将首批视频移动到视频库。'); return; }
    await pollTasks();
    if (!connected || activeTask) return;
    const prepare = t.uncategorized_count > 0;
    const message = (prepare ? `先将 ${count(t.uncategorized_count)} 个未分组视频按大小分组、按创建时间重命名。\n` : '')
        + `将下载区的 ${count(t.download_total_count)} 个视频与视频库比对。\n`
        + (totalGroups ? `会替换当前 ${count(totalGroups)} 组审阅列表。` : '结果会更新审阅列表，不自动删除视频。');
    if (await confirmAction(prepare ? '分组后与视频库比对' : '下载区与视频库比对', message, prepare ? '分组并比对' : '开始比对'))
        await submitTask('/api/similarity/refresh', {mode:'incremental_downloads', classify_first:prepare});
}

async function migrate() {
    if (!await refreshDownloads()) return;
    await pollTasks();
    const total = downloadStatus?.totals.classified_count || 0;
    if (!total || !connected || activeTask) return;
    const warning = totalGroups ? `还有 ${count(totalGroups)} 组未审阅。\n\n` : '';
    const destination = downloadStatus.config.archive_base;
    if (await confirmAction('移动到视频库', warning + `将下载区已分组的 ${count(total)} 个视频移动到：\n${destination}\n\n下载区不再保留这些文件。`, totalGroups ? '仍然移动到视频库' : '移动到视频库'))
        await submitTask('/api/download-library/migrate');
}

function updatePairCount() {
    updateLatestReviewStatus();
    renderDownloadWorkflow();
    $('review-count').textContent = count(totalGroups);
    $('pair-count').textContent = count(totalGroups) + ' 组';
    $('jump-total').textContent = '/ ' + count(totalGroups);
    $('jump-input').max = Math.max(1,totalGroups);
    if (document.activeElement !== $('jump-input')) $('jump-input').value = totalGroups ? currentIndex + 1 : 1;
    updateButtons();
}

function destroyPlayers() {
    captureAudioState(artA || artB);
    [artA,artB].forEach(art => { if (art) { try { art.destroy(); } catch (_) {} } });
    artA = artB = syncManager = null;
}

async function loadPair(index = 0) {
    const request = ++pairRequest;
    pairLoading = true; updateButtons();
    try {
        const metadata = await api('/api/metadata');
        if (request !== pairRequest) return;
        totalGroups = metadata.total;
        if (!totalGroups) {
            currentPair = null; currentIndex = 0; destroyPlayers();
            $('comparison').hidden = true; $('compare-empty').hidden = false;
            return;
        }
        index = Math.max(0, Math.min(index,totalGroups - 1));
        const data = await api('/api/pair?index=' + index);
        if (request !== pairRequest) return;
        currentPair = data.pair; currentIndex = data.index; totalGroups = data.total;
        $('comparison').hidden = false; $('compare-empty').hidden = true;
        renderPair();
    } catch (error) {
        currentPair = null; destroyPlayers();
        notice(error.message + ' 当前未提交任何审阅决定。');
    } finally {
        if (request === pairRequest) { pairLoading = false; updatePairCount(); }
    }
}

function renderPair() {
    destroyPlayers();
    const pair = currentPair;
    const [a,b] = pair.videos;
    const comparisons = CompareMetrics.compare(a,b);
    [['a',a],['b',b]].forEach(([id,video]) => {
        $('title-' + id).textContent = video.name;
        $('title-' + id).title = video.originalPath;
        $('meta-' + id).innerHTML = comparisons.map(row => `<div class="video-parameter ${row.winner === id.toUpperCase() ? 'parameter-emphasis' : ''}"><dt>${row.label}</dt><dd>${escapeHtml(id === 'a' ? row.left : row.right)}</dd><small>${row.winner === id.toUpperCase() ? escapeHtml(row.verb) : row.winner ? '与另一侧有差异' : escapeHtml(row.note)}</small></div>`).join('');
        $('player-error-' + id).hidden = true;
    });
    updateVideoSources();
    $('score-text').textContent = pair.similarity;
    $('comparison-differences').innerHTML = comparisons.map(row => `<span class="comparison-tag ${row.winner ? 'has-difference' : ''}">${row.label}：${escapeHtml(row.note)}</span>`).join('');
    const components = [['duration_similarity','时长'],['phash_similarity','画面结构'],['dhash_similarity','画面纹理'],['histogram_similarity','色彩分布']];
    const scoreDetails = components.filter(([key]) => Number.isFinite(pair.scoreDetails?.[key]));
    $('score-details').hidden = !scoreDetails.length;
    $('score-details').innerHTML = scoreDetails.map(([key,label]) => `<span>${label}<strong>${(pair.scoreDetails[key] * 100).toFixed(1)}%</strong></span>`).join('');
    $('comp-info').textContent = pair.recommend === 'equal' ? '规格相近，请结合画面判断'
        : `规格参考：${pair.recommend} 的分辨率与文件大小综合值更高。大小、像素数不等于画质，请结合画面判断。`;
    try {
        artA = createPlayer('#player-a',a.path); artB = createPlayer('#player-b',b.path);
        const left = artA, right = artB;
        Promise.all([new Promise(resolve => left.on('ready',resolve)),new Promise(resolve => right.on('ready',resolve))])
            .then(() => { if (artA === left && artB === right) syncManager = new VideoSyncManager(left,right); });
        [[left,'a'],[right,'b']].forEach(([art,id]) => art.on('video:error', () => {
            $('player-error-' + id).hidden = false;
            $('player-error-' + id).textContent = '此视频无法在浏览器播放。可在文件夹中打开原文件确认；尚未执行任何移除。';
        }));
    } catch (_) { notice('播放器初始化失败。请刷新页面，或在文件夹中打开视频确认。'); }
}

function updateVideoSources() {
    if (!currentPair) return;
    const normalize = path => String(path || '').replaceAll('\\', '/').toLowerCase().replace(/\/$/, '');
    currentPair.videos.forEach((video,index) => {
        const id = index ? 'b' : 'a';
        const path = normalize(video.originalPath);
        const config = downloadStatus?.config;
        const origin = !config ? 'pending'
            : path.startsWith(normalize(config.download_dir) + '/') ? 'download'
            : path.startsWith(normalize(config.archive_base) + '/') ? 'archive' : 'other';
        const label = {pending:'来源暂未确认', download:'下载区', archive:'视频库', other:'其他目录'}[origin];
        $('source-' + id).textContent = label;
        $('source-' + id).dataset.origin = origin;
        $('source-' + id).title = video.originalPath;
        const directory = String(video.originalPath || '').replace(/[\\/][^\\/]+$/, '');
        $('location-' + id).textContent = directory;
        $('location-' + id).title = directory;
    });
}

async function review(action) {
    if (!currentPair || submitting || activeTask || !connected || pairLoading) return;
    const pair = currentPair;
    const index = currentIndex;
    if (!['delete-a', 'delete-b', 'both'].includes(action)) return;
    const target = pair.videos[action === 'delete-b' ? 1 : 0];
    if (action !== 'both' && !await confirmAction('删除此视频？', `${target.name}\n${target.originalPath}\n\n将移入回收站。`, '删除', true)) return;
    // The heartbeat can reload a group while the confirmation is open.
    if (currentPair !== pair) { notice('相似列表已更新，请重新确认当前组。'); return; }
    submitting = true; updateButtons();
    try {
        const data = await api(action === 'both' ? '/api/dismiss' : '/api/prune', {method:'POST',body:JSON.stringify(action === 'both'
            ? {pathA:pair.videos[0].originalPath,pathB:pair.videos[1].originalPath}
            : {files:[target.originalPath]})});
        totalGroups = data.total;
        await loadPair(Math.min(index,Math.max(0,totalGroups - 1)));
        notice(action === 'both' ? '已保留两个视频，以后不再提示这一组。' : '视频已移入系统回收站。',true);
        refreshDownloads();
        if (libraryStatus) refreshLibrary();
    } catch (error) { notice(error.message + ' 请核对当前文件后重试。'); }
    finally { submitting = false; updateButtons(); }
}

async function openExplorer(id) {
    if (!currentPair) return;
    try { await api('/api/open-explorer', {method:'POST',body:JSON.stringify({path:currentPair.videos[id === 'A' ? 0 : 1].originalPath})}); }
    catch (error) { notice(error.message); }
}

function exportTask() {
    if (!detailTask) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(detailTask,null,2)],{type:'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = 'video-task-' + detailTask.id + '.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
}

document.addEventListener('click', event => {
    const tab = event.target.closest('[data-tab]');
    if (tab) switchTab(tab.dataset.tab);
    const task = event.target.closest('[data-task]');
    if (task) showTask(task.dataset.task);
    if (event.target.closest('[data-next="scan"]')) scanDownloads();
});
$('classify-btn').onclick = classify;
$('scan-btn').onclick = $('compare-scan-btn').onclick = scanDownloads;
$('migrate-btn').onclick = migrate;
$('rename-btn').onclick = async () => {
    if (await confirmAction('按创建时间重命名', '将下载区已分组视频的文件名改为创建时间。已有时间格式的文件跳过。', '重命名'))
        submitTask('/api/download-library/rename');
};
$('full-scan-btn').onclick = async () => {
    if (await confirmAction('比对视频库内部重复项', '只比较视频库内的视频，不包含下载区。\n会替换当前审阅列表，不自动删除视频。', '开始库内比对'))
        submitTask('/api/similarity/refresh',{mode:'full_library'});
};
$('cache-rebuild-btn').onclick = () => submitTask('/api/cache/rebuild');
$('cache-preview-btn').onclick = refreshCacheStatus;
$('clear-history-btn').onclick = clearHistory;
$('cache-repair-btn').onclick = async () => {
    if (await confirmAction('计算缺失特征', '检查下载区和视频库，仅为缺失或失效的缓存重新读取视频、计算特征。', '开始计算'))
        submitTask('/api/cache/repair');
};
$('cache-clean-btn').onclick = async () => {
    if (await confirmAction('删除无用缓存', '只删除已无法对应现存视频的特征缓存，不删除视频文件。', '删除缓存', true))
        submitTask('/api/cache/orphans',{dry_run:false});
};
$('delete-a').onclick = () => review('delete-a');
$('delete-b').onclick = () => review('delete-b');
$('keep-both').onclick = () => review('both');
$('explorer-a').onclick = () => openExplorer('A');
$('explorer-b').onclick = () => openExplorer('B');
$('prev-pair').onclick = () => loadPair(currentIndex - 1);
$('next-pair').onclick = () => loadPair(currentIndex + 1);
$('jump-pair').onclick = () => {
    const value = Number($('jump-input').value);
    if (Number.isInteger(value) && value >= 1 && value <= totalGroups) loadPair(value - 1);
    else notice(`请输入 1 到 ${count(totalGroups)} 之间的组号。`);
};
$('jump-input').onkeydown = event => { if (event.key === 'Enter') $('jump-pair').click(); };
$('task-details').onclick = () => activeTask && showTask(activeTask.id);
$('close-detail').onclick = () => $('detail-dialog').close();
$('export-task').onclick = exportTask;
$('refresh-all').onclick = async () => { await pollTasks(); if (connected) { refreshDownloads(); if (activePage === 'library') refreshLibrary(); if (activePage === 'compare') loadPair(currentIndex); if (activePage === 'maintenance') refreshCacheStatus(); } };
$('reconnect').onclick = pollTasks;
window.addEventListener('hashchange', () => switchTab(location.hash.slice(1),false));
window.addEventListener('online', pollTasks);
document.addEventListener('visibilitychange', () => { if (!document.hidden) pollTasks(); });
document.addEventListener('keydown', event => {
    if (activePage !== 'compare' || pairLoading || submitting || document.querySelector('dialog[open]') || event.target.closest('input,button,textarea,.artplayer-app') || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === 'ArrowLeft' && currentIndex > 0) { event.preventDefault(); loadPair(currentIndex - 1); }
    if (event.key === 'ArrowRight' && currentIndex < totalGroups - 1) { event.preventDefault(); loadPair(currentIndex + 1); }
});
switchTab(location.hash.slice(1) || 'download');
pollTasks();
