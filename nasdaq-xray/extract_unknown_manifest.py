#!/usr/bin/env python3
from __future__ import annotations
import json, os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
INPUT=Path(os.getenv("XRAY_UNKNOWN_SOURCE",str(ROOT/"canonical_current_full_state.json")))
OUT=Path(os.getenv("XRAY_UNKNOWN_OUT",str(ROOT/"canonical_current_unknowns.json")))
TASK="6a825366222081918997094d76e6ae46"

def main():
    s=json.loads(INPUT.read_text())
    assert s["task_id"]==TASK
    unknowns={}
    for sym,r in sorted((s.get("results") or {}).items()):
        st=str(r.get("status") or "")
        if not st.startswith("UNKNOWN"): continue
        unknowns[sym]={
          "status":st,
          "attempts":r.get("attempts"),
          "info":r.get("info"),
          "security_name":(s.get("security_names") or {}).get(sym),
          "discovery":(s.get("discovery") or {}).get(sym),
        }
    by_status={};by_reason={}
    for r in unknowns.values():
        by_status[r["status"]]=by_status.get(r["status"],0)+1
        info=r.get("info")
        reason=info.get("reason") if isinstance(info,dict) else str(info)
        reason=str(reason)
        by_reason[reason]=by_reason.get(reason,0)+1
    obj={
      "schema":"XRAY_CANONICAL_UNKNOWN_MANIFEST_V2","task_id":TASK,
      "asof_et":s["asof_et"],"execution":"NONE","real_money":"NO-GO",
      "source_state_hash":s.get("state_hash"),"source_queue_hash":s.get("queue_hash"),
      "source_unknown_count":s.get("unknown_count"),"source_counts":s.get("counts"),
      "official_footer":s.get("official_footer"),"unknown_count":len(unknowns),
      "by_status":dict(sorted(by_status.items())),"by_reason":dict(sorted(by_reason.items())),
      "unknowns":unknowns
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"asof":obj["asof_et"],"unknown_count":len(unknowns),"by_status":obj["by_status"]},sort_keys=True))
if __name__=="__main__": main()
