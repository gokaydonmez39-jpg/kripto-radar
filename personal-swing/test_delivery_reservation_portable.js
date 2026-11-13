"use strict";
const assert=require("node:assert/strict");
const {execFileSync}=require("node:child_process");
const {createHash}=require("node:crypto");
const {test}=require("node:test");
const fs=require("node:fs");
const vm=require("node:vm");
const portable=require("./delivery_reservation_portable");
const python=process.env.PYTHON || "python3";
const cmd=(args,input)=>execFileSync(python,args,{input:input===undefined?undefined:JSON.stringify(input),encoding:"utf8"});
const fixtures=JSON.parse(cmd(["-c",`
import json
import test_delivery_reservation as t
print(json.dumps([dict(action='plan',kind='event',sheet_id=17,asof=t.DAY,stamp=t.STAMP,baseline=t.events(),keys=[t.EID]),dict(action='plan',kind='digest',sheet_id=33,asof=t.DAY,stamp=t.STAMP,baseline=t.scores(),verified_sha='a'*64)]))
`]));
function py(input){
  try{return JSON.parse(cmd(["delivery_reservation.py"],input));}
  catch(e){assert.equal(e.status,2);return JSON.parse(e.stdout);}
}
function proof(input){
  const req=portable.operation(input).requests;
  const observed=structuredClone(input.baseline);
  const replies=[];
  for(const x of req){
    if(x.addNamedRange){replies.push(x);continue;}
    const {start:{rowIndex,columnIndex},rows}=x.updateCells;
    observed[rowIndex].splice(columnIndex,2,...rows[0].values.map(x=>x.userEnteredValue.stringValue));
    replies.push({});
  }
  return {...input,action:"verify",observed,response:{spreadsheetId:"fixture",replies},spreadsheet_id:"fixture"};
}
test("isolated V8 without Node or WebCrypto matches both Python plans",()=>{
  const ctx={input:fixtures[0]};
  const code=fs.readFileSync(require.resolve("./delivery_reservation_portable"),"utf8");
  const out=vm.runInNewContext(code+"\nJSON.stringify(XRAY_RESERVATION.operation(input));",ctx);
  assert.deepEqual(JSON.parse(out),py(fixtures[0]));
  for(const input of fixtures)assert.deepEqual(portable.operation(input),py(input));
});
test("identical POST receipt, readback and anti-replay decisions",()=>{
  for(const input of fixtures){
    const v=proof(input);
    for(const sample of [
      v,{...v,response:null},{...v,spreadsheet_id:"wrong"},
      {...v,observed:v.observed.map((r,i)=>i===1?r.map((c,j)=>j===6?"tampered":c):r)},
      {...v,response:{...v.response,replies:[{},{}]}},
      {...input,baseline:v.observed},{...input,stamp:"2026-11-13 25:00 TRT"},
      {...input,asof:"2026-02-30"},{...input,baseline:[input.baseline[0],...input.baseline.slice(1),input.baseline[1]]},
    ])assert.deepEqual(portable.operation(sample),py(sample));
  }
});
test("UTF-8 SHA and producer float canonicalization match Python",()=>{
  for(const x of ["","abc","örnek 🦖", "A".repeat(140)])
    assert.equal(portable.sha256(x),createHash("sha256").update(x).digest("hex"));
  const rows=[["2026-11-12|TEST","59.0","RİSK","101.000"],["2026-11-11|TEST","81.2","NORMAL","0.0001"],["2026-11-10|TEST","","HOLD",""],["2026-11-09|TEST","-0.0","HOLD","0"]];
  const expected=cmd(["-c",`
import hashlib,sys,json
rows=json.load(sys.stdin)
r=[(k,float(s) if s else '',tag,float(c) if c else '') for k,s,tag,c in rows]
p=dict(asof='2026-11-12',source='a',policy='b',version='v',rows=r)
print(hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest())
`],rows).trim();
  assert.equal(portable.scoreDigest("2026-11-12","a","b",rows,"v"),expected);
  assert.throws(()=>portable.scoreDigest("2026-11-12","a","b",[["x","1e-7","y",""]],"v"));
});
