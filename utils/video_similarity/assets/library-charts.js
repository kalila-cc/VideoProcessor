'use strict';

window.WorkspaceCharts = (() => {
    let categoryChart, histogramChart, latest, metric = 'count';
    const number = value => Number(value).toLocaleString('zh-CN');
    const capacity = value => `${(value / 1024 ** 3).toLocaleString('zh-CN', {maximumFractionDigits: 2})} GiB`;
    const axis = {ticks:{color:'#b4c3bb', font:{size:11}}, grid:{color:'#303b36'}, border:{display:false}};
    function options(interactionAxis = 'x') {
        return {responsive:true, maintainAspectRatio:false, animation:false,
            interaction:{mode:'index', axis:interactionAxis, intersect:false},
            plugins:{legend:{display:false}, tooltip:{backgroundColor:'#26362e', padding:12, titleColor:'#f0f5f2', bodyColor:'#dce7e0'}}};
    }
    function drawCategory() {
        if (!latest || !window.Chart) return;
        categoryChart?.destroy();
        const rows = latest.categories, isCount = metric === 'count';
        const total = isCount ? latest.totals.count : latest.totals.total_bytes;
        const format = value => isCount ? number(value) + ' 个' : capacity(value);
        const values = rows.map(row => row[isCount ? 'count' : 'total_bytes']);
        categoryChart = new Chart(document.getElementById('category-chart'), {
            type:'bar', data:{labels:rows.map(row => row.label), datasets:[{
                label:isCount ? '视频数量' : '占用容量', data:values,
                backgroundColor:'#79b49c', hoverBackgroundColor:'#acd8c5', borderRadius:3, maxBarThickness:27
            }]}, options:{...options('y'), indexAxis:'y',
                scales:{x:{...axis, beginAtZero:true, ticks:{...axis.ticks, callback:v => isCount ? number(v) : capacity(v)}}, y:{...axis, grid:{display:false}}},
                plugins:{...options().plugins, tooltip:{...options().plugins.tooltip, callbacks:{label:ctx => `${format(ctx.raw)} · ${total ? (ctx.raw / total * 100).toFixed(2) : 0}%`}}}
            }
        });
        const nonempty = values.filter(value => value > 0);
        document.getElementById('category-insight').textContent = !nonempty.length ? '视频库暂无视频，完成入库后会显示分布。'
            : isCount ? `每组 ${number(Math.min(...values))}–${number(Math.max(...values))} 个视频；悬停查看占比。`
            : `最大的分组占总容量 ${(Math.max(...values) / total * 100).toFixed(1)}%；容量分布与数量分布不同。`;
        document.getElementById('chart-count').setAttribute('aria-pressed', String(isCount));
        document.getElementById('chart-capacity').setAttribute('aria-pressed', String(!isCount));
    }
    function render(data) {
        latest = data;
        const status = document.getElementById('library-chart-status');
        if (!window.Chart) { status.textContent = '图表组件未加载，下方数据明细仍可查看。'; return; }
        status.textContent = data.totals.count ? '悬停查看数值；左图可切换数量与容量。' : '视频库暂无视频，完成入库后会显示分布。';
        drawCategory();
        histogramChart?.destroy();
        const rows = data.size_histogram;
        let sum = 0;
        const cumulative = rows.map(row => { sum += row.count; return data.totals.count ? sum / data.totals.count * 100 : 0; });
        histogramChart = new Chart(document.getElementById('histogram-chart'), {
            type:'bar', data:{labels:rows.map(row => row.label), datasets:[
                {label:'视频数量', data:rows.map(row => row.count), backgroundColor:'#79b49c', hoverBackgroundColor:'#acd8c5', borderRadius:2, yAxisID:'y', order:2},
                {type:'line', label:'累计占比', data:cumulative, borderColor:'#d5ded9', backgroundColor:'#d5ded9', borderWidth:2, pointRadius:2, pointHoverRadius:5, yAxisID:'percent', order:1}
            ]}, options:{...options(), scales:{
                x:{...axis, grid:{display:false}, ticks:{...axis.ticks, maxRotation:60, minRotation:40, autoSkip:false}},
                y:{...axis, beginAtZero:true, title:{display:true,text:'视频数',color:'#b4c3bb'}},
                percent:{...axis, position:'right', min:0,max:100,grid:{drawOnChartArea:false}, ticks:{...axis.ticks, callback:v => v+'%'}}
            }, plugins:{...options().plugins, legend:{display:true, labels:{color:'#c6d3cc', boxWidth:12, boxHeight:8}},
                tooltip:{...options().plugins.tooltip, callbacks:{label:ctx => ctx.dataset.yAxisID === 'percent' ? `累计 ${ctx.raw.toFixed(1)}%` : `${number(ctx.raw)} 个 · ${rows[ctx.dataIndex].count_percent}%`}}}}
        });
    }
    document.getElementById('chart-count').onclick = () => { metric = 'count'; drawCategory(); };
    document.getElementById('chart-capacity').onclick = () => { metric = 'total_bytes'; drawCategory(); };
    return {render};
})();
