#!/usr/bin/env python3
"""Personal Nasdaq exact-ASOF 260/52+daily30 joint cohort: 30Min SIP RTH bound.

Only same-run, exact-root research artifacts may establish the source cohort.
Uses historical 30Min SIP RTH slots and day closes with daily volume as ceiling.
Closing auction/corrections, official primary DV30, MC, G9, AL/R92 and vendor
redistribution are NEVER attested. Never store raw OHLCV or actual prices.
"""
from __future__ import annotations
import argparse
from collections import Counter
import datetime as dt
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from zoneinfo import ZoneInfo
from alpaca_full_universe_asof_sip_availability import historical_request_window, sha
from alpaca_personal_price_current_exact30 import (
    classify_mixed_full_and_early, dates30, STATES)
from alpaca_full_universe_30d_daily_proxy_shadow import VALID as D30_HIGH
from alpaca_sip_paginated_transport_shadow import SYMBOL_RE
from alpaca_sip_request_pacer import PACER
from source_epoch_freshness_guard import last_complete_session

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_PERSONAL_JOINT_HISTORY_DAILY30_EXACT_RTH30_BOUND_V1"
LONG="SHADOW_260_DAILY_52_WEEK_OBSERVED"
NY=ZoneInfo("America/New_York")
BASE="https://data.alpaca.markets/v2/stocks/bars"
BATCH=8
PAGES=32
MAX_CALLS=900
MAX_SYMBOL_ROWS=1200
MAX_RESPONSE_BYTES=3500000
PROVIDER_UNKNOWN="UNKNOWN_HISTORICAL_SIP_RTH_PROVIDER_STOP"
RTH_POSITIVE="LOWER_BOUND_GE_50M_SHADOW"
RTH_NEGATIVE="UPPER_BOUND_LT_50M_SHADOW"
RTH_AMBIGUOUS="AMBIGUOUS_BETWEEN_BOUNDS_SHADOW"
RTH_UNVERIFIED="UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW"


def need(ok, why):
    if not ok:
        raise ValueError("XRAY_PERSONAL_JOINT_RTH30_"+why)


def joint_source(history, bridge, now):
    need(type(history) is dict and type(bridge) is dict
         and type(now) is dt.datetime and now.tzinfo is not None,
         "INPUT_SCHEMA")
    asof=last_complete_session(now)
    need(history.get("asof_et")==bridge.get("asof_et")==asof,
         "LATEST_ASOF")
    need(bridge.get("schema")=="XRAY_PERSONAL_SIP_ROOT_SOURCE_BRIDGE_V1"
         and bridge.get("same_asof_same_universe_join") is True
         and bridge.get("research_observations_not_canonical_pass") is True
         and bridge.get("joint_scope_has_no_rth_mc_technical_or_signal_authority") is True
         and bridge.get("no_c417_dv30_or_mc_pass") is True,
         "SOURCE_BRIDGE_AUTHORITY")
    need(history.get("schema")==
         "XRAY_PERSONAL_FULL_NASDAQ_SIP_260_DAILY_52_WEEK_RESEARCH_V1"
         and history.get("no_vendor_ohlcv_persisted") is True
         and history.get("canonical_price_history_mc_untouched") is True
         and history.get("registered_R92_count")==0
         and history.get("source_rights_not_inferred") is True,
         "HISTORY_NO_AUTHORITY")
    need(all(d.get("execution")=="NONE" and d.get("real_money")=="NO-GO"
             for d in (history,bridge)), "NO_EXECUTION")
    h=history.get("symbol_classifications")
    d30=(history.get("daily30_source_proxy") or {}).get("symbol_classifications")
    need(type(h) is dict and type(d30) is dict and
         set(h)==set(d30) and
         len(h)==history.get("scope_count")==bridge.get("identity_scope_count") and
         bridge.get("exact_identity_queue_sha256")==history.get(
             "source_full_identity_queue_sha256") and
         sha(sorted(h))==bridge.get("exact_identity_queue_sha256"),
         "UNIVERSE_SHA")
    syms=sorted(s for s in h if h[s]==LONG and d30[s]==D30_HIGH)
    need(all(SYMBOL_RE.fullmatch(s) for s in syms)
         and len(syms)==bridge.get(
             "260_52_and_daily30_ge50m_joint_research_count")
         and sha(syms)==bridge.get("260_52_and_daily30_ge50m_joint_sha256")
         and len(syms)<=1500, "COHORT_SHA_OR_LIMIT")
    need(bridge.get("daily30_source_proxy_not_official_rth_dv30") is True
         and bridge.get("no_official_rth_exact_volume") is True
         and history["daily30_source_proxy"].get(
             "research_daily_proxy_not_official_rth_dv30") is True,
         "RTH_BEFORE_PROOF")
    return asof,syms,dates30(asof)


