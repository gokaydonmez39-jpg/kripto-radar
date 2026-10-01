#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, pathlib, sys

ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

from price_dv20_phase import classify as price_classify
from resolve_unknowns_fallback import classify as resolver_classify

def load_sina():
    spec=importlib.util.spec_from_file_location("sina_stage_test",ROOT/"sina_stage.py")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def bars(dates, price=100.0, volume=1_000_000.0):
    return {d:(price,volume) for d in dates}

def main():
    exp=[f"2026-09-{d:02d}" for d in range(1,21)]
    # The functions only need a stable ordered set of expected dates for this invariant test.
    exact=bars(exp)
    incomplete=bars(exp[:-1])
    low=bars(exp,price=20.0,volume=1_000_000.0)  # $20m/session => terminal DV20 fail

    st,info=price_classify(exact,exp[-1],exp,"TEST")
    assert st=="PASS_PRICE_DV20",(st,info)
    assert info["known_session_count"]==20 and info["missing_sessions"]==[]

    st,info=price_classify(incomplete,exp[-1],exp,"TEST")
    assert st=="UNKNOWN",(st,info)
    assert info["reason"]=="ASOF_MISSING"  # exact ASOF itself missing

    # Missing a middle expected session while ASOF exists must never PASS.
    mid=bars([d for d in exp if d!=exp[9]])
    st,info=price_classify(mid,exp[-1],exp,"TEST")
    assert st!="PASS_PRICE_DV20",(st,info)
    assert st in {"UNKNOWN","FAIL_DV20"}

    st,info=price_classify(low,exp[-1],exp,"TEST")
    assert st=="FAIL_DV20",(st,info)

    st,info=resolver_classify(exact,exp[-1],exp,"TEST")
    assert st=="PASS_HARD_GATES",(st,info)
    assert info["known_session_count"]==20 and info["missing_sessions"]==[]

    st,info=resolver_classify(mid,exp[-1],exp,"TEST")
    assert st!="PASS_HARD_GATES",(st,info)

    sina=load_sina()
    bad_overlay={
      "decision":"PASS_HARD_GATES","price":100.0,"bars":300,
      "dv20_lower_bound":100_000_000.0,"dv20_upper_bound":100_000_000.0,
      "known_session_count":19,"missing_sessions":[exp[9]],
      "no_synthetic_bar":True,"source":"TEST","proof":"BOUND"
    }
    st,info=sina.resolution_result("ZZZZ",bad_overlay,exp)
    assert st=="UNKNOWN_STATIC",(st,info)

    good_overlay={
      "decision":"PASS_HARD_GATES","price":100.0,"bars":300,
      "dv20_lower_bound":100_000_000.0,"dv20_upper_bound":100_000_000.0,
      "known_session_count":20,"missing_sessions":[],
      "no_synthetic_bar":True,"source":"TEST","proof":"EXACT20_MEDIAN"
    }
    st,info=sina.resolution_result("ZZZZ",good_overlay,exp)
    assert st=="PASS",(st,info)
    assert info["known_session_count"]==20 and info["missing_sessions"]==[]

    print({"status":"PASS","invariants":["EXACT20_REQUIRED_FOR_PASS","INCOMPLETE_NEVER_PASS","OVERLAY_EXACT20_REQUIRED"]})

if __name__=="__main__":
    main()
