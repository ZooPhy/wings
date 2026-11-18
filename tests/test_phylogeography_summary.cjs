const test=require('node:test'),assert=require('node:assert/strict');
const {displayFlows,mostProbableLocation}=require('../scripts/report/phylogeography-results.js');
const t=s=>Date.parse(s);
test('sampled flow counts all jumps by directed pair up to the selected time',()=>{
 const draw={history:{jumps:[{from:'A',to:'B',date:'2024-01-01'},{from:'B',to:'A',date:'2024-02-01'},{from:'A',to:'B',date:'2024-03-01'}]}};
 const before=JSON.stringify(draw);
 assert.deepEqual(displayFlows(null,t('2024-02-01'),draw),[{from:'A',to:'B',mean:1},{from:'B',to:'A',mean:1}]);
 assert.deepEqual(displayFlows(null,t('2024-03-01'),draw),[{from:'A',to:'B',mean:2},{from:'B',to:'A',mean:1}]);
 assert.deepEqual(displayFlows(null,t('2023-12-31'),draw),[]);assert.equal(JSON.stringify(draw),before);
});
test('summary flows average over all draws including zero-event draws',()=>{
 const pair={from:'A',to:'B',times:[t('2024-01-01'),t('2024-03-01')]};
 const pre={N:4,pairs:new Map([['AB',pair]])};
 assert.equal(displayFlows(pre,t('2024-01-02'))[0].mean,.25);
 assert.equal(displayFlows(pre,t('2024-03-01'))[0].mean,.5);
});
test('summary node is the marginal mode with deterministic explicitly reported ties',()=>{
 const states={West:.078,Midwest:.437,South:.36,Kentucky:.125};
 assert.deepEqual(mostProbableLocation(states),{id:'Midwest',probability:.437,tied:['Midwest']});
 assert.deepEqual(mostProbableLocation({B:.5,A:.5}),{id:'A',probability:.5,tied:['A','B']});
 assert.throws(()=>mostProbableLocation({}),/No posterior/);
});
