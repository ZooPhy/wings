// Run with: node tests/test_metadata_wizard_browser.cjs (Playwright + Chromium).
const assert=require('node:assert/strict');
const fs=require('node:fs');
const http=require('node:http');
const path=require('node:path');
const {chromium}=require('playwright');
const Core=require('../assets/wings-metadata-core.js');
const root=path.resolve(__dirname,'..');
const mutations=[];
const server=http.createServer((request,response)=>{
  const url=new URL(request.url,'http://127.0.0.1');
  if(request.method!=='GET')mutations.push(url.pathname);
  if(url.pathname==='/api/runs'){response.setHeader('Content-Type','application/json');response.end('[]');return;}
  if(url.pathname==='/api/health'){response.setHeader('Content-Type','application/json');response.end(JSON.stringify({snakemake_available:false,config_yaml_present:false}));return;}
  const file=path.resolve(root,'.'+decodeURIComponent(url.pathname));
  if(!file.startsWith(root+path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()){response.writeHead(404);response.end('Not found');return;}
  const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.jpg':'image/jpeg','.svg':'image/svg+xml'};
  response.setHeader('Content-Type',types[path.extname(file)] || 'application/octet-stream');response.end(fs.readFileSync(file));
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let browser;
  try {
    browser=await chromium.launch({headless:true,...(process.env.WINGS_BROWSER_EXECUTABLE?{executablePath:process.env.WINGS_BROWSER_EXECUTABLE}:{})});
    const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/run.html?new=1`);
    await page.locator('#readsFiles').setInputFiles([
      {name:'sample_a.fastq.gz',mimeType:'application/gzip',buffer:Buffer.from('fixture')},
      {name:'sample_b.fastq.gz',mimeType:'application/gzip',buffer:Buffer.from('fixture')},
    ]);
    await page.locator('.step-button[data-step="2"]').click();
    await page.locator('#openMetadataWizard').click();
    const dialog=page.locator('#metadataWizard');await dialog.waitFor({state:'visible'});
    const hostOptions=await dialog.locator('#mwHostNames option').evaluateAll(options=>options.map(option=>({value:option.value,label:option.label})));
    assert.deepEqual(hostOptions.filter(option=>option.label.startsWith('Mexican Duck · ')),[{value:'MEDU',label:'Mexican Duck · MEDU'}]);
    assert.equal(hostOptions.filter(option=>option.label.startsWith('Canada Goose · ')).length,1);
    assert.equal(hostOptions.some(option=>option.value==='Mexican Duck'),false);
    assert.equal(new Set(hostOptions.map(option=>option.label.split(' · ')[0])).size,hostOptions.length);
    const csv='Sample ID,Bird,Date collected,Province,Country,Lat,Long,Notes\nsample_a,Snow Goose,13/04/2025,QC,Canada,46.8139,-71.2080,"one ""quoted"" note\nsecond line"\nsample_b,CAGO,2025-04-15,KY,United States,38,-85,other';
    await dialog.locator('#mwPaste').fill(csv);await dialog.locator('[data-action="paste"]').click();await dialog.locator('[data-action="map"]').click();
    await dialog.locator('[data-action="step"][data-step="2"]').click();await dialog.locator('[data-action="normalize"]').click();await dialog.locator('[data-action="apply"]').click();
    const hostInput=dialog.locator('input[data-row="0"][data-field="host"]');
    await hostInput.fill('MEDU');await hostInput.press('Tab');
    assert.match(await hostInput.locator('..').innerText(),/Mexican Duck/);
    await hostInput.fill('SNGO');await hostInput.press('Tab');
    await dialog.locator('[data-action="step"][data-step="3"]').click();
    for(const row of [0,1])await dialog.locator(`select[data-row="${row}"][data-field="specimen_type"]`).selectOption('Oropharyngeal + Cloacal');
    await dialog.locator('[data-action="normalize"]').click();await dialog.locator('[data-action="apply"]').click();
    await dialog.locator('[data-action="step"][data-step="4"]').click();
    assert.match(await dialog.locator('#mwSummary').innerText(),/0 errors · 0 warnings/);
    const [download]=await Promise.all([page.waitForEvent('download'),dialog.locator('[data-action="download"]').click()]);
    assert.equal(download.suggestedFilename(),'metadata.tsv');
    const stream=await download.createReadStream(),chunks=[];for await(const chunk of stream)chunks.push(chunk);
    const output=Buffer.concat(chunks).toString('utf8'),parsed=Core.parseTable(output,'\t');
    assert.deepEqual(Core.inspectIds(output),['sample_a','sample_b']);assert.equal(parsed.rows[0][parsed.headers.indexOf('Notes')],'one "quoted" note\nsecond line');
    assert.equal(parsed.rows[0][parsed.headers.indexOf('host')],'SNGO');assert.equal(parsed.rows[0][parsed.headers.indexOf('country')],'CAN');
    await dialog.locator('[data-action="use"]').click();
    await page.waitForFunction(()=>document.getElementById('metadataSummary').textContent.includes('2 sample IDs match exactly'));
    assert.equal(await page.locator('#metadataFile').evaluate(input=>input.files[0].name),'metadata.tsv');
    await page.setViewportSize({width:390,height:844});await page.locator('#openMetadataWizard').click();
    assert.equal(await dialog.evaluate(node=>node.getBoundingClientRect().width<=innerWidth),true);
    // Native date selection, specimen choices, and preservation of imported values.
    await dialog.locator('[data-action="step"][data-step="0"]').click();
    await dialog.locator('#mwPaste').fill('sample_id,specimen_type,collection_date\nsample_a,Legacy specimen,03/04/2025\nsample_b,,2025-04-15');
    await dialog.locator('[data-action="paste"]').click();await dialog.locator('[data-action="map"]').click();
    await dialog.locator('[data-action="step"][data-step="3"]').click();
    const specimen=dialog.locator('select[data-row="0"][data-field="specimen_type"]');
    assert.equal(await specimen.inputValue(),'Legacy specimen');
    const choices=await specimen.locator('option').allTextContents();
    for(const choice of ['Cloacal','Oropharyngeal','Choanal','Pooled Sample','Other','Unknown'])assert.ok(choices.includes(choice));
    assert.equal(await dialog.locator('input[type="text"][data-row="0"][data-field="collection_date"]').inputValue(),'03/04/2025');
    assert.equal(await dialog.locator('input[type="date"][data-row="0"][data-field="collection_date"]').inputValue(),'');
    assert.equal(await dialog.locator('input[type="date"][data-row="1"][data-field="collection_date"]').inputValue(),'2025-04-15');
    await specimen.selectOption('Cloacal');
    await dialog.locator('input[type="date"][data-row="0"][data-field="collection_date"]').fill('2025-04-03');
    await dialog.locator('input[type="date"][data-row="0"][data-field="collection_date"]').press('Tab');
    await dialog.locator('[data-action="step"][data-step="4"]').click();
    await dialog.locator('#mwAcknowledge').check();
    const [controlsDownload]=await Promise.all([page.waitForEvent('download'),dialog.locator('[data-action="download"]').click()]);
    const controlsStream=await controlsDownload.createReadStream(),controlsChunks=[];for await(const chunk of controlsStream)controlsChunks.push(chunk);
    const controlsParsed=Core.parseTable(Buffer.concat(controlsChunks).toString('utf8'),'\t');
    assert.equal(controlsParsed.rows[0][controlsParsed.headers.indexOf('specimen_type')],'Cloacal');
    assert.equal(controlsParsed.rows[0][controlsParsed.headers.indexOf('collection_date')],'2025-04-03');
    const duplicate='sample_id\thost\nsample_a\tSNGO\nsample_a\tCAGO';
    await dialog.locator('[data-action="step"][data-step="0"]').click();await dialog.locator('#mwPaste').fill(duplicate);await dialog.locator('[data-action="paste"]').click();await dialog.locator('[data-action="map"]').click();await dialog.locator('[data-action="step"][data-step="4"]').click();
    assert.equal(await dialog.locator('[data-action="use"]').isDisabled(),true);assert.equal(await dialog.locator('[data-action="download"]').isDisabled(),true);
    // Missing FASTQ rows: visible no-op, pagination, idempotence, and absent files.
    await dialog.locator('[data-action="step"][data-step="1"]').click();
    await dialog.locator('[data-action="missing"]').click();
    assert.match(await dialog.locator('#mwMessage').innerText(),/Added 1 missing FASTQ metadata row/);
    await dialog.locator('[data-action="missing"]').click();
    assert.match(await dialog.locator('#mwMessage').innerText(),/every selected FASTQ already has a metadata row/);
    const large='sample_id\n'+Array.from({length:50},(_,i)=>'existing_'+i).join('\n');
    await dialog.locator('[data-action="step"][data-step="0"]').click();
    await dialog.locator('#mwPaste').fill(large);await dialog.locator('[data-action="paste"]').click();await dialog.locator('[data-action="map"]').click();
    await dialog.locator('[data-action="missing"]').click();
    assert.match(await dialog.locator('#mwMessage').innerText(),/Added 2 missing FASTQ metadata rows/);
    assert.equal(await dialog.locator('input[data-row="50"][data-field="sample_id"]').inputValue(),'sample_a');
    assert.equal(await dialog.locator('input[data-row="50"][data-field="sample_id"]').evaluate(node=>node===document.activeElement),true);
    assert.match(await dialog.locator('.mw-pager').innerText(),/Rows 51–52 of 52/);
    await dialog.locator('[data-action="missing"]').click();
    assert.match(await dialog.locator('#mwMessage').innerText(),/No rows added/);
    await page.locator('#readsFiles').setInputFiles([]);
    await dialog.locator('[data-action="missing"]').click();
    assert.match(await dialog.locator('#mwMessage').innerText(),/Select FASTQ files in the Sequences step/);
    await dialog.locator('[data-action="close"]').click();
    const css=fs.readFileSync(path.join(root,'scripts/report/sample-report.css'),'utf8')+'\n'+fs.readFileSync(path.join(root,'scripts/report/sample-navigation.css'),'utf8');
    const section=id=>`<section id="${id}"><div class="report-panel"><div class="escape-table-wrapper"><table><thead><tr><th>Segment</th><th>Result</th><th>Status</th></tr></thead><tbody><tr><td>PB2</td><td>Recorded</td><td>PASS</td></tr></tbody></table></div></div></section>`;
    await page.setContent('<style>'+css+'</style>'+['blast-top-hits','vadr-annotation-quality-control','consensus-and-variant-files'].map(section).join(''));
    for(const id of ['blast-top-hits','vadr-annotation-quality-control','consensus-and-variant-files']){
      const styles=await page.locator('#'+id).evaluate(section=>({header:getComputedStyle(section.querySelector('th')).backgroundColor,gold:getComputedStyle(section.querySelector('th')).borderBottomColor,padding:getComputedStyle(section.querySelector('td')).padding,top:getComputedStyle(section.querySelector('.report-panel')).borderTopWidth}));
      assert.deepEqual(styles,{header:'rgb(140, 29, 64)',gold:'rgb(255, 198, 39)',padding:'14px 18px',top:'6px'});
    }
    assert.deepEqual(mutations,[]);assert.deepEqual(errors,[]);
    console.log('PASS: wizard import/review/download/handoff, duplicate gating, mobile sizing, and matching annotation-table styles.');
  } finally {if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
