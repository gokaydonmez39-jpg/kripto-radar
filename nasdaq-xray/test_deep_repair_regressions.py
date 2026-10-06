#!/usr/bin/env python3
"""Deep repair regressions for C4.17 fail-closed alpha/data-plane semantics."""
from pathlib import Path
import json, tempfile, gzip
import pandas as pd
import alpha_semantics as alpha
import final_tech_shadow as ft
import build_candidate_legal_guard as legal_guard_mod
import build_current_resolver_request as resolver_req_mod
import price_dv30_recover_from_fullstate as price_recover_mod
import build_current_terminal as terminal_mod
import build_current_event_request as event_req_mod
import regime_breadth_shadow as rb
import deep_pre_r1_shadow as deep_mod
import semantic_cache_diff as cache_diff
from final_tech_shadow import eval_one, load_lifecycle_registry, persist_lifecycle_registry

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent

def frame(n=100):
    dates=pd.bdate_range("2025-01-02",periods=n)
    return pd.DataFrame({"date":dates,"open":[100.0]*n,"high":[103.0]*n,"low":[99.0]*n,
                         "close":[102.0]*n,"volume":[1_000_000.0]*n})

def frozen(df,trigger_idx,setup):
    td=df.date.iloc[trigger_idx].date().isoformat()
    return {"setup_id":setup,"symbol":"TEST","family":"D","trigger_date":td,
      "A":10.0,"P":100.0,"anchor":97.0,"entry_low":100.0,"entry_high":102.5,
      "entry_model":102.5,"chase_limit":105.0,"S0":95.0,"T1":150.0,
      "anchor_available_idx":trigger_idx-1,
      "anchor_available_date":df.date.iloc[trigger_idx-1].date().isoformat(),
      "target_source":"TEST_STRUCTURAL","target_zone":None,"target_overlap":False,
      "synthetic_target":False,"source_geometry":{"trigger_date":td,"P":100.0,"anchor":97.0}}

def test_r1_no_future_mutation_and_confirmation():
    # Isolate daily swing evidence. Otherwise a legitimately nearer base-high
    # zone can be selected before the synthetic 120 swing and invalidate the
    # test assumption without indicating a look-ahead bug.
    oldb,oldw,oldg=alpha._base_high_points,alpha._weekly_swing_points,alpha._gap_down_zones
    alpha._base_high_points=lambda prior,atr:[]
    alpha._weekly_swing_points=lambda prior:[]
    alpha._gap_down_zones=lambda prior:[]
    try:
        d=frame(100)
        d.loc[35,"high"]=120.0; d.loc[33:34,"high"]=[105.0,106.0]; d.loc[36:37,"high"]=[106.0,105.0]
        trigger=80
        r1=alpha.nearest_active_resistance(d,trigger,10.0,100.0,102.5,102.5)
        assert r1["status"]=="PASS" and abs(float(r1["T1"])-120.0)<1e-12,r1
        mutated=d.copy(); mutated.loc[trigger:,["open","high","low","close"]]=[900.0,999.0,800.0,950.0]
        r2=alpha.nearest_active_resistance(mutated,trigger,10.0,100.0,102.5,102.5)
        assert r2["status"]==r1["status"] and abs(float(r2["T1"])-float(r1["T1"]))<1e-12,(r1,r2)
        assert bool(r2["target_overlap"])==bool(r1["target_overlap"]),(r1,r2)
        d3=d.copy(); d3.loc[78,"high"]=140.0; d3.loc[76:77,"high"]=[105.0,106.0]; d3.loc[79,"high"]=106.0
        r3=alpha.nearest_active_resistance(d3,trigger,10.0,100.0,102.5,102.5)
        assert r3["status"]=="PASS" and abs(float(r3["T1"])-120.0)<1e-12,r3
        leak=d3.date.iloc[78].date().isoformat()
        for z in r3["zones"]:
            for p in z.get("points") or []:
                assert not (p.get("kind")=="DAILY_SWING_HIGH" and p.get("date")==leak),(z,p)
    finally:
        alpha._base_high_points,alpha._weekly_swing_points,alpha._gap_down_zones=oldb,oldw,oldg

def test_r1_pivot_boundary_is_not_overhead_but_entry_overlap_is():
    d=frame(80)
    old=alpha.resistance_zones
    try:
        # A zone ending exactly at P is the reclaimed pivot boundary and must
        # not become T1. The next true overhead zone is selected.
        alpha.resistance_zones=lambda df,ti,A:[
          {"lower":99.0,"upper":100.0,"active":True,"kind":"PIVOT_BOUNDARY","points":[]},
          {"lower":130.0,"upper":132.0,"active":True,"kind":"OVERHEAD","points":[]},
        ]
        r=alpha.nearest_active_resistance(d,70,10.0,100.0,102.5,102.5)
        assert r["status"]=="PASS" and abs(float(r["T1"])-130.0)<1e-12,r
        assert r["target_overlap"] is False,r

        # A zone that extends even slightly above P genuinely overlaps the entry
        # band and must remain the nearest veto; do not skip it for a prettier R/R.
        alpha.resistance_zones=lambda df,ti,A:[
          {"lower":99.5,"upper":100.1,"active":True,"kind":"ENTRY_OVERLAP","points":[]},
          {"lower":130.0,"upper":132.0,"active":True,"kind":"OVERHEAD","points":[]},
        ]
        r2=alpha.nearest_active_resistance(d,70,10.0,100.0,102.5,102.5)
        assert r2["status"]=="PASS" and abs(float(r2["T1"])-99.5)<1e-12,r2
        assert r2["target_overlap"] is True,r2
    finally:
        alpha.resistance_zones=old

def test_resistance_role_change_state_machine():
    oldb,oldw,oldg,olds=alpha._base_high_points,alpha._weekly_swing_points,alpha._gap_down_zones,alpha.strict_swings
    alpha._base_high_points=lambda prior,atr:[]
    alpha._weekly_swing_points=lambda prior:[]
    alpha._gap_down_zones=lambda prior:[]
    # Hold the structural evidence set fixed. Otherwise the synthetic breakout
    # and retest bars can themselves become newly confirmed swing highs and
    # create a legitimately new active resistance cluster.
    alpha.strict_swings=lambda prior:([20],[])
    try:
        d=frame(70)
        d.loc[20,"high"]=120.0; d.loc[18:19,"high"]=[105.0,106.0]; d.loc[21:22,"high"]=[106.0,105.0]
        d.loc[40,["open","high","low","close"]]=[121.0,123.0,121.0,121.5]
        z1=alpha.resistance_zones(d,60,10.0)
        t1=[z for z in z1 if any(abs(float(p.get("price",0))-120.0)<1e-12 for p in (z.get("points") or []))]
        assert t1 and t1[0]["active"] is True,t1
        d.loc[45,["open","high","low","close"]]=[121.0,122.0,119.5,121.0]
        z2=alpha.resistance_zones(d,60,10.0)
        t2=[z for z in z2 if any(abs(float(p.get("price",0))-120.0)<1e-12 for p in (z.get("points") or []))]
        assert t2 and t2[0]["active"] is False,t2
        assert t2[0].get("broken_at")==d.date.iloc[45].date().isoformat(),t2[0]
    finally:
        alpha._base_high_points,alpha._weekly_swing_points,alpha._gap_down_zones,alpha.strict_swings=oldb,oldw,oldg,olds

def test_final_history_normalizer_preserves_ohlcv():
    d=frame(40)
    x=ft._normalize_sina(d)
    assert x is not None and list(x.columns)==["date","open","high","low","close","volume"],x.columns
    fp=alpha.history_fingerprint(x,x.date.iloc[-1].date().isoformat())
    assert fp["rows"]==40 and fp["last_date"]==x.date.iloc[-1].date().isoformat(),fp

