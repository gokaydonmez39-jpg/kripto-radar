#!/usr/bin/env python3
"""Source-bound personal research status: separate data/technical progress from AL.

Validates the existing runner's historical SIP technical labels against the exact
GitHub-orchestrated full watch cohort. No signals, orders, vendor bars, false
phone receipt or change to canonical C4.17 release.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_PERSONAL_RESEARCH_DAILY_ATTESTATION_V1"
SHADOW="XRAY_PERSONAL_SEVEN_SIP_TECHNICAL_SHADOW_V1"
ALLOWED=frozenset({
 "NO_CURRENT_OR_RECENT_WEEKLY_GATE",
 "NO_CONFIRMED_A_B_D_RECENT_TRIGGER",
 "TECHNICAL_FAMILY_RESEARCH_ONLY_RELEASE_GATES_OPEN",
 "UNKNOWN_FROZEN_TECHNICAL_GEOMETRY",
 "UNKNOWN_CORPORATE_ACTION_PIT",
 "UNKNOWN_QQQ_260_52",
 "UNKNOWN_QQQ_PROVIDER_OR_SCOPE",
 "UNKNOWN_260_OFFICIAL_HISTORY",
 "UNKNOWN_52_COMPLETED_WEEKS",
 "UNKNOWN_NONINTEGER_VOLUME",
 "UNKNOWN_OFFICIAL_SESSION_ORDER",
 "UNKNOWN_ROW_COUNT",
 "UNKNOWN_SECONDARY_ENGINE_OR_PROVIDER",
 "UNKNOWN_BATCH_TRANSPORT_OR_SCOPE",
 "UNKNOWN_RATE_LIMIT_NOT_QUERIED",
 "FAIL_OFFICIAL_LISTED_HISTORY_LT260",
})
def require(ok,reason):
    if not ok:raise ValueError("XRAY_PERSONAL_ATTEST_"+reason)
def blob(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode()+bytes([0])+b).hexdigest()
def sha(symbols):
    return hashlib.sha256(("\n".join(symbols)+"\n").encode()).hexdigest()
def audit(orchestrator,study,state_blob):
    require(type(orchestrator) is dict and type(study) is dict,"STRUCTURED_INPUT")
    watch=orchestrator.get("watch_radar") or {}
    tech=orchestrator.get("candidate_technical_funnel") or {}
    asof=orchestrator.get("asof_et")
    require(type(asof) is str and len(asof)==10 and
            asof==watch.get("asof_et")==tech.get("asof_et")==study.get("asof_et"),
            "SAME_COMPLETED_SESSION")
    require(orchestrator.get("execution")=="NONE" and
            orchestrator.get("real_money")=="NO-GO" and
            study.get("execution")=="NONE" and study.get("real_money")=="NO-GO",
            "NO_TRADE_GUARD")
    records=watch.get("watchlist")
    require(type(records) is list and watch.get("watchlist_cap") is None and
            watch.get("all_eligible_candidates_tracked") is True and
            watch.get("watchlist_count")==len(records)==
                watch.get("price_liquidity_screened_count")==
                tech.get("candidate_count"),
            "ALL_WATCHED_NO_TOP_N")
    symbols=[x.get("symbol") for x in records if type(x) is dict]
    require(len(symbols)==len(records) and
            all(type(s) is str and s for s in symbols) and
            len(set(symbols))==len(symbols),"FULL_SYMBOL_IDENTITY")
    require(tech.get("source_candidates_sha256")==watch.get("source_candidates_sha256")
            and tech.get("watchlist_digest")==watch.get("watchlist_digest"),
            "WATCH_DIGEST_SOURCE_DRIFT")
    previous=tech.get("results") or {}
    require(type(previous) is dict and set(previous)==set(symbols),
            "TECH_EXACT_RESULT_COHORT")
    pending=sorted(sym for sym in symbols if
                   type(previous[sym]) is dict and
                   type(previous[sym].get("status")) is str and
                   previous[sym]["status"].startswith("UNKNOWN_"))
    require(pending==sorted(tech.get("pending_symbols") or []) and
            len(pending)==tech.get("pending_count"),
            "CURRENT_PENDING_SCOPE_DRIFT")
    require(study.get("schema")==SHADOW and
            study.get("source_state_git_blob_sha")==state_blob and
            study.get("source")=="ALPACA_HISTORICAL_SIP_PERSONAL_NONCOMMERCIAL" and
            study.get("scope_count")==len(pending),
            "EXACT_RESEARCH_SOURCE_BINDING")
    outcomes=study.get("statuses")
    require(type(outcomes) is dict and set(outcomes)==set(pending) and
            all(type(v) is str and (v in ALLOWED or v.startswith("UNKNOWN_"))
                for v in outcomes.values()),
            "NO_FAKE_SUCCESS_OR_MISSING_CANDIDATE")
    guards=("no_raw_market_data_exported","canonical_files_mutated",
            "canonical_price_promoted","canonical_history_promoted",
            "primary_mc_promoted","iphone_receipt_attested")
    for field in guards:
        require(study.get(field) is (field=="no_raw_market_data_exported"),
                "SECONDARY_STUDY_GUARD_"+field.upper())
    require(study.get("true_r92_count")==0 and
            study.get("final_buy_signals")==[] and
            study.get("pending_symbol_truncation") is False and
            type(study.get("api_batch_count")) is int,
            "NO_FALSE_ALPHA_OR_TRUNCATION")
    counts=dict(sorted(collections.Counter(outcomes.values()).items()))
    require(counts==study.get("counts"),"STATUS_COUNTS_EXACT")
    technical_research_only=sum(
       status=="TECHNICAL_FAMILY_RESEARCH_ONLY_RELEASE_GATES_OPEN"
       for status in outcomes.values())
    return {
      "schema":SCHEMA,"asof_et":asof,
      "full_watch_count":len(symbols),
      "canonical_candidate_technical_evaluated_count":tech.get("evaluated_count"),
      "candidate_pending_source_total":len(pending),
      "secondary_sip_history_pending_reexamined_count":len(outcomes),
      "research_only_technical_family_count":technical_research_only,
      "secondary_technical_status_counts":counts,
      "source_orchestrator_blob_sha":state_blob,
      "source_pending_symbol_hash":sha(pending),
      "secondary_no_unresolved_candidates_silently_dropped":True,
      "personal_research_workflow":"OPERATIONAL_SECONDARY_EVIDENCE_ONLY",
      "personal_research_not_trading":True,
      "certified_C417_AL_signals_created":0,
      "registered_R92_created":0,
      "phone_delivery_receipt_proven":False,
      "canonical_current_terminal_production_authority":False,
      "source_research_never_substitutes_live_G9":True,
      "execution":"NONE","real_money":"NO-GO",
      "status":"PERSONAL_RESEARCH_BOUND_PASS_NOT_PRODUCTION"
    }
def selftest():
    a="2026-10-13"
    w={"asof_et":a,"watchlist":[{"symbol":s} for s in ("AAA","BBB","CCC")],
       "watchlist_count":3,"price_liquidity_screened_count":3,"watchlist_cap":None,
       "all_eligible_candidates_tracked":True,
       "source_candidates_sha256":"a"*64,"watchlist_digest":"b"*64}
    t={"asof_et":a,"candidate_count":3,"evaluated_count":1,
       "pending_count":2,"pending_symbols":["BBB","CCC"],
       "source_candidates_sha256":"a"*64,"watchlist_digest":"b"*64,
       "results":{"AAA":{"status":"NO_CURRENT_OR_RECENT_WEEKLY_GATE"},
                  "BBB":{"status":"UNKNOWN_260_OFFICIAL_HISTORY"},
                  "CCC":{"status":"UNKNOWN_FROZEN_TECHNICAL_GEOMETRY"}}}
    m={"asof_et":a,"watch_radar":w,"candidate_technical_funnel":t,
       "execution":"NONE","real_money":"NO-GO"}
    h="1"*40
    s={"schema":SHADOW,"asof_et":a,"source_state_git_blob_sha":h,
       "source":"ALPACA_HISTORICAL_SIP_PERSONAL_NONCOMMERCIAL",
       "scope_count":2,"statuses":{"BBB":"NO_CURRENT_OR_RECENT_WEEKLY_GATE",
                 "CCC":"UNKNOWN_FROZEN_TECHNICAL_GEOMETRY"},
       "counts":{"NO_CURRENT_OR_RECENT_WEEKLY_GATE":1,
                  "UNKNOWN_FROZEN_TECHNICAL_GEOMETRY":1},
       "api_batch_count":2,"pending_symbol_truncation":False,
       "no_raw_market_data_exported":True,
       "canonical_files_mutated":False,"canonical_price_promoted":False,
       "canonical_history_promoted":False,"primary_mc_promoted":False,
       "iphone_receipt_attested":False,"true_r92_count":0,
       "final_buy_signals":[],"execution":"NONE","real_money":"NO-GO"}
    valid=audit(m,s,h)
    require(valid["full_watch_count"]==3 and
            valid["candidate_pending_source_total"]==2 and
            valid["registered_R92_created"]==0 and
            valid["status"]=="PERSONAL_RESEARCH_BOUND_PASS_NOT_PRODUCTION",
            "POSITIVE_EXACT_COHORT")
    import copy
    for field,mutation in (
      ("SOURCE",lambda x:x.update(source_state_git_blob_sha="2"*40)),
      ("BAD_R92",lambda x:x.update(true_r92_count=1)),
      ("TRUNCATED",lambda x:x["statuses"].pop("CCC")),
      ("FALSE_PRIMARY",lambda x:x.update(canonical_price_promoted=True)),
      ("ASOF_DRIFT",lambda x:x.update(asof_et="2026-10-12")),
      ("BAD_COUNT",lambda x:x.update(scope_count=1)),
    ):
        bad=copy.deepcopy(s)
        mutation(bad)
        try:audit(m,bad,h)
        except ValueError:pass
        else:raise AssertionError("FALSE_ATTEST_ACCEPTED_"+field)
    print("XRAY_PERSONAL_DAILY_ATTEST_SELFTEST=PASS_FULL_SCOPE_6_NEGATIVES_NO_C417_R92")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--study",type=Path)
    a=p.parse_args()
    if a.selftest:return selftest()
    require(a.study is not None and a.study.is_file(),"MISSING_STUDY")
    raw=(ROOT/"orchestrator_state.json").read_bytes()
    study=json.loads(a.study.read_text())
    result=audit(json.loads(raw),study,blob(raw))
    print("XRAY_PERSONAL_RESEARCH_ACCEPTANCE="+result["status"])
    print("XRAY_PERSONAL_RESEARCH_BOUND_SUMMARY="+json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
