'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const Chart = require('../utils/video_similarity/assets/chart.umd.min.js');

// Capture the app's chart configuration, then exercise the bundled Chart.js
// hit-testing implementation with actual BarElements at known coordinates.
const elements = new Map(), configurations = new Map();
const document = {getElementById(id) {
    if (!elements.has(id)) elements.set(id, {id, setAttribute() {}});
    return elements.get(id);
}};
class CaptureChart {
    constructor(canvas, config) { configurations.set(canvas.id, config); }
    destroy() {}
}
const context = {document, window:{Chart:CaptureChart}, Chart:CaptureChart};
vm.runInNewContext(fs.readFileSync('utils/video_similarity/assets/library-charts.js', 'utf8'), context);
const counts = [1280,1428,975,719,1091,734,812,1117];
const capacities = [1.56,4.1,4.71,4.86,10.52,9.97,17.08,208.44];
context.window.WorkspaceCharts.render({
    categories:counts.map((count,i) => ({count, total_bytes:capacities[i]*1024**3, label:`Group ${i}`})),
    totals:{count:8156, total_bytes:261.23*1024**3}, size_histogram:[]
});

function verifyRows() {
    const config = configurations.get('category-chart');
    const values = config.data.datasets[0].data;
    const data = values.map((value,i) => new Chart.BarElement({
        x:value/Math.max(...values)*950, y:20+i*40,
        base:0, width:value/Math.max(...values)*950, height:26, horizontal:true
    }));
    const meta = {index:0, data, _sorted:false, controller:{_cachedMeta:{iScale:{axis:'y'}}}};
    const chart = {getSortedVisibleDatasetMetas:() => [meta],
        isPointInArea:({x,y}) => x>=0 && x<=1000 && y>=0 && y<=320};
    const hit = (x,y,options=config.options.interaction) => Chart.Interaction.modes.index(chart,{native:true,x,y},options);
    // Reproduce the old wrong-row selection when x was used for horizontal bars.
    assert.notEqual(hit(700,20,{mode:'index',axis:'x',intersect:false})[0].index,0);
    for (let i=0;i<8;i++) {
        for (const x of [1,150,700,999]) {
            const selected = hit(x,20+i*40);
            assert.equal(selected.length,1);
            assert.equal(selected[0].index,i,`row ${i}, x=${x}`);
        }
    }
    assert.equal(hit(-10,20).length,0);
    assert.equal(hit(100,340).length,0);
}
verifyRows();
document.getElementById('chart-capacity').onclick();
verifyRows();
assert.equal(configurations.get('histogram-chart').options.interaction.axis,'x');
console.log('Chart hover: old bug reproduced; all 8 rows pass at 4 horizontal positions in count and capacity modes; outside-chart hits excluded.');
