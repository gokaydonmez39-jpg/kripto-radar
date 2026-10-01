#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MC=ROOT/"canonical_mc_20260930_v2.json"
H=ROOT/"canonical_history_20260930.json"
TASK="6a825366222081918997094d76e6ae46"
ASOF="2026-09-30"
def main():
    mc=json.loads(MC.read_text()); h=json.loads(H.read_text())
    assert mc["schema"]=="XRAY_CANONICAL_MC_20260930_V2"
    assert mc["task_id"]==TASK and mc["asof_et"]==ASOF
    assert mc["counts"]=={"MC_PASS_PRIMARY":456,"MC_FAIL_PRIMARY":13,"MC_PASS_FALLBACK_WATCH":35,"MC_UNKNOWN":0,"TOTAL":504}
    primary=sorted(mc["primary_pass_symbols"]); watch=sorted(mc["fallback_watch_symbols"])
    assert len(primary)==456 and len(set(primary))==456
    assert len(watch)==35 and len(set(watch))==35 and not (set(primary)&set(watch))
    results={s:h["results"][s] for s in primary}
    passed=sorted(s for s in primary if results[s].get("status")=="PASS_HISTORY")
    failed=sorted(s for s in primary if results[s].get("status")=="FAIL_HISTORY")
    unknown=sorted(s for s in primary if str(results[s].get("status","")).startswith("UNKNOWN"))
    assert len(passed)==442 and len(failed)==14 and not unknown
    assert set(passed)|set(failed)==set(primary)
    out=dict(h)
    out.update({
      "schema":"XRAY_CANONICAL_HISTORY_V2","task_id":TASK,"asof_et":ASOF,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "source_mc_artifact":"nasdaq-xray/canonical_mc_20260930_v2.json",
      "input_count":456,"counts":{"FAIL_HISTORY":14,"PASS_HISTORY":442},
      "pass_count":442,"pass_hash":hashlib.sha256("\n".join(passed).encode()).hexdigest(),
      "pass_symbols":passed,"unknown_count":0,"unknown_symbols":[],
      "state_caps":{s:"NORMAL" for s in primary},"r92_ineligible":[],"results":results,
      "c4_14_scope":{
        "mode":"MC_PRIMARY_PASS_ONLY","primary_input_count":456,
        "primary_history_pass_count":442,"primary_history_fail_count":14,
        "fallback_watch_excluded_count":35,"fallback_watch_symbols":watch,
        "fallback_watch_remains_watch_only":True,"fallback_watch_r92_eligible":False
      }
    })
    H.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"input":456,"pass":442,"fail":14,"unknown":0,"fallback_watch_excluded":35,"pass_hash":out["pass_hash"]},sort_keys=True))
if __name__=="__main__": main()
