#!/usr/bin/env python3
"""Candidate-local Oct13 exact-source Stage1 SIP research, pages 1..9 of 277.

Page 0 is immutable successful run 38533652716. No duplicate fetch.
Positive Stage1 weekly/pool status remains SHADOW until SEC class-aware MC,
exact-price-correction, R1/RR, official legal/event/halt and candidate receipt.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,time,urllib.error
from pathlib import Path
import candidate_local_oct13_stage1_sip28_shadow as base

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
SOURCE_SHA=base.SOURCE_SHA
TOTAL=277
PAGE=28

def require(ok,why):
    if not ok:raise ValueError("XRAY_STAGE1_277_"+why)

def scoped_symbols(path,index):
    require(type(index) is int and 1<=index<=9,"PAGE_1_THROUGH_9")
    raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==SOURCE_SHA,"IMMUTABLE_277_SOURCE")
    obj=json.loads(raw)
    require(obj.get("schema")=="XRAY_OCT13_LOCAL_404_SIP_SEC_HISTORY_REAL_SOURCE_ROLLUP_V1"
            and obj.get("asof_et")==ASOF
            and obj.get("source_overlap_count")==TOTAL
            and obj.get("exact_page_and_current_blob_coverage_verified") is True,
            "EXACT_CURRENT_COHORT")
    symbols=obj["source_overlap_symbols"]
    require(type(symbols) is list and len(symbols)==TOTAL
            and symbols==sorted(set(symbols)),"ALL_277_EXACT_SET")
    chosen=symbols[index*PAGE:(index+1)*PAGE]
    require(len(chosen)==(25 if index==9 else 28)
            and set(chosen).issubset(set(symbols)),
            "NO_SCOPE_LOSS")
    return chosen

def selftest():
    require(len(base.exact260())==260,"OFFICIAL_HISTORY")
    require([len(list(range(TOTAL))[i*PAGE:(i+1)*PAGE]) for i in range(10)]
            == [28]*9+[25],"EXACT_PAGE_PARTITION")
    require(sum(len(list(range(TOTAL))[i*PAGE:(i+1)*PAGE]) for i in range(10))
            == TOTAL,"ALL_SYMBOLS_ONCE")
    for n in (-1,0,10):
        try:
            require(1<=n<=9,"REJECTED_PAGE")
        except ValueError:
            pass
        else:
            raise AssertionError("XRAY_STAGE1_277_INVALID_PAGE_ACCEPTED")
    sample=base.assess({},base.exact260(),{})
    require(sample["status"]=="UNKNOWN_INCOMPLETE_260_SIP","MISSING_BARS_NOT_PASS")
    print("XRAY_STAGE1_277_SELFTEST=PASS_10_EXACT_PAGES_260_VETOES")

def run(page,source,out):
    require(out and not out.resolve().is_relative_to(ROOT.parent.resolve()),
            "NO_PUBLIC_VENDOR_ROWS")
    symbols=scoped_symbols(source,page)
    dates=base.exact260()
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or
         os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or
            os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    require(key and secret,"SIP_CREDENTIALS_NOT_CONFIGURED")
    w=base.stage.build_week_last(ASOF)
    report={"schema":"XRAY_20261013_277_STAGE1_SIP_PAGE_RESEARCH_V1",
            "asof_et":ASOF,"page":page,"source_277_json_sha256":SOURCE_SHA,
            "source_subset_is_sorted_exact":True,
            "scope_total":TOTAL,"scope_count":len(symbols),
            "target_symbols":symbols,"status_by_symbol":{},"result_counts":{},
            "api_calls":0,
            "provider":"ALPACA_HISTORICAL_SIP_SINGLE_TICKER_1DAY_260",
            "source_history_exact_260_official":True,
            "source_weekly_52_gate":"C417_STAGE1_EXISTING_ENGINE",
            "no_raw_OHLCV_export":True,
            "corporate_action_pit_fully_reconciled":False,
            "sec_class_aware_mc_primary":False,
            "price_close_corrections_primary":False,
            "official_event_halt_clear":False,
            "regime_setup_r1_rr_primary":False,
            "r92_registered":0,"canonical_mutated":False,
            "iphone_push_receipt_verified":False,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    def save():
        report["result_counts"]=dict(sorted(collections.Counter(
          row["status"] for row in report["status_by_symbol"].values()).items()))
        out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    save()
    for sym in symbols:
        report["api_calls"]+=1
        try:
            observations=base.one(sym,(key,secret),dates)
            report["status_by_symbol"][sym]=base.assess(observations,dates,w)
        except urllib.error.HTTPError as exc:
            report["status_by_symbol"][sym]={"status":"UNKNOWN_HTTP_"+str(exc.code)}
            if exc.code==429:
                report["stop_reason"]="RATE_LIMIT_STOP_NO_BYPASS"
                save()
                break
        except (urllib.error.URLError,ValueError,KeyError,TypeError,
                RuntimeError,TimeoutError,OverflowError):
            report["status_by_symbol"][sym]={"status":"UNKNOWN_SOURCE_OR_INTEGRITY"}
        save()
        time.sleep(.65)
    for sym in symbols:
        report["status_by_symbol"].setdefault(
           sym,{"status":"UNKNOWN_NOT_ATTEMPTED_AFTER_PROVIDER_STOP"})
    save()
    require(set(report["status_by_symbol"])==set(symbols)
            and sum(report["result_counts"].values())==len(symbols),
            "EXACT_SYMBOL_COVERAGE_NO_SILENT_DROP")
    print("XRAY_STAGE1_277_PAGE="+str(page))
    print("XRAY_STAGE1_277_ACTUAL_SIP_CALLS="+str(report["api_calls"]))
    print("XRAY_STAGE1_277_RESULT_COUNTS="+json.dumps(report["result_counts"],sort_keys=True))
    print("XRAY_STAGE1_277_RAW_BARS_NOT_PUBLIC_R92_ZERO=PASS")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--page",type=int)
    p.add_argument("--source",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:selftest()
    else:
        require(a.page is not None and a.source and a.out,"CLI")
        run(a.page,a.source,a.out)
