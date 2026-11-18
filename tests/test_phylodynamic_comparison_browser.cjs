'use strict';
// Localhost exercises the same static scripts used by the offline file bundle.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const {spawnSync}=require('node:child_process'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'wings-comparison-browser-'));
 const code=`import sys,json,copy,hashlib\nfrom pathlib import Path\nsys.path[:0]=['tests','scripts']\nfrom test_phylodynamics_comparison import fixture\nfrom build_phylodynamic_comparison import write_comparison\nroot=Path(sys.argv[1]);m,r=fixture()\nblocked=dict(r,status='blocked',reasons=['temporal_screen_failed'],introductions={})\na=dict(r,id='HA/available/replicate_1',strategy='available')\nb=dict(r,id='HA/available/replicate_2',strategy='available',replicate=2)\nfor rec in (a,b):\n p=root/'inference'/rec['id'];p.mkdir(parents=True);(p/'movie.json').write_text(json.dumps(m))\n for name,value in [('result.json',rec),('dated_nodes.json',m['segments'][0]['nodes'])]:(p/name).write_text(json.dumps(value))\n (p/'alignment.fasta').write_text('synthetic alignment fixture')\n tips=root/'selection'/rec['id']/'tips.tsv';tips.parent.mkdir(parents=True);tips.write_text('synthetic tips')\n hashes={name:hashlib.sha256((p/name).read_bytes()).hexdigest() for name in ('result.json','dated_nodes.json','alignment.fasta')};hashes['tips.tsv']=hashlib.sha256(tips.read_bytes()).hexdigest()\n # UI fixture only: these dates are fabricated, not an inference result.\n dating=dict(analysis=rec['id'],input_sha256=hashes,focal_sample_ids=rec['focal_sample_ids'],status='complete' if rec['replicate']==1 else 'not_converged',prior_only=False,tmrca=dict(median='2024-02-15',hpd95=['2024-02-01','2024-03-01']))\n dest=root/'bayesian'/rec['id']/'initial/summary.json';dest.parent.mkdir(parents=True);dest.write_text(json.dumps(dating))\nwrite_comparison(dict(analyses=[blocked,a,b],primary_analyses=[blocked['id']]),root)\n`;
 const prep=spawnSync(process.env.PYTHON||'python',['-c',code,tmp],{encoding:'utf8'});if(prep.status!==0)throw Error(prep.stderr);
 const server=http.createServer((req,res)=>{const f=path.resolve(tmp,'.'+new URL(req.url,'http://localhost').pathname);if(!f.startsWith(tmp+path.sep)||!fs.existsSync(f)){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',f.endsWith('.js')?'text/javascript':f.endsWith('.css')?'text/css':'text/html');fs.createReadStream(f).pipe(res);});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;
 try{
  browser=await chromium.launch({headless:true,...(process.env.WINGS_CHROMIUM?{executablePath:process.env.WINGS_CHROMIUM}:{}),args:['--no-sandbox']});
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/comparison.html`);
  assert.match(await page.locator('#load-status').textContent(),/No substitute/);
  assert.equal(await page.locator('canvas').count(),0);
  await page.locator('#replicates tbody button').nth(1).click();await page.waitForSelector('canvas');
  assert.match(await page.locator('.wpm-date').textContent(),/Feb 1, 2024/);
  assert.match(await page.locator('#bayesian').textContent(),/Median Feb 15, 2024 · 95% HPD Feb 1, 2024 – Mar 1, 2024/);
  assert.match(await page.locator('#bayesian').textContent(),/movie still uses TreeTime dates/);
  await page.locator('.wpm-slider').fill('1000');await page.locator('.wpm-slider').dispatchEvent('input');
  assert.match(await page.locator('canvas').getAttribute('aria-label'),/1.0 expected introductions/);
  await page.locator('.wpm-window').selectOption('full');assert.match(await page.locator('.wpm-date').textContent(),/Jan 1, 2024/);
  // A later selection wins even when an earlier movie script responds afterwards.
  await page.evaluate(()=>{document.querySelectorAll('#replicates tbody button')[1].click();document.querySelectorAll('#replicates tbody button')[2].click();});
  await page.waitForFunction(()=>document.querySelector('#load-status').textContent.includes('histories loaded'));
  assert.match(await page.locator('#selection-title').textContent(),/available · 2/);
  assert.match(await page.locator('#bayesian').textContent(),/Posterior HPD withheld · not_converged/);
  assert.doesNotMatch(await page.locator('#bayesian').textContent(),/Median/);
  assert.equal(await page.locator('canvas').count(),1);
  await page.locator('#replicates tbody button').nth(0).click();assert.equal(await page.locator('canvas').count(),0);
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);console.log('PASS: blocked primary, explicit replicate selection, scoped dates/counts, race handling, conditional Bayesian HPD display/withholding, mobile layout.');
 }finally{await browser?.close();server.close();fs.rmSync(tmp,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exit(1);});
