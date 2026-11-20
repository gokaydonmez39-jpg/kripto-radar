'use strict';

const assert=require('node:assert/strict');
const {test}=require('node:test');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');

const runtimeText=readFileSync(process.env.XRAY_TEST_RUNTIME || join(__dirname,'xray_477_task_runtime_v3.json'),'utf8');
const rt=JSON.parse(runtimeText);
const Portable=Function(rt.portable.code+'\nreturn XRAY_RESERVATION;')();
const asof='2026-01-06', opened='2026-01-05', sheet='synthetic_private_sheet_identifier';
const repo='gokaydonmez39-jpg/kripto-radar', path='.github/workflows/xray-personal-477-eod.yml';
const head='a'.repeat(40), scope='b'.repeat(64), policy='c'.repeat(64), version='synthetic-v1';
const from=asof+'T23:15:10Z', seen=asof+'T23:16:10Z', to=asof+'T23:17:10Z';
const runId=109, runURL=`https://api.github.com/repos/${repo}/actions/runs/${runId}`;
const webURL=`https://github.com/${repo}/actions/runs/${runId}`;
const jobsURL=runURL+'/attempts/1/jobs?per_page=100';
const symbol='SYNTH', episode=opened+'|'+symbol, score='72.5';
const noteSchema='XRAY_477_B_SOURCE_ENVELOPE_V1';
const git=(url,data)=>({structuredContent:{url,display_url:url,content:JSON.stringify(data)}});
const qualified=()=>({id:runId,url:runURL,path,event:'schedule',repository:{full_name:repo},head_branch:'main',
  head_sha:head,run_attempt:1,status:'completed',conclusion:'success',created_at:from,run_started_at:from,updated_at:to});
const jobNames=['offline-guard','private-sheets-auth-preflight','daily-private-scan','private-episode-followups',
 'guardian-acceptance','daily-private-score-acceptance'];
const render=value=>typeof value==='string'?value:JSON.stringify(value);
const grid=(title,sheetId,columnCount,rows)=>({properties:{title,sheetId,gridProperties:{rowCount:1000,columnCount}},
  data:[{rowData:rows.map(row=>({values:row.map(formattedValue=>({formattedValue}))}))}]});

