#!/usr/bin/env python3
"""C4.18 official SEC cross-issuer share-fact discovery (NOT market cap).

Seven bounded public SEC calls (one current CIK map, six frames max).
No price, raw share values in outputs, share-class promotion, PRIMARY or AL.
SEC frame 'filed' is a DATE, not a proven pre-close acceptance timestamp.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import json
import os
from pathlib import Path

import sec_free_mc_multisymbol_pit_audit as core
import sec_official_free_mc_transport_probe as sec

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_C418_SEC_FRAMES_SHARE_DISCOVERY_SHADOW_V1"
SEC_BASE="https://data.sec.gov/api/xbrl/frames"
CONCEPTS=(("dei","EntityCommonStockSharesOutstanding"),
          ("us-gaap","CommonStockSharesOutstanding"))
MAX_VINTAGE_AGE_DAYS=120
NO_AUTH={"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
         "c417_mc_primary_created":False,"c417_history_pass_created":False,
         "r92_eligible":False,"market_cap_calculated":False,
         "canonical_modified":False,"vendor_price_requested":False,
         "source_market_data_entitlement_attested":False,
         "issuer_share_class_pit_attested":False,
         "filing_acceptance_intraday_attested":False,
         "raw_shares_in_report":False}

def periods(asof:str)->tuple[str,...]:
    x=dt.date.fromisoformat(asof)
    if x.isoformat()!=asof:raise ValueError("ASOF_INVALID")
    year=x.year;quarter=(x.month-1)//3+1
    result=[]
    # Current quarter data should not be assumed complete at the close.
    for _ in range(3):
        quarter-=1
        if quarter==0:year-=1;quarter=4
        result.append(f"CY{year}Q{quarter}I")
    return tuple(result)

def classify_fact(row,asof):
    if not isinstance(row,dict):
        return "ROW_INVALID"
    required=("cik","accn","form","filed","end","val")
    if any(k not in row for k in required):return "ROW_MISSING_FIELD"
    try:
        cik=int(row["cik"])
        filed=dt.date.fromisoformat(str(row["filed"]))
        end=dt.date.fromisoformat(str(row["end"]))
        today=dt.date.fromisoformat(asof)
    except (ValueError,TypeError,OverflowError):
        return "ROW_INVALID"
    if cik<=0 or not isinstance(row["accn"],str) or not row["accn"]:
        return "ROW_INVALID"
    if row["form"] not in ("10-Q","10-K","10-Q/A","10-K/A","20-F","40-F"):
        return "FORM_NOT_FILING_SCOPE"
    if filed>=today:
        return "FILED_ON_OR_AFTER_ASOF_NO_PRE_CLOSE_PIT"
    if end>filed or end>today or (today-end).days>MAX_VINTAGE_AGE_DAYS:
        return "STALE_OR_FUTURE_SHARE_OBSERVATION"
    val=row["val"]
    if type(val) is not int or val<=0:
        return "NON_POSITIVE_OR_NONINTEGER_SHARES"
    return "DATE_ONLY_ELIGIBLE_NO_INTRADAY_ACCEPTANCE"

def interpret(frames_by_concept:dict,symbol_to_cik:dict,asof:str):
    """Deduplicate accession-level facts; never synthesize per-class shares."""
    symbols=sorted(symbol_to_cik)
    ciks={int(cik) for cik in symbol_to_cik.values()}
    seen=collections.defaultdict(set)
    available=collections.defaultdict(set)
    duplicates=collections.Counter()
    rejected=collections.Counter()
    if not isinstance(frames_by_concept,dict) or not frames_by_concept:
        raise ValueError("NO_OFFICIAL_FRAMES")
    for concept,frame_list in frames_by_concept.items():
        if concept not in ("dei","us-gaap") or not isinstance(frame_list,list):
            raise ValueError("FRAME_SCHEMA_TAMPERED")
        for frame in frame_list:
            if not isinstance(frame,dict) or not isinstance(frame.get("data"),list):
                raise ValueError("FRAME_DATA_SCHEMA_INVALID")
            for row in frame["data"]:
                reason=classify_fact(row,asof)
                if reason!="DATE_ONLY_ELIGIBLE_NO_INTRADAY_ACCEPTANCE":
                    rejected[reason]+=1
                    continue
                cik=int(row["cik"])
                if cik not in ciks:continue
                stamp=(row["accn"],row["end"],row["filed"])
                if stamp in seen[(concept,cik)]:
                    duplicates[concept]+=1
                seen[(concept,cik)].add(stamp)
                available[(concept,cik)].add((stamp,row["val"]))
    result={}
    for symbol in symbols:
        cik=int(symbol_to_cik[symbol])
        dei=available.get(("dei",cik),set())
        gaap=available.get(("us-gaap",cik),set())
        if dei:
            by_vintage=collections.defaultdict(set)
            for stamp,value in dei:
                by_vintage[stamp].add(value)
            latest=max(by_vintage)
            if len(by_vintage[latest])!=1:
                status="CONFLICTING_DEI_SAME_VINTAGE"
            else:
                status="DEI_DATE_ONLY_UNVERIFIED_CLASS_AND_ACCEPTANCE"
        elif gaap:
            status="USGAAP_ONLY_DIMENSIONAL_CLASS_UNKNOWN"
        else:
            status="NO_FRESH_FRAME_SHARE_FACT"
        result[symbol]=status
    return dict(sorted(collections.Counter(result.values()).items())),dict(rejected),dict(duplicates)

def report(asof,count,status,classification=None,reason=None):
    return dict(NO_AUTH,
        schema=SCHEMA,asof_et=asof,status=status,
        current_price_pass_scope_count=count,received_symbols=0 if classification is None else count,
        classes=classification or {},rejected_frame_row_reason_counts={},
        duplicate_frame_fact_counts={},reason_codes=[reason] if reason else [],
        source="SEC_OFFICIAL_XBRL_FRAMES",
        current_cik_mapping_not_pit=True,SEC_frame_filed_date_only=True,
        frame_api_cannot_prove_intraday_acceptance=True,
        one_issuer_not_one_tradeable_share_class=True)

def execute():
    asof,symbols=core.load_scope(0,514)
    r=report(asof,len(symbols),"SOURCE_NOT_AVAILABLE")
    useragent=os.getenv("XRAY_SEC_USER_AGENT","")
    if not sec.valid_operator_contact(useragent):
        r["reason_codes"]=["SEC_OPERATOR_CONTACT_MISSING"]
        return r
    try:
        company_map=sec.get_json(core.SEC_MAP,useragent)
        found=core.map_ciks(company_map)
    except ValueError as exc:
        r["reason_codes"]=[str(exc)[:90]]
        return r
    mapped={s:found[s] for s in symbols if s in found}
    missing_map=len(symbols)-len(mapped)
    frames={c:[] for c,t in CONCEPTS}
    fetched=0
    for period in periods(asof):
        for concept,tag in CONCEPTS:
            url=f"{SEC_BASE}/{concept}/{tag}/shares/{period}.json"
            try:
                blob=sec.get_json(url,useragent)
            except ValueError as exc:
                r["status"]="SOURCE_PARTIAL_FRAME_TRANSPORT"
                r["reason_codes"]=["SEC_FRAMES_"+str(exc)[:70]]
                r["frames_http200"]=fetched
                return r
            if not isinstance(blob,dict) or not isinstance(blob.get("data"),list):
                r["reason_codes"]=["SEC_FRAME_SCHEMA_MISMATCH"]
                r["frames_http200"]=fetched
                return r
            frames[concept].append(blob)
            fetched+=1
    groups,invalid,dupes=interpret(frames,mapped,asof)
    if missing_map:groups["NO_CURRENT_SEC_CIK_ROUTE"]=missing_map
    if sum(groups.values())!=len(symbols):
        return dict(r,reason_codes=["NOT_EXACT_514_SCOPE_PARTITION"])
    return dict(r,status="SHADOW_FRAME_DISCOVERY_COMPLETE_NOT_PIT",
        received_symbols=len(symbols),classes=groups,
        rejected_frame_row_reason_counts=invalid,
        duplicate_frame_fact_counts=dupes,frames_http200=fetched,
        reason_codes=["DATE_ONLY_CLASS_UNVERIFIED_NOT_PRIMARY"])

def selftest():
    assert periods("2026-10-09")==("CY2026Q2I","CY2026Q1I","CY2025Q4I")
    ok={"cik":1,"accn":"0000000001-26-000001","form":"10-Q",
        "filed":"2026-08-01","end":"2026-06-30","val":10_000_000}
    assert classify_fact(ok,"2026-10-09")=="DATE_ONLY_ELIGIBLE_NO_INTRADAY_ACCEPTANCE"
    altered=dict(ok,filed="2026-10-09")
    assert classify_fact(altered,"2026-10-09")=="FILED_ON_OR_AFTER_ASOF_NO_PRE_CLOSE_PIT"
    altered=dict(ok,val=0)
    assert classify_fact(altered,"2026-10-09")=="NON_POSITIVE_OR_NONINTEGER_SHARES"
    altered=dict(ok,form="8-K")
    assert classify_fact(altered,"2026-10-09")=="FORM_NOT_FILING_SCOPE"
    altered=dict(ok,end="2025-12-31")
    assert classify_fact(altered,"2026-10-09")=="STALE_OR_FUTURE_SHARE_OBSERVATION"
    altered=dict(ok,accn=None)
    assert classify_fact(altered,"2026-10-09")=="ROW_INVALID"
    a=dict(ok,cik=2,val=100)
    frames={"dei":[{"data":[ok,ok]}],
            "us-gaap":[{"data":[a]}]}
    counts,invalid,duplicates=interpret(frames,{"A":"0000000001","B":"0000000002","C":"0000000003"},"2026-10-09")
    assert counts=={"DEI_DATE_ONLY_UNVERIFIED_CLASS_AND_ACCEPTANCE":1,
                    "USGAAP_ONLY_DIMENSIONAL_CLASS_UNKNOWN":1,
                    "NO_FRESH_FRAME_SHARE_FACT":1}
    assert duplicates["dei"]==1
    conflict=dict(ok,val=11_000_000)
    frames["dei"][0]["data"].append(conflict)
    counts,_,_=interpret(frames,{"A":"0000000001"},"2026-10-09")
    assert counts=={"CONFLICTING_DEI_SAME_VINTAGE":1}
    assert report("2026-10-09",514,"TEST")["c417_mc_primary_created"] is False
    print("XRAY_C418_SEC_FRAMES_SHADOW_SELFTEST=PASS_PIT_CLASS_DUPLICATE_CONFLICT_NO_PRIMARY")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.selftest:selftest();return
    if not args.out:parser.error("--out required")
    r=execute()
    args.out.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n")
    print("XRAY_SEC_FRAMES_DISCOVERY_STATUS="+r["status"])
    print("XRAY_SEC_FRAMES_DISCOVERY_CLASSES="+json.dumps(r["classes"],sort_keys=True))
    print("XRAY_SEC_FRAMES_DISCOVERY_REASON_CODES="+json.dumps(r["reason_codes"]))
    print("XRAY_SEC_FRAMES_DISCOVERY_NO_MARKET_CAP_NO_PRIMARY_NO_R92")

if __name__=="__main__":
    main()
