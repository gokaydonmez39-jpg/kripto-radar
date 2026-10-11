#!/usr/bin/env python3
"""Official SEC original document + accession acceptance: 12 split events.

Separate from a vendor corporate-action API. For each SEC URL in the
11-stock official issuer registry, fetch the original HTML with a legitimate
SEC User-Agent, verify its filing-index identity, bound SEC acceptance to
the canonical Nasdaq ASOF close under both UTC and ET clock interpretations,
and check only that the document actually mentions split/consolidation.
Full machine parsing of ratio text / historical publication is NOT claimed,
and no PRIMARY MC/HISTORY/AL/R92/GO authority is created. Never persist
raw downloaded issuer filing bytes, share counts, prices or account keys.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,html,json,os,re,time,urllib.request,urllib.error
from pathlib import Path
from zoneinfo import ZoneInfo
from sec_official_free_mc_transport_probe import (
    accession_acceptance_index,official_nasdaq_close_utc,get_json,
    valid_operator_contact
)
from alpaca_free_sip_shadow_guard import blob_sha

ROOT=Path(__file__).resolve().parent
REG=ROOT/"research/p0_11_split_events_official_sec_issuer_registry_20261012.json"
SCHEMA="XRAY_SEC_12_OFFICIAL_SPLIT_DOC_AND_SUBMISSION_PIT_CANARY_V1"
URLPAT=re.compile(r"^https://www\.sec\.gov/Archives/edgar/data/(\d{1,10})/(\d{18})/([^?#/]+)$")
UTC=dt.timezone.utc
NY=ZoneInfo("America/New_York")
WAIT=0.65

def require(ok,why):
    if not ok:raise ValueError("XRAY_SEC_SPLIT_DOC:"+why)

def doc_key(event):
    require(type(event) is dict and type(event.get("document")) is str,
            "DOCUMENT_URL_MISSING")
    match=URLPAT.fullmatch(event["document"])
    require(match is not None,"OFFICIAL_SEC_ARCHIVE_URL_MALFORMED")
    cik,code,filename=match.groups()
    accession=code[:10]+"-"+code[10:12]+"-"+code[12:]
    require(cik.isdigit() and int(cik)>0
            and filename.endswith((".htm",".html")),"SEC_ARCHIVE_PATH_INVALID")
    return cik.zfill(10),accession,event["document"]

def match_submission(event,sub,asof):
    cik,acc,url=doc_key(event)
    require(str(sub.get("cik") or "").lstrip("0")==cik.lstrip("0"),
            "SEC_ACCESSION_ISSUER_CIK_DRIFT")
    idx=accession_acceptance_index(sub)
    row=idx.get(acc)
    require(type(row) is dict and row.get("form") in {
        "8-K","8-K/A","10-Q","10-K","10-K/A","10-Q/A","DEF 14A",
        "6-K","6-K/A"},
        "OFFICIAL_ISSUER_SUBMISSION_NOT_LISTED")
    raw=row.get("accepted_at")
    require(type(raw) is str and (raw.endswith("Z") or raw.endswith("+00:00")),
            "UNSUPPORTED_SEC_ACCEPTANCE_CLOCK")
    accepted=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
    require(accepted.tzinfo is not None,"SEC_ACCEPTANCE_NAIVE")
    possible=[accepted.astimezone(UTC),
              accepted.replace(tzinfo=None).replace(tzinfo=NY).astimezone(UTC)]
    cutoff=official_nasdaq_close_utc(asof)
    require(all(x<=cutoff for x in possible) and
            dt.date.fromisoformat(row["filed"])<=dt.date.fromisoformat(asof),
            "SEC_ISSUER_DOCUMENT_LOOKAHEAD")
    return acc

# Verified SEC filing language: acceptance at current ASOF was tested
# independently in this job. This is document text verification, not an
# independently reconstructed cap table or historical issuer CUSIP chain.
OFFICIAL_SPLIT_TEXT={
  "ASST@2026-02-06":(r"\b1\s*[:/-]\s*20\b",r"\b1\s*[- ]\s*for\s*[- ]\s*20\b"),
  "BKNG@2026-04-06":(r"twenty\s*[- ]\s*five\s*[- ]\s*for\s*[- ]\s*one",r"\b25\s*[- ]\s*for\s*[- ]\s*1\b"),
  "CRWD@2026-07-02":(r"four\s*[- ]\s*for\s*[- ]\s*one",r"\b4\s*[- ]\s*for\s*[- ]\s*1\b"),
  "HON@2026-06-29":(r"\b1\s*[- ]\s*for\s*[- ]\s*2\b",r"\b1\s*[:/]\s*2\b",r"every\s+two\s+shares.{0,230}combined\s+into\s+one\s+share"),
  "IESC@2026-08-24":(r"two\s*[- ]\s*for\s*[- ]\s*one",r"\b2\s*[- ]\s*for\s*[- ]\s*1\b"),
  "KLAC@2026-06-12":(r"ten\s*[- ]\s*to\s*[- ]\s*one",r"ten\s*[- ]\s*for\s*[- ]\s*one",r"\b10\s*[- ]\s*for\s*[- ]\s*1\b"),
  "MNST@2026-08-11":(r"two\s*[- ]\s*for\s*[- ]\s*one",r"\b2\s*[- ]\s*for\s*[- ]\s*1\b"),
  "NFLX@2025-11-17":(r"ten\s*[- ]\s*for\s*[- ]\s*one",r"\b10\s*[- ]\s*for\s*[- ]\s*1\b"),
  "POWL@2026-04-06":(r"three\s*[- ]\s*for\s*[- ]\s*one",r"\b3\s*[- ]\s*for\s*[- ]\s*1\b"),
  "SNEX@2026-03-23":(r"three\s*[- ]\s*for\s*[- ]\s*two",r"\b3\s*[- ]\s*for\s*[- ]\s*2\b"),
  "SNEX@2026-07-20":(r"three\s*[- ]\s*for\s*[- ]\s*two",r"\b3\s*[- ]\s*for\s*[- ]\s*2\b"),
  "TRI@2026-05-04":(r"\b0\.984560\b",r"\b0\.98456\b")
}

def check_html(event,body):
    require(type(body) is bytes and 100<=len(body)<=8_000_000,
            "SEC_ORIGINAL_DOC_UNREADABLE")
    readable=html.unescape(re.sub(r"<[^>]*>"," ",body.decode("utf-8",errors="replace")))
    readable=re.sub(r"\s+"," ",readable).lower()
    require("split" in readable or "consolidat" in readable,
            "ORIGINAL_DOC_NO_SPLIT_TEXT")
    key=event.get("symbol","")+"@"+event.get("process_date","")
    required=OFFICIAL_SPLIT_TEXT.get(key)
    require(type(required) is tuple and bool(required),"OFFICIAL_RATIO_PATTERN_NOT_REGISTERED")
    require(any(re.search(regex,readable) for regex in required),
            "OFFICIAL_DOC_NUMERIC_SPLIT_RATIO_NOT_PARSED")
    return True

def audit(registry,fetch_sub,fetch_original):
    require(registry.get("schema")=="XRAY_P0_11_SPLIT_OFFICIAL_SEC_ISSUER_SOURCE_REGISTRY_V1"
            and registry.get("decision_asof")=="2026-10-09"
            and registry.get("GO") is False
            and registry.get("current_C417_PRIMARY_MC_created")==0,
            "REGISTRY_SOURCE_EPOCH_OR_AUTHORITY")
    events=registry.get("events")
    require(type(events) is list and len(events)==12
            and len({x.get("symbol") for x in events})==11,
            "12_EVENTS_11_ISSUERS_REQUIRED")
    by_cik={}
    stats=collections.Counter();out={}
    for e in events:
        sym=e["symbol"]; day=e["process_date"]
        key=sym+"@"+day
        try:
            cik,acc,url=doc_key(e)
            if cik not in by_cik:
                by_cik[cik]=fetch_sub(cik)
            match_submission(e,by_cik[cik],"2026-10-09")
            body=fetch_original(url)
            check_html(e,body)
            out[key]="SEC_OFFICIAL_ACCEPTED_PRE_ASOF_ORIGINAL_DOC_RATIO_TEXT_VERIFIED"
        except (ValueError,RuntimeError,KeyError,TypeError,
                urllib.error.HTTPError,urllib.error.URLError,TimeoutError):
            out[key]="UNKNOWN_SEC_DOC_OR_ACCEPTANCE_NOT_PROVEN"
        stats[out[key]]+=1
    require(len(out)==12 and sum(stats.values())==12,
            "12_EVENT_LEDGER_PARTITION_INCOMPLETE")
    return {"schema":SCHEMA,"asof_et":"2026-10-09",
            "role":"SEC_OFFICIAL_ARCHIVE_AND_ACCEPTANCE_DOC_EXISTS_RESEARCH_ONLY",
            "source_registry_git_blob_sha":blob_sha(REG),
            "source_events":12,"source_symbols":11,
            "SEC_document_and_acceptance_verified_count":stats[
              "SEC_OFFICIAL_ACCEPTED_PRE_ASOF_ORIGINAL_DOC_RATIO_TEXT_VERIFIED"],
            "SEC_document_or_acceptance_unknown_count":stats[
              "UNKNOWN_SEC_DOC_OR_ACCEPTANCE_NOT_PROVEN"],
            "event_statuses":out,
            "all_ratio_strings_machine_parsed_and_verified":stats[
               "SEC_OFFICIAL_ACCEPTED_PRE_ASOF_ORIGINAL_DOC_RATIO_TEXT_VERIFIED"]==12,
            "post_filing_issuer_shareclass_issuance_bound":False,
            "historical_CA_publication_time_machine_attested":False,
            "raw_SEC_HTML_prices_or_shares_persisted":False,
            "C417_PRIMARY_MC_created":0,"canonical_HISTORY_PASS_created":0,
            "R92_created":False,"GO":False,
            "execution":"NONE","real_money":"NO-GO",
            "unknown_never_pass":True}

def selftest():
    reg=json.loads(REG.read_text())
    e=reg["events"][1] # BKNG
    cik,acc,url=doc_key(e)
    require(acc=="0000950157-26-000465" and cik=="0001075531",
            "SEC_FILENAMES_ACCESSION_CANARY")
    source={"cik":int(cik),"filings":{"recent":{
        "accessionNumber":[acc],"form":["8-K"],
        "filingDate":["2026-04-03"],
        "acceptanceDateTime":["2026-04-03T11:00:00Z"]}}}
    require(match_submission(e,source,"2026-10-09")==acc,
            "FILING_PRE_ASOF_POSITIVE")
    require(check_html(e,b"<html>" + b"twenty-five-for-one split a company" * 50 + b"</html>"),
            "ORIGINAL_DOCUMENT_POSITIVE")
    red=[
      ("FOREIGN_CIK",dict(source,cik=111)),
      ("POST_ASOF",{"cik":int(cik),"filings":{"recent":{
         "accessionNumber":[acc],"form":["8-K"],
         "filingDate":["2026-10-12"],
         "acceptanceDateTime":["2026-10-12T23:00:00Z"]}}}),
      ("BAD_FORM",{"cik":int(cik),"filings":{"recent":{
         "accessionNumber":[acc],"form":["4"],
         "filingDate":["2026-04-03"],
         "acceptanceDateTime":["2026-04-03T11:00:00Z"]}}})
    ]
    for label,bad in red:
        try:match_submission(e,bad,"2026-10-09")
        except ValueError:pass
        else:raise AssertionError("UNSAFE_OFFICIAL_DOC_PASS:"+label)
    wrong=dict(e,document="https://fake.example/Archives/edgar")
    try:doc_key(wrong)
    except ValueError:pass
    else:raise AssertionError("UNOFFICIAL_ARCHIVE_ACCEPTED")
    try:check_html(e,b"<html>" + b"two-for-one split stock" * 40 + b"</html>")
    except ValueError:pass
    else:raise AssertionError("WRONG_OFFICIAL_RATIO_TEXT_ACCEPTED")
    try:check_html(e,b"<html>" + b"unrelated publication" * 30+b"</html>")
    except ValueError:pass
    else:raise AssertionError("NO_SPLIT_DOCUMENT_ACCEPTED")
    print("XRAY_SEC_12_SPLIT_DOC_PIT_SELFTEST=PASS_3_POSITIVE_6_NEGATIVE_PYTHON_O_SAFE")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:return selftest()
    require(args.out is not None,"OUTPUT_REQUIRED")
    ua=os.getenv("XRAY_SEC_USER_AGENT","")
    require(valid_operator_contact(ua),"OFFICIAL_SEC_OPERATOR_CONTACT_REQUIRED")
    last=[0.]
    def pace():
        wait=WAIT-(time.monotonic()-last[0])
        if wait>0:time.sleep(wait)
        last[0]=time.monotonic()
    def fetch_sub(cik):
        pace()
        return get_json(f"https://data.sec.gov/submissions/CIK{cik}.json",ua)
    def fetch_html(url):
        pace()
        req=urllib.request.Request(url,headers={
             "User-Agent":ua,"Accept":"text/html",
             "Accept-Encoding":"identity"})
        try:
            with urllib.request.urlopen(req,timeout=20) as resp:
                require(resp.status==200,"SEC_DOC_HTTP_NON200")
                data=resp.read(8_000_001)
        except (OSError,urllib.error.URLError,TimeoutError) as exc:
            raise ValueError("SEC_DOC_TRANSPORT") from exc
        require(len(data)<=8_000_000,"SEC_DOC_TOO_LARGE")
        return data
    document=json.loads(REG.read_text())
    result=audit(document,fetch_sub,fetch_html)
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("XRAY_SEC_12_SPLIT_DOC_RESEARCH="+str(result["SEC_document_and_acceptance_verified_count"])+"/12")
    print("XRAY_SEC_12_SPLIT_DOC_UNKNOWN="+str(result["SEC_document_or_acceptance_unknown_count"]))
    print("XRAY_SEC_12_DOC_PRIMARY=0")

if __name__=="__main__":main()
