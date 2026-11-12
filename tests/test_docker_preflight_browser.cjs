// Run with: node tests/test_docker_preflight_browser.cjs (Playwright + Chromium).
const assert=require('node:assert/strict');
const fs=require('node:fs');
const http=require('node:http');
const path=require('node:path');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');let daemonReady=false,probes=0,endpointAvailable=true,releaseProbe=null,holdProbe=false;
const server=http.createServer((req,res)=>{
  const route=new URL(req.url,'http://localhost').pathname;
  const json=data=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(data));};
  // Older health responses omit the capability flag; the endpoint must still be tried.
  if(route==='/api/health')return json({snakemake_available:true,snakemake:'fixture',config_yaml_present:true,runs_root:'/fixture',storage_revision:'test',conda_pkgs_default:'default',free_bytes:100});
  if(route==='/api/runs')return json([]);
  if(route==='/api/docker/check'){
    let body='';req.on('data',chunk=>body+=chunk);req.on('end',()=>{
      const vadr=JSON.parse(body).vadr;probes++;
      const finish=()=>{
        if(!endpointAvailable){res.writeHead(404);res.end();return;}
        json({ready:!vadr||daemonReady,message:!vadr?'Docker is not required':daemonReady?'Docker engine is responding':'Docker engine is unavailable. Start Docker Desktop.',required:vadr});
      };
      if(holdProbe)releaseProbe=finish;else finish();
    });return;
  }
  const file=path.resolve(root,'.'+decodeURIComponent(route));
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
  const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.jpg':'image/jpeg','.svg':'image/svg+xml'};
  res.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;
  try{
    browser=await chromium.launch({headless:true});const page=await browser.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/run.html?new=1`);
    await page.waitForFunction(()=>document.getElementById('dockerStatus').textContent.includes('unavailable'));
    daemonReady=true;holdProbe=true;await page.locator('#checkDocker').click();
    assert.equal(await page.locator('#checkDocker').textContent(),'Checking…');
    assert.equal(await page.locator('#checkDocker').isDisabled(),true);
    while(!releaseProbe)await new Promise(resolve=>setTimeout(resolve,10));
    holdProbe=false;releaseProbe();releaseProbe=null;
    await page.waitForFunction(()=>document.getElementById('dockerStatus').textContent.includes('responding'));
    assert.match(await page.locator('#dockerStatus').textContent(),/Last attempt:/);
    endpointAvailable=false;await page.locator('#checkDocker').click();
    await page.waitForFunction(()=>document.getElementById('dockerStatus').textContent.includes('Restart the WINGS runner'));
    assert.equal(await page.locator('#checkDocker').isEnabled(),true);
    endpointAvailable=true;await page.locator('#checkDocker').click();
    await page.waitForFunction(()=>document.getElementById('dockerStatus').textContent.includes('responding'));
    await page.locator('.step-button[data-step="4"]').click();
    await page.waitForFunction(()=>document.getElementById('preflightList').textContent.includes('Docker engine is responding'));
    daemonReady=false;await page.locator('#checkDockerPreflight').click();
    await page.waitForFunction(()=>document.getElementById('preflightList').textContent.includes('Docker engine is unavailable'));
    assert.equal(await page.locator('#startRun').isDisabled(),true);
    await page.locator('.step-button[data-step="3"]').click();await page.locator('#optVadr').uncheck();
    await page.waitForFunction(()=>document.getElementById('dockerStatus').textContent.includes('not required'));
    assert.ok(probes>=4);assert.deepEqual(errors,[]);
    console.log('PASS: automatic Docker status, manual retry, Preflight gating, and refreshed analysis selection.');
  }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
