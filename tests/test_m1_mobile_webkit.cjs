'use strict';
// Synthetic only: WebKit touch emulation is not a physical iPhone Safari pass.
const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const root=path.resolve(__dirname,'..');
const {webkit}=require(process.env.BABY_WEBKIT_PLAYWRIGHT||'playwright');
const allowed=new Map([
 ['/dashboard/m1-review.html',['dashboard/m1-review.html','text/html; charset=utf-8']],
 ['/dashboard/m1-review.js',['dashboard/m1-review.js','application/javascript; charset=utf-8']]
]);
let server,browser,origin;
function fixture(name){
 return {name,mimeType:name.endsWith('.json')?'application/json':'text/plain',
  buffer:fs.readFileSync(path.join(root,'samples',name))};
}
async function phone(width=390,height=844){
 const context=await browser.newContext({viewport:{width,height},
  screen:{width,height},deviceScaleFactor:3,isMobile:true,hasTouch:true});
 const external=[];
 await context.route('**/*',async route=>{
  const url=route.request().url();
  if(!url.startsWith(origin+'/')){external.push(url);await route.abort();}
  else await route.continue();
 });
 const page=await context.newPage();
 await page.goto(origin+'/dashboard/m1-review.html',{waitUntil:'load'});
 return {context,page,external};
}
before(async()=>{
 server=http.createServer((req,res)=>{
  const item=allowed.get(req.url);
  if(!item){res.writeHead(404);res.end('not found');return;}
  res.writeHead(200,{'Content-Type':item[1],'Cache-Control':'no-store'});
  res.end(fs.readFileSync(path.join(root,item[0])));
 });
 await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
 origin='http://127.0.0.1:'+server.address().port;
 browser=await webkit.launch({headless:true});
});
after(async()=>{
 if(browser)await browser.close();
 if(server)await new Promise(resolve=>server.close(resolve));
});
test('390px touch viewer loads matching synthetic report, reveals evidence only on tap, and clears',async()=>{
 const {context,page,external}=await phone();
 try{
  await page.locator('#localFiles').setInputFiles([
   fixture('demo.investigation.json'),fixture('demo.proposal.json'),fixture('demo.diff')
  ]);
  await page.waitForFunction(()=>document.querySelector('#reviewStatus').textContent.includes('Local review'));
  assert.match(await page.locator('#modelTag').textContent(),/synthetic-fixture/);
  assert.match(await page.locator('#pairState').textContent(),/Matching file/);
  assert.match(await page.locator('#checksumState').textContent(),/matches supplied SHA-256/);
  assert.equal(await page.locator('#sourcePreview').isVisible(),false);
  assert.equal(await page.locator('#diffPreview').isVisible(),false);
  const dims=await page.evaluate(()=>({view:innerWidth,doc:document.documentElement.scrollWidth}));
  assert.ok(dims.doc<=dims.view+1,'no horizontal overflow: '+JSON.stringify(dims));
  for(const id of ['#clearAll','#toggleSource','#toggleDiff']){
   const rect=await page.locator(id).boundingBox();
   assert.ok(rect&&rect.height>=44,id+' touch target must be at least 44px high');
  }
  await page.locator('#toggleSource').click();
  await page.locator('#toggleDiff').click();
  assert.equal(await page.locator('#sourcePreview').isVisible(),true);
  assert.equal(await page.locator('#diffPreview').isVisible(),true);
  assert.match(await page.locator('#sourcePreview').textContent(),/SYNTHETIC EXAMPLE ONLY/);
  assert.match(await page.locator('#diffPreview').textContent(),/recoverSafely/);
  fs.mkdirSync(path.join(root,'artifacts'),{recursive:true});
  await page.screenshot({path:path.join(root,'artifacts/m1-webkit-synthetic-mobile.png'),fullPage:true});
  await page.locator('#clearAll').click();
  assert.equal(await page.locator('#sourcePreview').textContent(),'');
  assert.equal(await page.locator('#diffPreview').textContent(),'');
  assert.equal(await page.locator('#reviewStatus').textContent(),'No report selected');
  assert.equal(await page.locator('#toggleDiff').isDisabled(),true);
  assert.deepEqual(external,[]);
  assert.deepEqual(await context.cookies(),[]);
  assert.equal(await page.evaluate(()=>localStorage.length),0);
 }finally{await context.close();}
});
test('320px and 430px WebKit viewports have no horizontal overflow',async()=>{
 for(const width of [320,430]){
  const {context,page,external}=await phone(width,700);
  try{
   const d=await page.evaluate(()=>({view:innerWidth,doc:document.documentElement.scrollWidth}));
   assert.ok(d.doc<=d.view+1,'overflow at width '+width);
   assert.deepEqual(external,[]);
  }finally{await context.close();}
 }
});
test('hostile model report markup remains literal text and never makes an external request',async()=>{
 const {context,page,external}=await phone();
 try{
  const data=JSON.parse(fs.readFileSync(path.join(root,'samples/demo.investigation.json'),'utf8'));
  const attack='<img src="https://example.invalid/exfil" onerror="window.__xss=1">';
  data.analysis.summary=attack;
  await page.locator('#localFiles').setInputFiles({name:'injected.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(data))});
  await page.waitForFunction(()=>document.querySelector('#reviewStatus').textContent.includes('Local review'));
  assert.equal(await page.locator('#summary').textContent(),attack);
  assert.equal(await page.locator('img').count(),0);
  assert.equal(await page.evaluate(()=>window.__xss),undefined);
  assert.deepEqual(external,[]);
 }finally{await context.close();}
});
test('mismatched source commit blocks review and clears previously visible diff',async()=>{
 const {context,page,external}=await phone();
 try{
  await page.locator('#localFiles').setInputFiles([
   fixture('demo.investigation.json'),fixture('demo.proposal.json'),fixture('demo.diff')]);
  await page.waitForFunction(()=>document.querySelector('#reviewStatus').textContent.includes('Local review'));
  await page.locator('#toggleDiff').click();
  assert.equal(await page.locator('#diffPreview').isVisible(),true);
  const wrong=JSON.parse(fs.readFileSync(path.join(root,'samples/demo.proposal.json'),'utf8'));
  wrong.source_commit='0'.repeat(40);
  await page.locator('#localFiles').setInputFiles([
   fixture('demo.investigation.json'),
   {name:'wrong.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(wrong))},
   fixture('demo.diff')]);
  await page.waitForFunction(()=>document.querySelector('#reviewStatus').textContent==='Review blocked');
  assert.match(await page.locator('#reviewDetail').textContent(),/inconsistent source evidence/);
  assert.equal(await page.locator('#diffPreview').textContent(),'');
  assert.equal(await page.locator('#toggleDiff').isDisabled(),true);
  assert.deepEqual(external,[]);
 }finally{await context.close();}
});
