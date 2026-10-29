const {test}=require('node:test');
const assert=require('node:assert/strict');
const api=require('../scripts/report/genome-braid-clock.js');
for (const status of ['UNAVAILABLE_DOWNLOAD','UNAVAILABLE_MISSING_ACCESS_KEY','NO_STATUS_PRODUCT']) {
  test(`${status} retains reason and does not create an abundance profile`,()=>{
    const reason='Unavailable: data could not be obtained';
    const data=api.validatePhenology({schema_version:'wings.phenology.v1',synthetic:false,profiles:[],sample_status:[{sample_id:'A',status,reason,collection_week_value:null}]});
    const record=api.clockRecord({sample_id:'A',host:'Canada Goose',country:'US',state:'KY',collection_date:'2025-05-01'},data);
    assert.equal(record.status,status);
    assert.equal(record.reason,reason);
    assert.equal(record.profile,undefined);
  });
}
