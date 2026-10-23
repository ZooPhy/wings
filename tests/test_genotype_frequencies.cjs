const {test} = require('node:test');
const assert = require('node:assert/strict');
const {validate, summarize, csvExport, monthRange, chartRows, combineSources} = require('../assets/wings-genotypes.js');
const group = (month, genotype, n, extra={}) => ({month, genotype, n, host:'Bird', location:'USA/Kentucky//', status:genotype ? 'assigned' : 'unassigned', ...extra});
const data = groups => ({schema_version:'wings.genotype-frequencies.v1', unit:'SRA run', has_metadata:true, groups, audit:{included_runs:groups.reduce((s,g)=>s+g.n,0), assigned_runs:groups.filter(g=>g.status==='assigned').reduce((s,g)=>s+g.n,0)}});

test('assigned denominator excludes unavailable calls while retaining coverage', () => {
  const d=data([group('2025-01','D1.1',3),group('2025-01','B3.13',1),group('2025-01',null,6)]);
  const s=summarize(validate(d));
  assert.equal(s.total,10); assert.equal(s.assigned,4); assert.equal(s.rows[0].denominator,4);
  assert.deepEqual(s.rows[0].values.map(v=>v.share),[.75,.25]);
  const all=summarize(d,{denominator:'all'});
  assert.equal(all.rows[0].denominator,10); assert.equal(all.rows[0].values.at(-1).share,.6);
});
test('monthly percentages use each months denominator, not the entire collection', () => {
  const d=data([group('2025-01','D1.1',3),group('2025-01','B3.13',1),group('2025-03','D1.1',1),group('2025-03','B3.13',9)]);
  const s=summarize(d,{view:'monthly'});
  assert.equal(s.rows.length,3); assert.equal(s.rows[1].denominator,0);
  assert.ok(s.rows[1].values.every(v=>v.share===null));
  assert.equal(s.rows[0].values.find(v=>v.key==='call:D1.1').share,.75);
  assert.equal(s.rows[2].values.find(v=>v.key==='call:D1.1').share,.1);
});
test('missing dates contribute overall but never get an invented month', () => {
  const d=data([group(null,'D1.1',2),group('2025-02','B3.13',3)]);
  assert.equal(summarize(d).assigned,5);
  const monthly=summarize(d,{view:'monthly'});
  assert.equal(monthly.assigned,3); assert.equal(monthly.excludedDates,2);
});
test('host and location filters change both numerator and denominator', () => {
  const d=data([group('2025-01','D1.1',4),group('2025-01','B3.13',5,{host:'Cattle'}),group('2025-01','B3.13',3,{location:'USA/Texas//'})]);
  const s=summarize(d,{host:'Bird',location:'USA/Kentucky//'});
  assert.equal(s.total,4); assert.equal(s.rows[0].values[0].share,1);
});
test('rare genotypes aggregate only in the chart and remain separate in export', () => {
  const d=data(Array.from({length:12},(_,i)=>group('2025-01',`D1.${i+1}`,i+1)));
  const s=summarize(d);
  assert.equal(s.series.length,11); assert.equal(s.rows[0].values.at(-1).key,'other');
  assert.equal(s.rows[0].values.at(-1).n,3);
  assert.equal(s.rows[0].values.reduce((n,v)=>n+v.n,0),78);
  assert.equal(csvExport(s).trim().split('\r\n').length,13);
});
test('invalid counts, mismatched totals, and dates are rejected', () => {
  for (const g of [group('2025-13','D1.1',1),group('2025-01','D1.1',-1),group('2025-01','D1.1',1.5)]) assert.throws(()=>validate(data([g])));
  const d=data([group('2025-01','D1.1',1)]); d.audit.included_runs=10; assert.throws(()=>validate(d));
  assert.throws(()=>summarize(d,{from:'2025-03',through:'2025-01'}));
});
test('metadata required for monthly views and unsupported categories cannot disappear', () => {
  const d=data([group(null,null,2,{status:'unrecognized_call'})]); d.has_metadata=false;
  assert.throws(()=>summarize(d,{view:'monthly'}));
  const s=summarize(d,{denominator:'all'});
  assert.equal(s.rows[0].values[0].share,1);
  assert.equal(summarize(d).rows[0].denominator,0);
});
test('inclusive month ranges preserve zero-data gaps across years', () => {
  assert.deepEqual(monthRange('2024-12','2025-02'),['2024-12','2025-01','2025-02']);
});
test('compact display preserves counts, percentages, and export across a calendar gap', () => {
  const s=summarize(data([group('2025-01','D1.1',1),group('2025-03','B3.13',9)]),{view:'monthly'});
  const before=csvExport(s);
  const visible=chartRows(s);
  assert.deepEqual(visible.map(row=>row.period),['2025-01','2025-03']);
  assert.equal(visible.reduce((n,row)=>n+row.denominator,0),10);
  assert.equal(visible[0].values.find(v=>v.key==='call:D1.1').share,1);
  assert.equal(s.rows.length,3);
  assert.equal(csvExport(s),before);
  assert.deepEqual(chartRows(s,true).map(row=>row.period),['2025-01','2025-02','2025-03']);
});
test('months with only unassigned runs appear when all runs are the denominator', () => {
  const d=data([group('2025-01','D1.1',1),group('2025-02',null,4),group('2025-03','B3.13',2)]);
  assert.equal(chartRows(summarize(d,{view:'monthly'})).length,2);
  const s=summarize(d,{view:'monthly',denominator:'all'});
  assert.equal(chartRows(s).length,3);
  assert.equal(chartRows(s)[1].values.find(v=>v.key==='status:unassigned').share,1);
  assert.equal(chartRows(summarize(d)).length,1);
});
test('genotype selection retains the denominator for the selected public cohort', () => {
  const d=data([group('2025-01','D1.1',3),group('2025-01','B3.13',7),group('2025-01',null,10)]);
  const assigned=summarize(d,{genotype:'D1.1'});
  assert.deepEqual(assigned.series,['call:D1.1']);
  assert.equal(assigned.genotypeRuns,3);
  assert.equal(assigned.rows[0].denominator,10);
  assert.equal(assigned.rows[0].values[0].share,.3);
  const all=summarize(d,{genotype:'D1.1',denominator:'all'});
  assert.equal(all.rows[0].denominator,20);
  assert.equal(all.rows[0].values[0].share,.15);
  assert.equal(all.total,20);
});
test('selected genotype zeros remain distinct from unavailable monthly frequencies', () => {
  const d=data([group('2025-01','D1.1',1),group('2025-03','B3.13',4)]);
  const s=summarize(d,{view:'monthly',genotype:'D1.1'});
  assert.deepEqual(s.rows.map(r=>r.values[0].share),[1,null,0]);
  assert.deepEqual(chartRows(s).map(r=>r.period),['2025-01','2025-03']);
  const rows=csvExport(s).trim().split('\r\n');
  assert.equal(rows.length,4);
  assert.match(rows[2],/"2025-02","D1.1","0","Assigned runs","0",""/);
  assert.match(rows[3],/"2025-03","D1.1","0","Assigned runs","4","0.000000"/);
});
test('rare genotype selection and combined filters preserve cohort counts', () => {
  const d=data([...Array.from({length:12},(_,i)=>group('2025-01',`D1.${i+1}`,i+1)),group('2025-01','D1.1',10,{host:'Cattle'})]);
  const s=summarize(d,{genotype:'D1.1',host:'Bird',location:'USA/Kentucky//',from:'2025-01',through:'2025-01'});
  assert.equal(s.rows[0].denominator,78);
  assert.equal(s.rows[0].values[0].n,1);
  assert.equal(s.rows[0].values[0].share,1/78);
  assert.equal(csvExport(s).trim().split('\r\n').length,2);
  assert.throws(()=>summarize(d,{genotype:'Unknown'}),/Choose a recorded genotype/);
});
test('WINGS samples have independent audit totals, denominator labels and export units', () => {
  const groups=[group('2025-04','D1.1',13),group('2025-04','Minor114',1),group('2025-04',null,14),group('2025-04',null,2,{status:'not_eligible'})];
  const d={schema_version:'wings.genotype-frequencies.v1',unit:'WINGS sample',has_metadata:true,groups,audit:{included_samples:30,assigned_samples:14}};
  const selected=summarize(validate(d),{genotype:'D1.1'});
  assert.equal(selected.total,30);assert.equal(selected.rows[0].denominator,14);
  assert.equal(selected.rows[0].values[0].share,13/14);
  assert.equal(summarize(d,{genotype:'D1.1',denominator:'all'}).rows[0].values[0].share,13/30);
  const csv=csvExport(selected);
  assert.match(csv,/"sample_count"/);assert.match(csv,/"Assigned samples"/);
  assert.match(csv,/"WINGS","WINGS sample"/);assert.doesNotMatch(csv,/"SRA run"/);
  const bad={...d,audit:{included_runs:30,assigned_runs:14}};
  assert.throws(()=>validate(bad),/audit totals/);
});
const localData = groups => ({...data(groups),unit:'WINGS sample',audit:{included_samples:groups.reduce((n,g)=>n+g.n,0),assigned_samples:groups.filter(g=>g.status==='assigned').reduce((n,g)=>n+g.n,0)}});
test('All shares months and categories but preserves each source denominator',()=>{
  const local=localData([group('2025-01','D1.1',4),group('2025-01','B3.13',1),group('2025-03','D1.1',2)]);
  const pub=data([group('2025-01','D1.1',3),group('2025-01','B3.13',7)]);
  const result=summarize(combineSources([local,pub]),{view:'monthly',genotype:'D1.1'});
  assert.deepEqual(result.parts[0].rows.map(r=>r.period),result.parts[1].rows.map(r=>r.period));
  assert.equal(result.parts[0].rows[0].values[0].share,.8);
  assert.equal(result.parts[1].rows[0].values[0].share,.3);
  assert.equal(result.parts[0].rows[2].values[0].share,1);
  assert.equal(result.parts[1].rows[2].values[0].share,null);
  assert.deepEqual(chartRows(result).map(r=>r.period),['2025-01','2025-03']);
  assert.equal(chartRows(result,true).length,3);
  const csv=csvExport(result);
  assert.match(csv,/"2025-01","D1.1","4","Assigned samples","5","80.000000","WINGS","WINGS sample"/);
  assert.match(csv,/"2025-01","D1.1","3","Assigned runs","10","30.000000","Public Data","SRA run"/);
});
test('All can select a genotype present in only one source without removing the other denominator',()=>{
  const local=localData([group('2025-04','Minor114',1),group(null,'D1.1',2)]);
  const pub=data([group('2025-04','D1.1',10)]);
  const result=summarize(combineSources([local,pub]),{view:'monthly',genotype:'Minor114'});
  assert.equal(result.parts[0].rows[0].values[0].share,1);
  assert.equal(result.parts[0].excludedDates,2);
  assert.equal(result.parts[1].rows[0].values[0].share,0);
  assert.equal(result.parts[1].rows[0].denominator,10);
  assert.throws(()=>summarize(combineSources([local,pub]),{genotype:'Nonexistent'}));
});
test('All applies metadata and inclusive date filters to each source and preserves unassigned records',()=>{
  const local=localData([group('2025-01','D1.1',1),group('2025-02','D1.1',2),group('2025-02',null,2)]);
  const pub=data([group('2025-02','D1.1',4),group('2025-02','B3.13',6),group('2025-02','D1.1',20,{host:'Cattle'})]);
  const result=summarize(combineSources([local,pub]),{view:'monthly',denominator:'all',host:'Bird',location:'USA/Kentucky//',from:'2025-02',through:'2025-02'});
  assert.equal(result.parts[0].rows[0].denominator,4);
  assert.equal(result.parts[1].rows[0].denominator,10);
  for(const p of result.parts)assert.equal(p.rows[0].values.reduce((n,v)=>n+v.n,0),p.rows[0].denominator);
  assert.deepEqual(result.parts[0].rows[0].values.map(v=>v.key),result.parts[1].rows[0].values.map(v=>v.key));
});
test('All supports one available source and rejects duplicate sources',()=>{
  const pub=data([group('2025-01','D1.1',3)]);
  assert.equal(summarize(combineSources([pub]),{view:'monthly'}).parts.length,1);
  assert.throws(()=>combineSources([pub,pub]),/distinct data sources/);
});
