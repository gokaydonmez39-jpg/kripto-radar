'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');

const release = JSON.parse(fs.readFileSync(process.env.XRAY_TEST_RUNTIME ||
  path.join(__dirname, 'xray_477_task_runtime_v3.json'), 'utf8'));
const TASK = 'abcdefabcdefabcdefabcdefabcdefab';
const CHAT = '11111111-1111-4111-8111-111111111111';
const TURN = '22222222-2222-4222-8222-222222222222';
const SHEET = 'xray_synthetic_sheet_fixture_only';
const PROMPT = 'XRAY_A_DEPLOYMENT_STAGE=CANARY_LOCKED_V1';
const ASOF = '2026-01-06';
const OPEN = '2026-01-05';
const REPO = 'gokaydonmez39-jpg/kripto-radar';
const WORKFLOW = '.github/workflows/xray-personal-477-eod.yml';
const ROOT = 'https://api.github.com/repos/' + REPO + '/actions/runs';
const URL = ROOT + '/101';
const JOBS_URL = URL + '/attempts/1/jobs?per_page=100';
const WEB = 'https://github.com/' + REPO + '/actions/runs/101';
const HEAD = 'a'.repeat(40);
const START = ASOF + 'T23:16:00Z';
const PROOF_TIME = ASOF + 'T23:17:00Z';
const END = ASOF + 'T23:18:00Z';
const SLOT = '2026-01-07T01:57:48Z';
const bound = text => text.replaceAll('XRAY_CONFIG_TASK_ID_V1', TASK)
  .replaceAll('XRAY_CONFIG_CHAT_ID_V1', CHAT).replaceAll('XRAY_CONFIG_SHEET_ID_V1', SHEET);
const blocks = release.blocks.map(bound);
const compile = src => () => Function('__xrayCompile','__xrayBlocks','__xrayPortable',src)(
  compile, () => blocks, () => release.portable.code);
const A = compile(blocks[10] + '\nreturn XRAY_A_IMPL;')();
const stage = compile(blocks[11] + '\nreturn XRAY_AB_STAGED;')();
const {PENDING, A_JOBS, SCOPE, ALGO} = A.constants;
const eventHeader = ['OLAY_ANAHTARI','ADAY_ANAHTARI','AL_ASOF_ET','SEMBOL','OLAY_ASOF_ET',
  'OLAY_KODU','ONCELIK','IEX_KAPANIS_USD','ORIJINAL_STOP_USD','ORIJINAL_HEDEF_USD',
  'SMA20','SMA50','DESTEK_20','DIRENC_20','TEPE_52','TAKIP_SEANSI',
  'BIRINCIL_KANIT_URL','BILDIRIM_DURUMU','BILDIRIM_ZAMANI_TR','NOT'];
const scan = [['ASOF ET','ÜRETİM KANALI','İSTENEN','İŞLENEN','GEÇERLİ','EKSİK',
  'FINAL READY','YENİ KAYIT','RUN KANITI','DURUM / VERİ SINIRI'],
  [ASOF,'fixture','477','477','477','0','TRUE','1',WEB,
    'scopeSHA='+SCOPE+';algorithmSHA='+ALGO+';source_event=schedule;']];
const alKey = ASOF+'|SYNTHAL';
const stopKey = OPEN+'|SYNTHSTOP';
const history = [['ALARM KİMLİĞİ','ASOF ET','SEMBOL','SINIF','IEX KAPANIŞ USD',
  'STOP 2ATR','HEDEF 2R','TAKİP DURUMU','KAPANIŞ SEANSI','SONUÇ'],
  [alKey,ASOF,'SYNTHAL','fixture','100','90','120','AÇIK • 0/15 SEANS','',''],
  [stopKey,OPEN,'SYNTHSTOP','fixture','50','45','60','KAPALI • STOP_TOUCHED • 1/15 SEANS',ASOF,'STOP_TOUCHED']];
