'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('utils/video_similarity/assets/workspace.js', 'utf8');
const nodes = new Map();
const $ = id => {
    if (!nodes.has(id)) nodes.set(id, {textContent:'', innerHTML:''});
    return nodes.get(id);
};
const pair = {videos:[{name:'A.mp4',originalPath:'C:/Downloads/A.mp4'},
                      {name:'B.mp4',originalPath:'D:/Library/B.mp4'}]};
const task = {id:'scan',kind:'incremental_downloads',state:'complete',label:'Scan',
              result:{mode:'incremental_downloads',active_count:5,missing_count:0}};
let requests = [], confirmations = [];
const context = vm.createContext({
    $, currentPair:pair, currentIndex:0, totalGroups:5, connected:true,
    submitting:false, activeTask:null, pairLoading:false, libraryStatus:null,
    document:{activeElement:null}, stateNames:{complete:'已完成'},
    count:String,bytes:String,escapeHtml:String,timeText:() => 'time',
    updateButtons() {},renderDownloadWorkflow() {},
    notice(message, success) { assert.ok(success, message); },refreshDownloads() {},refreshLibrary() {},
    async confirmAction(...args) { confirmations.push(args); return true; },
    async api(route, options) {
        if (route.startsWith('/api/tasks/')) return {task};
        requests.push({route,body:JSON.parse(options.body)});
        return {total:context.totalGroups - 1};
    },
    async loadPair() { context.updatePairCount(); }
});
for (const [start,end] of [
    ['function resultSummary(', 'async function showTask('],
    ['function updatePairCount()', 'function destroyPlayers()'],
    ['async function review(', 'async function openExplorer(']
]) vm.runInContext(source.slice(source.indexOf(start),source.indexOf(end)), context);
for (const id of ['delete-a','delete-b','keep-both']) {
    vm.runInContext(source.split('\n').find(line => line.startsWith(`$('${id}').onclick`)),context);
}

(async () => {
    await context.renderLatestResult('scan');
    assert.doesNotMatch($('latest-result').innerHTML,/扫描完成时|失效组/);
    assert.match($('latest-review-status').textContent,/当前待审阅 5 组/);
    for (const [id,index] of [['delete-a',0],['delete-b',1]]) {
        context.currentPair=pair; context.totalGroups=5; requests=[];
        await $(id).onclick();
        assert.equal(requests.length,1);
        assert.equal(requests[0].route,'/api/prune');
        assert.deepEqual(requests[0].body.files,[pair.videos[index].originalPath]);
        assert.ok(confirmations.at(-1)[1].includes(pair.videos[index].originalPath));
        assert.equal(confirmations.at(-1)[2],'删除');
        assert.match($('latest-review-status').textContent,/当前待审阅 4 组/);
        await context.renderLatestResult('scan');
        assert.match($('latest-review-status').textContent,/当前待审阅 4 组/);
        assert.doesNotMatch($('latest-result').innerHTML,/扫描完成时|失效组/);
        assert.match(context.resultSummary(task.result),/扫描完成时待审阅组 5/);
        assert.equal(task.result.active_count,5);
    }
    context.totalGroups=1;
    await $('delete-a').onclick();
    assert.match($('latest-review-status').textContent,/当前待审阅 0 组/);
    requests=[];
    context.notice=() => {};
    context.confirmAction=async () => false;
    await $('delete-a').onclick();
    assert.equal(requests.length,0);
    context.confirmAction=async () => { context.currentPair={videos:[]}; return true; };
    await $('delete-b').onclick();
    assert.equal(requests.length,0);
    context.connected=false;context.updateLatestReviewStatus();
    assert.match($('latest-review-status').textContent,/暂不可用/);
    const articles = fs.readFileSync('utils/video_similarity/templates/report_template.html','utf8').match(/<article class="video-container">.*?<\/article>/g);
    for (const [i,side] of ['a','b'].entries()) {
        assert.ok(articles[i].includes(`id="player-${side}"`));
        assert.ok(articles[i].includes(`id="delete-${side}"`));
        assert.ok(articles[i].includes('删除此视频'));
    }
    console.log('Review: each red button deletes its own video; cancel/stale pair cannot delete; live count updates independently of scan history.');
})().catch(error => { console.error(error); process.exitCode=1; });
