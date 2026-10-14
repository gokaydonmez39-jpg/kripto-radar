#!/usr/bin/env python3
"""FROG D candidate-local official SEC/legal + NasdaqTrader historical halt.

Triggered only by immutable REAL SIP Deep A/B/D R1/RR watch evidence.
No automatic R92. SEC official primary documents reviewed with exact ASOF;
NasdaqTrader official historical RSS is negative-diagnostic, not a license
to assert canonical HALT_CLEAR if no matching halt row is found.
"""
from __future__ import annotations
import argparse,hashlib,json,os
from pathlib import Path
import pandas_market_calendars as mcal
import sec_official_free_mc_transport_probe as sec
from sec_free_mc_multisymbol_pit_audit import map_ciks
import build_candidate_legal_guard as legal
import price_historical_halt_probe as halt

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
FROG_SHA="b8a71c3200f38688a1c4612b88ba23a033b7f5d310cec69d79c2adcf4823e449"
def require(ok,why):
    if not ok:raise ValueError("XRAY_FROG_D_OFFICIAL_"+why)
def validate(source):
    raw=source.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==FROG_SHA,"IMMUTABLE_TRUE_FROG_DEEP")
    d=json.loads(raw)
    require(d.get("asof_et")==ASOF
            and d.get("schema")=="XRAY_20261013_LOCAL_277_DEEP_ABD_R1RR_PAGE_SHADOW_V1"
            and d.get("page")==3 and d.get("r92_registered")==0,
            "PIT_DEEP_PAGE_SOURCE")
    frog=d["evaluations"].get("FROG",{})
    f=frog.get("families",{}).get("D",{})
    require(f.get("actual_deep_trigger_confirmed") is True
            and f.get("risk_geometry_pass") is True
            and f.get("rr_basic_and_severe_pass") is True
            and f.get("technical_result")=="WATCH_EVENT_UNKNOWN_OR_BLOCKED",
            "C417_TRUE_FROG_D_TRIGGER_R1_RR")
    return d
def official4():
    cal=mcal.get_calendar("NASDAQ")
    days=[x.date().isoformat() for x in cal.valid_days(
        start_date="2026-10-01",end_date=ASOF)][-4:]
    require(len(days)==4 and days==["2026-10-08","2026-10-09","2026-10-12",ASOF],
            "OFFICIAL_LAST_FOUR_SESSIONS")
    return days
def selftest():
    d=official4()
    require(len(d)==4 and halt.source_url(ASOF).startswith("https://www.nasdaqtrader.com/rss.aspx?"),
            "OFFICIAL_RSS_URL")
    require(halt.full_session_halt_candidate({"IssueSymbol":"FROG"},"FROG",ASOF) is None,
            "INCOMPLETE_HALT_NO_FALSE_FAIL")
    print("XRAY_FROG_OFFICIAL_4DAY_SELFTEST=PASS_UNKNOWN_NEVER_CLEAR")