const alEvent = [alKey+'|'+ASOF+'|AL_NEW_EPISODE|1',alKey,ASOF,'SYNTHAL',ASOF,
  'AL_NEW_EPISODE','YENİ AL','100','90','120','','','','','','0/15',WEB,PENDING,'',''];
const stopEvent = [stopKey+'|'+ASOF+'|STOP_TOUCHED|1',stopKey,OPEN,'SYNTHSTOP',ASOF,
  'STOP_TOUCHED','KRİTİK','44','45','60','','','','','','1/15',WEB,PENDING,'',
  'Verified historical Alpaca IEX daily bar; theoretical contact only; synthetic'];
const queue = [eventHeader,alEvent,stopEvent];
const jobNames = [...A_JOBS,'daily-private-score-acceptance'];
const jobs = jobNames.map((name,i) => ({name,id:210+i,run_id:101,run_url:URL,run_attempt:1,
  head_branch:'main',head_sha:HEAD,status:'completed',conclusion:'success',started_at:START,completed_at:END,
  steps:i===5?[{name:'Attach and verify current B evidence note (schedule only)',conclusion:'success'}]:[]}));
const run = {id:101,url:URL,repository:{full_name:REPO},path:WORKFLOW,event:'schedule',
  head_branch:'main',head_sha:HEAD,run_attempt:1,status:'completed',conclusion:'success',
  created_at:START,run_started_at:START,updated_at:END};
const handoff = 'XRAY_PERSONAL_GITHUB_HANDOFF=PASS_477_477_SOURCE_POLICY_SHA_BOUND_PRIVATE';
const readback = {status:'PRIVATE_SHEET_READBACK_PASS',asof_et:ASOF,candidates:1};
const runScan = {asof_et:ASOF,no_execution:true,final_ready:true,universe:477,processed:477,
  valid:477,invalid_or_missing:0,remaining:0,new_entries:1,scope_sha256:SCOPE,analysis_fingerprint_sha256:ALGO};
const outbox = {asof_et:ASOF,status:'AL_OUTBOX_PENDING_READBACK_PASS',technical_al:1,
  messages_sent:0,device_ack:false,new_pending:1,new_suppressed:0};
const panel = {asof_et:ASOF,status:'PANEL_READBACK_PASS',device_ack:false};
const lifecycle = {asof_et:ASOF,status:'LIFECYCLE_READBACK_PASS',device_ack:false,
  notification_delivery:'NOT_ATTEMPTED_BY_GITHUB',terminal_updates:1};
const guardian = {last_verified_scan_asof:ASOF,schema:'XRAY_PERSONAL_PRIVATE_EVIDENCE_AUDIT_V1',
  status:'READ_ONLY_EVIDENCE_AUDIT',execution:'NONE',messages_sent:0,sheet_writes:0};
const encode = value => typeof value==='string'?value:JSON.stringify(value);
const asRawLog = rows => ({structuredContent:{content:rows.map(x=>PROOF_TIME+' '+encode(x)).join('\n')}});
const logs = {[jobs[2].id]:asRawLog([handoff,readback,runScan,outbox]),
  [jobs[3].id]:asRawLog([panel,lifecycle]),[jobs[4].id]:asRawLog([guardian])};
