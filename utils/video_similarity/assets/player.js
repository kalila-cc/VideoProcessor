// Player interactions retained from the original workspace.
function loadAudioState() {
    const fallback = { muted: true, volume: 0.5 };
    try {
        const saved = JSON.parse(localStorage.getItem(AUDIO_STATE_KEY) || '{}');
        return {
            muted: typeof saved.muted === 'boolean' ? saved.muted : fallback.muted,
            volume: normalizeVolume(saved.volume, fallback.volume),
        };
    } catch (e) {
        return fallback;
    }
}

function normalizeVolume(value, fallback = 0.5) {
    const num = Number(value);
    if (!Number.isFinite(num)) return fallback;
    return Math.min(1, Math.max(0, num));
}

function saveAudioState() {
    try { localStorage.setItem(AUDIO_STATE_KEY, JSON.stringify(audioState)); } catch (_) {}
}

function captureAudioState(art) {
    if (applyingAudioState || !art || !art.video) return;
    audioState = {
        muted: Boolean(art.video.muted),
        volume: normalizeVolume(art.video.volume, audioState.volume),
    };
    saveAudioState();
}

function applyAudioState(art) {
    if (!art || !art.video) return;

    applyingAudioState = true;
    art.video.volume = normalizeVolume(audioState.volume, 0.5);
    art.video.muted = Boolean(audioState.muted);
    requestAnimationFrame(() => { applyingAudioState = false; });
}

class VideoSyncManager {
    constructor(a, b) {
        this.a = a; this.b = b;
        this.master = null;
        this.isLocked = false;
        this.init();
    }

    init() {
        [{ art: this.a, id: 'A' }, { art: this.b, id: 'B' }].forEach(item => {
            const { art, id } = item;
            const other = id === 'A' ? this.b : this.a;

            const setMaster = () => {
                if (!this.isLocked && this.master !== id) {
                    console.log(`[Sync] Master -> ${id}`);
                    this.master = id;
                }
            };

            // ArtPlayer 的 proxy 可以轻松拦截底层事件
            art.on('video:mousedown', setMaster);
            art.on('video:touchstart', setMaster);
            art.on('control', setMaster); // 点击控制栏

            art.on('video:play', () => this.sync(id, 'play'));
            art.on('video:pause', () => this.sync(id, 'pause'));
            art.on('video:seeking', () => setMaster());
            art.on('video:seeked', () => this.sync(id, 'seek'));
            art.on('video:ratechange', () => this.sync(id, 'rate'));

            // 处理全屏退出后的强制对齐
            art.on('fullscreen', (state) => {
                if (!state) {
                    console.log(`[Sync] Fullscreen exit for ${id}, force alignment`);
                    this.sync(id, 'seek', true);
                }
            });
            art.on('fullscreenWeb', (state) => {
                if (!state) {
                    console.log(`[Sync] Web Fullscreen exit for ${id}, force alignment`);
                    this.sync(id, 'seek', true);
                }
            });
        });
    }

    sync(sourceId, action, force = false) {
        if (this.isLocked && !force) return;
        if (this.master && this.master !== sourceId && !force) return;

        const source = sourceId === 'A' ? this.a : this.b;
        const target = sourceId === 'A' ? this.b : this.a;

        // 检查全屏 (强制对齐除外，用于处理退出全屏后的同步)
        if ((source.fullscreen || source.fullscreenWeb) && !force) return;

        this.isLocked = true;

        try {
            const vS = source.video, vT = target.video;
            switch (action) {
                case 'play':
                    if (vT.paused) {
                        const playResult = vT.play();
                        if (playResult && typeof playResult.catch === 'function') {
                            playResult.catch(err => console.warn(`[Sync] Target ${sourceId === 'A' ? 'B' : 'A'} play blocked:`, err));
                        }
                    }
                    break;
                case 'pause': if (!vT.paused) target.pause(); break;
                case 'seek':
                    if (Math.abs(vS.currentTime - vT.currentTime) > 0.1) {
                        target.currentTime = vS.currentTime;
                    }
                    break;
                case 'rate': vT.playbackRate = vS.playbackRate; break;
            }
        } catch (e) { }

        setTimeout(() => { this.isLocked = false; }, 150);
    }
}

function createPlayer(container, url) {
    const art = new Artplayer({
        container, url,
        autoplay: false,
        muted: audioState.muted,
        preload: 'auto',
        autoSize: false,
        autoAttribute: false,
        theme: '#529a83',
        volume: audioState.volume,
        loop: true,
        playbackRate: true,
        aspectRatio: true,
        setting: true,
        fullscreen: true,
        fullscreenWeb: true,
        miniProgressBar: true,
        videoAttributes: {
            style: 'object-fit: contain',
        },
        controls: [
            {
                position: 'right',
                html: '旋转',
                click: function (art) {
                    art.rotate += 90;
                },
            },
        ],
    });

    bindAudioStatePersistence(art);
    bindDirectClickToggle(art, container);
    return art;
}

