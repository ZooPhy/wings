// Run with: node tests/test_storage_folder_picker_browser.cjs (Playwright + Chromium).
const assert=require('node:assert/strict');
const fs=require('node:fs');
const http=require('node:http');
const path=require('node:path');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const requests=[];
const server=http.createServer((req,res)=>{
  if(req.url==='/'){
    res.setHeader('Content-Type','text/html');
    res.end('<link rel="stylesheet" href="/assets/wings-folder-picker.css"><label for="runsDirectory">Runs</label><input id="runsDirectory" value="/runs"><button data-storage-browse="runsDirectory">Browse runs</button><input id="condaCacheDirectory" value=""><button data-storage-browse="condaCacheDirectory">Browse cache</button><p id="storageMessage"></p><script>window.edits=0;document.getElementById("runsDirectory").addEventListener("input",()=>window.edits++);</script><script src="/assets/wings-folder-picker.js"></script>');return;
  }
  if(req.url==='/api/storage/directories/create'){
    let data='';req.on('data',chunk=>data+=chunk);req.on('end',()=>{
      const payload=JSON.parse(data);requests.push(payload);res.setHeader('Content-Type','application/json');res.end(JSON.stringify({status:'CREATED',path:payload.path+'/'+payload.name}));
    });return;
  }
  if(req.url==='/api/storage/directories'){
    let data='';req.on('data',chunk=>data+=chunk);req.on('end',()=>{
      const payload=JSON.parse(data);requests.push(payload);res.setHeader('Content-Type','application/json');
      if(payload.path==='/denied'){res.writeHead(400);res.end(JSON.stringify({error:'Access denied'}));return;}
      const current=payload.path||'/home/user';
      const directories=current==='/runs'?[{name:'New project',path:'/runs/New project'},{name:'Denied',path:'/denied'},{name:'<img src=x>',path:'/runs/special'}]:[];
      res.end(JSON.stringify({path:current,parent:'/',directories:payload.query?directories.filter(x=>x.name.toLowerCase().includes(payload.query.toLowerCase())):directories,total:payload.query?0:directories.length,offset:0,limit:200,shortcuts:[{name:'Home',path:'/home/user'}],notice:''}));
    });return;
  }
  const name=req.url.split('?')[0];
  if(['/assets/wings-folder-picker.js','/assets/wings-folder-picker.css'].includes(name)){
    res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':'text/css');res.end(fs.readFileSync(path.join(root,name)));return;
  }
  res.writeHead(404);res.end();
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;
  try{
    browser=await chromium.launch({headless:true,...(process.env.WINGS_BROWSER_EXECUTABLE?{executablePath:process.env.WINGS_BROWSER_EXECUTABLE}:{})});
    const page=await browser.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.locator('[data-storage-browse="runsDirectory"]').click();
    const dialog=page.locator('#storageFolderPicker');await dialog.locator('#folderPickerChoose').waitFor();
    await page.waitForFunction(()=>!document.getElementById('folderPickerChoose').disabled);
    assert.equal(await dialog.locator('#folderPickerPath').innerText(),'/runs');
    assert.equal(await dialog.locator('img').count(),0);
    await dialog.getByRole('button',{name:'New project /',exact:true}).click();
    await page.waitForFunction(()=>document.getElementById('folderPickerPath').textContent==='/runs/New project');
    assert.equal(await page.locator('#runsDirectory').inputValue(),'/runs');
    await dialog.locator('#folderPickerNew').click();await dialog.locator('#folderPickerName').fill('New cache');
    await dialog.locator('#folderPickerCreate').click();
    await page.waitForFunction(()=>document.getElementById('folderPickerPath').textContent==='/runs/New project/New cache' && !document.getElementById('folderPickerChoose').disabled);
    assert.equal(await page.locator('#runsDirectory').inputValue(),'/runs');
    await dialog.locator('#folderPickerChoose').click();
    assert.equal(await page.locator('#runsDirectory').inputValue(),'/runs/New project/New cache');
    assert.equal(await page.evaluate(()=>window.edits),1);
    assert.match(await page.locator('#storageMessage').innerText(),/Validate and apply/);
    await page.locator('[data-storage-browse="condaCacheDirectory"]').click();
    await page.waitForFunction(()=>document.getElementById('folderPickerPath').textContent==='/home/user');
    await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
    assert.equal(await page.locator('#condaCacheDirectory').inputValue(),'');
    await page.locator('#runsDirectory').fill('/runs');await page.locator('[data-storage-browse="runsDirectory"]').click();
    // Force reopening before the previous native dialog close event is delivered.
    await page.evaluate(()=>{
      document.getElementById('storageFolderPicker').close();
      document.querySelector('[data-storage-browse="runsDirectory"]').click();
    });
    await page.waitForFunction(()=>document.getElementById('folderPickerPath').textContent==='/runs' && !document.getElementById('folderPickerChoose').disabled);
    await dialog.getByRole('button',{name:'Denied /',exact:true}).click();
    await page.waitForFunction(()=>document.getElementById('folderPickerStatus').textContent==='Access denied');
    assert.equal(await dialog.locator('#folderPickerChoose').isDisabled(),true);
    await page.keyboard.press('Escape');assert.equal(await dialog.isVisible(),false);
    await page.setViewportSize({width:390,height:844});await page.locator('[data-storage-browse="runsDirectory"]').click();
    assert.equal(await dialog.evaluate(node=>node.getBoundingClientRect().width<=innerWidth),true);
    assert.deepEqual(errors,[]);assert.ok(requests.length>=4);
    console.log('PASS: folder navigation, selection, input handoff, cancellation, permission errors, text escaping, and mobile dialog sizing.');
  }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