const schema = 'XRAY_477_B_SOURCE_ENVELOPE_V1';
function snapshot(options) {
  const addon = {schema:'XRAY_477_A_SOURCE_ENVELOPE_V1',scan:PROOF_TIME,
    outbox:[PROOF_TIME,1,0],panel:PROOF_TIME,life:[PROOF_TIME,1],
    guard:options.invalid?'2020-01-01T00:00:00Z':PROOF_TIME};
  const facts = [[handoff,readback],[{fixture:true}],[guardian],['fixture-score-proof']];
  const proof = jobs.slice(2).map((j,i)=>({jobName:j.name,jobId:j.id,
    lines:facts[i].map(f=>[PROOF_TIME,encode(f)])}));
  const note = schema+' '+JSON.stringify({schema,asof:ASOF,run:101,head:HEAD,proof,
    ...(options.noAddon?{}:{a:addon})});
  const hdr = Array(27).fill(''), sum = Array(27).fill('');
  hdr[0]='KAYIT_KIMLIGI';hdr[1]='ASOF_ET';hdr[4]='KAYIT_TIPI';hdr[26]='KANIT_URL';
  sum[0]=ASOF+'|SUMMARY';sum[1]=ASOF;sum[4]='SUMMARY';sum[26]=WEB;
  const tab=(title,sheetId,columnCount,rows)=>({properties:{title,sheetId,
    gridProperties:{rowCount:1000,columnCount}},data:[{rowData:rows.map(row=>({
      values:row.map(formattedValue=>({formattedValue}))
    }))}]});
  const score=tab('SWING_SKOR_GUNLUK',7,35,[hdr,sum]);
  score.data[0].rowData[1].values[26].note=note;
  return {structuredContent:{spreadsheetId:SHEET,sheets:[
    tab('TARAMA_KAYITLARI',4,26,scan),tab('ADAY_GECMISI',5,26,history),
    tab('UYARI_OLAYLARI',6,20,queue),score]}};
}
const encodeGit=(url,body)=>({structuredContent:{url,display_url:url,content:JSON.stringify(body)}});
async function probe(options = {}) {
  const calls = {write:0,logs:0,markers:[],writer:0,task:0};
  const api = {
    mcp__codex_apps__automations_peek:async()=>({structuredContent:{automations:[{
      id:TASK,is_enabled:true,conversation_id:CHAT,default_timezone:'Europe/Istanbul',
      timing_mode:'exact_schedule',schedule:'RRULE:FREQ=HOURLY;BYMINUTE=57',
      prompt:++calls.task===4&&options.taskDrift?PROMPT+'\nfixture changed':PROMPT,
      run_details:{last_run:{id:TURN,recorded_status:'in_progress',scheduled_for:SLOT,
        started_at:SLOT,completed_at:null,chat_ref:null},latest_result:null}
    }]}}),
    clock__curr_time:async()=>({current_time:'2026-01-07 01:58:05 UTC'}),
    mcp__codex_apps__google_drive_get_spreadsheet_cells:async({ranges})=>{
      if(ranges.length!==1)return snapshot(options);
      const name=ranges[0];calls.markers.push(name);
      assert.match(name,/^XRAY_DELIVERY_[a-f0-9]{64}$/);
      if(options.existingMarker&&calls.markers.length===1)return {structuredContent:{spreadsheetId:SHEET}};
      const error='HTTPError: 400:\nRequest URL:\nhttps://sheets.googleapis.com/v4/spreadsheets/'+
        SHEET+'?ranges='+name+"&fields=note\n'message': 'Unable to parse range: "+name+
        "'\n'status': 'INVALID_ARGUMENT'";
      return {isError:true,structuredContent:{error_code:'INVALID_ARGUMENT',error}};
    },
    mcp__codex_apps__google_drive_get_spreadsheet_range:async()=>({structuredContent:{
      range:'UYARI_OLAYLARI!A1:T1000',majorDimension:'ROWS',values:options.queueDrift?queue.slice(0,-1):queue}}),
    mcp__codex_apps__github_fetch:async({url})=>{
      if(url===URL)return encodeGit(url,run);
      if(url===JOBS_URL)return encodeGit(url,{total_count:jobs.length,jobs});
      assert.match(url,/\?status=(in_progress|queued|pending|waiting|requested)&per_page=100$/);
      calls.writer++;
      const rows=options.activeWriter&&url.includes('in_progress')?[{path:WORKFLOW}]:[];
      return encodeGit(url,{total_count:rows.length,workflow_runs:rows});
    }
  };
  if(options.logs)api.mcp__codex_apps__github_fetch_workflow_job_logs=async({job_id})=>{
    calls.logs++;assert.ok(logs[job_id]);return logs[job_id];
  };
  if(options.post)api.mcp__codex_apps__google_drive_batch_update_spreadsheet=async()=>{
    calls.write++;throw Error('Synthetic test must not attempt a write');
  };
  const result=await A.runNaturalCandidate({mode:'natural_task',expected_asof:ASOF,spreadsheetId:SHEET,
    dryRun:options.dry!==false,trigger:{kind:'schedule',task_id:TASK,run_id:TURN}},api,Object.keys(api));
  assert.equal(result.post_calls,0);
  assert.equal(calls.write,0);
  const eligible=stage.verifiedCanary(stage.phase(PROMPT),result,ASOF,{id:TURN});
  return {result,calls,eligible};
}
test('missing write capability proves reads but cannot unlock A', async()=>{
  const {result,calls,eligible}=await probe();
  assert.equal(result.state,'A_READ_DRY_VERIFIED');
  assert.equal(result.stage,'A_POST_ADAPTER_UNAVAILABLE');
  assert.equal(result.count,2);
  assert.equal(eligible,false);
  assert.equal(calls.logs,0);
  assert.equal(calls.writer,5);
  assert.equal(calls.markers.length,2);
});
test('exact note and declared POST capability preserve genuine dry eligibility with zero POST', async()=>{
  const {result,calls,eligible}=await probe({post:true});
  assert.equal(result.state,'A_READY_DRY');
  assert.equal(eligible,true);
  const hash=compile(release.portable.code+'\nreturn XRAY_RESERVATION.sha256;')();
  assert.equal(calls.markers[0],'XRAY_DELIVERY_'+hash('XRAY_PERSONAL_DELIVERY_V1\nevent\n'+stopEvent[0]));
  assert.equal(calls.logs,0);
});
for(const [name, opts, expected] of [
  ['bad note and unavailable job logs',{post:true,invalid:true},'A_EXACT_JOB_LOG_ADAPTER_UNAVAILABLE'],
  ['A supplement missing and job logs unavailable',{post:true,noAddon:true},'A_EXACT_JOB_LOG_ADAPTER_UNAVAILABLE'],
  ['existing marker',{post:true,existingMarker:true},'A_MARKER_EXISTS_OR_UNCERTAIN'],
  ['queue drift',{post:true,queueDrift:true},'A_EVENT_BASELINE_DRIFT'],
  ['task prompt drift',{post:true,taskDrift:true},'A_PRERESERVATION_AUTHORITY_UNVERIFIED'],
  ['GitHub producer still active',{post:true,activeWriter:true},'A_PRERESERVATION_AUTHORITY_UNVERIFIED'],
  ['non-dry path lacks POST adapter',{logs:true,dry:false},'TURN_NATIVE_ADAPTER_UNAVAILABLE'],
  ['non-dry path lacks exact log adapter',{post:true,dry:false},'TURN_NATIVE_ADAPTER_UNAVAILABLE']
]){
  test(name+' fails closed',async()=>{
    const {result,eligible}=await probe(opts);
    assert.equal(result.stage,expected);
    assert.equal(eligible,false);
  });
}