function fixture(){
 const jobs=jobNames.map((name,i)=>({id:i+201,name,run_id:runId,run_url:runURL,status:'completed',
   conclusion:'success',head_branch:'main',head_sha:head,run_attempt:1,started_at:from,completed_at:to}));
 const handoff='XRAY_PERSONAL_GITHUB_HANDOFF=PASS_477_477_SOURCE_POLICY_SHA_BOUND_PRIVATE';
 const proofLines=[
  [handoff,{status:'PRIVATE_SHEET_READBACK_PASS',asof_et:asof,candidates:0}],
  [{status:'SWING_SCORE_PRIVATE_READBACK_PASS',asof_et:asof,execution:'NONE',active_episodes:1,scoreable:1}],
  [{schema:'XRAY_PERSONAL_PRIVATE_EVIDENCE_AUDIT_V1',status:'READ_ONLY_EVIDENCE_AUDIT',execution:'NONE',
    sheet_writes:0,last_verified_scan_asof:asof,last_asof_score:'SUMMARY_PRESENT',score_count:1,
    score_hold_count:0,scored_active_episodes:1}],
  ['XRAY_DAILY_SWING_SCORE=PRIVATE_READBACK_PASS_ASOF_'+asof+'_NOT_CHATGPT_DELIVERY']
 ];
 const proof=jobs.slice(2).map(({name:jobName,id:jobId},i)=>({jobName,jobId,
   lines:proofLines[i].map(l=>[seen,render(l)])}));
 const note=noteSchema+' '+JSON.stringify({schema:noteSchema,asof,run:runId,head,proof});
 const header=['KAYIT_KIMLIGI','ASOF_ET','EPIZOT_KIMLIGI','SEMBOL','KAYIT_TIPI','SIRA','SKOR_100','TREND_20',
   'RSI_15','RVOL_15','REL_GUC_15','LIKIDITE_10','RISK_15','FIYAT_YAPISI_10','GUNCEL_IEX_CLOSE_USD',
   'ORIJINAL_REFERANS_USD','ORIJINAL_STOP_USD','ORIJINAL_HEDEF_2R_USD','TEORIK_DEGISIM_YUZDE','STOPA_MESAFE_YUZDE',
   'HEDEFE_MESAFE_YUZDE','TAKIP_SEANSI','RSI14','RVOL20','20SEANS_GETIRI_YUZDE','RISK_NOTU','KANIT_URL',
   'BILDIRIM_DURUMU','BILDIRIM_ZAMANI_TR','KAYIT_SHA256','KAPSAM_SHA256','ALGORITMA_SHA256','SKOR_SURUMU',
   'ORT_IEX_DOLAR_HACMI','ATR_RISK_YUZDE'];
 const scoreDigest=Portable.scoreDigest(asof,scope,policy,[[episode,score,'','101']],version);
 const summary=Array(35).fill(''), row=Array(35).fill('');
 const set=(a,start,values)=>a.splice(start,values.length,...values);
 set(summary,0,[asof+'|SUMMARY',asof,'','','SUMMARY','1','1','0','1']);
 set(summary,26,[webURL,'READY_FOR_CHATGPT_DAILY_DIGEST','',scoreDigest,scope,policy,version]);
 set(row,0,[asof+'|'+episode,asof,episode,symbol,'EPISODE','1',score,'15','10','10','10','8','12','7.5',
   '101','100','90','120','1','10.89','18.81','1','60','1.5','','']);
 set(row,26,[webURL,'','',scoreDigest,scope,policy,version]);
 const scoreTab=grid('SWING_SKOR_GUNLUK',11,35,[header,summary,row]);
 scoreTab.data[0].rowData[1].values[26].note=note;
 const scan=grid('TARAMA_KAYITLARI',12,26,[['ASOF ET','ÜRETİM KANALI','İSTENEN','İŞLENEN','GEÇERLİ','EKSİK',
   'FINAL READY','YENİ KAYIT','RUN KANITI','DURUM / VERİ SINIRI'],[asof,'schedule','477','477','477','0','TRUE','0',webURL,'synthetic']]);
 const history=grid('ADAY_GECMISI',13,26,[['ALARM KİMLİĞİ','ASOF ET','SEMBOL','IEX KAPANIŞ USD','STOP 2ATR',
   'HEDEF 2R','TAKİP DURUMU'],[episode,opened,symbol,'100','90','120','AÇIK • 1/15 SEANS']]);
 const event=grid('UYARI_OLAYLARI',14,20,[['OLAY_ANAHTARI'],['synthetic-pending-STOP']]);
 const snapshot={structuredContent:{spreadsheetId:sheet,sheets:[scan,scoreTab,history,event]}};
 return {snapshot,
   runResponse:git(runURL,qualified()),jobsResponse:git(jobsURL,{total_count:jobs.length,jobs})};
}

