#!/usr/bin/env python3
"""Non-authoritative diagnostic: compare C4.17 Family-A geometry with Research Ruleset 5.2.

This script MUST NOT change candidate state, terminal state, alerts, G9, ACCOUNT,
execution, or real-money status. It only measures potential setup-starvation
caused by policy-generation differences.
"""
from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd
import deep_pre_r1_shadow as deep
import final_tech_shadow as ft

ROOT=Path(__file__).resolve().parent
STAGE1=ROOT/"canonical_current_stage1.json"
DEEP=ROOT/"canonical_current_deep_full.json"
OUT=ROOT/"canonical_shadow_c417_vs_52_a.json"

def eval_a52_at_trigger(df,t):
    if t<=0 or t>=len(df):
        return {"pool":False,"reason":"A52_TRIGGER_INDEX"}
    x=df.iloc[:t+1].reset_index(drop=True)
    st=deep.active_hl_and_sh(x)
    if not st:
        return {"pool":False,"reason":"A52_NO_ACTIVE_HL"}
    hl=st["hl"]
    prev_h=[i for i in st["hs"] if i<hl]
    if not prev_h:
        return {"pool":False,"reason":"A52_NO_SH"}
    sh=prev_h[-1]
    sessions=t-(sh+2)
    if sessions<2 or sessions>8:
        return {"pool":False,"reason":"A52_SH_AGE","sessions_since_confirm":sessions}
    if t<hl+3:
        return {"pool":False,"reason":"A52_HL_NOT_CONFIRMED_BEFORE_REVERSAL","sessions_since_confirm":sessions}
    if float(x.close.iloc[t])<=float(x.high.iloc[t-1]):
        return {"pool":False,"reason":"A52_NO_REVERSAL","sessions_since_confirm":sessions}
    if not deep.trend_pullback_stage1_at(x,t):
        return {"pool":False,"reason":"A52_STAGE1_AT_TRIGGER_FAIL","sessions_since_confirm":sessions}

    atr=deep.atr14(x)
    if atr is None or pd.isna(atr.iloc[t-1]) or pd.isna(atr.iloc[sh]):
        return {"pool":False,"reason":"A52_ATR"}
    a_trigger=float(atr.iloc[t-1])
    a_peak=float(atr.iloc[sh])
    if a_trigger<=0 or a_peak<=0:
        return {"pool":False,"reason":"A52_ATR_NONPOSITIVE"}

    anchor=float(x.low.iloc[hl])
    peak=float(x.high.iloc[sh])
    p=float(x.high.iloc[t-1])
    # Ruleset 5.2: pullback minimum after the swing-high and before the reversal bar.
    lo_start=sh+1
    lo_end=t
    if lo_start>=lo_end:
        return {"pool":False,"reason":"A52_EMPTY_PULLBACK_WINDOW"}
    pullback_min=float(x.low.iloc[lo_start:lo_end].min())
    depth=(peak-pullback_min)/a_peak
    prelow=float(deep.family_a_pretrigger_low(x,t))
    near_hl=abs(prelow-anchor)<=0.5*a_trigger
    geom=bool(near_hl and 0.5<=depth<=2.5)
    return {
        "pool":geom,
        "reason":"A52_PASS" if geom else "A52_GEOMETRY_FAIL",
        "sh_date":x.date.iloc[sh].strftime("%Y-%m-%d"),
        "hl_date":x.date.iloc[hl].strftime("%Y-%m-%d"),
        "trigger_date":x.date.iloc[t].strftime("%Y-%m-%d"),
        "sessions_since_confirm":sessions,
        "P":p,"anchor":anchor,
        "A":a_trigger,"A_trigger":a_trigger,"A_peak":a_peak,
        "peak":peak,"pullback_min":pullback_min,
        "depth":depth,"depth_52":depth,"prelow_near_hl":near_hl,
    }

def family_a52(df,eligible_trigger_dates):
    allowed=set(str(x) for x in (eligible_trigger_dates or []))
    last=len(df)-1
    diagnostic=None
    # Ruleset 5.2: new trigger today or prior 3 completed sessions.
    for t in range(max(1,last-3),last+1):
        td=df.date.iloc[t].date().isoformat()
        if td not in allowed:
            continue
        g=eval_a52_at_trigger(df,t)
        diagnostic=g
        if g.get("pool"):
            g["trigger_age_sessions"]=last-t
            return g
    return diagnostic or {"pool":False,"reason":"A52_NO_RECENT_VALID_STRUCTURE"}

def load_one(sym,asof,strow):
    x,src=deep.load_history(sym,asof)
    if x is None or x.empty:
        return sym,None,src or "EMPTY"
    splits=strow.get("split_events") or []
    if splits:
        x=deep.apply_split_events(x,splits)
    x=x.reset_index(drop=True)
    return sym,x,src

