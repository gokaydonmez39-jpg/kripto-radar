#!/usr/bin/env python3
"""Independent official SEC submission timestamp witness for dual-class issuers.

Fetch exact SEC 10-Q accession acceptance for META & GOOGL 2026-Q2 cover
share-class disclosures. This cannot turn historical share vintages into
current listed-class shares or independent market-cap verification.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,json,os
from pathlib import Path
from zoneinfo import ZoneInfo
from sec_official_free_mc_transport_probe import (
    get_json,accession_acceptance_index,official_nasdaq_close_utc,
    valid_operator_contact
)
from alpaca_free_sip_shadow_guard import blob_sha

HERE=Path(__file__).resolve().parent
REG=HERE/"research/p0_sec_meta_googl_multiclass_cover_20261012_v1.json"
SCHEMA="XRAY_SEC_DUAL_CLASS_OFFICIAL_ACCESSION_PIT_WITNESS_V1"
UTC=dt.timezone.utc
ET=ZoneInfo("America/New_York")

def require(ok,reason):
    if not ok:raise ValueError("XRAY_SEC_MULTI_CLASS_PIT:"+reason)

def validate_registry(data):
    require(isinstance(data,dict) and data.get("schema")==
            "XRAY_20261012_SEC_2_MULTICLASS_SOURCE_RECOVERY_SHADOW_V1",
            "REGISTRY_SCHEMA")
    asof=data.get("asof_et")
    require(asof=="2026-10-09","ASOF_FROZEN_SOURCE_STALE")
    require(data.get("execution")=="NONE" and data.get("real_money")=="NO-GO"
            and data.get("unknown_never_pass") is True and
            data.get("submissions_acceptance_utc_independently_bound") is False
            and data.get("post_observed_to_20261009_split_and_issuance_reconciled") is False
            and data.get("c417_primary_mc_count_increment")==0
            and data.get("GO") is False,"NO_FALSE_AUTHORITY")
    rec=data.get("records")
    require(isinstance(rec,dict) and set(rec)=={"GOOGL","META"},
            "TWO_CLASS_ISSUER_SCOPE")
    for symbol,row in rec.items():
        cik=row.get("cik")
        accession=row.get("sec_accession")
        classes=row.get("classes")
        date=row.get("sec_class_observed_date")
        url=row.get("sec_10q_url")
        require(isinstance(cik,str) and len(cik)==10 and cik.isdigit()
                and isinstance(accession,str) and len(accession)==20
                and accession.count("-")==2
                and isinstance(url,str) and url.startswith("https://www.sec.gov/Archives/edgar/data/")
                and accession.replace("-","") in url,
                "OFFICIAL_FILING_ID_"+symbol)
        require(isinstance(classes,list) and len(classes)>=2
                and len({c.get("class") for c in classes})==len(classes)
                and any(c.get("ticker")==symbol and c.get("tradeable_nasdaq") is True for c in classes)
                and all(c.get("shares_as_filed",c.get("shares_millions_as_filed",0))>0 for c in classes),
                "MULTICLASS_ROW_INVALID_"+symbol)
        require(isinstance(date,str) and
                dt.date.fromisoformat(date)<=dt.date.fromisoformat(asof),
                "AFTER_DECISION_CLASS_FACT_"+symbol)
    return asof,rec

def verify_acceptance(row,sub,asof):
    require(str(sub.get("cik")).lstrip("0")==row["cik"].lstrip("0"),
            "CANNOT_BOUND_ISSUER_CIK")
    recent=accession_acceptance_index(sub)
    hit=recent.get(row["sec_accession"])
    require(isinstance(hit,dict) and hit.get("form")=="10-Q",
            "OFFICIAL_10Q_ACCESSION_NOT_LOCATED")
    filed=dt.date.fromisoformat(hit["filed"])
    observed=dt.date.fromisoformat(row["sec_class_observed_date"])
    require(observed<=filed<=dt.date.fromisoformat(asof),
            "OBSERVED_FILED_ASOF_ORDER_VIOLATED")
    raw=hit["accepted_at"]
    require(isinstance(raw,str) and (raw.endswith("Z") or raw.endswith("+00:00")),
            "UNSUPPORTED_SEC_ACCEPTANCE_CLOCK")
    t=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
    require(t.tzinfo is not None,"NAIVE_ACCEPTANCE")
    cutoff=official_nasdaq_close_utc(asof)
    possibilities=[t.astimezone(UTC),
                   t.replace(tzinfo=None).replace(tzinfo=ET).astimezone(UTC)]
    require(all(x<=cutoff for x in possibilities),
            "SEC_ACCEPTANCE_POST_DECISION_OR_AMBIGUOUS")
    require(all(x.date()<=dt.date.fromisoformat(asof) for x in possibilities),
            "SEC_ACCEPTANCE_FUTURE_DAY")
    return {"classification":"SEC_OFFICIAL_10Q_ACCEPTED_PRE_ASOF_TWO_CLOCK_SAFE",
            "acceptance_before_cutoff_both_clock_semantics":True,
            "observed_class_snapshot_before_ASOF":True}

def run(registry,fetch):
    asof,records=validate_registry(registry)
    out={}
    for ticker,row in records.items():
        try:
            sub=fetch(row["cik"])
            out[ticker]=verify_acceptance(row,sub,asof)
        except (ValueError,TypeError,KeyError,RuntimeError):
            out[ticker]={"classification":"UNKNOWN_OFFICIAL_SEC_PIT_OR_TRANSPORT",
                         "acceptance_before_cutoff_both_clock_semantics":False}
    counts=collections.Counter(x["classification"] for x in out.values())
    return {"schema":SCHEMA,"asof_et":asof,
            "status":"OFFICIAL_MULTI_CLASS_PIT_ACCEPTANCE_RESEARCH_ONLY",
            "outcomes":out,"counts":dict(sorted(counts.items())),
            "source_registry_git_blob_sha":blob_sha(REG),
            "observations":len(out),
            "current_class_shares_asof_verified":False,
            "independent_market_cap_comparator_verified":False,
            "c417_primary_mc_created":0,
            "can_register_R92":False,"GO":False,
            "raw_SEC_documents_and_shares_persisted":False,
            "execution":"NONE","real_money":"NO-GO"}

def selftest():
    from copy import deepcopy
    doc=json.loads(REG.read_text())
    asof,records=validate_registry(doc)
    require(len(records)==2,"TWO_ISSUER_POSITIVE")
    row=records["META"]; acc=row["sec_accession"]
    good={"cik":int(row["cik"]),"filings":{"recent":{
        "accessionNumber":[acc],"form":["10-Q"],
        "filingDate":["2026-08-01"],
        "acceptanceDateTime":["2026-08-01T14:00:00Z"]}}}
    witness=verify_acceptance(row,good,asof)
    require(witness["acceptance_before_cutoff_both_clock_semantics"],
            "PRE_ASOF_POSITIVE")
    faults=[
       ("WRONG_CIK",lambda x:x.__setitem__("cik",42)),
       ("AFTER_ASOF",lambda x:x["filings"]["recent"].__setitem__(
           "acceptanceDateTime",["2026-10-12T14:00:00Z"])),
       ("WRONG_FORM",lambda x:x["filings"]["recent"].__setitem__(
           "form",["8-K"])),
       ("ACC_MISMATCH",lambda x:x["filings"]["recent"].__setitem__(
           "accessionNumber",["0001628280-26-999999"])),
       ("FUTURE_FILED",lambda x:x["filings"]["recent"].__setitem__(
           "filingDate",["2026-10-12"])),
       ("NAIVE_ACCEPTED",lambda x:x["filings"]["recent"].__setitem__(
           "acceptanceDateTime",["2026-08-01T14:00:00"]))
    ]
    for name,fn in faults:
        x=deepcopy(good);fn(x)
        try:verify_acceptance(row,x,asof)
        except (ValueError,TypeError):pass
        else:raise AssertionError("SEC_DUALCLASS_PIT_FALSE_PASS:"+name)
    x=deepcopy(doc);x["records"]["GOOGL"]["classes"][0]["ticker"]="NOT_GOOGL"
    try:validate_registry(x)
    except ValueError:pass
    else:raise AssertionError("WRONG_SHARE_CLASS_ACCEPTED")
    print("XRAY_SEC_DUALCLASS_PIT_SELFTEST=PASS_2_POSITIVE_7_NEGATIVE_OPTIMIZED_SAFE")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:return selftest()
    require(args.out is not None,"NO_OUTPUT_PATH")
    ua=os.getenv("XRAY_SEC_USER_AGENT","")
    require(valid_operator_contact(ua),"OFFICIAL_SEC_FAIR_ACCESS_AGENT_MISSING")
    registry=json.loads(REG.read_text())
    result=run(registry,lambda cik:get_json(
        f"https://data.sec.gov/submissions/CIK{cik}.json",ua))
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_SEC_DUALCLASS_PIT_STATUS="+result["status"])
    print("XRAY_SEC_DUALCLASS_PIT_COUNTS="+json.dumps(result["counts"],sort_keys=True))
    print("XRAY_SEC_DUALCLASS_MC_PRIMARY=0_NO_C417_AUTHORITY")

if __name__=="__main__":main()
