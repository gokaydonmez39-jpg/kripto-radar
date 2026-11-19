function xrayStaticRuntime(binding,livePrompt){
function assertCurrentPrompt(p){if(p!==livePrompt)throw Error('LIVE_PROMPT_DRIFT');}
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
async function executeRecordedAB(expected_asof,T,inventory,initialRaw){
const id=binding.id;
const allowed=new Set((inventory??[]).map(x=>typeof x==="string"?x:x?.name));
const tool=["mcp__codex_apps__automations_peek","mcp__Automations__peek"].find(k=>typeof T?.[k]==="function"&&(allowed.size===0||allowed.has(k)));
if(!tool)return {state:"HOLD",stage:"AB_TASK_PEEK_UNAVAILABLE",post_calls:0};
let raw;
try { raw=initialRaw??await T[tool]({jawbone_id:id}); }
catch { return {state:"HOLD",stage:"AB_TASK_PEEK_FAILED",post_calls:0}; }
if(raw?.isError===true)return {state:"HOLD",stage:"AB_TASK_PEEK_FAILED",post_calls:0};
let x=raw;
for(let n=0;n<6&&x&&x.isError!==true&&!Array.isArray(x.automations);n++)x=x.structuredContent??x.result??null;
const a=x?.isError===true||!Array.isArray(x?.automations)?null:x.automations.filter(y=>y?.id===id);
if(a?.length!==1||typeof a[0].prompt!=="string")return {state:"HOLD",stage:"AB_TASK_RECORD_UNVERIFIED",post_calls:0};
assertCurrentPrompt(a[0].prompt);
const v=[XRAY_A_IMPL,XRAY_AB_STAGED];
return await v[1].run(expected_asof,T,inventory,v[0],"01617e17545aa47e6d92988c9884ce56387d26437bf2f72683edc5bcd6f3705b",a[0]);
}
const XRAY_B_NATURAL=(()=>{
const id=binding.id;
const fail=stage=>({state:"HOLD",stage,post_calls:0});
const capability={
task:["automations","peek"], clock:["clock","curr_time"], range:["google_drive","get_spreadsheet_range"],
meta:["google_drive","get_spreadsheet_metadata"], cells:["google_drive","get_spreadsheet_cells"],
github:["github","fetch"], logs:["github","fetch_workflow_job_logs"], post:["google_drive","batch_update_spreadsheet"]
};
function bind(T,inventory){
const registered=new Set((Array.isArray(inventory)?inventory:[]).flatMap(x=>typeof x==="string"?[x]:typeof x?.name==="string"?[x.name]:[]));
return Object.fromEntries(Object.entries(capability).map(([role,[ns,k]])=>{
const canonical=ns==="clock"?ns+"__"+k:"mcp__codex_apps__"+ns+"_"+k;
const provider={automations:"Automations",google_drive:"Google_Drive",github:"GitHub"}[ns];
const official=provider?"mcp__"+provider+"__"+k:null;
const alternatives=[canonical,official,"mcp__"+ns+"__"+k,ns+"__"+k,ns+"_"+k].filter(Boolean);
const match=alternatives.filter((n,j)=>alternatives.indexOf(n)===j&&
(registered.size===0||registered.has(n))&&typeof T?.[n]==="function");
const name=match.includes(canonical)?canonical:match.includes(official)?official:match.length===1?match[0]:null;
return [role,name?(x=>T[name](x)):null];
}));
}
const TIMEZONE="Europe/Istanbul";
const REPO="gokaydonmez39-jpg/kripto-radar",ROOT="https://api.github.com/repos/"+REPO+"/actions/runs";
const SHEET=binding.sheet;
const WRITER=".github/workflows/xray-personal-477-eod.yml";
const ACTIVE=["in_progress","queued","pending","waiting","requested"];
const rateLimited=r=>r?.isError===true&&(r.structuredContent?.result??r.structuredContent)?.error_code==="RATE_LIMITED";
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
function stopQueue(response,asof){
const x=unpack(response);
if(typeof x?.range!=="string"||!/^UYARI_OLAYLARI!A1:T[1-9]\d*$/.test(x.range)||
x.majorDimension!=="ROWS"||!Array.isArray(x.values))return "B_STOP_QUEUE_GET_UNVERIFIED";
const h=x.values[0], fields=["OLAY_ANAHTARI","OLAY_ASOF_ET","OLAY_KODU","ONCELIK","BILDIRIM_DURUMU"];
if(!Array.isArray(h)||fields.some(n=>h.indexOf(n)<0||h.indexOf(n)!==h.lastIndexOf(n)))return "B_STOP_QUEUE_SCHEMA";
const [k,d,c,p,z]=fields.map(n=>h.indexOf(n)), seen=new Set();
for(const row of x.values.slice(1)){
if(row[d]!==asof)continue;
if(typeof row[k]!=="string"||!row[k]||seen.has(row[k])||typeof row[c]!=="string"||typeof row[p]!=="string"||typeof row[z]!=="string")return "B_STOP_QUEUE_IDENTITY";
seen.add(row[k]);
if(row[z]==="EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST"&&
(/(?:^|_)(?:STOP|RISK)(?:_|$)/i.test(row[c])||/STOP|RISK|RİSK|KRITIK|KRİTİK/i.test(row[p])||
["SMA20_CROSS_DOWN","SMA50_CROSS_DOWN","SUPPORT_20_BREAKDOWN","DAILY_DROP_2ATR"].includes(row[c])))return "B_STOP_PRIORITY_PENDING";
}
return null;
}
function getOnlyRetry(K,waitFn){
let waiting=null;const exhausted=new Set();
const call=(name,f)=>typeof f!=="function"?null:async x=>{
const key=name+(x.sheet_name?":"+x.sheet_name:"");
const original=await f(x);
if(!rateLimited(original))return original;
if(!waiting&&typeof waitFn==="function")waiting=Promise.resolve().then(()=>waitFn(12000));
if(!waiting){exhausted.add(key);return original;}
await waiting;
const retried=await f(x);
if(rateLimited(retried))exhausted.add(key);
return retried;
};
return {range:call("range",K.range),cells:call("cells",K.cells),meta:call("meta",K.meta),exhausted};
}
async function run(i,T,inventory,waitFn,taskPeek,activeAdapters,initialTask){
let phase="B_TASK_CONTRACT_GET",writes=0;
try{
const K=bind(T,inventory);
for (const role of ["range","meta","cells","github","logs","post"]) {
if (!K[role] && typeof activeAdapters?.[role] === "function") K[role]=activeAdapters[role];
}
if(!K.task && typeof taskPeek==='function') K.task=taskPeek;
for(const role of ["task","range","cells","github","post"])if(!K[role])return fail("B_RUNTIME_TOOL_MISSING_"+role.toUpperCase());
const readTask=async()=>{
let x=await K.task({jawbone_id:id});
for(let n=0;n<6&&x&&x.isError!==true&&!Array.isArray(x.automations);n++)x=x.structuredContent??x.result??null;
if(!x||x.isError===true||!Array.isArray(x.automations))return null;
const a=x.automations.filter(y=>y?.id===id);
return a.length===1&&a[0].is_enabled===true&&a[0].default_timezone===TIMEZONE&&typeof a[0].prompt==="string"?a[0]:null;
};
const a=initialTask===undefined?await readTask():initialTask;
if(a?.id!==id||a?.is_enabled!==true||a?.default_timezone!==TIMEZONE||typeof a.prompt!=="string")return fail(phase);
const prompt=a.prompt;
assertCurrentPrompt(prompt);
phase="B_DRIVER_COMPILE";
const B=XRAY_B_DRIVER;
const now=async()=>{
if(!K.clock)return new Date().toISOString();
const raw=await K.clock({}), u=raw?.current_time;
if(typeof u!=="string"||!/^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC$/.test(u))throw Error("CLOCK");
return u.replace(" ","T").replace(" UTC","Z");
};
const stamp=u=>new Intl.DateTimeFormat("sv-SE",{timeZone:"Europe/Istanbul",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"})
.format(new Date(u))+" TRT";
const wait=typeof waitFn==="function"?waitFn:typeof setTimeout==="function"?(ms=>new Promise(r=>setTimeout(r,ms))):null;
const safe=getOnlyRetry(K,wait);
const io={
range:safe.range,
meta:safe.meta,
cells:safe.cells,
github:K.github,
logs:K.logs,
post:x=>{if(writes)throw Error("NO_SECOND_POST");writes=1;return K.post(x);}
};
phase="B_NATURAL_SLOT";
const slot=naturalB(a,await now(),i.trigger);
if(!slot)return fail(a.run_details?.last_run?.recorded_status==="in_progress"?"B_NATURAL_TRIGGER_IDENTITY_UNVERIFIED":"B_CURRENT_NATURAL_SLOT_UNVERIFIED");
phase="B_READ_CLOCK";
const v=await B.read({expected_asof:i.expected_asof,prompt,stamp:stamp(await now()),exact_closes:i.exact_closes,
canaryStopPriority:i.preferDryCanaryOnStop===true?stopQueue:undefined},io);
if(v.state!=="B_READ_VERIFIED")return safe.exhausted.size?fail("B_SHEETS_INITIAL_GET_RATE_LIMIT"):v;
for(const role of ["cells","post"])if(!K[role])return {...fail("B_RUNTIME_TOOL_MISSING_"+role.toUpperCase()),proof:v.proof};
phase="B_RUNTIME_GATES";
const alerts=v.alerts;
const stopStage=rateLimited(alerts)?"B_STOP_QUEUE_GET_RATE_LIMIT":stopQueue(alerts,v.proof.asof);
const stage=stopStage??await writer(K);
if(stage)return {...fail(stage),proof:v.proof,natural_run_id:slot.id};
phase="B_PREPOST_CLOCK";
io.prePostAuth=async()=>{
const [current,t]=await Promise.all([readTask(),now()]);
const fresh=naturalB(current,t,i.trigger);
return current?.prompt===prompt&&fresh?.id===slot.id&&
fresh?.scheduled_for===slot.scheduled_for&&fresh?.started_at===slot.started_at;
};
const finished=await B.finish(v,{prompt,stamp:stamp(await now()),scheduled_slot_verified:true,single_writer_verified:true,stop_priority_checked:true},io);
const quota=safe.exhausted.size&&finished.state!=="EMIT_NOW"&&["MARKER_EXISTING_OR_UNCERTAIN","PREPOST_GET_UNVERIFIED","READBACK_UNCERTAIN_DO_NOT_RESEND"].includes(finished.stage);
return {...finished,...(quota?{stage:writes?"B_SHEETS_POST_READ_RATE_LIMIT_DO_NOT_RESEND":"B_SHEETS_PREPOST_READ_RATE_LIMIT"}:{}),proof:v.proof,natural_run_id:slot.id};
}catch(_){return writes?{state:"HOLD",stage:"AFTER_POST_UNCERTAIN_DO_NOT_RESEND",post_calls:1}:fail(phase);}
}
async function observedRun(...args){
const result=await run(...args);
if(result.state==="HOLD" && typeof result.stage==="string"){
return {...result, diagnostic: ["XRAY_B_TRACE_V1","CALLED",result.stage,"POST="+result.post_calls].join(" | ")};
}
return result;
}
return {run:observedRun,natural,naturalB,writer,stopQueue,getOnlyRetry};
})();
const XRAY_B_DRIVER=(()=>{
const SID=binding.sheet, REPO="gokaydonmez39-jpg/kripto-radar";
const rev="c3aa60722cf848e83477525eceae209498c3e1e1", sha="1586498cd9c390b5eb3935261f90545d3e3b06f6";
const pinned="https://github.com/"+REPO+"/blob/"+rev+"/personal-swing/delivery_reservation_portable.js";
const blob="https://api.github.com/repos/"+REPO+"/git/blobs/"+sha;
const fail=(stage)=>({state:"HOLD",stage,post_calls:0});
const un=r=>r?.isError===true?null:(r?.structuredContent?.result??r?.structuredContent??r?.result??null);
const sheet=(r,tab,last)=>{const s=un(r);return typeof s?.range==="string"&&s.range.startsWith(tab+"!A1:"+last)&&/^[1-9]\d*$/.test(s.range.slice((tab+"!A1:"+last).length))&&s.majorDimension==="ROWS"&&Array.isArray(s.values)?s.values:null;};
const range=(sheet_name,range)=>({spreadsheet_id:SID,sheet_name,range,value_render_option:"FORMATTED_VALUE"});
const get=(io,url)=>io.github({url});
const names=["daily-private-scan","private-episode-followups","guardian-acceptance","daily-private-score-acceptance"];
function loadCode(prompt){
assertCurrentPrompt(prompt);
return [XRAY_B,XRAY_B_CHATGPT,XRAY_EXACT_EOD,XRAY_B_SOURCE,XRAY_B_ONCE,XRAY_B_LIFECYCLE];
}
function readBundle(raw){
const root=un(raw);
const specs=[["TARAMA_KAYITLARI","Z",26],["SWING_SKOR_GUNLUK","AI",35],["ADAY_GECMISI","Z",26],["UYARI_OLAYLARI","T",20]];
if(root?.spreadsheetId!==SID||!Array.isArray(root.sheets)||root.sheets.length!==specs.length)return null;
const out={};
for(const [name,end,width] of specs){
const found=root.sheets.filter(s=>s?.properties?.title===name);
if(found.length!==1)return null;
const s=found[0],g=s.properties?.gridProperties,d=s.data?.[0];
if(!Number.isInteger(s.properties?.sheetId)||!Number.isSafeInteger(g?.rowCount)||g.rowCount<1||g?.columnCount!==width||
s.data?.length!==1||(d?.startRow??0)!==0||(d?.startColumn??0)!==0||
!Array.isArray(d?.rowData)||d.rowData.length<1||d.rowData.length>g.rowCount)return null;
const rows=[];
for(const r of d.rowData){
const cells=r?.values??[];
if(!Array.isArray(cells)||cells.length>width)return null;
const row=cells.map(c=>c?.formattedValue??"");
if(row.some(x=>typeof x!=="string"))return null;
while(row.length&&row[row.length-1]==="")row.pop();
rows.push(row);
}
out[name]={result:{range:name+"!A1:"+end+g.rowCount,majorDimension:"ROWS",values:rows}};
}
return out;
}
async function read(i,io){
let stage="B_INPUT_ASOF";
try{
if(!/^\d{4}-\d\d-\d\d$/.test(i?.expected_asof??"")||typeof i.prompt!=="string")return fail(stage);
stage="B_INITIAL_READ";
const bundleRaw=await 
io.cells({spreadsheet_id:SID,ranges:[
"TARAMA_KAYITLARI!A:Z","SWING_SKOR_GUNLUK!A:AI",
"ADAY_GECMISI!A:Z","UYARI_OLAYLARI!A:T"],cell_fields:"formattedValue,note"});
const bundle=readBundle(bundleRaw);
if(!bundle)return fail("B_INITIAL_SNAPSHOT_UNVERIFIED");
const scanRaw=bundle.TARAMA_KAYITLARI,scoreRaw=bundle.SWING_SKOR_GUNLUK;
const history_response=bundle.ADAY_GECMISI,alerts=bundle.UYARI_OLAYLARI,metaRaw=bundleRaw;
const scan=sheet(scanRaw,"TARAMA_KAYITLARI","Z"),baseline=sheet(scoreRaw,"SWING_SKOR_GUNLUK","AI");
if(!scan||!baseline)return fail("B_SCAN_OR_SUMMARY_GET");
if ((function preflightCurrent(scan, expected) {
const header=['ASOF ET','ÜRETİM KANALI','İSTENEN','İŞLENEN','GEÇERLİ','EKSİK','FINAL READY','YENİ KAYIT','RUN KANITI','DURUM / VERİ SINIRI'];
if(!Array.isArray(scan)||JSON.stringify(scan[0])!==JSON.stringify(header)||!/^\d{4}-\d\d-\d\d$/.test(expected))return false;
const rows=scan.slice(1).filter(r=>r.some(x=>x!==''));
return rows.every(r=>/^\d{4}-\d\d-\d\d$/.test(r[0])&&r[0]<expected);
})(scan,i.expected_asof))return {state:"WAIT_CURRENT_EOD",post_calls:0};
stage="B_PINNED_RUNTIME";
const k=loadCode(i.prompt);if(!k)return fail(stage);
const [G,C,E,S,O,L]=k, route=G.route({expected_asof:i.expected_asof,scan,baseline});
if(route.state!=="CHECK_B")return {...route,post_calls:0};
if(i.canaryStopPriority?.(alerts,i.expected_asof)==="B_STOP_PRIORITY_PENDING")return fail("B_STOP_PRIORITY_PENDING");
stage="B_EXACT_EOD_GET";
const urls=E.urls(route.run_id),[runReply,jobsReply]=await Promise.all(urls.map(url=>get(io,url)));
const exact=E.read(runReply,jobsReply,route.run_id);
if(exact.state!=="EXACT_EOD_INPUT")return fail(exact.stage??stage);
stage="B_SUMMARY_PLAN";
const m=un(metaRaw);
const tabs=m?.spreadsheetId===SID&&m.sheets?.filter(x=>x.properties?.title==="SWING_SKOR_GUNLUK");
if(!Array.isArray(tabs)||tabs.length!==1||!Number.isInteger(tabs[0].properties.sheetId))return fail("B_SHEET_ID_UNVERIFIED");
const x={expected_asof:i.expected_asof,stamp:i.stamp,exact,scan,baseline,run:exact.run,jobs:exact.jobs,
sheet_id:tabs[0].properties.sheetId,history_response,...(i.exact_closes?{exact_closes:i.exact_closes}:{})};
const plan=G.prepare(x);if(plan.state!=="PLAN_ONLY")return {...plan,post_calls:0};
stage="B_SOURCE_NOTE_GET";
const sourceJobs=names.map(n=>exact.jobs.find(j=>j.name===n));
const clip=plan.requests?.[0]?.addNamedRange?.namedRange?.range;
if(!Number.isSafeInteger(route.row)||route.row<1||clip?.sheetId!==tabs[0].properties.sheetId||
clip.startRowIndex!==route.row||clip.endRowIndex!==route.row+1||
clip.startColumnIndex!==27||clip.endColumnIndex!==29)return fail("B_SOURCE_NOTE_COORDINATE");
const cell=tabs[0].data[0].rowData[route.row]?.values?.[26];
const prefix="XRAY_477_B_SOURCE_ENVELOPE_V1 ";
if(cell?.formattedValue!==route.url||typeof cell.note!=="string"||!cell.note.startsWith(prefix)||
cell.note.length>2700||/[\r\n]/.test(cell.note))return fail("B_SOURCE_NOTE_UNAVAILABLE");
const payload=JSON.parse(cell.note.slice(prefix.length));
if(payload?.schema!=="XRAY_477_B_SOURCE_ENVELOPE_V1"||payload.asof!==plan.asof||payload.run!==plan.run_id||
payload.head!==exact.run.head_sha||!Array.isArray(payload.proof)||payload.proof.length!==4)return fail("B_SOURCE_ENVELOPE_IDENTITY");
if(!payload.proof.every((p,j)=>p?.jobName===names[j]&&p.jobId===sourceJobs[j].id&&Array.isArray(p.lines)&&
p.lines.length===(j===0?2:1)&&p.lines.every(l=>Array.isArray(l)&&l.length===2&&typeof l[0]==="string"&&typeof l[1]==="string"&&l[1].length<700&&!/[\r\n]/.test(l[1]))))return fail("B_SOURCE_ENVELOPE_FORMAT");
x.rawByJobId=Object.fromEntries(payload.proof.map(p=>[p.jobId,{structuredContent:{content:p.lines.map(([time,line])=>time+" "+line).join("\n")}}]));
const source=S.check(exact,plan,scan,baseline,x.rawByJobId);
if(source.state!=="SOURCE_RECEIPTS_VERIFIED")return fail(source.stage??stage);
stage="B_LIFECYCLE_GET";
const history=sheet(history_response,"ADAY_GECMISI","Z");if(!history)return fail(stage);
const life=L.check(plan,baseline,history);if(life.state!=="LIFECYCLE_VERIFIED")return fail(life.stage??stage);
if(C.body(G,x).state!=="BODY_READY")return fail("B_CARD_BODY_UNVERIFIED");
return {state:"B_READ_VERIFIED",post_calls:0,proof:{asof:plan.asof,run_id:plan.run_id,episodes:life.count},x,alerts};
}catch(_){return fail(stage);}
}
async function finish(v,i,io){
if(v?.state!=="B_READ_VERIFIED")return fail("B_READ_PHASE_UNVERIFIED");
if(i?.scheduled_slot_verified!==true)return fail("B_CURRENT_NATURAL_SLOT_UNVERIFIED");
if(i?.single_writer_verified!==true)return fail("B_SINGLE_WRITER_UNVERIFIED");
if(i?.stop_priority_checked!==true)return fail("B_STOP_PRIORITY_NOT_RESOLVED");
let k;try{k=loadCode(i.prompt);}catch(_){return fail("B_PINNED_RUNTIME");}
if(!k)return fail("B_PINNED_RUNTIME");
const [G,C,E,S,O]=k;
if(!/^\d{4}-\d\d-\d\d [0-2]\d:[0-5]\d TRT$/.test(i.stamp??""))return fail("B_REAL_TSI_STAMP_UNVERIFIED");
return O.execute({...v.x,stamp:i.stamp,scheduled_slot_verified:true,single_writer_verified:true},
{cells:io.cells,range:io.range,post:io.post,prePostAuth:io.prePostAuth},G,C,S);
}
return {read,finish};
})();
/* XRAY 477: deterministic B-card gate. Pure calculation. No I/O or delivery. */
const XRAY_B = (P => {
"use strict";
const PATH=".github/workflows/xray-personal-477-eod.yml";
const REPO="gokaydonmez39-jpg/kripto-radar";
const SHEET=binding.sheet;
const READY="READY_FOR_CHATGPT_DAILY_DIGEST", REQUESTED="REQUESTED_NOT_DEVICE_ACK";
const REQUIRED=["offline-guard","private-sheets-auth-preflight","daily-private-scan",
"private-episode-followups","guardian-acceptance","daily-private-score-acceptance"];
const fail=(x,c)=>{if(!x)throw Error(c);};
const sha=x=>typeof x==="string"&&/^[0-9a-f]{64}$/.test(x);
const id=x=>Number.isSafeInteger(x)&&x>0;
const cell=(r,i)=>r[i]??"";
const natural=x=>/^(0|[1-9][0-9]*)$/.test(x)&&Number.isSafeInteger(Number(x));
const normalized=x=>typeof x==="string"&&/^-?\d+,\d+$/.test(x)?x.replace(",","."):x;
const decimal=x=>typeof normalized(x)==="string"&&/^-?\d+(?:\.\d+)?$/.test(normalized(x))&&Number.isFinite(Number(normalized(x)));
const failState=(e)=>({state:"HOLD",stage:/^[A-Z0-9_]+$/.test(e.message)?e.message:"INPUT_INVALID"});
const norm=(matrix)=>matrix.map(row=>Array.from({length:35},(_,i)=>cell(row,i)));
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
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
function route(i){
try{
fail(typeof i.expected_asof==="string"&&/^\d{4}-\d{2}-\d{2}$/.test(i.expected_asof),
"SOURCE_SESSION");
const scan=i.scan, matrix=i.baseline;
fail(Array.isArray(scan)&&Array.isArray(matrix)&&matrix.length>0,"SOURCE_MATRIX");
const names=["ASOF ET","İSTENEN","İŞLENEN","GEÇERLİ","EKSİK","FINAL READY","YENİ KAYIT","RUN KANITI"];
const cols=names.map(n=>scan[0]?.indexOf(n)??-1);
fail(cols.every((c,j)=>c>=0&&scan[0].lastIndexOf(names[j])===c),"SCAN_SCHEMA");
const nonempty=scan.slice(1).filter(r=>r.some(x=>x!==""));
fail(nonempty.every(r=>/^\d{4}-\d{2}-\d{2}$/.test(r[cols[0]])),"SCAN_SCHEMA");
const latest=nonempty.reduce((m,r)=>r[cols[0]]>m?r[cols[0]]:m,"");
if(latest<i.expected_asof)return {state:"WAIT_CURRENT_EOD"};
fail(latest===i.expected_asof,"SOURCE_FUTURE_ASOF");
const target=nonempty.filter(r=>r[cols[0]]===latest);
fail(target.length===1,"SOURCE_SCAN_IDENTITY");
fail(matrix[0][0]==="KAYIT_KIMLIGI"&&matrix[0][1]==="ASOF_ET"&&matrix[0][4]==="KAYIT_TIPI"&&
matrix[0][27]==="BILDIRIM_DURUMU"&&matrix[0][28]==="BILDIRIM_ZAMANI_TR","SUMMARY_SCHEMA");
const key=latest+"|SUMMARY", indices=[];
for(let n=1;n<matrix.length;n++)if(matrix[n][0]===key||
(matrix[n][1]===latest&&matrix[n][4]==="SUMMARY"))indices.push(n);
if(!indices.length)return {state:"WAIT_CURRENT_SUMMARY"};
fail(indices.length===1,"SUMMARY_IDENTITY");
const row=indices[0], summary=matrix[row];
fail(summary[0]===key&&summary[1]===latest&&summary[4]==="SUMMARY","SUMMARY_IDENTITY");
if(summary[27]===REQUESTED)return {state:"STOP_EXISTING_RESERVATION"};
fail(summary[27]===READY&&cell(summary,28)==="","SUMMARY_NOT_READY");
fail([1,2,3].every(j=>target[0][cols[j]]==="477")&&target[0][cols[4]]==="0"&&
target[0][cols[5]]==="TRUE"&&natural(target[0][cols[6]]),"SCAN_NOT_READY");
const url=target[0][cols[7]], match=typeof url==="string"&&
/^https:\/\/github\.com\/gokaydonmez39-jpg\/kripto-radar\/actions\/runs\/([1-9][0-9]*)(?:\/jobs\/[1-9][0-9]*)?$/.exec(url);
fail(match&&id(Number(match[1])),"EOD_RUN_URL");
return {state:"CHECK_B",asof:latest,key,row,run_id:Number(match[1]),url};
}catch(e){return failState(e);}
}
function prepare(i){
try{
const r=route(i);
if(r.state!=="CHECK_B")return r;
const run=i.run;
fail(run&&run.id===r.run_id&&run.path===PATH&&run.repository?.full_name===REPO&&
run.head_branch==="main"&&run.event==="schedule"&&run.run_attempt===1&&
run.conclusion==="success"&&run.status==="completed"&&/^[0-9a-f]{40}$/.test(run.head_sha),"EOD_IDENTITY");
fail(Array.isArray(i.jobs)&&i.jobs.length===6&&new Set(i.jobs.map(j=>j.id)).size===6&&
REQUIRED.every(n=>i.jobs.filter(j=>j.name===n&&id(j.id)&&j.run_id===r.run_id&&
j.head_sha===run.head_sha&&j.run_attempt===1&&j.conclusion==="success").length===1),"EOD_JOBS");
const s=i.baseline[r.row], epoch=i.baseline.filter(a=>a[1]===r.asof&&a[4]==="EPISODE");
for(const a of [s,...epoch])
fail(a[26]===r.url&&[29,30,31].every(n=>sha(a[n])&&a[n]===s[n])&&
typeof a[32]==="string"&&a[32]!==""&&a[32]===s[32],"SCORE_EPOCH");
const scored=epoch.filter(a=>cell(a,6)!==""), held=epoch.length-scored.length;
fail([5,6,7,8].every(n=>natural(s[n]))&&Number(s[5])===epoch.length&&Number(s[6])===scored.length&&
Number(s[7])===held&&Number(s[8])===new Set(epoch.map(a=>a[3])).size,"SCORE_COUNTS");
fail(new Set(epoch.map(a=>a[2])).size===epoch.length&&epoch.every(a=>
/^[A-Z0-9.]{1,16}$/.test(a[3])&&typeof a[2]==="string"&&
/^\d{4}-\d{2}-\d{2}\|/.test(a[2])&&a[2].slice(0,10)<=r.asof&&
a[2].slice(11)===a[3]&&a[0]===r.asof+"|"+a[2]&&
natural(a[21])&&Number(a[21])<=15),"EPISODE_IDENTITY");
fail(scored.every(a=>{
const parts=a.slice(7,14);
const limits=[20,15,15,15,10,15,10];
return decimal(a[6])&&Number(normalized(a[6]))>=0&&Number(normalized(a[6]))<=100&&
parts.length===7&&parts.every((v,j)=>decimal(v)&&Number(normalized(v))>=0&&
Number(normalized(v))<=limits[j])&&
Math.abs(parts.reduce((n,v)=>n+Number(normalized(v)),0)-Number(normalized(a[6])))<=0.350000001;
}),"SCORE_COMPONENTS");
fail(epoch.every(a=>[15,16,17].every(n=>decimal(a[n])&&Number(normalized(a[n]))>0)&&
Number(normalized(a[16]))<Number(normalized(a[15]))&&
Number(normalized(a[15]))<Number(normalized(a[17]))),"EPISODE_LEVELS");
const rank=row=>cell(row,6)===""?Infinity:Number(row[5]);
const ordered=epoch.slice().sort((a,b)=>rank(a)-rank(b)||(a[2]<b[2]?-1:a[2]>b[2]?1:0));
fail(ordered.slice(0,scored.length).every((a,k)=>a[5]===String(k+1)),"SCORE_RANK");
let digest;
try{
const closeOf=a=>i.exact_closes===undefined?normalized(cell(a,14)):
(cell(a,14)===""?"":i.exact_closes[a[2]]);
if(i.exact_closes!==undefined){
const needs=ordered.filter(a=>cell(a,14)!=="");
fail(i.exact_closes&&typeof i.exact_closes==="object"&&!Array.isArray(i.exact_closes)&&
Object.keys(i.exact_closes).length===needs.length&&needs.every(a=>
Object.hasOwn(i.exact_closes,a[2])&&typeof closeOf(a)==="string"&&
decimal(closeOf(a))&&Number(closeOf(a))>0&&
Math.abs(Number(closeOf(a))-Number(normalized(a[14])))<=0.00050000001),
"EXACT_CLOSE_BINDING");
}
digest=P.scoreDigest(r.asof,s[30],s[31],ordered.map(a=>
[a[2],normalized(cell(a,6)),cell(a,25),closeOf(a)]),s[32]);
}
catch(_){throw Error("SCORE_DECIMAL");}
fail(digest===s[29],"SCORE_SHA");
const input={kind:"digest",sheet_id:i.sheet_id,asof:r.asof,stamp:i.stamp,
baseline:i.baseline,verified_sha:digest};
const p=P.operation({...input,action:"plan"});
fail(p.status==="PLAN_ONLY"&&p.requests?.length===2,"PLAN");
const expected=p.requests[0].addNamedRange.namedRange;
fail(expected.range.sheetId===i.sheet_id&&expected.range.startRowIndex===r.row&&
expected.range.endRowIndex===r.row+1&&expected.range.startColumnIndex===27&&
expected.range.endColumnIndex===29,"PLAN_RANGE");
return {state:"PLAN_ONLY",run_id:r.run_id,key:r.key,asof:r.asof,score:digest,stamp:i.stamp,
marker:expected.name,requests:p.requests};
}catch(e){return failState(e);}
}
function beforePost(i){
try{
const p=prepare(i);
if(p.state!=="PLAN_ONLY")return p;
fail(i.scheduled_slot_verified===true&&i.source_receipts_verified===true&&
i.lifecycle_verified===true&&i.single_writer_verified===true&&
i.result_prepared===true,"PREPOST_EXTERNAL_GATES");
const m=classifyMarker(i.marker_response,p.marker);
fail(m?.kind==="exact_not_found"&&m.name===p.marker&&m.spreadsheetId===SHEET,
"MARKER_EXISTING_OR_UNCERTAIN");
fail(Array.isArray(i.fresh_baseline)&&same(norm(i.fresh_baseline),norm(i.baseline)),"PREPOST_DRIFT");
return {...p,state:"ONE_POST_ALLOWED"};
}catch(e){return failState(e);}
}
function afterPost(i){
try{
const p=beforePost(i);
if(p.state!=="ONE_POST_ALLOWED")return p.state==="HOLD"?p:{state:"HOLD",stage:"POST_CONTEXT"};
fail(i.post_attempts===1&&i.response?.spreadsheetId===SHEET,"POST_UNCERTAIN");
fail(i.independent_get_completed===true&&Array.isArray(i.observed),"GET_VERIFY");
const result=P.operation({kind:"digest",action:"verify",sheet_id:i.sheet_id,
asof:p.asof,stamp:p.stamp,baseline:i.baseline,verified_sha:p.score,
response:i.response,observed:i.observed,spreadsheet_id:SHEET});
fail(result.reserved===1&&result.message_proven===false&&result.device_ack===false,"GET_VERIFY");
return {state:"EMIT_NOW",receipt:["XRAY_B_RECEIPT_V1",p.asof,p.run_id,p.key,p.score,p.marker,
p.stamp,"POST=ACK_1","GET_VERIFY=PASS"].join(" | "),platform_visible_proven:false,device_ack:false};
}catch(e){return failState(e);}
}
return {route,prepare,beforePost,afterPost,classifyMarker};
})(XRAY_RESERVATION);
if(typeof module==="object"&&module.exports)module.exports=XRAY_B;
const XRAY_B_CHATGPT=(()=>{
const cell = (r,k) => r[k] ?? '';
const count = x => typeof x==='string' && /^(0|[1-9]\d*)$/.test(x) && Number.isSafeInteger(Number(x));
const decimal = x => {
if(typeof x!=='string'|| !/^-?\d+(?:[.,]\d+)?$/.test(x)) return null;
const [head, tail=''] = x.replace(',','.').split('.');
const a=head.replace(/^(-?)0+(?=\d)/,'$1'), b=tail.replace(/0+$/,'');
return (a==='-0'&&!b?'0':a)+(b?'.'+b:'');
};
const number = x => decimal(x)!==null && Number.isFinite(Number(decimal(x))) ? Number(decimal(x)) : null;
const numText = x => number(x)===null ? '—' : x;
const pct = x => number(x)===null ? '—' : x+'%';
const safe = x => String(x??'').replace(/[\r\n\t]/g,' ').replace(/[\\`*_[\]<>|]/g,'\\$&').trim().slice(0,180);
function body(G,i) {
const p=G.prepare(i);
if(p.state!=='PLAN_ONLY') return {state:p.state};
const h=i.scan[0], expected=['ASOF ET','YENİ KAYIT'];
const inds=expected.map(x=>h.indexOf(x));
const row=i.scan.find((r,k)=>k>0&&r[inds[0]]===p.asof);
const sum=i.baseline.find(r=>r[0]===p.key&&r[4]==='SUMMARY');
if(!row||!sum||!count(row[inds[1]])||![5,6,7,8].every(k=>count(sum[k]))) return {state:'CARD_INPUT_HOLD'};
const s=i.baseline.filter(r=>r[1]===p.asof&&r[4]==='EPISODE')
.sort((a,b)=>(cell(a,6)===''?Infinity:+a[5])-(cell(b,6)===''?Infinity:+b[5])||a[2].localeCompare(b[2]));
if(s.length!==+sum[5]) return {state:'CARD_INPUT_HOLD'};
const parts=['Trend','RSI','RVOL','Göreli güç','Likidite','ATR riski','Fiyat yapısı'];
const close=r=>i.exact_closes?.[r[2]]??cell(r,14);
const gapBadge=r=>{
const n=number(cell(r,19));
return n===null?'':n<0?' · 🔴 STOP altı':n<0.5?' · 🟠 görsel vurgu':'';
};
const text=[
'XNAS kapanışı **'+p.asof+'** · '+p.stamp+' · Alpaca IEX',
'',
'| Tarama | Açık epizot |','|---:|---:|','| **477/477** · 0 eksik | **'+sum[5]+'** |',
'| Puanlanan / aktif | Skor HOLD |','|---:|---:|','| **'+sum[6]+'/'+sum[5]+'** | **'+sum[7]+'** |',
'',
'**'+sum[8]+'** benzersiz sembol · **'+row[inds[1]]+'** yeni teknik AL. Bu sayı teslim edilen olay sayısı değildir.',
'',
'### Puanlanan ilk beş'
];
const ranked=s.filter(r=>cell(r,6)!=='').slice(0,5);
if(!ranked.length)text.push('Bu kapanışta puanlanmış epizot yok.');
ranked.forEach((r,j)=>{
text.push('', '#### '+(['🥇','🥈','🥉'][j]??('#'+r[5]))+' '+safe(r[3])+' · '+r[2].slice(0,10)+' · '+numText(r[6])+'/100 · '+r[21]+'/15',
'| IEX kapanış | 🔴 STOP | 🟢 2R |','|---:|---:|---:|',
'| '+[numText(close(r)),numText(r[16]),numText(r[17])].join(' | ')+' |',
'',
'İlk referans '+numText(r[15])+' USD · Teorik değişim '+pct(r[18])+' · STOP mesafesi '+pct(r[19])+gapBadge(r)+' · 2R mesafesi '+pct(r[20]),
'RSI14 '+numText(r[22])+' · RVOL20 '+numText(r[23]),
parts.map((name,k)=>name+' '+numText(r[7+k])).join(' · '));
if(r[25])text.push('Kaynak risk notu '+safe(r[25]));
});
text.push('','### Tam epizot takibi','| Sıra · Sembol / başlangıç | Skor | Seans | STOP mesafesi |','|---|---:|---:|---:|');
s.forEach(r=>text.push('| '+(r[6]?r[5]:'—')+' · '+safe(r[3])+' / '+r[2].slice(0,10)+' | '+(r[6]?numText(r[6]):'HOLD')+' | '+r[21]+'/15 | '+pct(r[19])+gapBadge(r)+' |'));
text.push('', '0,50% altı yalnız görsel vurgu. Orijinal seviyeler değişmez.',
'EOD, Guardian, skor ve epizot eşleşmesi B kapılarında doğrulanır. Rezervasyon ve ayrı geri okuma üstteki makbuzda gösterilir. Cihaz teslimi teyit edilmedi.',
'Araştırma çıktısı · Emir yok · [Kapanış koşusu](https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/'+p.run_id+')');
return {state:'BODY_READY',text:text.join('\n'),identity:[p.asof,p.run_id,p.key,p.score,p.marker,p.stamp]};
}
function finish(prepared,result,premium){
if(prepared?.state!=="BODY_READY"||result?.state!=="EMIT_NOW"||!Array.isArray(prepared.identity)||result.receipt!==["XRAY_B_RECEIPT_V1",...prepared.identity,"POST=ACK_1","GET_VERIFY=PASS"].join(" | "))return null;
const rich=typeof premium==="string"?premium.trim():"";
const detail=rich&&!rich.includes("XRAY_B_RECEIPT_V1")?rich:prepared.text;
return "## 🦖 XRAY NASDAQ Ω · Kapanış\n\n"+result.receipt+"\n\n"+detail;
}
return {body,finish};
})();
const XRAY_EXACT_EOD=(()=>{
const repo="gokaydonmez39-jpg/kripto-radar", base="https://api.github.com/repos/"+repo+"/actions/runs/";
const path=".github/workflows/xray-personal-477-eod.yml";
const expected=["offline-guard","private-sheets-auth-preflight","daily-private-scan","private-episode-followups","guardian-acceptance","daily-private-score-acceptance"];
const id=n=>Number.isSafeInteger(n)&&n>0;
const utc=s=>typeof s==="string"&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$/.test(s)?Date.parse(s):NaN;
const guard=(ok,stage)=>{if(!ok)throw Error(stage);};
function urls(n){guard(id(n),"EOD_RUN_ID");return [base+n,base+n+"/attempts/1/jobs?per_page=100"];}
function json(reply,url,stage){
const a=reply?.structuredContent?.result??reply?.structuredContent??reply?.result;
guard(reply?.isError!==true&&a?.url===url&&(a?.display_url===undefined||a.display_url===url)&&typeof a.content==="string",stage);
try{const v=JSON.parse(a.content);guard(v&&typeof v==="object"&&!Array.isArray(v),stage);return v;}
catch(_){throw Error(stage);}
}
function read(runReply,jobReply,n){
try{
const [runURL,jobsURL]=urls(n),run=json(runReply,runURL,"EOD_RUN_RESPONSE");
const j=json(jobReply,jobsURL,"EOD_ATTEMPT_RESPONSE"),jobs=j.jobs;
const c=utc(run.created_at),s=utc(run.run_started_at),e=utc(run.updated_at);
guard(run.id===n&&run.url===runURL&&run.repository?.full_name===repo&&run.path===path&&
run.event==="schedule"&&run.head_branch==="main"&&run.run_attempt===1&&run.status==="completed"&&
run.conclusion==="success"&&/^[a-f0-9]{40}$/.test(run.head_sha??"")&&c<=s&&s<=e,"EOD_RUN_IDENTITY");
guard(j.total_count===expected.length&&Array.isArray(jobs)&&jobs.length===expected.length&&
new Set(jobs.map(x=>x?.id)).size===expected.length&&expected.every(name=>jobs.filter(x=>
id(x?.id)&&x.name===name&&x.run_id===n&&x.run_url===runURL&&x.run_attempt===1&&
x.head_branch==="main"&&x.head_sha===run.head_sha&&x.status==="completed"&&x.conclusion==="success"&&
s<=utc(x.started_at)&&utc(x.started_at)<=utc(x.completed_at)&&utc(x.completed_at)<=e).length===1),
"EOD_JOBS_IDENTITY");
return {state:"EXACT_EOD_INPUT",run,jobs};
}catch(e){return {state:"HOLD",stage:/^[A-Z_0-9]+$/.test(e?.message??"")?e.message:"EOD_INPUT_INVALID"};}
}
return {urls,read};
})();
const XRAY_B_SOURCE=(()=>{
const names=["daily-private-scan","private-episode-followups","guardian-acceptance","daily-private-score-acceptance"];
const time=x=>typeof x==="string"?Date.parse(x):NaN;
const match=(x,fn)=>{const a=x.filter(fn);return a.length===1?a[0]:null;};
function lines(reply,job){
if(reply?.isError===true||typeof (reply?.structuredContent?.result??reply?.structuredContent??reply?.result)?.content!=="string")return null;
const from=time(job.started_at),to=time(job.completed_at);
if(!(from<=to))return null;
return (reply?.structuredContent?.result??reply?.structuredContent??reply?.result).content.split(/\r?\n/).flatMap(l=>{
const m=/^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z) (.*)$/.exec(l);
const t=time(m?.[1]);return m&&from<=t&&t<to+1000?[m[2].trim()]:[];
});
}
function payload(ls){
return (ls??[]).flatMap(s=>{
if(/^\*\*\*".*\*\*\*$/.test(s))s="{"+s.slice(3,-3)+"}";
if(!s.startsWith("{")||!s.endsWith("}"))return [];
try{const j=JSON.parse(s);return j&&typeof j==="object"&&!Array.isArray(j)?[j]:[];}catch{return [];}
});
}
function check(exact,plan,scan,score,rawByJobId){
const hold=stage=>({state:"HOLD",stage});
if(exact?.state!=="EXACT_EOD_INPUT"||plan?.state!=="PLAN_ONLY"||exact.run?.id!==plan.run_id||
!Array.isArray(scan)||!Array.isArray(score)||!Array.isArray(exact.jobs))return hold("SOURCE_CONTEXT");
const h=scan[0],d=plan.asof,id=plan.run_id;
const a=h?.indexOf("ASOF ET"), ac=h?.indexOf("YENİ KAYIT");
const sr=match(scan.slice(1),r=>r[a]===d), su=match(score.slice(1),r=>r[0]===plan.key&&r[1]===d&&r[4]==="SUMMARY");
const count=x=>typeof x==="string"&&/^(0|[1-9]\d*)$/.test(x)&&Number.isSafeInteger(Number(x));
if(!sr||!su||!count(sr[ac])||![5,6,7].every(i=>count(su[i])))return hold("SOURCE_COUNTS_CONTEXT");
const js=names.map(n=>match(exact.jobs,j=>j.name===n&&j.run_id===id&&j.run_attempt===1&&j.head_sha===exact.run.head_sha&&j.conclusion==="success"));
if(js.some(j=>!j))return hold("SOURCE_JOB_BIND");
const ll=js.map(j=>lines(rawByJobId?.[j.id],j));
const bad=ll.findIndex(x=>!x?.length);if(bad>=0)return hold("LOG_UNAVAILABLE_"+bad);
const [s,f,g]=ll.map(payload);
if(!match(ll[0],x=>x==="XRAY_PERSONAL_GITHUB_HANDOFF=PASS_477_477_SOURCE_POLICY_SHA_BOUND_PRIVATE")||
!match(s,o=>o.status==="PRIVATE_SHEET_READBACK_PASS"&&o.asof_et===d&&o.candidates===+sr[ac]))
return hold("SCAN_READBACK_RECEIPT");
const readable=new Set(["SWING_SCORE_PRIVATE_READBACK_PASS","SWING_SCORE_IDEMPOTENT_READBACK_PASS"]);
if(!match(f,o=>readable.has(o.status)&&o.asof_et===d&&o.execution==="NONE"&&o.active_episodes===+su[5]&&o.scoreable===+su[6]))
return hold("EPISODE_SCORE_READBACK_RECEIPT");
if(!match(g,o=>o.schema==="XRAY_PERSONAL_PRIVATE_EVIDENCE_AUDIT_V1"&&o.status==="READ_ONLY_EVIDENCE_AUDIT"&&
o.execution==="NONE"&&o.sheet_writes===0&&o.last_verified_scan_asof===d&&o.last_asof_score==="SUMMARY_PRESENT"&&
o.score_count===+su[6]&&o.score_hold_count===+su[7]&&o.scored_active_episodes===+su[5]))
return hold("GUARDIAN_CURRENT_ASOF_RECEIPT");
if(!match(ll[3],x=>x==="XRAY_DAILY_SWING_SCORE=PRIVATE_READBACK_PASS_ASOF_"+d+"_NOT_CHATGPT_DELIVERY"))
return hold("SCORE_ACCEPTANCE_RECEIPT");
return {state:"SOURCE_RECEIPTS_VERIFIED",asof:d,run_id:id};
}
return {check};
})();
const XRAY_B_ONCE=(()=>{
const SID=binding.sheet;
const digestSheet="SWING_SKOR_GUNLUK";
const unwrap=r=>{
if(r?.isError===true)return null;
const x=r?.structuredContent??r?.result;
return x?.result??x;
};
const inputRows=r=>{
const x=unwrap(r);
return typeof x?.range==="string"&&/^SWING_SKOR_GUNLUK!A1:AI[1-9]\d*$/.test(x.range)&&
x.majorDimension==="ROWS"&&Array.isArray(x.values)?x.values:null;
};
const hold=(stage,writes=0)=>({state:"HOLD",stage,post_calls:writes});
async function execute(i,api,G,C,S){
let attempted=0;
try{
const preliminary=G.prepare(i);
if(preliminary.state!=="PLAN_ONLY")return {state:preliminary.state,stage:preliminary.stage,post_calls:0};
if(i.scheduled_slot_verified!==true||i.single_writer_verified!==true)
return hold("REAL_SCHEDULE_OR_SINGLE_WRITER_UNVERIFIED");
const history=unwrap(i.history_response);
if(typeof history?.range!=="string"||!/^ADAY_GECMISI!A1:Z[1-9]\d*$/.test(history.range)||
history.majorDimension!=="ROWS"||!Array.isArray(history.values))
return hold("LIFECYCLE_HISTORY_GET_UNVERIFIED");
const life=XRAY_B_LIFECYCLE.check(preliminary,i.baseline,history.values);
if(life.state!=="LIFECYCLE_VERIFIED")return hold(life.stage);
const proof=S.check(i.exact,preliminary,i.scan,i.baseline,i.rawByJobId);
if(proof.state!=="SOURCE_RECEIPTS_VERIFIED")return hold(proof.stage??"SOURCE_RECEIPTS");
const prepared=C.body(G,i);
if(prepared.state!=="BODY_READY")return hold("CARD_BODY_UNVERIFIED");
const sb={spreadsheet_id:SID,sheet_name:digestSheet,range:"A:AI",value_render_option:"FORMATTED_VALUE"};
const [marker_response,fresh]=await Promise.all([
api.cells({spreadsheet_id:SID,ranges:[preliminary.marker],cell_fields:"formattedValue"}).catch(error=>({isError:true,marker_lookup_exception:String(error)})),
api.range(sb)
]);
const fresh_baseline=inputRows(fresh);
if(!fresh_baseline)return hold("PREPOST_GET_UNVERIFIED");
const gate={...i,marker_response,fresh_baseline,result_prepared:true,source_receipts_verified:true,lifecycle_verified:true};
const before=G.beforePost(gate);
if(before.state!=="ONE_POST_ALLOWED")return {state:before.state,stage:before.stage,post_calls:0};
if(typeof api.prePostAuth!=="function"||(await api.prePostAuth())!==true)
return hold("B_PREPOST_NATURAL_SLOT_UNVERIFIED");
attempted=1;
const raw=await api.post({spreadsheet_id:SID,requests:before.requests});
const response=unwrap(raw);
if(!response||response.spreadsheetId!==SID||!Array.isArray(response.replies))
return hold("POST_UNCERTAIN_DO_NOT_RESEND",attempted);
const observed=inputRows(await api.range(sb));
if(!observed)return hold("READBACK_UNCERTAIN_DO_NOT_RESEND",attempted);
const verified=G.afterPost({...gate,post_attempts:1,response,observed,independent_get_completed:true});
if(verified.state!=="EMIT_NOW")return hold(verified.stage??"READBACK_UNVERIFIED_DO_NOT_RESEND",attempted);
const text=C.finish(prepared,verified,i.premium);
if(typeof text!=="string"||!text)return hold("FINAL_RENDER_UNVERIFIED_DO_NOT_RESEND",attempted);
return {state:"EMIT_NOW",post_calls:1,text};
}catch(_){return hold(attempted?"AFTER_POST_UNCERTAIN_DO_NOT_RESEND":"PREPOST_CONNECTOR_UNAVAILABLE",attempted);}
}
return {execute};
})();
const XRAY_B_LIFECYCLE=(()=>{
const expected=["ALARM KİMLİĞİ","ASOF ET","SEMBOL","IEX KAPANIŞ USD","STOP 2ATR","HEDEF 2R","TAKİP DURUMU"];
const sc=["ASOF_ET","EPIZOT_KIMLIGI","SEMBOL","KAYIT_TIPI","ORIJINAL_REFERANS_USD","ORIJINAL_STOP_USD","ORIJINAL_HEDEF_2R_USD","TAKIP_SEANSI"];
const indexes=(h,names)=>Array.isArray(h)?names.map(n=>h.indexOf(n)!==h.lastIndexOf(n)?-1:h.indexOf(n)):[-1];
const num=x=>{
if(typeof x!=="string"||!/^\d+([.,]\d+)?$/.test(x))return null;
const [a,b=""]=x.replace(",",".").split(".");
const whole=a.replace(/^0+(?=\d)/,""), f=b.replace(/0+$/,"");
return whole==="0"&&!f?null:whole+(f?"."+f:"");
};
function check(p,score,history){
const hold=stage=>({state:"HOLD",stage});
if(p?.state!=="PLAN_ONLY"||!Array.isArray(score)||!Array.isArray(history)||
!/^\d{4}-\d\d-\d\d$/.test(p.asof??""))return hold("LIFECYCLE_CONTEXT");
const x=indexes(history[0],expected),y=indexes(score[0],sc);
if(x.includes(-1)||y.includes(-1))return hold("LIFECYCLE_SCHEMA");
const e=score.slice(1).filter(r=>r[y[0]]===p.asof&&r[y[3]]==="EPISODE");
const active=new Map(), ids=new Set();
for(const r of history.slice(1)){
if(!Array.isArray(r)||r.every(v=>!v))continue;
const k=r[x[0]], prefix=r[x[6]];
if(typeof k!=="string"||!k||ids.has(k))return hold("LIFECYCLE_HISTORY_ID");
ids.add(k);
if(typeof prefix!=="string")return hold("LIFECYCLE_STATUS");
const follow=/^AÇIK • (0|[1-9]|1[0-5])\/15 SEANS$/.exec(prefix);
if(follow){active.set(k,{r,t:follow[1]});}
else if(!/^KAPALI • .+ • (0|[1-9]|1[0-5])\/15 SEANS$/.test(prefix))return hold("LIFECYCLE_STATUS");
}
if(e.length!==active.size||new Set(e.map(r=>r[y[1]])).size!==e.length)return hold("LIFECYCLE_ACTIVE_SET");
for(const r of e){
const k=r[y[1]],sym=r[y[2]], z=active.get(k);
if(!z||typeof sym!=="string"||!/^[A-Z0-9][A-Z0-9.-]*$/.test(sym)||
!/^\d{4}-\d\d-\d\d\|/.test(k)||k!==z.r[x[1]]+"|"+sym||z.r[x[2]]!==sym||
String(z.r[x[1]])>p.asof||z.t!==r[y[7]])return hold("LIFECYCLE_EPISODE_ID_OR_SESSION");
if([4,5,6].some(j=>num(r[y[j]])===null||num(r[y[j]])!==num(z.r[x[j-1]])))return hold("LIFECYCLE_IMMUTABLE_LEVEL");
}
return {state:"LIFECYCLE_VERIFIED",count:e.length,asof:p.asof,run_id:p.run_id};
}
return {check};
})();
const XRAY_C_OPEN=(()=>{
const repo="gokaydonmez39-jpg/kripto-radar", root="https://api.github.com/repos/"+repo+"/actions/runs/", path=".github/workflows/xray-nasdaq-a34-preopen.yml";
const ts=x=>typeof x==="string"&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(x)?Date.parse(x):NaN;
const date=x=>typeof x==="string"&&/^\d{4}-\d\d-\d\d$/.test(x)&&Number.isFinite(ts(x+"T00:00:00Z"));
const positive=x=>Number.isSafeInteger(x)&&x>0, count=x=>Number.isSafeInteger(x)&&x>=0;
const utcDate=x=>new Date(x).toISOString().slice(0,10);
const openStates=new Set(["CORE_PREOPEN_PASS_DEVICE_ACK_UNKNOWN","CORE_PREOPEN_PASS_DISPUTED_EVENT_HOLD_DEVICE_ACK_UNKNOWN"]);
const state=(s,stage)=>({state:s,stage});
function json(reply,url){
const o=reply?.structuredContent?.result??reply?.structuredContent??reply?.result;
if(reply?.isError===true||o?.url!==url||(o?.display_url!==undefined&&o.display_url!==url)||typeof o.content!=="string")return null;
try{return JSON.parse(o.content);}catch(_){return null;}
}
function urls(id){return positive(id)?[root+id,root+id+"/attempts/1/jobs?per_page=100"]:null;}
function proof(i){
const {runId,session,asof,now_iso}=i??{}, t=ts(now_iso), u=urls(runId);
if(!u||!date(session)||!date(asof)||!(asof<session)||!Number.isFinite(t))return state("HOLD","A34_CONTEXT");
const r=json(i.run_response,u[0]), o=json(i.jobs_response,u[1]);
const start=ts(r?.run_started_at), end=ts(r?.updated_at);
if(r?.id!==runId||r?.url!==u[0]||r?.repository?.full_name!==repo||r?.head_branch!=="main"||r?.path!==path||
r?.run_attempt!==1||r?.status!=="completed"||r?.conclusion!=="success"||
!/^[a-f0-9]{40}$/.test(r?.head_sha??"")||!(ts(r?.created_at)<=start&&start<=end&&end<=t))return state("HOLD","A34_RUN_UNVERIFIED");
const ev=r.event;
if(ev!=="schedule"&&ev!=="workflow_run")return state("HOLD","A34_EVENT_UNVERIFIED");
if(ev==="schedule"&&(utcDate(start)!==session||start<ts(session+"T03:17:00Z")))return state("HOLD","A34_DOGAL_SLOT_UNVERIFIED");
if(ev==="workflow_run"&&utcDate(start)!==session)return state("HOLD","A34_DOWNSTREAM_SESSION_UNVERIFIED");
const j=o?.jobs, names=["offline-guard","private-preopen"];
if(o?.total_count!==2||!Array.isArray(j)||j.length!==2||new Set(j.map(x=>x?.id)).size!==2||
names.some(n=>j.filter(x=>positive(x?.id)&&x.name===n&&x.run_id===runId&&x.run_url===u[0]&&
x.run_attempt===1&&x.head_sha===r.head_sha&&x.status==="completed"&&x.conclusion==="success"&&
start<=ts(x.started_at)&&ts(x.started_at)<=ts(x.completed_at)&&ts(x.completed_at)<=end).length!==1))return state("HOLD","A34_JOBS_UNVERIFIED");
const p=j.find(x=>x.name==="private-preopen"), raw=(i.preopen_log?.structuredContent?.result??i.preopen_log?.structuredContent??i.preopen_log?.result)?.content;
if(i.preopen_job_id!==p.id||i.preopen_log?.isError===true||typeof raw!=="string")return state("HOLD","A34_LOG_UNVERIFIED");
const match=raw.split(/\r?\n/).flatMap(l=>{
const m=/^(\S+) (.*)$/.exec(l), at=ts(m?.[1]);if(!m||!(ts(p.started_at)<=at&&at<ts(p.completed_at)+1000))return [];
let s=m[2].trim();if(/^\*\*\*".*\*\*\*$/.test(s))s="{"+s.slice(3,-3)+"}";
if(!s.startsWith("{")||!s.endsWith("}"))return [];
try{const v=JSON.parse(s);return v&&openStates.has(v.state)&&v.asof_et===asof&&v.next_xnas_session===session&&
v.covered===477&&v.source==="ALPACA_IEX_RAW_1DAY"&&v.al_identity_check==="EXACT_AL_IDENTITY_PASS"&&
v.al_level_check==="EXACT_AL_LEVELS_PASS"&&v.orders===false&&v.writes===false&&v.private_data_published===false&&
count(v.open_episodes)&&count(v.quarantined_research_events)?[v]:[];}catch(_){return [];}
});
if(match.length!==1)return state("HOLD","A34_CURRENT_RECEIPT_UNVERIFIED");
return {state:ev==="schedule"?"NATURAL_A34_VERIFIED":"EOD_TRIGGERED_A34_VERIFIED",asof,session,run_id:runId,covered:477,open_episodes:match[0].open_episodes,quarantined:match[0].quarantined_research_events};
}
const timeParts=t=>Object.fromEntries(new Intl.DateTimeFormat("en-CA",{timeZone:"Europe/Istanbul",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(t).map(x=>[x.type,x.value]));
const day=x=>[x.year,x.month,x.day].join("-");
function render(i){
const started=ts(i?.started_at), now=ts(i?.now_iso), slot=ts(i?.scheduled_for);
if(i?.xnas_session_verified!==true||![started,now,slot].every(Number.isFinite)||now<started)return state("NO_C_CARD","NATURAL_SLOT_UNVERIFIED");
const p=timeParts(slot), s=timeParts(started), n=timeParts(now);
if(day(p)!==i.session||day(s)!==i.session||day(n)!==i.session||p.hour!=="16"||p.minute!=="57"||
Number(s.hour)*60+Number(s.minute)<1005||Number(n.hour)*60+Number(n.minute)>=1050)return state("NO_C_CARD","OUTSIDE_OPEN_WINDOW");
const proofOf=x=>x&&x.session===i.session&&x.asof===i.asof&&x.covered===477&&positive(x.run_id);
const a=proofOf(i.natural)&&i.natural.state==="NATURAL_A34_VERIFIED"?i.natural:
proofOf(i.downstream)&&i.downstream.state==="EOD_TRIGGERED_A34_VERIFIED"?i.downstream:null;
const natural=a?.state==="NATURAL_A34_VERIFIED";
const line=natural?"**Planlı doğal A34 doğrulandı.**":
a?"**Planlı doğal A34 doğrulanmadı.** Kapanış sonrası A34 veri kontrolü doğrulandı.":
"**Planlı doğal A34 doğrulanmadı.** Geçerli ön kontrol makbuzu yok.";
const footer=a?["ASOF "+a.asof+" · 477/477 · "+a.open_episodes+" açık epizot · "+a.quarantined+" karantina",
"[A34 koşusu](https://github.com/"+repo+"/actions/runs/"+a.run_id+")"]:[];
return {state:"C_BODY_READY",text:["## 🦖 XRAY NASDAQ 477 · Açılış sağlığı",
"P0|PREOPEN_DAILY_HEALTH|"+i.session,"",line,...footer,"",
"Araştırma radarı · Emir yok · Açılış teslim kabulü bu kart üretilirken ilan edilmez."].join("\n")};
}
return {urls,proof,render};
})();
const XRAY_A_IMPL=(()=>{const module={exports:{}};
'use strict';
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
function premiumBody(G,i) {
const p=G.prepare(i);
if(p.state!=='PLAN_ONLY') return {state:p.state};
const h=i.scan[0], expected=['ASOF ET','YENİ KAYIT'];
const inds=expected.map(x=>h.indexOf(x));
const row=i.scan.find((r,k)=>k>0&&r[inds[0]]===p.asof);
const sum=i.baseline.find(r=>r[0]===p.key&&r[4]==='SUMMARY');
if(!row||!sum||!count(row[inds[1]])||![5,6,7,8].every(k=>count(sum[k]))) return {state:'CARD_INPUT_HOLD'};
const s=i.baseline.filter(r=>r[1]===p.asof&&r[4]==='EPISODE')
.sort((a,b)=>(cell(a,6)===''?Infinity:+a[5])-(cell(b,6)===''?Infinity:+b[5])||a[2].localeCompare(b[2]));
if(s.length!==+sum[5]) return {state:'CARD_INPUT_HOLD'};
const parts=['Trend','RSI','RVOL','Göreli güç','Likidite','ATR riski','Fiyat yapısı'];
const close=r=>i.exact_closes?.[r[2]]??cell(r,14);
const gapBadge=r=>{
const n=number(cell(r,19));
return n===null?'':n<0?' · 🔴 STOP altı':n<0.5?' · 🟠 görsel vurgu':'';
};
const text=[
'XNAS kapanışı **'+p.asof+'** · '+p.stamp+' · Alpaca IEX',
'',
'| Tarama | Açık epizot |','|---:|---:|','| **477/477** · 0 eksik | **'+sum[5]+'** |',
'| Puanlanan / aktif | Skor HOLD |','|---:|---:|','| **'+sum[6]+'/'+sum[5]+'** | **'+sum[7]+'** |',
'',
'**'+sum[8]+'** benzersiz sembol · **'+row[inds[1]]+'** yeni teknik AL. Bu sayı teslim edilen olay sayısı değildir.',
'',
'### Puanlanan ilk beş'
];
const ranked=s.filter(r=>cell(r,6)!=='').slice(0,5);
if(!ranked.length)text.push('Bu kapanışta puanlanmış epizot yok.');
ranked.forEach((r,j)=>{
text.push('', '#### '+(['🥇','🥈','🥉'][j]??('#'+r[5]))+' '+safe(r[3])+' · '+r[2].slice(0,10)+' · '+numText(r[6])+'/100 · '+r[21]+'/15',
'| IEX kapanış | 🔴 STOP | 🟢 2R |','|---:|---:|---:|',
'| '+[numText(close(r)),numText(r[16]),numText(r[17])].join(' | ')+' |',
'',
'İlk referans '+numText(r[15])+' USD · Teorik değişim '+pct(r[18])+' · STOP mesafesi '+pct(r[19])+gapBadge(r)+' · 2R mesafesi '+pct(r[20]),
'RSI14 '+numText(r[22])+' · RVOL20 '+numText(r[23]),
parts.map((name,k)=>name+' '+numText(r[7+k])).join(' · '));
if(r[25])text.push('Kaynak risk notu '+safe(r[25]));
});
text.push('','### Tam epizot takibi','| Sıra · Sembol / başlangıç | Skor | Seans | STOP mesafesi |','|---|---:|---:|---:|');
s.forEach(r=>text.push('| '+(r[6]?r[5]:'—')+' · '+safe(r[3])+' / '+r[2].slice(0,10)+' | '+(r[6]?numText(r[6]):'HOLD')+' | '+r[21]+'/15 | '+pct(r[19])+gapBadge(r)+' |'));
text.push('', '0,50% altı yalnız görsel vurgu. Orijinal seviyeler değişmez.',
'EOD, Guardian, skor ve epizot eşleşmesi B kapılarında doğrulanır. Rezervasyon ve ayrı geri okuma üstteki makbuzda gösterilir. Cihaz teslimi teyit edilmedi.',
'Araştırma çıktısı · Emir yok · [Kapanış koşusu](https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/'+p.run_id+')');
return {state:'BODY_READY',text:text.join('\n'),identity:[p.asof,p.run_id,p.key,p.score,p.marker,p.stamp]};
}
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
let attempted=0;
try {
const proof=proveA(i);
if(proof.state!=='A_SOURCE_VERIFIED')return {...proof,post_calls:0};
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
const body=selected.map(({row:r,e})=>{
const label=stop(r)?'🔴 '+(r[5]==='BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS'?'STOP ve 2R teorik temas · sıra bilinmiyor':'Teorik STOP teması'):
r[5]==='TARGET_TOUCHED'?'🎯 Teorik 2R teması':r[5]==='AL_NEW_EPISODE'?'🟢 Yeni teknik AL':'⏱ Takip süresi doldu';
return ['**'+label+' · '+safe(r[3])+'**','Olay: `'+r[0]+'` · ASOF '+proof.asof+' · '+r[15],
'IEX kapanış '+r[7]+' USD · İlk referans '+e[4]+' USD · STOP '+r[8]+' USD · 2R '+r[9]+' USD',
(String(r[19]).includes('gap_below_stop=True')?'STOP altında boşluk kaydı var. ':'')+
'Araştırma çıktısı · Emir yok · İşlem fiyatı ve cihaz teyidi yok.',
'[Olayın kaynak koşusu]('+WEB+proof.runId+')'].join('\n');
}).join('\n\n');
if(!(await io.stillAuthorized()))return HOLD('A_PRERESERVATION_AUTHORITY_UNVERIFIED');
if(i.dry_run===true)return {state:'A_READY_DRY',post_calls:0,asof:proof.asof,count:keys.length};
attempted=1;
const response=unwrap(await io.post({spreadsheet_id:i.spreadsheetId,requests:result.requests}));
if(response?.spreadsheetId!==i.spreadsheetId||!Array.isArray(response.replies))return HOLD('A_POST_UNCERTAIN_DO_NOT_RESEND',1);
const observed=googleRows(await io.range(query),'UYARI_OLAYLARI','T',20);
const check=P.operation({...plan,action:'verify',spreadsheet_id:i.spreadsheetId,response,observed});
if(check.reserved!==keys.length||check.message_proven!==false||check.device_ack!==false)return HOLD('A_GET_VERIFY_DO_NOT_RESEND',1);
return {state:'EMIT_NOW',post_calls:1,text:'## 🦖 XRAY NASDAQ Ω · Olaylar\n\nXRAY_A_RECEIPT_V1 | '+
[proof.asof,proof.runId,i.stamp,'COUNT='+keys.length,'POST=ACK_1','GET_VERIFY=PASS'].join(' | ')+'\n\n'+body};
}catch{return HOLD(attempted?'A_AFTER_POST_UNCERTAIN_DO_NOT_RESEND':'A_PREPOST_FAILED',attempted);}
}
module.exports={premiumBody,locateA,proveA,reserveA,constants:{PENDING,API,WEB,WORKFLOW,REPO,A_JOBS,SCOPE,ALGO}};
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
range:io.range,cells:io.cells,post:io.post,
stillAuthorized:async()=> {
const [s,w]=await Promise.all([getSlot(),existing.writer(io)]);
return sameSlot(s,slot)&&w===null;
}
},lib.planner,lib.markerCheck);
} catch {return HOLD('A_RUNTIME_OR_SOURCE_UNVERIFIED');}
}
async function coordinate({checkCurrentRisk,runB,runA}) {
const risk=await checkCurrentRisk();
if(risk==='UNVERIFIED')return HOLD('TURN_RISK_QUEUE_UNVERIFIED');
if(risk===true){
const a=await runA(true);
if(a.state==='EMIT_NOW'||a.post_calls>0||a.state==='HOLD')return a;
}
const b=await runB();
if(b.state==='EMIT_NOW'||b.post_calls!==0)return b;
if(risk!==true){
const a=await runA(false);
if(a.state==='EMIT_NOW'||a.post_calls>0)return a;
return {state:'NO_EMIT',post_calls:0,b,a};
}
return b;
}
Object.assign(module.exports,{runA,coordinate});
const PIN_REV='c3aa60722cf848e83477525eceae209498c3e1e1';
const PIN_SHA='1586498cd9c390b5eb3935261f90545d3e3b06f6';
const PIN_URL='https://github.com/'+REPO+'/blob/'+PIN_REV+'/personal-swing/delivery_reservation_portable.js';
const BLOB_URL='https://api.github.com/repos/'+REPO+'/git/blobs/'+PIN_SHA;
const TASK_ID=binding.id;
function bindNative(tools, inventory) {
const short={task:['automations','peek'],range:['google_drive','get_spreadsheet_range'],
cells:['google_drive','get_spreadsheet_cells'],github:['github','fetch'],logs:['github','fetch_workflow_job_logs'],
post:['google_drive','batch_update_spreadsheet']};
const legacy={automations:'Automations',google_drive:'Google_Drive',github:'GitHub'};
const names=new Set((inventory??[]).map(t=>typeof t==='string'?t:t?.name));
const pick=(arr)=>arr.find(n=>typeof tools?.[n]==='function'&&(names.size===0||names.has(n)));
const roles=Object.fromEntries(Object.entries(short).map(([k,[p,op]])=>[k,pick([
'mcp__codex_apps__'+p+'_'+op,'mcp__'+legacy[p]+'__'+op
])]));
roles.clock=pick(['clock__curr_time']);
if(Object.values(roles).some(x=>!x))return null;
return Object.fromEntries(Object.entries(roles).map(([k,n])=>[k,args=>tools[n](args)]));
}
async function runNaturalCandidate({mode,expected_asof,spreadsheetId,trigger,dryRun=false},tools,inventory) {
if(mode!=='natural_task'||!oneday(expected_asof)||typeof spreadsheetId!=='string')return HOLD('TURN_NOT_NATURAL_OR_ASOF_UNVERIFIED');
const io=bindNative(tools,inventory);
if(!io)return HOLD('TURN_NATIVE_ADAPTER_UNAVAILABLE');
try {
const [task,clock]=await Promise.all([io.task({jawbone_id:TASK_ID}),io.clock({})]);
const a=(unwrap(task)??task)?.automations?.find(t=>t.id===TASK_ID);
const u=(unwrap(clock)??clock)?.current_time;
if(!a||typeof a.prompt!=='string'||typeof u!=='string'||!/^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC$/.test(u))return HOLD('TURN_RECORD');
assertCurrentPrompt(a.prompt);
const N=XRAY_B_NATURAL;
const bootSlot=N.natural(a,u.replace(' ','T').replace(' UTC','Z'),trigger);
if(!bootSlot)return HOLD('TURN_SLOT_UNVERIFIED');
const boot={prompt:a.prompt,slot:bootSlot};
if(spreadsheetId!==binding.sheet)return HOLD('TURN_SHEET_BIND');
const existing={natural:N.natural,writer:N.writer,loadPlanner:async()=>({planner:XRAY_RESERVATION,markerCheck:XRAY_B.classifyMarker})};
if(dryRun===true)return await runA({mode,expected_asof,spreadsheetId,trigger,taskId:TASK_ID,dryRun:true,boot},io,existing);
return await coordinate({
checkCurrentRisk:async()=>{
const queue=googleRows(await io.range({spreadsheet_id:spreadsheetId,
sheet_name:'UYARI_OLAYLARI',range:'A:T',value_render_option:'FORMATTED_VALUE'}),'UYARI_OLAYLARI','T',20);
if(!queue||queue[0][0]!=='OLAY_ANAHTARI'||queue[0][4]!=='OLAY_ASOF_ET'||queue[0][5]!=='OLAY_KODU'||
queue[0][6]!=='ONCELIK'||queue[0][17]!=='BILDIRIM_DURUMU')return 'UNVERIFIED';
const rows=queue.slice(1).filter(r=>r[4]===expected_asof);
if(rows.some(r=>!r[0]||!r[5]||!r[6]||!r[17])||new Set(rows.map(r=>r[0])).size!==rows.length)return 'UNVERIFIED';
return rows.some(r=>r[17]===PENDING&&stop(r));
},
runB:()=>N.run({expected_asof,trigger},tools,inventory),
runA:riskOnly=>runA({mode,expected_asof,spreadsheetId,trigger,taskId:TASK_ID,riskOnly,boot},io,existing)
});
}catch{return HOLD('TURN_READ_OR_BOOTSTRAP_UNVERIFIED');}
}
Object.assign(module.exports,{runNaturalCandidate});
return module.exports;})();
const XRAY_AB_STAGED=(()=>{const module={exports:{}};
'use strict';
const CANARY = 'CANARY_LOCKED_V1';
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
const calledAs = (a,n,clock) => {
const s=n.natural(a,clock);
const age=s&&Date.parse(clock)-Date.parse(s.started_at);
return s&&a.conversation_id===CHAT&&age>=-999&&age<=20*60*1000?s:null;
};
async function run(expected_asof,tools,inventory,implementation,seal,initial) {
if(!/^\d{4}-\d\d-\d\d$/.test(expected_asof)||!SHA_PATTERN.test(seal))return state('AB_ASOF');
const inv=new Set((inventory??[]).map(x=>typeof x==='string'?x:x?.name));
const pick=names=>names.find(n=>typeof tools?.[n]==='function'&&(inv.size===0||inv.has(n)));
const peekName=pick(['mcp__codex_apps__automations_peek','mcp__Automations__peek']);
const clockName=pick(['clock__curr_time']);
if(!peekName)return state('AB_AUTH_TOOLS');
const peek=async()=>{const a=own(await tools[peekName]({jawbone_id:TASK}));return a?.length===1?a[0]:null;};
const clock=async()=>{try{return clockName?iso(raw(await tools[clockName]({}),'current_time')?.current_time):'';}catch{return '';}};
const aTools=new Proxy(Object.create(null),{get(_target,key){
if(key===peekName)return async args=>{
const data=raw(await tools[peekName](args),'automations');
return data?{structuredContent:data}:{isError:true};
};
return tools[key];
}});
const start=initial??await peek();
if(!start||start.is_enabled!==true||start.conversation_id!==CHAT||typeof start.prompt!=='string')return state('AB_TASK_ID');
assertCurrentPrompt(start.prompt);
const N=XRAY_B_NATURAL;
const f=phase(start.prompt);
const nativeB=()=>N.run({expected_asof},tools,inventory);
if(!f||!clockName)return f?.kind===CANARY
? await N.run({expected_asof},tools,inventory,undefined,undefined,undefined,start)
: await nativeB();
const args={mode:'natural_task',expected_asof,spreadsheetId:binding.sheet};
if(f.kind==='ARMED_AFTER_CANARY_V1'){
const s=calledAs(start,N,await clock());
if(!s)return await nativeB();
if(f.seal!==seal||f.asof>expected_asof||f.run===s.id||!(Date.parse(f.stamp)<Date.parse(s.started_at)))return await nativeB();
const out=await implementation.runNaturalCandidate(args,aTools,inventory);
const beforeB=new Set(['TURN_NATIVE_ADAPTER_UNAVAILABLE','TURN_RISK_QUEUE_UNVERIFIED','TURN_SHEET_BIND','TURN_RECORD','TURN_SLOT_UNVERIFIED']);
if(out?.post_calls===0&&beforeB.has(out.stage))return await nativeB();
return out;
}
const b=await N.run({expected_asof,preferDryCanaryOnStop:f.kind===CANARY},tools,inventory,undefined,undefined,undefined,start);
if(b?.state==='EMIT_NOW'||b?.post_calls!==0||b?.state==='WAIT_CURRENT_EOD')return b;
const s=calledAs(start,N,await clock());
if(!s)return b;
if(!Number.isFinite(Date.parse(s.scheduled_for)))return b;
const cTime=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Istanbul',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(s.scheduled_for));
if(cTime==='16:57')return b;
const can=await implementation.runNaturalCandidate({...args,dryRun:true},aTools,inventory);
if(!verifiedCanary(f,can,expected_asof,s))return {state:'AB_CANARY_NOT_ACCEPTED',stage:can?.stage??can?.state,b,post_calls:0};
const updateName=pick(['mcp__codex_apps__automations_update','mcp__Automations__update']);
if(!updateName)return {state:'A_CANARY_VERIFIED_ACTIVATION_UNAVAILABLE',post_calls:0,asof:expected_asof};
const [fresh,checkedAt]=await Promise.all([peek(),clock()]);
const freshSlot=calledAs(fresh,N,checkedAt);
if(!identity(start,fresh)||fresh?.prompt!==start.prompt||freshSlot?.id!==s.id)return state('A_CANARY_ACTIVATION_DRIFT');
const next=promotePrompt(fresh.prompt,can,expected_asof,s,checkedAt,seal);
if(!next)return state('A_CANARY_ACTIVATION_PLAN');
const ack=raw(await tools[updateName]({jawbone_id:TASK,prompt:next}),'success');
const end=await peek();
if(ack?.success!==true||!identity(fresh,end)||end?.prompt!==next)return state('A_CANARY_ACTIVATION_READBACK');
return {state:'A_CANARY_VERIFIED_ARMED_NEXT_NATURAL',asof:expected_asof,post_calls:0,
text:'XRAY_A_CANARY_V1 | '+expected_asof+' | '+s.id+' | POST=0 | A_ARMED_NEXT_NATURAL'};
}
module.exports={run,phase,promotePrompt,verifiedCanary};
return module.exports;})();
return {executeRecordedAB,C_HELPER:XRAY_C_OPEN};
}