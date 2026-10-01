#!/usr/bin/env python3
from __future__ import annotations
import json, os, hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from price_dv20_phase import eval_one, expected20

ROOT=Path(__file__).resolve().parent
INPUT=Path(os.getenv("XRAY_FULLSTATE_INPUT",str(ROOT/"canonical_full_hard_gate_20260930_state.json")))
OUT=Path(os.getenv("XRAY_PRICE_DV20_RECOVER_OUT",str(ROOT/"canonical_price_dv20_20260930.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_PHASE_WORKERS","12"))
HARD_PRICE=10.0
HARD_DV20=50_000_000.0


def num(x):
    try:
        v=float(x)
        return v if v==v and abs(v)!=float("inf") else None
    except Exception:
        return None

def load_exception_bridge(asof,queue_hash):
    path=ROOT/f"canonical_resolver_bridge_{asof.replace('-','')}.json"
    if not path.exists():
        return {},{"status":"ABSENT","path":str(path)}
    try:
        obj=json.loads(path.read_text())
        if obj.get("schema")!="XRAY_RESOLVER_EPOCH_RESULT_V1" or obj.get("status")!="COMMITTED":
            raise ValueError("SCHEMA_OR_STATUS")
        if obj.get("task_id")!=TASK_ID or obj.get("execution")!="NONE" or obj.get("real_money")!="NO-GO":
            raise ValueError("SAFETY_OR_TASK")
        if obj.get("asof_et")!=asof or obj.get("queue_hash")!=queue_hash:
            raise ValueError("BINDING")
        prs=obj.get("price_resolutions") or {}
        if not isinstance(prs,dict): raise ValueError("PRICE_RESOLUTIONS")
        return prs,{"status":"PASS","path":str(path),"symbol_hash":obj.get("symbol_hash"),"source_result_task_id":obj.get("source_result_task_id")}
    except Exception as e:
        return {},{"status":"INVALID","path":str(path),"reason":f"{type(e).__name__}:{str(e)[:160]}"}

def valid_bridge_price_resolution(x,asof):
    if not isinstance(x,dict): return False
    d=x.get("decision")
    px=num(x.get("price"))
    if d=="FAIL_PRICE":
        return px is not None and px<=HARD_PRICE and bool(x.get("source")) and bool(x.get("proof"))
    if d=="FAIL_DV20":
        dv=num(x.get("dv20"))
        if dv is not None:
            return px is not None and px>HARD_PRICE and dv<HARD_DV20 and bool(x.get("source")) and bool(x.get("proof"))
        n=x.get("observed_completed_sessions")
        return (
          px is not None and px>HARD_PRICE and isinstance(n,int) and 0<=n<20
          and x.get("reason")=="EXACT20_INSUFFICIENT_LISTED_SESSIONS"
          and x.get("no_synthetic_bar") is True and bool(x.get("source")) and bool(x.get("proof"))
        )
    if d=="PASS_PRICE_DV20":
        dv=num(x.get("dv20")); known=x.get("known_session_count")
        return (
          px is not None and px>HARD_PRICE and dv is not None and dv>=HARD_DV20
          and known==20 and x.get("no_synthetic_bar") is True
          and bool(x.get("source")) and bool(x.get("proof"))
        )
    if d=="BLOCK_CURRENT_RUN":
        return x.get("trade_status")=="Halted" and bool(x.get("last_bar")) and bool(x.get("source"))
    if d=="BLOCK_POST_ASOF_LISTING":
        return bool(x.get("first_trade_date")) and str(x.get("first_trade_date"))>asof and bool(x.get("source"))
    return False

def main():
    s=json.loads(INPUT.read_text())
    asof=s.get("asof_et")
    assert s["task_id"]==TASK_ID and isinstance(asof,str) and len(asof)==10
    queue=s["queue"];old=s["results"];assert len(queue)==len(old) and len(queue)>3000
    results={};redo=[]
    for sym in queue:
        r=old[sym];st=r.get("status");info=r.get("info")
        if st=="PASS":
            results[sym]={"status":"PASS_PRICE_DV20","info":info,"provenance":"FULLSTATE_TERMINAL_PASS"}
        elif st=="FAIL_PRICE":
            results[sym]={"status":"FAIL_PRICE","info":info,"provenance":"FULLSTATE_TERMINAL_FAIL"}
        elif st=="FAIL_DV20":
            results[sym]={"status":"FAIL_DV20","info":info,"provenance":"FULLSTATE_TERMINAL_FAIL"}
        else:
            redo.append(sym)
    exp20=expected20(asof)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(eval_one,sym,exp20,asof):sym for sym in redo}
        for fut in as_completed(futs):
            sym,st,info,meta=fut.result()
            results[sym]={"status":st,"info":info,"provider_meta":meta,"provenance":"POLICY_ORDER_REEVALUATION"}
    bridge_price,exception_bridge_meta=load_exception_bridge(asof,s["queue_hash"])
    for sym,br in sorted(bridge_price.items()):
        if sym not in results or results[sym].get("status")!="UNKNOWN":
            continue
        if not valid_bridge_price_resolution(br,asof):
            continue
        st=br["decision"]
        results[sym]={
          "status":st,
          "info":{k:v for k,v in br.items() if k!="decision"},
          "provenance":"LONG_BRIDGE_TASKSTATE_RESOLVER_BRIDGE",
        }

    counts={}
    for r in results.values():counts[r["status"]]=counts.get(r["status"],0)+1
    unknown=sorted(s for s,r in results.items() if r["status"]=="UNKNOWN")
    passes=sorted(s for s,r in results.items() if r["status"]=="PASS_PRICE_DV20")
    obj={
      "schema":"XRAY_CANONICAL_PRICE_DV20_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "source_master_queue_hash":s["queue_hash"],"source_master_count":len(queue),
      "expected20":exp20,"gate_order":["PRICE","DV20"],"thresholds":{"price":">10","dv20":">=50000000 exact20 median"},
      "reused_terminal_count":len(queue)-len(redo),"reevaluated_count":len(redo),
      "exception_bridge_meta":exception_bridge_meta,
      "counts":dict(sorted(counts.items())),"unknown_count":len(unknown),"unknown_symbols":unknown,
      "pass_count":len(passes),"pass_symbols":passes,
      "pass_hash":hashlib.sha256("\n".join(passes).encode()).hexdigest(),
      "results":dict(sorted(results.items()))
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"reused":obj["reused_terminal_count"],"reevaluated":obj["reevaluated_count"],"counts":obj["counts"],"unknown_count":obj["unknown_count"],"pass_count":obj["pass_count"],"pass_hash":obj["pass_hash"]},sort_keys=True))
if __name__=="__main__":main()