function bindAudioStatePersistence(art) {
    art.on('ready', () => applyAudioState(art));
    art.video.addEventListener('volumechange', () => captureAudioState(art));
}

function bindDirectClickToggle(art, containerSelector) {
    const root = document.querySelector(containerSelector) || (art.template && (art.template.$player || art.template.player));
    if (!root) return;

    if (typeof root.__videoInteractionCleanup === 'function') {
        root.__videoInteractionCleanup();
    }

    let lastFullscreenToggleAt = 0;

    const toggleFromDoubleClick = () => {
        lastFullscreenToggleAt = Date.now();
        togglePlayerFullscreen(art, root);
    };

    const handleClick = (event) => {
        if (isPlayerChromeEvent(event)) {
            return;
        }

        event.preventDefault();
        event.stopImmediatePropagation();

        if (event.detail >= 2) {
            return;
        }

        if (art.video.paused) {
            playCurrentPairFromClick(art);
        } else {
            pauseCurrentPairFromClick(art);
        }
    };

    const handleDblClick = (event) => {
        if (isPlayerChromeEvent(event)) {
            return;
        }

        event.preventDefault();
        event.stopImmediatePropagation();
        if (Date.now() - lastFullscreenToggleAt > PLAYER_SINGLE_CLICK_DELAY_MS) {
            toggleFromDoubleClick();
        }
    };

    const handleVideoDblClick = (event) => {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        if (Date.now() - lastFullscreenToggleAt > PLAYER_SINGLE_CLICK_DELAY_MS) {
            toggleFromDoubleClick();
        }
    };

    root.addEventListener('click', handleClick, true);
    root.addEventListener('dblclick', handleDblClick, true);
    art.on('video:dblclick', handleVideoDblClick);

    root.__videoInteractionCleanup = () => {
        root.removeEventListener('click', handleClick, true);
        root.removeEventListener('dblclick', handleDblClick, true);
        if (typeof art.off === 'function') {
            art.off('video:dblclick', handleVideoDblClick);
        }
        root.__videoInteractionCleanup = null;
    };
}

function isPlayerChromeEvent(event) {
    const target = event.target;
    if (!target || typeof target.closest !== 'function') return false;
    return Boolean(target.closest('.art-control, .art-setting, .art-contextmenus, .art-info, .art-notice, button, input, select, textarea'));
}

function togglePlayerFullscreen(art, fullscreenRoot = null) {
    if (!art) return;
    const root = fullscreenRoot || (art.template && (art.template.$player || art.template.player));
    if (!root) return;

    try {
        if (typeof art.fullscreen !== 'undefined') {
            art.fullscreen = !art.fullscreen;
            focusPlayerRoot(root);
            return;
        }
    } catch (e) {
        console.warn('[Player] ArtPlayer fullscreen toggle failed:', e);
    }

    const fullscreenElement = document.fullscreenElement || document.webkitFullscreenElement;
    if (fullscreenElement) {
        const exitFullscreen = document.exitFullscreen || document.webkitExitFullscreen;
        if (exitFullscreen) exitFullscreen.call(document);
        focusPlayerRoot(root);
        return;
    }

    const requestFullscreen = root.requestFullscreen || root.webkitRequestFullscreen;
    if (requestFullscreen) {
        const result = requestFullscreen.call(root);
        if (result && typeof result.catch === 'function') {
            result.catch(err => console.warn('[Player] Browser fullscreen blocked:', err));
        }
        focusPlayerRoot(root);
        return;
    }
}

function focusPlayerRoot(root) {
    if (!root || typeof root.focus !== 'function') return;
    if (!root.hasAttribute('tabindex')) {
        root.setAttribute('tabindex', '-1');
    }
    requestAnimationFrame(() => root.focus({ preventScroll: true }));
}

function getClickPlaybackTargets(sourceArt) {
    if (sourceArt === artA && artB) return [artA, artB];
    if (sourceArt === artB && artA) return [artB, artA];
    return [sourceArt];
}

function playCurrentPairFromClick(sourceArt) {
    getClickPlaybackTargets(sourceArt).forEach(target => {
        if (!target || !target.video || !target.video.paused) return;
        const playResult = target.video.play();
        if (playResult && typeof playResult.catch === 'function') {
            playResult.catch(err => console.warn('[Player] Click play blocked:', err));
        }
    });
}

function pauseCurrentPairFromClick(sourceArt) {
    getClickPlaybackTargets(sourceArt).forEach(target => {
        if (target && target.video && !target.video.paused) {
            target.video.pause();
        }
    });
}
