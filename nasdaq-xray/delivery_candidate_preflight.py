#!/usr/bin/env python3
"""Zero-alpha, fail-closed registered R92 presence preflight.

Distinguish the *absence of any registered candidate* from a stale root
scheduler. Scheduler readiness is STILL mandatory whenever R92 is nonempty.
This does not validate a candidate or authorize delivery.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TASK="6a825366222081918997094d76e6ae46"

def classify(pointer:dict)->str:
    if not isinstance(pointer,dict):
        raise ValueError("POINTER_NOT_OBJECT")
    if (pointer.get("schema")!="XRAY_GITHUB_DURABLE_STATE_V3"
            or pointer.get("authority")!="GITHUB_CURRENT_POINTER"
            or pointer.get("execution")!="NONE"
            or pointer.get("real_money")!="NO-GO"):
        raise ValueError("POINTER_AUTHORITY_OR_SAFETY_UNVERIFIED")
    state=pointer.get("state_json")
    if isinstance(state,str):
        state=json.loads(state)
    if not isinstance(state,dict) or state.get("task_id")!=TASK:
        raise ValueError("POINTER_CANONICAL_STATE_INVALID")
    if state.get("execution") not in (None,"NONE") or state.get("real_money") not in (None,"NO-GO"):
        raise ValueError("POINTER_STATE_SAFETY_UNVERIFIED")
    r92=state.get("r92")
    keys=state.get("delivery_keys")
    if not isinstance(r92,list) or not isinstance(keys,list):
        raise ValueError("R92_REGISTRY_OR_DELIVERY_KEYS_INVALID")
    if any(not isinstance(k,str) or not k for k in keys) or len(keys)!=len(set(keys)):
        raise ValueError("DELIVERY_KEY_COLLECTION_INVALID")
    if not r92:
        # Old CONTROL and NO_CONFIRMED_SETUP keys do not indicate a real R92.
        return "NO_REGISTERED_R92"
    for row in r92:
        if not isinstance(row,dict) or row.get("schema")!="XRAY_RESEARCH_CANDIDATE_R92_V1":
            raise ValueError("MALFORMED_R92_REGISTRY")
        if row.get("execution")!="NONE" or row.get("real_money")!="NO-GO":
            raise ValueError("R92_SAFETY_UNVERIFIED")
        if row.get("delivery_key") not in keys:
            raise ValueError("R92_KEY_NOT_REGISTERED")
    return "REGISTERED_R92_REQUIRES_FULL_SCHEDULER_AND_DELIVERY_GATES"

def selftest():
    import copy
    base={"schema":"XRAY_GITHUB_DURABLE_STATE_V3","authority":"GITHUB_CURRENT_POINTER",
          "execution":"NONE","real_money":"NO-GO",
          "state_json":{"task_id":TASK,"r92":[],"delivery_keys":["CONTROL|TEST"]}}
    assert classify(base)=="NO_REGISTERED_R92"
    p=copy.deepcopy(base);p["state_json"]["r92"]=[{
        "schema":"XRAY_RESEARCH_CANDIDATE_R92_V1",
        "delivery_key":"R92|TEST","execution":"NONE","real_money":"NO-GO"
    }];p["state_json"]["delivery_keys"].append("R92|TEST")
    assert classify(p)=="REGISTERED_R92_REQUIRES_FULL_SCHEDULER_AND_DELIVERY_GATES"
    from copy import deepcopy
    cases=[
        lambda x:x.update(authority="UNKNOWN"),
        lambda x:x.update(execution="TRADE"),
        lambda x:x["state_json"].update(task_id="MALICIOUS"),
        lambda x:x["state_json"].update(r92=""),
        lambda x:x["state_json"].update(delivery_keys=None),
        lambda x:x["state_json"].update(delivery_keys=["DUP","DUP"]),
        lambda x:x["state_json"].update(r92=[{"schema":"UNKNOWN"}]),
        lambda x:x["state_json"].update(r92=[{
            "schema":"XRAY_RESEARCH_CANDIDATE_R92_V1",
            "delivery_key":"FORGED","execution":"NONE","real_money":"NO-GO"}]),
    ]
    for i,fn in enumerate(cases):
        x=deepcopy(base);fn(x)
        try:classify(x)
        except (ValueError,TypeError,KeyError):pass
        else:raise AssertionError("R92_PREFLIGHT_INVALID_ACCEPTED:"+str(i))
    print("XRAY_DELIVERY_CANDIDATE_PREFLIGHT_SELFTEST=PASS_REAL_R92_FENCED_8_NEGATIVES")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--pointer",type=Path,default=ROOT/"chatgpt_canonical_state_v2.json")
    args=ap.parse_args()
    if args.selftest:
        selftest();return
    pointer=json.loads(args.pointer.read_text(encoding="utf-8"))
    result=classify(pointer)
    print("XRAY_DELIVERY_CANDIDATE_PREFLIGHT="+result)
    print("XRAY_DELIVERY_R92_PRESENT="+str(result.startswith("REGISTERED")).lower())
    print("XRAY_DELIVERY_NO_ALPHA_OR_DEVICE_RECEIPT=TRUE")
if __name__=="__main__":
    main()
