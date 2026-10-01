#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATE=Path(os.getenv("XRAY_RESOLVER_STATE",str(ROOT/"canonical_current_full_state.json")))
UNKNOWNS=Path(os.getenv("XRAY_RESOLVER_UNKNOWNS",str(ROOT/"canonical_current_unknowns.json")))
OVERLAY=Path(os.getenv("XRAY_RESOLVER_OVERLAY",str(ROOT/"canonical_current_resolution_overlay.json")))
PRICE=Path(os.getenv("XRAY_RESOLVER_PRICE",str(ROOT/"canonical_current_price_dv20.json")))
POINTER=Path(os.getenv("XRAY_RESOLVER_POINTER",str(ROOT/"chatgpt_canonical_state_v2.json")))
OUT=Path(os.getenv("XRAY_RESOLVER_REQUEST_OUT",str(ROOT/"canonical_current_resolver_request.json")))
TASK="6a825366222081918997094d76e6ae46"

def blob_sha(p:Path)->str:
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def hash_lines(xs):
    return hashlib.sha256("\n".join(xs).encode()).hexdigest()

def prior_core_symbol(pointer_asof):
    candidates=[]
    cur=ROOT/"canonical_current_terminal.json"
    static=ROOT/f"canonical_terminal_{str(pointer_asof).replace('-','')}.json"
    for q in [cur,static]:
        if not q.exists(): continue
        try:
            x=json.loads(q.read_text())
            if x.get("task_id")!=TASK or x.get("asof_et")!=pointer_asof: continue
            lp=sorted(((x.get("sets") or {}).get("legal_pass") or []))
            if "MSFT" in lp: return "MSFT",str(q.relative_to(ROOT.parent)).replace("\\","/"),blob_sha(q)
            if lp: return lp[0],str(q.relative_to(ROOT.parent)).replace("\\","/"),blob_sha(q)
        except Exception:
            pass
    return None,None,None

def main():
    s=json.loads(STATE.read_text())
    u=json.loads(UNKNOWNS.read_text())
    o=json.loads(OVERLAY.read_text())
    p=json.loads(PRICE.read_text())
    ptr=json.loads(POINTER.read_text())
    ps=ptr.get("state_json") or {}
    if isinstance(ps,str):
        ps=json.loads(ps)
    assert isinstance(ps,dict)
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
    pointer_asof=str(ps.get("asof_et") or "")
    settlement_required=bool(pointer_asof and asof>pointer_asof)
    settlement_core_symbol,settlement_core_source_path,settlement_core_source_blob_sha=prior_core_symbol(pointer_asof)
    if settlement_required:
        assert settlement_core_symbol, "SETTLEMENT_PRIOR_CURRENT_CORE_UNAVAILABLE"
    bridge=ROOT/f"canonical_resolver_bridge_{asof.replace('-','')}.json"
    settlement_already_proven=False
    settlement_bridge_blob_sha=None
    if bridge.exists():
        try:
            br=json.loads(bridge.read_text())
            if (
              br.get("schema")=="XRAY_RESOLVER_EPOCH_RESULT_V1"
              and br.get("status")=="COMMITTED"
              and br.get("task_id")==TASK
              and br.get("execution")=="NONE" and br.get("real_money")=="NO-GO"
              and br.get("asof_et")==asof
              and br.get("queue_hash")==s["queue_hash"]
              and br.get("settlement_status")=="PASS"
            ):
                settlement_already_proven=True
                settlement_bridge_blob_sha=blob_sha(bridge)
        except Exception:
            pass
    ready=bool(union) or bool(settlement_required and not settlement_already_proven)
    obj={
      "schema":"XRAY_RESOLVER_EPOCH_REQUEST_V1",
      "status":"READY" if ready else "IDLE",
      "task_id":TASK,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "queue_hash":s["queue_hash"],"queue_total":len(s["queue"]),
      "pointer_asof_et":pointer_asof,
      "settlement_required":settlement_required,
      "settlement_already_proven":settlement_already_proven,
      "settlement_bridge_blob_sha":settlement_bridge_blob_sha,
      "settlement_policy":"RALLIES_VS_LONGBRIDGE_AAPL_NVDA_PLUS_ONE_PRIOR_CURRENT_CORE__PRINTED_TICK_OHLC__VOLUME_REL_DIFF_LE_0_001__FAIL_CLOSED",
      "settlement_symbols":["AAPL","NVDA",settlement_core_symbol] if settlement_required else [],
      "settlement_core_symbol":settlement_core_symbol,
      "settlement_core_source_path":settlement_core_source_path,
      "settlement_core_source_blob_sha":settlement_core_source_blob_sha,
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
      "source_pointer_path":"nasdaq-xray/chatgpt_canonical_state_v2.json",
      "source_pointer_blob_sha":blob_sha(POINTER),
      "resolver_policy":"LONG_BRIDGE_DAILY_ONLY__NEVER_G9__FAIL_CLOSED__SAME_ASOF_QUEUE_BINDING",
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"asof":asof,"pointer_asof":pointer_asof,"status":obj["status"],"settlement_required":settlement_required,"settlement_already_proven":settlement_already_proven,"master_unknown":len(master_symbols),"price_unknown":len(price_symbols),"union":len(union),"symbol_hash":obj["symbol_hash"]},sort_keys=True))

if __name__=="__main__":
    main()
