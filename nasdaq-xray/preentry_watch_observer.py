#!/usr/bin/env python3
"""Evidence-bound pre-entry observation and disjoint data-vs-tech attrition.

Research-only overlay. C4.17 alpha, delivery, candidate lifecycle and execution
remain untouched. An observed pivot proximity is NEVER an AL/BUY signal.
"""
from __future__ import annotations
import argparse
import collections
import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import research_watch_radar as existing

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_C417_PREENTRY_ATTRITION_WATCH_V1"


def finite(v):
    return type(v) in (int,float) and math.isfinite(v)


def diagnose_final(key,row):
    """Classify frozen final geometry without generating an entry decision."""
    symbol,sep,family=key.partition("|")
    if not sep or not symbol or family not in ("A","B","C","D"):
        raise ValueError("FINAL_KEY_INVALID")
    if not isinstance(row,dict) or row.get("family")!=family:
        raise ValueError("FINAL_FAMILY_INVALID")
    lv=row.get("levels") or {}
    need=("A","P","S0","T1","entry_low","entry_high","chase_limit","close")
    if not all(finite(lv.get(k)) for k in need):
        raise ValueError("NONFINITE_FROZEN_GEOMETRY")
    A,P,S,T,E0,E1,chase,close=(float(lv[k]) for k in need)
    if not (A>0 and 0<S<P<=E0<=E1<chase and close>0):
        raise ValueError("FROZEN_GEOMETRY_ORDER_INVALID")
    measured_risk=(E1-S)/E1
    stored_risk=(row.get("geometry") or {}).get("risk_percent")
    if not finite(stored_risk) or not math.isclose(
        measured_risk,float(stored_risk),rel_tol=1e-9,abs_tol=1e-9
    ):
        raise ValueError("FROZEN_RISK_ARITHMETIC_MISMATCH")
    rr=row.get("rr") or {}
    if not finite(rr.get("basic")) or not finite(rr.get("severe")):
        raise ValueError("MISSING_OR_NONFINITE_RR")
    risk_fail=(measured_risk>0.08 or row.get("risk_pass") is not True)
    rr_fail=rr.get("basic_pass") is not True or rr.get("severe_pass") is not True
    target_overlap=bool(row.get("target_overlap")) or T<=E1
    event_status=str(row.get("event_status") or "UNKNOWN")
    mc_not_primary=row.get("r92_eligible") is not True or row.get("state_cap") not in ("PASS","GREEN","AL")
    # Prospectiveness describes the position of a FROZEN setup. No forecast.
    if close<P:
        proximity="NEAR_PIVOT_HALF_ATR" if (P-close)<=0.5*A else "BELOW_PIVOT_FAR"
    elif close<=E1:
        proximity="IN_FROZEN_ENTRY_BAND"
    elif close<=chase:
        proximity="ABOVE_ENTRY_WAIT_RETEST"
    else:
        proximity="CHASE_EXCEEDED_NO_LATE_ENTRY"
    flags=[]
    if risk_fail:flags.append("RISK_GT_8PCT_OR_NOT_PROVEN")
    if rr_fail:flags.append("C417_RR_NOT_MET")
    if target_overlap:flags.append("R1_TARGET_OVERLAP_OR_BELOW_ENTRY")
    if event_status not in ("CLEAN_DISCOVERY","CLEAN","PASS","EVENT_CLEAN"):
        flags.append("EVENT_NOT_PROVEN_CLEAN")
    if mc_not_primary:flags.append("MC_NOT_PRIMARY_R92")
    if str(row.get("lifecycle") or "") in (
        "INVALIDATED_S0","EXPIRED_HORIZON","EXPIRED","INVALIDATED"
    ):
        flags.append("LIFECYCLE_INVALID_OR_EXPIRED")
    return {
        "symbol":symbol,"setup":family,"setup_id":row.get("setup_id"),
        "proximity":proximity,
        "pivot_distance_atr":round((P-close)/A,4),
        "risk_pct":round(measured_risk*100,4),
        "c417_hard_gate_blockers":sorted(flags),
        "historical_technical_fail":bool(risk_fail or rr_fail or target_overlap),
        "source_cap_mc_primary_verified":not mc_not_primary,
        "risk_pass":not risk_fail,"rr_pass":not rr_fail,
        "event_clean":not any(x.startswith("EVENT_") for x in flags),
        "al":False,"order":False,
    }


