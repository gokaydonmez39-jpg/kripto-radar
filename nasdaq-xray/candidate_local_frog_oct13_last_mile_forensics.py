#!/usr/bin/env python3
"""FROG actual Oct13 last-mile official SEC filings, issuer events, Nasdaq halt and SIP auction samples.

Research-only SHA-bound validation. Proves what was observed, not universal absence.
Never writes canonical, lifecycle, delivery; never creates R92 or phones.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
import sec_official_free_mc_transport_probe as sec
import price_historical_halt_probe as halt
import build_candidate_legal_guard as legal
from candidate_local_frog_oct13_sec_cover_mc_class_v1 import URL as COVER_URL
from candidate_local_oct13_primary_readiness import DEEP_SHA256, validate_source
from alpaca_rth_minute_integrity_shadow import official_window

HERE=Path(__file__).resolve().parent
SCHEMA="XRAY_FROG_OCT13_LAST_MILE_SEC_FORM4_CA_EVENT_HALT_TRADE_SHADOW_V1"
ASOF="2026-10-13"
START="2026-08-07"
CIK="0001800667"
SYMBOL="FROG"
SEC_TYPES={"8-K","8-K/A","6-K","10-K","10-Q","S-3","S-3/A","424B2",
           "424B3","424B4","424B5","424B7","4","4/A"}
IR_NEWS="https://investors.jfrog.com/news/"
IR_EVENTS="https://investors.jfrog.com/events-and-presentations/"
NY=ZoneInfo("America/New_York")

def need(test,name):
    if not test:raise ValueError("FROG_LAST_MILE_"+name)

def sha(buf):return hashlib.sha256(buf).hexdigest()

def load_sources(deep_path,frog_path):
    deep_bytes=deep_path.read_bytes()
    official=frog_path.read_bytes()
    deep=json.loads(deep_bytes)
    witness=json.loads(official)
    validate_source(deep,sha(deep_bytes),witness)
    need(witness.get("deep_source_sha256")==DEEP_SHA256,"DEEP_SOURCE_BINDING")
    return {"deep_json_sha256":sha(deep_bytes),"frog_official_json_sha256":sha(official)}

def sessions():
    days=[x.date().isoformat() for x in mcal.get_calendar("NASDAQ").valid_days(
         start_date="2026-08-20",end_date="2026-10-31")]
    need(ASOF in days,"ASOF_OFFICIAL_SESSION")
    before=days[:days.index(ASOF)+1]
    future=days[days.index(ASOF)+1:days.index(ASOF)+9]
    need(len(before)>=30 and len(future)==8,"OFFICIAL_30_AND_EIGHT")
    return before[-30:],future

def safe_filings(sub):
    recent=((sub.get("filings") or {}).get("recent") or {})
    idx=sec.accession_acceptance_index(sub)
    pdocs=recent.get("primaryDocument") or []
    accession=recent.get("accessionNumber") or []
    need(len(pdocs)==len(accession),"SEC_DOC_ROW_LENGTH")
    names={k:v for k,v in zip(accession,pdocs)}
    files=[]
    for acc,record in idx.items():
        fd=record.get("filed")
        if not isinstance(fd,str) or not START<=fd<=ASOF:
            continue
        form=str(record.get("form") or "").upper()
        doc=names.get(acc)
        files.append({"form":form,"filed":fd,"accession":acc,
                      "primary_doc_present":bool(doc),
                      "primary_doc":doc or None})
    files.sort(key=lambda z:(z["filed"],z["accession"]))
    oldest=min((v.get("filed") or "9999" for v in idx.values()),default="9999")
    complete_oldest=oldest<=START
    return files,complete_oldest

def sec_forensics(useragent):
    state={"status":"UNKNOWN_SEC_NOT_OBSERVED","inventory_pit_complete":False,
      "all_form4_issuer_and_owner_filings_complete":False,
      "current_class_shares_reconciled":False,
      "absence_of_80pct_change_proved":False,
      "corporate_actions_independent_pit_pass":False,
      "asof_mc_ge_2b_primary_pass":False,"primary_documents_verified":0}
    try:
        need(sec.valid_operator_contact(useragent),"SEC_USER_AGENT")
        sub=sec.get_json("https://data.sec.gov/submissions/CIK"+CIK+".json",useragent)
        need(str(sub.get("cik") or "").lstrip("0")==CIK.lstrip("0"),"CIK")
        records,complete=safe_filings(sub)
        count=collections.Counter(x["form"] for x in records)
        tracked=[x for x in records if x["form"] in SEC_TYPES or x["form"].startswith("424B")]
        after_asof_unsafe=sum(1 for x in tracked if x["filed"]==ASOF)
        state.update({"status":"OFFICIAL_SUBMISSIONS_READ",
          "all_issuer_filings_in_asof_interval":len(records),
          "tracked_issuer_filings":len(tracked),
          "tracked_form_counts":dict(sorted(count.items())),
          "filing_dates":[{"form":x["form"],"filed":x["filed"],
                           "accession":x["accession"]} for x in tracked],
          "submissions_recent_covers_interval":complete,
          "asof_date_filings_acceptance_clock_review_required":after_asof_unsafe})
        # Current issuer submissions do not exhaust individual owner-CIK Form 4;
        # and Form 4 owner disposition does not change issuer shares outstanding.
        # Primary SEC filings can nevertheless expose hard CA or issuance leads.
        targets=[x for x in tracked if x["form"] not in {"4","4/A"}]
        reviews=[]
        for row in targets[:12]:
            doc=row["primary_doc"]
            if not doc or not isinstance(doc,str) or ".." in doc or "/" in doc:
                reviews.append({"accession":row["accession"],"reviewed":False})
                continue
            url=("https://www.sec.gov/Archives/edgar/data/"+
                 str(int(CIK))+"/"+row["accession"].replace("-","")+"/"+doc)
            try:
                raw=legal._fetch(url,limit=4_000_000,retries=1)
                words=legal._clean_html(raw)
                leads=[token for token in (
                    "stock split","reverse share split","repurchase",
                    "share issuance","ordinary shares","at-the-market",
                    "public offering","dividend","equity incentive")
                    if token in words]
                reviews.append({"accession":row["accession"],"reviewed":True,
                                "source_sha256":sha(raw),
                                "corporate_action_phrase_leads":leads})
            except Exception as e:
                reviews.append({"accession":row["accession"],"reviewed":False,
                                "error_type":type(e).__name__})
        state["primary_documents_verified"]=sum(x["reviewed"] for x in reviews)
        state["primary_documents_in_scope"]=len(targets)
        state["bounded_primary_document_review"]=reviews
        state["status"]="OFFICIAL_INVENTORY_AND_BOUNDED_PRIMARY_DOCS_NOT_PIT_ROLLFORWARD"
    except (ValueError,KeyError,TypeError,urllib.error.URLError,OSError) as e:
        state["status"]="UNKNOWN_SEC_INVENTORY_OR_TRANSPORT"
        state["error_type"]=type(e).__name__
    return state

def issuer_ir():
    result={"source":"ISSUER_INVESTOR_RELATIONS",
      "status":"UNKNOWN_IR_SOURCE","eight_day_event_calendar_clear":False,
      "absence_of_published_event_is_not_positive_confirmation":True,"pages":{}}
    for tag,url in (("issuer_news",IR_NEWS),("issuer_events",IR_EVENTS)):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"NASDAQ-SWING-XRAY/1.0 source research",
                                                     "Accept":"text/html"})
            with urllib.request.urlopen(req,timeout=20) as resp:
                body=resp.read(400_001)
                need(resp.status==200 and 0<len(body)<=400_000,"IR_HTTP_SIZE")
            txt=body.decode("utf-8","replace").lower()
            result["pages"][tag]={"http_200":True,"body_sha256":sha(body),
               "mentions_third_quarter":("third quarter" in txt or "q3" in txt),
               "mentions_2026":("2026" in txt),
               "calendar_exact_eight_session_completeness_attested":False}
        except (ValueError,urllib.error.URLError,OSError,TimeoutError) as e:
            result["pages"][tag]={"status":"UNKNOWN_IR_HTTP","error_type":type(e).__name__}
    result["status"]="ISSUER_PAGES_OBSERVED_INCOMPLETE_CALENDAR" if all(
        x.get("http_200") is True for x in result["pages"].values()) else "UNKNOWN_IR_SOURCE"
    return result

def halts_forensics(asof,following):
    snapshot=json.loads((HERE/"canonical_official_source_guard.json").read_text())
    need(snapshot.get("schema")=="XRAY_OFFICIAL_SOURCE_GUARD_V1","HALT_SNAPSHOT_SCHEMA")
    result={"source":"NASDAQTRADER_OFFICIAL",
      "canonical_guard_timestamp":snapshot.get("generated_at_utc"),
      "canonical_snapshot_status":snapshot.get("status"),
      "snapshot_frog_veto":SYMBOL in (snapshot.get("candidate_safety") or {}).get("veto_symbols",[]),
      "snapshot_not_oct13_asof_and_not_live_forever":True,
      "historical_complete_clear_pass":False,"live_halt_clear_pass":False,
      "observed_dates":{}}
    # Neither single-day RSS nor current security-status page certifies the
    # exact complete 30-session history; absence of FROG rows is diagnostics.
    for day in (ASOF,following[0]):
        try:
            rows,meta=halt.fetch_rows(day)
            matches=[r for r in rows if str(r.get("IssueSymbol") or "").strip().upper()==SYMBOL]
            result["observed_dates"][day]={"source_url":meta["url"],
                 "http_200":meta["http_status"]==200,"published_rss_rows":len(rows),
                 "frog_halt_rows_observed":len(matches),
                 "all_30_sessions_attested":False,
                 "negative_rss_not_halt_clear":True}
        except Exception as e:
            result["observed_dates"][day]={"status":"UNKNOWN_RSS","error_type":type(e).__name__}
    return result

def classify_close_window_update_lineage(rows, next_page_token):
    """Actual Alpaca SIP trade-update semantics, with cancel/correction lineage.

    Trade update field u is 'canceled', 'incorrect', or 'corrected'. A canceled
    or incorrect print is NOT a valid closing-auction execution. A corrected
    print is counted as a valid replacement but is tracked separately.
    A four-second sample never certifies full-session corrected RTH volume.
    """
    need(type(rows) is list and len(rows)<=10000,"TRADE_SAMPLE_ROWS")
    need(next_page_token in (None,""),"CLOSE_WINDOW_PAGE_INCOMPLETE")
    ids=set()
    states=collections.Counter()
    total_auction=0
    valid_auction=0
    rejected_auction=0
    for row in rows:
        need(type(row) is dict and isinstance(row.get("t"),str),
             "TRADE_UPDATE_ROW_SHAPE")
        ident=row.get("i")
        need(ident is not None and ident not in ids,"TRADE_UPDATE_ID_DUPLICATE")
        ids.add(ident)
        cond=row.get("c") or []
        need(type(cond) is list,"TRADE_UPDATE_CONDITIONS")
        raw_update=row.get("u")
        need(raw_update is None or raw_update in
             ("canceled","incorrect","corrected"),
             "TRADE_UPDATE_UNKNOWN_STATE")
        state=raw_update or "unmodified"
        states[state]+=1
        auction="6" in cond and row.get("x")=="Q"
        if auction:
            total_auction+=1
            if state in ("canceled","incorrect"):
                rejected_auction+=1
            else:
                valid_auction+=1
    return {"status":"OBSERVED_WINDOW_ONLY",
            "rows":len(rows),
            "nasdaq_condition6_observed":valid_auction,
            "condition6_all_prints_observed":total_auction,
            "condition6_cancelled_or_incorrect_excluded":rejected_auction,
            "trade_update_counts":dict(sorted(states.items())),
            "sample_cancelled_or_incorrect_count":
                states["canceled"]+states["incorrect"],
            "sample_correction_replacement_count":states["corrected"],
            "pagination_complete":True,
            "four_second_sample_update_states_reviewed":True,
            "corrections_complete":False,
            "whole_session_volume_complete":False}


def fetch_closing_sample(day,key,secret):
    start,close,_=official_window(day)
    params={"start":close.isoformat(),"end":(close+dt.timedelta(seconds=4)).isoformat(),
            "feed":"sip","limit":10000,"sort":"asc"}
    url=("https://data.alpaca.markets/v2/stocks/FROG/trades?"+
        urllib.parse.urlencode(params))
    req=urllib.request.Request(url,headers={"APCA-API-KEY-ID":key,
          "APCA-API-SECRET-KEY":secret,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=25) as resp:
        need(resp.status==200,"ALPACA_TRADES_STATUS")
        raw=resp.read(3_000_001)
    need(len(raw)<=3_000_000,"ALPACA_TRADES_RESPONSE")
    j=json.loads(raw)
    need(type(j) is dict and type(j.get("trades")) is list,"ALPACA_TRADES_JSON")
    return classify_close_window_update_lineage(
        j["trades"],j.get("next_page_token"))

def closing_samples(days):
    key=(os.environ.get("XRAY_ALPACA_DATA_KEY_ID") or
         os.environ.get("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.environ.get("XRAY_ALPACA_DATA_SECRET_KEY") or
            os.environ.get("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    result={"source":"ALPACA_HISTORICAL_SIP_PERSONAL_READ_ONLY",
            "requested_sessions":len(days),"session_observations":{},
            "exact_consolidated_close_corrections_pass":False,
            "exact_rth_dv30_primary_pass":False}
    if not key or not secret:
        result["status"]="UNKNOWN_ALPACA_CREDENTIALS"
        return result
    for day in days:
        try:
            result["session_observations"][day]=fetch_closing_sample(day,key,secret)
        except (ValueError,TypeError,KeyError,urllib.error.URLError,OSError,TimeoutError) as e:
            result["session_observations"][day]={"status":"UNKNOWN_TRADE_SAMPLE",
                                                  "error_type":type(e).__name__}
    result["four_second_trade_update_rows_by_state"]={
        k:sum(v.get("trade_update_counts",{}).get(k,0)
              for v in result["session_observations"].values())
        for k in ("unmodified","canceled","incorrect","corrected")}
    result["four_second_trade_update_completed_sessions"]=sum(
        v.get("four_second_sample_update_states_reviewed") is True
        for v in result["session_observations"].values())
    result["full_session_trade_update_lineage_verified"]=False
    result["observed_sessions"]=sum(v.get("status")=="OBSERVED_WINDOW_ONLY"
                                    for v in result["session_observations"].values())
    result["observed_auction_condition6_sessions"]=sum(v.get("nasdaq_condition6_observed",0)>0
                                    for v in result["session_observations"].values())
    result["status"]="BOUNDED_CLOSE_WINDOW_OBSERVED_NOT_CONSOLIDATED_FINAL"
    return result

def evaluate_promotion(report,policy):
    required=("source_sec_pit_share_class","source_ca_pit_independent",
              "source_exact_corrected_dv30","source_future_events",
              "source_full_historical_live_halt","source_regime_breadth",
              "source_c417_delivery_authority")
    gates=dict.fromkeys(required,False)
    gates["source_sec_pit_share_class"]=report["sec"]["current_class_shares_reconciled"]
    gates["source_ca_pit_independent"]=report["sec"]["corporate_actions_independent_pit_pass"]
    gates["source_exact_corrected_dv30"]=report["price"]["exact_rth_dv30_primary_pass"]
    gates["source_future_events"]=report["issuer_event"]["eight_day_event_calendar_clear"]
    gates["source_full_historical_live_halt"]=(
        report["halt"]["historical_complete_clear_pass"] and
        report["halt"]["live_halt_clear_pass"])
    gates["source_c417_delivery_authority"]=(
        policy.get("can_create_r92") is True and
        policy.get("can_update_compiled_C417_alpha") is True)
    complete=all(v is True for v in gates.values())
    return {"gates":gates,"missing":[k for k,v in gates.items() if v is not True],
            "eligible_primary":complete,"registered_r92":bool(complete),
            "release_state":"R92_NOT_AUTHORIZED_INSUFFICIENT_EVIDENCE" if not complete else
                            "ELIGIBLE_FOR_SEPARATE_CANONICAL_RELEASE_REVIEW"}

def selftest_close_update_lineage():
    base=[
        {"t":"2026-10-13T20:00:00Z","i":1,"c":["6"],"x":"Q"},
        {"t":"2026-10-13T20:00:01Z","i":2,"c":["6"],"x":"Q",
         "u":"canceled"},
        {"t":"2026-10-13T20:00:02Z","i":3,"c":["6"],"x":"Q",
         "u":"incorrect"},
        {"t":"2026-10-13T20:00:03Z","i":4,"c":["6"],"x":"Q",
         "u":"corrected"}]
    result=classify_close_window_update_lineage(base,None)
    need(result["condition6_all_prints_observed"]==4 and
         result["nasdaq_condition6_observed"]==2 and
         result["condition6_cancelled_or_incorrect_excluded"]==2 and
         result["sample_correction_replacement_count"]==1 and
         result["corrections_complete"] is False,
         "CORRECTED_AUCTION_NOT_FALSE_POSITIVE")
    for broken,token in (
        (base,"MORE"),
        (base+[base[0]],None),
        ([dict(base[0],u="unknown")],None),
        ([dict(base[0],c="6")],None)):
        try:classify_close_window_update_lineage(broken,token)
        except (ValueError,TypeError):pass
        else:raise AssertionError("UNSAFE_TRADE_UPDATE_ACCEPTED")
    print("XRAY_FROG_SIP_TRADE_UPDATE_SELFTEST=PASS_CANCEL_INCORRECT_CORRECTED_PAGINATION")

def selftest():
    selftest_close_update_lineage()
    docs={"filings":{"recent":{"accessionNumber":["0001193125-26-340294"],
        "form":["10-Q"],"filingDate":["2026-08-07"],
        "acceptanceDateTime":["2026-08-07T10:00:00Z"],
        "primaryDocument":["frog-20260630.htm"]}}}
    rows,complete=safe_filings(docs)
    need(rows[0]["form"]=="10-Q" and rows[0]["filed"]==START,
         "TEST_SEC_ROW")
    need(complete,"TEST_PRESENT_START_BOUNDARY")
    incomplete={"filings":{"recent":{
        "accessionNumber":["0001193125-26-340295"],
        "form":["8-K"],"filingDate":["2026-08-08"],
        "acceptanceDateTime":["2026-08-08T10:00:00Z"],
        "primaryDocument":["event.htm"]}}}
    _,too_recent=safe_filings(incomplete)
    need(not too_recent,"TEST_MISSING_OLD_BOUNDARY")
    d,f=sessions()
    need(len(d)==30 and len(f)==8 and d[-1]==ASOF,"TEST_30_PLUS8")
    report={"sec":{"current_class_shares_reconciled":False,
                   "corporate_actions_independent_pit_pass":False},
            "price":{"exact_rth_dv30_primary_pass":False},
            "issuer_event":{"eight_day_event_calendar_clear":False},
            "halt":{"historical_complete_clear_pass":False,"live_halt_clear_pass":False}}
    p={"can_create_r92":False,"can_update_compiled_C417_alpha":False}
    value=evaluate_promotion(report,p)
    need(not value["eligible_primary"] and not value["registered_r92"] and
         len(value["missing"])==7,"TEST_NO_UNSUPPORTED_PROMOTION")
    report["sec"]["current_class_shares_reconciled"]=True
    value=evaluate_promotion(report,p)
    need(not value["eligible_primary"],"TEST_ONE_PASS_NOT_EVERY_PASS")
    print("XRAY_FROG_LAST_MILE_SELFTEST=PASS_30_SESSIONS_8_EVENT_DAYS_SEC_DATE_NO_FALSE_R92")

def run(deep,frog,out):
    need(not out.resolve().is_relative_to(HERE.parent.resolve()),"NO_PUBLIC_SOURCE_REPORT")
    sources=load_sources(deep,frog)
    dates,future=sessions()
    result={"schema":SCHEMA,"symbol":SYMBOL,"family":"D","asof_et":ASOF,
      "sec_window_start":START,"event_forward_8_official_sessions":future,
      "source_lineage":sources,
      "research_start":"YES","real_money":"NO-GO","execution":"NONE",
      "canonical_files_mutated":False,"delivery_ledger_mutated":False,
      "iphone_delivery_receipt_verified":False,"raw_sec_share_or_vendor_prices_persisted":False,
      "unknown_never_pass":True}
    def save():
        out.write_text(json.dumps(result,indent=2,sort_keys=True)+chr(10))
    save()
    result["sec"]=sec_forensics(os.getenv("XRAY_SEC_USER_AGENT","").strip())
    save()
    result["issuer_event"]=issuer_ir()
    save()
    result["halt"]=halts_forensics(ASOF,future)
    save()
    result["price"]=closing_samples(dates)
    save()
    policy=json.loads((HERE/"personal_research_technical_policy_v1.json").read_text())
    result["decision"]=evaluate_promotion(result,policy)
    need(not result["decision"]["eligible_primary"] and
         not result["decision"]["registered_r92"],"RELEASE_REQUIRES_OTHER_UNPROVEN_GATES")
    save()
    print("XRAY_FROG_LAST_MILE_SEC="+result["sec"]["status"])
    print("XRAY_FROG_LAST_MILE_SEC_FORMS="+json.dumps(result["sec"].get("tracked_form_counts",{}),sort_keys=True))
    print("XRAY_FROG_LAST_MILE_IR="+result["issuer_event"]["status"])
    print("XRAY_FROG_LAST_MILE_CLOSE_SAMPLE_DAYS="+str(result["price"].get("observed_sessions",0)))
    print("XRAY_FROG_SIP_TRADE_UPDATE_CENSUS="+json.dumps(result["price"].get("four_second_trade_update_rows_by_state",{}),sort_keys=True))
    print("XRAY_FROG_LAST_MILE_MISSING="+",".join(result["decision"]["missing"]))
    print("XRAY_FROG_LAST_MILE_R92=FALSE_CANONICAL_NOT_MUTATED")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--deep",type=Path)
    p.add_argument("--frog",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:
        selftest()
        return
    need(a.deep and a.frog and a.out,"ARGS")
    run(a.deep,a.frog,a.out)

if __name__=="__main__":
    main()
