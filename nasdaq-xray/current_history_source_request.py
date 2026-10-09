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
    assert price.get("unknown_count")==0,"PRICE_UNKNOWN_NONZERO"
    assert set(symbols)<=set(master.get("pass_symbols",[])),"PRICE_OUTSIDE_MASTER"
    assert type(price.get("blocked_count")) is int and price.get("blocked_count")>=0
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
       "unknown_count":0,"blocked_count":0,"execution":"NONE","real_money":"NO-GO"}
    out=build(p,m,"a"*40)
    assert out["status"]=="RESEARCH_HISTORY_REQUEST_READY_NO_MARKET_HISTORY_MEASURED"
    assert out["required_daily_count"]==260 and len(out["required_daily_official_sessions"])==260
    assert out["required_completed_week_count"]==52 and len(out["required_completed_week_closes"])==52
    assert out["can_register_R92"] is False and out["source_entitlement_proven"] is False
    cases=[
       ("ASOF_DRIFT",lambda a,b:b.update(asof_et="2026-10-07")),
       ("PRICE_HASH_DRIFT",lambda a,b:a.update(pass_hash="0"*64)),
       ("BAD_COUNT",lambda a,b:a.update(pass_count=3)),
       ("DUPLICATE",lambda a,b:a.update(pass_symbols=["AAA","AAA"])),
       ("OUTSIDE_MASTER",lambda a,b:a.update(pass_symbols=["ZZZ"])),
       ("UNKNOWN",lambda a,b:a.update(unknown_count=1)),
       ("EXECUTION",lambda a,b:a.update(execution="REAL")),
       ("NONSESSION",lambda a,b:(a.update(asof_et="2026-10-10"),b.update(asof_et="2026-10-10")))
    ]
    for name,mutator in cases:
        a,b=copy.deepcopy(p),copy.deepcopy(m)
        mutator(a,b)
        try:build(a,b,"a"*40)
        except (AssertionError,ValueError):continue
        raise AssertionError("INVALID_CURRENT_HISTORY_REQUEST_ACCEPTED:"+name)
    print("XRAY_CURRENT_HISTORY_REQUEST_SELFTEST=PASS_ONE_POSITIVE_EIGHT_FAIL_CLOSED")

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