const canarySeal='b'.repeat(64);
const isolatedCompile = src => () => {
  const value=compile(src)();
  return src.startsWith('const XRAY_B_NATURAL=')?{
    ...value, run:async()=>({state:'HOLD',stage:'B_STOP_PRIORITY_PENDING',post_calls:0})
  }:value;
};
const stagedOnly=Function('__xrayCompile','__xrayBlocks',blocks[11]+'\nreturn XRAY_AB_STAGED;')(
  isolatedCompile,()=>blocks);
async function inspectPhase(options={}) {
  const observed=options.early?'2026-01-07 01:57:40 UTC':'2026-01-07 01:58:05 UTC';
  const t0={id:TURN,recorded_status:'in_progress',scheduled_for:SLOT,
    started_at:options.early?'2026-01-07T01:57:19Z':SLOT,completed_at:null,chat_ref:null};
  let prompt=PROMPT, updates=0, reads=0;
  const record=last=>({id:TASK,is_enabled:true,conversation_id:CHAT,default_timezone:'Europe/Istanbul',
    timing_mode:'exact_schedule',schedule:'RRULE:FREQ=HOURLY;BYMINUTE=57',prompt,
    run_details:{last_run:last,latest_result:null}});
  const io={
    mcp__codex_apps__automations_peek:async()=>{
      reads++;
      const fresh=reads===1?options.changeBefore:options.changeAfter;
      return {structuredContent:{automations:[record({...t0,...fresh})]}};
    },
    clock__curr_time:async()=>({current_time:observed}),
    mcp__codex_apps__automations_update:async x=>{
      updates++;assert.equal(x.jawbone_id,TASK);assert.match(x.prompt,/ARMED_AFTER_CANARY_V1/);
      prompt=x.prompt;return {structuredContent:{success:true}};
    }
  };
  const proof={state:'A_READY_DRY',asof:ASOF,count:1,post_calls:0};
  const result=await stagedOnly.run(ASOF,io,Object.keys(io),{
    runNaturalCandidate:async args=>{assert.equal(args.dryRun,true);return proof;}
  },canarySeal,record(t0));
  assert.equal(result.post_calls,0);
  return {result,updates};
}
test('canary phase is not updated before the nominal schedule',async()=>{
  const {result,updates}=await inspectPhase({early:true});
  assert.equal(result.stage,'A_CANARY_BEFORE_SCHEDULED_FOR');
  assert.equal(updates,0);
});
for(const [field,t] of [
  ['started_at','2026-01-07T01:57:56Z'],['scheduled_for','2026-01-07T01:57:49Z']
]){
  test('same ID with drifted '+field+' is not authorized',async()=>{
    const {result,updates}=await inspectPhase({changeBefore:{[field]:t}});
    assert.equal(result.stage,'A_CANARY_ACTIVATION_DRIFT');
    assert.equal(updates,0);
  });
}
test('same-ID second start during phase readback is not reported as armed',async()=>{
  const {result,updates}=await inspectPhase({changeAfter:{started_at:'2026-01-07T01:57:56Z'}});
  assert.equal(result.stage,'A_CANARY_ACTIVATION_READBACK');
  assert.equal(updates,1);
});
test('the eligible same natural slot still promotes exactly once after its scheduled time',async()=>{
  const {result,updates}=await inspectPhase();
  assert.equal(result.state,'A_CANARY_VERIFIED_ARMED_NEXT_NATURAL');
  assert.equal(updates,1);
});
test('bad note with exact job logs preserves fallback and dry acceptance',async()=>{
  const {result,calls,eligible}=await probe({post:true,logs:true,invalid:true});
  assert.equal(result.state,'A_READY_DRY');
  assert.equal(eligible,true);
  assert.equal(calls.logs,3);
});

test('all declared adapters retain the same STOP-first dry result and do not read unnecessary logs',async()=>{
  const {result,calls,eligible}=await probe({post:true,logs:true});
  assert.equal(result.state,'A_READY_DRY');
  assert.equal(eligible,true);
  assert.equal(calls.logs,0);
  assert.equal(calls.markers.length,2);
});
for(const [name,flag,expected] of [
  ['marker','existingMarker','A_MARKER_EXISTS_OR_UNCERTAIN'],
  ['queue','queueDrift','A_EVENT_BASELINE_DRIFT'],
  ['task','taskDrift','A_PRERESERVATION_AUTHORITY_UNVERIFIED'],
  ['producer','activeWriter','A_PRERESERVATION_AUTHORITY_UNVERIFIED']
]){
  test('prior deny behavior with all capabilities: '+name,async()=>{
    const {result,eligible}=await probe({post:true,logs:true,[flag]:true});
    assert.equal(result.stage,expected);
    assert.equal(eligible,false);
  });
}