def test_regime_interval_bounds_and_finalist_gate():
    q={"close":749.58,"sma50":716.817,"sma200":668.60405,"sma50_slope20":5.7836}

    # Interval math remains a diagnostic only: current observed values make STRONG
    # impossible even under the most favorable completion of the 9 missing members.
    diagnostic,meta=rb.classify_regime_bounds(q,456,174,77,54,9)
    assert diagnostic=="MIXED" and meta["strong_possible"] is False,(diagnostic,meta)
    assert meta["breadth_above_sma50_pct_max"]<0.55,meta

    # C4.17 production authority is stricter: any missing CURRENT_CORE breadth
    # member is BREADTH_UNKNOWN / max WATCH. Diagnostic certainty may not promote it.
    regime,prod=rb.classify_regime_policy(q,456,174,77,54,9)
    assert regime=="UNKNOWN",(regime,prod)
    assert prod["diagnostic_interval_regime"]=="MIXED",prod
    assert prod["method"]=="C4_17_STRICT_BREADTH_MISSING_FAIL_CLOSED_V1",prod

    regime2,meta2=rb.classify_regime_bounds(q,100,54,20,19,2)
    assert regime2=="UNKNOWN" and meta2["strong_possible"] is True and meta2["strong_guaranteed"] is False,(regime2,meta2)
    prod2,pmeta2=rb.classify_regime_policy(q,100,54,20,19,2)
    assert prod2=="UNKNOWN" and pmeta2["diagnostic_interval_regime"]=="UNKNOWN",(prod2,pmeta2)

    # Even a diagnostically guaranteed STRONG classification cannot bypass the
    # compiled policy while one breadth member is missing.
    regime3,meta3=rb.classify_regime_bounds(q,100,56,25,20,1)
    assert regime3=="STRONG" and meta3["strong_guaranteed"] is True,(regime3,meta3)
    prod3,pmeta3=rb.classify_regime_policy(q,100,56,25,20,1)
    assert prod3=="UNKNOWN" and pmeta3["diagnostic_interval_regime"]=="STRONG",(prod3,pmeta3)

    # With exact breadth coverage the production classifier may use the normal class.
    exact,pmeta4=rb.classify_regime_policy(q,100,56,25,20,0)
    assert exact=="STRONG" and pmeta4["method"]=="C4_17_EXACT_BREADTH_CLASSIFICATION_V1",(exact,pmeta4)

    weak_q={"close":90.0,"sma50":100.0,"sma200":95.0,"sma50_slope20":-1.0}
    weak_diag,_=rb.classify_regime_bounds(weak_q,100,0,0,0,100)
    assert weak_diag=="WEAK",weak_diag
    weak_prod,_=rb.classify_regime_policy(weak_q,100,0,0,0,100)
    assert weak_prod=="UNKNOWN",weak_prod

    assert ft._regime_finalist_allowed({"regime":"MIXED","results":{"X":{"regime_finalist_pass":True}}},"X")
    assert not ft._regime_finalist_allowed({"regime":"MIXED","results":{"X":{"regime_finalist_pass":False}}},"X")
    assert not ft._regime_finalist_allowed({"regime":"UNKNOWN","results":{"X":{"regime_finalist_pass":True}}},"X")

def test_corporate_action_absence_vs_real_scale_break():
    clean=frame(300)
    x,status,events,lookup=ft.candidate_corporate_action_reconcile("TEST",clean,drow={})
    assert status=="PASS_NO_LOCAL_SPLIT_DISCONTINUITY",(status,events,lookup)
    assert events==[] and lookup is False

    # A material factor-like move is only a discovery trigger. When the split
    # reconciler returns exact verified scale evidence, Final must use that
    # adjusted history instead of double-blocking it as an unknown corporate
    # action. Detailed legal risk is independently fail-closed in the SEC guard.
    suspect=frame(300)
    suspect.loc[200:,["open","high","low","close"]]=[50.0,52.0,49.0,51.0]
    old=ft.split_consistent_history
    ft.split_consistent_history=lambda sym,df:(df,"PASS_SPLIT_RECONCILED_CROSSCHECKED",
        [{"date":df.date.iloc[200].date().isoformat(),"numerator":2.0,"denominator":1.0,"ratio":2.0}])
    try:
        _,status2,events2,lookup2=ft.candidate_corporate_action_reconcile("TEST",suspect,drow={})
        assert status2=="PASS_SPLIT_RECONCILED_CROSSCHECKED",(status2,events2,lookup2)
        assert lookup2 is True and events2
    finally:
        ft.split_consistent_history=old

def test_d_reclaim_cannot_use_same_bar_that_confirms_hl():
    d=frame(100);q=frame(100);t=len(d)-6
    d.loc[t,"close"]=110.0; d.loc[t,"volume"]=2_000_000.0
    old_active,old_atr,old_rs,old_dd=deep_mod.active_hl_and_sh,deep_mod.atr14,deep_mod.common_rs,deep_mod.drawdown_metrics
    try:
        def fake_active(x):
            if len(x)!=t+1:return None
            # HL center t-2 is confirmed only by completed bar t itself.
            return {"hl":t-2,"prior_hs":[t-6],"later_hs":[],"hs":[t-6],"ls":[t-8,t-2]}
        deep_mod.active_hl_and_sh=fake_active
        deep_mod.atr14=lambda x:pd.Series([10.0]*len(x),index=x.index,dtype="float64")
        deep_mod.common_rs=lambda s,qqq,n:0.10
        deep_mod.drawdown_metrics=lambda x:{"current_drawdown_252":-0.20,"max_drawdown_close_120":-0.20}
        td=d.date.iloc[t].date().isoformat()
        g=deep_mod.family_d(d,q,{td})
        assert g.get("dk3_pre_r1") is not True,g
        assert g.get("trigger_date") is None,g
    finally:
        deep_mod.active_hl_and_sh,deep_mod.atr14,deep_mod.common_rs,deep_mod.drawdown_metrics=old_active,old_atr,old_rs,old_dd

def test_family_a_trigger_time_reconstruction_survives_later_structure():
    d=frame(100);t=len(d)-4
    d.loc[t-6,"high"]=130.0
    d.loc[t-4,"low"]=99.0
    d.loc[t-1,["high","low","close"]]=[103.0,99.0,102.0]
    d.loc[t,["high","low","close"]]=[105.0,100.0,104.0]
    old_active,old_atr,old_stage=deep_mod.active_hl_and_sh,deep_mod.atr14,deep_mod.trend_pullback_stage1_at
    try:
        def fake_active(x):
            # A valid trigger inside the canonical age-3 discovery boundary is
            # reconstructed at trigger time even if later structure replaced it.
            if len(x)!=t+1:return None
            return {"hl":t-4,"prior_hs":[t-6],"later_hs":[],"hs":[t-6],"ls":[t-8,t-4]}
        deep_mod.active_hl_and_sh=fake_active
        deep_mod.atr14=lambda x:pd.Series([10.0]*len(x),index=x.index,dtype="float64")
        deep_mod.trend_pullback_stage1_at=lambda x,i: True
        td=d.date.iloc[t].date().isoformat()
        g=deep_mod.family_a(d,{td})
        assert g.get("pool") is True,g
        assert g.get("trigger_date")==td and g.get("trigger_age_sessions")==3,g
        assert 0.30<=float(g["d"])<=1.07 and 2.15<=float(g["depth"])<=4.00,g
    finally:
        deep_mod.active_hl_and_sh,deep_mod.atr14,deep_mod.trend_pullback_stage1_at=old_active,old_atr,old_stage

def test_family_a_age5_unrecorded_trigger_is_not_rediscovered():
    d=frame(100);t=len(d)-6
    d.loc[t-6,"high"]=130.0
    d.loc[t-4,"low"]=99.0
    d.loc[t-1,["high","low","close"]]=[103.0,99.0,102.0]
    d.loc[t,["high","low","close"]]=[105.0,100.0,104.0]
    old_active,old_atr,old_stage=deep_mod.active_hl_and_sh,deep_mod.atr14,deep_mod.trend_pullback_stage1_at
    try:
        def fake_active(x):
            if len(x)!=t+1:return None
            return {"hl":t-4,"prior_hs":[t-6],"later_hs":[],"hs":[t-6],"ls":[t-8,t-4]}
        deep_mod.active_hl_and_sh=fake_active
        deep_mod.atr14=lambda x:pd.Series([10.0]*len(x),index=x.index,dtype="float64")
        deep_mod.trend_pullback_stage1_at=lambda x,i: True
        td=d.date.iloc[t].date().isoformat()
        g=deep_mod.family_a(d,{td})
        assert g.get("pool") is not True,g
        assert g.get("trigger_date") is None,g
    finally:
        deep_mod.active_hl_and_sh,deep_mod.atr14,deep_mod.trend_pullback_stage1_at=old_active,old_atr,old_stage