for(const kind of ['structured','nested','ack-missing','post-throws','readback-fails']){
 test('B '+kind+' makes one POST and always attempts an independent GET',async()=>{
  const i=fixture();
  const blocks=rt.blocks.map(b=>b.replaceAll('XRAY_CONFIG_SHEET_ID_V1',sheet));
  const compile=code=>()=>Function('__xrayCompile','__xrayBlocks','__xrayPortable',code)(compile,()=>blocks,()=>rt.portable.code);
  const driver=compile(blocks[2]+'\nreturn XRAY_B_DRIVER;')();
  const stamp=asof+' 23:18 TRT';
  const initial=await driver.read({expected_asof:asof,prompt:'fixture',stamp},{
    cells:async()=>i.snapshot,github:async({url})=>url===runURL?i.runResponse:i.jobsResponse});
  assert.equal(initial.state,'B_READ_VERIFIED');
  const before=structuredClone(initial.x.baseline),after=structuredClone(before), sequence=[];
  const io={cells:async({ranges})=>{
    const m=ranges[0],error='HTTPError: 400:\nRequest URL:\nhttps://sheets.googleapis.com/v4/spreadsheets/'+sheet+
      '?ranges='+m+"&fields=note\n'message': 'Unable to parse range: "+m+"'\n'status': 'INVALID_ARGUMENT'";
    return {isError:true,structuredContent:{error_code:'INVALID_ARGUMENT',error}};
  },range:async()=>{
    const written=sequence.includes('POST');sequence.push(written?'AFTER':'BEFORE');
    if(written&&kind==='readback-fails')throw Error('synthetic read failure');
    return {structuredContent:{range:'SWING_SKOR_GUNLUK!A1:AI1000',majorDimension:'ROWS',values:written?after:before}};
  },prePostAuth:async()=>true,post:async({spreadsheet_id,requests})=>{
    sequence.push('POST');assert.equal(spreadsheet_id,sheet);
    assert.equal(requests.length,2);
    const r=requests[1].updateCells;
    after[r.start.rowIndex][27]=r.rows[0].values[0].userEnteredValue.stringValue;
    after[r.start.rowIndex][28]=r.rows[0].values[1].userEnteredValue.stringValue;
    if(kind==='post-throws')throw Error('synthetic ambiguous transport');
    const raw={spreadsheetId:sheet,replies:[structuredClone(requests[0]),{}],updatedSpreadsheet:null};
    if(kind==='ack-missing')return {structuredContent:{status:'success'}};
    if(kind==='nested')return {structuredContent:{result:{structuredContent:raw}}};
    return {content:[{type:'text',text:'Action completed.'}],structuredContent:raw,isError:false};
  }};
  const out=await driver.finish(initial,{prompt:'fixture',stamp,scheduled_slot_verified:true,
    single_writer_verified:true,stop_priority_checked:true},io);
  assert.deepEqual(sequence,['BEFORE','POST','AFTER']); assert.equal(out.post_calls,1);
  if(['structured','nested'].includes(kind)){
   assert.equal(out.state,'EMIT_NOW');assert.match(out.text,/POST=ACK_1 \| GET_VERIFY=PASS/);
  }else if(kind==='readback-fails')assert.equal(out.stage,'READBACK_UNCERTAIN_DO_NOT_RESEND');
  else assert.equal(out.stage,'POST_UNCERTAIN_DO_NOT_RESEND');
 });
}


// Regression: A reservation is not a ChatGPT-delivered STOP card.
// The guard is read from the exact versioned runtime blob used by the native task.
const bNaturalText=rt.blocks.filter(s=>/^const XRAY_B_NATURAL\s*=/m.test(s));
assert.equal(bNaturalText.length,1);
const gStart=bNaturalText[0].indexOf(' function stopQueue(response,asof,priorA,sourceRunId){');
const gEnd=bNaturalText[0].indexOf('\n function getOnlyRetry(',gStart);
assert.ok(gStart>0&&gEnd>gStart,'stop guard must be unique');
const stopGate=Function('unpack',bNaturalText[0].slice(gStart,gEnd)+'\nreturn stopQueue;')(r=>r);
const riskDate='2026-11-20', sourceRun='777';
const riskHeaders=Array.from({length:20},(_,j)=>'FIELD_'+j);
for(const [at,label] of [[0,'OLAY_ANAHTARI'],[4,'OLAY_ASOF_ET'],[5,'OLAY_KODU'],[6,'ONCELIK'],[17,'BILDIRIM_DURUMU']])
 riskHeaders[at]=label;
