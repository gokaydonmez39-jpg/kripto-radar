#!/usr/bin/env python3
"""Independent historical SIP remeasurement of exhausted Sina provider exceptions.

ONLY research source-availability counts. This may reveal that AkShare/Sina
raised an exception while a separately authenticated SIP daily source has the
official 260 sessions and 52 completed week closes. It NEVER repairs canonical
Sina state, creates HISTORY/PRICE/MC PASS, registers R92, executes orders, or
certifies data license, venue/exchange coverage, splits, PIT issuer identity.
Vendor OHLCV remains ephemeral; only counts and exact Git SHAs are written.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from alpaca_free_sip_shadow_guard import blob_sha, request_batch, sufficient_delay
from alpaca_full_scope_260_shadow import classify
from current_history_source_request import expected_dates
from sina_state_hash_guard import verify as verify_state_hash
from source_epoch_freshness_guard import last_complete_session

ROOT=Path(__file__).resolve().parent
SINA=ROOT/"sina_state.json"
MASTER=ROOT/"canonical_current_master_manifest.json"
SCHEMA="XRAY_EXHAUSTED_SINA_INDEPENDENT_ALPACA_SIP_260_SHADOW_V1"
BATCH=9
MAX_ELIGIBLE=32
PAGER_MAX_PAGES_PER_BATCH=24
TRANSIENT=("SyntaxError:","IndexError:","JSONDecodeError:",
           "TimeoutError:","ConnectionError:","HTTPError:")
OBSERVED="SHADOW_260_DAILY_52_WEEK_OBSERVED"
ALLOWED={
    OBSERVED,"NO_BAR","MISSING_EXACT_COMPLETED_SESSIONS",
    "MISSING_52_COMPLETED_WEEK_CLOSES","INVALID_OHLCV_OR_ZERO_VOLUME",
    "MALFORMED_BAR","BAD_PROVIDER_ROWS","NONFINITE_OHLCV",
    "DUPLICATE_SESSION","FUTURE_LOOKAHEAD","NON_OFFICIAL_SESSION",
    "TIMESTAMP_OR_OHLCV_PARSE_ERROR","TRANSPORT_UNVERIFIED",
}

def need(ok,code):
    if not ok:
        raise ValueError("XRAY_EXHAUSTED_SINA_SIP_"+code)

def cohort(state,master,now):
    """Fail closed on latest completed epoch, immutable full queue and source."""
    need(isinstance(state,dict) and isinstance(master,dict),"NOT_OBJECTS")
    need(now.tzinfo is not None,"NAIVE_NOW")
    asof=state.get("asof_et")
    need(isinstance(asof,str) and asof==last_complete_session(now)
         and master.get("asof_et")==asof,"ASOF_NOT_EXACT_LATEST")
    need(all(doc.get("execution")=="NONE" and doc.get("real_money")=="NO-GO"
                 and doc.get("unknown_never_pass") is True
                 for doc in (state,master)),"EXECUTION_POLICY")
    need(state.get("schema")=="XRAY_NASDAQ_SCREENER_SINA_V2"
         and state.get("status")=="HISTORY_PARTIAL","HISTORY_STATE_NOT_PARTIAL")
    queue=state.get("queue")
    rows=state.get("results")
    need(type(queue) is list and type(rows) is dict
         and len(queue)==len(set(queue)) and set(queue)==set(rows)
         and state.get("cursor")==len(queue)
         and state.get("queue_total")==len(queue)
         and state.get("queue_hash")==hashlib.sha256(
             "\n".join(queue).encode()).hexdigest(),
         "ROOT_QUEUE_SHA_OR_PARTITION")
    actual=collections.Counter(row.get("status") if isinstance(row,dict)
                               else "BAD_ROW" for row in rows.values())
    need(state.get("counts")==dict(actual)
         and state.get("unknown_count")==sum(
             n for k,n in actual.items() if k.startswith("UNKNOWN")),
         "SINA_STATUS_COUNTS_DRIFT")
    permitted=master.get("pass_symbols")
    need(type(permitted) is list and len(permitted)==len(set(permitted))
         and master.get("pass_count")==len(permitted)
         and set(queue).issubset(set(permitted)),"MASTER_IDENTITY_SCOPE")
    selected=sorted(s for s,v in rows.items()
                    if v.get("status")=="UNKNOWN_RETRY_EXHAUSTED"
                    and type(v.get("attempts")) is int
                    and v["attempts"]>=4
                    and type(v.get("transport_rescue_round",0)) is int
                    and v.get("transport_rescue_round",0)>=1
                    and type(v.get("info")) is str
                    and v["info"].startswith(TRANSIENT))
    need(len(selected)<=MAX_ELIGIBLE,"UNBOUNDED_TRANSIENT_COHORT")
    # A nonempty selection must correspond to every exhausted transient row:
    # do not silently suppress eligibility/integrity errors.
    all_exhausted=[s for s,v in rows.items()
                   if v.get("status")=="UNKNOWN_RETRY_EXHAUSTED"]
    need(len(all_exhausted)==len(selected),"EXHAUSTED_REASON_UNCLASSIFIED")
    return asof,selected

def make(asof,selected,days,weeks,sina_sha,master_sha,counts,attempted,
         status):
    need(len(days)==260 and len(weeks)==52 and days[-1]==asof,
         "OFFICIAL_CALENDAR")
    need(set(counts)<=ALLOWED and all(type(v) is int and v>=0
                                     for v in counts.values()),
         "INVALID_DIAGNOSTIC_COUNT")
    need(sum(counts.values())==len(selected),"EXACT_STATUS_PARTITION")
    need(type(attempted) is int and 0<=attempted<=(len(selected)+BATCH-1)//BATCH,
         "BATCH_BUDGET_EXCEEDED")
    return {
        "schema":SCHEMA,"status":status,"asof_et":asof,
        "source_sina_state_git_blob_sha":sina_sha,
        "source_master_git_blob_sha":master_sha,
        "selected_exhausted_transient_count":len(selected),
        "selected_exhausted_symbols_sha256":hashlib.sha256(
            "\n".join(selected).encode()).hexdigest(),
        "expected_daily_sessions":260,"expected_completed_week_closes":52,
        "batch_size":BATCH,"batch_requests_attempted":attempted,
        "max_pagination_pages_per_batch":PAGER_MAX_PAGES_PER_BATCH,
        "worst_case_page_requests_upper_bound":attempted*PAGER_MAX_PAGES_PER_BATCH,
        "counts":dict(sorted(counts.items())),
        "independent_sip_observed_count":counts.get(OBSERVED,0),
        "source_vendor_rights_independently_verified":False,
        "source_official_auction_and_corrections_verified":False,
        "share_class_corporate_actions_pit_verified":False,
        "canonical_history_pass_created":0,
        "canonical_price_pass_created":0,
        "canonical_mc_pass_created":0,
        "r92_registered":False,"provider_raw_ohlcv_persisted":False,
        "provider_symbol_rows_persisted":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
    }

def measure(asof,selected,days,weeks,sina_sha,master_sha,credentials,
            batch_fetch,now):
    need(now.tzinfo is not None and sufficient_delay(asof,now),
         "SIP_HOLDBACK_NOT_MET")
    need(type(selected) is list and selected==sorted(set(selected))
         and len(selected)<=MAX_ELIGIBLE,"INVALID_SELECTED_COHORT")
    need(len(days)==260 and len(weeks)==52 and days[-1]==asof,
         "OFFICIAL_260_52")
    if not selected:
        return make(asof,selected,days,weeks,sina_sha,master_sha,{},0,
                    "BLOCKED_NO_EXHAUSTED_TRANSIENT_COHORT")
    if not all(credentials):
        return make(asof,selected,days,weeks,sina_sha,master_sha,
                    {"TRANSPORT_UNVERIFIED":len(selected)},0,
                    "BLOCKED_PRIVATE_SIP_KEYS_NOT_CONFIGURED")
    start=days[0]+"T00:00:00Z"
    end=(dt.date.fromisoformat(asof)+dt.timedelta(days=1)).isoformat()+"T00:00:00Z"
    categories=collections.Counter()
    batches=0
    for idx in range(0,len(selected),BATCH):
        block=selected[idx:idx+BATCH]
        batches+=1
        try:
            rows=batch_fetch(block,start,end,*credentials,asof)
            need(type(rows) is dict and set(rows)<=set(block),
                 "PROVIDER_BATCH_SCOPE_UNVERIFIED")
            for symbol in block:
                status,_=classify(rows.get(symbol,[]),days,weeks,asof)
                need(status in ALLOWED,"UNRECOGNIZED_PROVIDER_CLASS")
                categories[status]+=1
        except (RuntimeError,ValueError,TypeError,KeyError,OSError):
            # Do not log vendor exception strings, or reinterpret missing
            # source as 260-session HISTORY PASS.
            categories["TRANSPORT_UNVERIFIED"]+=len(block)
            categories["TRANSPORT_UNVERIFIED"]+=len(selected)-idx-len(block)
            break
    status=("SHADOW_ALL_260_OBSERVED_NOT_CANONICAL"
            if categories.get(OBSERVED,0)==len(selected) else
            "SHADOW_PARTIAL_OR_BLOCKED_SOURCE_NOT_CANONICAL")
    return make(asof,selected,days,weeks,sina_sha,master_sha,
                dict(categories),batches,status)

def selftest():
    from alpaca_free_sip_shadow_guard import EST
    asof="2026-10-14"
    days,weeks=expected_dates(asof)
    now=dt.datetime(2026,10,15,19,tzinfo=dt.timezone.utc)
    names=["AAA","BBB","CCC"]
    rows={
      "AAA":{"status":"UNKNOWN_RETRY_EXHAUSTED","attempts":5,
             "transport_rescue_round":1,"info":"SyntaxError:broken"},
      "BBB":{"status":"UNKNOWN_RETRY_EXHAUSTED","attempts":5,
             "transport_rescue_round":1,"info":"IndexError:broken"},
      "CCC":{"status":"UNKNOWN_STATIC","info":{"reason":"ASOF_MISSING_REQUIRES_RESOLUTION"}},
    }
    state={"schema":"XRAY_NASDAQ_SCREENER_SINA_V2",
           "status":"HISTORY_PARTIAL","asof_et":asof,
           "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
           "queue":names,"queue_total":3,"cursor":3,
           "queue_hash":hashlib.sha256("\n".join(names).encode()).hexdigest(),
           "results":rows,"counts":{"UNKNOWN_RETRY_EXHAUSTED":2,
                                    "UNKNOWN_STATIC":1},"unknown_count":3}
    master={"asof_et":asof,"pass_symbols":names,"pass_count":3,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    a,selected=cohort(state,master,now)
    need(a==asof and selected==["AAA","BBB"],"ROOT_EXHAUSTED_POSITIVE")
    def bar(day):
        d=dt.datetime.combine(dt.date.fromisoformat(day),dt.time(),EST)
        return {"t":d.isoformat(),"o":10,"h":11,"l":9,"c":10,"v":1000}
    good=[bar(d) for d in days]
    calls=[]
    def fetch(block,start,end,key,secret,epoch):
        calls.append((block,epoch))
        return {"AAA":good,"BBB":good[:-1]}
    result=measure(a,selected,days,weeks,"a"*40,"b"*40,
                   ("SYNTHETIC","SYNTHETIC"),fetch,now)
    need(calls==[(["AAA","BBB"],asof)]
         and result["counts"]=={OBSERVED:1,
                               "MISSING_EXACT_COMPLETED_SESSIONS":1}
         and result["canonical_history_pass_created"]==0
         and result["r92_registered"] is False,
         "TWO_PROVIDER_OUTCOMES_REMAIN_SHADOW")
    stopped=measure(a,selected,days,weeks,"a"*40,"b"*40,("", ""),fetch,now)
    need(stopped["batch_requests_attempted"]==0 and
         stopped["counts"]=={"TRANSPORT_UNVERIFIED":2},
         "MISSING_PRIVATE_KEYS_MUST_NOT_FETCH")
    def denied(*args):
        raise RuntimeError("ALPACA_HTTP_403")
    blocked=measure(a,selected,days,weeks,"a"*40,"b"*40,
                    ("KEY","SECRET"),denied,now)
    need(blocked["counts"]=={"TRANSPORT_UNVERIFIED":2}
         and blocked["independent_sip_observed_count"]==0,
         "AUTH_CANNOT_MINT_HISTORY")
    import copy
    for label,edit in [
        ("QUEUE_HASH",lambda s,m:s.update(queue_hash="0"*64)),
        ("ASOF",lambda s,m:m.update(asof_et="2026-10-13")),
        ("COUNT",lambda s,m:s.update(unknown_count=0)),
        ("EXECUTION",lambda s,m:s.update(execution="LIVE")),
        ("RETRY_ROUND",lambda s,m:s["results"]["AAA"].update(transport_rescue_round=0)),
    ]:
        s,m=copy.deepcopy(state),copy.deepcopy(master)
        edit(s,m)
        try:cohort(s,m,now)
        except ValueError:pass
        else:raise AssertionError("BAD_EXHAUSTED_SCOPE_ACCEPTED_"+label)
    print("XRAY_EXHAUSTED_SINA_SIP_SELFTEST=PASS_260_52_SHADOW_5_NEGATIVES_NO_VENDOR_NO_CANONICAL")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.selftest:return selftest()
    need(args.out is not None and not args.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "PRIVATE_OUTPUT_ONLY")
    state=json.loads(SINA.read_text())
    master=json.loads(MASTER.read_text())
    now=dt.datetime.now(dt.timezone.utc)
    need(verify_state_hash(state)=="PASS_DETERMINISTIC_BLOB_INTERNAL",
         "ROOT_SINA_STATE_HASH_INVALID")
    asof,selected=cohort(state,master,now)
    days,weeks=expected_dates(asof)
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or "").strip()
    def query(block,start,end,k,secret,epoch):
        return request_batch(block,start,end,k,secret,adjustment="raw",asof=epoch)
    out=measure(asof,selected,days,weeks,blob_sha(SINA),blob_sha(MASTER),
                (key,secret),query,now)
    args.out.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("XRAY_EXHAUSTED_SINA_INDEPENDENT_SIP_STATUS="+out["status"])
    print("XRAY_EXHAUSTED_SINA_INDEPENDENT_SIP_COUNTS="+json.dumps(out["counts"],sort_keys=True))
    print("XRAY_EXHAUSTED_SINA_NO_CANONICAL_MC_R92=PASS")

if __name__=="__main__":
    main()