def classify(row,source_ready):
    """Exactly one operational class. Unknown external evidence preempts tech."""
    if not source_ready:
        return "DATA_BLOCKED","CURRENT_SOURCE_LINEAGE_NOT_EXACT"
    blocks=set(row["c417_hard_gate_blockers"])
    data_blocks={"EVENT_NOT_PROVEN_CLEAN","MC_NOT_PRIMARY_R92"}
    if blocks.intersection(data_blocks):
        return "DATA_BLOCKED","CANDIDATE_LOCAL_EVENT_OR_MC_AUTHORITY_MISSING"
    if row["historical_technical_fail"] or "LIFECYCLE_INVALID_OR_EXPIRED" in blocks:
        return "TECH_FAIL","FROZEN_C417_RISK_RR_TARGET_OR_LIFECYCLE"
    if row["proximity"]=="NEAR_PIVOT_HALF_ATR":
        return "WATCH_PRE_ENTRY","NEAR_FROZEN_PIVOT_NOT_AL"
    if row["proximity"]=="IN_FROZEN_ENTRY_BAND":
        return "WATCH_ENTRY_BAND","PENDING_FULL_C417_TERMINAL_NO_AL_PROMOTION"
    if row["proximity"]=="BELOW_PIVOT_FAR":
        return "WATCH_DISTANCE","BELOW_PIVOT_FAR_NOT_AN_ENTRY"
    if row["proximity"]=="ABOVE_ENTRY_WAIT_RETEST":
        return "WATCH_RETEST","DO_NOT_CHASE_WAIT_FOR_FRESH_VALIDATED_SETUP"
    return "TECH_FAIL","CHASE_EXCEEDED_DO_NOT_CHASE"


def b_armed_observation(symbol, record):
    """Prospective tight-base B: pivot proximity only, breakout unconfirmed."""
    if not isinstance(record,dict):
        raise ValueError("B_ARMED_RECORD_MISSING")
    b=record.get("B") or {}
    if b.get("pool") is not True or b.get("breakout_confirmed") is not False:
        raise ValueError("B_ARMED_BASE_CONTRACT_NOT_EXACT")
    if not all(finite(b.get(k)) for k in ("A","P","close","window")):
        raise ValueError("B_ARMED_NONFINITE_GEOMETRY")
    atr,pivot,close=float(b["A"]),float(b["P"]),float(b["close"])
    if not (atr>0 and pivot>0 and close>0 and
            type(b["window"]) is int and 5<=b["window"]<=20):
        raise ValueError("B_ARMED_INVALID_BASIS")
    distance=(pivot-close)/atr
    zone=("NEAR_B_PIVOT_HALF_ATR" if 0<=distance<=0.5
          else "B_PIVOT_NOT_NEAR" if distance>0.5
          else "B_ALREADY_ABOVE_PIVOT_BREAKOUT_UNCONFIRMED")
    return {
        "symbol":symbol,"setup":"B_ARMED","proximity":zone,
        "pivot_distance_atr":round(distance,4),
        "event_status":record.get("event_status") or "UNKNOWN",
        "source_cap":record.get("state_cap") or "UNKNOWN",
        "reason":"UNCONFIRMED_BREAKOUT_AND_EVENT_REQUIRES_INDEPENDENT_CHECK",
        "al":False,"order":False
    }


def build(root):
    radar=existing.build(root)
    terminal,_=existing.read(root,"canonical_current_terminal.json")
    final,_=existing.read(root,"canonical_current_final_tech.json")
    master,_=existing.read(root,"canonical_current_master_manifest.json")
    price,_=existing.read(root,"canonical_current_price_dv30.json")
    root_state,_=existing.read(root,"orchestrator_state.json")
    deep,_=existing.read(root,"canonical_current_deep_full.json")
    asof=terminal.get("asof_et")
    source_ready=bool(
        radar["source_exact"] and asof
        and asof==master.get("asof_et")==price.get("asof_et")
        and (terminal.get("full_end_to_end_research_pass") is True
             or terminal.get("candidate_local_research_pass") is True)
        and terminal.get("execution")=="NONE" and terminal.get("real_money")=="NO-GO"
    )
    observed=[]
    counts=collections.Counter()
    historical=collections.Counter()
    for key,row in sorted((final.get("results") or {}).items()):
        d=diagnose_final(key,row)
        klass,reason=classify(d,source_ready)
        counts[klass]+=1
        if d["historical_technical_fail"]:
            historical["FROZEN_RISK_RR_TARGET_FAIL"]+=1
        if d["proximity"]=="CHASE_EXCEEDED_NO_LATE_ENTRY":
            historical["FROZEN_CHASE_EXCEEDED"]+=1
        observed.append({**d,"classification":klass,"reason":reason,
                         "live_research_observation":source_ready})
    usable=[r for r in observed if r["classification"].startswith("WATCH_") and source_ready]
    # Observe B before breakout rather than waiting for the Final trigger.
    # Deep-full stage is bound by existing.research_watch_radar.build().
    armed=[]
    for symbol in sorted(set(deep.get("b_armed_rs_event_watch") or [])):
        row=(deep.get("results") or {}).get(symbol)
        armed.append(b_armed_observation(symbol,row))
    live_armed=armed if source_ready else []
    return {
        "schema":SCHEMA,"asof_et":asof,
        "observed_at_utc":datetime.now(timezone.utc).isoformat(),
        "source_blobs":radar["source_blobs"],
        "source_asof":{"terminal":asof,"master":master.get("asof_et"),
                       "price":price.get("asof_et"),"root":root_state.get("asof_et")},
        "source_exact":radar["source_exact"],
        "current_source_ready":source_ready,
        "status":"PROSPECTIVE_RESEARCH_WATCH_ONLY" if source_ready
                 else "DATA_BLOCKED_STALE_OR_INCOMPLETE_SOURCE",
        "source_binding_discrepancies":radar["binding_discrepancies"],
        "root_unknown_history":root_state.get("unknown_count"),
        "root_pending_retry":root_state.get("pending_retry"),
        "master_unknown_identity":master.get("unknown_count"),
        "disjoint_class_counts":dict(sorted(counts.items())),
        "observed_final_count":len(observed),
        "historical_frozen_reason_counts":dict(sorted(historical.items())),
        "preentry_watch":usable,
        "prospective_watch_count":len(usable)+len(live_armed),
        "prospective_final_watch_count":len(usable),
        "prebreakout_b_armed_watch":live_armed,
        "observed_b_armed_count":len(armed),
        "historical_b_armed_not_live":armed if not source_ready else [],
        "historical_diagnostic_only":observed if not source_ready else [],
        "alpha_authority":False,"delivery_authority":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
        "r92_candidates":[],"buy_candidates":[],"orders":[],
        "github_delivery_recorded":False,"device_receipt_proven":False,
        "note":"A WATCH classification is NOT a C4.17 AL candidate. Historical diagnostics are not current signals."
    }


