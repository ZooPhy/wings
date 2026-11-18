'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const movie=require('../scripts/report/phylogeography-movie.js');
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.WINGS_CHROMIUM?{executablePath:process.env.WINGS_CHROMIUM}:{}),args:['--no-sandbox']});
  try{
    const page=await browser.newPage({viewport:{width:1500,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.setContent('<!doctype html><html><head><meta charset="utf-8"></head><body><main id="movie"></main></body></html>');
    await page.addStyleTag({path:path.join(root,'scripts/report/phylogeography-movie.css')});
    await page.addScriptTag({path:path.join(root,'scripts/report/map-boundaries.js')});
    await page.addScriptTag({path:path.join(root,'scripts/report/phylogeography-movie.js')});
    await page.evaluate(()=>{window.player=WINGS_PHYLOGEOGRAPHY_MOVIE.mount(null,document.getElementById('movie'));});
    assert.equal(await page.locator('.wpm-empty').isVisible(),true);
    assert.equal(await page.locator('.wpm-body').isVisible(),false);
    await page.getByRole('button',{name:'Try illustrative example'}).click();
    assert.match(await page.locator('.wpm-status').innerText(),/Synthetic histories/);
    await page.evaluate(()=>player.setTime(player.range.end));
    assert.match(await page.locator('canvas').getAttribute('aria-label'),/2.3 expected introductions/);
    await page.getByLabel('Segment',{exact:true}).selectOption('NA');
    await page.evaluate(()=>player.setTime(player.range.end));
    assert.match(await page.locator('canvas').getAttribute('aria-label'),/2.6 expected introductions/);
    await page.getByLabel('View',{exact:true}).selectOption('history');
    await page.getByLabel('History',{exact:true}).selectOption('1');
    assert.match(await page.locator('canvas').getAttribute('aria-label'),/2.0 introductions/);
    await page.getByLabel('Introductions into',{exact:true}).selectOption('OH');
    assert.match(await page.locator('canvas').getAttribute('aria-label'),/Ohio/);
    await page.getByRole('button',{name:'Restart',exact:true}).click();
    const before=await page.evaluate(()=>player.state.time);
    await page.getByRole('button',{name:'Play',exact:true}).click();
    await page.waitForTimeout(250);assert.ok(await page.evaluate(()=>player.state.time)>before);
    await page.getByRole('button',{name:'Pause',exact:true}).click();
    await page.locator('.wpm-slider').fill('500');const t=await page.evaluate(()=>player.state.time);await page.waitForTimeout(100);assert.equal(await page.evaluate(()=>player.state.time),t);
    await page.locator('summary').click();await page.getByLabel('Inspect tree node').selectOption('d');assert.match(await page.locator('.wpm-node-info').innerText(),/Kentucky 100.0%/);
    await page.getByRole('button',{name:'Highlight',exact:true}).first().click();
    const previous=await page.evaluate(()=>player.state.segment);
    await page.getByLabel('Load phylogeographic reconstruction JSON').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from('{"schema":"wrong"}')});
    assert.match(await page.locator('.wpm-status').innerText(),/Could not load/);assert.equal(await page.evaluate(()=>player.state.segment),previous);
    const valid=movie.exampleData();valid.synthetic=false;valid.provenance.inference='empirical-bayes';valid.title='Test only, not study results';
    await page.getByLabel('Load phylogeographic reconstruction JSON').setInputFiles({name:'fixture.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(valid))});
    await page.waitForFunction(()=>!player.state.synthetic);
    await page.evaluate(()=>player.setTime(player.range.end));assert.match(await page.locator('canvas').getAttribute('aria-label'),/mapping interval/);
    // Unsafe imported strings are only displayed as text.
    valid.title='<img src=x onerror="window.injected=true">';await page.evaluate(d=>player.load(d),valid);assert.equal(await page.evaluate(()=>window.injected),undefined);
    await page.setViewportSize({width:390,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.setViewportSize({width:1500,height:1100});
    await page.evaluate(()=>{player.load(WINGS_PHYLOGEOGRAPHY_MOVIE.exampleData());player.setTime(player.range.end);});
    if(process.env.WINGS_MOVIE_SCREENSHOT)await page.locator('.wpm').screenshot({path:process.env.WINGS_MOVIE_SCREENSHOT});
    // A browser export must contain video bytes, and controls recover afterwards.
    if(await page.getByRole('button',{name:'Export video',exact:true}).isEnabled()){
      const download=page.waitForEvent('download');await page.getByRole('button',{name:'Export video',exact:true}).click();await page.waitForTimeout(900);
      await page.getByRole('button',{name:'Stop export',exact:true}).click();const d=await download;const saved=await d.path();assert.ok(fs.statSync(saved).size>1000);assert.match(d.suggestedFilename(),/illustrative\.(mp4|webm)$/);
      await page.waitForFunction(()=>!document.querySelector('.wpm-player button').disabled);
    }
    await page.getByRole('button',{name:'Play',exact:true}).click();await page.evaluate(()=>player.setActive(false));assert.equal(await page.evaluate(()=>player.state.playing),false);
    assert.deepEqual(errors,[]);console.log('PASS: playback, imports, posterior/history modes, uncertainty labels, node/route selection, responsive layout, export, and lifecycle.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
