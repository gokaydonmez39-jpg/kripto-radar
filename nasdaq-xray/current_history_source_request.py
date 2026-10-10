#!/usr/bin/env python3
"""Current C4.17 HISTORY source request, not market-data proof or signal.

Strictly binds the currently recorded PRICE pass set to a Git blob SHA,
and calculates the official 260-daily / 52-completed-week *expected* dates.
It fetches no vendor OHLCV, authorizes no licenses, and can never yield AL.
"""
from __future__ import annotations
import argparse
import copy
from datetime import date,timedelta
import hashlib
import json
import subprocess
from pathlib import Path
from history_transport_cache_guard import official_completed_sessions

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
PRICE="nasdaq-xray/canonical_current_price_dv30.json"
MASTER="nasdaq-xray/canonical_current_master_manifest.json"
SCHEMA="XRAY_C417_CURRENT_HISTORY_SOURCE_REQUEST_V1"

def sha256_lines(items):
    return hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()

def git_blob(path):
    return subprocess.check_output(["git","hash-object",str(REPO/path)],
                                   cwd=REPO,text=True).strip()

def expected_dates(asof):
    try:
        d=date.fromisoformat(asof)
        assert d.isoformat()==asof
        official=sorted(official_completed_sessions(asof))
        # Enumerate the next week too: asof Thursday is not completed Friday week.
        extended=sorted(official_completed_sessions((d+timedelta(days=10)).isoformat()))
        week_last={}
        for raw in extended:
            v=date.fromisoformat(raw)
            iso=v.isocalendar()
            week_last[(iso.year,iso.week)]=raw
        completed=sorted(day for day in week_last.values() if day<=asof)
        assert len(official)>=261 and len(completed)>=52
        assert official[-1]==asof,"ASOF_NOT_COMPLETED_EXCHANGE_SESSION"
        return official[-260:],completed[-52:]
    except Exception as e:
        raise ValueError("OFFICIAL_CALENDAR_UNAVAILABLE_OR_NOT_COMPLETED") from e

def build(price,master,price_sha):
    asof=price.get("asof_et")
    assert isinstance(price_sha,str) and len(price_sha)==40,"PRICE_BLOB_SHA_INVALID"
    assert isinstance(asof,str),"PRICE_ASOF_INVALID"
    assert master.get("asof_et")==asof,"MASTER_PRICE_ASOF_DRIFT"
    assert all(x.get("execution")=="NONE" and x.get("real_money")=="NO-GO" for x in (price,master))
    symbols=price.get("pass_symbols")
    assert isinstance(symbols,list) and symbols==sorted(set(symbols)) and symbols,"PRICE_PASS_SYMBOL_SET_INVALID"
    assert len(symbols)==price.get("pass_count"),"PRICE_PASS_COUNT_DRIFT"
    assert sha256_lines(symbols)==price.get("pass_hash"),"PRICE_PASS_HASH_DRIFT"
    # UNKNOWN/BLOCKED outside the independently established PASS set may
    # NEVER starve history preparation for the other known PASS symbols.
    # This is a SHADOW request only; global canonical completion remains blocked.
    unknown=price.get("unknown_symbols",[])
    blocked=price.get("blocked_symbols",[])
    assert isinstance(unknown,list) and unknown==sorted(set(unknown)),"PRICE_UNKNOWN_SET_INVALID"
    assert isinstance(blocked,list) and blocked==sorted(set(blocked)),"PRICE_BLOCKED_SET_INVALID"
    assert type(price.get("unknown_count")) is int and price["unknown_count"]==len(unknown),"PRICE_UNKNOWN_COUNT_INVALID"
    assert type(price.get("blocked_count")) is int and price["blocked_count"]==len(blocked),"PRICE_BLOCKED_COUNT_INVALID"
    pass_set=set(symbols)
    unknown_set=set(unknown)
    blocked_set=set(blocked)
    assert not(pass_set & unknown_set or pass_set & blocked_set or unknown_set & blocked_set),"PRICE_PARTITION_OVERLAP"
    master_set=set(master.get("pass_symbols",[]))
    assert pass_set|unknown_set|blocked_set <= master_set,"PRICE_OUTSIDE_MASTER"
    results=price.get("results")
    if results is not None:
        assert isinstance(results,dict) and set(results)==master_set,"PRICE_RESULT_PARTITION_DRIFT"
        for symbol in unknown:
            assert isinstance(results[symbol],dict) and results[symbol].get("status")!="PASS_PRICE_DV30","PRICE_UNKNOWN_RESULT_FALSE_PASS"
        for symbol in blocked:
            assert isinstance(results[symbol],dict) and results[symbol].get("status")!="PASS_PRICE_DV30","PRICE_BLOCKED_RESULT_FALSE_PASS"
    assert master.get("asof_et")==price.get("asof_et"),"SAME_ASOF_REQUIRED"
    daily,weekly=expected_dates(asof)
    assert len(daily)==260 and len(weekly)==52 and daily[-1]==asof
    assert len(set(daily))==260 and len(set(weekly))==52
    # An official calendar is only a target-date schedule; no real bar exists
    # until an authorized provider has supplied date-scoped evidence.
    return {
        "schema":SCHEMA,
        "status":"RESEARCH_HISTORY_REQUEST_READY_NO_MARKET_HISTORY_MEASURED",
        "asof_et":asof,"policy":"C4.17","control":"C4.27",
        "source_price_path":PRICE,"source_price_blob_sha":price_sha,
        "source_price_pass_count":len(symbols),
        "source_price_pass_hash":price["pass_hash"],
        "source_price_unknown_count":len(unknown),
        "source_price_unknown_omitted_from_scope":True,
        "source_price_blocked_count":len(blocked),
        "source_price_blocked_omitted_from_scope":True,
        "global_price_partition_complete":len(unknown)==0 and len(blocked)==0,
        "symbol_scope":symbols,
        "required_daily_official_sessions":daily,
        "required_completed_week_closes":weekly,
        "required_daily_count":260,"required_completed_week_count":52,
        "source_bar_count_measured":0,
        "source_entitlement_proven":False,
        "canonical_history_pass_created":0,
        "current_history_authority_proven":False,
        "r92_eligible":False,"can_register_R92":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
        "raw_vendor_ohlcv_in_report":False
    }

