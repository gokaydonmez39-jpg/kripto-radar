#!/usr/bin/env python3
from __future__ import annotations
import pathlib,sys,tempfile,types
import pandas as pd
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import alpha_semantics as alpha_mod
from alpha_semantics import (
    wilder_atr,ema_seeded,drawdown_metrics,nearest_active_resistance,
    extension_diagnostics,retest_bar,setup_id,
    find_recent_b_trigger,NEW_TRIGGER_DISCOVERY_MAX_AGE,mechanical_scale_breaks,
    apply_split_events,mechanical_split_suspects,_verify_split_events_against_raw,
    family_a_pretrigger_low,trend_pullback_stage1_at
)
import final_tech_shadow as final_mod
from final_tech_shadow import eval_one,_is_depositary_security_name,reconcile_final_result_scope,lifecycle_state_persists,_fresh_deep_family_confirmed
from deep_pre_r1_shadow import evaluate_recent_families
import stage1_shadow as stage1_mod
import history_phase as history_mod
from stage1_shadow import recent_weekly_context
from family_c_engine import eval_event,candidate_corporate_action_reconcile as family_c_ca_reconcile
from build_current_event_request import lifecycle_scope_from_final,event_geometry_scope
from regime_breadth_shadow import close_only_scale_breaks,new_high_low20_flags

def frame(n=90):
    rows=[]
    for i in range(n):
        close=100.0
        rows.append({"date":pd.Timestamp("2026-01-02")+pd.Timedelta(days=i),
                     "open":100.0,"high":105.0,"low":95.0,"close":close,"volume":1_000_000.0})
    return pd.DataFrame(rows)

