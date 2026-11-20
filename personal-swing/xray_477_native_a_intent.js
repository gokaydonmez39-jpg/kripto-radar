'use strict';

// Deterministic packaging, not a publisher. This module has no tool, network,
// reservation, phase-update, or delivery operation.
const {createHash} = require('node:crypto');
const hash=(kind,x)=>createHash(kind).update(x).digest('hex');
const forty=/^[0-9a-f]{40}$/;
const once=(xs)=>Array.isArray(xs)&&xs.length===1?xs[0]:null;
const hold=stage=>({state:'HOLD',stage,authorization:'NONE',post_calls:0});
const asofOk=d=>typeof d==='string'&&/^\d{4}-\d\d-\d\d$/.test(d);
const body=r=>r?.isError===true?null:(r?.structuredContent?.result??r?.structuredContent??r?.result??null);

function buildNativeAIntent(input) {
  try {
    const {runtimeText,runtimeBlob,binding,expectedAsof,snapshot,runResponse,jobsResponse,logs}=input;
    if(typeof runtimeText!=='string'||!forty.test(runtimeBlob??'')||
       hash('sha1','blob '+Buffer.byteLength(runtimeText)+'\0'+runtimeText)!==runtimeBlob) return hold('NATIVE_INTENT_RUNTIME_PIN');
    if(!asofOk(expectedAsof)||!/^[0-9a-f]{32}$/.test(binding?.task??'')||
       !/^[0-9a-f-]{36}$/.test(binding?.chat??'')||!/^[A-Za-z0-9_-]{20,70}$/.test(binding?.sheet??''))return hold('NATIVE_INTENT_BINDING');
    const rt=JSON.parse(runtimeText);
    if(rt.schema!=='XRAY_NASDAQ_477_RUNTIME_V3'||rt.blocks?.length!==12||
       typeof rt.portable?.code!=='string'||
       hash('sha1','blob '+Buffer.byteLength(rt.portable.code)+'\0'+rt.portable.code)!==rt.portable.blob)
      return hold('NATIVE_INTENT_RUNTIME_SCHEMA');
    const blocks=rt.blocks.map(b=>b.replaceAll('XRAY_CONFIG_TASK_ID_V1',binding.task)
      .replaceAll('XRAY_CONFIG_CHAT_ID_V1',binding.chat).replaceAll('XRAY_CONFIG_SHEET_ID_V1',binding.sheet));
    const last=/return module\.exports;\}\)\(\);\s*$/;
    if(!last.test(blocks[10]))return hold('NATIVE_INTENT_PROOF_EXPORT');
    const ai=Function(blocks[10].replace(last,'return {...module.exports, aNoteRows, aLogsFromNote};})();')+
      '\nreturn XRAY_A_IMPL;')();
    const portable=Function(rt.portable.code+'\nreturn XRAY_RESERVATION;')();
    const exact=Function(blocks[5]+'\nreturn XRAY_EXACT_EOD;')();
    const root=body(snapshot);
    if(root?.spreadsheetId!==binding.sheet||root.sheets?.length!==4)return hold('NATIVE_INTENT_SNAPSHOT');
    const schemas=[['TARAMA_KAYITLARI',26],['ADAY_GECMISI',26],['UYARI_OLAYLARI',20],['SWING_SKOR_GUNLUK',35]];
    const tabs=schemas.map(([title,width])=>{
      const t=once(root.sheets.filter(x=>x.properties?.title===title)),g=t?.properties?.gridProperties;
      const d=once(t?.data);
      if(!Number.isInteger(t?.properties?.sheetId)||g?.columnCount!==width||
         !Number.isInteger(g?.rowCount)||(d?.startRow??0)!==0||(d?.startColumn??0)!==0||
         !Array.isArray(d?.rowData)||d.rowData.length>g.rowCount)return null;
      const rows=d.rowData.map(x=>{
        const v=(x.values??[]).map(y=>y.formattedValue??'');
        while(v.length&&v.at(-1)==='')v.pop();
        return v;
      });
      if(rows.some(r=>r.length>width||r.some(x=>typeof x!=='string')))return null;
      return {id:t.properties.sheetId,rows};
    });
    if(tabs.some(t=>!t))return hold('NATIVE_INTENT_LAYOUT');
    const [scan,history,alerts]=tabs.map(t=>t.rows);
    const source={expected_asof:expectedAsof,scan,history,alerts,runResponse,jobsResponse};
    const route=ai.locateA(source);
    if(route.state!=='A_NEEDS_SOURCE')return hold(route.stage??route.state);
    const e=exact.read(runResponse,jobsResponse,route.runId);
    if(e.state!=='EXACT_EOD_INPUT')return hold(e.stage??'NATIVE_INTENT_EOD');
    const direct=ai.proveA({...source,logs});
    if(direct.state!=='A_SOURCE_VERIFIED')return hold(direct.stage??direct.state);
    const note=ai.aNoteRows(root,route);
    const compact=ai.aLogsFromNote(note,route,runResponse,e.jobs);
    if(!compact)return hold('NATIVE_INTENT_NOTE_UNVERIFIED');
    const reconstructed=ai.proveA({...source,logs:compact});
    if(reconstructed.state!==direct.state||JSON.stringify(reconstructed.verified)!==JSON.stringify(direct.verified)||
       JSON.stringify(reconstructed.held)!==JSON.stringify(direct.held))return hold('NATIVE_INTENT_A_PROOF_DRIFT');
    const selections=direct.verified.map(z=>z.row[0]);
    // Use the existing pure reservation planner only for coordinate and marker
    // parity; do not return, store, or submit its update-cell requests.
    const staged=portable.operation({kind:'event',action:'plan',sheet_id:tabs[2].id,
      asof:expectedAsof,baseline:alerts,stamp:expectedAsof+' 00:00 TRT',keys:selections});
    if(staged.status!=='PLAN_ONLY'||staged.requests.length!==2*selections.length)return hold('NATIVE_INTENT_RESERVATION_SHAPE');
    const events=direct.verified.map(({row,e:ep},i)=>{
      const named=staged.requests[i*2]?.addNamedRange?.namedRange, r=named?.range;
      const eventIndex=alerts.indexOf(row), episodeIndex=history.indexOf(ep);
      if(eventIndex<1||episodeIndex<1||r?.sheetId!==tabs[2].id||
         r.startRowIndex!==eventIndex||r.endRowIndex!==eventIndex+1||r.startColumnIndex!==17||r.endColumnIndex!==19||
         !/^XRAY_DELIVERY_[a-f0-9]{64}$/.test(named.name??''))return null;
      return {event_row:eventIndex+1,episode_row:episodeIndex+1,code:row[5],
        marker:named.name,row_sha256:hash('sha256',JSON.stringify([row,ep]))};
    });
    if(events.some(x=>!x)||new Set(events.map(x=>x.marker)).size!==events.length)return hold('NATIVE_INTENT_EVENT_BINDING');
    const fields={schema:'XRAY_477_NATIVE_A_INTENT_V1',asof:expectedAsof,source_run:e.run.id,
      source_head:e.run.head_sha,note_sha256:hash('sha256',note),events,
      authorization:'NONE',post_calls:0};
    return {...fields,state:'SOURCE_INTENT_ONLY',intent_sha256:hash('sha256',JSON.stringify(fields))};
  }catch{return hold('NATIVE_INTENT_UNVERIFIED');}
}
module.exports={buildNativeAIntent};
