function xrayAStaticCanary(binding) {
const N=(()=>{const id=binding.id; const TIMEZONE="Europe/Istanbul";
const REPO="gokaydonmez39-jpg/kripto-radar",ROOT="https://api.github.com/repos/"+REPO+"/actions/runs";
const WRITER=".github/workflows/xray-personal-477-eod.yml";
const ACTIVE=["in_progress","queued","pending","waiting","requested"];
const unpack=r=>r?.isError===true?null:(r?.structuredContent?.result??r?.structuredContent??r?.result??null);
const epoch=x=>typeof x==="string"?Date.parse(x):NaN;
function natural(a,now,trigger){
const r=a?.run_details?.last_run, n=epoch(now), t=epoch(r?.scheduled_for), s=epoch(r?.started_at);
if(a?.id!==id||a?.default_timezone!==TIMEZONE||
a?.is_enabled!==true||!/^RRULE:FREQ=HOURLY;BYMINUTE=57$/m.test(a.schedule??"")||
r?.recorded_status!=="in_progress"||r.completed_at!==null||a.run_details.latest_result?.run_id===r.id||
!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(r.id??"")||
![t,s,n].every(Number.isFinite)||s>n+999)return null;
const minute=new Intl.DateTimeFormat("en-GB",{timeZone:TIMEZONE,hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(t).find(x=>x.type==="minute")?.value;
if(minute!=="57")return null;
if(a.conversation_id!==binding.chat || a.timing_mode!=="exact_schedule")return null;
if(trigger?.kind!==undefined && trigger.kind!=="schedule")return null;
if(trigger?.task_id!==undefined && trigger.task_id!==id)return null;
if(trigger?.run_id!==undefined && trigger.run_id!==r.id)return null;
return {id:r.id,scheduled_for:r.scheduled_for,started_at:r.started_at,binding:"USER_AUTHORIZED_ACTIVE_TASK_RECORD"};
}
function naturalB(a,now,trigger){
const b=natural(a,now,trigger);
if(!b)return null;
const n=epoch(now), t=epoch(b.scheduled_for), s=epoch(b.started_at);
return n-s<=20*60*1000&&s>=t-12*60*1000&&s<=t+20*60*1000?b:null;
}
async function writer(K){
const urls=ACTIVE.map(status=>ROOT+"?status="+status+"&per_page=100");
const classify=(r,url)=>{
const x=unpack(r);if(x?.url!==url||typeof x.content!=="string")return "B_WRITER_ACTIVITY_UNVERIFIED";
let y;try{y=JSON.parse(x.content);}catch(_){return "B_WRITER_ACTIVITY_UNVERIFIED";}
if(!Number.isSafeInteger(y.total_count)||y.total_count<0||!Array.isArray(y.workflow_runs)||
y.workflow_runs.some(z=>typeof z?.path!=="string"))return "B_WRITER_ACTIVITY_INCOMPLETE";
if(y.workflow_runs.some(z=>z.path===WRITER))return "B_SAME_SHEET_PRODUCER_ACTIVE";
if(y.total_count===y.workflow_runs.length)return null;
return y.total_count<=100&&y.total_count>y.workflow_runs.length?"B_WRITER_RECHECK_LIST":"B_WRITER_ACTIVITY_INCOMPLETE";
};
const rs=await Promise.all(urls.map(url=>K.github({url})));
const states=rs.map((r,j)=>classify(r,urls[j]));
if(states.includes("B_SAME_SHEET_PRODUCER_ACTIVE"))return "B_SAME_SHEET_PRODUCER_ACTIVE";
const hard=states.find(s=>s!==null&&s!=="B_WRITER_RECHECK_LIST");if(hard)return hard;
const retry=states.reduce((acc,s,i)=>s==="B_WRITER_RECHECK_LIST"?[...acc,i]:acc,[]);
if(retry.length!==1)return retry.length?"B_WRITER_ACTIVITY_INCOMPLETE":null;
const url=urls[retry[0]], after=classify(await K.github({url}),url);
return after==="B_WRITER_RECHECK_LIST"?"B_WRITER_ACTIVITY_INCOMPLETE":after;
}
return {natural:naturalB,writer};})();
const P=(()=>{const CANARY = 'CANARY_LOCKED_V1';
const PHASE_RE = /^XRAY_A_DEPLOYMENT_STAGE=([^\r\n]+)$/gm;
const UUID = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const TASK = binding.id;
const CHAT = binding.chat;
const SHA_PATTERN = /^[0-9a-f]{64}$/;
const iso = x => typeof x==='string' && /^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC$/.test(x)
? x.replace(' ','T').replace(' UTC','Z') : '';
const state = (stage, post_calls=0) => ({state:'HOLD',stage,post_calls});
const raw = (o,k) => {
for(let n=0;n<7&&o&&typeof o==='object'&&o.isError!==true;n++){
if((k==='automations'&&Array.isArray(o[k]))||(k==='success'&&typeof o[k]==='boolean')||
(k==='current_time'&&typeof o[k]==='string'))return o;
o=o.structuredContent??o.result??null;
}
return null;
};
const own = o => raw(o,'automations')?.automations.filter(a=>a?.id===TASK);
const identity=(a,b)=>a&&b&&['id','title','schedule','timing_mode','default_timezone','conversation_id','is_enabled','environment_selection'].every(x=>a[x]===b[x]);
const phase = p => {
const found = [...p.matchAll(PHASE_RE)];
if(found.length!==1)return null;
if(found[0][1]===CANARY)return {kind:CANARY,line:found[0][0]};
const [kind,run,asof,stamp,seal]=found[0][1].split('|');
if(kind!=='ARMED_AFTER_CANARY_V1'||!UUID.test(run??'')||!/^\d{4}-\d\d-\d\d$/.test(asof??'')||
!Number.isFinite(Date.parse(stamp))||!SHA_PATTERN.test(seal??'')||found[0][1]!==[kind,run,asof,stamp,seal].join('|'))return null;
return {kind,run,asof,stamp,seal,line:found[0][0]};
};
const verifiedCanary = (p,c,r,s) => p?.kind===CANARY&&c?.state==='A_READY_DRY'&&c.post_calls===0&&
c.asof===r&&Number.isSafeInteger(c.count)&&c.count>=1&&c.count<=6&&UUID.test(s?.id??'');
function promotePrompt(p,c,asof,slot,checkedAt,seal) {
const f=phase(p);
if(!verifiedCanary(f,c,asof,slot)||!SHA_PATTERN.test(seal)||!Number.isFinite(Date.parse(checkedAt))||
p.split(f.line).length!==2)return null;
return p.replace(f.line,'XRAY_A_DEPLOYMENT_STAGE=ARMED_AFTER_CANARY_V1|'+[slot.id,asof,checkedAt,seal].join('|'));
}
return {phase,promotePrompt,identity,raw,own,iso,verifiedCanary};})();
const SHEET=binding.sheet;
function classifyMarker(result, marker) {
if(typeof marker!=="string"||!/^XRAY_DELIVERY_[0-9a-f]{64}$/.test(marker))return {kind:"uncertain"};
const p=result?.structuredContent?.result??result?.structuredContent??result?.result;
if(result?.isError!==true&&p?.spreadsheetId===SHEET)return {kind:"exists"};
const error=p?.error, prefix="https://sheets.googleapis.com/v4/spreadsheets/"+SHEET+"?ranges="+marker;
const thrown=result?.marker_lookup_exception;
if(result?.isError===true&&typeof thrown==="string"&&
thrown.startsWith("INVALID_ARGUMENT: Error code: INVALID_ARGUMENT; Error: HTTPError: 400:")&&
thrown.includes("Request URL:\n"+prefix+"&")&&
thrown.includes("'status': 'INVALID_ARGUMENT'")&&
new RegExp("'message': 'Unable to parse range: '\\s*'"+marker+"'").test(thrown))
return {kind:"exact_not_found",name:marker,spreadsheetId:SHEET};
if(result?.isError===true&&p?.error_code==="INVALID_ARGUMENT"&&typeof error==="string"&&
error.startsWith("HTTPError: 400:")&&error.includes("Request URL:\n"+prefix+"&")&&
error.includes("'message': 'Unable to parse range: "+marker+"'")&&
error.includes("'status': 'INVALID_ARGUMENT'"))
return {kind:"exact_not_found",name:marker,spreadsheetId:SHEET};
return {kind:"uncertain"};
}
/* Personal 477 pure planner. No tools, filesystem, network or notification. */
const XRAY_RESERVATION = (() => {
"use strict";
const EH = ["OLAY_ANAHTARI","ADAY_ANAHTARI","AL_ASOF_ET","SEMBOL","OLAY_ASOF_ET","OLAY_KODU","ONCELIK","IEX_KAPANIS_USD","ORIJINAL_STOP_USD","ORIJINAL_HEDEF_USD","SMA20","SMA50","DESTEK_20","DIRENC_20","TEPE_52","TAKIP_SEANSI","BIRINCIL_KANIT_URL","BILDIRIM_DURUMU","BILDIRIM_ZAMANI_TR","NOT"];
const DH = ["KAYIT_KIMLIGI","ASOF_ET","EPIZOT_KIMLIGI","SEMBOL","KAYIT_TIPI","SIRA","SKOR_100","TREND_20","RSI_15","RVOL_15","REL_GUC_15","LIKIDITE_10","RISK_15","FIYAT_YAPISI_10","GUNCEL_IEX_CLOSE_USD","ORIJINAL_REFERANS_USD","ORIJINAL_STOP_USD","ORIJINAL_HEDEF_2R_USD","TEORIK_DEGISIM_YUZDE","STOPA_MESAFE_YUZDE","HEDEFE_MESAFE_YUZDE","TAKIP_SEANSI","RSI14","RVOL20","20SEANS_GETIRI_YUZDE","RISK_NOTU","KANIT_URL","BILDIRIM_DURUMU","BILDIRIM_ZAMANI_TR","KAYIT_SHA256","KAPSAM_SHA256","ALGORITMA_SHA256","SKOR_SURUMU","ORT_IEX_DOLAR_HACMI","ATR_RISK_YUZDE"];
const PENDING = "EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST";
const REQUESTED = "ALERT_REQUESTED_NOT_DEVICE_ACK";
const READY = "READY_FOR_CHATGPT_DAILY_DIGEST";
const SUPPRESSED = "DUPLICATE_ACTIVE_EPISODE_NO_NEW_ALERT";
const DISPUTE = "DATA_DISPUTE_REVIEW_REQUIRED";
const STATES = new Set([PENDING,REQUESTED,"DELIVERY_UNKNOWN_REVIEW_REQUIRED","DEVICE_ACK_USER_ATTESTED",DISPUTE,SUPPRESSED]);
const TYPES = new Set(["AL_NEW_EPISODE","STOP_TOUCHED","GAP_BELOW_STOP","BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS","TARGET_TOUCHED","TIME_EXIT_AT_CLOSE","SMA20_CROSS_DOWN","SMA50_CROSS_DOWN","SUPPORT_20_BREAKDOWN","DAILY_DROP_2ATR","NEAR_STOP","NEAR_STOP_1ATR","52_SESSION_BREAKOUT","NEW_52_SESSION_HIGH","OFFICIAL_ISSUER_RISK","CORPORATE_ACTION_REVIEW"]);
const requireIt=(x,c)=>{if(!x)throw new Error(c);};
const same=(a,b)=>{
if(a===b)return true;
if(a===null||b===null||typeof a!=="object"||typeof b!=="object"||Array.isArray(a)!==Array.isArray(b))return false;
const ak=Object.keys(a),bk=Object.keys(b);
return ak.length===bk.length&&ak.every(k=>Object.hasOwn(b,k)&&same(a[k],b[k]));
};
function day(s){
requireIt(typeof s==="string"&&/^\d{4}-\d{2}-\d{2}$/.test(s)&&!s.startsWith("0000"),"BAD_DATE");
const d=new Date(s+"T00:00:00Z");
requireIt(Number.isFinite(+d)&&d.toISOString().slice(0,10)===s,"BAD_DATE");return s;
}
function matrix(rows,n){
requireIt(Array.isArray(rows)&&rows.length>0&&rows.length<=50001,"MATRIX_SIZE");
return rows.map(r=>{
requireIt(Array.isArray(r)&&r.length<=n&&Array.from(r).every(v=>typeof v==="string"),"MATRIX_SHAPE");
return r.concat(Array(n-r.length).fill(""));
});
}
function sha256(str){
const bytes=[];for(const c of str){const x=c.codePointAt(0);requireIt(x<0xd800||x>0xdfff,"INVALID_UTF8");if(x<128)bytes.push(x);else if(x<2048)bytes.push(192|(x>>6),128|(x&63));else if(x<65536)bytes.push(224|(x>>12),128|((x>>6)&63),128|(x&63));else bytes.push(240|(x>>18),128|((x>>12)&63),128|((x>>6)&63),128|(x&63));}
const bit=bytes.length*8;requireIt(bit<=0xffffffff,"HASH_SIZE");bytes.push(128);while(bytes.length%64!==56)bytes.push(0);bytes.push(0,0,0,0,(bit>>>24)&255,(bit>>>16)&255,(bit>>>8)&255,bit&255);
const h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
const k=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
const ro=(v,n)=>(v>>>n)|(v<<(32-n)), w=new Int32Array(64);
for(let p=0;p<bytes.length;p+=64){
for(let i=0;i<16;i++){const j=p+4*i;w[i]=(bytes[j]<<24)|(bytes[j+1]<<16)|(bytes[j+2]<<8)|bytes[j+3];}
for(let i=16;i<64;i++){const a=w[i-15],b=w[i-2];w[i]=(w[i-16]+(ro(a,7)^ro(a,18)^(a>>>3))+w[i-7]+(ro(b,17)^ro(b,19)^(b>>>10)))|0;}
let [a,b,c,d,e,f,g,j]=h;
for(let i=0;i<64;i++){const t=(j+(ro(e,6)^ro(e,11)^ro(e,25))+((e&f)^((~e)&g))+k[i]+w[i])|0;const u=((ro(a,2)^ro(a,13)^ro(a,22))+((a&b)^(a&c)^(b&c)))|0;j=g;g=f;f=e;e=(d+t)|0;d=c;c=b;b=a;a=(t+u)|0;}
[a,b,c,d,e,f,g,j].forEach((v,i)=>{h[i]=(h[i]+v)|0;});
}
return h.map(v=>(v>>>0).toString(16).padStart(8,"0")).join("");
}
function eventIndex(rows){
const found=new Map();
for(let i=1;i<rows.length;i++){
const r=rows[i];if(r.every(x=>x===""))continue;
const [key,ep,open,sym,event,type]=r;
requireIt(!found.has(key)&&/^[A-Z0-9.]{1,16}$/.test(sym)&&TYPES.has(type)&&STATES.has(r[17])&&day(event)>=day(open)&&ep===open+"|"+sym,"EVENT_LEDGER_INVALID");
const pref=ep+"|"+event+"|"+type+"|", suffix=key.slice(pref.length);
requireIt(key.startsWith(pref)&&/^[1-9]\d{0,14}$/.test(suffix),"EVENT_IDENTITY");
if(type==="CORPORATE_ACTION_REVIEW")requireIt(sym==="ROKU"&&open<="2026-11-06"&&event==="2026-11-09"&&r[6]==="KURUMSAL_ISLEM"&&r[7]===""&&r[19].includes("https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2026-806"),"CORPORATE_ACTION");
if(r[17]===DISPUTE)requireIt(type==="NEW_52_SESSION_HIGH","DISPUTE_EVENT");
if(r[17]===SUPPRESSED)requireIt(type==="AL_NEW_EPISODE","SUPPRESSION_EVENT");
found.set(key,i);
}
return found;
}
function calc(input){
requireIt(input&&typeof input==="object"&&["event","digest"].includes(input.kind),"BAD_KIND");
const {sheet_id:sid,asof,stamp,kind}=input, event=kind==="event", head=event?EH:DH, col=event?17:27;
requireIt(Number.isInteger(sid)&&sid>=0&&sid<=2147483647,"SHEET_ID");
requireIt(typeof stamp==="string"&&/^\d{4}-\d{2}-\d{2} (?:[01]\d|2[0-3]):[0-5]\d TRT$/.test(stamp)&&day(stamp.slice(0,10))>=day(asof),"STAMP");
const before=matrix(input.baseline,head.length);requireIt(same(input.baseline[0],head),"HEADER");
let targets;const status=event?REQUESTED:"REQUESTED_NOT_DEVICE_ACK";
if(event){
const keys=input.keys, index=eventIndex(before);
requireIt(Array.isArray(keys)&&keys.length>0&&keys.length<=6&&new Set(keys).size===keys.length,"BAD_EVENT_KEYS");
targets=keys.map(key=>{const i=index.get(key);requireIt(Number.isInteger(i)&&before[i][4]===asof&&before[i][17]===PENDING&&before[i][18]==="","NOT_CURRENT_PENDING");return [key,i];});
}else{
const key=asof+"|SUMMARY", hits=[];
requireIt(typeof input.verified_sha==="string"&&/^[a-f0-9]{64}$/.test(input.verified_sha),"BAD_VERIFIED_SHA");
for(let i=1;i<before.length;i++){const r=before[i];if(r[0]===key||r[1]===asof&&r[4]==="SUMMARY")hits.push(i);}
requireIt(hits.length===1,"DIGEST_IDENTITY");const i=hits[0],r=before[i];
requireIt(r[0]===key&&r[1]===asof&&r[4]==="SUMMARY"&&same(r.slice(27,30),[READY,"",input.verified_sha]),"NOT_CURRENT_READY");targets=[[key,i]];
}
const requests=targets.flatMap(([key,i])=>{
const id=sha256("XRAY_PERSONAL_DELIVERY_V1\n"+kind+"\n"+key);
return [{addNamedRange:{namedRange:{namedRangeId:"xray_"+id,name:"XRAY_DELIVERY_"+id,range:{sheetId:sid,startRowIndex:i,endRowIndex:i+1,startColumnIndex:col,endColumnIndex:col+2}}}},{updateCells:{start:{sheetId:sid,rowIndex:i,columnIndex:col},rows:[{values:[status,stamp].map(stringValue=>({userEnteredValue:{stringValue}}))}],fields:"userEnteredValue"}}];
});
return {requests,before,targets,status,col,stamp,head};
}
function operation(input){
try{
const p=calc(input);
if(input.action==="plan")return {status:"PLAN_ONLY",requests:p.requests};
requireIt(input.action==="verify","BAD_ACTION");
const r=input.response,id=input.spreadsheet_id;
requireIt(typeof id==="string"&&id.length>0&&r&&r.spreadsheetId===id&&Array.isArray(r.replies)&&r.replies.length===p.requests.length,"POST_RECEIPT");
for(let i=0;i<p.requests.length;i+=2)requireIt(same(r.replies[i],p.requests[i])&&same(r.replies[i+1],{}),"POST_RECEIPT_DRIFT");
p.targets.forEach(([,i])=>{p.before[i].splice(p.col,2,p.status,p.stamp);});
requireIt(same(p.before,matrix(input.observed,p.head.length)),"READBACK_DRIFT");
return {reserved:p.targets.length,message_proven:false,device_ack:false};
}catch(_){return {status:"RESERVATION_HOLD",message_proven:false,device_ack:false};}
}
function scoreDigest(asof, source, policy, rows, version){
const num=x=>{
if(x==="")return '""';
requireIt(typeof x==="string"&&/^-?\d+(?:\.\d+)?$/.test(x),"SCORE_DECIMAL");
const f=Number(x);requireIt(Number.isFinite(f)&&Math.abs(f)<1e15&&(f===0||Math.abs(f)>=1e-4),"SCORE_NUMBER_RANGE");
return Object.is(f,-0)?"-0.0":Number.isInteger(f)?f.toFixed(1):String(f);
};
const quote=s=>{requireIt(typeof s==="string","SCORE_TEXT");return JSON.stringify(s);};
const data=rows.map(r=>{requireIt(Array.isArray(r)&&r.length===4,"SCORE_ROW");return "["+[quote(r[0]),num(r[1]),quote(r[2]),num(r[3])].join(",")+"]";});
return sha256('{"asof":'+quote(day(asof))+',"policy":'+quote(policy)+',"rows":['+data.join(",")+'],"source":'+quote(source)+',"version":'+quote(version)+'}');
}
return {operation,scoreDigest,sha256};
})();
const PENDING = 'EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST';
const TERMINAL = new Set(['STOP_TOUCHED','TARGET_TOUCHED','BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS','TIME_EXIT_AT_CLOSE']);
const STOP = new Set(['STOP_TOUCHED','BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS','GAP_BELOW_STOP',
'SMA20_CROSS_DOWN','SMA50_CROSS_DOWN','SUPPORT_20_BREAKDOWN','DAILY_DROP_2ATR','OFFICIAL_ISSUER_RISK','NEAR_STOP','NEAR_STOP_1ATR']);
const HOLD = (stage,post_calls=0) => ({state:'HOLD',stage,post_calls});
const REPO = 'gokaydonmez39-jpg/kripto-radar';
const WEB = 'https://github.com/'+REPO+'/actions/runs/';
const API = 'https://api.github.com/repos/'+REPO+'/actions/runs/';
const WORKFLOW = '.github/workflows/xray-personal-477-eod.yml';
const A_JOBS = ['offline-guard','private-sheets-auth-preflight','daily-private-scan','private-episode-followups','guardian-acceptance'];
const SCOPE = '3d1d226e2ef511570b2abd57e59c74d2c2156e6eed9baf4a08b8d3df82223060';
const ALGO = '0c137ecbdaf0eb68dbab3a642cfd501e4af61641b52367607fe616713af32523';
const unwrap = r => r?.isError===true ? null : (r?.structuredContent?.result ?? r?.structuredContent ?? r?.result ?? null);
const cell = (r,k) => r[k] ?? '';
const count = x => typeof x==='string' && /^(0|[1-9]\d*)$/.test(x) && Number.isSafeInteger(Number(x));
const oneday = d => typeof d==='string' && /^\d{4}-\d\d-\d\d$/.test(d) &&
Number.isFinite(Date.parse(d)) && new Date(d).toISOString().slice(0,10)===d;
const time = s => typeof s==='string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$/.test(s) ? Date.parse(s) : NaN;
const decimal = x => {
if(typeof x!=='string'|| !/^-?\d+(?:[.,]\d+)?$/.test(x)) return null;
const [head, tail=''] = x.replace(',','.').split('.');
const a=head.replace(/^(-?)0+(?=\d)/,'$1'), b=tail.replace(/0+$/,'');
return (a==='-0'&&!b?'0':a)+(b?'.'+b:'');
};
const number = x => decimal(x)!==null && Number.isFinite(Number(decimal(x))) ? Number(decimal(x)) : null;
const eqPrice = (a,b) => number(a)>0 && decimal(a)===decimal(b);
const numText = x => number(x)===null ? '—' : x;
const pct = x => number(x)===null ? '—' : x+'%';
const safe = x => String(x??'').replace(/[\r\n\t]/g,' ').replace(/[\\`*_[\]<>|]/g,'\\$&').trim().slice(0,180);
const validRows = (x,w) => Array.isArray(x)&&x.length>0&&x.every(r=>Array.isArray(r)&&r.length<=w&&r.every(c=>typeof c==='string'));
const norm = (x,w) => JSON.stringify(x.map(r=>Array.from({length:w},(_,z)=>cell(r,z))));
const stop = r => STOP.has(r[5]) || /STOP|RISK|RİSK|KRİTİK|KRITIK/i.test(r[6]??'');
function payload(raw,job) {
const content=unwrap(raw)?.content;
if(typeof content!=='string'||!job)return null;
const a=time(job.started_at), b=time(job.completed_at);
const lines=content.split(/\r?\n/).flatMap(l=>{
const parts=/^(\S+) (.*)$/.exec(l);
if(!parts||!(a<=time(parts[1])&&time(parts[1])<b+1000))return [];
return [parts[2].trim()];
});
return {lines, rows:lines.flatMap(l=>{
if(/^\*\*\*".*\*\*\*$/.test(l))l='{'+l.slice(3,-3)+'}';
try {const x=JSON.parse(l);return x&&typeof x==='object'&&!Array.isArray(x)?[x]:[];}catch{return [];}
})};
}
function googleRows(raw,name,last,w) {
const x=unwrap(raw);
return typeof x?.range==='string'&&new RegExp('^'+name+'!A1:'+last+'[1-9]\\d*$').test(x.range)&&
x.majorDimension==='ROWS'&&validRows(x.values,w)?x.values:null;
}
function locateA(i) {
const d=i?.expected_asof;
if(!oneday(d)||!validRows(i.scan,26)||!validRows(i.alerts,20)||!validRows(i.history,26))return HOLD('A_INPUT');
const head=['ASOF ET','ÜRETİM KANALI','İSTENEN','İŞLENEN','GEÇERLİ','EKSİK','FINAL READY','YENİ KAYIT','RUN KANITI','DURUM / VERİ SINIRI'];
if(JSON.stringify(i.scan[0])!==JSON.stringify(head))return HOLD('A_SCAN_SCHEMA');
const scans=i.scan.slice(1).filter(r=>r.some(Boolean));
if(!scans.every(r=>oneday(r[0]))||new Set(scans.map(r=>r[0])).size!==scans.length)return HOLD('A_SCAN_IDENTITY');
const latest=scans.map(r=>r[0]).sort().at(-1);
if(!latest||latest<d)return {state:'WAIT_CURRENT_EOD'};
if(latest!==d)return HOLD('A_FUTURE_SOURCE');
const current=i.alerts.slice(1).filter(r=>r[4]===d);
const pending=current.filter(r=>r[17]===PENDING);
if(!pending.length)return {state:'NO_CURRENT_A'};
if(new Set(current.map(r=>r[0])).size!==current.length)return HOLD('A_EVENT_DUPLICATE');
const r=scans.find(r=>r[0]===d), uri=r[8], n=Number(uri?.slice(WEB.length));
if(!Number.isSafeInteger(n)||n<=0||uri!==WEB+n||r[2]!=='477'||r[3]!=='477'||r[4]!=='477'||r[5]!=='0'||r[6]!=='TRUE'||!count(r[7])||
!r[9]?.startsWith('scopeSHA='+SCOPE+';algorithmSHA='+ALGO+';source_event=schedule;'))return HOLD('A_SCAN_PROVENANCE');
return {state:'A_NEEDS_SOURCE',runId:n,asof:d,newAL:+r[7],hasRisk:pending.some(stop)};
}
function proveA(i) {
const route=locateA(i);
if(route.state!=='A_NEEDS_SOURCE')return route;
const {asof,runId,newAL}=route, rurl=API+runId, jurl=rurl+'/attempts/1/jobs?per_page=100';
const js=(reply,url)=>{
const x=unwrap(reply);
if(x?.url!==url || (x.display_url!==undefined&&x.display_url!==url)||typeof x.content!=='string')return null;
try{return JSON.parse(x.content);}catch{return null;}
};
const r=js(i.runResponse,rurl), j=js(i.jobsResponse,jurl);
if(r?.id!==runId||r.url!==rurl||r.repository?.full_name!==REPO||r.path!==WORKFLOW||r.event!=='schedule'||
r.head_branch!=='main'||r.run_attempt!==1||r.status!=='completed'||!['success','failure'].includes(r.conclusion)||
!/^[a-f0-9]{40}$/.test(r.head_sha??'')||!(time(r.created_at)<=time(r.run_started_at)&&time(r.run_started_at)<=time(r.updated_at)))return HOLD('A_EOD_IDENTITY');
let jobs=j?.jobs;
if(!Array.isArray(jobs)||j.total_count!==6||jobs.length!==6||new Set(jobs.map(x=>x.id)).size!==6||
jobs.some(x=>!Number.isSafeInteger(x.id)||x.id<=0||x.run_id!==runId||x.run_url!==rurl||x.head_branch!=='main'||
x.run_attempt!==1||x.head_sha!==r.head_sha||x.status!=='completed'||
!(time(r.run_started_at)<=time(x.started_at)&&time(x.started_at)<=time(x.completed_at)&&time(x.completed_at)<=time(r.updated_at)))||
A_JOBS.some(name=>jobs.filter(x=>x.name===name&&x.conclusion==='success').length!==1)||
jobs.filter(x=>x.name==='daily-private-score-acceptance'&&
(r.conclusion==='success'?x.conclusion==='success':x.conclusion==='failure')).length!==1)return HOLD('A_EOD_JOBS');
const logs=A_JOBS.slice(2).map(n=>{
const j=jobs.find(x=>x.name===n);
return payload(i.logs?.[j.id],j);
});
if(logs.some(x=>!x))return HOLD('A_JOB_LOG');
const [scan,follow,guard]=logs;
const once=(a,p)=>a.filter(p).length===1;
const here=o=>o.asof_et===asof;
if(!once(scan.lines,l=>l==='XRAY_PERSONAL_GITHUB_HANDOFF=PASS_477_477_SOURCE_POLICY_SHA_BOUND_PRIVATE')||
!once(scan.rows,o=>here(o)&&o.no_execution===true&&o.final_ready===true&&o.universe===477&&o.processed===477&&o.valid===477&&
o.invalid_or_missing===0&&o.remaining===0&&o.new_entries===newAL&&o.scope_sha256===SCOPE&&o.analysis_fingerprint_sha256===ALGO)||
!once(scan.rows,o=>here(o)&&o.status==='PRIVATE_SHEET_READBACK_PASS'&&o.candidates===newAL))return HOLD('A_SCAN_RECEIPT');
if(!once(follow.rows,o=>here(o)&&o.status==='PANEL_READBACK_PASS'&&o.device_ack===false)||
!once(guard.rows,o=>o.last_verified_scan_asof===asof&&o.schema==='XRAY_PERSONAL_PRIVATE_EVIDENCE_AUDIT_V1'&&
o.status==='READ_ONLY_EVIDENCE_AUDIT'&&o.execution==='NONE'&&o.messages_sent===0&&o.sheet_writes===0))
return HOLD('A_GUARDIAN_OR_PANEL_RECEIPT');
const owner=new Map();
const headers=['ALARM KİMLİĞİ','ASOF ET','SEMBOL','SINIF','IEX KAPANIŞ USD','STOP 2ATR','HEDEF 2R','TAKİP DURUMU','KAPANIŞ SEANSI','SONUÇ'];
if(headers.some((x,k)=>i.history[0][k]!==x))return HOLD('A_HISTORY_SCHEMA');
for(const e of i.history.slice(1)){
if(!e.some(Boolean))continue;
if(!oneday(e[1])||e[1]>asof||e[0]!==e[1]+'|'+e[2]||owner.has(e[0])||!/^[A-Z0-9.]{1,16}$/.test(e[2]??''))return HOLD('A_HISTORY_IDENTITY');
owner.set(e[0],e);
}
const verified=[], held=[];
for(const row of i.alerts.slice(1).filter(x=>x[4]===asof&&x[17]===PENDING)){
const type=row[5], e=owner.get(row[1]);
const session=/^(0|[1-9]|1[0-5])\/15$/.exec(row[15]??'');
const ref=number(e?.[4]), lo=number(row[8]), hi=number(row[9]);
const common=e&&session&&row[0]===row[1]+'|'+asof+'|'+type+'|1'&&row[2]===e[1]&&row[3]===e[2]&&
ref>0&&lo>0&&hi>0&&lo<ref&&ref<hi&&number(row[7])>0&&eqPrice(row[8],e[5])&&eqPrice(row[9],e[6])&&
row[16]===WEB+runId&&cell(row,18)==='';
let pass=false;
if(common&&type==='AL_NEW_EPISODE'){
const overlaps=[...owner.values()].some(x=>x[2]===e[2]&&x[1]<asof&&(!cell(x,8)||x[8]>=asof));
pass=!overlaps&&row[2]===asof&&session[1]==='0'&&eqPrice(row[7],e[4])&&row[6]==='YENİ AL'&&e[7]==='AÇIK • 0/15 SEANS'&&
once(scan.rows,o=>here(o)&&o.status==='AL_OUTBOX_PENDING_READBACK_PASS'&&o.technical_al===newAL&&o.messages_sent===0&&o.device_ack===false&&
Number.isSafeInteger(o.new_pending)&&o.new_pending>=0&&Number.isSafeInteger(o.new_suppressed)&&o.new_suppressed>=0&&o.new_pending+o.new_suppressed<=newAL);
} else if(common&&TERMINAL.has(type)){
pass=e[8]===asof&&e[9]===type&&e[7]==='KAPALI • '+type+' • '+row[15]+' SEANS'&&
row[19]?.startsWith('Verified historical Alpaca IEX daily bar; theoretical contact only;')&&
once(follow.rows,o=>here(o)&&o.status==='LIFECYCLE_READBACK_PASS'&&o.notification_delivery==='NOT_ATTEMPTED_BY_GITHUB'&&o.device_ack===false&&
Number.isSafeInteger(o.terminal_updates)&&o.terminal_updates>=0);
}
if(pass)verified.push({row,e});else held.push({type,risk:stop(row)});
}
verified.sort((a,b)=>Number(stop(b.row))-Number(stop(a.row))||Number(b.row[5]==='TARGET_TOUCHED')-Number(a.row[5]==='TARGET_TOUCHED')||a.row[0].localeCompare(b.row[0]));
if(held.some(x=>x.risk))return HOLD('A_RISK_EVIDENCE_UNVERIFIED');
if(!verified.length)return HOLD('A_NO_VERIFIABLE_EVENT');
return {state:'A_SOURCE_VERIFIED',asof,runId,verified:verified.slice(0,6),held,hasRisk:verified.some(x=>stop(x.row))};
}
async function reserveA(i, io, P, markerCheck) {
try {
const proof=proveA(i);
if(proof.state!=='A_SOURCE_VERIFIED')return {...proof,post_calls:0};
if(i.dry_run!==true)return HOLD('A_DRY_ONLY');
if(i.slot_verified!==true || i.writer_verified!==true)return HOLD('A_NATURAL_OR_WRITER_UNVERIFIED');
const selected=proof.verified, keys=selected.map(x=>x.row[0]);
const plan={kind:'event',asof:proof.asof,baseline:i.alerts,sheet_id:i.alertSheetId,stamp:i.stamp,keys};
const result=P.operation({...plan,action:'plan'});
if(result.status!=='PLAN_ONLY'||result.requests.length!==keys.length*2)return HOLD('A_PLAN');
const marks=result.requests.filter(x=>x.addNamedRange).map(x=>x.addNamedRange.namedRange.name);
const query={spreadsheet_id:i.spreadsheetId,sheet_name:'UYARI_OLAYLARI',range:'A:T',value_render_option:'FORMATTED_VALUE'};
const all=await Promise.all([io.range(query),...marks.map(name=>Promise.resolve().then(()=>{
return io.cells({spreadsheet_id:i.spreadsheetId,ranges:[name],cell_fields:'formattedValue'});
}).catch(error=>({isError:true,marker_lookup_exception:String(error)})))]);
const observedBefore=googleRows(all[0],'UYARI_OLAYLARI','T',20);
if(!observedBefore||norm(observedBefore,20)!==norm(i.alerts,20))return HOLD('A_EVENT_BASELINE_DRIFT');
if(!marks.every((m,k)=>{const x=markerCheck(all[k+1],m);return x?.kind==='exact_not_found'&&x.name===m&&x.spreadsheetId===i.spreadsheetId;}))
return HOLD('A_MARKER_EXISTS_OR_UNCERTAIN');
if(!(await io.stillAuthorized()))return HOLD('A_PRERESERVATION_AUTHORITY_UNVERIFIED');
return {state:'A_READY_DRY',post_calls:0,asof:proof.asof,count:keys.length};
}catch{return HOLD('A_PREPOST_FAILED');}
}
async function runA(options, io, existing) {
let slot;
const sameRun=(a,b)=>!!a&&!!b&&a.id===b.id&&a.scheduled_for===b.scheduled_for&&a.started_at===b.started_at;
const sameSlot=(a,b)=>sameRun(a,b)&&a.prompt===b.prompt;
const getSlot=async()=>{
const raw=await io.task({jawbone_id:options.taskId});
const a=(unwrap(raw)??raw)?.automations?.filter(x=>x.id===options.taskId);
const stampRaw=await io.clock({});
const u=(unwrap(stampRaw)??stampRaw)?.current_time;
if(a?.length!==1||typeof u!=='string'||!/^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC$/.test(u))return null;
const iso=u.replace(' ','T').replace(' UTC','Z');
const row=a[0], s=existing.natural(row,iso,options.trigger);
if(!s||typeof row.prompt!=='string')return null;
if(options.boot&&(!sameRun(s,options.boot.slot)||row.prompt!==options.boot.prompt))return null;
return {...s,iso,prompt:row.prompt};
};
try {
if(options.mode!=='natural_task'||!oneday(options.expected_asof))return HOLD('A_NOT_NATURAL');
slot=await getSlot();
if(!slot)return HOLD('A_NATURAL_SLOT_UNVERIFIED');
const specs=[['TARAMA_KAYITLARI','Z',26],['ADAY_GECMISI','Z',26],['UYARI_OLAYLARI','T',20]];
const raw=await io.cells({
spreadsheet_id:options.spreadsheetId,ranges:specs.map(([name,last])=>name+'!A:'+last),cell_fields:'formattedValue'
});
const x=unwrap(raw);
if(x?.spreadsheetId!==options.spreadsheetId||!Array.isArray(x.sheets)||x.sheets.length!==specs.length)
return HOLD('A_SNAPSHOT_UNVERIFIED');
const snap=specs.map(([name,_,width])=>{
const found=x.sheets.filter(s=>s.properties?.title===name);
const s=found[0], d=s?.data?.[0], g=s?.properties?.gridProperties;
if(found.length!==1||!Number.isSafeInteger(s.properties.sheetId)||g?.columnCount!==width||
!Number.isSafeInteger(g?.rowCount)||s.data?.length!==1||(d.startRow??0)!==0||(d.startColumn??0)!==0||
!Array.isArray(d?.rowData)||d.rowData.length>g.rowCount)return null;
const rows=d.rowData.map(r=>{
const row=(r.values??[]).map(c=>c.formattedValue??'');
while(row.length&&row.at(-1)==='')row.pop();
return row;
});
return validRows(rows,width)?{rows,id:s.properties.sheetId}:null;
});
if(snap.some(s=>!s))return HOLD('A_SNAPSHOT_SCHEMA');
const [s,h,a]=snap;
const input={expected_asof:options.expected_asof,spreadsheetId:options.spreadsheetId,
scan:s.rows,history:h.rows,alerts:a.rows,alertSheetId:a.id};
const route=locateA(input);
if(route.state!=='A_NEEDS_SOURCE')return {...route,post_calls:0};
if(options.riskOnly===true&&!route.hasRisk)return {state:'A_NO_RISK_PENDING',post_calls:0};
const root=API+route.runId;
const [runResponse,jobsResponse]=await Promise.all([
io.github({url:root}),io.github({url:root+'/attempts/1/jobs?per_page=100'})
]);
let j;
try{j=JSON.parse(unwrap(jobsResponse)?.content??'');}catch{return HOLD('A_JOB_DISCOVERY');}
if(!Array.isArray(j.jobs))return HOLD('A_JOB_DISCOVERY');
const jobs=A_JOBS.slice(2).map(name=>j.jobs.filter(y=>y.name===name));
if(jobs.some(a=>a.length!==1||!Number.isSafeInteger(a[0].id)||a[0].id<=0))return HOLD('A_JOB_DISCOVERY');
const ids=jobs.map(a=>a[0].id);
const lp=Promise.all(ids.map(job_id=>io.logs({repo_full_name:REPO,job_id})));
const libraries=existing.loadPlanner(io);
const [results, lib]=await Promise.all([lp,libraries]);
if(!lib?.planner||typeof lib.markerCheck!=='function')return HOLD('A_PINNED_RUNTIME');
const next=await getSlot();
if(!sameSlot(next,slot))return HOLD('A_NATURAL_SLOT_CHANGED');
const stamp=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Istanbul',year:'numeric',month:'2-digit',day:'2-digit',
hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(next.iso))+' TRT';
return await reserveA({...input,runResponse,jobsResponse,logs:Object.fromEntries(ids.map((id,k)=>[id,results[k]])),
stamp,slot_verified:true,writer_verified:true,dry_run:options.dryRun===true}, {
range:io.range,cells:io.cells,
stillAuthorized:async()=> {
const [s,w]=await Promise.all([getSlot(),existing.writer(io)]);
return sameSlot(s,slot)&&w===null;
}
},lib.planner,lib.markerCheck);
} catch {return HOLD('A_RUNTIME_OR_SOURCE_UNVERIFIED');}
}
return {N,P,runA,planner:XRAY_RESERVATION,classifyMarker};
}