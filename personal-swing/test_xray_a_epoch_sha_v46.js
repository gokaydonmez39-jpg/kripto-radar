'use strict';
// Exact A/outbox 2026-11-23 forward-only SHA cutover, no market reads or writes.
const assert=require('node:assert/strict');
const {test}=require('node:test');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const v=JSON.parse(readFileSync(join(__dirname,'xray_477_task_runtime_v3.json'),'utf8'));
assert.equal(v.schema,'XRAY_NASDAQ_477_RUNTIME_V3');
const A=Function(v.blocks[10]+'\nreturn XRAY_A_IMPL')();
const OLD='0c137ecbdaf0eb68dbab3a642cfd501e4af61641b52367607fe616713af32523';
const NEXT='cac4dd7b729e23cd4f6e4c181f569ef286858c1473217e46358202f595f7723c';
const R='gokaydonmez39-jpg/kripto-radar',SCOPE=A.constants.SCOPE;
const R_ID=123450987,URL='https://api.github.com/repos/'+R+'/actions/runs/'+R_ID;
const WEB='https://github.com/'+R+'/actions/runs/'+R_ID;
function fixture(asof,algo,opts={}){
 const channel=opts.channel||'GitHub schedule VERIFIED IEX EOD',noteExtra=opts.noteExtra||'';
 const scan=[['ASOF ET','ÜRETİM KANALI','İSTENEN','İŞLENEN','GEÇERLİ','EKSİK','FINAL READY','YENİ KAYIT','RUN KANITI','DURUM / VERİ SINIRI'],
 [asof,channel,'477','477','477','0','TRUE','1',WEB,
  'scopeSHA='+SCOPE+';algorithmSHA='+algo+';source_event=schedule;NO_ORDERS; SHEETS_READBACK_REQUIRED; NOT_DEVICE_ACK'+noteExtra]];
 const history=[['ALARM KİMLİĞİ','ASOF ET','SEMBOL','SINIF','IEX KAPANIŞ USD','STOP 2ATR','HEDEF 2R','TAKİP DURUMU','KAPANIŞ SEANSI','SONUÇ'],
 [asof+'|TEST',asof,'TEST','TEKNİK AL ADAYI','100','90','120','AÇIK • 0/15 SEANS','','']];
 const e=Array(20).fill('');
 Object.assign(e,{0:asof+'|TEST|'+asof+'|AL_NEW_EPISODE|1',1:asof+'|TEST',2:asof,3:'TEST',4:asof,5:'AL_NEW_EPISODE',6:'YENİ AL',7:'100',8:'90',9:'120',15:'0/15',16:WEB,17:'EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST'});
 return {expected_asof:asof,scan,history,alerts:[Array(20).fill(''),e]};
}
function sourced(algo){
 const asof='2026-11-23',x=fixture(asof,algo);
 const stamp=y=>'2026-11-24T'+y+':00Z',sha='a'.repeat(40);
 const jobNames=['offline-guard','private-sheets-auth-preflight','daily-private-scan','private-episode-followups','guardian-acceptance','daily-private-score-acceptance'];
 const slots=[['03:58','04:00'],['03:59','04:02'],['04:00','04:05'],['04:05','04:07'],['04:07','04:09'],['04:09','04:10']];
 const jobs=jobNames.map((name,i)=>({id:234500+i,name,run_id:R_ID,run_url:URL,head_branch:'main',run_attempt:1,
  head_sha:sha,status:'completed',conclusion:'success',started_at:stamp(slots[i][0]),completed_at:stamp(slots[i][1])}));
 const run={id:R_ID,url:URL,repository:{full_name:R},path:'.github/workflows/xray-personal-477-eod.yml',
  event:'schedule',head_branch:'main',run_attempt:1,head_sha:sha,status:'completed',conclusion:'success',
  created_at:stamp('03:58'),run_started_at:stamp('03:58'),updated_at:stamp('04:10')};
 const wrap=(url,data)=>({structuredContent:{url,display_url:url,content:JSON.stringify(data)}});
 const lines=list=>({structuredContent:{content:list.map(([t,s])=>
  '2026-11-24T'+t+'Z '+(typeof s==='string'?s:JSON.stringify(s))).join('\n')}});
 const logs={
 [jobs[2].id]:lines([
  ['04:00:40','XRAY_PERSONAL_GITHUB_HANDOFF=PASS_477_477_SOURCE_POLICY_SHA_BOUND_PRIVATE'],
  ['04:00:50',{asof_et:asof,no_execution:true,final_ready:true,universe:477,processed:477,valid:477,
   invalid_or_missing:0,remaining:0,new_entries:1,scope_sha256:SCOPE,analysis_fingerprint_sha256:algo}],
  ['04:01:10',{asof_et:asof,status:'PRIVATE_SHEET_READBACK_PASS',candidates:1}],
  ['04:01:20',{asof_et:asof,status:'AL_OUTBOX_PENDING_READBACK_PASS',technical_al:1,messages_sent:0,
   device_ack:false,new_pending:1,new_suppressed:0}]]),
 [jobs[3].id]:lines([
  ['04:05:20',{asof_et:asof,status:'PANEL_READBACK_PASS',device_ack:false}],
  ['04:05:30',{asof_et:asof,status:'LIFECYCLE_READBACK_PASS',
   notification_delivery:'NOT_ATTEMPTED_BY_GITHUB',device_ack:false,terminal_updates:0}]]),
 [jobs[4].id]:lines([
  ['04:07:30',{last_verified_scan_asof:asof,schema:'XRAY_PERSONAL_PRIVATE_EVIDENCE_AUDIT_V1',
   status:'READ_ONLY_EVIDENCE_AUDIT',execution:'NONE',messages_sent:0,sheet_writes:0}]])
 };
 return {...x,runResponse:wrap(URL,run),jobsResponse:wrap(URL+'/attempts/1/jobs?per_page=100',
  {total_count:6,jobs}),logs};
}
test('A cutoff: exact old historical fingerprint preserved',()=>{
 assert.equal(A.constants.sourceAlgo('2026-11-20'),OLD);
 assert.equal(A.locateA(fixture('2026-11-20',OLD)).state,'A_NEEDS_SOURCE');
});
test('A cutoff: official 23 Nov IEX UTC fingerprint admitted',()=>{
 assert.equal(A.constants.sourceAlgo('2026-11-23'),NEXT);
 assert.equal(A.locateA(fixture('2026-11-23',NEXT)).state,'A_NEEDS_SOURCE');
});
test('A cutoff: new SHA never backdates to Friday',()=>{
 const o=A.locateA(fixture('2026-11-20',NEXT));
 assert.equal(o.state,'HOLD');assert.equal(o.stage,'A_SCAN_PROVENANCE');
});
test('A cutoff: old SHA rejected from Monday onward',()=>{
 const o=A.locateA(fixture('2026-11-23',OLD));
 assert.equal(o.state,'HOLD');assert.equal(o.stage,'A_SCAN_PROVENANCE');
});
test('A cutoff: Tuesday still requires only future SHA',()=>{
 assert.equal(A.locateA(fixture('2026-11-24',NEXT)).state,'A_NEEDS_SOURCE');
 assert.equal(A.locateA(fixture('2026-11-24',OLD)).state,'HOLD');
});
test('A cutoff: bad workflow channel fails closed',()=>{
 const o=A.locateA(fixture('2026-11-23',NEXT,{channel:'GitHub workflow_dispatch VERIFIED IEX EOD'}));
 assert.equal(o.stage,'A_SCAN_PROVENANCE');
});
test('A cutoff: duplicated algorithm fingerprint fails closed',()=>{
 const o=A.locateA(fixture('2026-11-23',NEXT,{noteExtra:';algorithmSHA='+NEXT}));
 assert.equal(o.stage,'A_SCAN_PROVENANCE');
});
test('A exact six-job source receipts accept current 23 Nov policy',()=>{
 const o=A.proveA(sourced(NEXT));
 assert.equal(o.state,'A_SOURCE_VERIFIED');
 assert.equal(o.asof,'2026-11-23');assert.equal(o.verified.length,1);assert.equal(o.hasRisk,false);
});
test('A exact six-job source receipts reject stale SHA',()=>{
 const o=A.proveA(sourced(OLD));
 assert.equal(o.state,'HOLD');assert.equal(o.stage,'A_SCAN_PROVENANCE');
});
test('A source note synthesizer uses forward epoch, never old hardcode',()=>{
 const b=v.blocks[10];
 assert.match(b,/analysis_fingerprint_sha256:sourceAlgo\(asof\)/);
 assert.match(b,/o\.analysis_fingerprint_sha256===sourceAlgo\(asof\)/);
});
test('A test never imports providers or a write adapter',()=>{
 assert.equal(v.blocks.length,12);
 assert.equal(A.constants.ALGO,OLD);assert.equal(A.constants.ALGO_NEXT,NEXT);
});
