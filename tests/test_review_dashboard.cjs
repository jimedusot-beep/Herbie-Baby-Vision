'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {validatePacket,startDashboard,MAX_FILE_BYTES}=require('../dashboard/review.js');

function valid() {
  return {
    status:'ready_for_human_review',merge_allowed:false,
    task:'add-npm-test-entry-point',
    source_commit:'a'.repeat(40),model:'local-fixture',allowed_files:['package.json'],
    test_exit_code:0,baseline_test_exit_code:1,model_generated:true,
    proposal:{script:'npm run test:unit',reason:'use the approved unit entry point'},
    package_json:{scripts:{'test':'npm run test:unit',
      'test:unit':'node --test tests/*.test.cjs'}},
    patch:'diff --git a/package.json b/package.json\n+  "test": "npm run test:unit"',
    test_output:'PRIVATE_POTENTIAL_SECRET',baseline_test_output:'PRIVATE_BASELINE'
  };
}

test('accepts a structurally consistent first-task report as an unverified claim',()=>{
  const result=validatePacket(valid());
  assert.equal(result.ok,true);
  assert.equal(result.summary.status,'ready_for_human_review');
  assert.equal(result.summary.evidence_claim_only,true);
  assert.equal(JSON.stringify(result).includes('PRIVATE_POTENTIAL_SECRET'),false);
});

test('never authorizes merge even when a report says its tests succeeded',()=>{
  const packet=valid();
  packet.merge_allowed=true;
  const result=validatePacket(packet);
  assert.equal(result.ok,false);
  assert.match(result.errors.join(' '),/forbid automatic merging/);
});

test('rejects false success when tests failed or baseline did not fail',()=>{
  for(const [field,value] of [['test_exit_code',1],['baseline_test_exit_code',0]]) {
    const packet=valid();packet[field]=value;
    assert.equal(validatePacket(packet).ok,false,field);
  }
});

test('rejects task scope expansion and unapproved scripts',()=>{
  const cases=[
    ['task','deploy-firmware'],['allowed_files',['package.json','secret.env']],
    ['source_commit','not-a-commit'],['model_generated',false],
    ['proposal',{script:'node dangerous.js',reason:'oops'}],
    ['patch','diff --git a/secret.env b/secret.env']
  ];
  for(const [field,value] of cases) {
    const packet=valid();packet[field]=value;
    assert.equal(validatePacket(packet).ok,false,field);
  }
});

test('rejects incomplete evidence and fabricated status',()=>{
  assert.equal(validatePacket(null).ok,false);
  assert.equal(validatePacket([]).ok,false);
  const fake=valid();fake.status='merged';assert.equal(validatePacket(fake).ok,false);
  const missing=valid();delete missing.package_json;assert.equal(validatePacket(missing).ok,false);
});

test('accepts a genuinely blocked worker packet but cannot promote it',()=>{
  const packet={status:'blocked',merge_allowed:false,model:'local-fixture',
    error:'PRIVATE_POTENTIAL_SECRET',error_type:'RuntimeError',test_exit_code:null};
  const result=validatePacket(packet);
  assert.equal(result.ok,true);
  assert.equal(result.summary.status,'blocked');
  assert.equal(JSON.stringify(result).includes('PRIVATE_POTENTIAL_SECRET'),false);
});

function fakeDocument() {
  const elements=new Map();
  function element(id) {
    if(elements.has(id))return elements.get(id);
    const listeners=new Map();
    const e={textContent:'',hidden:false,disabled:false,value:'',files:[],
      addEventListener(name,fn){listeners.set(name,fn);},
      fire(name){return listeners.get(name)?.();}};
    elements.set(id,e);return e;
  }
  return {getElementById:element};
}

test('local UI refuses to mark an invalid packet reviewed',async()=>{
  const doc=fakeDocument();
  startDashboard(doc);
  const file=doc.getElementById('evidenceFile');
  file.files=[{size:100,text:async()=>JSON.stringify({...valid(),merge_allowed:true})}];
  await file.fire('change');
  assert.equal(doc.getElementById('markReviewed').disabled,true);
  assert.match(doc.getElementById('reviewStatus').textContent,/Review blocked/);
});

test('local UI accepts valid data, shows diff as text and never sends a request',async()=>{
  const doc=fakeDocument();
  startDashboard(doc);
  const packet=valid();
  packet.patch+='\n+<script>alert("not executed")</script>';
  const file=doc.getElementById('evidenceFile');
  file.files=[{size:1024,text:async()=>JSON.stringify(packet)}];
  await file.fire('change');
  assert.equal(doc.getElementById('markReviewed').disabled,false);
  const preview=doc.getElementById('diffPreview');
  assert.equal(preview.hidden,true);
  doc.getElementById('showDiff').fire('click');
  assert.equal(preview.hidden,false);
  assert.match(preview.textContent,/<script>/);
  doc.getElementById('markReviewed').fire('click');
  assert.match(doc.getElementById('reviewDetail').textContent,/No GitHub review/);
  doc.getElementById('clearReview').fire('click');
  assert.equal(doc.getElementById('markReviewed').disabled,true);
});

test('oversized evidence file is blocked before reading',async()=>{
  const doc=fakeDocument();startDashboard(doc);
  let reads=0;
  const file=doc.getElementById('evidenceFile');
  file.files=[{size:MAX_FILE_BYTES+1,text:async()=>{reads++;return '{}';}}];
  await file.fire('change');
  assert.equal(reads,0);
  assert.equal(doc.getElementById('markReviewed').disabled,true);
});

test('review page refuses network connections and identifies review-only scope',()=>{
  const html=fs.readFileSync('dashboard/index.html','utf8');
  assert.match(html,/connect-src 'none'/);
  assert.match(html,/No analytics, uploads, networking, or persistence/);
  assert.match(html,/cannot start a worker, run tests, verify Git commits/);
  assert.doesNotMatch(html,/<iframe|<form[^>]*action=/i);
});