def test_family_a_final_geometry_revalidation():
    d=frame(300)
    ti=298
    td=d.date.iloc[ti].date().isoformat()
    base={"setup_id":"A-VALID","symbol":"TEST","family":"A","trigger_date":td,
          "A":10.0,"P":100.0,"anchor":97.0,"entry_low":100.0,"entry_high":102.5,
          "entry_model":102.5,"chase_limit":105.0,"S0":95.0,"T1":150.0,
          "anchor_available_idx":ti-1,
          "anchor_available_date":d.date.iloc[ti-1].date().isoformat(),
          "target_source":"TEST_STRUCTURAL","target_zone":None,"target_overlap":False,
          "synthetic_target":False}
    good_g={"trigger_date":td,"P":100.0,"anchor":97.0,"depth":3.0,"prelow_near_hl":True}
    good=dict(base,source_geometry=good_g)
    rg=eval_one("TEST","A",good_g,d,"CLEAN_DISCOVERY",frozen=good,recorded_before=True)
    assert rg.get("family_geometry_pass") is True,rg

    bad_g={"trigger_date":td,"P":100.0,"anchor":97.0,"depth":4.5,"prelow_near_hl":True}
    bad=dict(base,setup_id="A-BAD-DEPTH",source_geometry=bad_g)
    rb=eval_one("TEST","A",bad_g,d,"CLEAN_DISCOVERY",frozen=bad,recorded_before=True)
    assert rb.get("family_geometry_pass") is False and rb.get("risk_pass") is False,rb

    far_g={"trigger_date":td,"P":100.0,"anchor":97.0,"depth":3.0,"prelow_near_hl":False}
    far=dict(base,setup_id="A-BAD-HL",source_geometry=far_g)
    rf=eval_one("TEST","A",far_g,d,"CLEAN_DISCOVERY",frozen=far,recorded_before=True)
    assert rf.get("family_geometry_pass") is False and rf.get("risk_pass") is False,rf

def test_lifecycle_expiry_and_frozen_stability():
    d=frame(300)
    f6=frozen(d,len(d)-7,"TEST-AGE6")
    r6=eval_one("TEST","D",f6["source_geometry"],d,"CLEAN_DISCOVERY",frozen=f6,recorded_before=True)
    assert r6["lifecycle_age_sessions"]==6 and r6["lifecycle"]=="EXPIRED_RETEST_WINDOW" and r6["result"]=="FAIL_EXPIRED",r6
    f9=frozen(d,len(d)-10,"TEST-AGE9")
    r9=eval_one("TEST","D",f9["source_geometry"],d,"CLEAN_DISCOVERY",frozen=f9,recorded_before=True)
    assert r9["lifecycle_age_sessions"]==9 and r9["lifecycle"]=="EXPIRED_HORIZON" and r9["result"]=="FAIL_EXPIRED",r9
    ti=280; fs=frozen(d,ti,"TEST-STABLE")
    a=eval_one("TEST","D",fs["source_geometry"],d.iloc[:ti+2].copy(),"CLEAN_DISCOVERY",frozen=fs,recorded_before=True)
    b=eval_one("TEST","D",fs["source_geometry"],d.iloc[:ti+3].copy(),"CLEAN_DISCOVERY",frozen=fs,recorded_before=True)
    for k in ("A","P","anchor","entry_low","entry_high","entry_model","chase_limit","S0","T1"):
        assert a["levels"][k]==b["levels"][k]==float(fs[k]),(k,a["levels"],b["levels"],fs)
    assert a["setup_id"]==b["setup_id"]==fs["setup_id"],(a,b)

def test_lifecycle_regime_revalidation_persists_without_pass():
    d=frame(300); ti=len(d)-1
    fs=frozen(d,ti,"TEST-REGIME")
    fail=eval_one("TEST","D",fs["source_geometry"],d,"CLEAN_DISCOVERY",frozen=fs,
                  recorded_before=True,regime_finalist_status="FAIL")
    assert fail["pre_g9_tech_pass"] is False and fail["result"]=="WATCH_REGIME_REVALIDATION_REQUIRED",fail
    unk=eval_one("TEST","D",fs["source_geometry"],d,"CLEAN_DISCOVERY",frozen=fs,
                 recorded_before=True,regime_finalist_status="UNKNOWN")
    assert unk["pre_g9_tech_pass"] is False and unk["result"]=="WATCH_REGIME_UNKNOWN",unk
    assert ft.lifecycle_state_persists(fail["result"]) and ft.lifecycle_state_persists(unk["result"])

def test_lifecycle_persistence_roundtrip():
    reg={"schema":"XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1","task_id":"6a825366222081918997094d76e6ae46",
      "asof_et":"2026-10-02","execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "records":{"abc":{"setup_id":"abc","symbol":"TEST","family":"D","trigger_date":"2026-10-01",
        "state":"WATCH_RETEST_REQUIRED","last_asof":"2026-10-02",
        "frozen_geometry":{"A":10.0,"P":100.0,"anchor":97.0,"entry_low":100.0,"entry_high":102.5,
          "entry_model":102.5,"chase_limit":105.0,"S0":95.0,"T1":150.0,
          "target_source":"TEST","target_zone":None,"synthetic_target":False},
        "state_cap":"NORMAL","r92_eligible":True}}}
    with tempfile.TemporaryDirectory() as td:
        side=Path(td)/"registry.json"; final=Path(td)/"final.json"
        assert persist_lifecycle_registry(reg,side)==reg
        assert load_lifecycle_registry(None,side)==reg
        stale=dict(reg); stale["records"]={}
        final.write_text(json.dumps({"lifecycle_registry":stale}))
        assert load_lifecycle_registry(final,side)==reg

def test_mc_bridge_immutable_supersession():
    price={"asof_et":"2026-10-05","pass_symbols":["AAA"],"pass_count":1,"pass_hash":"H"}
    common={
      "schema":"XRAY_MC_EPOCH_RESULT_V1","status":"COMMITTED","task_id":terminal_mod.TASK,
      "execution":"NONE","real_money":"NO-GO","asof_et":"2026-10-05",
      "input_path":"nasdaq-xray/canonical_current_price_dv30.json","input_blob_sha":"PB",
      "input_pass_hash":"H","input_count":1,"policy_hash":terminal_mod.POLICY_HASH,"policy_version":"C4.17",
      "results":{"AAA":{"status":"MC_PASS_PRIMARY"}},
    }
    old_root=terminal_mod.ROOT
    try:
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"nasdaq-xray";root.mkdir()
            terminal_mod.ROOT=root
            base=root/"canonical_mc_bridge_20261005_c417.json"
            base.write_text(json.dumps(common))
            base_sha=terminal_mod.blob_sha(base)
            r2=root/"canonical_mc_bridge_20261005_c417_r2.json"
            repaired={**common,"supersedes_mc_bridge_path":"nasdaq-xray/canonical_mc_bridge_20261005_c417.json",
                      "supersedes_mc_bridge_blob_sha":base_sha}
            r2.write_text(json.dumps(repaired))
            got=terminal_mod.find_mc(price,"PB")
            assert got[0].name==r2.name,(got[0],r2)

            repaired["supersedes_mc_bridge_blob_sha"]="0"*40
            r2.write_text(json.dumps(repaired))
            # A malformed successor is ineligible and MUST NOT suppress its
            # predecessor. The still-valid immutable predecessor remains the
            # sole active authority; this is fail-closed without manufacturing
            # duplicate authority.
            got2=terminal_mod.find_mc(price,"PB")
            assert got2[0].name==base.name,(got2[0],base)
    finally:
        terminal_mod.ROOT=old_root

