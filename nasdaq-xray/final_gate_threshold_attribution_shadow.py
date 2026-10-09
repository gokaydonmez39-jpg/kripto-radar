#!/usr/bin/env python3
"""C4.17 exact FINAL gate attribution and non-authoritative what-if diagnosis.

Uses immutable actual Final JSON and independently recalculates frozen
risk distance and transaction-cost risk/reward. NEVER changes alpha,
scores a win probability, trades, delivers or promotes WATCH to AL.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
FINAL = ROOT / "canonical_current_final_tech.json"
TERMINAL = ROOT / "canonical_current_terminal.json"
PRICE = ROOT / "canonical_current_price_dv30.json"
SCHEMA = "XRAY_C417_FINAL_GATE_ATTRIBUTION_SHADOW_V1"
RISK_CAP = 0.08
RR_THRESH = {"A":(1.5,1.1),"B":(2.,1.5),"C":(2.,1.5),"D":(2.,1.5)}
STRESS_CAPS = (0.08, 0.09, 0.10, 0.12, 0.15, 0.20)


def gblob(path:Path)->str:
    return subprocess.check_output(["git","hash-object",str(path)],cwd=REPO,text=True).strip()


def finite_positive(v:object)->float:
    if isinstance(v,bool):
        raise ValueError("UNTRUSTED_NUMERIC_BOOL")
    x=float(v)
    if not math.isfinite(x) or x<=0:
        raise ValueError("INVALID_NONPOSITIVE_NONFINITE_LEVEL")
    return x


def calc_rr(entry:float,stop:float,target:float,atr:float,cost_mult:float)->float:
    fee=atr*cost_mult
    denominator=(entry+fee)-(stop-fee)
    if denominator<=0:
        raise ValueError("RISK_DENOMINATOR_INVALID")
    return ((target-fee)-(entry+fee))/denominator


def one(key:str,row:dict)->dict:
    fam=row.get("family")
    if fam not in RR_THRESH or key.split("|")[-1]!=fam:
        raise ValueError("FAMILY_KEY_MISMATCH")
    frozen=row.get("frozen_geometry")
    if not isinstance(frozen,dict):
        raise ValueError("FROZEN_MISSING")
    A=finite_positive(frozen.get("A"))
    P=finite_positive(frozen.get("P"))
    S0=finite_positive(frozen.get("S0"))
    entry=finite_positive(frozen.get("entry_model"))
    entry_high=finite_positive(frozen.get("entry_high"))
    T1=finite_positive(frozen.get("T1"))
    anchor=finite_positive(frozen.get("anchor"))
    if S0>=entry or abs(entry-(P+0.25*A))>max(1e-9,entry*1e-9):
        raise ValueError("FROZEN_ENTRY_OR_STOP_INCONSISTENT")
    risk_pct=(entry-S0)/entry
    risk_atr=(entry-S0)/A
    basic=calc_rr(entry,S0,T1,A,0.10)
    severe=calc_rr(entry,S0,T1,A,0.25)
    geom=row.get("geometry") or {}
    rr=row.get("rr") or {}
    for name,calc,recorded in (
      ("risk_percent",risk_pct,geom.get("risk_percent")),
      ("risk_atr",risk_atr,geom.get("risk_atr")),
      ("RR_BASIC",basic,rr.get("basic")),
      ("RR_SEVERE",severe,rr.get("severe"))):
        if recorded is None or not math.isclose(calc,float(recorded),rel_tol=1e-8,abs_tol=1e-10):
            raise ValueError("ARITHMETIC_DRIFT_"+name)
    # Geometry ATR range, RR, anti-chase and target all remain independent gates.
    risk_atr_ok = 0.75<=risk_atr<=2.50
    rr_ok=(basic>=RR_THRESH[fam][0] and severe>=RR_THRESH[fam][1])
    target_ok=not bool(row.get("target_overlap")) and T1>entry_high
    lifecycle_ok=row.get("lifecycle") in ("ENTRY_BAND","RETEST_ENTRY_BAND")
    extension_ok=row.get("extension_veto") is False
    event_ok=row.get("event_status")=="CLEAN_DISCOVERY"
    regime_ok=row.get("regime_finalist_status")=="PASS"
    invalidation_ok=(row.get("invalidation") or {}).get("breached") is False
    mc_cap_ok=row.get("state_cap")=="PASS" and row.get("r92_eligible") is True
    if row.get("pre_g9_tech_pass") is True:
        raise ValueError("FROZEN_SOURCE_CLAIMS_TECH_PASS_DIFFERENT_THAN_ZERO_SCOPE")
    independent_other_technical=(risk_atr_ok and rr_ok and target_ok and lifecycle_ok
                                 and extension_ok and event_ok and regime_ok and invalidation_ok)
    return {
      "risk_percent":risk_pct, "risk_atr":risk_atr,"basic_rr":basic,"severe_rr":severe,
      "risk_atr_ok":risk_atr_ok,"rr_ok":rr_ok,"target_ok":target_ok,
      "lifecycle_ok":lifecycle_ok,"extension_ok":extension_ok,"event_ok":event_ok,
      "regime_ok":regime_ok,"invalidation_ok":invalidation_ok,
      "mc_cap_ok":mc_cap_ok,"other_technical_ok_without_risk_percent":independent_other_technical,
      "actual_risk_percent_pass":risk_pct<=RISK_CAP,
      "actual_hard_technical_pass":independent_other_technical and risk_pct<=RISK_CAP,
      "family":fam
    }


def evaluate(final:dict,terminal:dict,price:dict,final_sha:str,price_sha:str)->dict:
    if final.get("source_compiled_policy_version")!="C4.17" or terminal.get("compiled_policy_version")!="C4.17":
        raise ValueError("POLICY_NOT_EXACT_C417")
    asof=final.get("asof_et")
    if not isinstance(asof,str) or asof!=terminal.get("asof_et"):
        raise ValueError("FINAL_TERMINAL_ASOF_DRIFT")
    link=(terminal.get("evidence") or {}).get("final") or {}
    if link.get("blob_sha")!=final_sha or link.get("path")!="nasdaq-xray/canonical_current_final_tech.json":
        raise ValueError("EXACT_FINAL_SHA_NOT_PINNED_TO_TERMINAL")
    for d in (terminal,final,price):
        if d.get("execution")!="NONE" or d.get("real_money")!="NO-GO":
            raise ValueError("SAFETY_BROKEN")
    if not terminal.get("unknown_never_pass") or not final.get("unknown_never_pass"):
        raise ValueError("UNKNOWN_POLICY_BROKEN")
    if price.get("asof_et")==asof:
        # A fully current same-ASOF PRICE may be evaluated, but it is never
        # independently established by this snapshot-level technical audit.
        pass
    elif price.get("asof_et")<asof:
        raise ValueError("LATEST_PRICE_OLDER_THAN_FINAL")
    if len(price_sha)!=40 or len(final_sha)!=40:
        raise ValueError("INVALID_GIT_BLOB_SHA")
    rows=final.get("results")
    if not isinstance(rows,dict) or len(rows)!=final.get("fail_count") or final.get("pre_g9_tech_pass_count")!=0:
        raise ValueError("FINAL_SET_COUNT_OR_BASELINE_DRIFT")
    if set(rows)!=set(final.get("fail") or []):
        raise ValueError("FINAL_SET_MEMBERSHIP_DRIFT")
    if set(rows)!=set(terminal.get("sets",{}).get("final_fail") or []):
        raise ValueError("TERMINAL_FINAL_SET_MISMATCH")
    checks={key:one(key,row) for key,row in rows.items()}
    n=len(checks)
    count=lambda field:sum(bool(x[field]) for x in checks.values())
    if count("actual_hard_technical_pass")!=0:
        raise ValueError("BASELINE_HARD_TECH_PASS_DRIFT")
    gate_failures={k:n-count(k) for k in (
      "actual_risk_percent_pass","risk_atr_ok","rr_ok","target_ok","lifecycle_ok",
      "extension_ok","event_ok","regime_ok","invalidation_ok","mc_cap_ok")}
    # Diagnostic counterfactuals: do not weaken price/MC/history/event/RR or
    # do future/fantasy fills. Preserve every OTHER technical gate as frozen.
    sensitivity={}
    for cap in STRESS_CAPS:
        risk_only=sum(x["risk_percent"]<=cap for x in checks.values())
        other_technical=sum(x["other_technical_ok_without_risk_percent"] and x["risk_percent"]<=cap
                            for x in checks.values())
        with_mc_cap=sum(x["other_technical_ok_without_risk_percent"] and x["risk_percent"]<=cap
                        and x["mc_cap_ok"] for x in checks.values())
        sensitivity[f"{cap:.0%}"]={"risk_percent_only_meets_cap":risk_only,
            "all_other_technical_gates_still_met":other_technical,
            "all_other_and_mc_cap_met":with_mc_cap}
    blockers=Counter(s for row in rows.values() for s in (row.get("diagnostic_blockers") or []))
    known_calibrated=0  # No performance/win probability produced by this artifact.
    return {
      "schema":SCHEMA, "status":"RESEARCH_ATTRIBUTION_ONLY_NO_THRESHOLD_OR_WINRATE_AUTHORITY",
      "asof_et":asof,
      "latest_price_asof_et":price.get("asof_et"),
      "final_is_same_asof_as_latest_price":price.get("asof_et")==asof,
      "source_final_git_blob_sha":final_sha,
      "source_price_git_blob_sha":price_sha,
      "policy":"C4.17","control":"C4.27",
      "finalists_n":n,
      "family_counts":dict(sorted(Counter(x["family"] for x in checks.values()).items())),
      "gate_failed_counts_nonexclusive":gate_failures,
      "diagnostic_blocker_counts_nonexclusive":dict(sorted(blockers.items())),
      "counterfactual_risk_percent_caps_no_other_relaxation":sensitivity,
      "actual_pre_g9_tech_pass":0,
      "production_primary_mc_pass_confirmed":False,
      "win_rate_estimate":None,
      "comparable_completed_sample_count":known_calibrated,
      "probability_100_percent_claimed":False,
      "probability_80_90_percent_claimed":False,
      "attribution_sample_same_asof_complete_data":False,
      "threshold_changes_authorized":False,
      "canonical_artifacts_modified":False,
      "can_register_R92":False,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True
    }


def selftest()->None:
    A=1.
    P=15.
    entry=P+.25*A
    stop=entry-0.075*entry
    base={
      "family":"D",
      "frozen_geometry":{"A":A,"P":P,"anchor":stop+.2*A,"S0":stop,
                         "entry_model":entry,"entry_high":entry,"T1":entry+4.0*A},
      "geometry":{"risk_percent":(entry-stop)/entry,"risk_atr":entry-stop},
      "rr":{},
      "target_overlap":False,"lifecycle":"ENTRY_BAND","extension_veto":False,
      "event_status":"CLEAN_DISCOVERY","regime_finalist_status":"PASS",
      "invalidation":{"breached":False},
      "state_cap":"PASS","r92_eligible":True,"pre_g9_tech_pass":False
    }
    base["rr"]["basic"]=calc_rr(entry,stop,entry+4*A,A,.10)
    base["rr"]["severe"]=calc_rr(entry,stop,entry+4*A,A,.25)
    good=one("XYZ|D",base)
    assert good["risk_percent"]<=.08 and good["rr_ok"] and good["lifecycle_ok"]
    assert good["actual_hard_technical_pass"],"MATHEMATICALLY_UNREACHABLE_PASS"
    for mod in (
     lambda d:d["geometry"].update(risk_percent=.001),
     lambda d:d["rr"].update(basic=999),
     lambda d:d["frozen_geometry"].update(S0=-1),
     lambda d:d.update(family="A"),
    ):
        bad=copy.deepcopy(base);mod(bad)
        try:one("XYZ|D",bad)
        except (ValueError,TypeError):continue
        raise AssertionError("CORRUPTED_FROZEN_RISK_ACCEPTED")
    chase=copy.deepcopy(base);chase["lifecycle"]="CHASE_NO_VALID_FILL"
    assert not one("XYZ|D",chase)["actual_hard_technical_pass"]
    rr_bad=copy.deepcopy(base);rr_bad["frozen_geometry"]["T1"]=entry+0.5*A
    rr_bad["rr"]["basic"]=calc_rr(entry,stop,entry+.5*A,A,.10)
    rr_bad["rr"]["severe"]=calc_rr(entry,stop,entry+.5*A,A,.25)
    assert not one("XYZ|D",rr_bad)["actual_hard_technical_pass"]
    assert one("XYZ|D",rr_bad)["actual_risk_percent_pass"],"RISK_ONLY_ZERO_REJECTS"
    print("XRAY_C417_GATE_ATTRIBUTION_SELFTEST=PASS_MATH_POSITIVE_4_NEGATIVES_LIFECYCLE_AND_RR_INDEPENDENT")


def main()->None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    x=ap.parse_args()
    if x.selftest:
        selftest();return
    src=json.loads(FINAL.read_text(encoding="utf-8"))
    terminal=json.loads(TERMINAL.read_text(encoding="utf-8"))
    price=json.loads(PRICE.read_text(encoding="utf-8"))
    doc=evaluate(src,terminal,price,gblob(FINAL),gblob(PRICE))
    if x.out:
        x.out.write_text(json.dumps(doc,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("XRAY_C417_ATTRIBUTION_FINALISTS="+str(doc["finalists_n"]))
    print("XRAY_C417_ATTRIBUTION_NONEXCLUSIVE="+json.dumps(doc["gate_failed_counts_nonexclusive"],sort_keys=True))
    print("XRAY_C417_ATTRIBUTION_COUNTERFACTUAL="+json.dumps(doc["counterfactual_risk_percent_caps_no_other_relaxation"],sort_keys=True))
    print("XRAY_C417_ATTRIBUTION_ASOF_STALE_VS_PRICE="+str(not doc["final_is_same_asof_as_latest_price"]).lower())
    print("XRAY_C417_ATTRIBUTION_NO_REAL_AL_OR_PROBABILITY=PASS")


if __name__=="__main__":
    main()
