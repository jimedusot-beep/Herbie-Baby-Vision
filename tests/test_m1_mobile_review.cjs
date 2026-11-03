'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {createHash,webcrypto}=require('node:crypto');
const {validateInvestigation,validateProposal,parseFiles,correlate,startDashboard,MAX_JSON,MAX_DIFF}=require('../dashboard/m1-review.js');
const commit='a'.repeat(40);
const excerpt='const checkpoint = recoverRoom();';
function investigation(){return {
  source_commit:commit,query:'room checkpoint recovery',partial_scan:false,searched_files:547,
  evidence:[{path:'server/room-checkpoints.ts',line:42,excerpt}],
  analysis:{summary:'Possible interrupted recovery',suspected_cause:'Missing restart guard',
    suggested_change:'Review checkpoint state on reconnect',confidence:'medium',
    citations:[{path:'server/room-checkpoints.ts',line:42}]},
  warning:'Advisory only.'
};}
const diff='--- a/server/room-checkpoints.ts\n+++ b/server/room-checkpoints.ts\n@@ -42,1 +42,1 @@\n-const checkpoint = recoverRoom();\n+const checkpoint = recoverSafely();\n';
function proposal(){return {
  source_commit:commit,query:'room checkpoint recovery',model:'qwen2.5-coder:1.5b',
  target:'server/room-checkpoints.ts',partial_scan:false,
  diff_sha256:createHash('sha256').update(diff).digest('hex'),
  citations:[{path:'server/room-checkpoints.ts',line:42}],analysis:investigation().analysis,
  warning:'UNTESTED SUGGESTION ONLY'
};}
function file(name,data){return {name,size:Buffer.byteLength(data),text:async()=>data};}
function bundleFiles(override={}){return [file('investigation.json',JSON.stringify(investigation())),
  file('guided.json',JSON.stringify(proposal())),file('guided.diff',diff)].map(x=>({...x,...override}));}

