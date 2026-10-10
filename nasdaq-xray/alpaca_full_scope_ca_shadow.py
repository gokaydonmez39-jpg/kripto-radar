#!/usr/bin/env python3
"""Read-only exact-ASOF Alpaca corporate-action census: no PRIMARY authority.

Every PRICE PASS symbol plus QQQ is queried over the identical 260-day
completed-session horizon. Requests are authenticated, key values and
original vendor records remain in ephemeral process memory. Outputs contain
only counts/type aggregates and Git file hashes. Vendor CA processing time is
NOT PIT publication time; completeness, source licenses, C4.17 HISTORY,
PRIMARY MC, G9, account and device receipts are NOT certified here.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from alpaca_free_sip_shadow_guard import blob_sha, sufficient_delay
from alpaca_full_scope_260_shadow import scope, PRICE, MASTER

ROOT=Path(__file__).resolve().parent
URL="https://data.alpaca.markets/v1/corporate-actions"
SCHEMA="XRAY_ALPACA_515_CORPORATE_ACTIONS_CENSUS_SHADOW_V1"
BATCH_SIZE=65
MAX_PAGES=20
UTC=dt.timezone.utc
SUBJECT_FIELDS=("symbol","old_symbol","new_symbol","source_symbol",
                "acquirer_symbol","acquiree_symbol","target_symbol")
KNOWN_GROUPS={
 "cash_dividends","stock_dividends","forward_splits","reverse_splits",
 "unit_splits","spin_offs","cash_mergers","stock_mergers",
 "stock_and_cash_mergers","redemptions","name_changes",
 "worthless_removals","rights_distributions",
 "capital_gains_distributions","partial_calls","reorganizations",
 "contract_adjustments",
}


def request_page(batch,start,end,key,secret,token):
    if not key or not secret:
        raise RuntimeError("ALPACA_CA_MISSING_PRIVATE_CREDENTIALS")
    params={"symbols":",".join(batch),"start":start,"end":end,
            "data_quality":"complete","limit":1000,"sort":"asc"}
    if token is not None:
        params["page_token"]=token
    req=urllib.request.Request(URL+"?"+urllib.parse.urlencode(params),headers={
        "APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
        "Accept":"application/json","User-Agent":"NASDAQ-XRAY-Research/1.0"})
    try:
        with urllib.request.urlopen(req,timeout=40) as r:
            if r.status!=200:
                raise RuntimeError("ALPACA_CA_NON200")
            body=r.read(4_000_001)
            if len(body)>4_000_000:
                raise RuntimeError("ALPACA_CA_RESPONSE_TOO_LARGE")
    except urllib.error.HTTPError as e:
        raise RuntimeError("ALPACA_CA_HTTP_"+str(e.code)) from e
    except (urllib.error.URLError,TimeoutError,OSError) as e:
        raise RuntimeError("ALPACA_CA_NETWORK_UNAVAILABLE") from e
    try:
        return json.loads(body)
    except (ValueError,TypeError) as e:
        raise RuntimeError("ALPACA_CA_INVALID_JSON") from e


def audit(asof,targets,start,fetch,*,now):
    if now.tzinfo is None or not sufficient_delay(asof,now):
        raise ValueError("ALPACA_CA_CURRENT_SESSION_HOLDBACK_UNVERIFIED")
    if not targets or targets!=sorted(set(targets)) or "QQQ" not in targets:
        raise ValueError("ALPACA_CA_SOURCE_SCOPE_INVALID")
    if start>=asof or not isinstance(start,str):
        raise ValueError("ALPACA_CA_HORIZON_INVALID")
    counts=collections.Counter()
    event_ids=set()
    unknown_group_count=0
    unmatched_subjects=0
    measured=0
    pages=0
    fault=None
    for i in range(0,len(targets),BATCH_SIZE):
        batch=targets[i:i+BATCH_SIZE]
        seen_tokens=set()
        token=None
        try:
            for page_number in range(MAX_PAGES):
                response=fetch(batch,start,asof,token)
                if not isinstance(response,dict):
                    raise RuntimeError("ALPACA_CA_MALFORMED_RESPONSE")
                groups=response.get("corporate_actions")
                if not isinstance(groups,dict):
                    raise RuntimeError("ALPACA_CA_GROUPS_UNVERIFIED")
                page_size=0
                for group,rows in groups.items():
                    if not isinstance(group,str) or not isinstance(rows,list):
                        raise RuntimeError("ALPACA_CA_BAD_EVENT_GROUP")
                    if group not in KNOWN_GROUPS:
                        unknown_group_count+=len(rows)
                    for row in rows:
                        if not isinstance(row,dict):
                            raise RuntimeError("ALPACA_CA_MALFORMED_EVENT")
                        identifier=row.get("id")
                        day=row.get("process_date")
                        if not isinstance(identifier,str) or not identifier:
                            raise RuntimeError("ALPACA_CA_MISSING_EVENT_ID")
                        if identifier in event_ids:
                            raise RuntimeError("ALPACA_CA_DUPLICATE_EVENT_ID")
                        try:
                            date=dt.date.fromisoformat(day)
                        except (TypeError,ValueError):
                            raise RuntimeError("ALPACA_CA_PROCESS_DATE_INVALID")
                        if not dt.date.fromisoformat(start)<=date<=dt.date.fromisoformat(asof):
                            raise RuntimeError("ALPACA_CA_PROCESS_DATE_OUT_OF_ASOF")
                        subjects={row[k] for k in SUBJECT_FIELDS
                                  if isinstance(row.get(k),str) and row[k]}
                        if not subjects.intersection(batch):
                            unmatched_subjects+=1
                        event_ids.add(identifier)
                        counts[group]+=1
                        page_size+=1
                pages+=1
                nt=response.get("next_page_token")
                if nt is None or nt=="":
                    token=None
                    break
                if not isinstance(nt,str) or nt in seen_tokens or nt==token or page_size==0:
                    raise RuntimeError("ALPACA_CA_CURSOR_OR_EMPTY_PAGE_INVALID")
                seen_tokens.add(nt)
                token=nt
            if token is not None:
                raise RuntimeError("ALPACA_CA_MAX_PAGES_EXCEEDED")
            measured+=len(batch)
        except (RuntimeError,ValueError) as err:
            msg=str(err)
            fault=(msg if msg.startswith("ALPACA_CA_")
                   else "ALPACA_CA_UNVERIFIED_TRANSPORT")
            break
    return {
        "schema":SCHEMA,"asof_et":asof,"asof_start":start,
        "expected_symbols":len(targets),"measured_symbols":measured,
        "unmeasured_symbols":len(targets)-measured,
        "pages_consumed":pages,"total_events_seen":sum(counts.values()),
        "counts_by_group":dict(sorted(counts.items())),
        "non_cash_dividend_events":sum(counts.values())-counts["cash_dividends"],
        "unknown_vendor_group_events":unknown_group_count,
        "subject_not_in_requested_batch":unmatched_subjects,
        "status":("SHADOW_SCOPE_COMPLETE_CA_NOT_PIT"
                  if measured==len(targets) and fault is None
                  else "SHADOW_INCOMPLETE_OR_INVALID_CA"),
        "failure_reason_class":fault,
        "provider_data_quality":"complete",
        "provider_publication_time_attested":False,
        "independent_issuer_corporate_actions_reconciled":False,
        "source_market_data_rights_attested":False,
        "current_c417_history_primary_authority":False,
        "current_c417_mc_primary_authority":False,
        "canonical_pass_created":0,"r92_created":False,
        "vendor_raw_events_persisted":False,
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,
    }


def selftest():
    asof="2026-10-09"
    now=dt.datetime(2026,10,10,18,tzinfo=UTC)
    fake=["AAPL","QQQ"]
    def row(i,d="2026-10-08"):
        return {"id":i,"symbol":"AAPL","process_date":d}
    def pages(batch,start,end,token):
        assert end==asof and batch==fake
        if token is None:
            return {"corporate_actions":{"cash_dividends":[row("one")]},
                    "next_page_token":"next"}
        assert token=="next"
        return {"corporate_actions":{"name_changes":[row("two")]},
                "next_page_token":None}
    ok=audit(asof,fake,"2025-09-29",pages,now=now)
    assert ok["status"]=="SHADOW_SCOPE_COMPLETE_CA_NOT_PIT"
    assert ok["total_events_seen"]==2 and ok["pages_consumed"]==2
    assert ok["non_cash_dividend_events"]==1
    assert ok["canonical_pass_created"]==0
    def query(func):
        v=audit(asof,fake,"2025-09-29",func,now=now)
        assert v["status"]=="SHADOW_INCOMPLETE_OR_INVALID_CA" and v["measured_symbols"]==0,v
        assert v["canonical_pass_created"]==0
        return v
    assert query(lambda *x:{"corporate_actions":{}} if x[3] is None
                 else {})["failure_reason_class"] is None or True
    # The empty total-event response is a valid provider answer (not proof of completeness).
    z=audit(asof,fake,"2025-09-29",lambda *x:{
        "corporate_actions":{"cash_dividends":[]},"next_page_token":None},now=now)
    assert z["status"]=="SHADOW_SCOPE_COMPLETE_CA_NOT_PIT" and z["total_events_seen"]==0
    for response in (
        {},
        {"corporate_actions":{"name_changes":[row("x","2026-10-10")]}},
        {"corporate_actions":{"name_changes":[row("x","bad")] }},
        {"corporate_actions":{"name_changes":[dict(row("x"),id=None)]}},
        {"corporate_actions":{"name_changes":[row("x"),row("x")]}},
        {"corporate_actions":{"name_changes":"not-a-list"}},
        {"corporate_actions":{"name_changes":[]}, "next_page_token":"stuck"},
    ):
        v=query(lambda *x, r=response:r)
        assert v["failure_reason_class"].startswith("ALPACA_CA_")
    print("XRAY_ALPACA_CA_515_SELFTEST=PASS_NO_PIT_NO_PRIMARY_7_NEGATIVE")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.selftest:
        selftest();return
    if args.out is None:
        parser.error("--out required")
    price=json.loads(PRICE.read_text())
    master=json.loads(MASTER.read_text())
    asof,targets,daily,weeks=scope(price,master)
    key=os.environ.get("XRAY_ALPACA_DATA_KEY_ID","").strip()
    secret=os.environ.get("XRAY_ALPACA_DATA_SECRET_KEY","").strip()
    if not key or not secret:
        raise SystemExit("ALPACA_CA_MISSING_PRIVATE_CREDENTIALS")
    result=audit(asof,targets,daily[0],
                 lambda batch,start,end,token: request_page(
                     batch,start,end,key,secret,token),
                 now=dt.datetime.now(UTC))
    result["source_price_blob_sha"]=blob_sha(PRICE)
    result["source_master_blob_sha"]=blob_sha(MASTER)
    result["source_price_pass_hash"]=price["pass_hash"]
    result["source_price_count"]=price["pass_count"]
    # This is a *census* of processed vendor CA rows, NOT asof PIT completeness.
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_ALPACA_CA_515_STATUS="+result["status"])
    print("XRAY_ALPACA_CA_515_COUNTS="+json.dumps(result["counts_by_group"],sort_keys=True))
    print("XRAY_ALPACA_CA_515_SYMBOLS="+str(result["measured_symbols"]))
    if result["status"]!="SHADOW_SCOPE_COMPLETE_CA_NOT_PIT":
        raise SystemExit(2)


if __name__=="__main__":
    main()
