#!/usr/bin/env python3
"""Bounded three-symbol 13x30min RTH completeness recheck, research-only.

Nasdaq Carteret incident 2026-10-15: a successful 1Day bar is not proof
of 13 complete RTH 30min bars. Never persist or promote provider OHLCV;
only exact-ASOF counts can be observed, without any candidate or AL output.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
from personal_sip_asof_three_symbol_canary import (
    SAMPLES, select, ROOT, need,
)
from source_epoch_freshness_guard import last_complete_session

SCHEMA="XRAY_RUNNER_THREE_SIP_RTH30_RECOVERY_WITNESS_V1"
NY=ZoneInfo("America/New_York")
UTC=dt.timezone.utc
RTH_BARS=13
MAX_PAGES=2


def exact_session(asof, now):
    need(now.tzinfo is not None, "NAIVE_CLOCK")
    need(last_complete_session(now)==asof, "NOT_LATEST_COMPLETED_SESSION")
    schedule=mcal.get_calendar("NASDAQ").schedule(
        start_date=asof,end_date=asof)
    need(len(schedule)==1, "NOT_OFFICIAL_SESSION")
    open_=schedule.iloc[0]["market_open"].to_pydatetime()
    close=schedule.iloc[0]["market_close"].to_pydatetime()
    need(close-open_==dt.timedelta(hours=6,minutes=30), "NON_STANDARD_SESSION_FAIL_CLOSED")
    need(close+dt.timedelta(minutes=5)<=now.astimezone(UTC)-dt.timedelta(minutes=15),
         "HISTORICAL_SIP_DELAY_NOT_MATURE")
    return [open_+dt.timedelta(minutes=30*i) for i in range(RTH_BARS)],           open_.isoformat(),(close+dt.timedelta(minutes=5)).isoformat()


def bar_clock(row):
    if type(row) is not dict:
        return None
    try:
        raw=row.get("t")
        stamp=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
        values=[row.get(x) for x in ("o","h","l","c","v")]
        if (stamp.tzinfo is None or
            not all(type(v) in (int,float) and math.isfinite(v) and v>0
                    for v in values) or
            not all(values[k] > 0 for k in range(4)) or
            values[1] < max(values[0],values[3],values[2]) or
            values[2] > min(values[0],values[1],values[3])):
            return None
        return stamp.astimezone(UTC)
    except (ValueError,TypeError,AttributeError,OverflowError):
        return None


def query(symbols,asof,key,secret,now):
    need(bool(key and secret),"NO_RUNNER_CREDENTIALS")
    slots,start,end=exact_session(asof,now)
    base="https://data.alpaca.markets/v2/stocks/bars"
    output={}
    token=None
    for page in range(MAX_PAGES):
        p={"symbols":",".join(symbols),"timeframe":"30Min",
           "start":start,"end":end,"feed":"sip","adjustment":"raw",
           "limit":10000}
        if token is not None:p["page_token"]=token
        req=urllib.request.Request(
            base+"?"+urllib.parse.urlencode(p),
            headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
                     "Accept":"application/json",
                     "User-Agent":"xray-personal-rth30-recovery-witness/1.0"})
        with urllib.request.urlopen(req,timeout=24) as resp:
            payload=json.loads(resp.read())
        need(type(payload) is dict and type(payload.get("bars")) is dict,
             "PROVIDER_SCHEMA")
        need(set(payload["bars"]).issubset(symbols), "FOREIGN_SYMBOL")
        for symbol,rows in payload["bars"].items():
            need(type(rows) is list,"BAR_LIST_INVALID")
            output.setdefault(symbol,[]).extend(rows)
        nxt=payload.get("next_page_token")
        need(nxt is None or type(nxt) is str and nxt and nxt!=token,
             "PAGE_TOKEN_INVALID")
        if nxt is None:return output,page+1
        token=nxt
    need(False,"PAGINATION_BOUND_REACHED")


def assess(source_rows,slot_times):
    need(type(source_rows) is dict and len(slot_times)==RTH_BARS and
         len(set(slot_times))==RTH_BARS,"INVALID_SOURCE_OR_SESSION")
    missing=0
    complete=0
    invalid=0
    for symbol in SAMPLES:
        rows=source_rows.get(symbol,[])
        need(type(rows) is list,"BAR_LIST_INVALID")
        seen={}
        invalid_this=False
        for r in rows:
            stamp=bar_clock(r)
            if stamp is None:
                invalid_this=True
                continue
            if stamp in slot_times:
                seen[stamp]=seen.get(stamp,0)+1
        gaps=sum(seen.get(t,0)==0 for t in slot_times)
        duplicates=any(x>1 for x in seen.values())
        if invalid_this or duplicates:
            invalid+=1
        if gaps or invalid_this or duplicates:
            missing+=1
        else:
            complete+=1
    return {"sample_count":len(SAMPLES),
            "rth30_complete_symbols":complete,
            "rth30_incomplete_or_integrity_unknown_symbols":missing,
            "invalid_or_duplicate_symbol_count":invalid}


def evaluate(root,sina,asof,keys,provider,now):
    missing_source=select(root,sina,asof)
    slots,_,_=exact_session(asof,now)
    result={"schema":SCHEMA,"asof_et":asof,"sample_count":len(SAMPLES),
            "root_same_epoch_sealed":True,
            "sina_daily_asof_missing_sample_count":len(missing_source),
            "status":"NO_SINA_MISSING_SAMPLES_NO_REQUEST",
            "rth30_complete_symbols":0,
            "rth30_incomplete_or_integrity_unknown_symbols":len(SAMPLES),
            "invalid_or_duplicate_symbol_count":0,
            "provider_page_requests":0,
            "provider":"ALPACA_HISTORICAL_SIP_30MIN",
            "recovery_ready_for_independent_recheck":False,
            "historical_20261015_market_incident_does_not_prove_individual_gap_cause":True,
            "canonical_price_dv30_attested":False,
            "canonical_history_260_52_attested":False,
            "mc_authority_attested":False,
            "terminal_attested":False,"alpha_go":False,
            "registered_r92":False,"device_receipt_attested":False,
            "no_raw_ohlcv_persisted":True,
            "canonical_files_mutated":False,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    if not missing_source:
        return result
    if not all(keys):
        result["status"]="RUNNER_CREDENTIALS_NOT_CONFIGURED"
        return result
    try:
        rows,pages=provider(list(SAMPLES),asof,*keys,now)
        need(1<=pages<=MAX_PAGES and
             type(rows) is dict and set(rows).issubset(SAMPLES),
             "PROVIDER_PAGES_OR_SCOPE")
        result.update(assess(rows,slots))
        result["provider_page_requests"]=pages
        result["status"]=(
            "RTH30_THREE_SYMBOLS_SOURCE_COMPLETE_RECHECK_ONLY"
            if result["rth30_complete_symbols"]==len(SAMPLES)
            else "RTH30_SOURCE_INCOMPLETE_FAIL_CLOSED")
        result["recovery_ready_for_independent_recheck"]=(
            result["rth30_complete_symbols"]==len(SAMPLES))
    except urllib.error.HTTPError as e:
        result["status"]="RUNNER_SIP_HTTP_DENIED_OR_UNAVAILABLE"
    except (ValueError,TypeError,TimeoutError,urllib.error.URLError,OSError):
        result["status"]="RUNNER_SIP_RTH30_SOURCE_OR_INTEGRITY_UNKNOWN"
    return result


def selftest():
    now=dt.datetime(2026,10,16,0,30,tzinfo=UTC)
    slots,_,_=exact_session("2026-10-15",now)
    make=lambda t:{"t":t.isoformat(),"o":101.0,"h":102.0,"l":100.0,
                   "c":101.5,"v":1111}
    full={s:[make(t) for t in slots] for s in SAMPLES}
    assert assess(full,slots)["rth30_complete_symbols"]==3
    partial={s:list(rows) for s,rows in full.items()}
    for s in SAMPLES:partial[s]=[x for x in partial[s] if
        x["t"] not in {slots[7].isoformat(),slots[8].isoformat()}]
    neg=assess(partial,slots)
    assert neg["rth30_complete_symbols"]==0 and         neg["rth30_incomplete_or_integrity_unknown_symbols"]==3
    duplicate={s:list(v) for s,v in full.items()}
    duplicate["AAPL"].append(make(slots[0]))
    assert assess(duplicate,slots)["invalid_or_duplicate_symbol_count"]==1
    invalid={s:list(v) for s,v in full.items()}
    invalid["MSFT"][1]=dict(invalid["MSFT"][1],h=-4.0)
    assert assess(invalid,slots)["invalid_or_duplicate_symbol_count"]==1
    truncated={s:list(v) for s,v in full.items()}
    truncated["NVDA"]=[]
    assert assess(truncated,slots)["rth30_complete_symbols"]==2
    try:exact_session("2026-10-14",now)
    except ValueError as e:assert "NOT_LATEST_COMPLETED_SESSION" in str(e)
    else:raise AssertionError("OLD_ASOF_ACCEPTED")
    try:exact_session("2026-10-15",dt.datetime(2026,10,15,19,tzinfo=UTC))
    except ValueError:pass
    else:raise AssertionError("PRE_CLOSED_ASOF_ACCEPTED")
    print("XRAY_RTH30_RECOVERY_SELFTEST=PASS_7_NEGATIVES_NO_SOURCE_OR_ALPHA_PROMOTION")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    o=p.parse_args()
    if o.selftest:return selftest()
    if o.out is None:p.error("--out required")
    asof=last_complete_session(dt.datetime.now(UTC))
    root=json.loads((ROOT/"orchestrator_state.json").read_text())
    sina=json.loads((ROOT/"sina_state.json").read_text())
    key=os.getenv("XRAY_ALPACA_DATA_KEY_ID") or os.getenv("XRAY_ALPACA_API_KEY_ID") or ""
    secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or os.getenv("XRAY_ALPACA_API_SECRET_KEY") or ""
    result=evaluate(root,sina,asof,(key,secret),query,dt.datetime.now(UTC))
    o.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_RTH30_RECOVERY_COUNTS_ONLY="+json.dumps({
        k:result[k] for k in (
            "asof_et","status","rth30_complete_symbols",
            "rth30_incomplete_or_integrity_unknown_symbols",
            "provider_page_requests","recovery_ready_for_independent_recheck")
        },sort_keys=True))


if __name__=="__main__":
    main()