test('validates real M1 investigation and proposal shapes as unverified claims',()=>{
  assert.equal(validateInvestigation(investigation()).ok,true);
  assert.equal(validateProposal(proposal()).ok,true);
  assert.equal(correlate(validateInvestigation(investigation()).value,
    validateProposal(proposal()).value),'matching-claims');
});
test('rejects invented citations, malformed paths and invalid commit identifiers',()=>{
  const i=investigation();i.analysis.citations[0].line=900;
  assert.equal(validateInvestigation(i).ok,false);
  const p=proposal();p.target='../.env';assert.equal(validateProposal(p).ok,false);
  const j=investigation();j.source_commit='invalid';assert.equal(validateInvestigation(j).ok,false);
  const m=proposal();m.diff_sha256='invalid';assert.equal(validateProposal(m).ok,false);
});
test('rejects null, arrays and prototype-shaped nonrecords',()=>{
  assert.equal(validateInvestigation(null).ok,false);
  assert.equal(validateProposal([]).ok,false);
  assert.equal(validateInvestigation(Object.create(null)).ok,false);
});
test('paired investigation and proposal with valid matching diff digest are accepted',async()=>{
  const result=await parseFiles(bundleFiles(),webcrypto.subtle);
  assert.equal(result.ok,true,result.error);
  assert.equal(result.value.pairing,'matching-claims');
  assert.equal(result.value.diff,diff);
  assert.match(result.value.diffStatus,/matches supplied/);
});
test('rejects cross-file commit mismatch without displaying a patch',async()=>{
  const p=proposal();p.source_commit='b'.repeat(40);
  const result=await parseFiles([file('i.json',JSON.stringify(investigation())),
    file('p.json',JSON.stringify(p)),file('p.diff',diff)],webcrypto.subtle);
  assert.equal(result.ok,false);
  assert.match(result.error,/inconsistent source evidence/);
});
test('rejects cross-file citation mismatch',async()=>{
  const p=proposal();p.citations[0].line=43;p.analysis.citations[0].line=43;
  const result=await parseFiles([file('i.json',JSON.stringify(investigation())),
    file('p.json',JSON.stringify(p))],webcrypto.subtle);
  assert.equal(result.ok,false);
});
test('rejects altered patch, even if it has correct headers',async()=>{
  const result=await parseFiles([file('p.json',JSON.stringify(proposal())),
    file('p.diff',diff.replace('recoverSafely','takeoverControl'))],webcrypto.subtle);
  assert.equal(result.ok,false);
  assert.match(result.error,/SHA-256/);
});
test('never displays unchecked diff where digest support unavailable',async()=>{
  const result=await parseFiles([file('p.json',JSON.stringify(proposal())),file('p.diff',diff)],null);
  assert.equal(result.ok,true);
  assert.equal(result.value.diff,null);
  assert.equal(result.value.diffStatus,'checksum unavailable');
});
test('accepts standalone investigation or proposal for read-only inspection',async()=>{
  for (const obj of [investigation(),proposal()]) {
    const result=await parseFiles([file('report.json',JSON.stringify(obj))],webcrypto.subtle);
    assert.equal(result.ok,true);
    assert.equal(result.value.pairing,'unpaired');
  }
});
test('rejects unpaired diff, duplicate JSON types, and files over size limit before reading',async()=>{
  let reads=0;
  const tooLarge={name:'report.json',size:MAX_JSON+1,text:async()=>{reads++;return '{}';}};
  assert.equal((await parseFiles([tooLarge],webcrypto.subtle)).ok,false);
  assert.equal(reads,0);
  assert.equal((await parseFiles([file('r.diff',diff)],webcrypto.subtle)).ok,false);
  assert.equal((await parseFiles([file('a.json',JSON.stringify(proposal())),
     file('b.json',JSON.stringify(proposal()))],webcrypto.subtle)).ok,false);
  assert.equal((await parseFiles([file('x.diff','x'.repeat(MAX_DIFF+1)),
     file('p.json',JSON.stringify(proposal()))],webcrypto.subtle)).ok,false);
});
test('rejects fabricated mode, malformed report, or extra selected files',async()=>{
  const i=investigation();i.partial_scan='false';assert.equal(validateInvestigation(i).ok,false);
  assert.equal((await parseFiles([file('bad.json','{')],webcrypto.subtle)).ok,false);
  assert.equal((await parseFiles([file('bad.html','<script>alert(1)</script>')],webcrypto.subtle)).ok,false);
  const list=[file('a.json','{}'),file('b.json','{}'),file('c.json','{}'),file('d.json','{}')];
  assert.equal((await parseFiles(list,webcrypto.subtle)).ok,false);
});
function fakeDocument(){
 const elements=new Map();
 function element(id){if(elements.has(id))return elements.get(id);
  const listeners={};const x={textContent:'',hidden:false,disabled:false,value:'',files:[],
   addEventListener(event,cb){listeners[event]=cb},fire(event){return listeners[event]?.()}};
  elements.set(id,x);return x;}
 return {getElementById:element};
}
test('UI renders hostile source and patch as plain text only; clear removes private content',async()=>{
  const d=fakeDocument();startDashboard(d,webcrypto.subtle);
  const p=proposal();p.analysis.summary='<img src=x onerror=alert(1)>';
  const x=d.getElementById('localFiles');x.files=[file('p.json',JSON.stringify(p)),file('p.diff',diff)];
  await x.fire('change');
  assert.equal(d.getElementById('summary').textContent,p.analysis.summary);
  assert.equal(d.getElementById('toggleSource').disabled,true);
  assert.equal(d.getElementById('toggleDiff').disabled,false);
  d.getElementById('toggleDiff').fire('click');
  assert.equal(d.getElementById('diffPreview').textContent,diff);
  d.getElementById('clearAll').fire('click');
  assert.equal(d.getElementById('diffPreview').textContent,'');
  assert.equal(d.getElementById('summary').textContent,'—');
});
test('clearing while file read is pending prevents stale report from reappearing',async()=>{
 const d=fakeDocument();startDashboard(d,webcrypto.subtle);
 let resolveRead;const pending=new Promise(resolve=>{resolveRead=resolve});
 const input=d.getElementById('localFiles');
 input.files=[{name:'p.json',size:200,text:async()=>pending}];
 const reading=input.fire('change');
 d.getElementById('clearAll').fire('click');
 resolveRead(JSON.stringify(proposal()));await reading;
 assert.equal(d.getElementById('reviewStatus').textContent,'No report selected');
 assert.equal(d.getElementById('toggleDiff').disabled,true);
});
test('HTML CSP forbids network and active third-party dependencies',()=>{
 const html=fs.readFileSync('dashboard/m1-review.html','utf8');
 assert.match(html,/connect-src 'none'/);
 assert.match(html,/default-src 'none'/);
 assert.match(html,/form-action 'none'/);
 assert.match(html,/script src="m1-review.js" defer/);
 assert.doesNotMatch(html,/<iframe|<form|<img|<script(?! src="m1-review.js")/i);
 assert.doesNotMatch(html,/<button[^>]*>(?:Approve|Execute|Run tests)/i);
});
