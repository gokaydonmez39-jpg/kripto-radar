'use strict';
// XRAY NASDAQ 477 — deterministic, read-only A34 C-helper adjacency guard.
// No new schedule, request, provider access, user notification, Sheet POST or order.
const assert=require('node:assert/strict');
const {test}=require('node:test');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const version=JSON.parse(readFileSync(join(__dirname,'xray_477_task_runtime_v3.json'),'utf8'));
assert.equal(version.schema,'XRAY_NASDAQ_477_RUNTIME_V3');
assert.equal(version.blocks.length,12);
const C=Function(version.blocks[9]+'\nreturn XRAY_C_OPEN')();
const REPO='gokaydonmez39-jpg/kripto-radar',URL='https://api.github.com/repos/'+REPO+'/actions/runs/';
function receipt(asof,session,{event='schedule',quarantined=0}={}){
 const id=123450987,root=URL+id,head='a'.repeat(40);
 const run={id,url:root,repository:{full_name:REPO},head_branch:'main',
  path:'.github/workflows/xray-nasdaq-a34-preopen.yml',run_attempt:1,
  status:'completed',conclusion:'success',head_sha:head,
  created_at:session+'T10:00:00Z',run_started_at:session+'T10:00:00Z',
  updated_at:session+'T10:04:00Z',event};
 const jobs=['offline-guard','private-preopen'].map((name,i)=>({
  id:137111111111+i,name,run_id:id,run_url:root,run_attempt:1,
  head_sha:head,status:'completed',conclusion:'success',
  started_at:session+'T10:0'+i+':00Z',
  completed_at:session+'T10:0'+(i+1)+':00Z'}));
 const payload={state:'CORE_PREOPEN_PASS_DEVICE_ACK_UNKNOWN',asof_et:asof,
  next_xnas_session:session,covered:477,source:'ALPACA_IEX_RAW_1DAY',
  al_identity_check:'EXACT_AL_IDENTITY_PASS',al_level_check:'EXACT_AL_LEVELS_PASS',
  orders:false,writes:false,private_data_published:false,open_episodes:18,
  quarantined_research_events:quarantined};
 const wrap=(url,x)=>({structuredContent:{url,display_url:url,content:JSON.stringify(x)}});
 return {runId:id,session,asof,now_iso:session+'T10:10:00Z',
  run_response:wrap(root,run),
  jobs_response:wrap(root+'/attempts/1/jobs?per_page=100',{total_count:2,jobs}),
  preopen_job_id:jobs[1].id,
  preopen_log:{structuredContent:{content:session+'T10:01:30Z '+JSON.stringify(payload)}}};
}
for(const [label,asof,session,expected] of [
 ['Nov23 prior Friday', '2026-11-20','2026-11-23','NATURAL_A34_VERIFIED'],
 ['Nov23 stale Thursday','2026-11-19','2026-11-23','HOLD'],
 ['Nov23 weekend Saturday','2026-11-21','2026-11-23','HOLD'],
 ['Thanksgiving holiday','2026-11-25','2026-11-26','HOLD'],
 ['Nov27 after Thanksgiving','2026-11-25','2026-11-27','NATURAL_A34_VERIFIED'],
 ['Nov30 after short Friday','2026-11-27','2026-11-30','NATURAL_A34_VERIFIED'],
 ['Dec28 after Christmas','2026-12-24','2026-12-28','NATURAL_A34_VERIFIED'],
 ['Dec28 stale Dec23','2026-12-23','2026-12-28','HOLD'],
 ['2027 Good Friday','2027-03-25','2027-03-26','HOLD'],
 ['2027 Juneteenth observed','2027-06-17','2027-06-18','HOLD'],
 ['2027 July 5 holiday','2027-07-02','2027-07-05','HOLD']
]){
 test('C proof: '+label,()=>{
  const out=C.proof(receipt(asof,session));
  assert.equal(out.state,expected);
  if(expected==='HOLD')assert.equal(out.stage,'A34_CONTEXT');
  else {assert.equal(out.asof,asof);assert.equal(out.session,session);assert.equal(out.covered,477);}
 });
}
const context=()=>({xnas_session_verified:true,started_at:'2026-11-23T13:57:48Z',
 scheduled_for:'2026-11-23T13:57:48Z',now_iso:'2026-11-23T13:58:15Z',
 session:'2026-11-23',asof:'2026-11-20',natural:null,downstream:null});
test('C render: no GitHub proof is visible HOLD, not fake PASS',()=>{
 const out=C.render(context());
 assert.equal(out.state,'C_BODY_READY');
 assert.match(out.text,/Planlı doğal A34 doğrulanmadı/);
 assert.match(out.text,/P0\|PREOPEN_DAILY_HEALTH\|2026-11-23/);
});
test('C render: valid preceding XNAS session is allowed',()=>{
 const valid=C.proof(receipt('2026-11-20','2026-11-23'));
 const out=C.render({...context(),natural:valid});
 assert.equal(out.state,'C_BODY_READY');
 assert.match(out.text,/Planlı doğal A34 doğrulandı/);
});
test('C render: forged stale EOD cannot turn red into green',()=>{
 const forged={state:'NATURAL_A34_VERIFIED',asof:'2026-11-19',session:'2026-11-23',
  covered:477,run_id:123,open_episodes:18,quarantined:0};
 const out=C.render({...context(),asof:'2026-11-19',natural:forged});
 assert.equal(out.state,'C_BODY_READY');
 assert.match(out.text,/Planlı doğal A34 doğrulanmadı/);
});
test('C render: quarantined event must stay HOLD',()=>{
 const forged={state:'NATURAL_A34_VERIFIED',asof:'2026-11-20',session:'2026-11-23',
  covered:477,run_id:123,open_episodes:18,quarantined:1};
 const out=C.render({...context(),natural:forged});
 assert.equal(out.state,'C_BODY_READY');
 assert.match(out.text,/Planlı doğal A34 doğrulanmadı/);
});
test('C render: wrong natural slot never produces an opening card',()=>{
 const out=C.render({...context(),scheduled_for:'2026-11-23T12:57:48Z'});
 assert.equal(out.state,'NO_C_CARD');
});
test('No injected provider/Sheet/order methods are necessary',()=>{
 assert.equal(typeof C.proof,'function');
 assert.equal(typeof C.render,'function');
});