def main():
    st=json.loads(STAGE1.read_text())
    dp=json.loads(DEEP.read_text())
    asof=str(dp["asof_et"])
    scope=list(dp.get("weekly_trigger_scope") or [])
    strows=st.get("results") or {}
    histories={}
    errors={}
    with ThreadPoolExecutor(max_workers=6) as ex:
        fut={ex.submit(load_one,s,asof,strows.get(s) or {}):s for s in scope}
        for f in as_completed(fut):
            s=fut[f]
            try:
                sym,x,src=f.result()
                if x is None: errors[s]=src
                else: histories[s]=(x,src)
            except Exception as e:
                errors[s]=f"{type(e).__name__}:{str(e)[:160]}"

    rows={}
    counts={"scope":len(scope),"history_ready":0,"history_unknown":len(errors),
            "c417_pool":0,"a52_pool":0,"both":0,"a52_only":0,"c417_only":0,"neither":0}
    for s in scope:
        old=((dp.get("results") or {}).get(s) or {}).get("A") or {}
        old_pass=old.get("pool") is True
        if old_pass: counts["c417_pool"]+=1
        if s not in histories:
            rows[s]={"status":"UNKNOWN","history_error":errors.get(s),"c417":old}
            continue
        counts["history_ready"]+=1
        x,src=histories[s]
        new=family_a52(x,(strows.get(s) or {}).get("recent_weekly_pass_dates") or [])
        new_pass=new.get("pool") is True
        if new_pass: counts["a52_pool"]+=1
        if old_pass and new_pass: bucket="both"
        elif new_pass: bucket="a52_only"
        elif old_pass: bucket="c417_only"
        else: bucket="neither"
        counts[bucket]+=1

        upper=None
        if new_pass:
            frozen,ferr=ft._frozen_geometry(s,"A",new,x)
            if ferr:
                upper={"status":"UNKNOWN","reason":"FROZEN_GEOMETRY_"+str(ferr.get("reason"))}
            else:
                drow=((dp.get("results") or {}).get(s) or {})
                base=ft.eval_one(
                    s,"A",new,x,drow.get("event_status","UNKNOWN"),
                    frozen=frozen,recorded_before=False,
                    regime_finalist_status=drow.get("regime_finalist_status","UNKNOWN")
                )
                geo=base.get("geometry") or {}
                rr=base.get("rr") or {}
                inv=base.get("invalidation") or {}
                risk_atr=geo.get("risk_atr"); risk_pct=geo.get("risk_percent")
                lifecycle=base.get("lifecycle")
                risk52=bool(isinstance(risk_atr,(int,float)) and isinstance(risk_pct,(int,float))
                            and 1.0<=float(risk_atr)<=2.5 and float(risk_pct)<=0.08)
                rr52=bool(float(rr.get("basic",float("-inf")))>=2.0 and float(rr.get("severe",float("-inf")))>=1.5)
                entry_ready=lifecycle in {"ENTRY_BAND","RETEST_ENTRY_BAND"}
                event_pass=drow.get("event_status")=="CLEAN_DISCOVERY"
                regime_pass=drow.get("regime_finalist_status")=="PASS"
                pre_score=bool(risk52 and rr52 and not base.get("target_overlap")
                               and not base.get("extension_veto") and entry_ready
                               and event_pass and regime_pass and not inv.get("breached"))
                upper={
                    "status":"EVALUATED",
                    "lifecycle":lifecycle,
                    "risk_atr":risk_atr,"risk_percent":risk_pct,"risk_pass_52":risk52,
                    "rr_basic":rr.get("basic"),"rr_severe":rr.get("severe"),"rr_pass_52":rr52,
                    "target_overlap":base.get("target_overlap"),
                    "extension_veto":base.get("extension_veto"),
                    "event_pass":event_pass,"regime_pass":regime_pass,
                    "breached":inv.get("breached"),
                    "pre_score_technical_upper_bound_52":pre_score,
                    "note":"Not AL/PRE_G9 authority: 5.2 score, detailed legal, halt/live, G9 and ACCOUNT are not promoted by this shadow."
                }
        rows[s]={"status":"EVALUATED","history_source":src,"bucket":bucket,"c417":old,"a52":new,"a52_final_upper_bound":upper}

    upper_bound_symbols=sorted([
        s for s,v in rows.items()
        if ((v.get("a52_final_upper_bound") or {}).get("pre_score_technical_upper_bound_52") is True)
    ])
    out={
      "schema":"XRAY_POLICY_GENERATION_SHADOW_COMPARE_V1",
      "asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "alpha_authority":"NONE_DIAGNOSTIC_ONLY",
      "production_policy":"C4.17_UNCHANGED",
      "shadow_policy":"NASDAQ-SWING-RADAR-5.2_FAMILY_A_ONLY",
      "purpose":"MEASURE_POLICY_GENERATION_SIGNAL_STARVATION_WITHOUT_CHANGING_ALPHA",
      "counts":counts,
      "a52_only_symbols":sorted([s for s,v in rows.items() if v.get("bucket")=="a52_only"]),
      "c417_only_symbols":sorted([s for s,v in rows.items() if v.get("bucket")=="c417_only"]),
      "a52_pre_score_technical_upper_bound_symbols":upper_bound_symbols,
      "rows":dict(sorted(rows.items())),
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({k:out[k] for k in ("schema","asof_et","alpha_authority","counts","a52_only_symbols","c417_only_symbols","a52_pre_score_technical_upper_bound_symbols")},sort_keys=True))

if __name__=="__main__":
    main()
