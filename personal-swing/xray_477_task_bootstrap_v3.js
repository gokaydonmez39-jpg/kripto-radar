function xrayGitBlobSha(source){
 const enc=encodeURIComponent(source), raw=[];
 for(let i=0;i<enc.length;i++){if(enc[i]==="%"){raw.push(parseInt(enc.slice(i+1,i+3),16));i+=2;}else raw.push(enc.charCodeAt(i));}
 const b=[...Array.from("blob "+raw.length+"\0",c=>c.charCodeAt(0)),...raw],l=b.length*8;
 b.push(128);while(b.length%64!==56)b.push(0);for(let k=7;k>=0;k--)b.push(Math.floor(l/256**k)&255);
 let h=[0x67452301,0xefcdab89,0x98badcfe,0x10325476,0xc3d2e1f0];
 const rot=(x,n)=>(x<<n)|(x>>>(32-n));
 for(let j=0;j<b.length;j+=64){const w=[];for(let i=0;i<16;i++){const p=j+4*i;w[i]=(b[p]<<24)|(b[p+1]<<16)|(b[p+2]<<8)|b[p+3];}
  for(let i=16;i<80;i++)w[i]=rot(w[i-3]^w[i-8]^w[i-14]^w[i-16],1);
  let [a,c,d,e,f]=h;for(let i=0;i<80;i++){const g=i<20?(c&d)|(~c&e):i<40?c^d^e:i<60?(c&d)|(c&e)|(d&e):c^d^e;
   const k=i<20?0x5a827999:i<40?0x6ed9eba1:i<60?0x8f1bbcdc:0xca62c1d6;
   const t=(rot(a,5)+g+f+k+w[i])|0; f=e;e=d;d=rot(c,30);c=a;a=t;}
  h=h.map((q,i)=>(q+[a,c,d,e,f][i])|0);}
 return h.map(q=>(q>>>0).toString(16).padStart(8,"0")).join("");
}
async function xrayTaskEntry(expected_asof, T, inventory, binding, mode="AB") {
 const HOLD=stage=>({state:"HOLD",stage,post_calls:0});
 const all=new Set((inventory??[]).map(k=>typeof k==="string"?k:k?.name));
 const pick=arr=>arr.find(k=>typeof T?.[k]==="function"&&(!all.size||all.has(k)));
 const peek=pick(["mcp__codex_apps__automations_peek","mcp__Automations__peek"]);
 const github=pick(["mcp__codex_apps__github_fetch","mcp__GitHub__fetch"]);
 const uuid=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
 const sha=/^[0-9a-f]{40}$/;
 if(!/^[0-9a-f]{32}$/i.test(binding?.id??"")||!uuid.test(binding?.chat??"")||!/^[A-Za-z0-9_-]{30,70}$/.test(binding?.sheet??"")||!sha.test(binding?.commit??"")||!sha.test(binding?.blob??""))return HOLD("ENTRY_BINDING_INVALID");
 if(!peek||!github)return HOLD("ENTRY_READ_TOOL_UNAVAILABLE");
 const r="gokaydonmez39-jpg/kripto-radar";
 const url="https://api.github.com/repos/"+r+"/git/blobs/"+binding.blob;
 let input, raw;
 try{[input,raw]=await Promise.all([T[peek]({jawbone_id:binding.id}),T[github]({url})]);}
 catch{return HOLD("ENTRY_READ_EXCEPTION");}
 const open=(o,match)=>{for(let k=0;k<6&&o&&typeof o==="object"&&!o.isError;k++){if(match(o))return o;o=o.structuredContent??o.result??null;}return null;};
 const a=open(input,x=>Array.isArray(x.automations))?.automations?.filter(x=>x.id===binding.id);
 if(a?.length!==1||a[0].conversation_id!==binding.chat||!a[0].is_enabled)return HOLD("ENTRY_LIVE_TASK_UNVERIFIED");
 const lines=a[0].prompt?.split("\n")??[];
 if(lines.filter(l=>l.startsWith("XRAY_RUNTIME_PIN_V1=")).length!==1||!lines.includes("XRAY_RUNTIME_PIN_V1="+binding.commit+"|"+binding.blob)||
    lines.filter(l=>l.startsWith("XRAY_RUNTIME_BINDING_V1=")).length!==1||!lines.includes("XRAY_RUNTIME_BINDING_V1="+[binding.id,binding.chat,binding.sheet].join("|")))return HOLD("ENTRY_LIVE_TASK_UNVERIFIED");
 const rec=open(raw,o=>typeof o.content==="string"&&typeof o.url==="string");
 if(rec?.url!==url||rec?.title!==binding.blob||xrayGitBlobSha(rec.content)!==binding.blob)return HOLD("ENTRY_RELEASE_PIN_UNVERIFIED");
 let entry;
 try{
  const v=JSON.parse(rec.content);
  if(v?.schema!=="XRAY_NASDAQ_477_RUNTIME_V3"||v.blocks?.length!==12||v.blocks.some(x=>typeof x!=="string")||v.portable?.blob!=="1586498cd9c390b5eb3935261f90545d3e3b06f6"||typeof v.portable.code!=="string"||xrayGitBlobSha(v.portable.code)!==v.portable.blob)return HOLD("ENTRY_RELEASE_SCHEMA");
  const parts=v.blocks.map(b=>b.replaceAll("XRAY_CONFIG_TASK_ID_V1",binding.id).replaceAll("XRAY_CONFIG_CHAT_ID_V1",binding.chat).replaceAll("XRAY_CONFIG_SHEET_ID_V1",binding.sheet));
  const __xrayBlocks=x=>{if(x!==a[0].prompt)throw Error("LIVE_PROMPT_DRIFT");return parts.slice();};
  const __xrayPortable=()=>v.portable.code;
  const __xrayCompile=src=>()=>Function("__xrayCompile","__xrayBlocks","__xrayPortable",src)(__xrayCompile,__xrayBlocks,__xrayPortable);
  if(mode==="C_HELPER")return {state:"C_HELPER_READY",helper:__xrayCompile(parts[9]+"\nreturn XRAY_C_OPEN;")()};
  if(mode!=="AB")return HOLD("ENTRY_MODE_UNVERIFIED");
  entry=__xrayCompile(parts[0]+"\nreturn executeRecordedAB;")();
 }catch{return HOLD("ENTRY_RELEASE_COMPILE_UNVERIFIED");}
 return await entry(expected_asof,T,inventory,input);
}
