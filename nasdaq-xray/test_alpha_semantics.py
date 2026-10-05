#!/usr/bin/env python3
from __future__ import annotations
import pathlib,sys
import pandas as pd
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from alpha_semantics import (
    wilder_atr,ema_seeded,drawdown_metrics,nearest_active_resistance,
    extension_diagnostics,retest_bar,setup_id,
    find_recent_b_trigger,mechanical_scale_breaks,
    apply_split_events,mechanical_split_suspects
)
from final_tech_shadow import eval_one,_is_depositary_security_name

def frame(n=90):
    rows=[]
    for i in range(n):
        close=100.0
        rows.append({"date":pd.Timestamp("2026-01-02")+pd.Timedelta(days=i),
                     "open":100.0,"high":105.0,"low":95.0,"close":close,"volume":1_000_000.0})
    return pd.DataFrame(rows)

def main():
    # Wilder first TR is undefined; first ATR seed is after 14 valid transitions.
    d=frame(20)
    a=wilder_atr(d,14)
    assert pd.isna(a.iloc[13]) and not pd.isna(a.iloc[14]),a.tolist()

    # Canonical EMA seed is SMA(n), not pandas first-value seed.
    s=pd.Series([1.,2.,3.,4.,5.,6.])
    e=ema_seeded(s,3)
    assert pd.isna(e.iloc[1]) and abs(e.iloc[2]-2.0)<1e-12,e.tolist()
    assert abs(e.iloc[3]-3.0)<1e-12,e.tolist()

    # D-pool definitions: 252 uses current close vs high; 120 uses worst close drawdown.
    rows=[]
    for i in range(260):
        close=100.0
        high=101.0
        if i==150: close=150.0;high=151.0
        if i==190: close=105.0;high=106.0
        rows.append({"date":pd.Timestamp("2025-01-01")+pd.Timedelta(days=i),
                     "open":close,"high":high,"low":close-1,"close":close,"volume":1e6})
    dd=drawdown_metrics(pd.DataFrame(rows))
    assert dd["current_drawdown_252"] < -0.30,dd
    assert dd["max_drawdown_close_120"] < -0.25,dd

    # R1 must be structural and trigger-1 bounded: an unconfirmed high on trigger day
    # cannot become R1. A confirmed strict swing high before trigger can.
    d=frame(90)
    d.loc[35,"high"]=120.0
    d.loc[34,"high"]=106.0;d.loc[36,"high"]=106.0
    d.loc[33,"high"]=105.5;d.loc[37,"high"]=105.5
    d.loc[69:71,"high"]=107.0  # plateau: ordinary highs, never a strict confirmed swing
    d.loc[80,"high"]=130.0  # trigger-day/future point must never leak into trigger-1 R1
    r=nearest_active_resistance(d,80,10.0,100.0,102.5,102.5)
    assert r["status"]=="PASS",r
    assert r["T1"]>110.0 and r["T1"]<125.0,r

    # Entry-band overlap can never be skipped for a farther target.
    d2=frame(90)
    d2.loc[35,"high"]=121.0
    d2.loc[34,"high"]=106.0;d2.loc[36,"high"]=106.0
    d2.loc[33,"high"]=105.5;d2.loc[37,"high"]=105.5
    r2=nearest_active_resistance(d2,80,10.0,120.0,122.5,122.5)
    assert r2["status"]=="PASS" and r2["target_overlap"] is True,r2

    # Three-session extension uses close_t-close_t-3. A valid intervening retest is a reset.
    x=frame(8)
    x.loc[4,"close"]=100.0;x.loc[5,"low"]=120.5;x.loc[5,"close"]=121.0
    x.loc[6,"close"]=123.0;x.loc[7,"close"]=125.0
    ex=extension_diagnostics(x,10.0,120.0,122.5)
    assert ex["move3_atr"]>2.0 and ex["reset_between_tminus3_and_t"] is True,ex
    assert ex["extension_veto"] is False,ex
    x.loc[5,"low"]=123.0;x.loc[5,"close"]=123.5
    ex2=extension_diagnostics(x,10.0,120.0,122.5)
    assert ex2["move3_atr"]>2.0 and ex2["reset_between_tminus3_and_t"] is False,ex2
    assert ex2["extension_veto"] is True,ex2

    row=pd.Series({"low":121.5,"close":122.0})
    assert retest_bar(row,120.0,122.5) is True
    assert setup_id("TEST","D","2026-10-02",120,100,10)==setup_id("TEST","D","2026-10-02",120,100,10)

    # B trigger persists when it happened two completed sessions ago.
    rows=[]
    for i in range(70):
        if i<48:
            o=100.0;h=102.0;l=98.0;cl=100.0;vol=1_000_000.0
        else:
            o=100.0;h=100.5;l=99.5;cl=100.0;vol=1_000_000.0
        rows.append({"date":pd.Timestamp("2026-04-01")+pd.Timedelta(days=i),
                     "open":o,"high":h,"low":l,"close":cl,"volume":vol})
    bf=pd.DataFrame(rows)
    t=len(bf)-3
    bf.loc[t,"open"]=100.8;bf.loc[t,"high"]=102.5;bf.loc[t,"low"]=100.7
    bf.loc[t,"close"]=102.0;bf.loc[t,"volume"]=3_000_000.0
    b=find_recent_b_trigger(bf,3)
    assert b and b["breakout_confirmed"] is True and b["trigger_age_sessions"]==2,b

    # A likely mechanical split/ADR-ratio scale discontinuity is never silently ignored.
    sf=frame(40)
    sf.loc[20:,"open"]=50.0;sf.loc[20:,"high"]=52.0;sf.loc[20:,"low"]=48.0;sf.loc[20:,"close"]=50.0
    sb=mechanical_scale_breaks(sf,40)
    assert sb and 1.8<=sb[0]["ratio"]<=2.2,sb
    ss=mechanical_split_suspects(sf)
    assert ss,ss
    adjusted=apply_split_events(sf,[{"date":sf.date.iloc[20].date().isoformat(),
                                     "ratio":2.0,"numerator":2.0,"denominator":1.0}])
    assert abs(float(adjusted.close.iloc[19])-50.0)<1e-12,adjusted.iloc[18:22]
    assert abs(float(adjusted.volume.iloc[19])-2_000_000.0)<1e-12,adjusted.iloc[18:22]
    assert abs(float(adjusted.close.iloc[20])-50.0)<1e-12,adjusted.iloc[18:22]

    # A newly discovered trigger older than three completed sessions is WATCH only;
    # the same frozen setup may become actionable only when it was prospectively recorded.
    hf=frame(270)
    hf[["open","high","low","close"]]=[101.0,103.0,99.0,102.0]
    trigger_idx=len(hf)-5
    td=hf.date.iloc[trigger_idx].date().isoformat()
    frozen={"setup_id":"TEST-HIST","symbol":"TEST","family":"D","trigger_date":td,
            "A":10.0,"P":100.0,"anchor":97.0,"entry_low":100.0,"entry_high":102.5,
            "entry_model":102.5,"chase_limit":105.0,"S0":95.0,"T1":150.0,
            "target_source":"TEST","target_zone":None,"target_overlap":False,
            "synthetic_target":False,"source_geometry":{"trigger_date":td,"P":100.0,"anchor":97.0}}
    g={"trigger_date":td,"P":100.0,"anchor":97.0}
    hr=eval_one("TEST","D",g,hf,"CLEAN_DISCOVERY",frozen=frozen,recorded_before=False)
    assert hr["result"]=="WATCH_HISTORICAL_SETUP",hr
    pr=eval_one("TEST","D",g,hf,"CLEAN_DISCOVERY",frozen=frozen,recorded_before=True)
    assert pr["result"]=="PRE_G9_TECH_PASS",pr

    # A chase has no valid fill now but the frozen setup must survive for a valid retest.
    cf=frame(270)
    cf[["open","high","low","close"]]=[102.0,103.0,99.0,102.0]
    cti=len(cf)-3;ctd=cf.date.iloc[cti].date().isoformat()
    cfr={"setup_id":"TEST-CHASE","symbol":"TEST","family":"D","trigger_date":ctd,
         "A":10.0,"P":100.0,"anchor":97.0,"entry_low":100.0,"entry_high":102.5,
         "entry_model":102.5,"chase_limit":105.0,"S0":95.0,"T1":150.0,
         "target_source":"TEST","target_zone":None,"target_overlap":False,
         "synthetic_target":False,"source_geometry":{"trigger_date":ctd,"P":100.0,"anchor":97.0}}
    cg={"trigger_date":ctd,"P":100.0,"anchor":97.0}
    cf.loc[len(cf)-1,["open","high","low","close"]]=[105.5,107.0,105.0,106.0]
    cr=eval_one("TEST","D",cg,cf,"CLEAN_DISCOVERY",frozen=cfr,recorded_before=True)
    assert cr["result"]=="WATCH_CHASE_RETEST_REQUIRED",cr
    cf.loc[len(cf)-1,["open","high","low","close"]]=[102.2,103.0,101.0,102.0]
    rr=eval_one("TEST","D",cg,cf,"CLEAN_DISCOVERY",frozen=cfr,recorded_before=True)
    assert rr["result"]=="PRE_G9_TECH_PASS",rr

    assert _is_depositary_security_name("Example Corp - American Depositary Shares") is True
    assert _is_depositary_security_name("Example Corp - Common Stock") is False

    print({"status":"PASS","tests":[
      "WILDER_FIRST_TR_UNDEFINED","EMA_SMA_SEED","D_DRAWDOWN_DEFINITIONS",
      "R1_STRUCTURAL_TRIGGER_MINUS1","R1_ENTRY_OVERLAP","EXTENSION_RESET","RETEST_BAR","SETUP_ID_STABLE",
      "B_RECENT_TRIGGER_PERSISTENCE","MECHANICAL_SCALE_BREAK_GUARD","SPLIT_ONLY_RECONCILIATION","HISTORICAL_DISCOVERY_WATCH","CHASE_FROZEN_RETEST_RECOVERY",
      "ADR_RATIO_FAIL_CLOSED_CLASSIFICATION"
    ]})

if __name__=="__main__":
    main()
