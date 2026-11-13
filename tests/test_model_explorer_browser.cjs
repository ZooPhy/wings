'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/concordance_model_explorer.json'),'utf8'));
(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1280,height:1000}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.setContent('<main id="app"></main>');
    await page.addStyleTag({path:path.join(__dirname,'../scripts/report/concordance-model-explorer.css')});
    await page.addScriptTag({path:path.join(__dirname,'../scripts/report/concordance-model-explorer.js')});
    await page.evaluate(f=>{
      const samples=f.sample_features.map((s,i)=>({...s,host:i%2?'Host A':'Host B',country:'USA',state:i%2?'Arizona':'Utah',collection_date:'2025-10-01'}));
      window.input={payload:{samples,genomic_ecological_concordance:{models:[],readiness:{minimum_unique_samples:8},interactive_inputs:f}}};
      window.controller=WINGS_MODEL_EXPLORER.mount(input,document.getElementById('app'));
    },fixture);
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Fit preview ready'));
    assert.equal(await page.locator('.wme-chart [role=button]').count(),3);
    await page.locator('.wme-chart [role=button]').last().focus();
    assert.match(await page.locator('.wme-evidence').innerText(),/Add seasonal patterns/);
    const selects=page.locator('.wme-controls select');
    await selects.nth(3).selectOption('0');
    assert.match(await page.locator('.wme-status').innerText(),/Selection changed/);
    assert.equal(await page.locator('.wme-chart svg').count(),0);
    await page.locator('.wme-factors label').nth(2).locator('input').check();
    await page.locator('.wme-factors label').nth(3).locator('input').check();
    await page.getByRole('button',{name:'Update comparison',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Comparison updated'));
    assert.match(await page.locator('.wme-path-legend').innerText(),/Weather path/);
    assert.match(await page.locator('.wme-path-legend').innerText(),/Migration path/);
    const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download comparison',exact:true}).click();assert.equal((await download).suggestedFilename(),'wings-model-comparison.json');
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1));
    await page.locator('.wme-sample-picker summary').click();await page.getByRole('button',{name:'Clear all',exact:true}).click();
    await page.getByRole('button',{name:'Update comparison',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Comparison updated'));
    assert.match(await page.locator('.wme-evidence').innerText(),/Too few distinct samples/);
    assert.equal(await page.locator('.wme-chart [role=button]').count(),0);
    assert.deepEqual(errors,[]);
    console.log('PASS: interactive selection, real refitting, separate branches, keyboard inspection, downloads, unavailable states, and mobile containment');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
