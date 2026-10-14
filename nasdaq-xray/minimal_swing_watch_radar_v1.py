#!/usr/bin/env python3
"""Small candidate-local Nasdaq swing observation radar.

Produces actionable RESEARCH WATCHING, not fake buy/R92 alerts.
Healthy symbols are not blocked by unrelated upstream UNKNOWN symbols.
Only exact-30 positive price/turnover observations enter the list.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_MINIMAL_SWING_WATCH_RADAR_V1"
ASOF_FROG="2026-10-13"
FROG_DEEP_SOURCE_SHA256="ed9cc814c488fb743f52227d42c18f8c81876d67c9167ebc1128738a8406c855"
FROG_EVENT_SOURCE_RUN=38557974466

def need(ok,reason):
    if not ok: raise ValueError("XRAY_MINIMAL_RADAR_"+reason)

def fingerprint(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def take_watch_candidates(raw,max_items=12):
    need(type(raw) is dict and raw.get("schema")=="XRAY_SINA_CANDIDATES_V2"
         and type(raw.get("asof_et")) is str,"SOURCE_SCHEMA")
    rows=raw.get("candidates")
    need(type(rows) is dict and raw.get("candidate_count")==len(rows),"CANDIDATE_TOTAL")
    need(type(max_items) is int and 1<=max_items<=30,"LIMIT")
    clean=[]
    rejected=0
    for symbol,record in sorted(rows.items()):
        if (type(symbol) is not str or not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}",symbol)
             or type(record) is not dict):
            rejected+=1
            continue
        v=record
        price=v.get("price")
        dv=v.get("dv30")
        good=(v.get("proof")=="EXACT30_MEDIAN"
              and v.get("known_session_count")==30
              and v.get("missing_sessions")==[]
              and v.get("no_synthetic_bar") is True
              and type(price) in (int,float)
              and type(dv) in (int,float)
              and math.isfinite(price) and math.isfinite(dv)
              and price>=5 and dv>=50_000_000)
        if not good:
            rejected+=1
            continue
        name=str(v.get("security_name") or "")
        # Avoid turning raw warrants/rights/SPAC units into ordinary-stock picks.
        if re.search(r"\b(warrants?|rights?|units|preferred stock|depositary shares)\b",name,re.I):
            rejected+=1
            continue
        clean.append({"symbol":symbol,"name":name[:120],
                      "close_usd_observed":round(price,4),
                      "dv30_usd_observed":round(dv,2),
                      "exact_completed_sessions":30,
                      "price_observation_pass":True,
                      "liquidity_observation_pass":True,
                      "setup_confirmation":"NOT_EVALUATED_HERE",
                      "buy_signal":False,
                      "classification":"WATCH_LIQUIDITY_PRE_SCREEN_ONLY"})
    clean.sort(key=lambda x:(-x["dv30_usd_observed"],x["symbol"]))
    return clean[:max_items],len(clean),rejected

def compile_watch_radar(candidates,previous=None,source_sha256=None,max_items=12):
    prev=previous if type(previous) is dict else {}
    top,n,rejected=take_watch_candidates(candidates,max_items)
    asof=candidates["asof_et"]
    previous_radar=prev.get("watch_radar") or {}
    previous_rows=previous_radar.get("watchlist") or []
    prior_by_symbol={x.get("symbol"):x for x in previous_rows if type(x) is dict}
    prev_syms=set(prior_by_symbol)
    previous_asof=previous_radar.get("asof_et")
    for v in top:
        old=prior_by_symbol.get(v["symbol"])
        v["tracking_state"]="PERSISTING" if old is not None else "NEW_ON_WATCHLIST"
        old_price=old.get("close_usd_observed") if old else None
        v["previous_completed_session_change_pct"]=None
        if (previous_asof and previous_asof!=asof and
                type(old_price) in (int,float) and
                math.isfinite(old_price) and old_price>0):
            v["previous_completed_session_change_pct"]=round(
                100*(v["close_usd_observed"]/old_price-1),2)
    previous_set=prev_syms
    current={x["symbol"] for x in top}
    fingerprint_id=fingerprint({"asof_et":asof,"watchlist":
                                [(x["symbol"],x["close_usd_observed"],x["dv30_usd_observed"])
                                 for x in top]})
    frog=(candidates.get("candidates") or {}).get("FROG") or {}
    special=None
    if asof==ASOF_FROG and frog.get("proof")=="EXACT30_MEDIAN" and frog.get("known_session_count")==30:
        special={"symbol":"FROG","setup_family":"D",
           "technical_deep_source_sha256":FROG_DEEP_SOURCE_SHA256,
           "technical_R1_RR_asof":ASOF_FROG,
           "technical_risk_rr_geometry_pass":True,
           "known_issuer_event_block":True,
           "official_event_dates":["2026-10-20","2026-10-21","2026-10-22"],
           "official_event_evidence_run_id":FROG_EVENT_SOURCE_RUN,
           "status":"TECHNICAL_WATCH_EVENT_VETO_NO_BUY_NO_R92",
           "registered_r92":False}
    out={"schema":SCHEMA,"asof_et":asof,
         "authority":"OPEN_PRICE_LIQUIDITY_RESEARCH_WATCH_ONLY",
         "candidate_count_from_source":len(candidates["candidates"]),
         "price_liquidity_screened_count":n,"source_rows_excluded":rejected,
         "global_upstream_unknown_does_not_veto_healthy_watch_rows":True,
         "source_candidates_sha256":source_sha256 or fingerprint(candidates),
         "watchlist":top,
         "watchlist_count":len(top),
         "watchlist_digest":fingerprint_id,
         "new_watchlist_symbols":sorted(current-previous_set),
         "no_longer_in_top_watchlist":sorted(previous_set-current),
         "candidate_local_special_review":special,
         "setup_D_or_A_or_B_fully_approved":False,
         "registered_r92_count":0,
         "orders":[],"execution":"NONE","real_money":"NO-GO",
         "unknown_never_pass":True,
         "alert_semantics":"RESEARCH_WATCH_NOT_AL_OR_REGISTERED_R92"}
    return out

def selftest():
    def rec(name,price,dv,ok=True):
        return {"security_name":name,"price":price,"dv30":dv,
                "proof":"EXACT30_MEDIAN" if ok else "UNKNOWN",
                "known_session_count":30,"missing_sessions":[],
                "no_synthetic_bar":True}
    data={"schema":"XRAY_SINA_CANDIDATES_V2","asof_et":ASOF_FROG,
        "candidate_count":5,
        "candidates":{
           "AAPL":rec("Apple Inc - Common Stock",123,100_000_000),
           "FROG":rec("JFrog Ltd - Ordinary shares",99,60_000_000),
           "BAD":rec("Bad Source",99,999_000_000,False),
           "LOW":rec("Low Liquidity",99,12_000_000),
           "WARR":rec("Some Warrant",99,400_000_000)}}
    r=compile_watch_radar(data)
    need(r["watchlist_count"]==2 and
         [x["symbol"] for x in r["watchlist"]]==["AAPL","FROG"] and
         r["candidate_local_special_review"]["known_issuer_event_block"] is True
         and r["registered_r92_count"]==0,"CANDIDATE_LOCAL_PASS_OTHERS_VETO")
    same=compile_watch_radar(data,{"watch_radar":r})
    need(same["new_watchlist_symbols"]==[] and
         all(x["tracking_state"]=="PERSISTING" for x in same["watchlist"]),
         "TRACKING_STABLE")
    tomorrow=json.loads(json.dumps(data))
    tomorrow["asof_et"]="2026-10-14"
    tomorrow["candidates"]["AAPL"]["price"]=129.15
    changed=compile_watch_radar(tomorrow,{"watch_radar":r})
    apple=next(x for x in changed["watchlist"] if x["symbol"]=="AAPL")
    need(apple["previous_completed_session_change_pct"]==5.0
         and apple["tracking_state"]=="PERSISTING"
         and changed["candidate_local_special_review"] is None,
         "NEXT_SESSION_TRACKS_TRUE_PRICE_CHANGE_NO_STALE_DEEP")
    for name,breakit in [
      ("SOURCE_PARTITION",lambda x:x.update(candidate_count=4)),
      ("SOURCE_SCHEMA",lambda x:x.update(schema="BAD"))]:
        bad=json.loads(json.dumps(data));breakit(bad)
        try:compile_watch_radar(bad)
        except ValueError:pass
        else:raise AssertionError("INVALID_WATCH_ACCEPTED_"+name)
    newer=json.loads(json.dumps(data))
    newer["asof_et"]="2026-10-14"
    future=compile_watch_radar(newer)
    need(future["candidate_local_special_review"] is None,
         "OLD_FROG_DEEP_NOT_REUSED_NEXT_SESSION")
    print("XRAY_MINIMAL_RADAR_SELFTEST=PASS_LOCAL_2_OF_5_TRACKING_NO_FAKE_AL")

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--candidates",type=Path,default=ROOT/"sina_candidates.json")
    p.add_argument("--previous",type=Path,default=ROOT/"orchestrator_state.json")
    args=p.parse_args()
    if args.selftest:return selftest()
    src=args.candidates.read_bytes()
    data=json.loads(src)
    prev=json.loads(args.previous.read_text()) if args.previous.is_file() else {}
    out=compile_watch_radar(data,prev,hashlib.sha256(src).hexdigest())
    print(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2))

if __name__=="__main__":main()
