#!/usr/bin/env python3
"""Date-bound SEC SIC source-index audit. Diagnostic only; never creates alpha."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
MASTER=ROOT/"canonical_current_master_manifest.json"
SOURCE=ROOT/"research/master_20261012_ten_sec_sic_pit_forensic_v1.json"
SAFE={"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def demand(ok,code):
    if not ok:
        raise ValueError("XRAY_TEN_SEC_"+code)

def gitsha(buf):
    return hashlib.sha1(b"blob "+str(len(buf)).encode()+bytes([0])+buf).hexdigest()

def inspect(doc,master):
    m=json.loads(master)
    demand(doc.get("schema")=="XRAY_MASTER_TEN_SEC_PIT_FORENSIC_V1","SCHEMA")
    demand(doc.get("asof_et")==m.get("asof_et")=="2026-10-12","ASOF")
    demand(doc.get("source_master_git_blob_sha")==gitsha(master),"MASTER_BLOB")
    demand(doc.get("source_master_expected_unknown_count")==m.get("unknown_count")==10,"COUNT")
    demand(all(doc.get(k)==v for k,v in SAFE.items()) and
           doc.get("no_auto_override") is True and
           doc.get("no_master_mutation") is True and
           doc.get("actual_source_html_sha256_captured") is False,
           "RESEARCH_AUTHORITY")
    rows=doc.get("observations")
    demand(type(rows) is dict and set(rows)==set(m["unknown_symbols"]),"SYMBOL_SCOPE")
    sources=0
    conflict=[]
    unresolved=[]
    for symbol,row in sorted(rows.items()):
        cik=row.get("cik")
        filings=row.get("sec_filings")
        demand(type(row.get("issuer")) is str and type(filings) is list,"RECORD")
        if cik is None:
            demand(not filings and row.get("diagnostic_class")==
                   "OFFICIAL_ISSUER_AND_TICKER_IDENTITY_UNRESOLVED","UNKNOWN_CIK")
            unresolved.append(symbol)
            continue
        demand(type(cik) is str and re.fullmatch(r"\d{10}",cik) is not None
               and len(filings)>0,"CIK")
        codes=set()
        dates=[]
        for item in filings:
            url=urlsplit(item.get("url",""))
            demand(url.scheme=="https" and url.netloc=="www.sec.gov" and
                   url.path.startswith("/Archives/edgar/data/"+str(int(cik))+"/") and
                   not url.query and not url.fragment,"SEC_URL")
            date=dt.date.fromisoformat(item["filing_date"])
            demand(date<=dt.date(2026,10,12),"LOOKAHEAD")
            sic=item["sic"]
            demand(type(sic) is int and 100<=sic<=9999,"INVALID_SIC")
            codes.add(sic)
            dates.append(date)
            sources+=1
        demand(dates==sorted(set(dates)),"ORDER_OR_DUPLICATES")
        if len(codes)>1:
            conflict.append(symbol)
            demand(row.get("diagnostic_class")==
                   "CONFLICTING_DATED_SEC_SIC_REQUIRES_EVENT_RECONCILIATION",
                   "HIDDEN_CONFLICT")
    demand(sources==10 and unresolved==["IPXG"] and conflict==["HCAC"],
           "EXPECTED_SOURCE_COHORT")
    return {"schema":"XRAY_TEN_SEC_PIT_FORENSIC_RESULT_V1",
            "asof_et":"2026-10-12",
            "source_master_git_blob_sha":gitsha(master),
            "source_references":sources,"issuer_scope":len(rows),
            "issuer_identity_unresolved":unresolved,
            "sic_conflicting":conflict,"canonical_unknown_unchanged":10,
            "primary_identity_promoted":False,"primary_mc_created":False,
            "primary_price_created":False,"r92_created":False,
            "official_filing_content_hashes_verified":False,
            "exact_asof_listed_class_verified":False,**SAFE}

def selftest(doc,raw):
    x=inspect(doc,raw)
    demand(x["canonical_unknown_unchanged"]==10 and
           x["source_references"]==10,"POSITIVE")
    tests=[
      lambda d:d.update(asof_et="2026-10-13"),
      lambda d:d.update(source_master_git_blob_sha="0"*40),
      lambda d:d.update(no_auto_override=False),
      lambda d:d.update(execution="AUTO"),
      lambda d:d["observations"].pop("IPXG"),
      lambda d:d["observations"]["ALIS"]["sec_filings"][0].update(
                 filing_date="2026-10-14"),
      lambda d:d["observations"]["WTG"]["sec_filings"][0].update(
                 url="https://example.net/other"),
      lambda d:d["observations"]["HCAC"].update(diagnostic_class="OTHER"),
      lambda d:d["observations"]["HCAC"]["sec_filings"].append(
                 copy.deepcopy(d["observations"]["HCAC"]["sec_filings"][0])),
      lambda d:d["observations"]["IPXG"].update(cik="0000000001")]
    for number,change in enumerate(tests):
        bad=copy.deepcopy(doc)
        change(bad)
        try:inspect(bad,raw)
        except (ValueError,KeyError):
            continue
        raise RuntimeError("NEGATIVE_ACCEPTED_"+str(number))
    print("XRAY_MASTER_TEN_SEC_PIT_SELFTEST=PASS_10_NEGATIVES_NO_PRIMARY")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    raw=MASTER.read_bytes()
    doc=json.loads(SOURCE.read_text())
    if args.selftest:
        demand(args.out is None,"SELFTEST_OUTPUT")
        selftest(doc,raw)
        return
    demand(args.out is not None and not args.out.resolve().is_relative_to(ROOT),
           "OUTPUT_NOT_EPHEMERAL")
    result=inspect(doc,raw)
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("XRAY_MASTER_TEN_SEC_PIT_REFS="+str(result["source_references"]))
    print("XRAY_MASTER_TEN_SEC_NO_PRIMARY=PASS")

if __name__=="__main__":
    main()