def test_candidate_local_legal_unknown_does_not_globally_suppress():
    ft={
      "policy_semantics_exact":True,
      "lifecycle_semantics_exact":True,
      "candidate_legal_guard_exact_binding":True,
      "detailed_legal_review_exact":False,
      "results":{
        "GOOD|D":{"candidate_legal_review_status":"PASS"},
        "OTHER|D":{"candidate_legal_review_status":"UNKNOWN"},
      },
    }
    safety={"status":"PASS"}
    assert terminal_mod.candidate_local_research_ready({"GOOD|D"},safety,ft,True) is True
    assert terminal_mod.candidate_local_research_ready({"GOOD|D","OTHER|D"},safety,ft,True) is False

def test_candidate_legal_guard_scope_is_candidate_local():
    deep={
      "a_geometry_rs_event_pass":["A"],
      "b_breakout_rs_event_pass":["B"],
      "d_dk3_pre_r1":["D"],
      "results":{
      "A":{"regime_finalist_pass":True,"A":{"pool":True},"B":{},"D":{}},
      "B":{"regime_finalist_pass":True,"A":{},"B":{"breakout_confirmed":True},"D":{}},
      "C":{"regime_finalist_pass":True,"A":{},"B":{},"D":{}},
      "D":{"regime_finalist_pass":True,"A":{},"B":{},"D":{"dk3_pre_r1":True}},
      "DROP":{"regime_finalist_pass":False,"A":{},"B":{"breakout_confirmed":True},"D":{}},
      "UNK":{"regime_finalist_pass":None,"A":{},"B":{},"D":{"dk3_pre_r1":True}},
      "N":{"regime_finalist_pass":True,"A":{},"B":{},"D":{}},
    }}
    fc={"confirmed":{"C":{"confirmed":True},"DROP":{"confirmed":True},"X":{"confirmed":False}}}
    lifecycle={"records":{
      "old":{"symbol":"L","state":"WATCH_RETEST_REQUIRED"},
      "dead":{"symbol":"DEAD","state":"FAIL_EXPIRED"},
    }}
    got=legal_guard_mod.candidate_scope(deep,fc,lifecycle)
    expected=["A","B","C","D","L"]
    assert got==expected,(got,expected,sorted(legal_guard_mod.LIFECYCLE_ACTIVE_STATES),deep,fc,lifecycle)

def test_cross_session_lifecycle_scope_persists_active_only():
    assert deep_mod.LIFECYCLE_ACTIVE_STATES==ft.LIFECYCLE_PERSIST_STATES
    assert event_req_mod.LIFECYCLE_ACTIVE_STATES==ft.LIFECYCLE_PERSIST_STATES
    assert legal_guard_mod.LIFECYCLE_ACTIVE_STATES==ft.LIFECYCLE_PERSIST_STATES
    prev={
      "asof_et":"2026-10-02",
      "lifecycle_registry":{
        "schema":"XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1",
        "execution":"NONE","real_money":"NO-GO","asof_et":"2026-10-02",
        "records":{
          "pi":{"symbol":"PI","state":"WATCH_RETEST_REQUIRED","last_asof":"2026-10-02"},
          "dead":{"symbol":"DEAD","state":"FAIL_EXPIRED","last_asof":"2026-10-02"},
        },
      },
    }
    assert event_req_mod.lifecycle_scope_from_final(prev,"2026-10-05")==["PI"]
    future={**prev,"asof_et":"2026-10-06"}
    assert event_req_mod.lifecycle_scope_from_final(future,"2026-10-05")==[]
    side={
      "schema":"XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1",
      "execution":"NONE","real_money":"NO-GO","asof_et":"2026-10-05",
      "records":{
        "swks":{"symbol":"SWKS","state":"PRE_G9_TECH_PASS","last_asof":"2026-10-05"},
        "dead2":{"symbol":"DEAD2","state":"FAIL_INVALIDATED_S0","last_asof":"2026-10-05"},
      },
    }
    assert event_req_mod.lifecycle_scope_from_final(prev,"2026-10-05",side)==["SWKS"]

    old_prev,old_side=deep_mod.PREV_FINAL,deep_mod.LIFECYCLE
    try:
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); pf=td/"final.json"; sc=td/"lifecycle.json"
            pf.write_text(json.dumps(prev))
            deep_mod.PREV_FINAL=pf; deep_mod.LIFECYCLE=sc
            assert deep_mod._lifecycle_scope("2026-10-05")==["PI"]
            sc.write_text(json.dumps(side))
            assert deep_mod._lifecycle_scope("2026-10-05")==["SWKS"]
    finally:
        deep_mod.PREV_FINAL,deep_mod.LIFECYCLE=old_prev,old_side

def test_candidate_legal_guard_lifecycle_fallback_matches_final():
    old_prev,old_side=legal_guard_mod.PREV_FINAL,legal_guard_mod.LIFECYCLE
    try:
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            prev=td/"prev_final.json"; side=td/"lifecycle.json"
            embedded={"schema":"XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1","task_id":ft.TASK_ID,
                      "execution":"NONE","real_money":"NO-GO","records":{"p":{"symbol":"PI"}}}
            prev.write_text(json.dumps({"lifecycle_registry":embedded}))
            legal_guard_mod.PREV_FINAL=prev;legal_guard_mod.LIFECYCLE=side
            got,src=legal_guard_mod.load_lifecycle_state()
            assert src=="PREVIOUS_FINAL_EMBEDDED" and got["records"]["p"]["symbol"]=="PI",(src,got)
            sidecar={"schema":"XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1","task_id":ft.TASK_ID,
                     "execution":"NONE","real_money":"NO-GO","records":{"s":{"symbol":"SWKS"}}}
            side.write_text(json.dumps(sidecar))
            got2,src2=legal_guard_mod.load_lifecycle_state()
            assert src2=="SIDECAR" and set(got2["records"])=={"s"},(src2,got2)
    finally:
        legal_guard_mod.PREV_FINAL,legal_guard_mod.LIFECYCLE=old_prev,old_side

def test_future_lifecycle_evidence_rejected():
    reg={"schema":"XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1","task_id":ft.TASK_ID,
         "asof_et":"2026-10-06","execution":"NONE","real_money":"NO-GO",
         "records":{"x":{"symbol":"PI","state":"WATCH_RETEST_REQUIRED","last_asof":"2026-10-06"}}}
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); side=td/"registry.json"; final=td/"final.json"
        side.write_text(json.dumps(reg))
        raised=False
        try: ft.load_lifecycle_registry(None,side,asof="2026-10-05")
        except RuntimeError: raised=True
        assert raised

        old_prev,old_side=legal_guard_mod.PREV_FINAL,legal_guard_mod.LIFECYCLE
        try:
            legal_guard_mod.PREV_FINAL=td/"missing.json"; legal_guard_mod.LIFECYCLE=side
            raised2=False
            try: legal_guard_mod.load_lifecycle_state("2026-10-05")
            except RuntimeError: raised2=True
            assert raised2
        finally:
            legal_guard_mod.PREV_FINAL,legal_guard_mod.LIFECYCLE=old_prev,old_side

