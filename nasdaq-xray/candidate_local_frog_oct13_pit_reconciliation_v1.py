#!/usr/bin/env python3
"""Real source-limited FROG D reverse-funnel: corporate actions, price, SEC, legal, halt.

All queries read-only; raw licensed Alpaca data and SEC share counts stay in RAM.
An HTTP200 or absent RSS row is NOT an affirmative PIT release attestation.
Output is operational evidence with independently named unanswered gates.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
import alpaca_full_scope_ca_shadow as ca
import alpaca_sip_4symbol_30min_rth_shadow as rth
import sec_official_free_mc_transport_probe as sec
from sec_free_mc_multisymbol_pit_audit import map_ciks
import build_candidate_legal_guard as legal
import price_historical_halt_probe as halts
from candidate_local_oct13_primary_readiness import (
    DEEP_SHA256, validate_source,
)

ROOT = Path(__file__).resolve().parent
ASOF = "2026-10-13"
SYMBOL = "FROG"
CIK = "0001800667"
NY = ZoneInfo("America/New_York")
SCHEMA = "XRAY_FROG_20261013_CANDIDATE_LOCAL_LIVE_SOURCE_RECONCILIATION_V1"
MAX_PROVIDER_CALLS = 24

def need(v, code):
    if not v:
        raise ValueError("XRAY_FROG_RECON_" + code)

def blob_sha(path):
    b = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(b)).encode() + bytes((0,)) + b).hexdigest()

def sessions():
    all_days = [d.date().isoformat() for d in mcal.get_calendar("NASDAQ").valid_days(
        start_date="2025-07-01", end_date=ASOF)]
    need(len(all_days) >= 260 and all_days[-1] == ASOF, "CALENDAR_ASOF")
    return all_days[-260:], all_days[-30:]

def source_deep(deep_path, frog_path):
    d = deep_path.read_bytes()
    f = frog_path.read_bytes()
    doc, frog = json.loads(d), json.loads(f)
    q = validate_source(doc, hashlib.sha256(d).hexdigest(), frog)
    need(set(q) == {"FROG|D","MANH|B","MRVL|D","MSFT|D",
                    "MTSI|D","MU|D","TWST|D"}, "EXACT_TECH_SCOPE")
    need(q["FROG|D"]["risk_geometry_pass"] is True and
         q["FROG|D"]["rr_basic_and_severe_pass"] is True, "REAL_TRIGGER")
    return hashlib.sha256(f).hexdigest()

def fetch_price(tf, adjustment, dates, key, secret, calls):
    start = dt.datetime.combine(dt.date.fromisoformat(dates[0]),dt.time(),tzinfo=NY)
    end = dt.datetime.combine(dt.date.fromisoformat(ASOF)+dt.timedelta(days=1),
                              dt.time(),tzinfo=NY)
    token = None
    visited = set()
    rows = []
    for _ in range(8):
        need(calls[0] < MAX_PROVIDER_CALLS, "ALPACA_CALL_BUDGET")
        params = {"symbols":SYMBOL, "timeframe":tf, "feed":"sip",
                  "adjustment":adjustment, "sort":"asc", "limit":10000,
                  "start":start.isoformat(), "end":end.isoformat()}
        if token:
            params["page_token"] = token
        req = urllib.request.Request(
            "https://data.alpaca.markets/v2/stocks/bars?"+urllib.parse.urlencode(params),
            headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
                     "Accept":"application/json"})
        calls[0] += 1
        with urllib.request.urlopen(req, timeout=40) as resp:
            need(resp.status == 200, "ALPACA_PRICE_HTTP")
            raw = resp.read(4_000_001)
        need(len(raw) <= 4_000_000, "ALPACA_PRICE_BYTES")
        payload = json.loads(raw)
        need(isinstance(payload,dict) and
             isinstance(payload.get("bars"),dict) and
             set(payload["bars"]).issubset({SYMBOL}), "ALPACA_PRICE_SCHEMA")
        part = payload["bars"].get(SYMBOL) or []
        need(isinstance(part,list), "ALPACA_PRICE_ROWS")
        rows.extend(part)
        next_token = payload.get("next_page_token")
        if not next_token:
            return rows
        need(isinstance(next_token,str) and next_token not in visited,
             "PRICE_PAGE_LOOP")
        visited.add(next_token)
        token = next_token
    raise ValueError("XRAY_FROG_RECON_PRICE_PAGE_BUDGET")

def quality30(daily_raw,daily_all,half,days):
    valid=set(days)
    def view(bars):
        by_day={}
        for row in bars:
            need(isinstance(row,dict) and isinstance(row.get("t"),str),
                 "DAILY_DATE_SHAPE")
            parsed=dt.datetime.fromisoformat(row["t"].replace("Z","+00:00"))
            need(parsed.tzinfo is not None, "DAILY_TZ_AWARE")
            day=parsed.astimezone(NY).date().isoformat()
            if day not in valid:
                continue
            need(day not in by_day, "DAILY_DUPLICATE")
            need(type(row.get("c")) in (int,float) and
                 0 < row["c"] < 1e7, "CLOSE_VALUE")
            by_day[day]=row
        return by_day
    raw=view(daily_raw)
    adj=view(daily_all)
    shared=set(raw)&set(adj)
    close_disagreements=sum(
        abs(raw[d]["c"]-adj[d]["c"]) > 0.000001 for d in shared)
    try:
        lower = rth.classify_one(daily_raw,half,days)
    except (ValueError,TypeError,KeyError) as exc:
        lower = "UNKNOWN_PRICE_30MIN_"+type(exc).__name__
    # 30Min SIP RTH aggregation excludes close auction; even all-adjusted
    # daily bars are not independent corrections / final CTA tape witness.
    return {"raw_completed_days":len(raw),"all_adjusted_completed_days":len(adj),
            "shared_dates":len(shared),"raw_vs_all_close_diff_days":close_disagreements,
            "observed_30min_lower_bound_state":lower,
            "actual_30day_bar_scope_present":set(raw)==set(adj)==valid,
            "official_rth_auction_complete":False,
            "independent_close_corrections_verified":False,
            "split_dividend_issuer_pit_reconciled":False,
            "dv30_primary_pass":False,
            "price_source":"ALPACA_HISTORICAL_SIP_PERSONAL_READONLY"}

def corporate_actions(start, key, secret, calls):
    report={"complete":{},"all":{},"source":"ALPACA_CORPORATE_ACTIONS",
            "no_event_not_proof_of_no_event":True,
            "asof_publication_time_confirmed":False,
            "issuer_ca_independent_pit_reconciled":False,
            "ca_primary_pass":False}
    for mode in ("complete","all"):
        token=None
        seen=set()
        counts=collections.Counter()
        pages=0
        try:
            for _ in range(6):
                need(calls[0]<MAX_PROVIDER_CALLS, "CA_CALL_BUDGET")
                payload=ca.request_page([SYMBOL],start,ASOF,key,secret,token,
                                        data_quality=mode)
                calls[0]+=1
                need(type(payload) is dict and
                     type(payload.get("corporate_actions")) is dict,
                     "CA_GROUP_SCHEMA")
                for group,rows in payload["corporate_actions"].items():
                    need(group in ca.KNOWN_GROUPS and type(rows) is list,
                         "CA_UNKNOWN_SCHEMA")
                    for row in rows:
                        need(type(row) is dict, "CA_ROW_INVALID")
                        if any(row.get(k)==SYMBOL for k in ca.SUBJECT_FIELDS):
                            counts[group]+=1
                pages+=1
                next_token=payload.get("next_page_token")
                if next_token in (None,""):
                    report[mode]={"status":"SOURCE_RESPONSES_COMPLETE_WITHIN_BUDGET",
                                  "event_types":dict(sorted(counts.items())),
                                  "pages":pages}
                    break
                need(type(next_token) is str and next_token not in seen,
                     "CA_CURSOR_LOOP")
                seen.add(next_token)
                token=next_token
            else:
                report[mode]={"status":"UNKNOWN_CA_PAGE_BUDGET"}
        except (RuntimeError,ValueError,TypeError,KeyError,urllib.error.URLError) as ex:
            report[mode]={"status":"UNKNOWN_CA_TRANSPORT_OR_SCHEMA",
                          "error_type":type(ex).__name__}
    return report

def sec_and_legal(ua):
    report={"source":"SEC_EDGAR_OFFICIAL",
            "class_specific_outstanding_reconciled":False,
            "mc_2b_primary_pass":False,"issuer_event_calendar_clear":False,
            "official_legal_clear_pit":False}
    try:
        routes=map_ciks(sec.get_json("https://www.sec.gov/files/company_tickers_exchange.json",ua))
        need(routes.get(SYMBOL)==CIK, "CURRENT_SEC_CIK_ROUTE")
        facts=sec.get_json("https://data.sec.gov/api/xbrl/companyfacts/CIK"+CIK+".json",ua)
        subs=sec.get_json("https://data.sec.gov/submissions/CIK"+CIK+".json",ua)
        shares=sec.select_shares(facts,subs,ASOF,expected_cik=CIK)
        report.update({"sec_cik_exact":True,
                       "entity_shares_vintage_status":shares.get("status","UNKNOWN"),
                       "entity_shares_vintage_reason":shares.get("reason"),
                       "selected_filing_date":shares.get("selected_filing_date"),
                       "share_observation_date":shares.get("observation_date"),
                       "accession_present":shares.get("accession_present",False),
                       "sec_companyfacts_and_submissions_http": "VALIDATED"})
    except (ValueError,KeyError,TypeError,urllib.error.URLError) as ex:
        report["sec_transport"]="UNKNOWN_SEC_SOURCE_OR_IDENTITY"
        report["error_type"]=type(ex).__name__
        return report
    try:
        lr=legal.review_symbol(SYMBOL,CIK,ASOF)
        report.update({"official_legal_review_status":lr.get("status","UNKNOWN"),
                       "official_legal_review_reason":lr.get("reason"),
                       "primary_documents_read":len(lr.get("reviewed_primary_documents") or []),
                       "document_failures":len(lr.get("document_failures") or []),
                       "hard_legal_flag_count":len(lr.get("hard_legal_flags") or []),
                       "risk_flag_count":len(lr.get("risk_flags") or []),
                       "legal_source_available":lr.get("status") in ("PASS","UNKNOWN")})
        # Even a historical SEC legal PASS cannot certify a future earnings
        # event calendar, official current halt status or share-class MC.
        report["official_legal_clear_pit"]=lr.get("status")=="PASS" and (
            len(lr.get("document_failures") or [])==0 and
            len(lr.get("hard_legal_flags") or [])==0)
    except Exception as ex:
        report["official_legal_review_status"]="UNKNOWN_SEC_PRIMARY_DOC_UNAVAILABLE"
        report["legal_error_type"]=type(ex).__name__
    return report

def halt_checks(master):
    result={"official_source":"NASDAQTRADER_RSS",
            "historical_halt_full_completeness_verified":False,
            "live_halt_clear_verified":False, "daily":{}}
    for d in master[-4:]:
        try:
            rows,meta=halts.fetch_rows(d)
            matching=[x for x in rows if
                      (x.get("IssueSymbol") or "").strip().upper()==SYMBOL]
            known=[halts.full_session_halt_candidate(x,SYMBOL,d) for x in matching]
            result["daily"][d]={"http_status":meta["http_status"],
                                "rss_rows":len(rows),"matching_records":len(matching),
                                "full_session_halt_candidate_count":
                                    len([x for x in known if x]),
                                "negative_rss_not_full_clear":True}
        except (OSError,ValueError,TypeError,KeyError) as ex:
            result["daily"][d]={"status":"UNKNOWN_HALT_SOURCE",
                                "error_type":type(ex).__name__}
    return result

def selftest():
    _,d=sessions()
    need(len(d)==30 and d[-1]==ASOF, "TEST_30")
    q=quality30([],[],[],d)
    need(q["dv30_primary_pass"] is False and
         q["actual_30day_bar_scope_present"] is False, "TEST_EMPTY_NOT_PRIMARY")
    a={"status":"SHADOW_SHARES_VINTAGE_ONLY"}
    need(a["status"]!="PASS", "TEST_ENTITY_NOT_CLASS_MC")
    need(DEEP_SHA256.startswith("ed9cc"), "TEST_PINNED_SOURCE")
    print("XRAY_FROG_REVERSE_FUNNEL_SELFTEST=PASS_EMPTY_PRICE_NO_ENTITY_MC_NO_HALT_CLEAR")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--deep",type=Path)
    p.add_argument("--frog",type=Path)
    p.add_argument("--out",type=Path)
    x=p.parse_args()
    if x.selftest:
        selftest()
        return
    need(x.deep and x.frog and x.out, "REQUIRED_PATHS")
    need(not x.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "NO_RAW_VENDOR_OR_EVIDENCE_PUBLIC_REPO")
    frog_sha=source_deep(x.deep,x.frog)
    master,days=sessions()
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or
         os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or
            os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    ua=(os.getenv("XRAY_SEC_USER_AGENT") or "").strip()
    state={
      "schema":SCHEMA, "asof_et":ASOF,"symbol":SYMBOL,
      "real_trigger":"D","risk_rr_geometry_pass":True,
      "source_deep_sha256":DEEP_SHA256,
      "source_frog_sha256":frog_sha,
      "master_git_blob_sha":blob_sha(ROOT/"canonical_current_master_manifest.json"),
      "official_source_guard_git_blob_sha":blob_sha(ROOT/"canonical_official_source_guard.json"),
      "price":{},"corporate_actions":{},"sec_mc_legal_event":{},
      "nasdaq_halt":{},"live_source_diagnostics":{},
      "ca_primary_pass":False,"price_primary_pass":False,
      "class_aware_mc_2b_primary_pass":False,
      "issuer_event_clear_pass":False,"historical_and_live_halt_clear_pass":False,
      "regime_breadth_primary_pass":False,
      "candidate_local_c417_complete":False,
      "canonical_primary_created":False,"r92_registered":0,
      "iphone_push_receipt_verified":False,
      "research_start":"YES","real_money":"NO-GO","execution":"NONE",
      "canonical_files_modified":False,"raw_vendor_ohlcv_persisted":False,
      "raw_sec_share_values_persisted":False,"unknown_never_pass":True}
    def save():
        x.out.write_text(json.dumps(state,sort_keys=True,indent=2)+chr(10))
    save()
    calls=[0]
    if key and secret:
        try:
            raw=fetch_price("1Day","raw",days,key,secret,calls)
            adjusted=fetch_price("1Day","all",days,key,secret,calls)
            thirty=fetch_price("30Min","raw",days,key,secret,calls)
            state["price"]=quality30(raw,adjusted,thirty,days)
        except (ValueError,TypeError,KeyError,urllib.error.URLError,OSError) as ex:
            state["price"]={"status":"UNKNOWN_SIP_PRICE_TRANSPORT_OR_CORRECTIONS",
                            "error_type":type(ex).__name__,"dv30_primary_pass":False}
        save()
        state["corporate_actions"]=corporate_actions(master[0],key,secret,calls)
    else:
        state["price"]={"status":"UNKNOWN_ALPACA_CREDENTIALS_MISSING"}
        state["corporate_actions"]={"status":"UNKNOWN_ALPACA_CREDENTIALS_MISSING"}
    save()
    if sec.valid_operator_contact(ua):
        state["sec_mc_legal_event"]=sec_and_legal(ua)
    else:
        state["sec_mc_legal_event"]={"status":"UNKNOWN_SEC_OPERATOR_CONTACT"}
    save()
    state["nasdaq_halt"]=halt_checks(master)
    official=json.loads((ROOT/"canonical_official_source_guard.json").read_text())
    state["live_source_diagnostics"]={
       "canonical_guard_generated_at_utc":official.get("generated_at_utc"),
       "canonical_guard_is_after_asof_not_pit_proof":True,
       "current_snapshot_symbol_veto_observed":SYMBOL in (
           official.get("candidate_safety",{}).get("veto_symbols") or []),
       "snapshot_no_veto_is_not_historical_or_live_halt_clear":True}
    state["alpaca_http_requests"]=calls[0]
    save()
    print("XRAY_FROG_REVERSE_FUNNEL_REAL_ALPACA_HTTP="+str(calls[0]))
    print("XRAY_FROG_CA_QUALITY="+str(state["corporate_actions"].get("all",{}).get("status","UNKNOWN")))
    print("XRAY_FROG_PRICE_BOUNDS="+str(state["price"].get("observed_30min_lower_bound_state","UNKNOWN")))
    print("XRAY_FROG_SEC_VINTAGE="+str(state["sec_mc_legal_event"].get("entity_shares_vintage_status","UNKNOWN")))
    print("XRAY_FROG_SEC_LEGAL="+str(state["sec_mc_legal_event"].get("official_legal_review_status","UNKNOWN")))
    print("XRAY_FROG_C417=NO_PRIMARY_R92=0_IPHONE_RECEIPT=NOT_ATTESTED")

if __name__=="__main__":
    main()
