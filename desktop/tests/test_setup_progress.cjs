const assert = require('node:assert/strict');
const {test} = require('node:test');
const {view} = require('../setup-progress.js');
const s = {phase:4,code:'build',status:'running',started:1000,heartbeat:1120,lastOutput:1001,browserOpened:false};
test('Real completed steps, elapsed time and quiet-but-running heartbeat',()=>{
 const v=view(s,1122); assert.equal(v.completed,3);assert.equal(v.elapsed,'2m 2s');
 assert.match(v.detail,/Building the BLAST/);assert.match(v.activity,/No new output/);assert.equal(v.stale,false);
});
test('Missing heartbeat stops claiming running; recovering heartbeat restores active status',()=>{
 const v=view(s,1140); assert.equal(v.stale,true);assert.match(v.title,/Waiting/);assert.doesNotMatch(v.activity,/is running/);
 assert.equal(view({...s,heartbeat:1140},1141).stale,false);
});
test('Success alone completes progress; elapsed time freezes at completion',()=>{
 const v=view({...s,status:'ready',phase:6,browserOpened:true},1300);
 assert.equal(v.completed,6);assert.equal(v.elapsed,'2m 0s');assert.match(v.detail,/another browser/);
 assert.match(view({...s,status:'ready'},1300).detail,/could not open/);
});
test('Failure keeps pending steps incomplete; known errors offer action',()=>{
 const v=view({...s,status:'failed',error:'disk'},1300);assert.equal(v.completed,3);assert.equal(v.failure,true);assert.match(v.detail,/disk is full/);
 assert.match(view({...s,status:'failed',error:'older'},1300).detail,/Finish its jobs/);
});
test('Only fixed messages can reach the page',()=>{
 const v=view({...s,status:'failed',error:'<script>secret</script>',code:'token'},1300);
 assert.doesNotMatch(JSON.stringify(v),/<script>|secret|token/);
});
