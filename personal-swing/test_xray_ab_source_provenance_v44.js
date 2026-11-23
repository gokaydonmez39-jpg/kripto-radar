'use strict';
// XRAY Personal 477: PINNED A/B production source-row tamper regression.
// All tests are pure offline; no actions, Sheets POST, alerts or orders.
const assert=require('node:assert/strict');
const {test}=require('node:test');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const version=JSON.parse(readFileSync(join(__dirname,'xray_477_task_runtime_v3.json'),'utf8'));
assert.equal(version.schema,'XRAY_NASDAQ_477_RUNTIME_V3');
assert.equal(version.blocks.length,12);
const SID='synthetic_private_sheet_id';
const B=Function(version.portable.code+'\n'+version.blocks[3].replaceAll('XRAY_CONFIG_SHEET_ID_V1',SID)+'\nreturn XRAY_B;')();
const A=Function(version.blocks[10]+'\nreturn XRAY_A_IMPL;')();
const ASOF='2026-11-23', RUN='https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/123456789';
const SCOPE='3d1d226e2ef511570b2abd57e59c74d2c2156e6eed9baf4a08b8d3df82223060';
const ALGO='cac4dd7b729e23cd4f6e4c181f569ef286858c1473217e46358202f595f7723c'; // Reviewed forward-only 2026-11-23 epoch
const SCAN_HEAD=['ASOF ET','ÜRETİM KANALI','İSTENEN','İŞLENEN','GEÇERLİ','EKSİK','FINAL READY','YENİ KAYIT','RUN KANITI','DURUM / VERİ SINIRI'];
const SCAN_ROW=[ASOF,'GitHub schedule VERIFIED IEX EOD','477','477','477','0','TRUE','1',RUN,
  'scopeSHA='+SCOPE+';algorithmSHA='+ALGO+';source_event=schedule;NO_ORDERS'];
const SCORE_HEAD=Array(35).fill('');
for(const [idx,value] of [[0,'KAYIT_KIMLIGI'],[1,'ASOF_ET'],[4,'KAYIT_TIPI'],[27,'BILDIRIM_DURUMU'],[28,'BILDIRIM_ZAMANI_TR']])SCORE_HEAD[idx]=value;
const SUM=Array(35).fill('');
SUM[0]=ASOF+'|SUMMARY';SUM[1]=ASOF;SUM[4]='SUMMARY';SUM[27]='READY_FOR_CHATGPT_DAILY_DIGEST';
const base=()=>[SCAN_HEAD.slice(),SCAN_ROW.slice()];
const route=scan=>B.route({expected_asof:ASOF,scan,baseline:[SCORE_HEAD,SUM]});
const event=Array(20).fill('');
event[0]=ASOF+'|TEST|'+ASOF+'|AL_NEW_EPISODE|1'; event[1]=ASOF+'|TEST';
event[2]=ASOF;event[3]='TEST';event[4]=ASOF;event[5]='AL_NEW_EPISODE';
event[6]='YENİ AL';event[17]='EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST';
const alerts=[Array(20).fill(''),event],history=[Array(13).fill('')];
const aRoute=scan=>A.locateA({expected_asof:ASOF,scan,alerts,history});
test('B: valid natural source row may advance to exact GitHub proof',()=>{
 assert.equal(route(base()).state,'CHECK_B');
});
test('A: valid pending event may advance to exact GitHub proof',()=>{
 assert.equal(aRoute(base()).state,'A_NEEDS_SOURCE');
});
for(const [name,mutate] of [
 ['fake workflow_dispatch label',r=>r[1]='GitHub workflow_dispatch VERIFIED IEX EOD'],
 ['manual channel label',r=>r[1]='manual'],
 ['wrong source_event',r=>r[9]=r[9].replace('source_event=schedule','source_event=workflow_dispatch')],
 ['duplicated source_event',r=>r[9]+=';source_event=workflow_dispatch'],
 ['duplicated source fingerprint',r=>r[9]+=';scopeSHA='+SCOPE],
 ['non-hex source fingerprint',r=>r[9]=r[9].replace('scopeSHA='+SCOPE,'scopeSHA=z'+SCOPE.slice(1))],
 ['source fingerprint missing',r=>r[9]=r[9].replace('scopeSHA='+SCOPE,'')],
 ['algorithm fingerprint missing',r=>r[9]=r[9].replace('algorithmSHA='+ALGO,'')]
]){
 test('B: reject '+name,()=>{
  const scan=base();mutate(scan[1]);const out=route(scan);
  assert.equal(out.state,'HOLD');assert.equal(out.stage,'SCAN_SOURCE_PROVENANCE');
 });
}
for(const [name,mutate] of [
 ['wrong channel',r=>r[1]='manual'],
 ['duplicated source event',r=>r[9]+=';source_event=workflow_dispatch'],
 ['duplicated scope SHA',r=>r[9]+=';scopeSHA='+SCOPE],
 ['duplicated algorithm SHA',r=>r[9]+=';algorithmSHA='+ALGO]
]){
 test('A: reject '+name,()=>{
  const scan=base();mutate(scan[1]);const out=aRoute(scan);
  assert.equal(out.state,'HOLD');assert.equal(out.stage,'A_SCAN_PROVENANCE');
 });
}
test('No older ASOF may be served from a later verified source',()=>{
 const scan=base();assert.equal(B.route({expected_asof:'2026-11-20',scan,baseline:[SCORE_HEAD,SUM]}).stage,'SOURCE_FUTURE_ASOF');
});
test('No private side effects are referenced in this isolated suite',()=>{
 assert.equal(version.portable.blob.length,40);
 assert.equal(version.blocks[3].includes('SCAN_SOURCE_PROVENANCE'),true);
});
