#!/usr/bin/env python3
"""Official Oct13 ten SPAC SEC submission vintage and filing-item witness.

A live issuer SIC is not immutable Oct13 operating status. An issuer named
Acquisition Corp may have closed a transaction during the as-of period;
do not count SIC drift, company name or an uninspected 8-K as de-SPAC PASS.
No canonical MASTER update absent independently verified as-of completion.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,time,urllib.parse,urllib.request
from pathlib import Path
import sec_official_free_mc_transport_probe as sec

ROOT=Path(__file__).resolve().parent
TARGET="2026-10-13"
SCHEMA="XRAY_MASTER_TEN_OCT13_LIVE_SEC_VINTAGE_V1"
SCOPE=("ALIS","BSAA","FACT","FVN","HCAC","IPXG","MACI","MCGA","MMTX","WTG")
def need(test,reason):
    if not test:raise ValueError("XRAY_OCT13_TEN_"+reason)
def blob(p):
    b=p.read_bytes()
    return hashlib.sha1(b"blob "+str(len(b)).encode()+bytes([0])+b).hexdigest()

def eligible_filing_index(recent,asof=TARGET):
    forms=recent.get("form") or []
    filings=recent.get("filingDate") or []
    acc=recent.get("accessionNumber") or []
    doc=recent.get("primaryDocument") or []
    out=[]
    for f,d,a,p in zip(forms,filings,acc,doc):
        if not all(isinstance(x,str) for x in (f,d,a,p)):continue
        if d<=asof and f in ("8-K","10-Q","10-K","S-4","S-4/A","8-A12B","425"):
            out.append({"form":f,"filed":d,"accession":a,"document":p})
    return sorted(out,key=lambda x:(x["filed"],x["accession"]),reverse=True)

def latest_8k_text(url,ua):
    req=urllib.request.Request(url,headers={"User-Agent":ua,"Accept":"text/html"})
    with urllib.request.urlopen(req,timeout=17) as response:
        body=response.read(2000001)
    need(len(body)<=2000000,"SEC_FILING_BODY_TOO_LARGE")
    lower=body.decode("utf-8","replace").lower()
    return {"body_sha256":hashlib.sha256(body).hexdigest(),
       "item_2_01_text_appears":("item 2.01" in lower or "item&nbsp;2.01" in lower),
       "combination_term_appears":"business combination" in lower,
       "acquisition_close_term_appears":any(s in lower for s in
             ("consummated the business combination","closing of the business combination")),
       "filing_text_not_legal_conclusion":True}

def selftest():
    j={"form":["8-K","10-Q","8-K"],"filingDate":["2026-10-14","2026-10-12","2026-10-13"],
       "accessionNumber":["1","2","3"],"primaryDocument":["a.htm","b.htm","c.htm"]}
    good=eligible_filing_index(j)
    need(len(good)==2 and good[0]["accession"]=="3","SEC_LOOKAHEAD_VETO")
    need(len(SCOPE)==10 and len(set(SCOPE))==10,"SCOPE")
    print("XRAY_MASTER_TEN_OCT13_SELFTEST=PASS_OFFICIAL_SEC_ASOF_FILING_GUARDS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:selftest();return
    need(a.out and not a.out.resolve().is_relative_to(ROOT.parent.resolve()),"OUTPUT_LOCAL_ONLY")
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    research=json.loads((ROOT/"research/master_ten_sec_cik_sic_resolution_20261012_v1.json").read_text())
    need(master.get("asof_et")==TARGET and master.get("unknown_count")==10
         and tuple(sorted(master.get("unknown_symbols") or []))==SCOPE,
         "OCT13_MASTER_10_SET")
    need(set(research.get("rows") or {})==set(SCOPE)
         and research.get("cik_matched_count")==10,"CIK10_REFERENCE")
    ua=(os.getenv("XRAY_SEC_USER_AGENT") or "").strip()
    need(sec.valid_operator_contact(ua),"OFFICIAL_SEC_OPERATOR_CONTACT")
    result={"schema":SCHEMA,"asof_et":TARGET,
       "master_git_blob_sha":blob(ROOT/"canonical_current_master_manifest.json"),
       "reference_sec_ten_blob_sha":blob(ROOT/"research/master_ten_sec_cik_sic_resolution_20261012_v1.json"),
       "symbols":list(SCOPE),"rows":{},"sec_submissions_attempted":0,
       "sec_8k_documents_attempted":0,
       "sec_cik_mapped_count":10,
       "production_master_unknown_count_before":10,
       "production_master_unknown_count_after":10,
       "production_master_modified":False,"new_operating_pass_created":0,
       "new_r92_created":0,"execution":"NONE","real_money":"NO-GO",
       "unknown_never_pass":True}
    def save():
        result["classification_counts"]=dict(sorted(collections.Counter(
          (v.get("classification") or "UNKNOWN_NOT_CHECKED") for v in result["rows"].values()).items()))
        a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    save()
    for symbol in SCOPE:
        ref=research["rows"][symbol]
        cik=ref["cik"]
        need(isinstance(cik,str) and len(cik)==10 and cik.isdigit(),"CIK_IDENTITY")
        row={"cik":cik,"prior_issuer":ref.get("issuer"),
             "prior_sic":ref.get("sic_diagnostic"),
             "sec_submissions_url":"https://data.sec.gov/submissions/CIK"+cik+".json",
             "classification":"UNKNOWN_OFFICIAL_COMPLETION_NOT_VERIFIED_ASOF13"}
        result["sec_submissions_attempted"]+=1
        try:
            doc=sec.get_json(row["sec_submissions_url"],ua)
            need(str(doc.get("cik","")).zfill(10)==cik,"LIVE_CIK_RESPONSE")
            row["current_sec_issuer_name"]=doc.get("name")
            row["current_sec_sic"]=doc.get("sic")
            row["current_sic_not_asof13_pit"]=True
            row["current_sec_tickers"]=doc.get("tickers")
            submissions=eligible_filing_index((doc.get("filings") or {}).get("recent") or {})
            row["asof_filing_count_in_recent_index"]=len(submissions)
            row["latest_asof_filings"]=submissions[:5]
            latest_8k=next((x for x in submissions if x["form"]=="8-K"),None)
            if latest_8k:
                digits=latest_8k["accession"].replace("-","")
                name=latest_8k["document"]
                if name and "/" not in name and ".." not in name:
                    url=("https://www.sec.gov/Archives/edgar/data/"+
                      str(int(cik))+"/"+digits+"/"+urllib.parse.quote(name))
                    row["latest_8k_source_url"]=url
                    result["sec_8k_documents_attempted"]+=1
                    try:
                        row["latest_8k_text_witness"]=latest_8k_text(url,ua)
                    except (ValueError,TimeoutError,Exception) as ex:
                        row["latest_8k_text_witness_status"]="UNAVAILABLE_NO_INFERENCE"
                    time.sleep(.6)
        except ValueError as e:
            row["sec_source_status"]="OFFICIAL_SEC_RESPONSE_UNAVAILABLE"
            if any(z in str(e) for z in ("HTTP_403","HTTP_429")):
                row["classification"]="UNKNOWN_SEC_FAIR_ACCESS_STOP"
                result["rows"][symbol]=row;save();break
        result["rows"][symbol]=row
        save();time.sleep(.6)
    for symbol in SCOPE:
        if symbol not in result["rows"]:
            result["rows"][symbol]={
              "cik":research["rows"][symbol]["cik"],
              "classification":"UNKNOWN_NOT_ATTEMPTED_AFTER_SEC_STOP"}
    save()
    print("XRAY_MASTER_TEN_OCT13_SEC_SUBMISSIONS="+str(result["sec_submissions_attempted"]))
    print("XRAY_MASTER_TEN_OCT13_SEC_8K_DOCS="+str(result["sec_8k_documents_attempted"]))
    print("XRAY_MASTER_TEN_OCT13_CLASSIFICATIONS="+json.dumps(result["classification_counts"],sort_keys=True))
    print("XRAY_MASTER_TEN_OCT13_CANONICAL_UNKNOWN=10_NO_R92")

if __name__=="__main__":main()
