#!/usr/bin/env python3
"""Narrow reuse of an immutable SAME-ASOF settlement witness after FAIL-only PRICE completion.

This is not a market-data fetch or settlement measurement. It never promotes
PRICE/MC/HISTORY, never supplies license entitlement, never creates alpha/R92.
The prior 3-source RTH settlement must remain unchanged. Only PASS -> identical
PASS and previous unresolved -> terminal FAIL transitions are permitted.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math

TASK="6a825366222081918997094d76e6ae46"
POLICY_HASH="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
POLICY_BLOB="16c50cc8f887a5234a4be23862d7c8d0e564b0ac"
HEX="0123456789abcdef"
SETTLEMENT=("AAPL","NVDA","MSFT")

def _lines(rows):
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()

def _ordered(rows):
    return isinstance(rows,list) and rows==sorted(set(rows)) and all(
        isinstance(x,str) and x for x in rows)

def safe_same_asof_failonly_settlement(bridge,price,master,master_blob,price_blob):
    """Return bool; an old PRICE SHA is NEVER generalized to new price authority."""
    if not all(isinstance(j,dict) for j in (bridge,price,master)):
        return False
    if not (isinstance(price_blob,str) and len(price_blob)==40
        and all(c in HEX for c in price_blob)
        and isinstance(master_blob,str) and len(master_blob)==40
        and all(c in HEX for c in master_blob)):
        return False
    asof=price.get("asof_et")
    try: dt.date.fromisoformat(asof)
    except (ValueError,TypeError):return False
    if not all(j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
               and j.get("unknown_never_pass") is True for j in (bridge,price,master)):
        return False
    if (bridge.get("schema")!="XRAY_RESOLVER_EPOCH_RESULT_V1"
        or bridge.get("status")!="COMMITTED"
        or bridge.get("bridge_role")!="CURRENT_RESIDUAL_REQUEST_AUTHORITY"
        or not (bridge.get("task_id")==price.get("task_id")==master.get("task_id")==TASK)):
        return False
    if bridge.get("task_id")!=TASK:return False
    if (bridge.get("asof_et")!=asof or master.get("asof_et")!=asof
        or bridge.get("queue_hash")!=master.get("queue_hash")
        or price.get("source_master_queue_hash")!=master.get("queue_hash")
        or bridge.get("source_master_blob_sha")!=master_blob
        or bridge.get("source_master_path")!="nasdaq-xray/canonical_current_master_manifest.json"
        or bridge.get("source_price_path")!="nasdaq-xray/canonical_current_price_dv30.json"
        or bridge.get("source_price_blob_sha")==price_blob):
        return False
    if (bridge.get("compiled_policy_version")!="C4.17"
        or bridge.get("compiled_policy_hash")!=POLICY_HASH
        or bridge.get("compiled_policy_blob_sha")!=POLICY_BLOB
        or bridge.get("settlement_status")!="PASS"
        or bridge.get("settlement_required") is not True
        or bridge.get("settlement_method")!="ALPACA_DELAYED_SIP_SNAPSHOT_DAILY_BAR_RALLIES_LONGBRIDGE_OHLC"
        or bridge.get("coverage_complete") is not True
        or bridge.get("classification_coverage_complete") is not True
        or bridge.get("pagination_complete") is not True
        or bridge.get("partial_data") is not False):
        return False
    queue=master.get("pass_symbols")
    passing=price.get("pass_symbols")
    unknown=price.get("unknown_symbols")
    blocked=price.get("blocked_symbols")
    old_scope=bridge.get("symbols")
    old_pass=bridge.get("pass_price_dv30_symbols")
    old_block=bridge.get("block_current_run")
    if not all(_ordered(x) for x in (queue,passing,unknown,blocked,old_scope,old_pass,old_block)):
        return False
    if (len(queue)!=master.get("queue_total")
        or len(queue)!=bridge.get("queue_total")
        or master.get("queue_hash")!=_lines(queue)
        or price.get("source_master_count")!=len(queue)
        or price.get("unknown_count")!=0
        or price.get("blocked_count")!=0
        or unknown!=[] or blocked!=[]
        or passing!=old_pass
        or len(passing)!=price.get("pass_count")
        or price.get("pass_hash")!=_lines(passing)
        or not old_block
        or bridge.get("symbol_count")!=len(old_scope)
        or bridge.get("price_unknown_count")!=len(old_scope)
        or old_scope!=sorted(set(old_pass)|set(old_block))
        or set(old_pass)&set(old_block)
        or not set(old_scope).issubset(queue)):
        return False
    if (bridge.get("pass_price_dv30_hash")!=_lines(old_pass)
        or bridge.get("block_hash")!=_lines(old_block)
        or bridge.get("unresolved_symbols")!=[]
        or set(bridge.get("price_resolutions") or {})!=set(old_scope)):
        return False
    for sym in old_pass:
        old=(bridge["price_resolutions"] or {}).get(sym)
        cur=(price.get("results") or {}).get(sym)
        if not isinstance(old,dict) or old.get("decision")!="PASS_PRICE_DV30":
            return False
        if not isinstance(cur,dict) or cur.get("status")!="PASS_PRICE_DV30":
            return False
    for sym in old_block:
        old=(bridge["price_resolutions"] or {}).get(sym)
        cur=(price.get("results") or {}).get(sym)
        if not isinstance(old,dict) or old.get("decision")!="BLOCK_CURRENT_RUN":
            return False
        if not isinstance(cur,dict) or cur.get("status") not in {
            "FAIL_PRICE","FAIL_DV30","FAIL_PRICE_NO_ASOF_BAR","FAIL_DV30_INSUFFICIENT_SESSIONS"
        }:
            return False
        if cur.get("status")=="FAIL_DV30_INSUFFICIENT_SESSIONS":
            info=cur.get("info") or {}
            if info.get("decision_direction")!="FAIL_ONLY_NEVER_PASS" or info.get("no_synthetic_bar") is not True:
                return False
    if (bridge.get("settlement_symbols")!=list(SETTLEMENT)
        or not set(SETTLEMENT).issubset(passing)
        or bridge.get("settlement_evidence") is None):
        return False
    ev=bridge["settlement_evidence"]
    if set(ev)!=set(SETTLEMENT):
        return False
    for sym in SETTLEMENT:
        v=ev[sym]
        if not isinstance(v,dict):return False
        ohlc=v.get("ohlc")
        if not isinstance(ohlc,list) or len(ohlc)!=4 or not all(
            isinstance(q,(float,int)) and not isinstance(q,bool) and math.isfinite(q) and q>0 for q in ohlc):
            return False
        op,high,low,cl=ohlc
        if not (low<=op<=high and low<=cl<=high):return False
        for k in ("alpaca_volume","rallies_volume","longbridge_volume"):
            z=v.get(k)
            if not isinstance(z,(int,float)) or isinstance(z,bool) or not math.isfinite(z) or z<=0:
                return False
        if v.get("longbridge_trade_status")!="Normal":
            return False
        stamp=v.get("longbridge_rth_close_timestamp")
        if not isinstance(stamp,str) or not stamp.startswith(asof+"T"):
            return False
    return True

def selftest():
    print("XRAY_SAME_ASOF_SETTLEMENT_REBIND_MODULE_LOAD=PASS_FAIL_ONLY_NO_PROVIDER")
if __name__=="__main__":
    selftest()