def run(source,out):
    require(out and not out.resolve().is_relative_to(ROOT.parent.resolve()),
            "NO_PUBLIC_SEC_RAW_DOC_EXPORT")
    validate(source)
    ua=(os.getenv("XRAY_SEC_USER_AGENT") or "").strip()
    require(sec.valid_operator_contact(ua),"SEC_OPERATOR_CONTACT")
    report={"schema":"XRAY_20261013_FROG_D_OFFICIAL_SEC_LEGAL_HALT_PIT_WITNESS_V1",
      "asof_et":ASOF,"symbol":"FROG","setup_family":"D",
      "frozen_true_sip_deep_page_sha256":FROG_SHA,
      "deep_R1RR_pass":True,"risk_geometry_pass":True,
      "nasdaq_halt_diagnostic_by_date":{},
      "nasdaq_official_last_four_days":official4(),
      "halt_confirmed_negative_count":0,
      "nasdaq_halt_clear_primary_attested":False,
      "issuer_cik_current_map_pit_not_attested":True,
      "sec_legal_review_status":"UNKNOWN_NOT_ATTEMPTED",
      "sec_issuer_class_mc_pit_status":"UNKNOWN_NOT_ATTEMPTED",
      "independent_price_close_corrections_attested":False,
      "regime_breadth_finalist_asof_attested":False,
      "full_C417_price_sec_mc_legal_event_halt_attested":False,
      "canonical_primary_promotion_count":0,"r92_registered":0,
      "iphone_delivery_receipt_attested":False,
      "canonical_mutated":False,"execution":"NONE",
      "real_money":"NO-GO","unknown_never_pass":True}
    def save():
        out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    save()
    try:
        index=sec.get_json("https://www.sec.gov/files/company_tickers_exchange.json",ua)
        routes=map_ciks(index)
        cik=routes.get("FROG")
        require(type(cik) is str and len(cik)==10,"SEC_CIK_ROUTE")
        report["sec_cik_matched"]=True
        report["sec_cik"]=cik
        facts=sec.get_json("https://data.sec.gov/api/xbrl/companyfacts/CIK"+cik+".json",ua)
        subs=sec.get_json("https://data.sec.gov/submissions/CIK"+cik+".json",ua)
        v=sec.select_shares(facts,subs,ASOF,expected_cik=cik)
        report["sec_issuer_class_mc_pit_status"]=v.get("status","UNKNOWN")
        report["sec_shares_selected_acceptance_bound"]=bool(v.get("accession_present"))
        report["sec_shares_vintage_reason"]=v.get("reason")
        save()
        try:
            ll=legal.review_symbol("FROG",cik,ASOF)
            report["sec_legal_review_status"]=ll.get("status","UNKNOWN")
            report["sec_legal_review_reason"]=ll.get("reason")
            report["sec_legal_review_filing_count"]=ll.get("reviewed_filing_count")
            report["sec_legal_review_document_count"]=len(ll.get("reviewed_primary_documents") or [])
            report["sec_legal_hard_flags"]=ll.get("hard_legal_flags") or []
            report["sec_legal_risk_flags"]=ll.get("risk_flags") or []
            report["sec_legal_missing_documents_count"]=len(ll.get("document_failures") or [])
        except Exception as error:
            report["sec_legal_review_status"]="UNKNOWN_OFFICIAL_SOURCE_FAILURE"
            report["sec_legal_review_reason"]=type(error).__name__
    except Exception as error:
        report["sec_legal_review_status"]="UNKNOWN_OFFICIAL_SEC_SOURCE"
        report["sec_issuer_class_mc_pit_status"]="UNKNOWN_OFFICIAL_SEC_SOURCE"
        report["sec_source_error_type"]=type(error).__name__
    save()
    for date in report["nasdaq_official_last_four_days"]:
        try:
            rows,meta=halt.fetch_rows(date)
            sym=[x for x in rows if str(x.get("IssueSymbol") or "").strip().upper()=="FROG"]
            confirmed=[halt.full_session_halt_candidate(x,"FROG",date)
                       for x in sym]
            proof=[x for x in confirmed if x]
            report["nasdaq_halt_diagnostic_by_date"][date]={
                "fetch_status":"OFFICIAL_RSS_HTTP_"+str(meta["http_status"]),
                "source_url":halt.source_url(date),
                "official_published_total_rows":len(rows),
                "symbol_halt_rows":len(sym),
                "full_session_halt_proven_by_validator":len(proof),
                "no_match_does_not_prove_complete_halt_clear":True}
            report["halt_confirmed_negative_count"]+=len(proof)
        except Exception as error:
            report["nasdaq_halt_diagnostic_by_date"][date]={
                "fetch_status":"UNKNOWN_OFFICIAL_RSS_SOURCE",
                "error_type":type(error).__name__}
        save()
    require(len(report["nasdaq_halt_diagnostic_by_date"])==4,"FOUR_DAYS_VISITED")
    print("XRAY_FROG_OFFICIAL_SEC_LEGAL_STATUS="+report["sec_legal_review_status"])
    print("XRAY_FROG_OFFICIAL_SEC_SHARES_STATUS="+report["sec_issuer_class_mc_pit_status"])
    print("XRAY_FROG_NASDAQ_HALT_SOURCE_ROWS="+json.dumps(report["nasdaq_halt_diagnostic_by_date"],sort_keys=True))
    print("XRAY_FROG_WATCH_REAL_R1RR_NO_FALSE_R92=PASS")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--deep",type=Path)
    a.add_argument("--out",type=Path)
    x=a.parse_args()
    if x.selftest:selftest();return
    require(x.deep and x.out,"CLI")
    run(x.deep,x.out)
if __name__=="__main__":main()
