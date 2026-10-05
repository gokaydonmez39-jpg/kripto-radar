#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATE=Path(os.getenv("XRAY_RESOLVER_STATE",str(ROOT/"canonical_current_full_state.json")))
UNKNOWNS=Path(os.getenv("XRAY_RESOLVER_UNKNOWNS",str(ROOT/"canonical_current_unknowns.json")))
OVERLAY=Path(os.getenv("XRAY_RESOLVER_OVERLAY",str(ROOT/"canonical_current_resolution_overlay.json")))
PRICE=Path(os.getenv("XRAY_RESOLVER_PRICE",str(ROOT/"canonical_current_price_dv20.json")))
MASTER=Path(os.getenv("XRAY_MASTER_MANIFEST",str(ROOT/"canonical_current_master_manifest.json")))
POINTER=Path(os.getenv("XRAY_RESOLVER_POINTER",str(ROOT/"chatgpt_canonical_state_v2.json")))
OUT=Path(os.getenv("XRAY_RESOLVER_REQUEST_OUT",str(ROOT/"canonical_current_resolver_request.json")))
CHUNK_MANIFEST=Path(os.getenv("XRAY_RESOLVER_CHUNK_MANIFEST_OUT",str(ROOT/"canonical_current_resolver_chunk_manifest.json")))
CHUNK_SIZE=max(1,min(100,int(os.getenv("XRAY_RESOLVER_CHUNK_SIZE","100"))))
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
            eligible=[s for s in lp if s not in {"AAPL","NVDA"}]
            if eligible: return eligible[0],str(q.relative_to(ROOT.parent)).replace("\\","/"),blob_sha(q)
        except Exception:
            pass
    return None,None,None

def write_chunk_manifest(request_obj):
    # A large exact resolver scope is materialized into small content-addressed
    # chunks so provider-reader invocations can resume durably without parsing
    # one oversized request payload. Chunks carry no alpha decisions.
    for old in ROOT.glob("canonical_current_resolver_chunk_*.json"):
        if old.name!="canonical_current_resolver_chunk_manifest.json":
            old.unlink()
    symbols=list(request_obj.get("symbols") or [])
    request_blob=blob_sha(OUT)
    chunk_rows=[]
    total=(len(symbols)+CHUNK_SIZE-1)//CHUNK_SIZE
    for i in range(total):
        xs=symbols[i*CHUNK_SIZE:(i+1)*CHUNK_SIZE]
        path=ROOT/f"canonical_current_resolver_chunk_{i+1:04d}.json"
        obj={
          "schema":"XRAY_RESOLVER_REQUEST_CHUNK_V1",
          "task_id":TASK,"asof_et":request_obj["asof_et"],
          "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
          "request_path":"nasdaq-xray/canonical_current_resolver_request.json",
          "request_blob_sha":request_blob,
          "compiled_policy_blob_sha":request_obj["compiled_policy_blob_sha"],
          "compiled_policy_hash":request_obj["compiled_policy_hash"],
          "compiled_policy_version":request_obj["compiled_policy_version"],
          "queue_hash":request_obj["queue_hash"],
          "symbol_hash":request_obj["symbol_hash"],
          "chunk_index":i+1,"chunk_total":total,
          "symbol_count":len(xs),"symbols":xs,"chunk_symbol_hash":hash_lines(xs),
        }
        path.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
        chunk_rows.append({
          "chunk_index":i+1,
          "path":str(path.relative_to(ROOT.parent)).replace("\\","/"),
          "blob_sha":blob_sha(path),
          "symbol_count":len(xs),
          "chunk_symbol_hash":obj["chunk_symbol_hash"],
        })
    manifest={
      "schema":"XRAY_RESOLVER_REQUEST_CHUNK_MANIFEST_V1",
      "task_id":TASK,"asof_et":request_obj["asof_et"],
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "request_path":"nasdaq-xray/canonical_current_resolver_request.json",
      "request_blob_sha":request_blob,
      "compiled_policy_blob_sha":request_obj["compiled_policy_blob_sha"],
      "compiled_policy_hash":request_obj["compiled_policy_hash"],
      "compiled_policy_version":request_obj["compiled_policy_version"],
      "queue_hash":request_obj["queue_hash"],
      "symbol_hash":request_obj["symbol_hash"],
      "symbol_count":len(symbols),
      "chunk_size":CHUNK_SIZE,"chunk_count":total,
      "chunks":chunk_rows,
      "coverage_complete":sum(x["symbol_count"] for x in chunk_rows)==len(symbols),
    }
    CHUNK_MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    return manifest

