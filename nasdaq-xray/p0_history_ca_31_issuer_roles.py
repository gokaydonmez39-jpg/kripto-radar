#!/usr/bin/env python3
"""P0 31 corporate-action residual: actual security roles, exact source bind.

Precisely joins authenticated Alpaca 31-event queries to the immutable 515
symbol-local CA census and 497-history review artifact. Distinguishes direct
security-identity/rebase (name/symbol changes, spinoff source, stock dividend,
merger acquiree) from acquirer-side cap-table changes. Both remain research
UNKNOWN under C4.17; acquirer role is not an issuer capital-structure proof.
No raw event, ID, CUSIP, price, share count or monetary data persisted.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,json,os,hashlib
from pathlib import Path
from alpaca_full_scope_ca_shadow import (
    request_page,MAX_PAGES,KNOWN_GROUPS,SUBJECT_FIELDS
)
from alpaca_free_sip_shadow_guard import blob_sha

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_P0_31_CA_ROLES_DIRECT13_ACQUIRER18_SHADOW_V1"
DIRECT=frozenset(("symbol","source_symbol","old_symbol","new_symbol",
                 "acquiree_symbol","target_symbol"))
ACQUIRER=frozenset(("acquirer_symbol",))
EXCLUDED=frozenset(("cash_dividends","forward_splits",
                    "reverse_splits","unit_splits"))
DIRECT_ONLY="DIRECT_IDENTITY_OR_PRICE_CA_REQUIRES_PIT"
ACQUIRER_ONLY="ACQUIRER_SIDE_CAP_TABLE_AND_ISSUANCE_PIT_REQUIRED"
UNCERTAIN="UNKNOWN_CA_ROLE_OR_SOURCE_LEDGER"

def require(ok,reason):
    if not ok:raise ValueError("XRAY_CA_ROLE_31:"+reason)

def check_source(census,queue):
    require(census.get("schema")==
            "XRAY_ALPACA_515_CORPORATE_ACTIONS_CENSUS_SHADOW_V1" and
            census.get("status")=="SHADOW_SCOPE_COMPLETE_CA_NOT_PIT" and
            queue.get("schema")==
            "XRAY_P0_497_31_466_CA_LOCAL_RISK_PARTITION_SHADOW_V1",
            "SOURCE_SCHEMA_STATUS")
    require(census.get("asof_et")==queue.get("asof_et")=="2026-10-09",
            "MISMATCH_SOURCE_ASOF")
    for doc in (census,queue):
        require(doc.get("source_price_blob_sha")==blob_sha(
                ROOT/"canonical_current_price_dv30.json")
                and doc.get("source_master_blob_sha")==blob_sha(
                ROOT/"canonical_current_master_manifest.json"),
                "SOURCE_GIT_BLOB_WRONG")
    require(census.get("symbol_local_CA_registry_completed") is True
            and census.get("independent_issuer_corporate_actions_reconciled") is False
            and census.get("canonical_pass_created")==0
            and queue.get("production_HISTORY_PASS_created")==0
            and queue.get("production_C417_PRIMARY_MC_created")==0
            and queue.get("GO") is False,
            "SOURCE_FALSE_PRODUCTION_RIGHTS")
    cohort=queue.get("full_history_non_split_review_symbols")
    require(type(cohort) is list and len(cohort)==31 and
            cohort==sorted(set(cohort)) and
            queue.get("full_history_non_split_CA_review_required")==31 and
            queue.get("full_history_stock_count")==497 and
            set(cohort).issubset(set(census.get("symbol_local_non_split_review") or {})),
            "COHORT_OR_EVENT_STATUS_DRIFT")
    return cohort

def inspect_events(batch,first,asof,fetch):
    require(type(batch) is list and batch==sorted(set(batch)) and
            0<len(batch)<=65,"REQUEST_COHORT_INVALID")
    all_events=set();seen_cursors=set();cursor=None
    role_sets={sym:set() for sym in batch}
    type_counts={sym:collections.Counter() for sym in batch}
    for _ in range(MAX_PAGES):
        data=fetch(batch,first,asof,cursor)
        require(type(data) is dict and type(data.get("corporate_actions")) is dict,
                "CA_RESPONSE_SCHEMA_INVALID")
        for group,rows in data["corporate_actions"].items():
            require(group in KNOWN_GROUPS and type(rows) is list,
                    "UNSUPPORTED_CA_TYPE")
            for row in rows:
                require(type(row) is dict and type(row.get("id")) is str
                        and row["id"] not in all_events
                        and row["id"],"DUPLICATE_OR_UNKNOWN_CA_ID")
                all_events.add(row["id"])
                process=row.get("process_date")
                require(type(process) is str and len(process)==10
                        and first<=process<=asof,
                        "CA_ACTION_AFTER_CUTOFF_OR_BEFORE_SCOPE")
                related={key:row.get(key) for key in SUBJECT_FIELDS
                         if type(row.get(key)) is str and
                         row.get(key) in role_sets}
                require(bool(related),"CA_EVENT_WITHOUT_REQUESTED_PARTY")
                if group in EXCLUDED:continue
                # A single event can list the SAME symbol both as old and
                # new ticker or both acquiree/acquirer. The original 515
                # census counted once per event+symbol, NOT once per role.
                # Preserve every role while counting each affected security
                # only once, otherwise the 31 exact source joins drift.
                for sym in set(related.values()):
                    type_counts[sym][group]+=1
                for role,sym in related.items():
                    if role in DIRECT:role_sets[sym].add("DIRECT")
                    elif role in ACQUIRER:role_sets[sym].add("ACQUIRER")
                    else:raise ValueError("XRAY_CA_ROLE_31:UNKNOWN_EVENT_SUBJECT_ROLE")
        nxt=data.get("next_page_token")
        if nxt in (None,""):break
        require(type(nxt) is str and nxt!=cursor and nxt not in seen_cursors
                and 0<len(nxt)<=2048,"CA_CURSOR_BAD_OR_LOOP")
        seen_cursors.add(nxt);cursor=nxt
    else:
        raise ValueError("XRAY_CA_ROLE_31:MAX_PAGES_EXCEEDED")
    return type_counts,role_sets

def reconcile(census,queue,fetch):
    cohort=check_source(census,queue)
    ca_counts,roles=inspect_events(cohort,"2025-09-29","2026-10-09",fetch)
    outcome={};drift=[]
    for sym in cohort:
        original=census["symbol_local_non_split_review"][sym]["event_type_counts"]
        got=dict(sorted(ca_counts[sym].items()))
        if got!=original:
            drift.append(sym)
            outcome[sym]=UNCERTAIN
        elif "DIRECT" in roles[sym]:
            outcome[sym]=DIRECT_ONLY
        elif roles[sym]=={"ACQUIRER"}:
            outcome[sym]=ACQUIRER_ONLY
        else:
            drift.append(sym);outcome[sym]=UNCERTAIN
    counts=collections.Counter(outcome.values())
    return {
        "schema":SCHEMA,"asof_et":"2026-10-09",
        "status":("RECONCILED_31_CA_ROLE_PARTITION_SHADOW_ONLY"
                  if not drift else "UNKNOWN_31_CA_ROLE_SOURCE_DRIFT"),
        "source_515_CA_run_id":38181356461,
        "source_497_CA_partition_run_id":38181517369,
        "source_price_blob_sha":blob_sha(ROOT/"canonical_current_price_dv30.json"),
        "source_master_blob_sha":blob_sha(ROOT/"canonical_current_master_manifest.json"),
        "full_history_review_cohort":31,
        "direct_security_CA_review_symbols":sorted(
            sym for sym,role in outcome.items() if role==DIRECT_ONLY),
        "acquirer_cap_table_CA_review_symbols":sorted(
            sym for sym,role in outcome.items() if role==ACQUIRER_ONLY),
        "unknown_role_or_census_drift_symbols":sorted(drift),
        "category_counts":dict(sorted(counts.items())),
        "every_symbol_still_requires_issuer_event_PIT":True,
        "acquirer_role_does_not_prove_cap_table_continuity":True,
        "no_non_split_event_observed_proves_absence":False,
        "historical_security_identity_PIT_proven":False,
        "issuer_MC_class_and_all_CA_pit_proven":False,
        "raw_CA_events_prices_shares_ids_persisted":False,
        "C417_PRIMARY_MC_pass_created":0,
        "canonical_HISTORY_PASS_created":0,
        "R92_created":False,"GO":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True
    }

def selftest():
    date="2026-10-07"
    rows=[
      ("stock_mergers",{"id":"test-A","acquirer_symbol":"AA","process_date":date}),
      ("name_changes",{"id":"test-B","old_symbol":"BB","new_symbol":"CC","process_date":date}),
      ("spin_offs",{"id":"test-C","source_symbol":"DD","process_date":date}),
      ("cash_dividends",{"id":"test-D","symbol":"AA","process_date":date})
    ]
    def fetch(batch,first,asof,cursor):
        return {"corporate_actions":{k:[item] for k,item in rows},
                "next_page_token":None}
    counts,roles=inspect_events(["AA","BB","CC","DD"],"2025-09-29",
                                "2026-10-09",fetch)
    duplicate_role_event={"id":"test-E","old_symbol":"BB","new_symbol":"BB",
                          "process_date":date}
    repeated=inspect_events(["BB"],"2025-09-29","2026-10-09",lambda *a:
                  {"corporate_actions":{"name_changes":[duplicate_role_event]},
                   "next_page_token":None})
    require(repeated[0]["BB"]=={"name_changes":1}
            and repeated[1]["BB"]=={"DIRECT"},
            "SAME_SYMBOL_MULTI_ROLE_EVENT_MUST_COUNT_ONCE")
    require(roles["AA"]=={"ACQUIRER"} and
            roles["BB"]==roles["CC"]==roles["DD"]=={"DIRECT"} and
            counts["AA"]=={"stock_mergers":1} and
            counts["BB"]=={"name_changes":1},"SYNTHETIC_ROLE_POSITIVE")
    def reject(label,bad):
        try:inspect_events(["AA","BB","CC","DD"],"2025-09-29",
                           "2026-10-09",lambda *a:bad)
        except ValueError:return
        raise AssertionError("FALSE_ACTION_ROLE_ACCEPT:"+label)
    reject("UNKNOWN_GROUP",{"corporate_actions":{"unknown_vendor":[rows[0][1]]}})
    reject("OUT_OF_ASOF",{"corporate_actions":{"stock_mergers":[
          dict(rows[0][1],process_date="2026-10-10")]}})
    reject("FOREIGN_CA",{"corporate_actions":{"stock_mergers":[
          dict(rows[0][1],acquirer_symbol="ZZ")]}})
    reject("DUPLICATE_EVENT",{"corporate_actions":{"stock_mergers":[
          rows[0][1],rows[0][1]]}})
    reject("EMPTY_SCHEMA",{})
    print("XRAY_P0_CA_ROLE_31_SELFTEST=PASS_2_POSITIVE_5_NEGATIVE_PYTHON_O_SAFE")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--census",type=Path)
    ap.add_argument("--queue",type=Path)
    ap.add_argument("--out",type=Path)
    a=ap.parse_args()
    if a.selftest:return selftest()
    require(a.census and a.queue and a.out,"SOURCE_ARTIFACT_AND_OUT_REQUIRED")
    key=os.getenv("XRAY_ALPACA_DATA_KEY_ID","")
    secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY","")
    require(key and secret,"READ_ONLY_API_CREDENTIALS_REQUIRED")
    ca=json.loads(a.census.read_text())
    q=json.loads(a.queue.read_text())
    output=reconcile(ca,q,lambda batch,start,end,token:
                     request_page(batch,start,end,key,secret,token))
    a.out.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")
    print("XRAY_P0_CA_ROLES="+output["status"])
    print("XRAY_P0_CA_ROLE_COUNTS="+json.dumps(output["category_counts"],sort_keys=True))
    print("XRAY_P0_CA_ROLES_PRIMARY_CREATED=0")

if __name__=="__main__":main()
