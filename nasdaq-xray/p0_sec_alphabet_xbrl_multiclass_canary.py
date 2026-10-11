#!/usr/bin/env python3
"""Official original SEC XBRL R1 multiclass identity diagnostic, NEVER C4.17 MC.

On Oct 9 2026 the companyfacts non-dimensional DEI shares are insufficient
to reconcile GOOG/GOOGL listed classes, nonlisted Class B, and preferred ADS.
Uses a fixed original accepted 2026 Q2 filing only as a real canary. Its
class disclosure does NOT attest post-filing issuance or same-ASOF marketcap.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from sec_official_free_mc_transport_probe import (
    accession_acceptance_index, get_json, official_nasdaq_close_utc,
    valid_operator_contact,
)

ASOF="2026-10-09"
CIK="0001652044"
ACCESSION="0001652044-26-000071"
R1_URL="https://www.sec.gov/Archives/edgar/data/1652044/000165204426000071/R1.htm"
SUB_URL="https://data.sec.gov/submissions/CIK0001652044.json"
SCHEMA="XRAY_SEC_MULTICLASS_GOOG_GOOGLE_ORIGINAL_XBRL_R1_V1"

def require(ok,why):
    if not ok:raise ValueError("XRAY_SEC_XBRL_CLASS:"+why)

class Reader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
        self.suppressed=0
    def handle_starttag(self,tag,attrs):
        if tag in ("style","script"):self.suppressed+=1
    def handle_endtag(self,tag):
        if tag in ("style","script") and self.suppressed:self.suppressed-=1
    def handle_data(self,data):
        if not self.suppressed:self.parts.append(data)

def text_of_report(raw):
    require(type(raw) is bytes and 500<len(raw)<9_000_000,"HTML_MISSING_OR_OVERSIZED")
    parser=Reader()
    parser.feed(raw.decode("utf-8","strict"))
    return re.sub(r"\s+"," "," ".join(parser.parts).replace("\xa0"," ")).strip()

def match_report(raw):
    text=text_of_report(raw)
    require("COVER PAGE - shares" in text and
            "Jul. 15, 2026" in text and "10-Q" in text and
            "Alphabet Inc." in text, "NOT_ORIGINAL_ALPHABET_2026_Q2_R1")
    # Presence of two registered common classes and a separately disclosed,
    # unlisted voting class is evidence AGAINST entity-level issuer shares
    # being the shares outstanding of either Nasdaq ticker.
    def window(marker):
        idx=text.find(marker)
        require(idx>=0,"MISSING_CLASS_LABEL_"+marker.replace(" ","_"))
        return text[idx:idx+1700]
    a=window("Class A Common Stock")
    c=window("Class C Capital Stock")
    b=window("Class B Common Stock")
    for label,excerpt,ticker in (("A",a,"GOOGL"),("C",c,"GOOG")):
        require("Title of 12(b) Security" in excerpt
                and re.search(r"\bTrading Symbol\b\s*"+ticker+r"\b",excerpt)
                and "Entity Common Stock, Shares Outstanding" in excerpt,
                "REGISTERED_CLASS_TICKER_OR_DEI_NOT_BOUND_"+label)
    require("Entity Common Stock, Shares Outstanding" in b,
            "UNLISTED_CLASS_B_NOT_SEPARATELY_DISCLOSED")
    # Report also lists preferred securities with 1/20 ADS underlying interest.
    require(re.search(r"\bTrading Symbol\b\s*GOOGM\b",text)
            and re.search(r"\bTrading Symbol\b\s*GOOGN\b",text)
            and "1/20th interest" in text,
            "PREFERRED_DEPOSITARY_CLASS_UNACCOUNTED")
    # Original SEC report may omit explicit base XBRL context attributes in
    # this human-readable rendering; never mark XBRL axis/member *fully*
    # audited from this report view.
    return {"verified_common_ticker_classes":{
            "GOOGL":"CLASS_A_COMMON", "GOOG":"CLASS_C_CAPITAL"},
            "unlisted_common_class_B_seen":True,
            "preferred_depositary_symbols":["GOOGM","GOOGN"],
            "filing_report_date":"2026-06-30",
            "filing_share_count_reference_date":"2026-07-15",
            "SEC_original_R1_rendering_sha256":hashlib.sha256(raw).hexdigest()}

def filing_pit(sub):
    require(str(sub.get("cik","")).lstrip("0")==CIK.lstrip("0"),
            "SUBMISSION_CIK_MISMATCH")
    idx=accession_acceptance_index(sub)
    r=idx.get(ACCESSION)
    require(type(r) is dict and r.get("form")=="10-Q",
            "ORIGINAL_ACCESSION_NOT_IN_SEC_SUBMISSIONS_RECENT")
    stamped=dt.datetime.fromisoformat(r["accepted_at"].replace("Z","+00:00"))
    require(stamped.tzinfo is not None and
            stamped.astimezone(dt.timezone.utc)<=official_nasdaq_close_utc(ASOF),
            "POST_ASOF_FILING_CANNOT_PROVE_ASOF")
    return True

def selftest():
    header="XML 108 R1.htm IDEA: XBRL DOCUMENT v3.26.1 COVER PAGE - shares shares in Millions 6 Months Ended Jun. 30, 2026 Jul. 15, 2026 Alphabet Inc. Form 10-Q "
    def block(name,ticker,units):
        return name+" Document Information [Line Items] Title of 12(b) Security "+name+" Trading Symbol "+ticker+" Security Exchange Name NASDAQ Entity Common Stock, Shares Outstanding "+units+" "
    valid=header+block("Class A Common Stock","GOOGL","5,868")+block("Class C Capital Stock","GOOG","5,527")+"Class B Common Stock Document Information [Line Items] Entity Common Stock, Shares Outstanding 835 "+"Depositary Shares 1/20th interest Trading Symbol GOOGM Depositary Shares 1/20th interest Trading Symbol GOOGN"
    def fixture(source):
        return ("<html><body>"+source+"</body></html>"+" "*600).encode()
    positive=match_report(fixture(valid))
    require(positive["verified_common_ticker_classes"]=={
        "GOOGL":"CLASS_A_COMMON","GOOG":"CLASS_C_CAPITAL"} and
        positive["unlisted_common_class_B_seen"],
        "POSITIVE_MULTICLASS_BOUND")
    def red(label,data):
        try:match_report(fixture(data))
        except ValueError:return
        raise AssertionError("SEC_MULTICLASS_FALSE_ACCEPT:"+label)
    red("SWAPPED_TICKER",valid.replace("Trading Symbol GOOGL","Trading Symbol SWAPPED"))
    red("NO_B",valid.replace("Class B Common Stock","Class K Common Stock"))
    red("NO_C",valid.replace("Class C Capital Stock","Class D Capital Stock"))
    red("MISSING_DEI",valid.replace("Entity Common Stock, Shares Outstanding","UNKNOWN"))
    red("MISSING_PREFERRED",valid.replace("Trading Symbol GOOGN","Trading Symbol NONE"))
    red("WRONG_DOCUMENT",valid.replace("Jul. 15, 2026","Jan. 15, 2026"))
    red("WRONG_ISSUER",valid.replace("Alphabet Inc.","Another Company"))
    print("XRAY_SEC_ALPHABET_MULTICLASS_SELFTEST=PASS_1_POSITIVE_7_NEGATIVE_PYTHON_O_SAFE_NO_PRIMARY")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:return selftest()
    require(a.out is not None,"OUTPUT_REQUIRED")
    ua=os.environ.get("XRAY_SEC_USER_AGENT","")
    require(valid_operator_contact(ua),"OFFICIAL_SEC_OPERATOR_CONTACT_REQUIRED")
    require(filing_pit(get_json(SUB_URL,ua)),"PIT_ACCEPTANCE_FAILED")
    req=urllib.request.Request(R1_URL,headers={
        "User-Agent":ua,"Accept":"text/html","Accept-Encoding":"identity"})
    try:
        with urllib.request.urlopen(req,timeout=30) as resp:
            require(resp.status==200,"SEC_R1_HTTP_NOT_200")
            raw=resp.read(9_000_001)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError("XRAY_SEC_XBRL_CLASS:OFFICIAL_SEC_R1_TRANSPORT_UNAVAILABLE") from exc
    result=match_report(raw)
    output={
        "schema":SCHEMA,"asof_et":ASOF,
        "CIK":CIK,"original_accession":ACCESSION,
        "original_SEC_URL":R1_URL,
        "official_original_SEC_10Q_accepted_before_20261009_close":True,
        **result,
        "SEC_R1_table_not_complete_machine_XBRL_context_axis_witness":True,
        "issuer_total_class_share_composition_unproven_at_asof":True,
        "post_filing_issuance_splits_repurchases_ADS_not_reconciled":True,
        "independent_issuer_market_cap_at_ASOF_not_attested":True,
        "GOOGL_GOOG_common_share_counts_not_equal_to_issuer_total":True,
        "no_vendor_prices_shares_MC_values_persisted":True,
        "C417_PRIMARY_MC_created":0,
        "canonical_HISTORY_PASS_created":0,
        "R92_created":False,"GO":False,"execution":"NONE",
        "real_money":"NO-GO","unknown_never_pass":True,
    }
    a.out.write_text(json.dumps(output,sort_keys=True,indent=2)+"\n")
    print("XRAY_SEC_ALPHABET_R1_CLASS_DIAGNOSTIC=OFFICIAL_PIT_MULTICLASS_SHADOW_ONLY")
    print("XRAY_SEC_ALPHABET_R1_NO_PRIMARY=true")

if __name__=="__main__":main()
