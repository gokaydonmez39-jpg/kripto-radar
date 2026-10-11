#!/usr/bin/env python3
"""C4.18 exact NASDAQ 260x52 shadow transport validation.

No HTTP, provider auth, market-price storage, export, PRIMARY, R92 or orders.
A numeric 260x52 check never grants licensed C4.17 HISTORY_PASS.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

SCHEMA = "XRAY_C418_HISTORY_EXACT_SESSION_SHADOW_V1"
ROOT = Path(__file__).resolve().parent.parent
N_DAILY, N_WEEKS = 260, 52

def day(v):
    if not isinstance(v, str) or len(v) != 10: return None
    try:
        d = date.fromisoformat(v)
        return d if d.isoformat() == v else None
    except ValueError: return None

def official(asof):
    d = day(asof)
    if not d: raise ValueError("INVALID_ASOF")
    import pandas_market_calendars as mcal
    x = mcal.get_calendar("NASDAQ").valid_days(
        start_date=d-timedelta(days=550), end_date=d)
    result = tuple(t.date().isoformat() for t in x)[-N_DAILY:]
    if len(result)!=N_DAILY or result[-1]!=asof:
        raise ValueError("ASOF_NOT_OFFICIAL_COMPLETED_SESSION")
    return result

def report(asof, provider, symbols):
    return {
        "schema": SCHEMA, "asof_et": asof, "provider": provider,
        "status": "DATA_BLOCKED", "scope_count": len(symbols),
        "numeric_exact_260_count": 0, "nonpassing_count": len(symbols),
        "nonpassing_symbols": {}, "reason_counts": {},
        "production_authority": False, "can_create_PRIMARY": False,
        "can_create_HISTORY_PASS": False, "can_register_R92": False,
        "adjustment_and_corporate_actions_proven": False,
        "non_display_runner_rights_proven": False,
        "feed_independence_proven": False, "vendor_raw_data_exported": False,
        "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True,
    }

def audit(rows, symbols, asof, provider, required):
    r = report(asof, provider, symbols)
    if (not day(asof) or not isinstance(rows, list)
        or not isinstance(symbols, list) or not symbols
        or len(symbols)!=len(set(symbols))
        or not all(isinstance(s,str) and s for s in symbols)
        or not isinstance(provider,str) or not provider
        or not isinstance(required, (tuple,list))
        or len(required)!=N_DAILY or len(set(required))!=N_DAILY
        or tuple(required)!=tuple(sorted(required))
        or not all(day(x) for x in required)
        or required[-1]!=asof
        or len({(day(d).isocalendar().year,day(d).isocalendar().week)
                for d in required})<N_WEEKS):
        r["reason_counts"]={"INVALID_SCOPE_CALENDAR_OR_PRIVATE_ROWS":1}
        return r
    req, scope = set(required), set(symbols)
    present=defaultdict(set)
    bad=defaultdict(set)
    for row in rows:
        if not isinstance(row,dict):
            r["reason_counts"]={"INVALID_SOURCE_RECORD":1}
            return r
        sym, dt = row.get("symbol"), row.get("date")
        if not isinstance(sym,str) or sym not in scope or not day(dt):
            r["reason_counts"]={"UNBOUND_SOURCE_SYMBOL_OR_DATE":1}
            return r
        if dt>asof:
            bad[sym].add("FUTURE_DATED_BAR");continue
        if dt in present[sym]:
            bad[sym].add("DUPLICATE_SESSION")
        present[sym].add(dt)
        if dt not in req:
            # Historical preceding dates are optional; only pinned 260 count.
            continue
        vals={}
        for col in ("open","high","low","close","volume"):
            value=row.get(col)
            if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
                bad[sym].add("ZERO_INVALID_OR_NONFINITE_OHLCV")
            else: vals[col]=value
        if len(vals)==5 and (
            vals["low"]>min(vals["open"], vals["close"]) or
            vals["high"]<max(vals["open"], vals["close"], vals["low"])):
            bad[sym].add("OHLC_CONTRADICTION")
    for sym in symbols:
        why=set(bad[sym])
        if len(req & present[sym])!=N_DAILY:
            why.add("MISSING_OFFICIAL_SESSION")
        if why:
            r["nonpassing_symbols"][sym]=sorted(why)
        else:
            r["numeric_exact_260_count"]+=1
    r["nonpassing_count"]=len(r["nonpassing_symbols"])
    r["reason_counts"]=dict(sorted(Counter(
        reason for reasons in r["nonpassing_symbols"].values() for reason in reasons).items()))
    r["status"]="SHADOW_NUMERIC_COMPLETE" if not r["nonpassing_count"] else "SHADOW_NUMERIC_INCOMPLETE"
    return r

def git_blob_sha(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\x00"+raw).hexdigest()

def private_scope_check(input_path, expected_sha):
    repo_root=ROOT.resolve()
    if input_path.resolve().is_relative_to(repo_root):
        raise ValueError("PRIVATE_VENDOR_DATA_MUST_NOT_BE_IN_PUBLIC_REPO")
    content=(ROOT/"nasdaq-xray/canonical_current_price_dv30.json").read_bytes()
    c=json.loads(content)
    raw=json.loads(input_path.read_text())
    symbols=c.get("pass_symbols")
    if (git_blob_sha(content)!=expected_sha
        or c.get("asof_et")!=raw.get("asof_et")
        or not isinstance(symbols,list) or len(set(symbols))!=len(symbols)
        or c.get("pass_count")!=len(symbols)
        or raw.get("schema")!="XRAY_C418_PRIVATE_HISTORY_ROWS_V1"):
        raise ValueError("UNBOUND_OR_MALFORMED_CURRENT_PRICE_SCOPE")
    return audit(raw.get("rows"),symbols,c["asof_et"],raw.get("provider"),official(c["asof_et"]))

def selftest():
    required=official("2026-10-09")
    assert len(required)==260 and required[0]=="2025-09-29"
    def bar(s,d):
        return {"symbol":s,"date":d,"open":10.0,"high":10.3,
                "low":9.8,"close":10.1,"volume":500}
    base=[bar(s,d) for s in ("AAPL","QQQ") for d in required]
    def run(rows, count, reason=None):
        r=audit(rows,["AAPL","QQQ"],"2026-10-09","PRIVATE_TEST",required)
        assert r["numeric_exact_260_count"]==count, r
        assert not r["can_create_HISTORY_PASS"] and not r["can_register_R92"]
        assert not r["vendor_raw_data_exported"]
        if reason:assert reason in r["reason_counts"],r
    run(base,2)
    run(base[:-1],1,"MISSING_OFFICIAL_SESSION")
    for field,badval,reason in (
        ("volume",0,"ZERO_INVALID_OR_NONFINITE_OHLCV"),
        ("close",float("nan"),"ZERO_INVALID_OR_NONFINITE_OHLCV"),
        ("low",12,"OHLC_CONTRADICTION")):
        row=[dict(x) for x in base]; row[0][field]=badval
        run(row,1,reason)
    run(base+[dict(base[0])],1,"DUPLICATE_SESSION")
    run(base+[bar("QQQ","2026-10-11")],1,"FUTURE_DATED_BAR")
    assert audit(base+[bar("FAKE","2026-10-09")],["AAPL","QQQ"],
                 "2026-10-09","PRIVATE_TEST",required)["status"]=="DATA_BLOCKED"
    assert audit(None,["AAPL","QQQ"],"2026-10-09","PRIVATE_TEST",required)["status"]=="DATA_BLOCKED"
    print("XRAY_C418_EXACT_260_SIP_SHADOW_SELFTEST=PASS_9_CONTRACT_AND_NEGATIVE_TESTS_NO_PROMOTION")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--private-input",type=Path)
    parser.add_argument("--price-blob-sha")
    args=parser.parse_args()
    if args.selftest:selftest();return
    try:
        if not args.private_input or not args.price_blob_sha:
            raise ValueError("MISSING_PRIVATE_INPUT_OR_SHA")
        result=private_scope_check(args.private_input,args.price_blob_sha)
    except (OSError,ValueError,TypeError,KeyError,ImportError):
        result={
            "schema":SCHEMA,"status":"DATA_BLOCKED",
            "reason_counts":{"PRIVATE_AUTHORITATIVE_INPUT_OR_LICENSE_MISSING":1},
            "can_create_PRIMARY":False,"can_create_HISTORY_PASS":False,
            "can_register_R92":False,"vendor_raw_data_exported":False,
            "execution":"NONE","real_money":"NO-GO"}
    print(json.dumps(result,sort_keys=True))
    raise SystemExit(2)

if __name__=="__main__":
    main()
