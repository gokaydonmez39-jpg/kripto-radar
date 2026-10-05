#!/usr/bin/env python3
from __future__ import annotations
import pathlib,sys
import pandas as pd
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from alpha_semantics import (
    wilder_atr,ema_seeded,drawdown_metrics,nearest_active_resistance,
    extension_diagnostics,retest_bar,setup_id
)

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
    d.loc[70,"high"]=107.0  # ordinary prior high, not a confirmed structural swing
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

    print({"status":"PASS","tests":[
      "WILDER_FIRST_TR_UNDEFINED","EMA_SMA_SEED","D_DRAWDOWN_DEFINITIONS",
      "R1_STRUCTURAL_TRIGGER_MINUS1","R1_ENTRY_OVERLAP","EXTENSION_RESET","RETEST_BAR","SETUP_ID_STABLE"
    ]})

if __name__=="__main__":
    main()
