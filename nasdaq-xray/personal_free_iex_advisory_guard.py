#!/usr/bin/env python3
"""Private IEX technical research advisory: strict evidence and dedup only.

Only pre-existing unique ChatGPT alert task can reserve in the existing
personal-research ledger. It cannot create R92/AL, price, MC, source license,
device acknowledgement, orders or any public raw IEX data.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib,json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ALERT_TASK="6a825366222081918997094d76e6ae46"
RESEARCH_SCHEMA="XRAY_PERSONAL_FREE_IEX_EOD_RESEARCH_V1"
LEDGER_SCHEMA="XRAY_PERSONAL_RESEARCH_ADVISORY_LEDGER_V1"
LABELS={"RESEARCH_BREAKOUT_WATCH","RESEARCH_RECLAIM_WATCH",
        "TREND_WATCH","WATCH_ONLY","UNKNOWN_IEX_COVERAGE"}
REVIEW={"RESEARCH_BREAKOUT_WATCH","RESEARCH_RECLAIM_WATCH"}
RESERVED="RESERVED_ATTEMPT_NOT_DEVICE_DELIVERY"
SYMBOL=re.compile(r"[A-Z0-9.]+\Z")
GIT_SHA=re.compile(r"[0-9a-f]{40}\Z")
S256=re.compile(r"[0-9a-f]{64}\Z")

def need(x,tag):
    if not x: raise ValueError("XRAY_PRIVATE_IEX_ADVISORY_"+tag)

def gitblob(raw):
    need(isinstance(raw,bytes),"RAW_GIT_BLOB_REQUIRED")
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def stable_key(study,root,root_git_blob_sha):
    need(isinstance(study,dict) and study.get("schema")==RESEARCH_SCHEMA
         and study.get("source")=="ALPACA_FREE_IEX_EOD_NONCOMMERCIAL"
         and study.get("source_data_not_current_intraday") is True
         and study.get("root_blob_sha")==root_git_blob_sha
         and GIT_SHA.fullmatch(root_git_blob_sha or "")
         and study.get("asof_et")==root.get("asof_et")
         and re.fullmatch(r"20\d\d-\d\d-\d\d",study.get("asof_et","")),
         "SOURCE_ASOF_OR_GIT_BLOB")
    watch=root.get("watch_radar") or {}
    tech=root.get("candidate_technical_funnel") or {}
    names=sorted(r.get("symbol") for r in watch.get("watchlist",[])
                 if isinstance(r,dict) and isinstance(r.get("symbol"),str))
    need(root.get("execution")=="NONE" and root.get("real_money")=="NO-GO"
         and watch.get("execution")=="NONE" and watch.get("real_money")=="NO-GO"
         and watch.get("asof_et")==study["asof_et"]
         and tech.get("asof_et")==study["asof_et"]
         and watch.get("all_eligible_candidates_tracked") is True
         and watch.get("watchlist_cap") is None
         and watch.get("unknown_never_pass") is True
         and watch.get("source_candidates_sha256")==tech.get("source_candidates_sha256")
         and names and len(names)==len(set(names))
         and len(names)==watch.get("watchlist_count")==watch.get("price_liquidity_screened_count")
         and all(SYMBOL.fullmatch(n) for n in names)
         and all(x.get("buy_signal") is False
                 and x.get("classification")=="WATCH_LIQUIDITY_PRE_SCREEN_ONLY"
                 for x in watch["watchlist"]), "ROOT_WATCH_SCOPE")
    need(study.get("population_sha256")==hashlib.sha256(
              "\n".join(names).encode()).hexdigest()
         and study.get("total_watch_symbols")==len(names)
         and study.get("attempted_symbols")==len(names),
         "FULL_POPULATION_HASH")
    conf=study.get("confidence") or {}
    need(conf.get("grade")=="LOW"
         and conf.get("feed")=="IEX_SINGLE_EXCHANGE"
         and conf.get("consolidated_rth_volume_verified") is False
         and conf.get("independent_issuer_mc_verified") is False
         and conf.get("issuer_event_clearance_verified") is False
         and conf.get("is_probability") is False,
         "SINGLE_VENUE_LOW_CONFIDENCE")
    for k,v in (("canonical_price_promoted",False),
                 ("canonical_history_promoted",False),
                 ("canonical_mc_promoted",False),
                 ("registered_r92_count",0),
                 ("certified_buy_count",0),
                 ("broker",False),("orders",[]),
                 ("iphone_receipt_attested",False),
                 ("execution","NONE"),("real_money","NO-GO"),
                 ("unknown_never_pass",True),
                 ("raw_vendor_ohlcv_exported",False)):
        need(study.get(k)==v and type(study.get(k)) is type(v),"NO_FALSE_ALPHA_"+k)
    max_calls=study.get("max_vendor_requests")
    calls=study.get("vendor_requests")
    need(type(max_calls) is int and max_calls==64
         and type(calls) is int and 0<calls<=max_calls,
         "REAL_BOUNDED_PROVIDER_MEASUREMENT")
    rows=study.get("per_symbol")
    need(isinstance(rows,dict) and set(rows)==set(names),"EXACT_STATUS_PARTITION")
    counts={}
    review=[]
    for sym,row in rows.items():
        need(isinstance(row,dict) and set(row)=={"label","reasons"}
             and row["label"] in LABELS
             and isinstance(row["reasons"],list) and bool(row["reasons"])
             and all(isinstance(x,str) and 0<len(x)<100 for x in row["reasons"]),
             "INVALID_SYMBOL_STATUS")
        label=row["label"]
        counts[label]=counts.get(label,0)+1
        if label in REVIEW:
            need(row["reasons"]==["IEX_ONLY_NO_EVENT_OR_MC_CLEARANCE"],
                 "UNAPPROVED_REVIEW_STATUS")
            review.append(sym)
    review.sort()
    need(study.get("state_counts")==dict(sorted(counts.items()))
         and study.get("research_review_symbols")==review
         and study.get("research_review_count")==len(review)
         and len(review)<=len(names),"COUNT_SET_HASH_MISMATCH")
    if not review: return None
    k={"source":"PRIVATE_FREE_IEX_STUDY_NO_R92",
       "root_git_blob_sha":root_git_blob_sha,
       "asof_et":study["asof_et"],"population_sha256":study["population_sha256"],
       "research_review_symbols":review,
       "labels":{s:rows[s]["label"] for s in review}}
    return hashlib.sha256(json.dumps(k,sort_keys=True,
                        separators=(",",":")).encode()).hexdigest()

def reserve(current,study,root,root_git_blob_sha,task_id):
    need(isinstance(current,dict)
         and current.get("schema")==LEDGER_SCHEMA
         and current.get("execution")=="NONE" and current.get("real_money")=="NO-GO"
         and current.get("unknown_never_pass") is True
         and current.get("scope")=="PERSONAL_RESEARCH_ADVISORY_ONLY_NEVER_R92"
         and isinstance(current.get("entries"),list)
         and len(current["entries"])<=1000,"EXISTING_LEDGER_AUTHORITY")
    history=current["entries"]
    need(len(history)==len({e.get("key") for e in history if isinstance(e,dict)})
         and all(isinstance(e,dict)
                 and S256.fullmatch(e.get("key",""))
                 and e.get("status")==RESERVED
                 and e.get("device_receipt_attested") is False
                 and e.get("execution")=="NONE" and e.get("real_money")=="NO-GO"
                 and isinstance(e.get("symbols"),list)
                 for e in history),"LEDGER_HISTORY_INTEGRITY")
    key=stable_key(study,root,root_git_blob_sha)
    if key is None or any(x["key"]==key for x in history):
        return None
    need(task_id==ALERT_TASK,"ONLY_SINGLE_EXISTING_CHATGPT_ALERT_TASK")
    new=deepcopy(current)
    new["entries"].append({
        "key":key,"asof_et":study["asof_et"],
        "symbols":study["research_review_symbols"],
        "source_epoch_blobs":{"root":root_git_blob_sha},
        "source":"PRIVATE_FREE_IEX_SINGLE_VENUE_LOW_CONFIDENCE_NO_AL",
        "status":RESERVED,
        "device_receipt_attested":False,
        "execution":"NONE","real_money":"NO-GO"})
    return new

def selftest():
    root_raw=(ROOT/"orchestrator_state.json").read_bytes()
    root=json.loads(root_raw)
    sha=gitblob(root_raw)
    names=sorted(x["symbol"] for x in root["watch_radar"]["watchlist"])
    assert len(names)==root["watch_radar"]["watchlist_count"]
    rows={s:{"label":"WATCH_ONLY","reasons":["NO_RESEARCH_SETUP_OBSERVED"]}
          for s in names}
    rows[names[0]]={"label":"RESEARCH_BREAKOUT_WATCH",
                    "reasons":["IEX_ONLY_NO_EVENT_OR_MC_CLEARANCE"]}
    study={
        "schema":RESEARCH_SCHEMA,"source":"ALPACA_FREE_IEX_EOD_NONCOMMERCIAL",
        "source_data_not_current_intraday":True,
        "root_blob_sha":sha,"asof_et":root["asof_et"],
        "population_sha256":hashlib.sha256("\n".join(names).encode()).hexdigest(),
        "total_watch_symbols":len(names),"attempted_symbols":len(names),
        "confidence":{"grade":"LOW","feed":"IEX_SINGLE_EXCHANGE",
                      "consolidated_rth_volume_verified":False,
                      "independent_issuer_mc_verified":False,
                      "issuer_event_clearance_verified":False,
                      "is_probability":False},
        "state_counts":{"RESEARCH_BREAKOUT_WATCH":1,"WATCH_ONLY":len(names)-1},
        "research_review_symbols":[names[0]],"research_review_count":1,
        "per_symbol":rows,"max_vendor_requests":64,"vendor_requests":1,
        "canonical_price_promoted":False,"canonical_history_promoted":False,
        "canonical_mc_promoted":False,"registered_r92_count":0,
        "certified_buy_count":0,"broker":False,"orders":[],
        "iphone_receipt_attested":False,"execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"raw_vendor_ohlcv_exported":False}
    existing=json.loads((ROOT/"personal_research_advisory_ledger.json").read_text())
    positive=reserve(existing,study,root,sha,ALERT_TASK)
    need(positive is not None and len(positive["entries"])==len(existing["entries"])+1
         and reserve(positive,study,root,sha,ALERT_TASK) is None
         and positive["entries"][-1]["device_receipt_attested"] is False,
         "POSITIVE_DEDUP_NOT_DEVICE")
    negatives=(
      ("FALSE_PRICE_PROMOTION",lambda x:x.update(canonical_price_promoted=True)),
      ("FALSE_R92",lambda x:x.update(registered_r92_count=1)),
      ("WRONG_VOLUME_GRADE",lambda x:x["confidence"].update(
          consolidated_rth_volume_verified=True)),
      ("FAKE_HIGH",lambda x:x["confidence"].update(grade="HIGH")),
      ("FAKE_BROKER",lambda x:x.update(broker=True)),
      ("FAKE_IEX_SOURCE",lambda x:x.update(source="SIP")),
      ("WRONG_ASOF",lambda x:x.update(asof_et="2026-10-01")),
      ("BAD_ROOT",lambda x:x.update(root_blob_sha="0"*40)),
      ("EMPTY_PROVIDER_IO",lambda x:x.update(vendor_requests=0)),
      ("FALSE_POPULATION",lambda x:x.update(total_watch_symbols=1)),
      ("FORGED_CANDIDATE",lambda x:x["research_review_symbols"].clear()),
      ("BYPASS_EVENT",lambda x:x["per_symbol"][names[0]].update(reasons=[])),
      ("MORE_THAN_MAX",lambda x:x.update(vendor_requests=65)),
      ("DISAGREE_COUNTS",lambda x:x["state_counts"].update(WATCH_ONLY=1)),
    )
    for tag,mutation in negatives:
        bad=deepcopy(study)
        mutation(bad)
        try:stable_key(bad,root,sha)
        except ValueError:pass
        else:raise AssertionError("FALSE_FREE_IEX_ADVISORY_"+tag)
    badroot=deepcopy(root)
    badroot["watch_radar"]["watchlist"][0]["buy_signal"]=True
    try:stable_key(study,badroot,sha)
    except ValueError:pass
    else:raise AssertionError("FORGED_ROOT_BUY")
    try:reserve(existing,study,root,sha,"WRONG_TASK")
    except ValueError:pass
    else:raise AssertionError("UNAUTHORIZED_WRITER")
    quiet=deepcopy(study)
    quiet["per_symbol"][names[0]]={"label":"TREND_WATCH",
                                    "reasons":["NO_BREAKOUT_OR_RECLAIM_CONFIRMATION"]}
    quiet["state_counts"]={"TREND_WATCH":1,"WATCH_ONLY":len(names)-1}
    quiet["research_review_symbols"]=[]
    quiet["research_review_count"]=0
    need(reserve(existing,quiet,root,sha,ALERT_TASK) is None,"NO_TRIGGER_MUST_BE_SILENT")
    print("XRAY_PRIVATE_FREE_IEX_ALERT_SELFTEST=PASS_16_NEGATIVES_EXACT_475_ROOT_LOW_GRADE_NO_R92")

if __name__=="__main__":selftest()
