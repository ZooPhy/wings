const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Core = require('../assets/wings-metadata-core.js');
const reference = JSON.parse(fs.readFileSync(path.join(__dirname,'../assets/wings-metadata-reference.json'),'utf8'));
const index = Core.buildIndex(reference);
const sample = (id='sample_a',extra={}) => ({sample_id:id,host:'SNGO',specimen_type:'Dry (Oral+Cloacal)',collection_date:'2025-04-13',state:'Quebec',country:'CAN',latitude:'46.8139',longitude:'-71.2080',...extra});
const codes = result => result.errors.map(issue=>issue.code);

test('CSV import handles quoted commas, escaped quotes and multiline notes',()=>{
  const parsed=Core.parseTable('Sample ID,Bird,Notes\r\na,Snow Goose,"one, two\r\nnext ""quoted"" line"\r\n');
  assert.equal(parsed.delimiter,',');assert.deepEqual(parsed.rows,[['a','Snow Goose','one, two\nnext "quoted" line']]);
  const mapped=Core.mapTable(parsed);assert.equal(mapped.rows[0].sample_id,'a');assert.equal(mapped.rows[0].host,'Snow Goose');assert.equal(mapped.rows[0].Notes,'one, two\nnext "quoted" line');
});
test('tab, semicolon, UTF-8 BOM and trailing empty fields are accepted',()=>{
  for(const delimiter of ['\t',';']){
    const parsed=Core.parseTable('\uFEFFsample_id'+delimiter+'host'+delimiter+'notes\na'+delimiter+'BLVU'+delimiter+'\n');
    assert.equal(parsed.delimiter,delimiter);assert.deepEqual(parsed.rows,[['a','BLVU','']]);
  }
  assert.deepEqual(Core.parseTable('sample_id\ta\nb').rows,[['b','']]);
});
test('malformed tables fail without dropping columns or overwriting duplicate headers',()=>{
  for(const source of ['', 'sample_id,sample_id\na,b','sample_id,\na,b','sample_id,host\na,b,c','sample_id,notes\na,"unfinished','sample_id\na"b'])assert.throws(()=>Core.parseTable(source));
  const parsed=Core.parseTable('Sample ID,host,Host Common Name\na,SNGO,Snow Goose');
  assert.throws(()=>Core.mapTable(parsed),/same output column/);
  const mapped=Core.mapTable(parsed,['sample_id','host','Host Common Name']);assert.equal(mapped.rows[0]['Host Common Name'],'Snow Goose');
});
test('header aliases cover province, specimen, date and coordinate names',()=>{
  const parsed=Core.parseTable('Sample ID\tBird\tSample Type\tDate Collected\tProvince/Territory\tCountry Code\tLat\tLng\tExtra\na\tBLVU\tDry (Oral)\t2025-01-01\tQC\tCA\t45\t-71\tretained');
  const mapped=Core.mapTable(parsed);assert.deepEqual(mapped.fields,[...Core.FIELDS,'Extra']);assert.equal(mapped.rows[0].state,'QC');assert.equal(mapped.rows[0].longitude,'-71');assert.equal(mapped.rows[0].Extra,'retained');
});
test('host names standardize to accepted codes and existing aliases are retained',()=>{
  for(const [input,expected] of [['Snow Goose','SNGO'],['black vulture','BLVU'],['Turkey Vulture','TUVU'],['Canada Goose','CAGO'],['CANG','CANG'],['cago','CAGO']])assert.equal(Core.normalizeRows([sample('a',{host:input})],index,'hosts').rows[0].host,expected);
  const unknown=Core.normalizeRows([sample('a',{host:'Unidentified goose'})],index,'hosts');assert.equal(unknown.rows[0].host,'Unidentified goose');assert.equal(unknown.changes.length,0);assert.ok(Core.validate(unknown.rows,[],index).warnings.some(issue=>issue.code==='unknown_host'));
});
test('normalization is a proposal and does not mutate original rows or extra columns',()=>{
  const original=[sample(' a ',{host:'Snow Goose',state:'QC',country:'Canada',Notes:'retain\nthis "note"'})],snapshot=JSON.stringify(original);
  const proposal=Core.normalizeRows(original,index,'all');assert.equal(JSON.stringify(original),snapshot);assert.equal(proposal.rows[0].sample_id,'a');assert.equal(proposal.rows[0].host,'SNGO');assert.equal(proposal.rows[0].state,'Quebec');assert.equal(proposal.rows[0].country,'CAN');assert.equal(proposal.rows[0].Notes,original[0].Notes);assert.ok(proposal.changes.some(change=>change.before==='Snow Goose'&&change.after==='SNGO'));
});
test('countries use ISO alpha-3 and regions are matched within the chosen country',()=>{
  for(const [country,state,outCountry,outState] of [['United States','CA','USA','California'],['Canada','QC','CAN','Quebec'],['CA','Québec','CAN','Quebec'],['United Kingdom','England','GBR','England'],['Australia','NSW','AUS','New South Wales']]){
    const row=Core.normalizeRows([sample('a',{country,state})],index,'collection').rows[0];assert.equal(row.country,outCountry);assert.equal(row.state,outState);
  }
  assert.equal(Core.regionMatch('CA','CAN',index),null);assert.equal(Core.regionMatch('Ontario','USA',index),null);assert.equal(reference.countries.length,249);
});
test('dates use strict calendar validation and ambiguous source dates require a choice',()=>{
  for(const [value,valid] of [['2024-02-29',true],['2025-02-29',false],['2025-04-31',false],['0000-01-01',false],['2025-13-01',false],['2025-1-1',false]])assert.equal(Core.validDate(value),valid,value);
  assert.equal(Core.normalizeDate('03/04/2025'),'03/04/2025');assert.equal(Core.normalizeDate('03/04/2025','DMY'),'2025-04-03');assert.equal(Core.normalizeDate('03/04/2025','MDY'),'2025-03-04');
  assert.equal(Core.normalizeDate('13/04/2025'),'2025-04-13');assert.equal(Core.normalizeDate('2025-4-3'),'2025-04-03');assert.equal(Core.normalizeDate('31/02/2025','DMY'),'31/02/2025');
  assert.equal(Core.normalizeRows([sample('2025-10-20_barcode04',{collection_date:''})],index).rows[0].collection_date,'');
});
test('region choices follow country and incompatible imported pairs block export',()=>{
  const german=Core.regionsForCountry('Germany',index);
  assert.equal(german.length,16);assert.ok(german.some(region=>region.name==='Berlin'));
  assert.equal(german.some(region=>region.name==='New York'),false);
  assert.equal(Core.regionMatch('New York','Germany',index),null);
  assert.ok(codes(Core.validate([sample('a',{country:'DEU',state:'New York'})],['a.fastq.gz'],index)).includes('unknown_region'));
  assert.equal(Core.validate([sample('a',{country:'DEU',state:'Berlin'})],['a.fastq.gz'],index).errors.length,0);
  assert.ok(codes(Core.validate([sample('a',{country:'USA',state:'Ontario'})],['a.fastq.gz'],index)).includes('unknown_region'));
  assert.equal(Core.regionMatch('DE-BY','DEU',index).name,'Bayern');
  assert.equal(Core.regionMatch('BY','Germany',index).name,'Bayern');
  const changed=Core.normalizeRows([sample('a',{country:'Australia',state:'NSW'})],index,'collection');
  assert.equal(changed.rows[0].state,'New South Wales');
});
test('coordinates are validated without guessed locations or silent axis swapping',()=>{
  for(const [latitude,longitude] of [['NaN','-71'],['Infinity','-71'],['91','0'],['0','181'],['0x01','0'],['1,23','0']])assert.ok(codes(Core.validate([sample('a',{latitude,longitude})],['a.fastq.gz'],index)).includes('coordinate'));
  assert.equal(Core.validate([sample('a',{latitude:'0',longitude:'0'})],['a.fastq.gz'],index).errors.length,0);
  const row=Core.normalizeRows([sample('a',{latitude:'46.8 N',longitude:'71.2 W'})],index,'collection').rows[0];assert.equal(row.latitude,'46.8');assert.equal(row.longitude,'-71.2');
  const blank=Core.normalizeRows([sample('a',{latitude:'',longitude:''})],index,'collection').rows[0];assert.equal(blank.latitude,'');assert.equal(blank.longitude,'');
});
test('sample matching preserves case and read suffixes while checking duplicate IDs',()=>{
  for(const name of ['a.fastq.gz','a.fq.gz','a.fastq','a.fq'])assert.equal(Core.stripFastq(name),'a');
  assert.equal(Core.stripFastq('sample_R1.fastq.gz'),'sample_R1');
  assert.ok(codes(Core.validate([sample('a'),sample('a')],['a.fastq.gz'],index)).includes('duplicate_id'));
  assert.ok(codes(Core.validate([sample('A')],['a.fastq.gz'],index)).includes('unmatched_id'));
  assert.ok(codes(Core.validate([sample('a'),sample('b')],['a.fastq.gz'],index)).includes('unmatched_id'));
  assert.ok(codes(Core.validate([sample('a')],['a.fastq.gz','b.fastq.gz'],index)).includes('missing_metadata'));
});
test('duplicate FASTQ stems, mixed extensions and unsupported filenames are blocking',()=>{
  assert.ok(codes(Core.validate([sample('a')],['a.fastq','a.fastq.gz'],index)).includes('duplicate_fastq'));
  assert.ok(codes(Core.validate([sample('a'),sample('b')],['a.fastq','b.fastq.gz'],index)).includes('mixed_extensions'));
  assert.ok(codes(Core.validate([sample('a')],['a.gz'],index)).includes('extension'));
});
test('filename suggestions are returned for explicit confirmation, not applied',()=>{
  const files=['run1_barcode04.fastq.gz','run2_barcode04.fastq.gz','run1_barcode040.fastq.gz'];
  assert.deepEqual(Core.suggestIds('barcode04',files),['run1_barcode04','run2_barcode04']);
  const rows=[sample('barcode04')];Core.suggestIds(rows[0].sample_id,files);assert.equal(rows[0].sample_id,'barcode04');
  assert.deepEqual(Core.suggestIds('sample a',['sample_a.fastq.gz']),['sample_a']);
});
test('schema-required fields are distinguished from missing optional collection details',()=>{
  const row=Object.fromEntries(Core.FIELDS.map(field=>[field,field==='sample_id'?'a':'']));
  const result=Core.validate([row],['a.fastq.gz'],index);assert.equal(result.errors.length,0);assert.equal(result.exactMatch,true);assert.equal(result.complete,0);assert.equal(result.warnings.length,7);
  assert.ok(Core.validate([sample('a')],[],index).warnings.some(issue=>issue.code==='reads_pending'));
  assert.equal(Core.validate([sample('a')],['a.fastq.gz'],index).complete,1);
});
test('TSV export round-trips quoted notes and the run-form parser rejects duplicate or empty IDs',()=>{
  const rows=[sample('a',{notes:'comma, tab\t and "quotes"\nnext line'}),sample('b',{notes:'<img src=x onerror=alert(1)>'})],fields=[...Core.FIELDS,'notes'];
  const output=Core.toTSV(fields,rows),parsed=Core.parseTable(output,'\t');
  assert.deepEqual(Core.inspectIds(output),['a','b']);assert.equal(parsed.rows[0].at(-1),rows[0].notes);assert.equal(parsed.rows[1].at(-1),rows[1].notes);
  assert.throws(()=>Core.inspectIds('sample_id\thost\na\tBLVU\na\tCAGO'),/duplicate/);
  assert.throws(()=>Core.inspectIds('sample_id\thost\n\tBLVU'),/empty sample_id/);
  assert.throws(()=>Core.inspectIds('\uFEFFsample_id\na'),/UTF-8 BOM/);
});
test('CSV-to-WINGS workflow keeps every row and produces exact FASTQ matches',()=>{
  const parsed=Core.parseTable('ID,Bird,Sample type,Date,Province,Country,Lat,Long,Notes\na,Snow Goose,Dry (Oral+Cloacal),13/04/2025,QC,Canada,46.8 N,71.2 W,retained\nb,CAGO,Dry (Oral),2025-04-15,KY,USA,38,-85,other');
  const mapped=Core.mapTable(parsed),proposal=Core.normalizeRows(mapped.rows,index,'all'),result=Core.validate(proposal.rows,['a.fastq.gz','b.fastq.gz'],index);
  assert.equal(result.errors.length,0);assert.equal(result.warnings.length,0);assert.equal(result.complete,2);assert.equal(result.exactMatch,true);
  assert.deepEqual(Core.inspectIds(Core.toTSV(mapped.fields,proposal.rows)),['a','b']);assert.equal(proposal.rows[0].Notes,'retained');
});