def test_resolver_metadata_only_resume_identity():
    base={
      "schema":"XRAY_RESOLVER_EPOCH_REQUEST_V1","status":"READY",
      "task_id":resolver_req_mod.TASK,"asof_et":"2026-10-05",
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "queue_hash":"Q","queue_total":2,"pointer_asof_et":"2026-10-02",
      "settlement_required":True,"settlement_already_proven":False,
      "compiled_policy_blob_sha":"P","compiled_policy_hash":"H","compiled_policy_version":"C4.17",
      "expected20":["2026-09-08","2026-10-05"],
      "price_unknown_count":2,"price_unknown_symbols":["AAA","BBB"],
      "price_unknown_detail":{"AAA":{"price_result":{"status":"UNKNOWN"}},"BBB":{"price_result":{"status":"UNKNOWN"}}},
      "price_blocked_count":0,"price_blocked_symbols":[],
      "symbols":["AAA","BBB"],"symbol_count":2,"symbol_hash":"S",
      "source_price_blob_sha":"PRICE",
      "source_state_blob_sha":"STATE1","source_unknowns_blob_sha":"UNK1",
      "source_overlay_blob_sha":"OV1","source_master_blob_sha":"M1",
      "source_pointer_blob_sha":"PTR1","official_footer":"FOOTER1",
    }
    meta={**base,"source_state_blob_sha":"STATE2","source_unknowns_blob_sha":"UNK2",
          "source_overlay_blob_sha":"OV2","source_master_blob_sha":"M2",
          "source_pointer_blob_sha":"PTR2","official_footer":"FOOTER2"}
    assert resolver_req_mod.resolver_resume_semantic_view(base)==resolver_req_mod.resolver_resume_semantic_view(meta)
    assert resolver_req_mod.resolver_resume_semantic_view(base)!=resolver_req_mod.resolver_resume_semantic_view({**meta,"source_price_blob_sha":"PRICE2"})
    assert resolver_req_mod.resolver_resume_semantic_view(base)!=resolver_req_mod.resolver_resume_semantic_view({**meta,"symbol_hash":"S2"})
    changed={**meta,"price_unknown_detail":{"AAA":{"price_result":{"status":"PASS_PRICE_DV30"}},"BBB":{"price_result":{"status":"UNKNOWN"}}}}
    assert resolver_req_mod.resolver_resume_semantic_view(base)!=resolver_req_mod.resolver_resume_semantic_view(changed)

def test_resolver_bridge_bound_to_exact_pre_run_price_and_scope():
    old_out,old_req,old_manifest=price_recover_mod.OUT,price_recover_mod.RESOLVER_REQUEST,price_recover_mod.RESOLVER_CHUNK_MANIFEST
    try:
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            out=td/"price.json"; req=td/"request.json"; manifest=td/"manifest.json"
            out.write_text(json.dumps({"schema":"XRAY_CANONICAL_PRICE_DV30_V1","asof_et":"2026-10-05","results":{}})+"\n")
            pb=price_recover_mod.git_blob_sha(out)
            q={
              "schema":"XRAY_RESOLVER_EPOCH_REQUEST_V1","status":"READY","task_id":price_recover_mod.TASK_ID,
              "asof_et":"2026-10-05","execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
              "queue_hash":"Q","compiled_policy_blob_sha":"16c50cc8f887a5234a4be23862d7c8d0e564b0ac",
              "compiled_policy_hash":"68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4",
              "compiled_policy_version":"C4.17","source_price_blob_sha":pb,
              "symbols":["AAA","BBB"],"symbol_count":2,"symbol_hash":"S",
              "price_unknown_symbols":["AAA","BBB"],
            }
            req.write_text(json.dumps(q,sort_keys=True)+"\n")
            rb=price_recover_mod.git_blob_sha(req)
            cm={
              "schema":"XRAY_RESOLVER_REQUEST_CHUNK_MANIFEST_V1","task_id":price_recover_mod.TASK_ID,
              "asof_et":"2026-10-05","execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
              "request_blob_sha":rb,"queue_hash":"Q","symbol_hash":"S","symbol_count":2,"coverage_complete":True,
            }
            manifest.write_text(json.dumps(cm,sort_keys=True)+"\n")
            price_recover_mod.OUT=out; price_recover_mod.RESOLVER_REQUEST=req; price_recover_mod.RESOLVER_CHUNK_MANIFEST=manifest
            bridge={
              "source_price_blob_sha":pb,"source_request_blob_sha":"OLD_REQUEST","source_manifest_blob_sha":"OLD_MANIFEST",
              "symbols":["AAA","BBB"],"symbol_count":2,"symbol_hash":"S","price_unknown_symbols":["AAA","BBB"],
            }
            ok,role,reason=price_recover_mod.resolver_bridge_input_binding(bridge,"2026-10-05","Q")
            assert ok and role=="SEMANTIC_REBIND_EXACT_SOURCE_PRICE_AND_SCOPE" and reason is None,(ok,role,reason)
            bridge2={**bridge,"source_price_blob_sha":"WRONG"}
            assert price_recover_mod.resolver_bridge_input_binding(bridge2,"2026-10-05","Q")[0] is False
            bridge3={**bridge,"symbols":["AAA"],"symbol_count":1,"symbol_hash":"X","price_unknown_symbols":["AAA"]}
            assert price_recover_mod.resolver_bridge_input_binding(bridge3,"2026-10-05","Q")[0] is False
            q2={**q,"source_price_blob_sha":"WRONG"}
            req.write_text(json.dumps(q2,sort_keys=True)+"\n")
            cm["request_blob_sha"]=price_recover_mod.git_blob_sha(req)
            manifest.write_text(json.dumps(cm,sort_keys=True)+"\n")
            assert price_recover_mod.resolver_bridge_input_binding(bridge,"2026-10-05","Q")[0] is False
    finally:
        price_recover_mod.OUT,price_recover_mod.RESOLVER_REQUEST,price_recover_mod.RESOLVER_CHUNK_MANIFEST=old_out,old_req,old_manifest


def test_family_c_event_request_covers_boundary_amc_source_session():
    past,future=event_req_mod.sessions("2026-10-05")
    assert len(past)==12 and len(future)==8,(past,future)
    assert past[-1]=="2026-10-05",past
    # AMC after past[0] close maps reaction0 to past[1]. Current ASOF past[11]
    # is exactly 10 sessions later and must remain discoverable.
    assert len(past)-2==10,past

def test_candidate_legal_guard_phrase_severity():
    boiler="the credit agreement contains customary events of default and financial covenants and other standard provisions"
    assert legal_guard_mod._phrase_flags(boiler,legal_guard_mod.HARD_PHRASES)==[]
    risk=legal_guard_mod._phrase_flags(boiler,legal_guard_mod.RISK_PHRASES)
    assert "EVENT_OF_DEFAULT_REFERENCE" in risk
    assert "COVENANT_REFERENCE" in risk
    hard="management concluded there is substantial doubt about our ability to continue as a going concern"
    assert "SUBSTANTIAL_DOUBT_GOING_CONCERN" in legal_guard_mod._phrase_flags(hard,legal_guard_mod.HARD_PHRASES)
    src=(ROOT/"build_candidate_legal_guard.py").read_text()
    assert 'ANNUAL={"10-K","20-F","40-F"}' in src
    assert "NO_RECENT_ANNUAL_FILING_BEFORE_ASOF" in src
    assert "LATEST_ANNUAL_THROUGH_ASOF_WITH_ALL_LATER_PERIODIC_CURRENT_AND_OFFERING_FILINGS" in src
    assert "_ticker_cik_map(scope) if scope else ({},{},[])" in src
    old_cache=legal_guard_mod.CIK_CACHE
    try:
        with tempfile.TemporaryDirectory() as td:
            cp=Path(td)/"sec_ticker_cik_cache.json"
            cp.write_text(json.dumps({
              "schema":"XRAY_SEC_TICKER_CIK_CACHE_V1","execution":"NONE","real_money":"NO-GO",
              "unknown_never_pass":True,"records":{"PI":{"cik":"0001114995","title":"IMPINJ INC"}}
            }))
            legal_guard_mod.CIK_CACHE=cp
            cmap,csrc,cerr=legal_guard_mod._ticker_cik_map(["PI","MISS"],allow_network=False)
            assert cmap["PI"]=="0001114995" and "MISS" not in cmap,(cmap,csrc,cerr)
            assert csrc["PI"]=="DURABLE_SEC_COMPANY_TICKERS_SNAPSHOT"
            assert cerr==[]
    finally:
        legal_guard_mod.CIK_CACHE=old_cache

