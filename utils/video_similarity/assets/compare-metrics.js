'use strict';

// Pure comparison model, shared by the view and regression tests.
window.CompareMetrics = (() => {
    const valid = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
    function values(video) {
        const res = /^(\d+)\s*[x×]\s*(\d+)$/i.exec(video.resolution || '');
        const clock = /^(\d+):(\d+(?:\.\d+)?)$/.exec(video.duration || '');
        const size = /^([\d.]+)\s*(B|K(?:i)?B|M(?:i)?B|G(?:i)?B)$/i.exec(video.size || '');
        return {
            duration: valid(video.durationSeconds) ? video.durationSeconds : clock ? Number(clock[1]) * 60 + Number(clock[2]) : null,
            resolution: res ? Number(res[1]) * Number(res[2]) : null,
            size: valid(video.sizeBytes) ? video.sizeBytes : size ? Number(size[1]) * 1024 ** ({B:0,KB:1,KIB:1,MB:2,MIB:2,GB:3,GIB:3}[size[2].toUpperCase()]) : null
        };
    }
    function compare(a, b) {
        const av = values(a), bv = values(b);
        const display = (video, key) => {
            if (key === 'duration' && valid(video.durationSeconds)) {
                const rounded = Math.round(video.durationSeconds * 100);
                const minutes = Math.floor(rounded / 6000);
                const seconds = (rounded % 6000 / 100).toFixed(2).replace(/\.?0+$/, '');
                return `${minutes}:${Number(seconds) < 10 ? '0' : ''}${seconds}`;
            }
            return video[key] || '—';
        };
        return [
            {key:'duration', label:'时长', verb:'更长', unit:'秒'},
            {key:'resolution', label:'分辨率', verb:'像素更多'},
            {key:'size', label:'文件大小', verb:'文件更大'}
        ].map(row => {
            const left = av[row.key], right = bv[row.key];
            let note = '参数不可用', winner = null;
            if (valid(left) && valid(right)) {
                if (left === right) note = row.key === 'resolution' && a.resolution !== b.resolution ? '像素数相同，尺寸不同' : '两者相同';
                else {
                    winner = left > right ? 'A' : 'B';
                    const delta = Math.abs(left - right);
                    const difference = row.key === 'duration' ? `${Number(delta.toFixed(2))} 秒`
                        : Math.min(left, right) > 0 ? `${(delta / Math.min(left, right) * 100).toFixed(1)}%` : '';
                    note = `${winner} ${row.verb}${difference ? ' · 相差 ' + difference : ''}`;
                }
            }
            return {...row, left: display(a, row.key), right: display(b, row.key), winner, note};
        });
    }
    return {compare};
})();
