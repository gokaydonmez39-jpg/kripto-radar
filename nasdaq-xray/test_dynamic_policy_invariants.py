#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, pathlib, sys

ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

from price_dv20_phase import classify as price_classify
from resolve_unknowns_fallback import classify as resolver_classify
from deep_pre_r1_shadow import family_b
import pandas as pd

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

    history_prefix={f"H{i:03d}":(100.0,1_000_000.0) for i in range(260)}
    rich_exact={**history_prefix,**exact}
    rich_mid={**history_prefix,**mid}
    st,info=resolver_classify(rich_exact,exp[-1],exp,"TEST")
    assert st=="PASS_HARD_GATES",(st,info)
    assert info["known_session_count"]==20 and info["missing_sessions"]==[]

    st,info=resolver_classify(rich_mid,exp[-1],exp,"TEST")
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

    # Setup-B regression: breakout pivot MUST come from the completed base and
    # exclude the current breakout bar. Including the current bar makes the
    # breakout inequality self-containing/unsatisfiable (a bug class observed
    # in an external Donchian implementation).
    rows=[]
    for i in range(60):
        if i < 39:
            o=100.0; h=102.0; l=98.0; close=100.0; vol=1_000_000.0
        elif i < 59:
            o=100.0; h=100.5; l=99.5; close=100.0; vol=1_000_000.0
        else:
            o=101.0; h=150.0; l=100.8; close=102.0; vol=3_000_000.0
        rows.append({"date":pd.Timestamp("2026-01-01")+pd.Timedelta(days=i),
                     "open":o,"high":h,"low":l,"close":close,"volume":vol})
    b=family_b(pd.DataFrame(rows))
    assert b and b["pool"] is True,b
    assert abs(float(b["P"])-100.5)<1e-9,b
    assert b["breakout_confirmed"] is True,b

    print({"status":"PASS","invariants":[
        "EXACT20_REQUIRED_FOR_PASS","INCOMPLETE_NEVER_PASS",
        "OVERLAY_EXACT20_REQUIRED","SETUP_B_PIVOT_EXCLUDES_CURRENT_BAR"
    ]})

if __name__=="__main__":
    main()