def test_workflow_race_and_pre_mc_freeze_contracts():
    final_wf=(REPO/".github/workflows/xray-canonical-current-final.yml").read_text()
    assert "group: xray-canonical-current-final-c417" in final_wf
    assert "cancel-in-progress: ${{ github.event_name == 'push' }}" in final_wf
    assert "python nasdaq-xray/semantic_cache_diff.py" in final_wf
    hard_guard=final_wf.split('changed="$(git diff --name-only',1)[1].split('cache_changed="$(git diff --name-only',1)[0]
    assert "nasdaq-xray/canonical_benchmark_cache/**" not in hard_guard
    assert "nasdaq-xray/semantic_cache_diff.py" in hard_guard
    assert "XRAY_BENCHMARK_CACHE_DRIFT=BYTE_ONLY_GZIP_HEADER_OR_EXACT_PAYLOAD" in final_wf
    payload=b"date,close\\n2026-10-05,1.0\\n"
    gz1=gzip.compress(payload,mtime=1); gz2=gzip.compress(payload,mtime=2)
    assert gz1!=gz2 and cache_diff.gzip_payload_equal(gz1,gz2)
    assert not cache_diff.gzip_payload_equal(gz1,gzip.compress(payload+b"x",mtime=2))
    assert "Fail closed when exact event binding is unavailable" in final_wf
    assert "steps.event.outputs.ready != 'true' && steps.event.outputs.upstream_epoch_drift != 'true'" in final_wf
    assert "XRAY_FINAL_EVENT_BINDING=FAIL_CLOSED" in final_wf
    assert "Healthy no-op while current upstream epoch is incomplete" in final_wf
    assert 'print("upstream_epoch_drift=true")' in final_wf
    assert 'master_asof!=req_asof or price_asof!=req_asof' in final_wf
    assert 'int(p.get("unknown_count",-1))!=0' in final_wf
    assert "XRAY_FINAL_UPSTREAM_EPOCH=WAITING_NOOP" in final_wf
    # Production source drift must stale-abort an in-flight Final. Test-only
    # file edits are intentionally excluded so a test maintenance commit cannot
    # preempt or invalidate an otherwise exact-bound production epoch.
    critical=["nasdaq-xray/alpha_semantics.py","nasdaq-xray/family_c_engine.py",
      "nasdaq-xray/deep_pre_r1_shadow.py","nasdaq-xray/build_candidate_legal_guard.py",
      "nasdaq-xray/final_tech_shadow.py"]
    test_only=["nasdaq-xray/test_alpha_semantics.py","nasdaq-xray/test_deep_repair_regressions.py"]
    stale=final_wf[final_wf.index('changed="$(git diff'):]
    for p in critical: assert p in stale,("FINAL_STALE_GUARD_MISSING",p)
    for p in test_only: assert p not in stale,("FINAL_TEST_ONLY_SHOULD_NOT_STALE_PRODUCTION",p)
    for p in ("nasdaq-xray/canonical_current_master_manifest.json","nasdaq-xray/canonical_current_price_dv30.json"):
        assert p in stale,("FINAL_UPSTREAM_STALE_GUARD_MISSING",p)
    assert "nasdaq-xray/canonical_candidate_lifecycle_registry.json" in final_wf
    assert "python nasdaq-xray/test_alpha_semantics.py" in final_wf
    assert "python nasdaq-xray/test_deep_repair_regressions.py" in final_wf
    assert "current_source_binding=false" in final_wf
    assert 'r.get(k)!=v for k,v in current_sources.items()' in final_wf

    post=(REPO/".github/workflows/xray-canonical-current-post-mc.yml").read_text()
    assert "Fail closed on ambiguous MC binding" in post
    post_stale=post[post.index('changed="$(git diff'):]
    for p in ("nasdaq-xray/canonical_current_master_manifest.json","nasdaq-xray/canonical_current_price_dv30.json"):
        assert p in post_stale,("POST_MC_UPSTREAM_STALE_GUARD_MISSING",p)
    assert "steps.mc.outputs.binding_fault == 'true'" in post
    assert "XRAY_POST_MC_BINDING=FAIL_CLOSED_DUPLICATE" in post
    assert "Healthy no-op while resolver or MC commit is pending" in post
    assert "XRAY_POST_MC=BLOCKED_UPSTREAM_PENDING" in post
    assert "supersedes_mc_bridge_path" in post and "supersedes_mc_bridge_blob_sha" in post
    assert "Revalidate reused HISTORY and hydrate same-run technical cache" in post
    assert "old.get(\"pass_hash\")==new.get(\"pass_hash\")" in post
    assert 'XRAY_STAGE1_CACHE_REQUIRED: "1"' in post
    assert 'XRAY_BREADTH_CACHE_REQUIRED: "1"' in post
    assert "XRAY_BREADTH_HISTORY_CACHE_DIR" in post
    assert "XRAY_TECHNICAL_BENCHMARK_CACHE" in post
    assert 'XRAY_DEEP_CACHE_REQUIRED: "1"' in post
    assert "XRAY_DEEP_HISTORY_CACHE_DIR" in post

    # Partial upstream coverage must remain fail-closed in the terminal, but it
    # must not globally abort event/final evaluation of the known candidate scope.
    post_gate=post.split("- name: Structural post-MC gate",1)[1].split("- name: Commit current post-MC artifacts",1)[0]
    assert 'assert s["unknown_count"]==0' not in post_gate
    assert 'assert r["breadth_missing_count"]==0' not in post_gate
    assert 'coverage_unknowns' in post_gate
    assert 'upstream_coverage_complete' in post_gate
    assert 'request_scope_complete' in post_gate
    assert 'UNKNOWN_STAGE1_LEAKED_INTO_TRIGGER_SCOPE' in post_gate

    s1=(ROOT/"stage1_shadow.py").read_text()
    reg=(ROOT/"regime_breadth_shadow.py").read_text()
    assert "SINA_SAME_RUN_CACHE_MISSING" in s1 and "HISTORY_CACHE_REQUIRED" in s1
    assert "if HISTORY_CACHE_REQUIRED:" in reg
    assert 'HISTORY_CACHE_REQUIRED and sym!="QQQ"' not in reg

    ftsrc=(ROOT/"final_tech_shadow.py").read_text()
    assert "CORPORATE_ACTION_RECONCILIATION_UNPROVEN_FOR_FINALISTS" in ftsrc
    assert "and lifecycle_semantics_exact" in ftsrc

    er_src=(ROOT/"build_current_event_request.py").read_text()
    term_src=(ROOT/"build_current_terminal.py").read_text()
    assert 'assert int(s.get("unknown_count",0))==0' not in er_src
    assert 'assert int(r.get("breadth_missing_count",0))==0' not in er_src
    assert '"coverage_unknowns"' in er_src and '"upstream_coverage_complete"' in er_src
    assert '"request_scope_complete":True' in er_src
    assert '"coverage_complete":not (' not in er_src
    assert 'assert st["unknown_count"]==0' not in term_src
    assert 'rg["current_core_count"]==len(lpass) and rg["breadth_missing_count"]==0' not in term_src
    assert '"stage1_unknown":int(st["unknown_count"])' in term_src
    assert '"breadth_missing":int(rg["breadth_missing_count"])' in term_src
    assert '"regime_unknown":0 if rg.get("regime") in {"STRONG","MIXED","WEAK"} else 1' in term_src
    assert '"lifecycle_regime_unknown":int(ft.get("regime_revalidation_unknown_count",0))' in term_src
    assert '"detailed_legal_review_unknown":0 if ft.get("detailed_legal_review_exact") is True else 1' in term_src
    deep_src=(ROOT/"deep_pre_r1_shadow.py").read_text()
    assert '"regime_finalist_pass":regime_finalist_pass' in deep_src
    assert 'outres[s].get("regime_finalist_pass") is True' in deep_src
    assert "qqq_scale_breaks=mechanical_scale_breaks(qqq,260)" in deep_src
    assert "qqq_split_suspects=mechanical_split_suspects(qqq,260)" in deep_src
    assert "if qqq_scale_breaks or qqq_split_suspects:" in deep_src
    assert '"lifecycle_revalidation":dict(sorted(lifecycle_revalidation.items()))' in deep_src
    assert "history_syms=sorted(set(syms)|set(lifecycle_scope))" in deep_src
    assert "_regime_finalist_allowed" in ftsrc
    assert "WATCH_REGIME_REVALIDATION_REQUIRED" in ftsrc and "WATCH_REGIME_UNKNOWN" in ftsrc
    assert "candidate_local_research_ready" in term_src
    assert "PARTIAL_UNKNOWN" in term_src
    resolver_src=(ROOT/"build_current_resolver_request.py").read_text()
    assert "XRAY_RESOLVER_REQUEST_CHUNK_MANIFEST_V1" in resolver_src
    assert "XRAY_RESOLVER_REQUEST_CHUNK_V1" in resolver_src
    assert "CHUNK_SIZE=max(1,min(100" in resolver_src
    assert '"request_blob_sha":request_blob' in resolver_src
    pre_mc_wf=(REPO/".github/workflows/xray-canonical-current-pre-mc.yml").read_text()
    assert "canonical_current_resolver_chunk_manifest.json" in pre_mc_wf
    assert 'canonical_current_resolver_chunk_[0-9][0-9][0-9][0-9].json' in pre_mc_wf
    assert 'rebuilt==q["symbols"]' in pre_mc_wf
    structural_gate=pre_mc_wf.split("- name: Structural gate",1)[1].split("- name: Commit current pre-MC artifacts",1)[0]
    assert 'cm=json.load(open("nasdaq-xray/canonical_current_resolver_chunk_manifest.json"))' in structural_gate

    # C4.17 detailed legal/filing review is finalist-local. The global LEGAL
    # phase is only a shell/identity screen and may never by itself authorize R92.
    legal_src=(ROOT/"legal_phase.py").read_text()
    assert '"legal_scope":"GLOBAL_SHELL_IDENTITY_ONLY"' in legal_src
    assert '"detailed_candidate_filing_review_complete":False' in legal_src
    assert '"SEPARATE_FINALIST_GUARD_REQUIRED"' in legal_src
    assert "_load_candidate_legal_guard" in ftsrc
    assert "DETAILED_LEGAL_REVIEW_NOT_PROVEN" in ftsrc
    assert '"detailed_legal_review_exact"' in ftsrc
    assert "CANDIDATE_LEGAL_GUARD_DEEP_BINDING_MISMATCH" in ftsrc
    assert "CANDIDATE_LEGAL_GUARD_FAMILY_C_BINDING_MISMATCH" in ftsrc
    assert "CANDIDATE_LEGAL_GUARD_LIFECYCLE_BINDING_MISMATCH" not in ftsrc
    assert "DIAGNOSTIC_PRE_FINAL_SCOPE_AUGMENTATION" in ftsrc
    assert "CANDIDATE_LEGAL_GUARD_POLICY_BLOB_MISMATCH" in ftsrc
    assert "CANDIDATE_LEGAL_GUARD_POLICY_HASH_MISMATCH" in ftsrc
    assert "CANDIDATE_LEGAL_GUARD_CIK_CACHE_PATH_MISMATCH" in ftsrc
    assert "CANDIDATE_LEGAL_GUARD_CIK_CACHE_BINDING_MISMATCH" in ftsrc
    assert '"candidate_legal_guard_exact_binding"' in ftsrc
    assert '"candidate_legal_risk_flags"' in ftsrc
    assert "Build exact-bound detailed finalist legal guard" in final_wf
    assert "python nasdaq-xray/build_candidate_legal_guard.py" in final_wf
    assert "Validate detailed finalist legal guard binding" in final_wf
    assert "nasdaq-xray/canonical_candidate_legal_guard.json" in final_wf
    push_block=final_wf.split("permissions:",1)[0]
    assert '"nasdaq-xray/build_candidate_legal_guard.py"' in push_block
    assert '"nasdaq-xray/sec_ticker_cik_cache.json"' in push_block
    assert "nasdaq-xray/sec_ticker_cik_cache.json" in stale
    assert '"nasdaq-xray/canonical_candidate_legal_guard.json"' not in push_block
    ca_block=ftsrc[ftsrc.index("def candidate_corporate_action_reconcile"):ftsrc.index("def _frozen_geometry")]
    assert "UNKNOWN_PRIMARY_CORPORATE_ACTION_EVIDENCE_REQUIRED" not in ca_block
    assert "return x2.reset_index(drop=True),status,events,True" in ca_block
    assert 'ft.get("candidate_legal_guard_exact_binding") is True' in term_src
    assert '"candidate_pre_g9_legal_pass"' in term_src
    assert '"all_finalists_detailed_legal_review_exact"' in term_src
    assert '"regime_no_missing":True' not in term_src
    assert '"regime_no_missing":bool(not breadth_missing and rg.get("regime") in {"STRONG","MIXED","WEAK"})' in term_src

    # Repair-time CI must be latest-wins and must exercise the detailed legal
    # guard itself; otherwise rapid source commits can starve production runs
    # and legal-guard changes can bypass deterministic regression coverage.
    phase_wf=(REPO/".github/workflows/xray-dynamic-phase-regression.yml").read_text()
    policy_wf=(REPO/".github/workflows/xray-dynamic-policy-invariants.yml").read_text()
    for wf,group in ((phase_wf,"xray-dynamic-phase-regression"),(policy_wf,"xray-dynamic-policy-invariants")):
        assert f"group: {group}" in wf
        assert "cancel-in-progress: true" in wf
        push=wf.split("permissions:",1)[0]
        assert '"nasdaq-xray/build_candidate_legal_guard.py"' in push
        assert '"nasdaq-xray/sec_ticker_cik_cache.json"' in push
        assert "nasdaq-xray/build_candidate_legal_guard.py \\" in wf

    pre=(REPO/".github/workflows/xray-canonical-current-pre-mc.yml").read_text()
    marker="- name: Completed-session epoch rollover guard"; assert marker in pre
    guard=pre.split(marker,1)[1].split("- name: Recover corrupted frozen pre-MC snapshot",1)[0]
    assert "same_completed_epoch=bool(pointer_asof and latest_completed==pointer_asof)" in guard
    assert "current_epoch_artifact_exists=bool(price_asof and price_asof==latest_completed)" in guard
    assert "active_completed_epoch=bool(same_completed_epoch or current_epoch_artifact_exists)" in guard
    assert "policy_replay=bool(active_completed_epoch and price_integrity_ok and not price_semantics_ok)" in guard
    assert "bootstrap_rebuild=bool(" in guard
    assert "deferred_bootstrap_artifact(px,latest_completed)" in guard
    assert "recover=bool(active_completed_epoch and not price_integrity_ok and not bootstrap_rebuild)" in guard
    assert "XRAY_PRICE_FORCE_POLICY_REPLAY" in pre
    assert "identity_replay=bool(" in guard
    assert 'mf.get("identity_ruleset")!="V5_SEC_SPAC_PROOF_AT_MASTER"' in guard
    assert "build=bool(not active_completed_epoch or bootstrap_rebuild or identity_replay)" in guard
    assert "REPLAY_COMPLETED_EPOCH_UNDER_CURRENT_IDENTITY_POLICY" in guard
    assert "REBUILD_DEFERRED_DV30_BOOTSTRAP" in guard
    assert 'out.write(f"recovery_asof={frozen_asof}\\n")' in guard
    assert "terminal_result" not in guard and "FULL_E2E_RESEARCH_PASS" not in guard
    recovery=pre.split("- name: Recover corrupted frozen pre-MC snapshot",1)[1].split("- name: Frozen completed epoch healthy no-op",1)[0]
    assert "XRAY_RECOVERY_ASOF:" in recovery
    assert "steps.rollover.outputs.recovery_asof" in recovery
    assert "python nasdaq-xray/recover_pre_mc_snapshot.py" in recovery
    recsrc=(ROOT/"recover_pre_mc_snapshot.py").read_text()
    assert "NO_VALID_SAME_ASOF_PRICE_SNAPSHOT" in recsrc
    assert 'CURRENT_PRICE_RULE=">=5"' in recsrc
    assert 'CURRENT_DV30_RULE=">=50000000 exact30 median"' in recsrc
    assert "CURRENT_POLICY_HASH" in recsrc and "CURRENT_POLICY_BLOB" in recsrc
    assert "canonical_current_resolver_chunk_manifest.json" in recsrc
    assert "canonical_current_resolver_chunk_[0-9][0-9][0-9][0-9].json" in recsrc
    assert 'assert rebuilt==req["symbols"]' in recsrc
    assert "RECOVERY_PUSH_RACE_EXHAUSTED" in recsrc
    assert 'manifest=show_json(sha,"nasdaq-xray/canonical_current_resolver_chunk_manifest.json")' in recsrc
    assert 'declared=manifest.get("chunks") or []' in recsrc
    assert 'assert existing_rel==declared_paths' in recsrc
    assert 'assert blob(cp)==row["blob_sha"]' in recsrc
    assert "\'nasdaq-xray/canonical_current_resolver_chunk_*.json\'" in pre
    assert 'assert req["source_price_blob_sha"]==blob(ROOT/"canonical_current_price_dv30.json")' in recsrc
    assert 'assert int(price["source_master_count"])==int(master["queue_total"])' in recsrc
    assert '"resolver_chunks":len(declared)' in recsrc
    assert '"resolver_chunks":len(chunks)' not in recsrc
    def core(pointer_asof,latest_completed,price_asof,integrity_ok,semantics_ok):
        same=bool(pointer_asof and latest_completed==pointer_asof)
        current=bool(price_asof and price_asof==latest_completed)
        active=bool(same or current)
        return {
          "build":not active,
          "recover":bool(active and not integrity_ok),
          "policy_replay":bool(active and integrity_ok and not semantics_ok),
        }
    assert core("2026-10-02","2026-10-02","2026-10-02",True,True)=={"build":False,"recover":False,"policy_replay":False}
    assert core("2026-10-02","2026-10-02","2026-10-02",True,False)=={"build":False,"recover":False,"policy_replay":True}
    assert core("2026-10-02","2026-10-02","2026-10-02",False,False)=={"build":False,"recover":True,"policy_replay":False}
    assert core("2026-10-02","2026-10-05","2026-10-05",True,True)=={"build":False,"recover":False,"policy_replay":False}
    assert core("2026-10-02","2026-10-05","2026-10-05",True,False)=={"build":False,"recover":False,"policy_replay":True}
    assert core("2026-10-02","2026-10-05","2026-10-02",False,False)=={"build":True,"recover":False,"policy_replay":False}

