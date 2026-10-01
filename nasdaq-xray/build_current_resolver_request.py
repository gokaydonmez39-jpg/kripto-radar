#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATE=Path(os.getenv("XRAY_RESOLVER_STATE",str(ROOT/"canonical_current_full_state.json")))
UNKNOWNS=Path(os.getenv("XRAY_RESOLVER_UNKNOWNS",str(ROOT/"canonical_current_unknowns.json")))
OVERLAY=Path(os.getenv("XRAY_RESOLVER_OVERLAY",str(ROOT/"canonical_current_resolution_overlay.json")))
PRICE=Path(os.getenv("XRAY_RESOLVER_PRICE",str(ROOT/"canonical_current_price_dv20.json")))
OUT=Path(os.getenv("XRAY_RESOLVER_REQUEST_OUT",str(ROOT/"canonical_current_resolver_request.json")))
TASK="6a825366222081918997094d76e6ae46"

def blob_sha(p:Path)->str:
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def hash_lines(xs):
    return hashlib.sha256("\n".join(xs).encode()).hexdigest()

def main():
    s=json.loads(STATE.read_text())
    u=json.loads(UNKNOWNS.read_text())
    o=json.loads(OVERLAY.read_text())
    p=json.loads(PRICE.read_text())
    asof=s["asof_et"]
    assert s["task_id"]==u["task_id"]==o["task_id"]==p["task_id"]==TASK
    assert u["asof_et"]==p["asof_et"]==asof and o["base_asof_et"]==asof
    assert s["execution"]==u["execution"]==o["execution"]==p["execution"]=="NONE"
    assert s["real_money"]==u["real_money"]==o["real_money"]==p["real_money"]=="NO-GO"
    assert u["source_queue_hash"]==s["queue_hash"]
    assert p["source_master_queue_hash"]==s["queue_hash"]
    assert int(p["source_master_count"])==len(s["queue"])
    master_symbols=sorted((u.get("unknowns") or {}).keys())
    price_symbols=sorted(p.get("unknown_symbols") or [])
    assert len(master_symbols)==int(u.get("unknown_count",len(master_symbols)))
    assert len(price_symbols)==int(p.get("unknown_count",len(price_symbols)))
    overlay_unresolved=o.get("unresolved") or {}
    master_detail={}
    for sym in master_symbols:
        master_detail[sym]={
          "security_name":(s.get("security_names") or {}).get(sym),
          "unknown_manifest":(u.get("unknowns") or {}).get(sym),
          "resolver_unresolved":overlay_unresolved.get(sym),
        }
    price_detail={}
    for sym in price_symbols:
        price_detail[sym]={
          "security_name":(s.get("security_names") or {}).get(sym),
          "price_result":(p.get("results") or {}).get(sym),
        }
    union=sorted(set(master_symbols)|set(price_symbols))
    obj={
      "schema":"XRAY_RESOLVER_EPOCH_REQUEST_V1",
      "status":"READY" if union else "IDLE",
      "task_id":TASK,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "queue_hash":s["queue_hash"],"queue_total":len(s["queue"]),
      "official_footer":s.get("official_footer"),
      "expected20":p.get("expected20") or s.get("expected20") or [],
      "master_unknown_count":len(master_symbols),"master_unknown_symbols":master_symbols,
      "master_unknown_detail":master_detail,
      "price_unknown_count":len(price_symbols),"price_unknown_symbols":price_symbols,
      "price_unknown_detail":price_detail,
      "symbols":union,"symbol_count":len(union),"symbol_hash":hash_lines(union),
      "source_state_path":"nasdaq-xray/canonical_current_full_state.json",
      "source_state_blob_sha":blob_sha(STATE),
      "source_unknowns_path":"nasdaq-xray/canonical_current_unknowns.json",
      "source_unknowns_blob_sha":blob_sha(UNKNOWNS),
      "source_overlay_path":"nasdaq-xray/canonical_current_resolution_overlay.json",
      "source_overlay_blob_sha":blob_sha(OVERLAY),
      "source_price_path":"nasdaq-xray/canonical_current_price_dv20.json",
      "source_price_blob_sha":blob_sha(PRICE),
      "resolver_policy":"LONG_BRIDGE_DAILY_ONLY__NEVER_G9__FAIL_CLOSED__SAME_ASOF_QUEUE_BINDING",
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"asof":asof,"status":obj["status"],"master_unknown":len(master_symbols),"price_unknown":len(price_symbols),"union":len(union),"symbol_hash":obj["symbol_hash"]},sort_keys=True))

if __name__=="__main__":
    main()
