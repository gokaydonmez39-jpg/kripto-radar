#!/usr/bin/env python3
"""515x260 raw-split restatement vs Alpaca event-type API; same provider only.

Checks whether each of the 11 numerically restated stock histories has a
corresponding Alpaca split event within the exact current 260-session period.
No historical announcement/creation-time PIT guarantee and no independent
issuer or shareholder class attestation. Read-only, encrypted-secret access,
sanitized derived statuses only. Never creates HISTORY/MC/R92/GO authority.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import json
import os
from pathlib import Path

from alpaca_full_scope_260_shadow import scope,PRICE,MASTER
from alpaca_full_scope_ca_shadow import (
    request_page,KNOWN_GROUPS,SUBJECT_FIELDS,MAX_PAGES
)
from alpaca_free_sip_shadow_guard import blob_sha

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_P0_SPLIT_EVENT_RESTATEMENT_BRIDGE_SHADOW_V1"
SPLIT_GROUPS=frozenset({"forward_splits","reverse_splits","unit_splits"})

def require(condition,code):
    if not condition:raise ValueError("XRAY_CA_SPLIT_RESTATEMENT:"+code)

def reconcile_source(history,price,master,asof,targets):
    require(history.get("schema")=="XRAY_ALPACA_515_DUAL_RAW_SPLIT_SHADOW_V1"
            and history.get("status")=="SHADOW_DUAL_ADJUSTMENT_SCOPE_MEASURED_NO_PIT_AUTHORITY"
            and history.get("asof_et")==asof
            and history.get("ticker_identity_mapping_asof_et")==asof
            and history.get("source_price_blob_sha")==blob_sha(PRICE)
            and history.get("source_master_blob_sha")==blob_sha(MASTER)
            and history.get("source_price_pass_hash")==price.get("pass_hash"),
            "DUAL_SOURCE_HASH_OR_ASOF")
    require(history.get("scope_with_qqq")==len(targets)
            and history.get("measured_scope")==len(targets)
            and history.get("transport_failure_class") is None
            and history.get("unresolved_symbols")=={}
            and history.get("production_HISTORY_PASS_created")==0
            and history.get("C417_PRIMARY_MC_created")==0
            and history.get("R92_created") is False
            and history.get("GO") is False,
            "DUAL_SOURCE_PARTITION_NOT_CLOSED")
    src=history.get("source_symbol_statuses")
    changed=history.get("numeric_restatement_symbols")
    require(isinstance(src,dict) and set(src)==set(targets)
            and isinstance(changed,list) and changed==sorted(set(changed))
            and set(changed).issubset(set(targets))
            and len(changed)==history.get("numeric_restatement_count"),
            "RESTATEMENT_SYMBOL_SET_INEXACT")
    for s in targets:
        status=src[s]
        if s in changed:
            require(status.get("dual_classification")==
                    "SHADOW_SPLIT_RESTATEMENT_NUMERICALLY_CONSISTENT",
                    "RESTATEMENT_SYMBOL_NOT_CONFIRMED_"+s)
        else:
            require(status.get("dual_classification")=="SHADOW_NO_RESTATEMENT_SEEN",
                    "CROSS_SOURCE_SPLIT_STATUS_UNKNOWN_"+s)
    return changed

def event_group_status(batch,start,end,request):
    """All pages; exact recognized split subjects and unique event IDs only."""
    require(len(batch)==1,"MUST_USE_ONE_TICKER_PER_QUERY")
    ticker=batch[0]
    known=set();splits=set();seen=set();token=None
    for _ in range(MAX_PAGES):
        data=request(batch,start,end,token)
        require(isinstance(data,dict) and isinstance(data.get("corporate_actions"),dict),
                "CA_SCHEMA_OR_TRANSPORT")
        actions=data["corporate_actions"]
        for group,items in actions.items():
            require(group in KNOWN_GROUPS and isinstance(items,list),
                    "UNKNOWN_CA_GROUP")
            for e in items:
                require(isinstance(e,dict) and
                        isinstance(e.get("id"),str) and e["id"],
                        "BAD_CA_EVENT_ID")
                id=e["id"]
                require(id not in seen,"CA_DUPLICATE_EVENT_ID")
                seen.add(id)
                process=e.get("process_date")
                require(isinstance(process,str) and
                        len(process)==10 and start<=process<=end,
                        "CA_PROCESS_DATE_NOT_ASOF_BOUND")
                subjects={e[k] for k in SUBJECT_FIELDS
                          if isinstance(e.get(k),str) and e[k]}
                require(ticker in subjects,
                        "CA_NOT_BOUND_TO_CURRENT_SECURITY_TICKER")
                known.add(id)
                if group in SPLIT_GROUPS:splits.add(id)
        nt=data.get("next_page_token")
        if nt in (None,""):break
        require(isinstance(nt,str) and nt!=token and nt not in seen,
                "CA_CURSOR_INVALID")
        token=nt
    else:
        raise ValueError("XRAY_CA_SPLIT_RESTATEMENT:PAGE_BUDGET")
    return {"status":("SHADOW_MATCHED_SPLIT_CA_EVENT" if splits else
                      "UNKNOWN_RESTATED_BUT_NO_CA_SPLIT_RECORD"),
            "split_ca_count":len(splits),
            "total_events_matched_to_ticker":len(known)}

def run(history,fetch,*,meta_only=False):
    price=json.loads(PRICE.read_text())
    master=json.loads(MASTER.read_text())
    asof,targets,daily,weeks=scope(price,master)
    changed=reconcile_source(history,price,master,asof,targets)
    counts=collections.Counter()
    entries={}
    for ticker in changed:
        try:
            outcome=event_group_status(
                [ticker],daily[0],asof,fetch)
        except (ValueError,RuntimeError,TypeError,KeyError):
            outcome={"status":"UNKNOWN_CA_FEED_OR_SUBJECT_PROVENANCE",
                     "split_ca_count":None}
        entries[ticker]=outcome
        counts[outcome["status"]]+=1
    return {"schema":SCHEMA,"asof_et":asof,
            "source_raw_split_run_id":38178676524,
            "source_price_blob_sha":blob_sha(PRICE),
            "source_master_blob_sha":blob_sha(MASTER),
            "full_515_raw_split_measured":len(targets),
            "numerically_restated_symbols":len(changed),
            "actual_changed_symbols":changed,
            "status_counts":dict(sorted(counts.items())),
            "correlations":entries,
            "status":"SAME_PROVIDER_EVENT_EXISTENCE_RESEARCH_ONLY",
            "independent_issuer_CA_PIT_verified":False,
            "provider_event_creation_PIT_verified":False,
            "split_adjustment_full_52week_primary_authority":False,
            "can_create_HISTORY_PASS":False,
            "can_create_C417_PRIMARY_MC":False,
            "can_register_R92":False,"GO":False,
            "raw_vendor_events_saved":False,
            "execution":"NONE","real_money":"NO-GO",
            "unknown_never_pass":True}

def selftest():
    T="TEST"
    good={"corporate_actions":{"forward_splits":[
          {"id":"SYNTHETIC_CA_1","symbol":T,"process_date":"2026-10-08"}]},
          "next_page_token":None}
    f=lambda *args:good
    result=event_group_status([T],"2025-09-29","2026-10-09",f)
    require(result["split_ca_count"]==1 and
            result["status"]=="SHADOW_MATCHED_SPLIT_CA_EVENT",
            "SPLIT_EXISTENCE_POSITIVE")
    no=event_group_status([T],"2025-09-29","2026-10-09",
           lambda *args:{"corporate_actions":{"cash_dividends":[]},
                         "next_page_token":None})
    require(no["status"]=="UNKNOWN_RESTATED_BUT_NO_CA_SPLIT_RECORD",
            "MISSING_CA_REMAINS_UNKNOWN")
    wrongs=[
      {"corporate_actions":{"UNKNOWN":[good["corporate_actions"]["forward_splits"][0]]}},
      {"corporate_actions":{"forward_splits":[dict(
          good["corporate_actions"]["forward_splits"][0],symbol="OTHER")]}},
      {"corporate_actions":{"forward_splits":[dict(
          good["corporate_actions"]["forward_splits"][0],process_date="2026-10-10")]}},
      {"corporate_actions":{"forward_splits":[dict(
          good["corporate_actions"]["forward_splits"][0],id="")]}},
      {"corporate_actions":{"forward_splits":"not a list"}},
      {"corporate_actions":{"forward_splits":[
          good["corporate_actions"]["forward_splits"][0]]*2}},
      {"corporate_actions":None}
    ]
    for i,bad in enumerate(wrongs):
        try:event_group_status([T],"2025-09-29","2026-10-09",lambda *a,c=bad:c)
        except ValueError:pass
        else:raise AssertionError("SYNTHETIC_FALSE_CA_ACCEPT_"+str(i))
    print("XRAY_SPLIT_CA_EVENT_BRIDGE_SELFTEST=PASS_2_POSITIVE_7_NEGATIVE_PYTHON_O_SAFE_NO_PRIMARY")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--raw-split",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:return selftest()
    require(a.raw_split is not None and a.out is not None,
            "EXACT_RUN_AND_OUTPUT_REQUIRED")
    key=os.environ.get("XRAY_ALPACA_DATA_KEY_ID","")
    secret=os.environ.get("XRAY_ALPACA_DATA_SECRET_KEY","")
    require(key and secret,"ALPACA_DATA_API_CREDENTIALS_MISSING")
    evidence=json.loads(a.raw_split.read_text())
    result=run(evidence,lambda batch,start,end,token:
               request_page(batch,start,end,key,secret,token))
    a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_SPLIT_EVENT_P0_BRIDGE_STATUS="+result["status"])
    print("XRAY_SPLIT_EVENT_P0_BRIDGE_COUNTS="+json.dumps(result["status_counts"],sort_keys=True))
    print("XRAY_SPLIT_EVENT_NO_PRIMARY=true")

if __name__=="__main__":main()