def test_detailed_legal_gate_is_only_for_actual_pre_g9_promotion():
    # Detailed filing review is a candidate-promotion guard, not a prerequisite
    # for classifying a deterministic technical non-pass. A provider outage
    # must never turn WATCH/FAIL into UNKNOWN, while PRE_G9 still requires PASS.
    assert ft.detailed_legal_required_for_technical_state("PRE_G9_TECH_PASS")
    for state in (
        "WATCH_CHASE_RETEST_REQUIRED","WATCH_RECONFIRMATION_REQUIRED",
        "WATCH_RETEST_REQUIRED","WATCH_EXTENSION_RESET_REQUIRED",
        "WATCH_REGIME_REVALIDATION_REQUIRED","WATCH_REGIME_UNKNOWN",
        "FAIL_R1_ENTRY_OVERLAP","FAIL_RR","UNKNOWN",None
    ):
        assert not ft.detailed_legal_required_for_technical_state(state),state


def test_terminal_lifecycle_state_contract_covers_final_persistence():
    # Terminal may accept extra diagnostic states, but it must never reject a
    # lifecycle state that Final is explicitly allowed to persist.
    assert set(ft.LIFECYCLE_PERSIST_STATES) <= set(terminal_mod.LIFECYCLE_TERMINAL_ALLOWED_STATES)
    assert "WATCH_EVENT_UNKNOWN_OR_BLOCKED" in terminal_mod.LIFECYCLE_TERMINAL_ALLOWED_STATES


