#!/usr/bin/env python3
"""Rights-gated, one-call Massive grouped EOD sample; no canonical promotion."""
import argparse,json,math,os,urllib.request
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def inspect(obj,asof,symbols):
    if obj.get("status")!="OK" or not isinstance(obj.get("results"),list):raise ValueError("INVALID_STATUS")
    present=set();valid=set()
    for r in obj["results"]:
        s=r.get("T")
        if not isinstance(s,str) or s in present:raise ValueError("INVALID_SYMBOL")
        present.add(s)
        vals=[]
        for k in ("o","h","l","c","v"):
            v=float(r[k])
            if not math.isfinite(v) or v<0:raise ValueError("BAD_NUMBER")
            vals.append(v)
        o,h,l,c,v=vals
        if min(o,h,l,c)<=0 or h<max(o,c,l) or l>min(o,c):raise ValueError("BAD_OHLC")
        if datetime.fromtimestamp(int(r["t"])/1000,timezone.utc).date().isoformat()!=asof:raise ValueError("ASOF_MISMATCH")
        if v>0:valid.add(s)
    return {"all_market_rows":len(present),"scope_count":len(symbols),
            "scope_covered":len(set(symbols)&valid),"scope_complete":set(symbols)<=valid}
def probe(price,key,licensed,proof,transport=None):
    asof=price["asof_et"];scope=price["pass_symbols"]
    assert price["execution"]=="NONE" and price["real_money"]=="NO-GO"
    assert len(scope)==price["pass_count"] and len(scope)==len(set(scope))
    out={"schema":"XRAY_MASSIVE_GROUPED_EOD_SHADOW_V1","asof_et":asof,
         "status":"BLOCKED_RIGHTS_OR_KEY","calls":0,"scope_count":len(scope),
         "all_market_rows":0,"scope_covered":0,"scope_complete":False,
         "HISTORY_PASS":False,"MC_PASS":False,"R92_AL":False,
         "source_independent_of_RALLIES":False,
         "vendor_bars_persisted":False,"execution":"NONE","real_money":"NO-GO"}
    if not (key and licensed=="true" and len(proof)==64):
        return out
    out["calls"]=1
    try:
        if transport is None:
            u="https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/"+asof+"?adjusted=true&include_otc=false"
            req=urllib.request.Request(u,headers={"Authorization":"Bearer "+key})
            with urllib.request.urlopen(req,timeout=22) as f: obj=json.loads(f.read(7000000))
        else:obj=transport()
        counts=inspect(obj,asof,scope);out.update(counts)
        out["status"]="ONE_DAY_COMPLETE_SHADOW_ONLY" if counts["scope_complete"] else "BLOCKED_SCOPE_NOT_COMPLETE"
    except Exception:out["status"]="BLOCKED_VENDOR_RESPONSE"
    return out
def selftest():
    asof="2026-10-08";ms=1791489600000
    p={"asof_et":asof,"pass_symbols":["AAPL","FSLY"],"pass_count":2,"execution":"NONE","real_money":"NO-GO"}
    a={"status":"OK","results":[{"T":x,"o":20,"h":21,"l":19,"c":20,"v":12.5,"t":ms} for x in ("AAPL","FSLY")]}
    assert probe(p,"","","")["calls"]==0
    ok=probe(p,"example","true","a"*64,lambda:a)
    assert ok["scope_complete"] and not ok["R92_AL"] and not ok["source_independent_of_RALLIES"]
    from copy import deepcopy
    for k,v in (("h",10),("l",22),("v",-1),("t",ms+86400000)):
        bad=deepcopy(a);bad["results"][0][k]=v
        assert probe(p,"example","true","a"*64,lambda bad=bad:bad)["status"]=="BLOCKED_VENDOR_RESPONSE"
    no=deepcopy(a);no["results"].pop()
    assert probe(p,"example","true","a"*64,lambda:no)["status"]=="BLOCKED_SCOPE_NOT_COMPLETE"
    print("XRAY_MASSIVE_GROUPED_BASIC_SELFTEST=PASS_5_NEGATIVES_NO_ALPHA")
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--selftest",action="store_true");ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:selftest()
    else:
        if not args.out or args.out.resolve().is_relative_to(ROOT.parent.resolve()):ap.error("private output only")
        price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
        doc=probe(price,os.getenv("XRAY_MASSIVE_API_KEY",""),
                  os.getenv("XRAY_MASSIVE_NONDISPLAY_LICENSE_OK",""),
                  os.getenv("XRAY_MASSIVE_LICENSE_EVIDENCE_SHA256",""))
        args.out.write_text(json.dumps(doc,sort_keys=True)+"\n")
        print("XRAY_MASSIVE_GROUPED_PROBE="+doc["status"])
