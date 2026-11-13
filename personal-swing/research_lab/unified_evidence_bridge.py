"""Pure XRAY research-only bridge: validated 477×3 readback to Decision V1.

Caller must independently authenticate XNAS and private sources. This module
cannot read Sheets, schedule runs, send messages, publish, trade, fit, or change
AL/STOP/2R. It will refuse a missing Kronos partition, not synthesize records.
"""
from __future__ import annotations

from collections import defaultdict
import decision_intelligence as decision
import private_research_readback as readback

SCHEMA="XRAY_UNIFIED_READONLY_EVIDENCE_V1"


def compose(scan_matrix,score_matrix,kronos_matrix,*,
            expected_asof,expected_symbols,
            expected_algorithm_sha,expected_run_id):
    """Compose a private snapshot with no new source or notification authority."""
    snapshot=readback.build_readback(
        scan_matrix,score_matrix,kronos_matrix,
        expected_asof=expected_asof,expected_symbols=expected_symbols,
        expected_algorithm_sha=expected_algorithm_sha,
        expected_run_id=expected_run_id)
    decision.require(snapshot["scope_count"]==477 and
                     snapshot["forecast_count"]==1431 and
                     snapshot["source_authentication"]=="CALLER_WITNESS_NOT_ATTESTED" and
                     not any(snapshot[k] for k in
                             ("may_publish","may_notify","may_modify_al","may_trade")),
                     "UNTRUSTED_OR_UNSAFE_READBACK")
    by_symbol=defaultdict(dict)
    for f in snapshot["forecasts"]:
        symbol,horizon=f["symbol"],f["horizon"]
        decision.require(horizon in (1,5,12) and
                         horizon not in by_symbol[symbol] and
                         isinstance(f["source_row_sha256"],str),
                         "FORECAST_UNIQUE_HORIZON")
        by_symbol[symbol][horizon]=f
    decision.require(len(by_symbol)==477 and
                     all(set(g)=={1,5,12} for g in by_symbol.values()),
                     "KRONOS_COHORT")
    verdicts=[]
    for ep in sorted(snapshot["episodes"],key=lambda x:x["rank"]):
        horizons=by_symbol[ep["symbol"]]
        ordered=[horizons[h] for h in (1,5,12)]
        qualities={r["model_quality"] for r in ordered}
        decision.require(len(qualities)==1 and
                         len({r["source_close"] for r in ordered})==1,
                         "FORECAST_REFERENCE_OR_QUALITY_DRIFT")
        quality=ordered[0]["model_quality"]
        ready=quality in ("RESEARCH_ONLY","RESEARCH_CLOSE_ONLY")
        decision.require(ready or quality.startswith("HOLD_QC_"),
                         "INVALID_MODEL_QUALITY")
        payload=({"model_quality":quality,
                  "reference":ordered[0]["source_close"],
                  "closes":{str(h):horizons[h]["close"] for h in (1,5,12)}}
                 if ready else {})
        core={"system":decision.SYSTEM,"asof":snapshot["asof"],
              "episode_id":ep["episode_id"],"symbol":ep["symbol"],
              "source_run":snapshot["source_run_id"],
              "scope_sha":snapshot["scope_sha"],
              "algorithm_sha":snapshot["algorithm_sha"],
              "reference":ep["reference"],"stop":ep["stop"],
              "target":ep["target_2r"],
              "current_close":ep["current_close"],
              "technical_score":ep["technical_score"]}
        witness={"source":"KRONOS","asof":snapshot["asof"],
                 "episode_id":ep["episode_id"],
                 "scope_sha":snapshot["scope_sha"],
                 "algorithm_sha":snapshot["algorithm_sha"],
                 "source_run":snapshot["source_run_id"],
                 "status":"READY" if ready else "HOLD","payload":payload}
        witness["sha256"]=decision.digest(witness)
        verdict=decision.assess(core,[witness])
        decision.require(verdict["decision_influence"]=="NO_GO" and
                         not any(verdict[k] for k in
                                 ("may_publish","may_notify","may_modify_al","may_trade")) and
                         verdict["success_probability"] is None and
                         verdict["net_expected_r"] is None,
                         "DECISION_AUTHORITY_BREACH")
        verdict["source_witness_sha256"]=decision.digest(
            {"score_sha256":snapshot["score_digest_consistency_only"],
             "source_row_sha256":[r["source_row_sha256"] for r in ordered],
             "research_sha256":verdict["research_sha256"]})
        verdicts.append(verdict)
    result={"schema":SCHEMA,"asof":snapshot["asof"],
            "source_run_id":snapshot["source_run_id"],
            "scope_sha":snapshot["scope_sha"],
            "algorithm_sha":snapshot["algorithm_sha"],
            "scope_count":snapshot["scope_count"],
            "forecast_count":snapshot["forecast_count"],
            "episode_count":snapshot["score_count"],
            "verdicts":verdicts,
            "research_only":True,
            "source_authentication":"CALLER_WITNESS_NOT_ATTESTED",
            "may_notify":False,"may_publish":False,
            "may_modify_al":False,"may_trade":False}
    decision.require(len(verdicts)==result["episode_count"],
                     "EPISODE_VIEW_COUNT")
    result["source_evidence_sha256"]=decision.digest({
        "source_run":snapshot["source_run_id"],
        "scope_sha256":snapshot["scope_sha"],
        "score_sha256":snapshot["score_digest_consistency_only"],
        "kronos_row_sha256":[r["source_row_sha256"] for r in snapshot["forecasts"]],
        "research_sha256":[r["research_sha256"] for r in verdicts]})
    return result
