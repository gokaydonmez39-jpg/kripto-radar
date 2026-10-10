#!/usr/bin/env python3
"""Validate SOURCE-scope math in v46 shadow triage; NOT data-provider proof.

No network, API credentials, canonical mutations, MC promotion or notifications.
This protects readers against accidental treatment of connected-app observations
as authorized same-ASOF market-data evidence.
"""
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RECORD=Path(__file__).with_name(
    "continuation_checkpoint_20261010_price514_three_source_shadow_triage_v46.json"
)

def git_blob_sha(raw:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def validate(record:dict,price:dict,price_sha:str)->tuple[bool,list[str]]:
    errors=[]
    def demand(test,reason):
        if not test:errors.append(reason)
    demand(record.get("schema")=="XRAY_PRICE514_THREE_SOURCE_RESEARCH_SHADOW_TRIAGE_V1","SCHEMA_DRIFT")
    demand(record.get("source_price_git_blob_sha")==price_sha,"PRICE_SHA_DRIFT")
    demand(record.get("asof_et")==price.get("asof_et"),"ASOF_MISMATCH")
    scope=price.get("pass_symbols") or []
    n=price.get("pass_count")
    demand(type(n) is int and len(scope)==n and len(set(scope))==n,"PRICE_SCOPE_INVALID")
    demand(record.get("price_pass_count")==n,"PRICE_PASS_COUNT_MISMATCH")
    universe=set(scope)
    h=record.get("history_alpaca_connected") or {}
    m=record.get("mc_longbridge_connected") or {}
    sec=record.get("sec_edgar") or {}
    missing=h.get("incomplete_symbols") or []
    below=m.get("below_floor_symbols") or []
    demand(len(missing)==len(set(missing)) and set(missing)<=universe,"HISTORY_SET_INVALID")
    demand(len(below)==len(set(below)) and set(below)<=universe,"MC_SET_INVALID")
    demand(h.get("requested_price_pass_symbols")==n and h.get("batches_complete")==26
           and h.get("exchange_sessions_exact")==260 and h.get("weekly_last_closes_exact")==52
           and h.get("calendar_first")=="2025-09-29"
           and h.get("calendar_last")=="2026-10-09", "HISTORY_SCOPE_UNVERIFIED")
    demand(h.get("exact_session_and_week_date_coverage")==n-len(missing)
           and h.get("incomplete_date_coverage")==len(missing), "HISTORY_COUNT_MISMATCH")
    demand(m.get("requested_price_pass_symbols")==n and m.get("groups_complete")==11
           and m.get("market_cap_values_received")==n, "MC_SCOPE_INCOMPLETE")
    demand(m.get("above_or_equal_existing_usd_2b_mc_floor")==n-len(below)
           and m.get("below_existing_usd_2b_mc_floor")==len(below),"MC_COUNT_MISMATCH")
    demand(sec.get("source_exact_price_pass_scope")==n
           and (sec.get("accepted_share_vintage_shadows",0)+
                sec.get("unknown_issuer_shares",0)+
                sec.get("unknown_sec_transport",0))==n,"SEC_PARTITION_MISMATCH")
    both=sorted(set(missing)&set(below))
    joint=record.get("shadow_joint_partition") or {}
    demand(joint.get("intersection_both_missing")==both
           and joint.get("history_and_mc_shadow_preliminary_qualifiers")==
              n-len(missing)-len(below)+len(both),"CROSS_SOURCE_SET_MATH_INVALID")
    # A successful diagnostic may NEVER become authority, even if the math checks.
    demand(record.get("execution")=="NONE" and record.get("real_money")=="NO-GO"
           and record.get("unknown_never_pass") is True
           and record.get("can_create_primary_mc") is False
           and record.get("can_repair_canonical_history") is False
           and record.get("can_register_r92") is False
           and record.get("release_status")=="RESEARCH_DIAGNOSTIC_ONLY_NO_GO",
           "ILLEGAL_PRIMARY_OR_R92_PROMOTION")
    demand(m.get("market_cap_primary_promotion") is False
           and m.get("asof_et_value_witness_present") is False
           and m.get("non_display_automation_license_proven") is False
           and h.get("git_runner_secret_present") is False
           and h.get("connected_app_evidence_publicly_replayable") is False,
           "NON_ATTESTED_SOURCE_MUST_REMAIN_BLOCKED")
    return not errors, sorted(set(errors))

def selftest():
    raw=(ROOT/"canonical_current_price_dv30.json").read_bytes()
    price=json.loads(raw)
    record=json.loads(RECORD.read_bytes())
    sha=git_blob_sha(raw)
    assert validate(record,price,sha)==(True,[]),validate(record,price,sha)
    cases=[
       ("sha",lambda a: a.update({"source_price_git_blob_sha":"0"*40})),
       ("asof",lambda a: a.update({"asof_et":"2026-10-08"})),
       ("noauth",lambda a: a.update({"can_create_primary_mc":True})),
       ("device",lambda a: a.update({"can_register_r92":True})),
       ("history",lambda a:a["history_alpaca_connected"]["incomplete_symbols"].append("AAPL")),
       ("mc",lambda a:a["mc_longbridge_connected"]["above_or_equal_existing_usd_2b_mc_floor"].__class__),
       ("partition",lambda a:a["sec_edgar"].update({"accepted_share_vintage_shadows":347})),
       ("math",lambda a:a["shadow_joint_partition"].update({"history_and_mc_shadow_preliminary_qualifiers":514})),
       ("license",lambda a:a["mc_longbridge_connected"].update({"non_display_automation_license_proven":True})),
    ]
    for name,mutate in cases:
        a=copy.deepcopy(record)
        if name=="mc":
            a["mc_longbridge_connected"]["above_or_equal_existing_usd_2b_mc_floor"]+=1
        else:mutate(a)
        ok,reasons=validate(a,price,sha)
        assert not ok,(name,reasons)
    print("XRAY_SHADOW_V46_READBACK_TEST=PASS_POSITIVE_9_NEGATIVES_NO_PRIMARY")

if __name__=="__main__":
    selftest()
