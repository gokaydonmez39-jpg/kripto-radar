#!/usr/bin/env python3
"""Read-only four PRICE-UNKNOWN investigation contract.

The witness is based on a user-connected SIP plugin observation plus public
official listing evidence, not on an authenticated GitHub vendor call.
Never transmute historical availability into C4.17 source entitlement.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"research/20261009_price_four_unknown_source_triage_shadow.json"
PRICE=ROOT/"canonical_current_price_dv30.json"
SCHEMA="XRAY_20261009_PRICE_FOUR_UNKNOWN_SOURCE_TRIAGE_SHADOW_V1"
SYMS=["AIOK","GRAL","RTSN","TRXB"]
NEW=["AIOK","RTSN","TRXB"]

def blob_sha(buf):
    return hashlib.sha1(b"blob "+str(len(buf)).encode()+bytes([0])+buf).hexdigest()

def evaluate(j,p,source_sha):
    if not all(isinstance(x,dict) for x in (j,p)):
        raise ValueError("NON_OBJECT_SOURCE")
    if (j.get("schema")!=SCHEMA or j.get("asof_et")!="2026-10-09"
        or j.get("asof_et")!=p.get("asof_et")
        or j.get("price_source_git_blob_sha")!=source_sha):
        raise ValueError("SOURCE_ASOF_OR_PRICE_SHA_DRIFT")
    if not (j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
            and j.get("unknown_never_pass") is True):
        raise ValueError("SOURCE_POLICY_INVALID")
    if not (p.get("execution")=="NONE" and p.get("real_money")=="NO-GO"
            and p.get("unknown_never_pass") is True):
        raise ValueError("PRICE_POLICY_INVALID")
    unknown=j.get("price_unknown_symbols")
    if (unknown!=SYMS or p.get("unknown_symbols")!=SYMS
        or j.get("price_unknown_count")!=4 or p.get("unknown_count")!=4
        or p.get("pass_count")!=514):
        raise ValueError("PRICE_UNKNOWN_PARTITION_DRIFT")
    expected=p.get("expected30")
    if not (isinstance(expected,list) and len(expected)==30
            and expected==sorted(set(expected)) and expected[-1]=="2026-10-09"):
        raise ValueError("OFFICIAL_30_SESSION_SCOPE_INVALID")
    obs=j.get("alpaca_connector_observation") or {}
    if not (obs.get("type")=="READ_ONLY_PLUGIN_OBSERVATION_NOT_GITHUB_RUNNER_EVIDENCE"
            and obs.get("feed")=="SIP" and obs.get("timeframe")=="1Day"
            and obs.get("source_automated_use_rights_verified") is False
            and obs.get("raw_vendor_bars_committed") is False):
        raise ValueError("VENDOR_SOURCE_SCOPE_OR_RIGHTS_OVERCLAIM")
    rows=obs.get("per_symbol")
    if not isinstance(rows,dict) or sorted(rows)!=SYMS:
        raise ValueError("FOUR_SYMBOLS_NOT_EXACT")
    listing=j.get("listing_identity_evidence")
    if not isinstance(listing,dict) or sorted(listing)!=NEW:
        raise ValueError("LISTING_IDENTITY_INCOMPLETE")
    total=0
    for s in SYMS:
        r=rows[s]
        n=r.get("observed_in_30")
        m=r.get("missing_of_30")
        if (type(n) is not int or type(m) is not int or
            n<0 or m<0 or n+m!=30 or r.get("asof_record_seen") is not True):
            raise ValueError("OBSERVATION_COUNT_INCONSISTENT")
        total+=n
        if s=="GRAL":
            if not (n==30 and m==0
                and r.get("extended_observed_dates")==265
                and r.get("dv30_ge_50m_by_connector_math") is True
                and r.get("decision")=="SHADOW_30_30_PRICE_DV_SOURCE_OBSERVED_NOT_LICENSED_PRIMARY"):
                raise ValueError("GRAL_RESEARCH_OBSERVATION_INCONSISTENT")
        else:
            if not (n==1 and m==29 and
                r.get("decision")=="SHADOW_LISTING_AGE_LT30_NO_HISTORY_PASS"):
                raise ValueError("NEW_LISTING_OBSERVATION_INCONSISTENT")
            official=listing[s]
            if not (official.get("date")=="2026-10-09"
                    and isinstance(official.get("official_source"),str)
                    and official["official_source"].startswith("https://")
                    and (official.get("predecessor_composite_authorized") is False
                         if s!="AIOK" else
                         official.get("independent_parent_composite_authorized") is False)):
                raise ValueError("NEW_LISTING_CONTINUITY_UNPROVEN")
    if not (j.get("authority")=="INDEPENDENT_RESEARCH_DIAGNOSTIC_ONLY_NOT_C417_PRICE_PRIMARY"
            and j.get("source_rights_independently_verified") is False
            and j.get("primary_price_pass_created")==0
            and j.get("canonical_history_pass_created")==0
            and j.get("mc_primary_pass_created")==0
            and j.get("r92_created") is False
            and j.get("device_delivery_proven") is False):
        raise ValueError("RESEARCH_OVERCLAIM_OR_UNSAFE_PROMOTION")
    # Not a cryptographic proof of external SIP bytes: preserve witness limits.
    return {
       "schema":"XRAY_FOUR_UNKNOWN_DIAGNOSTIC_VALIDATED_BUT_SOURCE_UNREPLAYED_V1",
       "asof_et":"2026-10-09","price_blob_sha":source_sha,
       "price_pass_count_unmodified":514,"four_unknown_remain_unknown":True,
       "observed_date_entries_research_only":total,
       "new_issue_less_than_30":3,"gral_exact_30_sip_observed":True,
       "gral_260_official_sessions_proven":False,
       "official_listings_source_urls_only_not_live_replayed":True,
       "private_sip_connector_response_replayed_in_CI":False,
       "source_entitlement_proven":False,
       "canonical_history_pass_created":0,"mc_primary_pass_created":0,
       "r92_created":False,"execution":"NONE","real_money":"NO-GO"
    }

def selftest(doc,price,sha):
    valid=evaluate(doc,price,sha)
    assert valid["four_unknown_remain_unknown"] is True
    cases=(
      ("sha",lambda x:x.update(price_source_git_blob_sha="0"*40)),
      ("rights",lambda x:x.update(source_rights_independently_verified=True)),
      ("asof",lambda x:x.update(asof_et="2026-10-08")),
      ("bad_count",lambda x:x["alpaca_connector_observation"]["per_symbol"]["GRAL"].update(observed_in_30=29)),
      ("new_faked",lambda x:x["alpaca_connector_observation"]["per_symbol"]["RTSN"].update(observed_in_30=30,missing_of_30=0)),
      ("no_primary",lambda x:x.update(primary_price_pass_created=1)),
      ("false_r92",lambda x:x.update(r92_created=True)),
      ("parent",lambda x:x["listing_identity_evidence"]["AIOK"].update(independent_parent_composite_authorized=True)),
      ("missing_identity",lambda x:x["listing_identity_evidence"].pop("TRXB")),
      ("vendor_rights",lambda x:x["alpaca_connector_observation"].update(source_automated_use_rights_verified=True)),
      ("unknown_set",lambda x:x.update(price_unknown_symbols=["AIOK","GRAL","RTSN"])),
    )
    for tag,mutate in cases:
        altered=copy.deepcopy(doc)
        mutate(altered)
        try:evaluate(altered,price,sha)
        except ValueError:continue
        raise AssertionError("UNSAFE_RESEARCH_CLAIM_ACCEPTED:"+tag)
    print("XRAY_FOUR_UNKNOWN_OFFICIAL_LISTING_SIP_TRIAGE=PASS_11_NEGATIVES_NO_CANONICAL_PROMOTION")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out",type=Path)
    a=parser.parse_args()
    pbytes=PRICE.read_bytes()
    p=json.loads(pbytes)
    j=json.loads(SOURCE.read_bytes())
    sha=blob_sha(pbytes)
    if a.selftest:selftest(j,p,sha)
    report=evaluate(j,p,sha)
    if a.out:
        if a.out.resolve().is_relative_to(ROOT.parent):
            raise ValueError("REPORT_DESTINATION_PUBLIC_REPO_FORBIDDEN")
        a.out.write_text(json.dumps(report,sort_keys=True,indent=2)+chr(10))
    print("XRAY_FOUR_UNKNOWN_TRIAGE=RESEARCH_SHADOW_VALIDATED_3_NEW_LISTINGS_1_GRAL_NO_PRIMARY")
if __name__=="__main__":main()