def main():
    s=json.loads(STATE.read_text())
    u=json.loads(UNKNOWNS.read_text())
    o=json.loads(OVERLAY.read_text())
    p=json.loads(PRICE.read_text())
    m=json.loads(MASTER.read_text())
    ptr=json.loads(POINTER.read_text())
    ps=ptr.get("state_json") or {}
    if isinstance(ps,str):
        ps=json.loads(ps)
    assert isinstance(ps,dict)
    asof=s["asof_et"]
    assert s["task_id"]==u["task_id"]==o["task_id"]==p["task_id"]==m["task_id"]==TASK
    assert u["asof_et"]==p["asof_et"]==m["asof_et"]==asof and o["base_asof_et"]==asof
    assert s["execution"]==u["execution"]==o["execution"]==p["execution"]==m["execution"]=="NONE"
    assert s["real_money"]==u["real_money"]==o["real_money"]==p["real_money"]==m["real_money"]=="NO-GO"
    assert u["source_queue_hash"]==s["queue_hash"]
    assert p["source_master_queue_hash"]==s["queue_hash"]
    assert int(p["source_master_count"])==len(s["queue"])
    assert m.get("phase")=="MASTER_IDENTITY"
    assert m.get("status")=="HISTORY_COMPLETE" and int(m.get("unknown_count",-1))==0
    assert m.get("queue_hash")==s["queue_hash"] and int(m.get("queue_total",-1))==len(s["queue"])
    master_symbols=[]
    price_symbols=sorted(p.get("unknown_symbols") or [])
    assert len(price_symbols)==int(p.get("unknown_count",len(price_symbols)))
    blocked_symbols=sorted(p.get("blocked_symbols") or [])
    if "blocked_count" in p:
        assert len(blocked_symbols)==int(p.get("blocked_count",len(blocked_symbols)))
    master_detail={}
    price_detail={}
    for sym in sorted(set(price_symbols)|set(blocked_symbols)):
        price_detail[sym]={
          "security_name":(s.get("security_names") or {}).get(sym),
          "price_result":(p.get("results") or {}).get(sym),
        }
    union=sorted(set(master_symbols)|set(price_symbols)|set(blocked_symbols))
    pointer_asof=str(ps.get("asof_et") or "")
    settlement_required=bool(pointer_asof and asof>pointer_asof)
    settlement_core_symbol,settlement_core_source_path,settlement_core_source_blob_sha=prior_core_symbol(pointer_asof)
    if settlement_required:
        assert settlement_core_symbol, "SETTLEMENT_PRIOR_CURRENT_CORE_UNAVAILABLE"
    bridge_candidates=sorted(ROOT.glob(f"canonical_resolver_bridge_{asof.replace('-','')}*.json"))
    current_policy_bridges=[]
    for bridge in bridge_candidates:
        try:
            br=json.loads(bridge.read_text())
            if (
              br.get("schema")=="XRAY_RESOLVER_EPOCH_RESULT_V1"
              and br.get("status")=="COMMITTED"
              and br.get("task_id")==TASK
              and br.get("execution")=="NONE" and br.get("real_money")=="NO-GO"
              and br.get("asof_et")==asof
              and br.get("queue_hash")==s["queue_hash"]
              and br.get("compiled_policy_hash")=="26a95745a50b65e85f6ece24b6501af0994764a84ddd886edb70d1fcd770849c"
              and br.get("compiled_policy_version")=="C4.17"
              and br.get("compiled_policy_blob_sha")=="10d7af14870dfac0dc4566595d95a06f3faa854d"
              and br.get("settlement_status")=="PASS"
            ):
                current_policy_bridges.append((bridge,br))
        except Exception:
            pass
    assert len(current_policy_bridges)<=1, "AMBIGUOUS_CURRENT_POLICY_RESOLVER_BRIDGE"
    settlement_already_proven=bool(current_policy_bridges)
    settlement_bridge_blob_sha=blob_sha(current_policy_bridges[0][0]) if current_policy_bridges else None
    settlement_bridge_path=(str(current_policy_bridges[0][0].relative_to(ROOT.parent)).replace("\\","/") if current_policy_bridges else None)
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
      "settlement_bridge_path":settlement_bridge_path,
      "compiled_policy_path":"nasdaq-xray/chatgpt_compiled_policy_v3.json",
      "compiled_policy_blob_sha":"10d7af14870dfac0dc4566595d95a06f3faa854d",
      "compiled_policy_hash":"26a95745a50b65e85f6ece24b6501af0994764a84ddd886edb70d1fcd770849c",
      "compiled_policy_version":"C4.17",
      "settlement_policy":"ALPACA_HISTORICAL_SIP_DAILY_AFTER_15M__AAPL_NVDA_PLUS_ONE_PRIOR_CURRENT_CORE__RALLIES_LONGBRIDGE_QUOTE_OHLC_0_01_CROSSCHECK__SIP_VOLUME_AUTHORITY__FAIL_CLOSED__DELAYED_SIP_NEVER_G9",
      "settlement_symbols":["AAPL","NVDA",settlement_core_symbol] if settlement_required else [],
      "settlement_core_symbol":settlement_core_symbol,
      "settlement_core_source_path":settlement_core_source_path,
      "settlement_core_source_blob_sha":settlement_core_source_blob_sha,
      "official_footer":s.get("official_footer"),
      "expected20":p.get("expected20") or s.get("expected20") or [],
      "master_unknown_count":len(master_symbols),"master_unknown_symbols":master_symbols,
      "master_unknown_detail":master_detail,
      "price_unknown_count":len(price_symbols),"price_unknown_symbols":price_symbols,
      "price_blocked_count":len(blocked_symbols),"price_blocked_symbols":blocked_symbols,
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
      "source_master_path":"nasdaq-xray/canonical_current_master_manifest.json",
      "source_master_blob_sha":blob_sha(MASTER),
      "source_pointer_path":"nasdaq-xray/chatgpt_canonical_state_v2.json",
      "source_pointer_blob_sha":blob_sha(POINTER),
      "resolver_policy":"ALPACA_SIP_PREFERRED__RALLIES_LONGBRIDGE_DUAL_SOURCE_CONNECTOR_FAILOVER__NEVER_G9__FAIL_CLOSED__SAME_ASOF_QUEUE_BINDING",
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    chunks=write_chunk_manifest(obj)
    assert chunks["coverage_complete"] is True and chunks["symbol_count"]==obj["symbol_count"]
    print(json.dumps({"asof":asof,"pointer_asof":pointer_asof,"status":obj["status"],"settlement_required":settlement_required,"settlement_already_proven":settlement_already_proven,"master_unknown":len(master_symbols),"price_unknown":len(price_symbols),"price_blocked":len(blocked_symbols),"union":len(union),"symbol_hash":obj["symbol_hash"],"resolver_chunks":chunks["chunk_count"]},sort_keys=True))

if __name__=="__main__":
    main()
