#!/usr/bin/env python3
"""Bind Alpaca complete-versus-all early events to exact 31 issuer CA roles.

Protects the 466 no-non-split-event-observed group from being promoted based
on the provider default complete filter. Source artifacts are immutable GitHub
Actions runs and PRICE/MASTER blobs; only derived labels in public outputs.
No live trading, false MC/HISTORY PASS, AL, R92, or GO.
"""
from __future__ import annotations
import argparse,copy,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_P0_31_QUALITY_INCOMPLETE_EVENTS_SOURCE_JOIN_V1"

def require(ok,why):
    if not ok:raise ValueError("XRAY_31_CA_QUALITY_JOIN:"+why)

def gitblob(path):
    raw=path.read_bytes()
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def evaluate(role,quality,price_sha,master_sha):
    require(role.get("schema")=="XRAY_P0_31_CA_ROLES_DIRECT13_ACQUIRER18_SHADOW_V1"
            and role.get("status")=="RECONCILED_31_CA_ROLE_PARTITION_SHADOW_ONLY"
            and quality.get("schema")=="XRAY_515_CA_COMPLETE_ALL_INCOMPLETE_SHADOW_V1"
            and quality.get("status")=="SHADOW_QUALITY_BOTH_515_SCOPES_CLOSED",
            "REAL_ROLE_AND_QUALITY_WITNESSES_REQUIRED")
    for p in (role,quality):
        require(p.get("asof_et")=="2026-10-09"
                and p.get("source_price_blob_sha")==price_sha
                and p.get("source_master_blob_sha")==master_sha
                and p.get("execution")=="NONE" and p.get("real_money")=="NO-GO"
                and p.get("GO") is False,
                "SOURCE_ASOF_SHA_OR_SAFETY_DRIFT")
    direct=set(role.get("direct_security_CA_review_symbols") or [])
    acquirer=set(role.get("acquirer_cap_table_CA_review_symbols") or [])
    require(len(direct)==13 and len(acquirer)==18
            and not(direct&acquirer)
            and role.get("full_history_review_cohort")==31
            and role.get("canonical_HISTORY_PASS_created")==0
            and role.get("C417_PRIMARY_MC_pass_created")==0,
            "EXPECTED_31_CA_ROLE_SET_UNVERIFIED")
    extra=set(quality.get("new_all_nonsplit_affected_tickers") or [])
    require(quality.get("source_scope_with_qqq")==515
            and type(quality.get("complete_event_ids")) is int
            and type(quality.get("all_event_ids")) is int
            and type(quality.get("all_not_in_complete")) is int
            and quality.get("all_not_in_complete")>=len(extra)
            and quality.get("all_event_ids")-quality.get("complete_event_ids")==
                 quality.get("all_not_in_complete")
            and quality.get("complete_missing_from_all")==0
            and quality.get("canonical_HISTORY_PASS_created")==0
            and quality.get("C417_PRIMARY_MC_created")==0,
            "PROVIDER_EVENT_QUALITY_ARITHMETIC_INVALID")
    new_direct=sorted(extra&direct)
    new_acquirer=sorted(extra&acquirer)
    new_outside=sorted(extra-(direct|acquirer))
    return {"schema":SCHEMA,"asof_et":"2026-10-09",
            "status":("SHADOW_INCOMPLETE_CA_EVENTS_BOUND_TO_EXISTING_REVIEW"
                      if not new_outside else
                      "UNKNOWN_NEW_CA_ISSUER_REVIEW_OUTSIDE_31"),
            "source_31_roles_run_id":38181849385,
            "source_515_complete_all_run_id":38182564771,
            "source_price_blob_sha":price_sha,
            "source_master_blob_sha":master_sha,
            "full_history_non_split_CA_review_count":31,
            "prior_direct_security_requiring_review":13,
            "prior_acquirer_cap_table_requiring_review":18,
            "data_quality_complete_events":quality["complete_event_ids"],
            "data_quality_all_events":quality["all_event_ids"],
            "new_unprocessed_events_from_all":quality["all_not_in_complete"],
            "new_unprocessed_non_split_direct_symbols":new_direct,
            "new_unprocessed_non_split_acquirer_symbols":new_acquirer,
            "new_unprocessed_non_split_outside_existing_31":new_outside,
            "outside_existing_31_count":len(new_outside),
            "not_observed_is_not_proven_absent":True,
            "issuer_issuance_and_CA_publication_PIT_reconciled":False,
            "canonical_HISTORY_PASS_created":0,"C417_PRIMARY_MC_created":0,
            "R92_created":False,"GO":False,
            "provider_raw_events_or_OHLCV_persisted":False,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def selftest(role,quality,p,m):
    original=evaluate(role,quality,p,m)
    require(original["new_unprocessed_events_from_all"]>=0
            and original["canonical_HISTORY_PASS_created"]==0,
            "POSITIVE_JOIN")
    def red(label,rr=role,qq=quality,pp=p,mm=m):
        try:evaluate(rr,qq,pp,mm)
        except ValueError:return
        raise AssertionError("CA_QUALITY_FALSE_PASS:"+label)
    r=copy.deepcopy(role);r["source_master_blob_sha"]="0"*40
    red("MASTER_TAMPER",rr=r)
    q=copy.deepcopy(quality);q["source_price_blob_sha"]="0"*40
    red("PRICE_TAMPER",qq=q)
    q=copy.deepcopy(quality);q["complete_missing_from_all"]=1
    red("QUALITY_NOT_SUPERSET",qq=q)
    q=copy.deepcopy(quality);q["all_not_in_complete"]=-1
    red("NEGATIVE_NEW_EVENT_COUNT",qq=q)
    q=copy.deepcopy(quality);q["canonical_HISTORY_PASS_created"]=1
    red("FALSE_PRODUCTION_HISTORY",qq=q)
    q=copy.deepcopy(quality)
    q["new_all_nonsplit_affected_tickers"]=["INVENTED"]
    q["all_not_in_complete"]=max(1,q["all_not_in_complete"])
    q["all_event_ids"]=q["complete_event_ids"]+q["all_not_in_complete"]
    mismatch=evaluate(role,q,p,m)
    require(mismatch["status"]=="UNKNOWN_NEW_CA_ISSUER_REVIEW_OUTSIDE_31"
            and mismatch["outside_existing_31_count"]==1,
            "NEW_UNCLASSIFIED_ISSUER_EVENT_MUST_BLOCK")
    print("XRAY_CA_QUALITY_ROLE_JOIN=PASS_REAL_2_POSITIVE_5_NEGATIVE_PYTHON_O_NO_PRIMARY")

def main():
    parser=argparse.ArgumentParser()
    for key in ("roles","quality"):
        parser.add_argument("--"+key,type=Path,required=True)
    parser.add_argument("--out",type=Path)
    parser.add_argument("--selftest",action="store_true")
    x=parser.parse_args()
    role=json.loads(x.roles.read_text())
    quality=json.loads(x.quality.read_text())
    p=gitblob(ROOT/"canonical_current_price_dv30.json")
    m=gitblob(ROOT/"canonical_current_master_manifest.json")
    if x.selftest:return selftest(role,quality,p,m)
    require(x.out is not None,"OUT_REQUIRED")
    result=evaluate(role,quality,p,m)
    x.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("XRAY_CA_ROLE_QUALITY_BINDING="+result["status"])
    print("XRAY_CA_ROLE_QUALITY_EXTRA="+str(result["new_unprocessed_events_from_all"]))
    print("XRAY_CA_ROLE_QUALITY_OUTSIDE_EXISTING_31="+str(result["outside_existing_31_count"]))
    print("XRAY_CA_ROLE_QUALITY_PRODUCTION_PRIMARY=0")

if __name__=="__main__":main()
