#!/usr/bin/env python3
"""Deep repair regressions for C4.17 fail-closed alpha/data-plane semantics."""
from pathlib import Path
import json, tempfile
import pandas as pd
import alpha_semantics as alpha
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
    d=frame(100)
    d.loc[35,"high"]=120.0; d.loc[33:34,"high"]=[105.0,106.0]; d.loc[36:37,"high"]=[106.0,105.0]
    trigger=80
    r1=alpha.nearest_active_resistance(d,trigger,10.0,100.0,102.5,102.5)
    assert r1["status"]=="PASS" and 110.0<r1["T1"]<125.0,r1
    mutated=d.copy(); mutated.loc[trigger:,["open","high","low","close"]]=[900.0,999.0,800.0,950.0]
    r2=alpha.nearest_active_resistance(mutated,trigger,10.0,100.0,102.5,102.5)
    assert r2["status"]==r1["status"] and abs(float(r2["T1"])-float(r1["T1"]))<1e-12,(r1,r2)
    assert bool(r2["target_overlap"])==bool(r1["target_overlap"]),(r1,r2)
    d3=d.copy(); d3.loc[78,"high"]=140.0; d3.loc[76:77,"high"]=[105.0,106.0]; d3.loc[79,"high"]=106.0
    r3=alpha.nearest_active_resistance(d3,trigger,10.0,100.0,102.5,102.5)
    assert r3["status"]=="PASS" and float(r3["T1"])<130.0,r3
    leak=d3.date.iloc[78].date().isoformat()
    for z in r3["zones"]:
        for p in z.get("points") or []:
            assert not (p.get("kind")=="DAILY_SWING_HIGH" and p.get("date")==leak),(z,p)

def test_resistance_role_change_state_machine():
    oldb,oldw,oldg=alpha._base_high_points,alpha._weekly_swing_points,alpha._gap_down_zones
    alpha._base_high_points=lambda prior,atr:[]
    alpha._weekly_swing_points=lambda prior:[]
    alpha._gap_down_zones=lambda prior:[]
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
        alpha._base_high_points,alpha._weekly_swing_points,alpha._gap_down_zones=oldb,oldw,oldg

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

def test_workflow_race_and_pre_mc_freeze_contracts():
    final_wf=(REPO/".github/workflows/xray-canonical-current-final.yml").read_text()
    critical=["nasdaq-xray/alpha_semantics.py","nasdaq-xray/test_alpha_semantics.py",
      "nasdaq-xray/test_deep_repair_regressions.py","nasdaq-xray/family_c_engine.py",
      "nasdaq-xray/deep_pre_r1_shadow.py","nasdaq-xray/final_tech_shadow.py"]
    stale=final_wf[final_wf.index('changed="$(git diff'):]
    for p in critical: assert p in stale,("FINAL_STALE_GUARD_MISSING",p)
    assert "nasdaq-xray/canonical_candidate_lifecycle_registry.json" in final_wf
    assert "python nasdaq-xray/test_alpha_semantics.py" in final_wf
    assert "python nasdaq-xray/test_deep_repair_regressions.py" in final_wf
    pre=(REPO/".github/workflows/xray-canonical-current-pre-mc.yml").read_text()
    marker="- name: Completed-session epoch rollover guard"; assert marker in pre
    guard=pre.split(marker,1)[1].split("- name: Recover corrupted frozen pre-MC snapshot",1)[0]
    assert "same_completed_epoch=bool(pointer_asof and latest_completed==pointer_asof)" in guard
    assert "recover=bool(same_completed_epoch and not price_ok)" in guard
    assert "build=not same_completed_epoch" in guard
    assert "terminal_result" not in guard and "FULL_E2E_RESEARCH_PASS" not in guard
    def core(pointer_asof,latest_completed,price_ok):
        same=bool(pointer_asof and latest_completed==pointer_asof)
        return {"build":not same,"recover":bool(same and not price_ok)}
    assert core("2026-10-02","2026-10-02",True)=={"build":False,"recover":False}
    assert core("2026-10-02","2026-10-02",False)=={"build":False,"recover":True}
    assert core("2026-10-02","2026-10-05",True)=={"build":True,"recover":False}

def main():
    test_r1_no_future_mutation_and_confirmation(); test_resistance_role_change_state_machine()
    test_lifecycle_expiry_and_frozen_stability(); test_lifecycle_persistence_roundtrip()
    test_workflow_race_and_pre_mc_freeze_contracts()
    print({"status":"PASS","tests":["R1_NO_FUTURE_MUTATION","R1_PLUS2_CONFIRMATION_NO_LEAK",
      "RESISTANCE_ROLE_CHANGE_STATE_MACHINE","RETEST_WINDOW_EXPIRES_AFTER_5","MODEL_HORIZON_EXPIRES_AFTER_8",
      "FROZEN_LEVELS_NEXT_ASOF_STABLE","LIFECYCLE_PERSISTENCE_ROUNDTRIP",
      "FINAL_ALPHA_STALE_SOURCE_GUARD","PRE_MC_COMPLETED_ASOF_FREEZE_TRUTH_TABLE"]})

if __name__=="__main__": main()