def selftest():
    asof="2026-10-08"
    m={"asof_et":asof,"pass_symbols":["AAA","BBB"],"execution":"NONE","real_money":"NO-GO"}
    p={"asof_et":asof,"pass_symbols":["AAA","BBB"],"pass_count":2,
       "pass_hash":sha256_lines(["AAA","BBB"]),
       "unknown_count":0,"unknown_symbols":[],"blocked_count":0,"blocked_symbols":[],
       "execution":"NONE","real_money":"NO-GO"}
    out=build(p,m,"a"*40)
    assert out["status"]=="RESEARCH_HISTORY_REQUEST_READY_NO_MARKET_HISTORY_MEASURED"
    assert out["required_daily_count"]==260 and len(out["required_daily_official_sessions"])==260
    assert out["required_completed_week_count"]==52 and len(out["required_completed_week_closes"])==52
    assert out["can_register_R92"] is False and out["source_entitlement_proven"] is False
    # A single independent UNKNOWN must not suppress known-PASS SHADOW history.
    m_partial=copy.deepcopy(m)
    p_partial=copy.deepcopy(p)
    m_partial["pass_symbols"].append("CCC")
    p_partial["unknown_symbols"]=["CCC"]
    p_partial["unknown_count"]=1
    partial=build(p_partial,m_partial,"b"*40)
    assert partial["symbol_scope"]==["AAA","BBB"]
    assert partial["source_price_unknown_count"]==1
    assert partial["global_price_partition_complete"] is False
    assert partial["canonical_history_pass_created"]==0 and partial["can_register_R92"] is False
    assert partial["current_history_authority_proven"] is False
    cases=[
       ("ASOF_DRIFT",lambda a,b:b.update(asof_et="2026-10-07")),
       ("PRICE_HASH_DRIFT",lambda a,b:a.update(pass_hash="0"*64)),
       ("BAD_COUNT",lambda a,b:a.update(pass_count=3)),
       ("DUPLICATE",lambda a,b:a.update(pass_symbols=["AAA","AAA"])),
       ("OUTSIDE_MASTER",lambda a,b:a.update(pass_symbols=["ZZZ"])),
       ("UNKNOWN_COUNT_MISMATCH",lambda a,b:a.update(unknown_count=1)),
       ("UNKNOWN_COLLISION",lambda a,b:a.update(unknown_symbols=["AAA"],unknown_count=1)),
       ("BLOCKED_COLLISION",lambda a,b:a.update(blocked_symbols=["BBB"],blocked_count=1)),
       ("UNKNOWN_BLOCKED_OVERLAP",lambda a,b:a.update(unknown_symbols=["CCC"],unknown_count=1,blocked_symbols=["CCC"],blocked_count=1)),
       ("FOREIGN_UNKNOWN",lambda a,b:a.update(unknown_symbols=["ZZZ"],unknown_count=1)),
       ("EXECUTION",lambda a,b:a.update(execution="REAL")),
       ("NONSESSION",lambda a,b:(a.update(asof_et="2026-10-10"),b.update(asof_et="2026-10-10")))
    ]
    for name,mutator in cases:
        a,b=copy.deepcopy(p),copy.deepcopy(m)
        mutator(a,b)
        try:build(a,b,"a"*40)
        except (AssertionError,ValueError):continue
        raise AssertionError("INVALID_CURRENT_HISTORY_REQUEST_ACCEPTED:"+name)
    print("XRAY_CURRENT_HISTORY_REQUEST_SELFTEST=PASS_TWO_POSITIVES_TWELVE_FAIL_CLOSED")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:selftest();return
    price=json.loads((REPO/PRICE).read_text(encoding="utf-8"))
    master=json.loads((REPO/MASTER).read_text(encoding="utf-8"))
    doc=build(price,master,git_blob(PRICE))
    if args.out:args.out.write_text(json.dumps(doc,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("XRAY_CURRENT_HISTORY_REQUEST_STATUS="+doc["status"])
    print("XRAY_CURRENT_HISTORY_REQUEST_ASOF="+doc["asof_et"])
    print("XRAY_CURRENT_HISTORY_REQUEST_SYMBOLS="+str(doc["source_price_pass_count"]))
    print("XRAY_CURRENT_HISTORY_REQUEST_NO_VENDOR_BARS_OR_PRIMARY=PASS")

if __name__=="__main__":main()