def main():
    test_r1_no_future_mutation_and_confirmation(); test_r1_pivot_boundary_is_not_overhead_but_entry_overlap_is(); test_resistance_role_change_state_machine()
    test_final_history_normalizer_preserves_ohlcv()
    test_regime_interval_bounds_and_finalist_gate()
    test_corporate_action_absence_vs_real_scale_break()
    test_d_reclaim_cannot_use_same_bar_that_confirms_hl(); test_family_a_trigger_time_reconstruction_survives_later_structure(); test_family_a_age5_unrecorded_trigger_is_not_rediscovered(); test_family_a_final_geometry_revalidation()
    test_lifecycle_expiry_and_frozen_stability(); test_lifecycle_regime_revalidation_persists_without_pass(); test_lifecycle_persistence_roundtrip()
    test_mc_bridge_immutable_supersession()
    test_candidate_local_legal_unknown_does_not_globally_suppress()
    test_candidate_legal_guard_scope_is_candidate_local()
    test_cross_session_lifecycle_scope_persists_active_only()
    test_candidate_legal_guard_lifecycle_fallback_matches_final()
    test_future_lifecycle_evidence_rejected()
    test_detailed_legal_gate_is_only_for_actual_pre_g9_promotion()
    test_terminal_lifecycle_state_contract_covers_final_persistence()
    test_resolver_metadata_only_resume_identity()
    test_resolver_bridge_bound_to_exact_pre_run_price_and_scope()
    test_family_c_event_request_covers_boundary_amc_source_session(); test_candidate_legal_guard_phrase_severity()
    test_workflow_race_and_pre_mc_freeze_contracts()
    print({"status":"PASS","tests":["R1_NO_FUTURE_MUTATION","R1_PLUS2_CONFIRMATION_NO_LEAK","R1_PIVOT_BOUNDARY_NOT_OVERHEAD",
      "RESISTANCE_ROLE_CHANGE_STATE_MACHINE","FINAL_HISTORY_OHLCV_BINDING","REGIME_INTERVAL_BOUNDS_AND_FINALIST_GATE","CORPORATE_ACTION_NONE_VS_SCALE_BREAK_FAIL_CLOSED","D_RECLAIM_AFTER_HL_AVAILABILITY","FAMILY_A_TRIGGER_TIME_RECONSTRUCTION","FAMILY_A_AGE5_UNRECORDED_NOT_REDISCOVERED","FAMILY_A_FINAL_GEOMETRY_REVALIDATION","RETEST_WINDOW_EXPIRES_AFTER_5","MODEL_HORIZON_EXPIRES_AFTER_8",
      "FROZEN_LEVELS_NEXT_ASOF_STABLE","LIFECYCLE_REGIME_REVALIDATION_PERSISTS","LIFECYCLE_PERSISTENCE_ROUNDTRIP","MC_BRIDGE_IMMUTABLE_SUPERSESSION",
      "FINAL_ALPHA_STALE_SOURCE_GUARD","PARTIAL_COVERAGE_DOES_NOT_GLOBAL_ABORT",
      "DETAILED_FINALIST_LEGAL_FAIL_CLOSED","CANDIDATE_LOCAL_LEGAL_UNKNOWN_ISOLATION","FINAL_VERIFIED_MARKET_GAP_NOT_DOUBLE_BLOCKED","DETAILED_LEGAL_GUARD_EXACT_SOURCE_BINDING","DETAILED_LEGAL_GUARD_POLICY_BINDING","DETAILED_LEGAL_GUARD_NONCIRCULAR_LIFECYCLE","CROSS_SESSION_LIFECYCLE_ACTIVE_ONLY","FAMILY_C_EVENT_REQUEST_BOUNDARY_AMC","FUTURE_LIFECYCLE_EVIDENCE_REJECTED","DETAILED_LEGAL_GUARD_LIFECYCLE_FALLBACK_PARITY","DETAILED_LEGAL_GUARD_BOILERPLATE_SEVERITY","DETAILED_LEGAL_GUARD_ANNUAL_PLUS_QUARTERLY_SCOPE","DETAILED_LEGAL_GUARD_EMPTY_SCOPE_NO_NETWORK","TERMINAL_DETAILED_LEGAL_FULL_E2E_BLOCKER","DETAILED_LEGAL_GUARD_NO_SELF_TRIGGER",
      "POST_MC_PARTIAL_COVERAGE_GATE","TERMINAL_LIFECYCLE_STATE_CONTRACT","PRE_MC_COMPLETED_ASOF_FREEZE_TRUTH_TABLE"]})

if __name__=="__main__": main()