def pager(symbols,tf,start,end,asof,credentials,calls):
    need(type(symbols) is list and 1<=len(symbols)<=BATCH
         and symbols==sorted(set(symbols))
         and tf in ("1Day","30Min") and len(start)>10 and len(end)>10,
         "FETCH_SCOPE")
    rows={s:[] for s in symbols};seen={s:set() for s in symbols};used=set()
    token=None
    for _ in range(PAGES):
        need(calls[0]<MAX_CALLS,"SOURCE_CALL_BUDGET")
        params={"symbols":",".join(symbols),"timeframe":tf,"feed":"sip",
                "adjustment":"raw","sort":"asc","start":start,"end":end,
                "limit":"10000","asof":asof}
        if token:params["page_token"]=token
        req=urllib.request.Request(BASE+"?"+urllib.parse.urlencode(params),
            headers={"APCA-API-KEY-ID":credentials[0],
                     "APCA-API-SECRET-KEY":credentials[1],
                     "Accept":"application/json",
                     "User-Agent":"NASDAQ-XRAY-Personal-Historical-Research/1.0"})
        PACER.pace()  # Every page, not merely every 8-symbol batch.
        calls[0]+=1
        try:
            with urllib.request.urlopen(req,timeout=40) as res:
                need(res.status==200,"HTTP_NON200")
                raw=res.read(MAX_RESPONSE_BYTES+1)
        except urllib.error.HTTPError as exc:
            raise RuntimeError("ALPACA_HTTP_"+str(exc.code)) from exc
        except (TimeoutError,urllib.error.URLError) as exc:
            raise RuntimeError("ALPACA_NETWORK_UNAVAILABLE") from exc
        need(len(raw)<=MAX_RESPONSE_BYTES,"RESPONSE_OVERSIZE")
        try:doc=json.loads(raw)
        except (TypeError,ValueError) as exc:
            raise RuntimeError("ALPACA_JSON_INVALID") from exc
        need(type(doc) is dict and type(doc.get("bars")) is dict,
             "PAGE_SCHEMA")
        fresh=0
        for sym,items in doc["bars"].items():
            need(sym in rows and type(items) is list,"FOREIGN_OR_BAD_BARS")
            for item in items:
                need(type(item) is dict and type(item.get("t")) is str
                     and item["t"] and item["t"] not in seen[sym],
                     "DUPLICATE_OR_BAD_BAR_TIMESTAMP")
                seen[sym].add(item["t"])
                rows[sym].append(item);fresh+=1
                need(len(rows[sym])<=MAX_SYMBOL_ROWS,"EXCESSIVE_SYMBOL_ROWS")
        nxt=doc.get("next_page_token")
        if nxt is None:return rows
        need(type(nxt) is str and nxt and len(nxt)<2048
             and nxt not in used and fresh>0, "PAGINATION_NO_PROGRESS")
        used.add(nxt);token=nxt
    raise RuntimeError("ALPACA_PAGE_BUDGET_EXHAUSTED")