def main():
    assert NEW_TRIGGER_DISCOVERY_MAX_AGE==3,NEW_TRIGGER_DISCOVERY_MAX_AGE
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

    # A newly completed tight base between t-3 and t is also a canonical reset.
    br=[]
    for i in range(36):
        if i<30:
            o=100.0;h=105.0;l=95.0;cl=100.0
        elif i<35:
            o=100.0;h=101.5;l=98.5;cl=100.0
        else:
            o=129.0;h=131.0;l=129.0;cl=130.0
        br.append({"date":pd.Timestamp("2026-03-02")+pd.Timedelta(days=i),
                   "open":o,"high":h,"low":l,"close":cl,"volume":1_000_000.0})
    breset=pd.DataFrame(br)
    bx=extension_diagnostics(breset,10.0,125.0,127.5)
    assert bx["move3_atr"]>2.0 and bx["pivot_extension"]<0.08,bx
    assert bx["reset_between_tminus3_and_t"] is True and bx["reset_kind"]=="TIGHT_BASE",bx
    assert bx["extension_veto"] is False,bx

    row=pd.Series({"low":121.5,"close":122.0})
    assert retest_bar(row,120.0,122.5) is True

    # Family A proximity is bound to exactly trigger-1, not a multi-bar minimum
    # and not the trigger bar's low.
    af=frame(8)
    af.loc[4,"low"]=99.0
    af.loc[5,"low"]=120.0
    af.loc[6,"low"]=80.0
    assert family_a_pretrigger_low(af,6)==120.0

    # A-family Stage1 is evaluated at the candidate trigger, not today's bar.
    rows=[]
    for i in range(90):
        cl=100.0+i*0.25
        rows.append({"date":pd.Timestamp("2026-01-02")+pd.Timedelta(days=i),
                     "open":cl-0.2,"high":cl+1.0,"low":cl-1.0,"close":cl,"volume":1e6})
    at=pd.DataFrame(rows)
    assert trend_pullback_stage1_at(at,80) is True
    at.loc[89,["open","high","low","close"]]=[80.0,81.0,79.0,80.0]
    assert trend_pullback_stage1_at(at,80) is True
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
    b=find_recent_b_trigger(bf,NEW_TRIGGER_DISCOVERY_MAX_AGE)
    assert b and b["breakout_confirmed"] is True and b["trigger_age_sessions"]==2,b
    # New discovery is bounded to current/prior three completed sessions.
    # A five-session-old trigger may remain live only if it was already durably
    # recorded; it cannot be rediscovered today as a new setup.
    bf5=bf.copy()
    bf5.loc[t,["open","high","low","close","volume"]]=[100.0,100.5,99.5,100.0,1_000_000.0]
    t5=len(bf5)-6
    bf5.loc[t5,["open","high","low","close","volume"]]=[100.8,102.5,100.7,102.0,3_000_000.0]
    b5=find_recent_b_trigger(bf5,NEW_TRIGGER_DISCOVERY_MAX_AGE)
    assert b5 is None,b5
    # Weekly-at-trigger eligibility participates in trigger selection.
    allowed_date=bf.date.iloc[t].date().isoformat()
    only_allowed=find_recent_b_trigger(bf5,NEW_TRIGGER_DISCOVERY_MAX_AGE,{allowed_date})
    assert only_allowed is None,only_allowed
    original_allowed=find_recent_b_trigger(bf,NEW_TRIGGER_DISCOVERY_MAX_AGE,{allowed_date})
    assert original_allowed and original_allowed["trigger_age_sessions"]==2,original_allowed
    # Production deep evaluator must not suppress a recent trigger merely
    # because today's cheap Stage1 snapshot pool changed.
    _,bdeep,_=evaluate_recent_families(bf,bf.copy())
    assert bdeep.get("breakout_confirmed") is True and bdeep.get("trigger_age_sessions")==2,bdeep
    _,bdeep5,_=evaluate_recent_families(bf5,bf5.copy())
    assert bdeep5.get("breakout_confirmed") is not True,bdeep5

    # A likely mechanical split/ADR-ratio scale discontinuity is never silently ignored.
    sf=frame(40)
    sf.loc[20:,"open"]=50.0;sf.loc[20:,"high"]=52.0;sf.loc[20:,"low"]=48.0;sf.loc[20:,"close"]=50.0
    sb=mechanical_scale_breaks(sf,40)
    assert sb and 1.8<=sb[0]["ratio"]<=2.2,sb
    # Regime breadth uses date+close only; corporate-action guard must never
    # regress to an OHLC/open dependency.
    close_only=sf[["date","close"]].copy()
    cb=close_only_scale_breaks(close_only)
    assert cb and 1.8<=cb[0]["ratio"]<=2.2,cb
    ss=mechanical_split_suspects(sf)
    assert ss,ss

    # QQQ/regime is close-only, so fractional common split ratios must also be
    # visible to the fail-closed scale guard (a 3:2 split is below 1.8x).
    frac_close=frame(40)[["date","close"]].copy()
    frac_close.loc[19,"close"]=150.0;frac_close.loc[20:,"close"]=100.0
    fcb=close_only_scale_breaks(frac_close)
    assert fcb and any(abs(float(x["nearest_common_factor"])-1.5)<1e-12 for x in fcb),fcb

    # Finalists get a stricter candidate-scoped check for fractional split-like
    # gaps that are below the universe-wide severe scale-break threshold.
    frac=frame(40)
    frac.loc[19,["open","high","low","close"]]=[150.0,152.0,148.0,150.0]
    frac.loc[20,["open","high","low","close"]]=[100.0,102.0,98.0,100.0]
    assert mechanical_scale_breaks(frac,40)==[],mechanical_scale_breaks(frac,40)
    assert mechanical_split_suspects(frac,40),mechanical_split_suspects(frac,40)
    old_split_lookup=final_mod.split_consistent_history
    calls=[]
    try:
        def _fake_split_lookup(sym,df):
            calls.append(sym)
            return df,"PASS_NO_SPLIT_EVENTS_CROSSCHECKED",[]
        final_mod.split_consistent_history=_fake_split_lookup
        fx,fst,fev,flookup=final_mod.candidate_corporate_action_reconcile(
            "TEST",frac,{"corporate_action_status":"PASS_NO_LOCAL_SPLIT_DISCONTINUITY","split_events":[]}
        )
        assert flookup is True and calls==["TEST"],(flookup,calls)
        # A successful exact split lookup with no declared event proves there is
        # no split to reconcile. Factor-like news gaps are not corporate-action
        # UNKNOWN at Final; detailed legal risk is handled by the SEC guard.
        assert fst=="PASS_NO_SPLIT_EVENTS_CROSSCHECKED" and fev==[],(fst,fev)
        assert len(fx)==len(frac)
    finally:
        final_mod.split_consistent_history=old_split_lookup
    adjusted=apply_split_events(sf,[{"date":sf.date.iloc[20].date().isoformat(),
                                     "ratio":2.0,"numerator":2.0,"denominator":1.0}])
    assert abs(float(adjusted.close.iloc[19])-50.0)<1e-12,adjusted.iloc[18:22]
    assert abs(float(adjusted.volume.iloc[19])-2_000_000.0)<1e-12,adjusted.iloc[18:22]
    assert abs(float(adjusted.close.iloc[20])-50.0)<1e-12,adjusted.iloc[18:22]
    sev={"date":sf.date.iloc[20].date().isoformat(),"ratio":2.0,"numerator":2.0,"denominator":1.0}
    ok,why=_verify_split_events_against_raw(sf,[sev])
    assert ok,(ok,why)
    # A successful split lookup with no declared split means the severe move is
    # an ordinary market gap at Stage1/breadth, not automatic CA ambiguity.
    gap_ok,gap_why=_verify_split_events_against_raw(sf,[])
    assert gap_ok is True,(gap_ok,gap_why)
    old_fetch_gap=alpha_mod.fetch_yahoo_split_events
    try:
        alpha_mod.fetch_yahoo_split_events=lambda sym,start,end:("PASS",[])
        _,gap_status,gap_events=alpha_mod.split_consistent_history("TEST",sf,40)
        assert gap_status=="PASS_NO_SPLIT_EVENTS_CROSSCHECKED",(gap_status,gap_events)
        assert gap_events==[]
    finally:
        alpha_mod.fetch_yahoo_split_events=old_fetch_gap
    # A provider-declared split that conflicts with raw OHLC still fails closed.
    wrong={"date":sf.date.iloc[20].date().isoformat(),"ratio":4.0,"numerator":4.0,"denominator":1.0}
    bad,why2=_verify_split_events_against_raw(sf,[wrong])
    assert bad is False and "SPLIT_RATIO_RAW_CONFLICT" in why2,(bad,why2)

    # Historical provider artifacts outside the current 260-session technical
    # horizon must not poison today's geometry/regime.
    old=frame(400)
    old.loc[20:,"open"]=50.0;old.loc[20:,"high"]=52.0;old.loc[20:,"low"]=48.0;old.loc[20:,"close"]=50.0
    ok_old,why_old=_verify_split_events_against_raw(old,[])
    assert ok_old is True,(ok_old,why_old)

    # split_consistent_history must use the same active 260-session horizon.
    # A stale provider event far outside that horizon cannot make today's
    # Stage1/breadth UNKNOWN even if the provider erroneously returns it.
    old_fetch=alpha_mod.fetch_yahoo_split_events
    split_calls=[]
    try:
        ancient_day=old.date.iloc[20].date().isoformat()
        def _fake_windowed_splits(sym,start,end):
            split_calls.append((sym,start,end))
            return "PASS",[{"date":ancient_day,"numerator":2.0,"denominator":1.0,"ratio":2.0}]
        alpha_mod.fetch_yahoo_split_events=_fake_windowed_splits
        hx,hstatus,hevents=alpha_mod.split_consistent_history("TEST",old,260)
        assert hstatus=="PASS_NO_SPLIT_EVENTS_CROSSCHECKED",(hstatus,hevents,split_calls)
        assert hevents==[],hevents
        assert split_calls and split_calls[0][1]>ancient_day,split_calls
        assert len(hx)==len(old)
    finally:
        alpha_mod.fetch_yahoo_split_events=old_fetch

    # R92/R93 is prospective-only, but current research eligibility is not.
    # A still-valid setup first discovered on session 4/5 may be PRE_G9 now;
    # only pre-registration observations are forbidden from validation backfill.
    hf=frame(270)
    hf[["open","high","low","close"]]=[101.0,103.0,99.0,102.0]
    trigger_idx=len(hf)-5
    td=hf.date.iloc[trigger_idx].date().isoformat()
    frozen={"setup_id":"TEST-HIST","symbol":"TEST","family":"D","trigger_date":td,
            "A":10.0,"P":100.0,"anchor":97.0,"entry_low":100.0,"entry_high":102.5,
            "entry_model":102.5,"chase_limit":105.0,"S0":95.0,"T1":150.0,
            "anchor_available_idx":trigger_idx-1,"anchor_available_date":hf.date.iloc[trigger_idx-1].date().isoformat(),
            "target_source":"TEST","target_zone":None,"target_overlap":False,
            "synthetic_target":False,"source_geometry":{"trigger_date":td,"P":100.0,"anchor":97.0}}
    g={"trigger_date":td,"P":100.0,"anchor":97.0}
    hr=eval_one("TEST","D",g,hf,"CLEAN_DISCOVERY",frozen=frozen,recorded_before=False)
    assert hr["result"]=="PRE_G9_TECH_PASS" and hr["pre_g9_tech_pass"] is True,hr
    assert hr["historical_discovery_age_gt3"] is True,hr
    assert hr["r92_backfill_allowed"] is False,hr
    assert hr["r92_observation_rule"]=="REGISTER_NOW_OBSERVE_FUTURE_ONLY_NO_BACKFILL",hr
    pr=eval_one("TEST","D",g,hf,"CLEAN_DISCOVERY",frozen=frozen,recorded_before=True)
    assert pr["result"]=="PRE_G9_TECH_PASS",pr

    # A chase has no valid fill now but the frozen setup must survive for a valid retest.
    cf=frame(270)
    cf[["open","high","low","close"]]=[102.0,103.0,99.0,102.0]
    cti=len(cf)-3;ctd=cf.date.iloc[cti].date().isoformat()
    cfr={"setup_id":"TEST-CHASE","symbol":"TEST","family":"D","trigger_date":ctd,
         "A":10.0,"P":100.0,"anchor":97.0,"entry_low":100.0,"entry_high":102.5,
         "entry_model":102.5,"chase_limit":105.0,"S0":95.0,"T1":150.0,
         "anchor_available_idx":cti-1,"anchor_available_date":cf.date.iloc[cti-1].date().isoformat(),
         "target_source":"TEST","target_zone":None,"target_overlap":False,
         "synthetic_target":False,"source_geometry":{"trigger_date":ctd,"P":100.0,"anchor":97.0}}
    cg={"trigger_date":ctd,"P":100.0,"anchor":97.0}
    cf.loc[len(cf)-1,["open","high","low","close"]]=[105.5,107.0,105.0,106.0]
    cr=eval_one("TEST","D",cg,cf,"CLEAN_DISCOVERY",frozen=cfr,recorded_before=True)
    assert cr["result"]=="WATCH_CHASE_RETEST_REQUIRED",cr
    cf.loc[len(cf)-1,["open","high","low","close"]]=[102.2,103.0,101.0,102.0]
    rr=eval_one("TEST","D",cg,cf,"CLEAN_DISCOVERY",frozen=cfr,recorded_before=True)
    assert rr["result"]=="PRE_G9_TECH_PASS",rr

    # B/C anchors are available at trigger-1 close, so a trigger-day low at/below
    # S0 must invalidate even when all later bars stay above S0.
    bf2=frame(270)
    bf2[["open","high","low","close"]]=[102.0,104.0,99.0,102.0]
    bti=len(bf2)-2;btd=bf2.date.iloc[bti].date().isoformat()
    bfr={"setup_id":"TEST-BREACH","symbol":"TEST","family":"B","trigger_date":btd,
         "A":10.0,"P":100.0,"anchor":97.0,"entry_low":100.0,"entry_high":102.5,
         "entry_model":102.5,"chase_limit":105.0,"S0":95.0,"T1":150.0,
         "anchor_available_idx":bti-1,"anchor_available_date":bf2.date.iloc[bti-1].date().isoformat(),
         "target_source":"TEST","target_zone":None,"target_overlap":False,
         "synthetic_target":False,"source_geometry":{"trigger_date":btd,"P":100.0,"anchor":97.0}}
    bf2.loc[bti,"low"]=94.0
    br=eval_one("TEST","B",{"trigger_date":btd,"P":100.0,"anchor":97.0},bf2,
                "CLEAN_DISCOVERY",frozen=bfr,recorded_before=True)
    assert br["result"]=="FAIL_INVALIDATED_S0" and br["invalidation"]["first_breach_date"]==btd,br

    # C4.17 price discovery permits synthetic P+3A only with a hard ORANGE cap.
    # It is still a research-eligible PRE_G9 technical candidate; the cap must
    # survive in machine-readable output rather than suppressing the candidate.
    pdf=frame(270)
    pdf[["open","high","low","close"]]=[200.0,204.0,196.0,200.0]
    pdi=len(pdf)-1;pdd=pdf.date.iloc[pdi].date().isoformat()
    pdf.loc[pdi,["open","high","low","close"]]=[200.5,202.0,199.0,201.0]
    pfr={"setup_id":"TEST-PRICE-DISCOVERY","symbol":"TEST","family":"A","trigger_date":pdd,
         "A":10.0,"P":200.0,"anchor":190.0,"entry_low":200.0,"entry_high":202.5,
         "entry_model":202.5,"chase_limit":205.0,"S0":188.0,"T1":230.0,
         "anchor_available_idx":pdi-1,"anchor_available_date":pdf.date.iloc[pdi-1].date().isoformat(),
         "target_source":"SYNTHETIC_P_PLUS_3A_PRICE_DISCOVERY","target_zone":None,
         "target_overlap":False,"synthetic_target":True,
         "source_geometry":{"trigger_date":pdd,"P":200.0,"anchor":190.0,
                            "depth":3.0,"prelow_near_hl":True}}
    pr=eval_one("TEST","A",pfr["source_geometry"],pdf,"CLEAN_DISCOVERY",frozen=pfr,recorded_before=False)
    assert pr["result"]=="PRE_G9_TECH_PASS" and pr["pre_g9_tech_pass"] is True,pr
    assert pr["research_tier_cap"]=="ORANGE" and pr["price_discovery_cap"] is True,pr

    # Prospectively discovered technical passes and resolvable watches survive
    # across later deep-scope changes; historical backfill must never self-promote.
    assert lifecycle_state_persists("PRE_G9_TECH_PASS") is True
    assert lifecycle_state_persists("WATCH_RETEST_REQUIRED") is True
    assert lifecycle_state_persists("WATCH_EVENT_UNKNOWN_OR_BLOCKED") is True
    assert lifecycle_state_persists("PRE_G9_TECH_PASS") is True
    assert lifecycle_state_persists("FAIL_RR") is False

    # Frozen lifecycle symbols remain in event research even after leaving current
    # weekly/fresh geometry scope.
    faux_final={
      "asof_et":"2026-10-02",
      "lifecycle_registry":{
        "schema":"XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1",
        "execution":"NONE","real_money":"NO-GO",
        "records":{"id1":{"symbol":"OLDW","state":"WATCH_RETEST_REQUIRED"}}
      }
    }
    ls=lifecycle_scope_from_final(faux_final,"2026-10-02")
    assert ls==["OLDW"],ls
    assert event_geometry_scope(["FRESH"],ls)==["FRESH","OLDW"]

    # Trigger-time weekly scope: a valid Thursday context must survive a
    # Friday weekly-close failure so recent-trigger discovery cannot be erased.
    dates=pd.bdate_range("2025-01-06",periods=60*5)
    wr=[]
    for i,dte in enumerate(dates):
        w=i//5
        cl=100.0+w
        if i==len(dates)-1: cl=20.0
        wr.append({"date":dte,"open":cl,"high":cl+1.0,"low":cl-1.0,"close":cl,"volume":1e6})
    wdf=pd.DataFrame(wr)
    wl={}
    for k,g in wdf.assign(week=wdf["date"].dt.to_period("W-FRI")).groupby("week"):
        wl[k.start_time.date().isoformat()]=g["date"].iloc[-1].date().isoformat()
    pass_dates,wctx=recent_weekly_context(wdf,wl,NEW_TRIGGER_DISCOVERY_MAX_AGE)
    fri=wdf.date.iloc[-1].date().isoformat()
    thu=wdf.date.iloc[-2].date().isoformat()
    prior_fri=wdf.date.iloc[-6].date().isoformat()
    assert fri not in pass_dates,(pass_dates,wctx[fri])
    assert thu in pass_dates,(pass_dates,wctx[thu])
    assert prior_fri not in pass_dates,(pass_dates,wctx.get(prior_fri))

    # Breadth NEW_HIGH20/NEW_LOW20 excludes today's close from the prior-20
    # window and equality is never a pass.
    ties=pd.Series([100.0]*21)
    assert new_high_low20_flags(ties)==(False,False),new_high_low20_flags(ties)
    hi=pd.Series([float(i) for i in range(1,21)]+[21.0])
    lo=pd.Series([float(i) for i in range(2,22)]+[1.0])
    assert new_high_low20_flags(hi)==(True,False),new_high_low20_flags(hi)
    assert new_high_low20_flags(lo)==(False,True),new_high_low20_flags(lo)

    # Stage1 process must bind the computed recent weekly context into its output.
    # This catches a runtime NameError class that py_compile cannot detect.
    olds=(stage1_mod.load_history,stage1_mod.weekly_gate,stage1_mod.mechanical_scale_breaks,
          stage1_mod.mechanical_split_suspects,stage1_mod.split_consistent_history,
          stage1_mod.recent_weekly_context,stage1_mod.base_pool,stage1_mod.drawdown_metrics)
    try:
        sx=frame(300)
        stage1_mod.load_history=lambda sym,asof:(sx.copy(),"TEST")
        stage1_mod.weekly_gate=lambda df,asof,week_last:{"pass":True}
        stage1_mod.mechanical_scale_breaks=lambda df,lookback=260:[]
        stage1_mod.mechanical_split_suspects=lambda df,lookback=260:[]
        stage1_mod.recent_weekly_context=lambda df,week_last,n:(["2026-10-02"],{"2026-10-02":{"pass":True}})
        stage1_mod.base_pool=lambda df:[]
        stage1_mod.drawdown_metrics=lambda df:{"current_drawdown_252":-0.16,"max_drawdown_close_120":-0.21}
        _,sr=stage1_mod.process("TEST","2026-10-02",{})
        assert sr["status"]=="WEEKLY_PASS",sr
        assert sr["recent_weekly_context"]=={"2026-10-02":{"pass":True}},sr
        assert sr["corporate_action_status"]=="PASS_NO_LOCAL_SPLIT_DISCONTINUITY",sr

        # Fractional split-like gaps (for example 3:2) are below the severe
        # 1.8x scale-break threshold but still must invoke exact split
        # reconciliation before Stage1 geometry is trusted.
        calls=[]
        stage1_mod.mechanical_scale_breaks=lambda df,lookback=260:[]
        stage1_mod.mechanical_split_suspects=lambda df,lookback=260:[{"date":"2026-09-30","matched_split_ratio":1.5}]
        def _split_check(sym,df):
            calls.append(sym)
            return df.copy(),"PASS_NO_SPLIT_EVENTS_CROSSCHECKED",[]
        stage1_mod.split_consistent_history=_split_check
        _,sr2=stage1_mod.process("FRAC","2026-10-02",{})
        assert calls==["FRAC"],calls
        assert sr2["status"]=="WEEKLY_PASS",sr2
        assert sr2["corporate_action_status"]=="PASS_NO_SPLIT_EVENTS_CROSSCHECKED",sr2
    finally:
        (stage1_mod.load_history,stage1_mod.weekly_gate,stage1_mod.mechanical_scale_breaks,
         stage1_mod.mechanical_split_suspects,stage1_mod.split_consistent_history,
         stage1_mod.recent_weekly_context,stage1_mod.base_pool,stage1_mod.drawdown_metrics)=olds

    # Same-run HISTORY -> Stage1 OHLCV cache roundtrip. Cache is transport only;
    # wrong-ASOF reads must return None so the normal fail-closed fetch path remains authoritative.
    with tempfile.TemporaryDirectory() as td:
        old_h=history_mod.HISTORY_CACHE_DIR;old_s=stage1_mod.HISTORY_CACHE_DIR
        try:
            history_mod.HISTORY_CACHE_DIR=td;stage1_mod.HISTORY_CACHE_DIR=td
            cx=frame(300);casof=cx["date"].iloc[-1].date().isoformat()
            history_mod._write_sina_cache("CACHE_TEST",cx)
            cached=stage1_mod._cached_sina_history("CACHE_TEST",casof)
            assert cached is not None and len(cached)==len(cx),("SAME_RUN_HISTORY_CACHE_ROUNDTRIP",cached)
            assert stage1_mod._cached_sina_history("CACHE_TEST","2025-01-01") is None
        finally:
            history_mod.HISTORY_CACHE_DIR=old_h;stage1_mod.HISTORY_CACHE_DIR=old_s

    # HISTORY PASS must be transport-complete for downstream Stage1. The exact
    # bug class: Sina lacks exact ASOF, official Nasdaq proves HISTORY PASS, and
    # the old early-return skipped Yahoo OHLCV hydration, creating Stage1 cache
    # missing UNKNOWNs for otherwise eligible symbols.
    with tempfile.TemporaryDirectory() as td:
        old_cache=history_mod.HISTORY_CACHE_DIR
        olds=(history_mod.official_listing_upper_bound_fail,history_mod.sina,history_mod.nasdaq,
              history_mod.yahoo,history_mod.yahoo_ohlcv,history_mod.continuity_composite_pass,
              history_mod.eastmoney,history_mod.bridge_resolution)
        try:
            history_mod.HISTORY_CACHE_DIR=td
            asof="2026-10-02"
            ds=pd.bdate_range(end=asof,periods=320)
            by={d.date().isoformat():(100.0,1_000_000.0) for d in ds}
            raw=pd.DataFrame({
              "date":ds,"open":[100.0]*len(ds),"high":[101.0]*len(ds),
              "low":[99.0]*len(ds),"close":[100.0]*len(ds),"volume":[1_000_000.0]*len(ds)
            })
            calls=[]
            history_mod.official_listing_upper_bound_fail=lambda sym,a:None
            history_mod.sina=lambda sym,a:({},{"usable":0})
            history_mod.nasdaq=lambda sym,a:(by,{"usable":len(by)})
            history_mod.yahoo=lambda sym,a:(_ for _ in ()).throw(AssertionError("HISTORY_YAHOO_SHOULD_NOT_BE_NEEDED_AFTER_NASDAQ_PASS"))
            history_mod.yahoo_ohlcv=lambda sym,a:(calls.append((sym,a)) or raw.copy(),{"source":"TEST_RAW_OHLCV"})
            history_mod.continuity_composite_pass=lambda *args,**kwargs:None
            history_mod.eastmoney=lambda sym,a:({},{"usable":0})
            history_mod.bridge_resolution=lambda *args,**kwargs:None
            sym,st,info,meta=history_mod.eval_one("CACHE_NASDAQ_PASS",asof)
            assert sym=="CACHE_NASDAQ_PASS" and st=="PASS_HISTORY",(sym,st,info,meta)
            assert calls==[("CACHE_NASDAQ_PASS",asof)],calls
            assert history_mod._technical_cache_exact("CACHE_NASDAQ_PASS",asof) is True
            assert (meta.get("technical_cache") or {}).get("status")=="PASS_YAHOO_EXACT_ASOF_HYDRATED",meta
        finally:
            history_mod.HISTORY_CACHE_DIR=old_cache
            (history_mod.official_listing_upper_bound_fail,history_mod.sina,history_mod.nasdaq,
             history_mod.yahoo,history_mod.yahoo_ohlcv,history_mod.continuity_composite_pass,
             history_mod.eastmoney,history_mod.bridge_resolution)=olds

    # Regression: split transport configuration must be readable inside alpha_semantics.
    # Missing `import os` previously converted every split-suspect symbol to Stage1 UNKNOWN.
    old_curl=sys.modules.get("curl_cffi")
    old_retry=alpha_mod.os.environ.get("XRAY_SPLIT_HTTP_RETRIES")
    old_timeout=alpha_mod.os.environ.get("XRAY_SPLIT_HTTP_TIMEOUT_SECONDS")
    alpha_mod._SPLIT_CACHE.clear()
    calls=[]
    class _Resp:
        status_code=200
        def json(self):
            return {"chart":{"result":[{"events":{"splits":{}}}]}}
    class _Req:
        @staticmethod
        def get(url,params=None,impersonate=None,timeout=None):
            calls.append({"url":url,"timeout":timeout,"params":params})
            return _Resp()
    fake=types.ModuleType("curl_cffi")
    fake.requests=_Req
    sys.modules["curl_cffi"]=fake
    try:
        alpha_mod.os.environ["XRAY_SPLIT_HTTP_RETRIES"]="1"
        alpha_mod.os.environ["XRAY_SPLIT_HTTP_TIMEOUT_SECONDS"]="4"
        st,events=alpha_mod.fetch_yahoo_split_events("OSENVTEST","2026-01-01","2026-10-06")
        assert st=="PASS" and events==[],(st,events)
        assert len(calls)==1 and abs(float(calls[0]["timeout"])-4.0)<1e-12,calls

        # A transient query1 failure must fail over within the same Yahoo chart
        # provider family before Stage1 is forced to UNKNOWN. query2 may create
        # PASS only after a real 200 + parseable chart payload; both-host failure
        # still remains UNKNOWN.
        alpha_mod._SPLIT_CACHE.clear()
        calls.clear()
        class _FailoverReq:
            @staticmethod
            def get(url,params=None,impersonate=None,timeout=None):
                calls.append({"url":url,"timeout":timeout,"params":params})
                if "query1.finance.yahoo.com" in url:
                    class _Bad:
                        status_code=502
                    return _Bad()
                return _Resp()
        fake.requests=_FailoverReq
        st2,events2=alpha_mod.fetch_yahoo_split_events("HOSTFAILOVER","2026-01-01","2026-10-06")
        assert st2=="PASS" and events2==[],(st2,events2)
        assert [("query1.finance.yahoo.com" in x["url"],"query2.finance.yahoo.com" in x["url"]) for x in calls]==[(True,False),(False,True)],calls

        alpha_mod._SPLIT_CACHE.clear()
        calls.clear()
        class _BothBadReq:
            @staticmethod
            def get(url,params=None,impersonate=None,timeout=None):
                calls.append({"url":url,"timeout":timeout,"params":params})
                class _Bad:
                    status_code=502
                return _Bad()
        fake.requests=_BothBadReq
        st3,events3=alpha_mod.fetch_yahoo_split_events("HOSTBOTHBAD","2026-01-01","2026-10-06")
        assert st3.startswith("UNKNOWN:") and events3==[],(st3,events3)
        assert len(calls)==2,calls
    finally:
        alpha_mod._SPLIT_CACHE.clear()
        if old_curl is None: sys.modules.pop("curl_cffi",None)
        else: sys.modules["curl_cffi"]=old_curl
        if old_retry is None: alpha_mod.os.environ.pop("XRAY_SPLIT_HTTP_RETRIES",None)
        else: alpha_mod.os.environ["XRAY_SPLIT_HTTP_RETRIES"]=old_retry
        if old_timeout is None: alpha_mod.os.environ.pop("XRAY_SPLIT_HTTP_TIMEOUT_SECONDS",None)
        else: alpha_mod.os.environ["XRAY_SPLIT_HTTP_TIMEOUT_SECONDS"]=old_timeout

    # Family C canonical pivot includes reaction high. A breakout above only the
    # consolidation high must not pass if it remains below reaction high.
    dates=pd.bdate_range("2026-06-01",periods=36)
    rows=[]
    for dte in dates:
        rows.append({"date":dte,"open":100.0,"high":102.0,"low":98.0,"close":100.0,"volume":1_000_000.0})
    cdf=pd.DataFrame(rows)
    r0=25
    cdf.loc[r0,["open","high","low","close","volume"]]=[103.0,110.0,101.0,107.0,2_000_000.0]
    cdf.loc[r0+1,["open","high","low","close","volume"]]=[106.0,108.0,102.0,106.0,1_200_000.0]
    cdf.loc[r0+2,["open","high","low","close","volume"]]=[106.0,107.0,102.5,106.0,1_100_000.0]
    for j,h in zip((r0+3,r0+4,r0+5),(106.5,107.0,107.5)):
        cdf.loc[j,["open","high","low","close","volume"]]=[105.0,h,104.0,105.5,900_000.0]
    t=r0+6
    cdf.loc[t,["open","high","low","close","volume"]]=[107.0,109.0,105.0,108.5,2_000_000.0]
    sess=[d.date().isoformat() for d in cdf["date"]]
    edt=cdf.date.iloc[r0].date().isoformat()+"T08:00:00-04:00"
    ce={"event_datetime_et":edt,"official_source_url":"TEST","source":"TEST"}
    cg,cd=eval_event("TEST",cdf,ce,cdf.date.iloc[-1].date().isoformat(),sess,"CLEAN_DISCOVERY")
    assert cg is None,(cg,cd)

    # Once price actually clears the reaction-high pivot, the same valid structure can confirm.
    cdf2=cdf.copy()
    cdf2.loc[t,["open","high","low","close","volume"]]=[109.0,112.0,105.0,111.5,2_000_000.0]
    cg2,cd2=eval_event("TEST",cdf2,ce,cdf2.date.iloc[-1].date().isoformat(),sess,"CLEAN_DISCOVERY")
    assert cg2 and abs(float(cg2["P"])-110.0)<1e-12,(cg2,cd2)
    assert cg2.get("gap_floor_intact") is True,(cg2,cd2)

    # GAP_FLOOR is persistent through consolidation and breakout, not only reaction0+1+2.
    cdf3=cdf2.copy()
    cdf3.loc[r0+4,"low"]=99.0
    cg3,cd3=eval_event("TEST",cdf3,ce,cdf3.date.iloc[-1].date().isoformat(),sess,"CLEAN_DISCOVERY")
    assert cg3 is None and cd3.get("gap_floor_breach_date")==cdf3.date.iloc[r0+4].date().isoformat(),(cg3,cd3)

    # Full positive reachability: actual structural R1 -> frozen geometry -> RR -> PRE_G9.
    # This prevents a self-lock where individually valid gates can never compose into a candidate.
    rf=frame(100)
    rf[["open","high","low","close","volume"]]=[100.0,105.0,95.0,100.0,1_000_000.0]
    rf.loc[35,"high"]=150.0
    rf.loc[33:34,"high"]=[105.0,106.0]
    rf.loc[36:37,"high"]=[106.0,105.0]
    rti=len(rf)-1
    rf.loc[rti,["open","high","low","close","volume"]]=[100.0,103.0,95.0,101.0,2_000_000.0]
    rtd=rf.date.iloc[rti].date().isoformat()
    rg={"trigger_date":rtd,"P":100.0,"anchor":96.5}
    frozen,err=final_mod._frozen_geometry("REACH","B",rg,rf)
    assert err is None and frozen is not None,(frozen,err)
    assert frozen["target_source"]=="STRUCTURAL_ACTIVE_R1_LOWER_BOUND",frozen
    assert float(frozen["T1"])>float(frozen["entry_high"]),frozen
    reach=eval_one("REACH","B",rg,rf,"CLEAN_DISCOVERY",frozen=frozen,recorded_before=True)
    assert reach["result"]=="PRE_G9_TECH_PASS" and reach["pre_g9_tech_pass"] is True,reach

    # Fresh Final scope must use Deep's event+RS confirmed aggregate sets,
    # never a raw per-symbol geometry flag that can remain true after an event veto.
    deep_scope={
      "a_geometry_rs_event_pass":["AOK"],
      "b_breakout_rs_event_pass":["BOK"],
      "d_dk3_pre_r1":["DOK"],
    }
    assert _fresh_deep_family_confirmed(deep_scope,"AOK","A") is True
    assert _fresh_deep_family_confirmed(deep_scope,"BLOCKED_RAW","A") is False
    assert _fresh_deep_family_confirmed(deep_scope,"BOK","B") is True
    assert _fresh_deep_family_confirmed(deep_scope,"DOK","D") is True
    assert _fresh_deep_family_confirmed(deep_scope,"DOK","C") is False

    # Lifecycle-only Final rows pruned beyond the model horizon must not
    # survive as unbacked results. Fresh current finalists always remain.
    scoped,dropped=reconcile_final_result_scope(
        {"NEOG|D":{"result":"UNKNOWN"},"PI|D":{"result":"UNKNOWN"},"MU|B":{"result":"UNKNOWN"}},
        ["MU|B"],
        {"records":{"sid":{"symbol":"PI","family":"D","state":"WATCH_RETEST_REQUIRED"}}},
    )
    assert set(scoped)=={"PI|D","MU|B"},scoped
    assert dropped==["NEOG|D"],dropped

    # Missing inherited Stage1 corporate-action metadata is not itself evidence
    # of a corporate action. Family C must independently validate price-scale
    # integrity and remain fail-closed only on explicit non-PASS evidence.
    fc=frame(300)
    fc[["open","high","low","close"]]=[100.0,101.0,99.0,100.0]
    _,fs,fe,fl=family_c_ca_reconcile("TEST",fc,{})
    assert fs=="PASS_NO_LOCAL_SPLIT_DISCONTINUITY" and fe==[] and fl is False,(fs,fe,fl)
    _,fs,fe,fl=family_c_ca_reconcile("TEST",fc,{"corporate_action_status":"UNKNOWN_EXPLICIT"})
    assert fs=="UNKNOWN_EXPLICIT" and fl is False,(fs,fl)

    assert _is_depositary_security_name("Example Corp - American Depositary Shares") is True
    assert _is_depositary_security_name("Example Corp - Common Stock") is False

    print({"status":"PASS","tests":[
      "WILDER_FIRST_TR_UNDEFINED","EMA_SMA_SEED","D_DRAWDOWN_DEFINITIONS",
      "R1_STRUCTURAL_TRIGGER_MINUS1","R1_ENTRY_OVERLAP","EXTENSION_RESET","EXTENSION_TIGHT_BASE_RESET","RETEST_BAR","FAMILY_A_TRIGGER_MINUS1_LOW","SETUP_ID_STABLE",
      "B_RECENT_TRIGGER_PERSISTENCE","DEEP_RECENT_TRIGGER_INDEPENDENT_OF_CURRENT_STAGE1","A_STAGE1_ASOF_TRIGGER","MECHANICAL_SCALE_BREAK_GUARD","BREADTH_CLOSE_ONLY_SCALE_GUARD","SPLIT_ONLY_RECONCILIATION","SPLIT_RAW_CROSSCHECK","UNDECLARED_SCALE_MOVE_MARKET_GAP","HISTORICAL_DISCOVERY_RESEARCH_ELIGIBLE_NO_R92_BACKFILL","CHASE_FROZEN_RETEST_RECOVERY","ANCHOR_AVAILABLE_S0_CHRONOLOGY",
      "ADR_RATIO_FAIL_CLOSED_CLASSIFICATION","FINALIST_FRACTIONAL_SPLIT_VERIFICATION","SYNTHETIC_PRICE_DISCOVERY_ORANGE_CAP","PROSPECTIVE_LIFECYCLE_PERSISTENCE","FROZEN_LIFECYCLE_EVENT_SCOPE","ANCIENT_SCALE_BREAK_OUTSIDE_TECH_HORIZON","TRIGGER_TIME_WEEKLY_SCOPE","BREADTH_NH20_NL20_PRIOR20_STRICT",
      "HISTORY_PASS_EXACT_ASOF_CACHE_BINDING","FAMILY_C_REACTION_HIGH_PIVOT","FAMILY_C_PERSISTENT_GAP_FLOOR","FAMILY_C_MISSING_INHERITED_CA_NOT_AUTO_UNKNOWN","FAMILY_C_EXPLICIT_CA_UNKNOWN_FAIL_CLOSED","FINAL_RESULT_SCOPE_PRUNES_EXPIRED_UNBACKED_LIFECYCLE","FULL_R1_TO_PRE_G9_REACHABILITY","FRESH_FINAL_SCOPE_EXACT_DEEP_EVENT_PASS_SET","SPLIT_RECONCILIATION_ACTIVE_HORIZON_ONLY","SPLIT_ENV_CONFIG_IMPORT_REGRESSION","SPLIT_YAHOO_DUAL_HOST_FAILOVER"
    ]})

if __name__=="__main__":
    main()
