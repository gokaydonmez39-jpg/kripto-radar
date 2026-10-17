#!/usr/bin/env python3
"""C4.17/C4.27 no-vendor-call recovery acceptance audit.

Checks existing canonical SHA bindings and exact official 30-session dates.
This audit CANNOT grant vendor rights, reconcile auction trade conditions,
create PRIMARY MC, promote MASTER UNKNOWN, produce R92, or mutate artifacts.
A healthy audit execution is not a healthy trading/research data chain.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

import pandas_market_calendars as mcal

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
SCHEMA = "XRAY_ZERO_LIMIT_CORE_REBIND_READINESS_V1"
POLICY_HASH = "68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
TARGET_10 = ("ALIS", "BSAA", "FACT", "FVN", "HCAC", "IPXG", "MACI", "MCGA", "MMTX", "WTG")
FILES = {
    "MASTER": "canonical_current_master_manifest.json",
    "PRICE_DV30": "canonical_current_price_dv30.json",
    "HISTORY": "canonical_current_history.json",
    "TERMINAL": "canonical_current_terminal.json",
    "MANUAL_MODE": "manual_decision_policy_v1.json",
    "COMPILED": "chatgpt_compiled_policy_v3.json",
}

def require(condition, code):
    if not condition:
        raise ValueError("ZERO_LIMIT_" + code)

def digest(value):
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def git_blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def official30(asof,now_utc=None):
    require(type(asof) is str,"ASOF_FORMAT")
    day=dt.date.fromisoformat(asof)
    require(day.isoformat()==asof,"ASOF_NONCANONICAL")
    now=dt.datetime.now(dt.timezone.utc) if now_utc is None else now_utc
    require(type(now) is dt.datetime and now.tzinfo is not None and
        now.utcoffset()==dt.timedelta(0),"AWARE_UTC_CLOCK_REQUIRED")
    cal=mcal.get_calendar("NASDAQ")
    schedule=cal.schedule(start_date=day,end_date=day)
    require(len(schedule)==1,"ASOF_NOT_TRADING_SESSION")
    close=schedule.iloc[0]["market_close"].to_pydatetime()
    require(close.tzinfo is not None and
        close+dt.timedelta(minutes=30)<=now,"ASOF_NOT_SETTLED")
    days=cal.valid_days(start_date=day-dt.timedelta(days=80),end_date=day)
    found=[str(x.date()) for x in days]
    require(len(found)>=30 and found[-1]==asof,"OFFICIAL30_INCOMPLETE")
    return found[-30:]

def analyze(inputs,blobs,expected=None):
    require(set(inputs)==set(FILES) and set(blobs)==set(FILES),"INPUT_SCOPE")
    require(all(type(row) is dict for row in inputs.values()),"INPUT_TYPES")
    require(all(type(blobs[k]) is str and len(blobs[k])==40 for k in FILES),"BLOB_SHA")
    m,p,h,t,manual,compiled=(inputs[k] for k in
       ("MASTER","PRICE_DV30","HISTORY","TERMINAL","MANUAL_MODE","COMPILED"))
    asof=m.get("asof_et")
    require(asof==p.get("asof_et"),"MASTER_PRICE_ASOF_DRIFT")
    require(all(x.get("execution")=="NONE" and x.get("real_money")=="NO-GO"
        and x.get("unknown_never_pass") is True for x in (m,p,h,t)),
        "CANONICAL_SAFETY")
    require(manual.get("execution")=="NONE" and manual.get("real_money")=="NO-GO"
        and manual.get("parent_policy_sha256")==POLICY_HASH,
        "MANUAL_POLICY_BINDING")
    require(compiled.get("policy_hash")==POLICY_HASH,"COMPILED_POLICY_BINDING")
    official=official30(asof) if expected is None else expected
    require(type(official) is list and len(official)==30 and
        all(type(s) is str for s in official) and
        official==sorted(set(official)) and official[-1]==asof,
        "OFFICIAL30_SCOPE")
    declared=p.get("expected30")
    exact=declared==official
    require(exact,"DECLARED_OFFICIAL30_DRIFT")
    unknown_m=m.get("unknown_symbols")
    unknown_p=p.get("unknown_symbols")
    require(type(unknown_m) is list and type(unknown_p) is list,
            "UNKNOWN_LIST_MISSING")
    require(len(set(unknown_m))==len(unknown_m) and
            len(set(unknown_p))==len(unknown_p),"UNKNOWN_DUPLICATE")
    require(m.get("unknown_count")==len(unknown_m) and
            p.get("unknown_count")==len(unknown_p),"UNKNOWN_COUNT_MISMATCH")
    require(set(unknown_m).isdisjoint(set(m.get("pass_symbols") or [])),
            "MASTER_UNKNOWN_PASS_OVERLAP")
    require(set(unknown_p).isdisjoint(set(p.get("pass_symbols") or [])),
            "PRICE_UNKNOWN_PASS_OVERLAP")
    identity_10=sorted(set(TARGET_10)&set(unknown_m))
    conditions={
        "exact_30_official_dates":exact,
        "all_master_10_resolved":not identity_10,
        "all_price_unknown_resolved":len(unknown_p)==0,
        "rth_auction_trade_condition_lineage":False,
        "licensed_unattended_historical_sip":False,
        "sec_shareclass_and_corporate_actions_pit":False,
        "primary_mc_authorized":False,
        "same_asof_history_terminal":h.get("asof_et")==t.get("asof_et")==asof,
        "manual_research_delivery_enabled":False,
        "strict_g9_pass":False,
        "same_run_account_pass":False,
    }
    return {
       "schema":SCHEMA,"asof_et":asof,"policy":"C4.17","policy_hash":POLICY_HASH,
       "control":"C4.27","execution":"NONE","real_money":"NO-GO",
       "unknown_never_pass":True,"api_calls":0,"external_http":False,
       "canonical_mutated":False,"source_blob_sha":dict(sorted(blobs.items())),
       "master":{"unknown_count":len(unknown_m),
                 "target10_still_unknown_count":len(identity_10),
                 "target10_still_unknown":identity_10,
                 "target10_sha256":digest(sorted(TARGET_10))},
       "price_dv30":{"unknown_count":len(unknown_p),
                     "unknown_symbol_list_sha256":digest(sorted(unknown_p)),
                     "expected30_sha256":digest(official),
                     "declared30_matches_official":exact,
                     "rth_volume_verified":False},
       "history_terminal":{"history_asof":h.get("asof_et"),
                           "terminal_asof":t.get("asof_et"),
                           "same_asof":conditions["same_asof_history_terminal"]},
       "conditions":conditions,
       "primary_mc_count_created":0,"r92_count_created":0,
       "research_status":"BLOCKED_UNVERIFIED_PRICE_MC_AND_CURRENT_CHAIN",
       "true_full_go":False,
    }

def read_current():
    inputs={}
    blobs={}
    for key,name in FILES.items():
        data=(ROOT/name).read_bytes()
        inputs[key]=json.loads(data)
        blobs[key]=git_blob(data)
    return analyze(inputs,blobs)

def selftest():
    asof="2026-10-12"
    official=official30(asof)
    # A future/unsettled session or calendar holiday must never enter DV30.
    edge=dt.datetime(2026,10,12,20,29,tzinfo=dt.timezone.utc)
    try:official30(asof,edge)
    except ValueError:pass
    else:raise AssertionError("UNSETTLED_RTH_SESSION_ACCEPTED")
    require(official30(asof,dt.datetime(2026,10,12,20,30,
           tzinfo=dt.timezone.utc))==official,"SETTLED_RTH_SESSION_REJECTED")
    try:official30("2026-07-03",dt.datetime(2026,7,4,tzinfo=dt.timezone.utc))
    except ValueError:pass
    else:raise AssertionError("NASDAQ_HOLIDAY_ACCEPTED")
    m={"asof_et":asof,"execution":"NONE","real_money":"NO-GO",
       "unknown_never_pass":True,"unknown_symbols":["ALIS"],"unknown_count":1,
       "pass_symbols":["AAPL"]}
    p={"asof_et":asof,"execution":"NONE","real_money":"NO-GO",
       "unknown_never_pass":True,"unknown_symbols":["NVDA"],"unknown_count":1,
       "pass_symbols":["AAPL"],"expected30":official}
    h={"asof_et":"2026-10-07","execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    t=dict(h)
    manual={"execution":"NONE","real_money":"NO-GO","parent_policy_sha256":POLICY_HASH}
    compiled={"policy_hash":POLICY_HASH}
    good=dict(zip(FILES,(m,p,h,t,manual,compiled)))
    blobs={key:"a"*40 for key in FILES}
    result=analyze(good,blobs,official)
    require(result["master"]["target10_still_unknown_count"]==1
            and result["price_dv30"]["unknown_count"]==1
            and result["history_terminal"]["same_asof"] is False
            and result["primary_mc_count_created"]==0
            and result["r92_count_created"]==0
            and result["api_calls"]==0,"POSITIVE_BLOCKED_DIAGNOSTIC")
    variants=[
       lambda x:x["MASTER"].update(asof_et="2026-10-09"),
       lambda x:x["PRICE_DV30"].update(expected30=official[1:]),
       lambda x:x["PRICE_DV30"].update(expected30=official[::-1]),
       lambda x:x["PRICE_DV30"].update(unknown_count=0),
       lambda x:x["PRICE_DV30"].update(unknown_symbols=["NVDA","NVDA"],unknown_count=2),
       lambda x:x["MASTER"].update(unknown_count=0),
       lambda x:x["MASTER"].update(pass_symbols=["AAPL","ALIS"]),
       lambda x:x["PRICE_DV30"].update(pass_symbols=["AAPL","NVDA"]),
       lambda x:x["MANUAL_MODE"].update(parent_policy_sha256="0"*64),
       lambda x:x["COMPILED"].update(policy_hash="0"*64),
       lambda x:x["TERMINAL"].update(real_money="GO"),
       lambda x:x["HISTORY"].update(unknown_never_pass=False),
    ]
    for mut in variants:
        altered=copy.deepcopy(good)
        mut(altered)
        try:analyze(altered,blobs,official)
        except (ValueError,TypeError,KeyError):pass
        else:raise AssertionError("DANGEROUS_CANONICAL_INPUT_ACCEPTED")
    require(len(variants)==12,"NEGATIVE_FIXTURE_COUNT")
    print("XRAY_ZERO_LIMIT_CORE_REBIND_SELFTEST=PASS_12_NEGATIVES_3_CALENDAR_GATES_NO_VENDOR_NO_PRIMARY_NO_R92")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--check-current",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:
        selftest()
        return
    require(args.check_current,"EXPLICIT_CHECK_REQUIRED")
    report=read_current()
    if args.out:
        require(not args.out.resolve().is_relative_to(REPO.resolve()),
                "PUBLIC_REPO_OUTPUT_FORBIDDEN")
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n",
                            encoding="utf-8")
        reread = json.loads(args.out.read_text(encoding="utf-8"))
        require(reread == report, "JSON_ARTIFACT_ROUNDTRIP_FAILED")
    print("XRAY_ZERO_LIMIT_CORE_REBIND="+report["research_status"])
    print("XRAY_ZERO_LIMIT_MASTER_UNKNOWN="+str(report["master"]["unknown_count"]))
    print("XRAY_ZERO_LIMIT_PRICE_UNKNOWN="+str(report["price_dv30"]["unknown_count"]))
    print("XRAY_ZERO_LIMIT_SOURCE_HTTP=0_PRIMARY_MC=0_R92=0")

if __name__=="__main__":
    main()
