const test=require('node:test'),assert=require('node:assert/strict');
const {primaryAnalysisId,referenceLabel}=require('../scripts/report/phylogeography-results.js');
test('primary is balanced set 1 regardless of input ordering or default comparison',()=>{
 const model={default_analysis:'HA/available/replicate_3',analyses:[{id:'HA/available/replicate_3'},{id:'HA/balanced/replicate_2'},{id:'HA/balanced/replicate_1'}]};
 assert.equal(primaryAnalysisId(model),'HA/balanced/replicate_1');
});
test('a missing or failed primary is not replaced by another method or reference set',()=>{
 const model={default_analysis:'HA/available/replicate_1',analyses:[{id:'HA/available/replicate_1',methods:{fast:{status:'passed'}}}]};
 assert.equal(primaryAnalysisId(model),'HA/balanced/replicate_1');
 model.analyses.push({id:'HA/balanced/replicate_1',methods:{},unavailable:{fast:'Temporal check failed'}});
 assert.equal(primaryAnalysisId(model),'HA/balanced/replicate_1');assert.equal(primaryAnalysisId(model,'NA'),'NA/balanced/replicate_1');
});
test('reference labels describe the strategy and use set numbers rather than ranks',()=>{
 assert.equal(referenceLabel('HA/balanced/replicate_1'),'HA · Location/time balanced · Set 1');
 assert.equal(referenceLabel('HA/available/replicate_3'),'HA · Random eligible references · Set 3');
 assert.equal(referenceLabel('NA/diversity/replicate_2'),'NA · Diversity-enriched · Set 2');
});
