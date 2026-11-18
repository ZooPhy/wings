#!/usr/bin/env node
'use strict';
// Deterministic offline MP4 export. Requires Playwright, Chromium, and ffmpeg.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn,spawnSync}=require('node:child_process');
const {once}=require('node:events');
const movie=require('./report/phylogeography-movie.js');

async function main(){
  const args=process.argv.slice(2),opts={};
  const allowed=new Set(['input','output','segment','target','mode','history','seconds','fps','chromium']);
  for(let i=0;i<args.length;i++){
    if(args[i]==='--example'){opts.example=true;continue;}
    if(args[i]==='--help'){console.log('node scripts/render_phylogeography_movie.cjs --input reconstruction.json --output movie.mp4 [--segment HA] [--target KY] [--mode summary|history] [--history 0] [--seconds 20] [--fps 24] [--chromium /path/to/chromium]\nUse --example in place of --input for explicitly synthetic demonstration data.');return;}
    const key=args[i].replace(/^--/,'');if(!allowed.has(key)||!args[i].startsWith('--')||!args[i+1]||args[i+1].startsWith('--'))throw Error('Unknown or incomplete argument: '+args[i]);opts[key]=args[++i];
  }
  if(!opts.output||(!opts.input&&!opts.example)||opts.input&&opts.example)throw Error('Supply --output and exactly one of --input or --example.');
  const output=path.resolve(opts.output);if(path.extname(output).toLowerCase()!=='.mp4')throw Error('Output must use .mp4.');if(fs.existsSync(output))throw Error('Output already exists; choose a new path.');
  const raw=opts.example?movie.exampleData():JSON.parse(fs.readFileSync(opts.input,'utf8')),model=movie.validate(raw);
  const seconds=Number(opts.seconds||20),fps=Number(opts.fps||24),frames=Math.ceil(seconds*fps)+1;
  if(!Number.isFinite(seconds)||seconds<1||seconds>600||!Number.isInteger(fps)||fps<1||fps>60)throw Error('Use seconds 1–600 and integer fps 1–60.');
  const segment=opts.segment||model.segments[0].id,target=opts.target||(model.states.has('KY')?'KY':model.states.keys().next().value);
  if(!model.segments.some(s=>s.id===segment)||!model.states.has(target))throw Error('Unknown segment or focal state.');
  if(!['summary','history'].includes(opts.mode||'summary'))throw Error('Mode must be summary or history.');
  if(spawnSync('ffmpeg',['-version'],{stdio:'ignore'}).status!==0)throw Error('ffmpeg is required on PATH.');
  const {chromium}=require('playwright');
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'wings-movie-')),temp=path.join(dir,'movie.mp4');
  let browser,encoder,stderr='';
  try{
    browser=await chromium.launch({headless:true,...(opts.chromium?{executablePath:opts.chromium}:{}),args:['--no-sandbox']});
    const page=await browser.newPage({viewport:{width:1480,height:1200}});await page.setContent('<!doctype html><meta charset="utf-8"><main id="movie"></main>');
    await page.addScriptTag({path:path.join(__dirname,'report/map-boundaries.js')});
    await page.addScriptTag({path:path.join(__dirname,'report/phylogeography-movie.js')});
    await page.addStyleTag({path:path.join(__dirname,'report/phylogeography-movie.css')});
    await page.evaluate(({raw,segment,target,mode,history})=>{
      window.player=WINGS_PHYLOGEOGRAPHY_MOVIE.mount(null,document.getElementById('movie'),{data:raw});player.setSegment(segment);player.setTarget(target);player.setMode(mode,history);
    },{raw,segment,target,mode:opts.mode||'summary',history:Number(opts.history||0)});
    encoder=spawn('ffmpeg',['-hide_banner','-loglevel','error','-f','image2pipe','-vcodec','png','-framerate',String(fps),'-i','pipe:0','-an','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',temp],{stdio:['pipe','ignore','pipe']});
    encoder.stderr.on('data',d=>{stderr+=d;});const finished=once(encoder,'close');encoder.stdin.on('error',()=>{});
    for(let i=0;i<frames;i++){
      const png=await page.evaluate(f=>{const {start,end}=player.range;player.setTime(start+(end-start)*f);return player.canvas.toDataURL('image/png').split(',')[1];},i/(frames-1));
      if(encoder.exitCode!==null)throw Error('ffmpeg failed: '+stderr);
      if(!encoder.stdin.write(Buffer.from(png,'base64')))await once(encoder.stdin,'drain');
      if(i%fps===0)process.stdout.write(`\rRendering ${Math.round(i/(frames-1)*100)}%`);
    }
    encoder.stdin.end();const [code]=await finished;if(code!==0)throw Error('ffmpeg failed: '+stderr);
    fs.mkdirSync(path.dirname(output),{recursive:true});fs.copyFileSync(temp,output,fs.constants.COPYFILE_EXCL);
    console.log('\nSaved '+output+(raw.synthetic?' (synthetic example)':''));
  }finally{if(encoder&&encoder.exitCode===null)encoder.kill();if(browser)await browser.close();fs.rmSync(dir,{recursive:true,force:true});}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