def selftest():
    base={
        "family":"D","setup_id":"FIXTURE",
        "levels":{"A":2.0,"P":100.0,"S0":96.0,"T1":114.0,
                  "entry_low":100.0,"entry_high":101.0,
                  "chase_limit":102.0,"close":99.3},
        "geometry":{"risk_percent":5/101},
        "rr":{"basic":2.4,"severe":1.8,"basic_pass":True,"severe_pass":True},
        "risk_pass":True,"target_overlap":False,
        "event_status":"CLEAN_DISCOVERY","r92_eligible":True,"state_cap":"PASS",
        "lifecycle":"ENTRY_BAND",
    }
    from copy import deepcopy
    row=diagnose_final("TEST|D",base)
    assert row["proximity"]=="NEAR_PIVOT_HALF_ATR"
    assert classify(row,True)[0]=="WATCH_PRE_ENTRY"
    assert classify(row,False)[0]=="DATA_BLOCKED"
    assert not row["al"] and not row["order"]
    changed=deepcopy(base);changed["levels"]["close"]=104
    assert diagnose_final("TEST|D",changed)["proximity"]=="CHASE_EXCEEDED_NO_LATE_ENTRY"
    assert classify(diagnose_final("TEST|D",changed),True)[0]=="TECH_FAIL"
    for path,value in [
        (("r92_eligible",),False),
        (("event_status",),"UNKNOWN"),
    ]:
        changed=deepcopy(base);changed[path[0]]=value
        assert classify(diagnose_final("TEST|D",changed),True)[0]=="DATA_BLOCKED"
    changed=deepcopy(base)
    changed["levels"]["S0"]=89
    changed["geometry"]["risk_percent"]=12/101
    changed["risk_pass"]=False
    assert classify(diagnose_final("TEST|D",changed),True)[0]=="TECH_FAIL"
    changed=deepcopy(base);changed["rr"]["basic_pass"]=False
    assert classify(diagnose_final("TEST|D",changed),True)[0]=="TECH_FAIL"
    for key,val in (("close",float("nan")),("A",0),("S0",True),("entry_high",float("inf"))):
        changed=deepcopy(base);changed["levels"][key]=val
        try:diagnose_final("TEST|D",changed)
        except ValueError:pass
        else:raise AssertionError("INVALID_LEVEL_ACCEPTED:"+key)
    b={"B":{"A":2.0,"P":100,"close":99.4,
           "window":5,"pool":True,"breakout_confirmed":False},
       "event_status":"UNKNOWN","state_cap":"WATCH"}
    assert b_armed_observation("TEST",b)["proximity"]=="NEAR_B_PIVOT_HALF_ATR"
    for name,val in [("A",0),("P",float("nan")),("window",True)]:
        bad=deepcopy(b);bad["B"][name]=val
        try:b_armed_observation("TEST",bad)
        except ValueError:pass
        else:raise AssertionError("B_ARMED_INVALID_ACCEPTED:"+name)
    changed=deepcopy(base);changed["geometry"]["risk_percent"]=0.01
    try:diagnose_final("TEST|D",changed)
    except ValueError:pass
    else:raise AssertionError("MISMATCHED_RISK_ACCEPTED")
    print("XRAY_PREENTRY_OBSERVER_SELFTEST=PASS_PROXIMITY_DATA_TECH_10_NEGATIVE_NO_AL")


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    a=ap.parse_args()
    if a.selftest:selftest()
    else:
        if not a.out:ap.error("--out required")
        j=build(ROOT)
        a.out.write_text(json.dumps(j,sort_keys=True,indent=2)+"\n")
        print("XRAY_PREENTRY_SOURCE="+j["status"])
        print("XRAY_PREENTRY_CLASS_COUNTS="+json.dumps(j["disjoint_class_counts"],sort_keys=True))
        print("XRAY_PREENTRY_WATCH="+str(j["prospective_watch_count"]))
        print("XRAY_PREENTRY_BUY=0_EXECUTION_NONE")
