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
      "counts":dict(sorted(counts.items())),"unknown_count":len(unknown),"unknown_symbols":unknown,
      "pass_count":len(passes),"pass_symbols":passes,
      "pass_hash":hashlib.sha256("\n".join(passes).encode()).hexdigest(),
      "results":dict(sorted(results.items()))
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"reused":obj["reused_terminal_count"],"reevaluated":obj["reevaluated_count"],"counts":obj["counts"],"unknown_count":obj["unknown_count"],"pass_count":obj["pass_count"],"pass_hash":obj["pass_hash"]},sort_keys=True))
if __name__=="__main__":main()
