'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('utils/video_similarity/assets/workspace.js', 'utf8');
const nodes = new Map();
const $ = id => {
    if (!nodes.has(id)) nodes.set(id, {textContent:'', dataset:{}});
    return nodes.get(id);
};
let confirmations = [], submissions = [], accept = false, keydown;
const context = vm.createContext({
    $, count:String, connected:true, activeTask:null, submitting:false, pairLoading:false,
    tasks:[],cacheStatusInFlight:null,refreshCacheStatus() {},clearHistory() {},
    currentIndex:0, totalGroups:5, currentPair:null, activePage:'compare',
    downloadStatus:{config:{download_dir:'C:\\Users\\Chris\\Downloads',archive_base:'D:\\Private\\Videos'},
        totals:{uncategorized_count:2,classified_count:3,download_total_count:5,archive_count:8156}},
    document:{querySelectorAll:() => [],querySelector:() => null,
        addEventListener(name, callback) { if (name === 'keydown') keydown=callback; }},
    async refreshDownloads() { return context.downloadStatus; },
    async pollTasks() {}, notice() {}, switchTab() {},
    async confirmAction(...args) { confirmations.push(args); return accept; },
    async submitTask(...args) { submissions.push(args); },
    loadPair(index) { context.currentIndex=index; },
    review() { throw new Error('Keyboard must not submit a review decision'); }
});
for (const [start,end] of [
    ['function updateButtons()', 'function switchTab('],
    ['function renderDownloadWorkflow()', 'async function refreshLibrary('],
    ['async function classify()', 'function updatePairCount()'],
    ['function updateVideoSources()', 'async function review('],
    ["$('full-scan-btn').onclick", "$('delete-a').onclick"],
    ["document.addEventListener('keydown'", "switchTab(location.hash"]
]) vm.runInContext(source.slice(source.indexOf(start),source.indexOf(end,source.indexOf(start))),context);

(async () => {
    context.currentPair={videos:[{originalPath:'c:/USERS/Chris/Downloads/group/a.mp4'},
        {originalPath:'D:\\Private\\Videos\\group\\b.mp4'}]};
    context.updateVideoSources();
    assert.equal($('source-a').textContent,'下载区');
    assert.equal($('source-b').textContent,'视频库');
    assert.equal($('location-b').textContent,'D:\\Private\\Videos\\group');
    context.currentPair.videos.reverse(); context.updateVideoSources();
    assert.equal($('source-a').textContent,'视频库');
    assert.equal($('source-b').textContent,'下载区');
    context.currentPair.videos[1].originalPath='C:/Users/Chris/Downloads-old/a.mp4';
    context.updateVideoSources(); assert.equal($('source-b').textContent,'其他目录');
    const config=context.downloadStatus.config;
    context.downloadStatus.config=null; context.updateVideoSources();
    assert.equal($('source-a').textContent,'来源暂未确认');
    context.downloadStatus.config=config;

    await context.migrate();
    assert.match(confirmations.at(-1)[1],/已分组的 3 个/);
    assert.ok(confirmations.at(-1)[1].includes(config.archive_base));
    assert.match(confirmations.at(-1)[1],/5 组未审阅/);
    assert.equal(submissions.length,0);
    await context.scanDownloads();
    assert.match(confirmations.at(-1)[1],/2 个未分组视频/);
    assert.match(confirmations.at(-1)[1],/替换当前 5 组/);
    await $('full-scan-btn').onclick();
    assert.match(confirmations.at(-1)[1],/只比较视频库内/);
    assert.match(confirmations.at(-1)[1],/替换当前审阅列表/);
    await $('cache-clean-btn').onclick();
    assert.equal(confirmations.at(-1)[3],true);
    assert.equal(submissions.length,0,'Cancelled dialogs cannot submit operations');

    accept=true;
    await context.scanDownloads();
    assert.equal(submissions.at(-1)[0],'/api/similarity/refresh');
    assert.equal(submissions.at(-1)[1].classify_first,true);
    context.downloadStatus.totals.uncategorized_count=0;
    await context.scanDownloads();
    assert.equal(submissions.at(-1)[1].classify_first,false);
    await context.migrate();
    assert.equal(submissions.at(-1)[0],'/api/download-library/migrate');
    const before=submissions.length;
    context.activeTask={id:'busy'};
    await context.scanDownloads(); await context.migrate();
    assert.equal(submissions.length,before);
    context.updateButtons();
    assert.equal($('delete-a').disabled,true);
    context.activeTask=null;
    context.downloadStatus.totals.archive_count=0;
    context.updateButtons();
    assert.equal($('scan-btn').disabled,true);
    assert.equal($('compare-scan-btn').disabled,true);
    assert.equal($('full-scan-btn').disabled,true);
    await context.scanDownloads(); assert.equal(submissions.length,before);

    context.totalGroups=0; context.renderDownloadWorkflow();
    assert.match($('compare-empty-description').textContent,/仍有 5 个视频/);
    const event={target:{closest:() => null},preventDefault() {}};
    keydown({...event,key:'k'}); keydown({...event,key:'K'});
    assert.equal(context.currentIndex,0);
    context.totalGroups=5; keydown({...event,key:'ArrowRight'});
    assert.equal(context.currentIndex,1);
    console.log('Workflow: path-based origins, explicit operation scopes, cancel/busy guards, empty-library guard and safe keyboard navigation pass.');
})().catch(error => { console.error(error); process.exitCode=1; });