# Incomplete 30Min slots cannot pass the strict RTH gate.
# LOW * volume is a deliberately conservative RESEARCH PROXY, NOT a genuine
# trade-notional lower bound: Alpaca trade conditions can update bar VOLUME
# without updating HIGH/LOW (e.g. odd lots). Actual trade price for a
# volume-contributing print might be LOWER than the reported bar low.
# DAILY CLOSE * observed volume is also not a mathematical floor.
# Thus neither observed proxy may prove official DV30 >= $50M.
# This remains research-only, not corrected/auction/PIT primary market data.
PARTIAL_HIGH="PARTIAL_OBSERVED_RTH_BARLOW_NOTIONAL_PROXY_GE50M_RESEARCH_ONLY"
PARTIAL_UNRESOLVED="PARTIAL_OBSERVED_RTH_BARLOW_NOTIONAL_PROXY_INDETERMINATE"
PARTIAL_REJECTED="PARTIAL_SOURCE_SCHEMA_OR_VOLUME_REJECTED"

def partial_missing_slot_bounds(daily,halfhour,days):
    """Return bar-LOW-weighted research proxy, NOT a trade-notional lower bound."""
    from decimal import Decimal
    from alpaca_personal_price_current_exact30 import cached_official_window
    from alpaca_sip_30min_rth_lower_bound_pilot import stamp,data_check
    from alpaca_sip_4symbol_30min_rth_shadow import LIMIT
    need(type(days) is list and len(days)==30 and len(set(days))==30
         and days==sorted(days) and type(daily) is list
         and type(halfhour) is list,"PARTIAL_SOURCE_INPUT")
    expected={}
    windows={}
    for day in days:
        start,close,n=cached_official_window(day)
        need(n in (210,390) and n%30==0,"PARTIAL_SESSION_WINDOW")
        windows[day]=(start,close)
        for i in range(n//30):
            slot=start+dt.timedelta(minutes=30*i)
            need(slot not in expected and slot<close,"PARTIAL_SLOT_CLOCK")
            expected[slot]=day
    daybars={}
    for bar in daily:
        day=stamp(bar).astimezone(NY).date().isoformat()
        if day in windows:
            need(day not in daybars,"PARTIAL_DUPLICATE_DAILY")
            data_check(bar)
            daybars[day]=bar
    need(set(daybars)==set(days),"PARTIAL_DAILY_NOT_EXACT30")
    observed={}
    for bar in halfhour:
        at=stamp(bar)
        if at in expected:
            need(at not in observed,"PARTIAL_DUPLICATE_30MIN")
            volume=data_check(bar)
            # Bar LOW (not daily close) reduces upward pricing bias.
            # Bar VOLUME may contain excluded LOW prints: still ONLY A PROXY.
            # Do not persist vendor OHLCV in any research artifact.
            try:
                o,h,l,c=(Decimal(str(bar[k])) for k in ("o","h","l","c"))
            except (TypeError,ValueError,KeyError,ArithmeticError) as exc:
                raise ValueError("XRAY_PERSONAL_JOINT_RTH30_PARTIAL_BAD_BAR_OHLC") from exc
            need(all(p.is_finite() and p>0 for p in (o,h,l,c)) and
                 l<=o<=h and l<=c<=h,
                 "PARTIAL_BAD_BAR_PRICE_ORDER")
            observed[at]=(volume,l)
        elif any(start<=at<close for start,close in windows.values()):
            raise ValueError("XRAY_PERSONAL_JOINT_RTH30_PARTIAL_OFFGRID_RTH")
    missing=set(expected)-set(observed)
    need(bool(missing),"PARTIAL_EXPECTED_GAP_NOT_PRESENT")
    perday={day:0 for day in days}
    notional={day:Decimal(0) for day in days}
    for slot,(volume,low) in observed.items():
        day=expected[slot]
        perday[day]+=volume
        notional[day]+=low*volume
    lower=[]
    for day in days:
        daily_volume=data_check(daybars[day])
        need(perday[day]<=daily_volume,"PARTIAL_RTH_GREATER_THAN_DAILY")
        lower.append(notional[day])
    lower.sort()
    conservative_median=(lower[14]+lower[15])/Decimal(2)
    kind=PARTIAL_HIGH if conservative_median>=LIMIT else PARTIAL_UNRESOLVED
    return kind,len(missing),len({expected[slot] for slot in missing})


def measure(asof,syms,days,source,now,pace=0):
    need(len(days)==30 and days[-1]==asof and
         syms==sorted(set(syms)), "MEASUREMENT_INPUT")
    status={s:"UNKNOWN_UNCHECKED" for s in syms}
    integrity_causes={}
    partial_counts=Counter();partial_status={};partial_missing_slots=0;partial_missing_days=0
    calls=[0];stop=None;attempted=0
    # Close+5 must be in delayed historical SIP window, not a future ET midnight.
    _,end=historical_request_window(asof,now)
    start=dt.datetime.combine(dt.date.fromisoformat(days[0]),dt.time(),
                              NY).isoformat(timespec="seconds")
    need(dt.datetime.fromisoformat(start)<dt.datetime.fromisoformat(end),
         "WINDOW_ORDER")
    for k in range(0,len(syms),BATCH):
        group=syms[k:k+BATCH]
        if stop is not None:
            for name in group:status[name]=PROVIDER_UNKNOWN
            continue
        try:
            daily=source(group,"1Day",start,end,asof,calls)
            half=source(group,"30Min",start,end,asof,calls)
            need(set(daily)==set(group) and set(half)==set(group),
                 "PROVIDER_PARTITION")
            for name in group:
                try:
                    out=classify_mixed_full_and_early(
                        daily[name],half[name],days)
                    need(out in STATES,"EXACT30_CLASSIFIER_SET")
                    status[name]=out
                except (ValueError,TypeError,KeyError,OverflowError) as exc:
                    status[name]=RTH_UNVERIFIED
                    # No raw market response or prices are disclosed.
                    v=str(exc)
                    safe={
                        "EXACT_30_DAILY_SET", "EARLY_AND_FULL_BAR_COUNTS_EXACT",
                        "DAILY_VOLUME_BOUND", "DUPLICATE_DAILY",
                        "DUPLICATE_30MIN", "CLOSE_PRICE", "BOUNDS_INVERSION",
                        "BAR_SLOT_INTEGRITY", "OFFICIAL_SESSION_LENGTH",
                    }
                    code=v.removeprefix("XRAY_PERSONAL_CURRENT_PRICE_")
                    integrity_causes[name]=(code if code in safe else
                                            "RTH_UNCLASSIFIED_DATA_INTEGRITY")
                    if code=="EARLY_AND_FULL_BAR_COUNTS_EXACT":
                        try:
                            kind,missing_slots,missing_days=partial_missing_slot_bounds(
                                daily[name],half[name],days)
                            partial_counts[kind]+=1
                            partial_status[name]=kind
                            partial_missing_slots+=missing_slots
                            partial_missing_days+=missing_days
                        except (ValueError,TypeError,KeyError,OverflowError):
                            partial_counts[PARTIAL_REJECTED]+=1
                            partial_status[name]=PARTIAL_REJECTED
            attempted+=len(group)
        except (RuntimeError,ValueError,TimeoutError,OSError) as exc:
            v=str(exc)
            stop=(v if v.startswith(("ALPACA_HTTP_","ALPACA_PAGE_"))
                  else "SOURCE_CALL_BUDGET_REACHED_NO_RTH"
                  if "SOURCE_CALL_BUDGET" in v
                  else "UNKNOWN_RTH_30MIN_TRANSPORT_OR_INTEGRITY")
            for name in group:status[name]=PROVIDER_UNKNOWN
        if pace:time.sleep(pace)
    count=dict(sorted(Counter(status.values()).items()))
    need(sum(partial_counts.values())==sum(
         v=="EARLY_AND_FULL_BAR_COUNTS_EXACT" for v in integrity_causes.values())
         and set(partial_counts)<={PARTIAL_HIGH,PARTIAL_UNRESOLVED,
                                  PARTIAL_REJECTED} and
         dict(sorted(Counter(partial_status.values()).items()))==
         dict(sorted(partial_counts.items())) and
         set(partial_status)=={sym for sym,code in integrity_causes.items()
             if code=="EARLY_AND_FULL_BAR_COUNTS_EXACT"} and
         all(status[sym]==RTH_UNVERIFIED for sym in partial_status),
         "PARTIAL_DIAGNOSTIC_ACCOUNTING")
    need(set(integrity_causes).issubset(
         {k for k,v in status.items() if v==RTH_UNVERIFIED}),
         "INTEGRITY_CAUSE_SCOPE")
    need(sum(count.values())==len(syms)
         and set(status)==set(syms)
         and set(count).issubset(
             {RTH_POSITIVE,RTH_NEGATIVE,RTH_AMBIGUOUS,
              RTH_UNVERIFIED,PROVIDER_UNKNOWN}),
         "COMPLETE_COHORT_PARTITION")
    return {
        "schema":SCHEMA,"asof_et":asof,
        "joint_history260_daily30_cohort_sha256":sha(syms),
        "joint_cohort_count":len(syms),
        "official_session_count":30,
        "feed":"ALPACA_DELAYED_HISTORICAL_SIP",
        "source_rth_granularity":"30Min_09_30_TO_OFFICIAL_EXCHANGE_CLOSE",
        "classifications":dict(sorted(status.items())),
        "classification_counts":count,
        "rth_lower_bound_ge50m_shadow_count":count.get(RTH_POSITIVE,0),
        "rth_upper_bound_lt50m_shadow_count":count.get(RTH_NEGATIVE,0),
        "rth_ambiguous_shadow_count":count.get(RTH_AMBIGUOUS,0),
        "rth_incomplete_or_unknown_count":(
            count.get(RTH_UNVERIFIED,0)+count.get(PROVIDER_UNKNOWN,0)),
        "source_api_calls":calls[0],"source_call_budget":MAX_CALLS,
        "symbols_attempted_count":attempted,
        "symbol_rth_integrity_failure_codes":dict(sorted(integrity_causes.items())),
        "rth_integrity_cause_counts":dict(sorted(
            Counter(integrity_causes.values()).items())),
        "partial_missing_slot_research_counts":dict(sorted(partial_counts.items())),
        "partial_missing_slot_research_by_symbol":dict(sorted(partial_status.items())),
        "partial_missing_slot_symbolic_only_never_canonical":True,
        "partial_notional_method":"SUM_OBSERVED_30MIN_BAR_LOW_TIMES_VOLUME_PER_OFFICIAL_SESSION",
        "partial_no_daily_close_proxy_or_unobserved_zero_fill":True,
        "partial_notional_source_trade_conditions_unattested":True,
        "partial_notional_proxy_not_mathematical_trade_floor":True,
        "partial_missing_slot_total_observed_gap_count":partial_missing_slots,
        "partial_missing_slot_affected_session_total":partial_missing_days,
        "partial_research_never_promotes_strict_rth":True,
        "source_stop_class":stop,
        "status":"RTH_30MIN_PERSONAL_SOURCE_SHADOW_NO_CANONICAL_AUTHORITY",
        "official_RTH_close_auction_volume_attested":False,
        "official_RTH_corrections_attested":False,
        "same_issuer_corporate_action_adjustment_attested":False,
        "official_c417_primary_dv30_attested":False,
        "source_rights_not_inferred":True,
        "canonical_master_price_history_mc_untouched":True,
        "registered_R92_count":0,"vendor_ohlcv_persisted":False,
        "execution":"NONE","real_money":"NO-GO"
    }


def selftest():
    from alpaca_rth_minute_integrity_shadow import official_window
    asof="2026-10-14"
    now=dt.datetime(2026,10,14,22,tzinfo=dt.timezone.utc)
    dates=dates30(asof)
    symbols=["AAPL"]
    fp=sha(symbols)
    h={"schema":"XRAY_PERSONAL_FULL_NASDAQ_SIP_260_DAILY_52_WEEK_RESEARCH_V1",
       "asof_et":asof,"symbol_classifications":{"AAPL":LONG},
       "daily30_source_proxy":{
           "symbol_classifications":{"AAPL":D30_HIGH},
           "research_daily_proxy_not_official_rth_dv30":True},
       "scope_count":1,"source_full_identity_queue_sha256":fp,
       "no_vendor_ohlcv_persisted":True,
       "canonical_price_history_mc_untouched":True,
       "registered_R92_count":0,"source_rights_not_inferred":True,
       "execution":"NONE","real_money":"NO-GO"}
    b={"schema":"XRAY_PERSONAL_SIP_ROOT_SOURCE_BRIDGE_V1",
       "asof_et":asof,"same_asof_same_universe_join":True,
       "research_observations_not_canonical_pass":True,
       "joint_scope_has_no_rth_mc_technical_or_signal_authority":True,
       "no_c417_dv30_or_mc_pass":True,"identity_scope_count":1,
       "exact_identity_queue_sha256":fp,
       "260_52_and_daily30_ge50m_joint_research_count":1,
       "260_52_and_daily30_ge50m_joint_sha256":fp,
       "daily30_source_proxy_not_official_rth_dv30":True,
       "no_official_rth_exact_volume":True,
       "execution":"NONE","real_money":"NO-GO"}
    a,n,d=joint_source(h,b,now)
    need(a==asof and n==symbols and d==dates,"POSITIVE_JOINT")
    b["260_52_and_daily30_ge50m_joint_sha256"]="x"*64
    try:joint_source(h,b,now)
    except ValueError as exc:
        need("COHORT_SHA_OR_LIMIT" in str(exc),"BAD_SHA_FENCE_REASON")
    else:raise AssertionError("UNBOUND_260_PRICE_JOIN_ACCEPTED")
    b["260_52_and_daily30_ge50m_joint_sha256"]=fp
    daily=[];rth=[]
    for day in dates:
        start,close,minutes=official_window(day)
        stamp=dt.datetime.combine(dt.date.fromisoformat(day),dt.time(),
            NY).astimezone(dt.timezone.utc).isoformat()
        daily.append({"t":stamp,"o":10,"h":11,"l":9,"c":10,"v":9000000})
        for i in range(minutes//30):
            moment=start+dt.timedelta(minutes=30*i)
            rth.append({"t":moment.isoformat(),"o":10,"h":11,
                        "l":9,"c":10,"v":500000})
    def synth(group,tf,start,end,day,calls):
        need(group==symbols and day==asof and
             start.startswith(dates[0]),"SELFTEST_REQUEST")
        calls[0]+=1
        return {"AAPL":daily if tf=="1Day" else rth}
    x=measure(asof,symbols,dates,synth,now)
    need(x["rth_lower_bound_ge50m_shadow_count"]==1
         and x["source_api_calls"]==2
         and x["registered_R92_count"]==0,"RTH_BOUND_POSITIVE_NO_ALPHA")
    kind,missing,affected=partial_missing_slot_bounds(daily,rth[:-1],dates)
    need(kind==PARTIAL_HIGH and missing==1 and affected==1,
         "PARTIAL_HIGH_OBSERVED_ONLY_NO_ZERO_FILL")
    low_rth=[dict(row,v=10000) for row in rth[:-1]]
    kind,missing,affected=partial_missing_slot_bounds(daily,low_rth,dates)
    need(kind==PARTIAL_UNRESOLVED and missing==1 and affected==1,
         "PARTIAL_LOW_MUST_REMAIN_UNRESOLVED")
    # Adversarial counterexample: daily close $10 would seem to clear $50m
    # although every observed $0.10-$0.30 trade bar cannot prove $50m.
    small_prices=[dict(row,o=0.2,h=0.3,l=0.1,c=0.2)
                  for row in rth[:-1]]
    kind,missing,affected=partial_missing_slot_bounds(
        daily,small_prices,dates)
    need(kind==PARTIAL_UNRESOLVED and missing==1,
         "DAILY_CLOSE_TIMES_VOLUME_IS_NOT_DOLLAR_VOLUME_FLOOR")
    for broken in (
        dict(rth[0],l=0),
        dict(rth[0],l=11.01),
        dict(rth[0],o=-1),
        dict(rth[0],l="NaN"),
    ):
        test_bars=rth[:-1].copy();test_bars[0]=broken
        try:partial_missing_slot_bounds(daily,test_bars,dates)
        except ValueError:pass
        else:raise AssertionError("FORGED_BAR_PRICE_ACCEPTED")
    for bad in (rth[:-1]+[rth[0]],
                rth[:-1]+[dict(rth[0],t=(dt.datetime.fromisoformat(
                    rth[0]["t"])+dt.timedelta(minutes=1)).isoformat())]):
        try:partial_missing_slot_bounds(daily,bad,dates)
        except ValueError:pass
        else:raise AssertionError("PARTIAL_DUPLICATE_OR_OFFGRID_ACCEPTED")
    bad_rth=rth[:-1]
    def partial(group,tf,start,end,day,calls):
        calls[0]+=1
        return {"AAPL":daily if tf=="1Day" else bad_rth}
    y=measure(asof,symbols,dates,partial,now)
    need(y["rth_incomplete_or_unknown_count"]==1 and
         y["rth_lower_bound_ge50m_shadow_count"]==0 and
         y["rth_integrity_cause_counts"] == {
             "EARLY_AND_FULL_BAR_COUNTS_EXACT":1} and
         y["partial_missing_slot_research_counts"]=={PARTIAL_HIGH:1} and
         y["partial_missing_slot_research_by_symbol"]=={"AAPL":PARTIAL_HIGH} and
         y["partial_missing_slot_symbolic_only_never_canonical"] is True and
         y["partial_notional_proxy_not_mathematical_trade_floor"] is True and
         y["partial_research_never_promotes_strict_rth"] is True,
         "MISSING_LAST_RTH_SLOT_DIAGNOSED_NOT_PASS")
    def blocked(*args):
        raise RuntimeError("ALPACA_HTTP_429")
    z=measure(asof,symbols,dates,blocked,now)
    need(z["source_stop_class"]=="ALPACA_HTTP_429" and
         z["rth_incomplete_or_unknown_count"]==1 and
         z["partial_missing_slot_research_by_symbol"]=={},
         "RATE_LIMIT_NEVER_PASS")
    def budget(*args):
        raise ValueError("XRAY_PERSONAL_JOINT_RTH30_SOURCE_CALL_BUDGET")
    limited=measure(asof,symbols,dates,budget,now)
    need(limited["source_stop_class"]=="SOURCE_CALL_BUDGET_REACHED_NO_RTH"
         and limited["rth_lower_bound_ge50m_shadow_count"]==0,
         "CALL_BUDGET_EXHAUSTION_NOT_VENDOR_INTEGRITY")
    print("XRAY_PERSONAL_JOINT_RTH30_SELFTEST=PASS_BAR_LOW_NOTIONAL_PROXY_NOT_A_TRADE_FLOOR_NO_PRIMARY")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--history",type=Path)
    ap.add_argument("--bridge",type=Path)
    ap.add_argument("--out",type=Path)
    x=ap.parse_args()
    if x.selftest:
        selftest();return
    need(all(z is not None and z.is_file() for z in (x.history,x.bridge))
         and x.out is not None and
         not x.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "SAME_RUN_REPORTS_AND_EPHEMERAL_OUTPUT")
    now=dt.datetime.now(dt.timezone.utc)
    history=json.loads(x.history.read_text())
    bridge=json.loads(x.bridge.read_text())
    asof,syms,days=joint_source(history,bridge,now)
    key=os.getenv("XRAY_ALPACA_DATA_KEY_ID","").strip()
    secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY","").strip()
    need(key and secret,"PRIVATE_PERSONAL_SIP_CREDENTIALS_REQUIRED")
    def real(group,tf,start,end,day,calls):
        return pager(group,tf,start,end,day,(key,secret),calls)
    out=measure(asof,syms,days,real,now,pace=0.85)
    x.out.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("XRAY_PERSONAL_JOINT_RTH30="+json.dumps({
        "asof_et":asof,"source_joint":len(syms),
        "rth30_lower_bound_ge50m":out["rth_lower_bound_ge50m_shadow_count"],
        "rth30_upper_bound_lt50m":out["rth_upper_bound_lt50m_shadow_count"],
        "rth30_ambiguous":out["rth_ambiguous_shadow_count"],
        "rth30_unknown":out["rth_incomplete_or_unknown_count"],
        "rth30_integrity_causes":out["rth_integrity_cause_counts"],
        "api_calls":out["source_api_calls"],
        "transport_stop":out["source_stop_class"],
        "R92":0},sort_keys=True))


if __name__=="__main__":
    main()
