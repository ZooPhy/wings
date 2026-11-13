'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/concordance_model_explorer.json'),'utf8'));
(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1280,height:1000}});
    page.setDefaultTimeout(15000);
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
    assert.equal(await page.getByLabel('Sample eligibility',{exact:true}).inputValue(),'shared');
    assert.match(await page.locator('.wme-eligibility-summary').innerText(),/Every model below uses these same samples and pairs/);
    assert.equal(await page.locator('.wme-comparison').count(),1);
    assert.equal(await page.locator('.wme-model-row').count(),3);
    // Quarto places semantic <aside> elements into a margin grid column.
    // Reproduce that host rule, then verify every marker remains in the plot.
    await page.addStyleTag({content:'.quarto-layout aside { grid-column:4; width:640px; } #app { max-width:100%; }'});
    await page.locator('#app').evaluate(el=>el.classList.add('quarto-layout'));
    for(const width of [1600,1024,768,390]){
      await page.setViewportSize({width,height:1000});
      assert.ok(await page.evaluate(()=>{
        const chart=document.querySelector('.wme-chart'),bounds=chart.getBoundingClientRect();
        const bars=[...chart.querySelectorAll('.wme-bar')];
        return bars.length===3&&chart.scrollWidth<=chart.clientWidth+1&&bars.every(bar=>{
          const r=bar.getBoundingClientRect();return r.left>=bounds.left-1&&r.right<=bounds.right+1;
        });
      }),'All model bars must be visible without horizontal scrolling at '+width);
      if(width<=1024)assert.ok(await page.evaluate(()=>document.querySelector('.wme-evidence').getBoundingClientRect().top>=document.querySelector('.wme-chart').getBoundingClientRect().bottom));
    }
    await page.setViewportSize({width:1280,height:1000});

    await page.locator('.wme-model-row').last().focus();
    assert.match(await page.locator('.wme-evidence').innerText(),/Time & Location & Host & Seasonal Bird Abundance/);
    assert.equal(await page.getByLabel('Include samples from host',{exact:true}).inputValue(),'');
    assert.equal(await page.getByLabel('Host identity',{exact:true}).isChecked(),true);
    const selects=page.locator('.wme-controls select');
    await selects.nth(3).selectOption('0');
    assert.match(await page.locator('.wme-status').innerText(),/Selection changed/);
    assert.equal(await page.locator('.wme-chart svg').count(),0);
    await page.locator('.wme-factors label').nth(2).locator('input').check();
    await page.locator('.wme-factors label').nth(3).locator('input').check();
    await page.getByRole('button',{name:'Update comparison',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Comparison updated'));
    assert.equal(await page.locator('.wme-comparison').count(),1);
    assert.deepEqual(await page.locator('.wme-comparison h4').allTextContents(),['Models on the same samples']);
    assert.equal(await page.locator('.wme-model-row').count(),5);
    const labels=await page.locator('.wme-row-label').allTextContents();
    assert.equal(new Set(labels).size,5);
    assert.equal(labels[0],'Time & Location');
    assert.equal(labels[3],'Time & Location & Host & Seasonal Bird Abundance & Weather');
    assert.equal(labels[4],'Time & Location & Host & Seasonal Bird Abundance & Migration');
    assert.match(await page.locator('.wme-branch-note').innerText(),/Weather and Migration each extend Time & Location & Host & Seasonal Bird Abundance separately/);
    // Each terminal gold bar must start from the common core, not the previous visual row.
    for(const code of ['weather','migration']){
      const row=page.locator(`[data-model-code="${code}"]`);
      const gold=row.locator('.wme-bar-gain');
      assert.ok(Math.abs(Number(await gold.getAttribute('x'))-fixture.expected_r2.seasonal*1000)<1e-9);
      assert.ok(Math.abs(Number(await gold.getAttribute('width'))-(fixture.expected_r2[code]-fixture.expected_r2.seasonal)*1000)<1e-9);
      await row.focus();
      assert.match(await page.locator('.wme-evidence').innerText(),/Compared with: Time & Location & Host & Seasonal Bird Abundance/);
    }
    assert.ok(await page.locator('.wme-added-factor').evaluateAll(els=>els.length>0&&els.every(el=>getComputedStyle(el).color==='rgb(0, 0, 0)'&&getComputedStyle(el).backgroundColor==='rgb(255, 198, 39)')));

    const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download comparison',exact:true}).click();const downloaded=await download;assert.equal(downloaded.suggestedFilename(),'wings-model-comparison.json');
    const chunks=[];for await(const chunk of await downloaded.createReadStream())chunks.push(chunk);
    const exported=JSON.parse(Buffer.concat(chunks).toString());assert.equal(exported.options.cohort_mode,'shared');
    assert.match(exported.notes,/all models use the same samples/);
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1));
    await page.locator('.wme-sample-picker summary').click();await page.getByRole('button',{name:'Clear all',exact:true}).click();
    await page.getByRole('button',{name:'Update comparison',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Comparison updated'));
    assert.match(await page.locator('.wme-evidence').innerText(),/Too few distinct samples/);
    assert.equal(await page.locator('.wme-bar').count(),0);
    assert.equal(await page.locator('.wme-model-unavailable').count(),5);
    // Different cohorts and unavailable starting models must remain explicit.
    await page.evaluate(f=>{
      controller.cancel();document.getElementById('app').replaceChildren();delete input.modelExplorerSettings;
      f.pairs.forEach(r=>{
        r.environmental_distance=r.same_host;
        r.migration_context_distance=(['S01','S02'].includes(r.sample_a)||['S01','S02'].includes(r.sample_b))?null:r.temporal_days;
        r.same_host=r.temporal_days;
        r.seasonal_profile_distance=r.geographic_km;
      });
      f.sample_features.forEach(s=>s.migration_context_key='one setting');
      input.payload.genomic_ecological_concordance.interactive_inputs=f;
      controller=WINGS_MODEL_EXPLORER.mount(input,document.getElementById('app'));
    },fixture);
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Fit preview ready'));
    await page.locator('.wme-controls select').nth(3).selectOption('0');
    await page.locator('.wme-factors label').nth(2).locator('input').check();
    await page.locator('.wme-factors label').nth(3).locator('input').check();
    await page.getByRole('button',{name:'Update comparison',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Comparison updated'));
    assert.equal(await page.locator('.wme-comparison').count(),1);
    assert.equal(await page.locator('.wme-model-row').count(),5);
    assert.equal(await page.locator('[data-model-code="migration"] .wme-bar').count(),0);
    assert.match(await page.locator('.wme-eligibility-summary').innerText(),/Using 10 of 12 selected samples/);
    assert.equal(await page.locator('.wme-cohort-note').count(),0);
    await page.getByLabel('Sample eligibility',{exact:true}).selectOption('per-comparison');
    assert.match(await page.locator('.wme-status').innerText(),/Selection changed/);
    assert.equal(await page.locator('.wme-model-row').count(),0);
    await page.getByRole('button',{name:'Update comparison',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Comparison updated'));
    assert.equal(await page.evaluate(()=>controller.getResult().options.cohort_mode),'per-comparison');
    assert.equal(await page.evaluate(()=>input.modelExplorerSettings.cohort_mode),'per-comparison');
    assert.match(await page.locator('.wme-eligibility-summary').innerText(),/Maximum available samples/);
    assert.equal(await page.locator('.wme-comparison').count(),4);
    assert.equal(await page.locator('.wme-model-row').count(),8);
    assert.equal(await page.locator('.wme-comparison').first().locator('.wme-cohort').innerText(),'12 samples · 66 pairs');
    assert.equal(await page.locator('.wme-migration .wme-cohort').innerText(),'10 samples · 45 pairs');
    assert.equal(await page.locator('.wme-migration .wme-model-unavailable').count(),2);
    assert.match(await page.locator('.wme-migration').innerText(),/Only 1 distinct migration setting; at least 8/);
    assert.match(await page.locator('.wme-migration .wme-model-row').first().innerText(),/Among these 10 eligible samples, the starting-model predictors contain redundant information/);
    await page.locator('.wme-migration .wme-model-row').last().focus();
    await page.keyboard.press('Enter');
    assert.match(await page.locator('.wme-evidence').innerText(),/Only 1 distinct migration setting; at least 8/);
    assert.equal(await page.locator('.wme-migration .wme-model-row').last().getAttribute('aria-pressed'),'true');
    for(const width of [1600,1024,390]){
      await page.setViewportSize({width,height:1000});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1));
    }
    await page.getByRole('button',{name:'Reset filters',exact:true}).click();
    assert.equal(await page.getByLabel('Sample eligibility',{exact:true}).inputValue(),'shared');
    for(const checkbox of await page.locator('.wme-factors input').all())await checkbox.uncheck();
    await page.getByRole('button',{name:'Update comparison',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Comparison updated'));
    assert.equal(await page.locator('.wme-model-row').count(),1);
    assert.equal(await page.locator('.wme-row-label').innerText(),'Time & Location');
    await page.locator('.wme-factors label').nth(3).locator('input').check();
    await page.getByRole('button',{name:'Update comparison',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Comparison updated'));
    assert.deepEqual(await page.locator('.wme-row-label').allTextContents(),['Time & Location','Time & Location & Migration']);
    assert.equal(await page.locator('.wme-branch-note').count(),0);
    // Exercise the real enclosing Concordance renderer: sample selection calls
    // its refresh method, not the model controller's refreshView method.
    await page.addScriptTag({path:path.join(__dirname,'../scripts/report/genomic-ecological-concordance.js')});
    await page.evaluate(f=>{
      controller.cancel();document.getElementById('app').replaceChildren();
      delete input.modelExplorerSettings;
      f.pairs.push(...f.pairs.map(r=>({...r,segment:'NP'})));
      input.payload.genomic_ecological_concordance.interactive_inputs=f;
      input.selectSample=function(id){this.selectedSampleId=id;this.concordanceController.refresh();};
      input.concordanceController=WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE.mount(input,document.getElementById('app'));
    },fixture);
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Fit preview ready'));
    await page.locator('.wme-controls select').nth(0).selectOption('NP');
    await page.locator('.wme-controls select').nth(3).selectOption('199');
    await page.getByRole('button',{name:'Update comparison',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Comparison updated'));
    assert.equal(await page.evaluate(()=>{
      window.finished=input.modelExplorer.getResult();window.live=input.modelExplorer;
      input.selectSample(input.payload.samples[0].sample_id);
      return input.modelExplorer===live&&input.modelExplorer.getResult()===finished&&finished.options.permutations===199;
    }),true);
    assert.equal(await page.locator('.wme-controls select').first().inputValue(),'NP');
    assert.ok(await page.evaluate(()=>input.modelExplorer.getResult().results.some(r=>r.segment==='NP'&&r.permutation_p!==null&&r.fdr_q!==null)));
    // Dirty controls must stay dirty; unrelated selection must not trigger a fit.
    await page.locator('.wme-controls select').nth(1).selectOption('Host A');
    assert.equal(await page.locator('.wme-host-scope').isVisible(),true);
    await page.evaluate(()=>input.selectSample(input.payload.samples[1].sample_id));
    assert.equal(await page.locator('.wme-controls select').nth(1).inputValue(),'Host A');
    assert.match(await page.locator('.wme-status').innerText(),/Selection changed/);
    assert.equal(await page.locator('.wme-chart svg').count(),0);
    await page.locator('.wme-controls select').nth(1).selectOption('');
    // Refresh while a permutation calculation is yielding; it must finish.
    await page.evaluate(()=>{
      document.querySelector('.wme-primary').click();
      input.selectSample(input.payload.samples[2].sample_id);
    });
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Comparison updated'));
    assert.equal(await page.evaluate(()=>input.modelExplorer===live&&input.modelExplorer.getResult().options.permutations===199),true);
    // A replacement dataset must mount a new controller, not reuse stale results.
    await page.evaluate(()=>{
      input.payload={...input.payload,genomic_ecological_concordance:{...input.payload.genomic_ecological_concordance,interactive_inputs:null}};
      input.concordanceController.refresh();
    });
    assert.equal(await page.evaluate(()=>input.modelExplorer===live),false);
    assert.match(await page.locator('.wme-status').innerText(),/Saved comparisons shown/);
    // Original inputs loaded into a legacy report must survive the same refresh.
    await page.locator('.wme-legacy input').setInputFiles({name:'concordance.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({...fixture,models:[]}))});
    await page.waitForFunction(()=>document.querySelector('.wme-status').textContent.startsWith('Fit preview ready'));
    await page.evaluate(()=>{window.loaded=input.modelExplorer;input.selectSample(input.payload.samples[3].sample_id);});
    assert.equal(await page.evaluate(()=>input.modelExplorer===loaded&&input.modelExplorer.getResult().scope==='browser-refit'),true);
    assert.equal(await page.locator('.wme-legacy').isVisible(),false);
    assert.deepEqual(errors,[]);
    console.log('PASS: comparison cards, unavailable rows, keyboard selection, mobile layout, completed and in-flight checks, dirty filters, imported inputs, and replacement datasets');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