const RISK_PENDING='EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST';
const RISK_RESERVED='ALERT_REQUESTED_NOT_DEVICE_ACK';
const riskRow=(key,status,code='STOP_TOUCHED',day=riskDate)=>{
 const row=Array(20).fill('');
 row[0]=key;row[4]=day;row[5]=code;row[6]=code==='STOP_TOUCHED'?'KRITIK':'YENI AL';row[17]=status;
 return row;
};
const riskSheet=(...rows)=>({range:'UYARI_OLAYLARI!A1:T'+(rows.length+1),majorDimension:'ROWS',values:[riskHeaders,...rows]});
const aReceipt=(keys,day=riskDate,run=sourceRun,count=keys.length)=>({
 content_text:'## 🦖 XRAY NASDAQ Ω · Olaylar\n\nXRAY_A_RECEIPT_V1 | '+day+' | '+run+
  ' | 2026-11-21 03:00 TRT | COUNT='+count+' | POST=ACK_1 | GET_VERIFY=PASS\n'+
  keys.map(k=>'Olay: ' + String.fromCharCode(96)+k+String.fromCharCode(96)).join('\n'),
 content_truncated:false,is_failure_message:false,requires_user_action:false
});
for(const [name,rows,receipt,run,expected] of [
 ['nonrisk reservation cannot block B',[riskRow('al',RISK_RESERVED,'AL_NEW_EPISODE')],null,sourceRun,null],
 ['pending STOP blocks B',[riskRow('one',RISK_PENDING)],null,sourceRun,'B_STOP_PRIORITY_PENDING'],
 ['reserved STOP without output receipt blocks B',[riskRow('one',RISK_RESERVED)],null,sourceRun,'B_STOP_A_RECEIPT_UNVERIFIED'],
 ['valid natural A receipt releases B',[riskRow('one',RISK_RESERVED)],aReceipt(['one']),sourceRun,null],
 ['wrong session cannot release B',[riskRow('one',RISK_RESERVED)],aReceipt(['one'],'2026-11-19'),sourceRun,'B_STOP_A_RECEIPT_UNVERIFIED'],
 ['wrong EOD run cannot release B',[riskRow('one',RISK_RESERVED)],aReceipt(['one']),"778",'B_STOP_A_RECEIPT_UNVERIFIED'],
 ['wrong event key cannot release B',[riskRow('one',RISK_RESERVED)],aReceipt(['two']),sourceRun,'B_STOP_A_RECEIPT_UNVERIFIED'],
 ['partial A receipt blocks B',[riskRow('one',RISK_RESERVED),riskRow('two',RISK_RESERVED)],aReceipt(['one']),sourceRun,'B_STOP_A_RECEIPT_UNVERIFIED'],
 ['all two risk keys release B',[riskRow('one',RISK_RESERVED),riskRow('two',RISK_RESERVED)],aReceipt(['one','two']),sourceRun,null],
 ['truncated task result blocks B',[riskRow('one',RISK_RESERVED)],{...aReceipt(['one']),content_truncated:true},sourceRun,'B_STOP_A_RECEIPT_UNVERIFIED'],
 ['failed task result blocks B',[riskRow('one',RISK_RESERVED)],{...aReceipt(['one']),is_failure_message:true},sourceRun,'B_STOP_A_RECEIPT_UNVERIFIED'],
 ['A count lower than reserved STOP count blocks B',[riskRow('one',RISK_RESERVED),riskRow('two',RISK_RESERVED)],aReceipt(['one','two'],riskDate,sourceRun,1),sourceRun,'B_STOP_A_RECEIPT_UNVERIFIED'],
 ['mixed queued STOP remains priority',[riskRow('one',RISK_RESERVED),riskRow('two',RISK_PENDING)],aReceipt(['one']),sourceRun,'B_STOP_PRIORITY_PENDING'],
 ['duplicate event identity fails closed',[riskRow('one',RISK_RESERVED),riskRow('one',RISK_RESERVED)],aReceipt(['one']),sourceRun,'B_STOP_QUEUE_IDENTITY'],
 ['old session event cannot block current B',[riskRow('old',RISK_RESERVED,'STOP_TOUCHED','2026-11-19')],null,sourceRun,null],
 ['missing EOD ID blocks B',[riskRow('one',RISK_RESERVED)],aReceipt(['one']),null,'B_STOP_A_RECEIPT_UNVERIFIED'],
 ['duplicate A receipt lines block B',[riskRow('one',RISK_RESERVED)],{...aReceipt(['one']),content_text:aReceipt(['one']).content_text+'\n'+aReceipt(['one']).content_text},sourceRun,'B_STOP_A_RECEIPT_UNVERIFIED'],
 ['duplicate same event in A text blocks B',[riskRow('one',RISK_RESERVED)],{...aReceipt(['one']),content_text:aReceipt(['one']).content_text+'\nOlay: ' + String.fromCharCode(96)+'one'+String.fromCharCode(96)},sourceRun,'B_STOP_A_RECEIPT_UNVERIFIED']
]){
 test('B STOP receipt boundary: '+name,()=>{
  const out=stopGate(riskSheet(...rows),riskDate,receipt,run);
  assert.equal(out,expected);
 });
}
