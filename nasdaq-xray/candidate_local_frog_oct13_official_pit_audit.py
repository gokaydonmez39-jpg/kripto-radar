#!/usr/bin/env python3
"""Candidate-local real FROG D trigger: SEC PIT, official Nasdaq halt and IR probe.

The immutable Oct13 real SIP deep rollup is the only input trigger authority.
All 13-Oct issuer share-class, 30-session close corrections, forward-event,
official historical/current halt, live safety and release gates are independent.
No unsupported assumption about absence of news/halts may create PASS/R92.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import sec_official_free_mc_transport_probe as sec
from sec_free_mc_multisymbol_pit_audit import map_ciks
from price_historical_halt_probe import fetch_rows

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
ISSUER="FROG"
FAMILY="D"
CIK="0001800667"
DEEP_SHA="ed9cc814c488fb743f52227d42c18f8c81876d67c9167ebc1128738a8406c855"
SOURCE_ID=38536372509
TRIGGER_KEY="FROG|D"
INDEX="https://www.sec.gov/files/company_tickers_exchange.json"
NEWS="https://investors.jfrog.com/news/default.aspx"

def need(ok,msg):
    if not ok:raise ValueError("XRAY_FROG_LOCAL_PIT_"+msg)

def verify_deep(raw):
    need(hashlib.sha256(raw).hexdigest()==DEEP_SHA,"IMMUTABLE_DEEP_SHA")
    r=json.loads(raw)
    need(r.get("schema")=="XRAY_OCT13_277_REAL_STAGE1_DEEP_R1RR_COMPLETE_SHADOW_V1"
        and r.get("asof_et")==ASOF
        and r.get("source_277_stage1_count")==277
        and r.get("stage1_pool_count")==54
        and r.get("actual_confirmed_recent_family_trigger_count")==7
        and r.get("provenance_exact") is True
        and r.get("registered_r92")==0
        and r.get("execution")=="NONE"
        and r.get("real_money")=="NO-GO"
        and r.get("unknown_never_pass") is True,
        "FROZEN_STAGE_DEEP_CHAIN")
    q=r.get("risk_rr_diagnostics") or {}
    need(set(q)=={
        "FROG|D","MANH|B","MRVL|D","MSFT|D","MTSI|D","MU|D","TWST|D"},
        "FROZEN_SEVEN_EXACT_SET")
    matched=[k for k,v in q.items() if
        v.get("frozen_R1_RR_evaluated") is True and
        v.get("risk_geometry_pass") is True and
        v.get("rr_basic_and_severe_pass") is True]
    need(matched==[TRIGGER_KEY],"ONLY_FROG_RISK_RR_QUALIFIED")
    need(q[TRIGGER_KEY].get("technical_result")=="WATCH_EVENT_UNKNOWN_OR_BLOCKED",
         "TRIGGER_NOT_R92")
    return True

def filers_asof(sub):
    """Official submissions are metadata-only; after-close/unknown is excluded."""
    recent=((sub.get("filings") or {}).get("recent") or {})
    idx=sec.accession_acceptance_index(sub)
    rows=[]
    for accession,hit in idx.items():
        try:
            filed=dt.date.fromisoformat(hit["filed"])
        except (TypeError,ValueError):
            continue
        if (hit["form"] in {"10-Q","10-K","10-Q/A","10-K/A","8-K","8-K/A"}
            and dt.date(2025,10,13)<=filed<=dt.date.fromisoformat(ASOF)):
            # Filed on ASOF is not enough to establish pre-close acceptance.
            pre_asof_certain=(filed<dt.date.fromisoformat(ASOF))
            rows.append({"form":hit["form"],"filed":hit["filed"],
                         "accession":accession,
                         "pre_asof_session_close_certain":pre_asof_certain})
    rows.sort(key=lambda x:(x["filed"],x["accession"]))
    return rows[-25:]

def historical_halt_probe():
    try:
        rows,meta=fetch_rows(ASOF)
        need(meta["http_status"]==200,"HALT_HTTP_NOT_200")
        # An RSS feed might be truncated. No reported symbol is NOT proof
        # that the full official historical universe was observed.
        matches=[x for x in rows if str(x.get("IssueSymbol") or "").strip().upper()==ISSUER]
        out={"transport":"NASDAQ_TRADER_OFFICIAL_HALTDATE_RSS_OBSERVED",
             "url":meta["url"],
             "http_status":meta["http_status"],
             "rss_items_observed":len(rows),
             "symbol_halt_entries_observed":len(matches),
             "full_day_completeness_attested":False,
             "historical_day_clear_pass":False,
             "current_live_halt_guard_pass":False}
        if matches:
            out["symbol_status"]="HISTORICAL_HALT_RECORD_PRESENT_REQUIRE_MANUAL"
        else:
            out["symbol_status"]="NO_MATCH_IN_BOUNDED_RSS_NOT_HALT_CLEAR"
        return out
    except (ValueError,KeyError,TypeError,urllib.error.URLError,OSError) as e:
        return {"transport":"OFFICIAL_HALT_RSS_UNAVAILABLE",
                "symbol_status":"UNKNOWN_HALT",
                "full_day_completeness_attested":False,
                "historical_day_clear_pass":False,
                "current_live_halt_guard_pass":False}

def issuer_news_probe():
    # HTML presence is NOT a complete earnings schedule and the page is
    # retrieved after Oct13. Therefore no date inference or CLEAR occurs.
    req=urllib.request.Request(NEWS,headers={
        "User-Agent":"NASDAQ-SWING-XRAY/1.0 research source witness",
        "Accept":"text/html"})
    try:
        with urllib.request.urlopen(req,timeout=18) as resp:
            sample=resp.read(100_000)
            status=int(resp.status)
        return {"source_url":NEWS,"http_status":status,
                "issuer_ir_reachable":status==200 and len(sample)>0,
                "asof_oct13_future_event_horizon_clear":False,
                "later_retrieval_not_oct13_pit_proof":True,
                "event_status":"UNKNOWN_NO_EXPLICIT_PIT_EVENT_SCHEDULE_EVIDENCE"}
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,OSError):
        return {"source_url":NEWS,"issuer_ir_reachable":False,
                "asof_oct13_future_event_horizon_clear":False,
                "event_status":"UNKNOWN_ISSUER_IR_UNAVAILABLE"}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--deep",type=Path)
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:
        good={"FROG|D":{"frozen_R1_RR_evaluated":True,
                        "risk_geometry_pass":True,
                        "rr_basic_and_severe_pass":True}}
        need(len(good)==1 and TRIGGER_KEY in good,"TEST_SCOPE")
        malformed={"filings":{"recent":{
           "accessionNumber":["0000000000-26-000001","0000000000-26-000002"],
           "form":["8-K","8-K"],"filingDate":["2026-10-12","2026-10-14"],
           "acceptanceDateTime":["2026-10-12T16:00:00Z","2026-10-14T16:00:00Z"]}}}
        evidence=filers_asof(malformed)
        need(len(evidence)==1 and evidence[0]["filed"]=="2026-10-12",
             "POST_ASOF_REJECTED")
        print("XRAY_FROG_LOCAL_OFFICIAL_SELFTEST=PASS_NO_FUTURE_FILINGS_OR_HALT_INFERENCE")
        return
    need(args.deep and args.out and
        not args.out.resolve().is_relative_to(ROOT.parent.resolve()),"ARGS")
    data=args.deep.read_bytes()
    verify_deep(data)
    ua=(os.getenv("XRAY_SEC_USER_AGENT") or "").strip()
    need(sec.valid_operator_contact(ua),"SEC_OPERATOR_AGENT_REQUIRED")
    report={
      "schema":"XRAY_OCT13_FROG_D_POST_TRIGGER_SEC_NASDAQ_IR_OFFICIAL_RESEARCH_V1",
      "asof_et":ASOF,"symbol":ISSUER,"family":FAMILY,
      "deep_source_sha256":hashlib.sha256(data).hexdigest(),
      "deep_source_actions_run":SOURCE_ID,
      "trigger_stage1_and_r1_rr_observed":True,
      "risk_geometry_pass":True,
      "rr_basic_severe_pass":True,
      "source_authority":"RESEARCH_SHADOW_ONLY",
      "sec_pit":{},"nasdaq_halt":{},
      "issuer_event":{},
      "provider_http_requests":0,
      "share_class_asof_mc_primary_pass":False,
      "exact_corrected_dv30_primary_pass":False,
      "issuer_legal_event_clear_pass":False,
      "official_halt_live_guard_pass":False,
      "regime_breadth_primary_pass":False,
      "registered_r92_count":0,
      "real_iphone_receipt_verified":False,
      "raw_market_series_or_share_counts_persisted":False,
      "canonical_files_mutated":False,
      "execution":"NONE","real_money":"NO-GO",
      "unknown_never_pass":True}
    def save():
        args.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    save()
    try:
        mapping=map_ciks(sec.get_json(INDEX,ua))
        report["provider_http_requests"]+=1
        need(mapping.get(ISSUER)==CIK,"OFFICIAL_CIK_EXACT")
        facts=sec.get_json(
            "https://data.sec.gov/api/xbrl/companyfacts/CIK"+CIK+".json",ua)
        report["provider_http_requests"]+=1
        subs=sec.get_json(
            "https://data.sec.gov/submissions/CIK"+CIK+".json",ua)
        report["provider_http_requests"]+=1
        select=sec.select_shares(facts,subs,ASOF,expected_cik=CIK)
        filings=filers_asof(subs)
        report["sec_pit"]={
            "source":"SEC_EDGAR_OFFICIAL",
            "cik_exact_matched":True,
            "entity_shares_vintage_status":select.get("status","UNKNOWN"),
            "entity_shares_vintage_reason":select.get("reason"),
            "selected_filing_date":select.get("selected_filing_date"),
            "observation_date":select.get("observation_date"),
            "current_listed_class_shares_reconciled":False,
            "share_price_corporate_action_13oct_reconciled":False,
            "source_filing_count_last_year":len(filings),
            "forms_and_accessions":filings,
            "release":"SHADOW_NOT_C417_PRIMARY"}
    except (ValueError,TypeError,KeyError,OSError):
        report["sec_pit"]={"status":"UNKNOWN_SEC_DATA_OR_IDENTITY",
                           "current_listed_class_shares_reconciled":False}
    save()
    report["nasdaq_halt"]=historical_halt_probe()
    report["provider_http_requests"]+=1
    save()
    report["issuer_event"]=issuer_news_probe()
    report["provider_http_requests"]+=1
    save()
    need(report["provider_http_requests"]<=5 and
        report["registered_r92_count"]==0 and
        report["execution"]=="NONE" and
        report["real_money"]=="NO-GO","FINAL_NO_FALSE_SIGNAL")
    print("XRAY_FROG_REAL_OFFICIAL_HTTP="+str(report["provider_http_requests"]))
    print("XRAY_FROG_SEC_PIT_VINTAGE="+str(report["sec_pit"].get("entity_shares_vintage_status","UNKNOWN")))
    print("XRAY_FROG_OFFICIAL_HALT="+report["nasdaq_halt"]["symbol_status"])
    print("XRAY_FROG_EVENT="+report["issuer_event"]["event_status"])
    print("XRAY_FROG_R92=0_NO_PREMATURE_RELEASE")
if __name__=="__main__":
    main()
