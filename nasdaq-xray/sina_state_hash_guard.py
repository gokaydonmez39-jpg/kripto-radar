#!/usr/bin/env python3
"""Deterministic, locally verifiable Sina root-state hash; not market authority."""
from __future__ import annotations
import copy
import hashlib
import json

VERSION="SHA256_DETERMINISTIC_WITHOUT_SELF_FIELD_V1"

def compute(state):
    if not isinstance(state,dict):
        raise ValueError("SINA_STATE_NOT_OBJECT")
    source={k:v for k,v in state.items() if k!="state_hash"}
    return hashlib.sha256(json.dumps(
        source,sort_keys=True,separators=(",",":"),
        ensure_ascii=True).encode("utf-8")).hexdigest()

def seal(state):
    if not isinstance(state,dict):
        raise ValueError("SINA_STATE_NOT_OBJECT")
    state["state_hash_version"]=VERSION
    state["state_hash"]=compute(state)
    return state

def verify(state):
    if not isinstance(state,dict):
        return "INVALID_STRUCTURE"
    if state.get("state_hash_version")!=VERSION:
        return "LEGACY_HASH_NOT_INDEPENDENTLY_VERIFIABLE"
    h=state.get("state_hash")
    if not isinstance(h,str) or len(h)!=64:
        return "CURRENT_HASH_MISSING_OR_MALFORMED"
    return "PASS_DETERMINISTIC_BLOB_INTERNAL" if h==compute(state) else "CURRENT_HASH_MISMATCH"

def selftest():
    base={"schema":"XRAY_NASDAQ_SCREENER_SINA_V2","asof_et":"2026-10-09",
          "results":{"AAPL":{"status":"PASS"}}, "execution":"NONE",
          "real_money":"NO-GO","unknown_never_pass":True}
    s=seal(copy.deepcopy(base))
    assert verify(s)=="PASS_DETERMINISTIC_BLOB_INTERNAL"
    assert compute(s)==s["state_hash"]
    assert seal(s)["state_hash"]==compute(s)
    assert seal(s)["state_hash"]==seal(copy.deepcopy(s))["state_hash"]
    bad=copy.deepcopy(s)
    bad["results"]["AAPL"]["status"]="UNKNOWN_STATIC"
    assert verify(bad)=="CURRENT_HASH_MISMATCH"
    bad=copy.deepcopy(s);bad["state_hash"]="0"*64
    assert verify(bad)=="CURRENT_HASH_MISMATCH"
    bad=copy.deepcopy(s);bad.pop("state_hash")
    assert verify(bad)=="CURRENT_HASH_MISSING_OR_MALFORMED"
    bad=copy.deepcopy(s);bad.pop("state_hash_version")
    assert verify(bad)=="LEGACY_HASH_NOT_INDEPENDENTLY_VERIFIABLE"
    assert verify([])=="INVALID_STRUCTURE"
    print("XRAY_SINA_STATE_HASH_SELFTEST=PASS_DETERMINISTIC_REPEATED_SEAL_5_NEGATIVES_NO_AL")

if __name__=="__main__":
    selftest()
