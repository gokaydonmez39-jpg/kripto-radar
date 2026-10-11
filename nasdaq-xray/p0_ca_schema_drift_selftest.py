#!/usr/bin/env python3
"""CA semantics must reject unknown provider schema / unbound ticker subjects.

Normal/optimized Python safe, no vendor data, market-cap, corporate action
primary attestations, or security transactions.
"""
from __future__ import annotations
import datetime as dt
from alpaca_full_scope_ca_shadow import audit,SCHEMA

NOW=dt.datetime(2026,10,10,18,tzinfo=dt.timezone.utc)
TARGETS=["AAPL","QQQ"]
START="2025-09-29"
ASOF="2026-10-09"

def require(ok,why):
    if not ok:raise RuntimeError("P0_CA_SCHEMA_DRIFT_TEST:"+why)

def row(symbol,ident):
    return {"id":ident,"symbol":symbol,"process_date":"2026-10-07"}

def run_with(group,rows):
    def source(batch,start,end,token):
        require(batch==TARGETS and start==START and end==ASOF and token is None,
                "SOURCE_EPOCH_OR_SCOPE_CHANGED")
        return {"corporate_actions":{group:rows},"next_page_token":None}
    return audit(ASOF,TARGETS,START,source,now=NOW)

def main():
    good=run_with("forward_splits",[row("AAPL","SYNTHETIC_ONLY_1")])
    require(good["status"]=="SHADOW_SCOPE_COMPLETE_CA_NOT_PIT","GOOD_KNOWN_GROUP")
    require(good["unknown_vendor_group_events"]==0
            and good["subject_not_in_requested_batch"]==0,"GOOD_BINDING")
    require(good["current_c417_history_primary_authority"] is False
            and good["current_c417_mc_primary_authority"] is False
            and good["r92_created"] is False,"GOOD_NOT_PRIMARY")
    empty=run_with("forward_splits",[])
    require(empty["status"]=="SHADOW_SCOPE_COMPLETE_CA_NOT_PIT"
            and empty["total_events_seen"]==0
            and empty["independent_issuer_corporate_actions_reconciled"] is False,
            "EMPTY_NOT_INDEPENDENT_COMPLETENESS")
    wrong=run_with("NEW_UNKNOWN_SPLIT_TYPE",[row("AAPL","SYNTHETIC_ONLY_2")])
    require(wrong["status"]=="SHADOW_INCOMPLETE_OR_INVALID_CA"
            and wrong["failure_reason_class"]=="ALPACA_CA_UNKNOWN_VENDOR_GROUP_SCHEMA"
            and wrong["unknown_vendor_group_events"]==1,"UNKNOWN_VENDOR_GROUP_NOT_REJECTED")
    foreign=run_with("forward_splits",[row("NOT_IN_QUERY","SYNTHETIC_ONLY_3")])
    require(foreign["status"]=="SHADOW_INCOMPLETE_OR_INVALID_CA"
            and foreign["failure_reason_class"]=="ALPACA_CA_EVENT_SUBJECT_NOT_BOUND_TO_REQUEST"
            and foreign["subject_not_in_requested_batch"]==1,"FOREIGN_EVENT_NOT_REJECTED")
    for out in (good,empty,wrong,foreign):
        require(out["schema"]==SCHEMA and
                out["current_c417_history_primary_authority"] is False
                and out["canonical_pass_created"]==0
                and out["real_money"]=="NO-GO","NO_AUTHORITY_FOR_ANY_CASE")
    print("XRAY_CA_UNKNOWN_GROUP_UNBOUND_SUBJECT_GUARD=PASS_2_POSITIVE_2_NEGATIVE_PYTHON_O_SAFE_SHADOW")

if __name__=="__main__":main()
