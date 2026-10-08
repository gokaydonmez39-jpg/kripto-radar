#!/usr/bin/env python3
"""Manual-decision candidate follow-up classification; research ONLY, no orders, no user delivery.
It accepts trusted, time-stamped OHLC bars; it does NOT fetch prices or claim broker fills.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path

SCHEMA="XRAY_MANUAL_RESEARCH_FOLLOWUP_SHADOW_V1"
STATES={"MONITORING","ENTRY_ZONE_TOUCHED","TARGET_LEVEL_TOUCHED",
        "STOP_LEVEL_TOUCHED","INVALIDATED","EXPIRED",
        "AMBIGUOUS_INTRABAR_ORDER","OFFICIAL_HALT","SOURCE_STALE","EVENT_VETO"}
CLOSED={"STOP_LEVEL_TOUCHED","TARGET_LEVEL_TOUCHED","INVALIDATED","EXPIRED","OFFICIAL_HALT","EVENT_VETO"}
SIDE_ONLY="LONG_RESEARCH_LEVELS_ONLY_NEVER_POSITION_OR_FILL"
SYMBOL=re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")

def iso(value):
    try:
        stamp=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        if stamp.tzinfo is None:raise ValueError("NO_TZ")
        return stamp.astimezone(dt.timezone.utc)
    except (TypeError,AttributeError,ValueError) as e:
        raise ValueError("INVALID_TIMESTAMP") from e

def finite(v):
    if isinstance(v,bool):return None
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError,OverflowError):
        return None

def validate_candidate(c):
    if not isinstance(c,dict):raise ValueError("CANDIDATE_FORMAT")
    if c.get("manual_approved") is not True or c.get("research_authority_verified") is not True:
        raise ValueError("UNQUALIFIED_CANDIDATE")
    s=c.get("symbol")
    if not isinstance(s,str) or not SYMBOL.fullmatch(s):
        raise ValueError("INVALID_SYMBOL")
    if not isinstance(c.get("delivery_key"),str) or not re.fullmatch("[A-Za-z0-9:_|.-]{12,200}",c["delivery_key"]):
        raise ValueError("INVALID_KEY")
    e1=finite(c.get("entry_low"));e2=finite(c.get("entry_high"))
    stop=finite(c.get("stop"));target=finite(c.get("target"))
    if None in (e1,e2,stop,target) or not (0<stop<e1<=e2<target):
        raise ValueError("INVALID_LONG_LEVEL_GEOMETRY")
    begin=iso(c.get("origin_at_utc"))
    expiration=iso(c.get("expires_at_utc"))
    if expiration<=begin:raise ValueError("INVALID_HORIZON")
    if c.get("execution")!="NONE" or c.get("real_money")!="NO-GO":
        raise ValueError("SAFETY")
    if c.get("source_asof_et") is None:raise ValueError("SOURCE_ASOF_MISSING")
    return begin,expiration

def validate_bar(b,c,begin,asof_now):
    if not isinstance(b,dict) or b.get("symbol")!=c["symbol"]:
        raise ValueError("BAR_SYMBOL_MISMATCH")
    if b.get("source_authorized") is not True or b.get("source_provenance_verified") is not True:
        raise ValueError("UNTRUSTED_MARKET_DATA")
    if not isinstance(b.get("source_hash"),str) or not re.fullmatch("[a-f0-9]{40,64}",b["source_hash"]):
        raise ValueError("BAR_SOURCE_HASH_MISSING")
    if b.get("timeframe") not in ("1m","5m","15m","1h","1d"):
        raise ValueError("TIMEFRAME_UNAPPROVED")
    ts=iso(b.get("bar_end_utc"))
    observed=iso(asof_now)
    if ts<begin or ts>observed+dt.timedelta(seconds=30):
        raise ValueError("LOOKAHEAD_OR_PREDATING_CANDIDATE")
    low=finite(b.get("low"));high=finite(b.get("high"))
    if low is None or high is None or not (low>0 and low<=high):
        raise ValueError("INVALID_PRICE_BAR")
    delay=(observed-ts).total_seconds()
    if delay < -30:raise ValueError("FUTURE_PRICE_DATA")
    return ts,low,high,delay

def event(c,bar,prev=None,*,observed_at_utc,halt=False,material_event=False,
          invalidated=False,max_age_minutes=35):
    """Produce a user-review event. STOP/TARGET are touches, never actual order fills."""
    begin,expires=validate_candidate(c)
    ts,low,high,age=validate_bar(bar,c,begin,observed_at_utc)
    prev=prev or {}
    if prev:
        if prev.get("delivery_key")!=c["delivery_key"]:
            raise ValueError("PREVIOUS_CANDIDATE_KEY_DRIFT")
        if prev.get("status") not in STATES:
            raise ValueError("PREVIOUS_STATE_INVALID")
        if prev.get("status") in CLOSED:
            return {"status":prev["status"],"transition":"TERMINAL_STATE_LOCKED",
                    "alert":False,"research_only":True,"orders":[]}
        previous_ts=iso(prev.get("last_bar_end_utc"))
        if ts<previous_ts:
            raise ValueError("OUT_OF_ORDER_BAR")
    if halt is True:status="OFFICIAL_HALT"
    elif material_event is True:status="EVENT_VETO"
    elif invalidated is True:status="INVALIDATED"
    # Expiry follows the observation clock, even when no fresh market bar arrives.
    # An expired research setup cannot remain indefinitely SOURCE_STALE.
    elif iso(observed_at_utc)>=expires:status="EXPIRED"
    elif age>max_age_minutes*60:status="SOURCE_STALE"
    else:
        stop_hit=low<=finite(c["stop"])
        target_hit=high>=finite(c["target"])
        entry_hit=low<=finite(c["entry_high"]) and high>=finite(c["entry_low"])
        if stop_hit and target_hit:status="AMBIGUOUS_INTRABAR_ORDER"
        elif stop_hit:status="STOP_LEVEL_TOUCHED"
        elif target_hit:
            # Target can be hit even if user never entered; it is NOT P/L.
            status="TARGET_LEVEL_TOUCHED"
        elif entry_hit:status="ENTRY_ZONE_TOUCHED"
        else:status="MONITORING"
    prev_status=prev.get("status")
    fresh=prev_status!=status
    last_ts=prev.get("last_bar_end_utc")
    if last_ts==ts.isoformat() and prev_status==status:fresh=False
    key_text="|".join([c["delivery_key"],status,ts.isoformat(),bar["source_hash"]])
    delivery_id=hashlib.sha256(key_text.encode()).hexdigest()
    return {"schema":SCHEMA,"symbol":c["symbol"],"delivery_key":c["delivery_key"],
            "status":status,"transition":status if fresh else "UNCHANGED",
            "alert":fresh and status!="MONITORING",
            "alert_dedup_key":delivery_id,
            "last_bar_end_utc":ts.isoformat(),"asof_observed_utc":iso(observed_at_utc).isoformat(),
            "source_sha":bar["source_hash"],"max_market_data_age_seconds":int(age),
            "reason":"BAR_TOUCH_NOT_A_TRADE_FILL","mode":SIDE_ONLY,
            "research_only":True,"execution":"NONE","real_money":"NO-GO",
            "orders":[],"user_notification_delivered":False}

def fixtures():
    date="2026-10-08T19:00:00Z"
    c={"symbol":"TEST","delivery_key":"TEST|A|20261008|fixture",
       "manual_approved":True,"research_authority_verified":True,
       "entry_low":100.0,"entry_high":102.0,"stop":95.0,"target":120.0,
       "origin_at_utc":"2026-10-08T18:00:00Z",
       "expires_at_utc":"2026-10-16T20:00:00Z",
       "source_asof_et":"2026-10-08","execution":"NONE","real_money":"NO-GO"}
    b={"symbol":"TEST","source_authorized":True,"source_provenance_verified":True,
       "source_hash":"c"*40,"timeframe":"15m","bar_end_utc":date,
       "low":101.0,"high":103.0}
    return c,b

def selftest():
    c,b=fixtures()
    kwargs={"observed_at_utc":"2026-10-08T19:10:00Z"}
    row=event(c,b,**kwargs)
    assert row["status"]=="ENTRY_ZONE_TOUCHED" and row["alert"]
    assert event(c,b,row,**kwargs)["alert"] is False
    q={**b,"low":94,"high":121}
    assert event(c,q,**kwargs)["status"]=="AMBIGUOUS_INTRABAR_ORDER"
    assert event(c,{**b,"low":94,"high":101},**kwargs)["status"]=="STOP_LEVEL_TOUCHED"
    assert event(c,{**b,"low":105,"high":121},**kwargs)["status"]=="TARGET_LEVEL_TOUCHED"
    assert event(c,b,**kwargs,halt=True)["status"]=="OFFICIAL_HALT"
    assert event(c,b,**kwargs,material_event=True)["status"]=="EVENT_VETO"
    assert event(c,b,**kwargs,invalidated=True)["status"]=="INVALIDATED"
    assert event(c,b,observed_at_utc="2026-10-08T19:40:00Z")["status"]=="SOURCE_STALE"
    expired=event(c,b,observed_at_utc="2026-10-16T20:00:00Z")
    assert expired["status"]=="EXPIRED" and expired["alert"] is True
    assert event(c,b,expired,observed_at_utc="2026-10-17T20:00:00Z")["alert"] is False
    for bad in [
        {**c,"research_authority_verified":False},
        {**c,"stop":102.1},
        {**c,"execution":"BUY"},
        {**c,"origin_at_utc":"2026-10-09T19:00:00Z"},
    ]:
        try:event(bad,b,**kwargs)
        except ValueError:pass
        else:raise AssertionError("UNSAFE_CANDIDATE_ADMITTED")
    for invalid in [
        {**b,"source_authorized":False},
        {**b,"bar_end_utc":"2026-10-08T20:00:00Z"},
        {**b,"low":0.0},
        {**b,"symbol":"OTHER"},
        {**b,"source_hash":"forged"}]:
        try:event(c,invalid,**kwargs)
        except ValueError:pass
        else:raise AssertionError("UNSAFE_BAR_ADMITTED")
    stopped=event(c,{**b,"low":94,"high":101},**kwargs)
    assert event(c,b,stopped,**kwargs)["transition"]=="TERMINAL_STATE_LOCKED"
    print("XRAY_MANUAL_FOLLOWUP_SHADOW_SELFTEST=PASS NO_ORDERS_NO_PUSH_CLAIM")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out")
    args=p.parse_args()
    if args.selftest:selftest();return
    # No live candidate source integration: never mint signals from fixtures.
    if args.out:
        Path(args.out).write_text(json.dumps({
            "schema":SCHEMA,"status":"SHADOW_NOT_CONNECTED_TO_CANONICAL_DELIVERY",
            "orders":[],"execution":"NONE","real_money":"NO-GO",
            "user_notification_delivered":False,"candidate_count":0},indent=2)+"\n")
        print("XRAY_MANUAL_FOLLOWUP_SHADOW=BLOCKED_LIVE_INTEGRATION")
    else:
        p.error("--selftest or --out needed")

if __name__=="__main__":
    main()
