'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('utils/video_similarity/assets/workspace.js','utf8');
const nodes = new Map();
const $ = id => {
    if (!nodes.has(id)) nodes.set(id,{textContent:'',open:false});
    return nodes.get(id);
};
let calls=[], confirm=false, fail=false;
const context=vm.createContext({
    $, connected:true, activeTask:null, submitting:false, cacheStatusInFlight:null,
    tasks:[{id:'old'}], totalGroups:3, detailTask:null,
    count:String, bytes:value => `${value} B`, timeText:String, updateButtons() {}, notice() {},
    async confirmAction() { return confirm; },
    async pollTasks() { context.tasks=[]; },
    async api(route,options) {
        calls.push({route,options});
        if (fail) throw new Error('unavailable');
        return route.endsWith('/status') ? {count:2,bytes:120,checked_at:'now',error_count:0} : {cleared_count:1};
    }
});
vm.runInContext(source.slice(source.indexOf('async function refreshCacheStatus()'),source.indexOf('function distribution(')),context);
(async () => {
    await Promise.all([context.refreshCacheStatus(),context.refreshCacheStatus()]);
    assert.equal(calls.length,1,'Concurrent refreshes share one read');
    assert.equal(calls[0].options,undefined,'Status read must not submit a task');
    assert.equal($('cache-orphan-count').textContent,'2 个');
    assert.equal($('cache-orphan-bytes').textContent,'120 B');
    fail=true; await context.refreshCacheStatus();
    assert.match($('cache-orphan-status').textContent,/检查失败/);
    assert.equal($('cache-orphan-count').textContent,'2 个','Failure cannot be shown as zero');
    fail=false; calls=[];
    await context.clearHistory(); assert.equal(calls.length,0);
    confirm=true; context.activeTask={id:'running'};
    await context.clearHistory(); assert.equal(calls.length,0);
    context.activeTask=null; await context.clearHistory();
    assert.equal(calls.length,1);
    assert.equal(calls[0].route,'/api/tasks/clear');
    assert.equal(calls[0].options.method,'POST');
    assert.equal(context.totalGroups,3);
    assert.equal(context.tasks.length,0);
    assert.equal(context.submitting,false);
    console.log('Maintenance: deduplicated read-only cache status, visible failure, cancelled/busy history clear and preserved review count pass.');
})().catch(error => { console.error(error); process.exitCode=1; });
