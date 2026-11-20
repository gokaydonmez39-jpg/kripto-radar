"""Private aggregate health view for the four Personal 477 research lanes.

This is a pure contract over independently retrieved caller evidence. A match
is not source authentication, trading permission, or a ChatGPT delivery ACK.
"""
from __future__ import annotations

from datetime import date
import re


SCHEMA = "XRAY_PERSONAL_477_SOURCE_HEALTH_V1"
REPOSITORY = "gokaydonmez39-jpg/kripto-radar"
EOD = ".github/workflows/xray-personal-477-eod.yml"
WORKFLOWS = {
    "CORE": EOD,
    "KRONOS_V2": ".github/workflows/xray-personal-kronos-shadow.yml",
    "COVE": ".github/workflows/xray-personal-cove-shadow.yml",
    "OFFICIAL_477": EOD,
}
PRIMARY = {"CORE", "OFFICIAL_477"}
RECEIPT_KEYS = {"source", "asof", "eod_run_id", "eod_head_sha", "run",
                "result", "metrics"}
RUN_KEYS = {"id", "path", "repository", "branch", "head_sha", "attempt",
            "event", "status", "conclusion"}


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _valid_date(value):
    if type(value) is not str:
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _valid_id(value):
    return type(value) is int and 0 < value <= 2**53 - 1


def _valid_sha(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{40}", value) is not None


def _metrics(supplied, expected):
    """Do not accept bool as int; accept no fields that can leak raw data."""
    return (type(supplied) is dict and supplied.keys() == expected.keys()
            and all(type(supplied[k]) is type(v) and supplied[k] == v
                    for k, v in expected.items()))


def _evaluate(source, receipt, asof, eod_run_id, eod_head_sha):
    _require(receipt.keys() == RECEIPT_KEYS, "RECEIPT_SCHEMA")
    _require(receipt["asof"] == asof and _valid_id(receipt["eod_run_id"])
             and receipt["eod_run_id"] == eod_run_id
             and receipt["eod_head_sha"] == eod_head_sha, "SOURCE_EPOCH_MISMATCH")
    run = receipt["run"]
    _require(type(run) is dict and run.keys() == RUN_KEYS, "RUN_SCHEMA")
    _require(_valid_id(run["id"]) and (run["id"] == eod_run_id) == (source in PRIMARY)
             and run["path"] == WORKFLOWS[source]
             and run["repository"] == REPOSITORY and run["branch"] == "main"
             and run["head_sha"] == eod_head_sha
             and type(run["attempt"]) is int and run["attempt"] == 1
             and run["event"] == ("schedule" if source in PRIMARY else "workflow_run"),
             "RUN_IDENTITY_MISMATCH")
    _require(run["status"] == "completed" and run["conclusion"] == "success",
             "RUN_NOT_SUCCESSFUL")
    claimed = receipt["result"]
    metrics = receipt["metrics"]

    if source == "CORE":
        expected = {"requested": 477, "processed": 477, "valid": 477,
                    "missing": 0, "history_sessions": 52,
                    "feed": "ALPACA_IEX_RAW_1DAY", "calendar": "XNAS",
                    "final_ready": True, "guardian_verified": True,
                    "score_verified": True}
        _require(claimed == "CORE_EOD_READBACK_VERIFIED" and _metrics(metrics, expected),
                 "CORE_READBACK_UNVERIFIED")
        status = "MATCHED_CORE_RECEIPT"
    elif source == "KRONOS_V2":
        counts = ("full_geometry", "close_only", "qc_hold")
        _require(type(metrics) is dict and set(counts) <= metrics.keys()
                 and all(type(metrics[k]) is int and 0 <= metrics[k] <= 477 for k in counts),
                 "KRONOS_QUALITY_COUNTS")
        expected = {"symbols": 477, "rows": 1431, "horizons": [1, 5, 12],
                    **{k: metrics[k] for k in counts}}
        _require(_metrics(metrics, expected) and sum(expected[k] for k in counts) == 477
                 and all(type(h) is int for h in metrics["horizons"]), "KRONOS_SCOPE_COUNT")
        _require(expected["qc_hold"] == 0, "KRONOS_QC_HOLD")
        exact = "CLOSE_ONLY" if expected["close_only"] else "FULL_GEOMETRY"
        _require(claimed == "KRONOS2_PRIVATE_READBACK_" + exact,
                 "KRONOS_RECEIPT_QUALITY_MISMATCH")
        status = "MATCHED_" + exact
    elif source == "COVE":
        expected = {}
        _require(claimed == "READONLY_RESEARCH_PASS_NO_PUBLIC_METRICS"
                 and _metrics(metrics, expected), "COVE_READBACK_UNVERIFIED")
        status = "MATCHED_RESEARCH_READONLY"
    else:
        expected = {"rows": 477, "pit_verified": False, "market_clearance": False}
        _require(claimed == "RESEARCH_LEDGER_READBACK_PASS_NO_MARKET_CLEARANCE"
                 and _metrics(metrics, expected), "OFFICIAL_RESEARCH_RECEIPT_UNVERIFIED")
        status = "MATCHED_RESEARCH_NO_MARKET_CLEARANCE"

    return {"state": status, "reason": None, "observed_run_id": run["id"],
            "metrics": expected}


def observe(*, asof, eod_run_id, eod_head_sha, receipts):
    """Report each source independently. The caller verifies latest XNAS ASOF."""
    _require(_valid_date(asof) and _valid_id(eod_run_id) and _valid_sha(eod_head_sha),
             "INVALID_EXPECTED_EPOCH")
    _require(type(receipts) in (list, tuple) and len(receipts) <= 32, "RECEIPT_INPUT_LIMIT")
    groups = {source: [] for source in WORKFLOWS}
    ignored = 0
    for item in receipts:
        source = item.get("source") if type(item) is dict else None
        if type(source) is not str or source not in groups:
            ignored += 1
        else:
            groups[source].append(item)

    sources = {}
    for source, group in groups.items():
        if not group:
            sources[source] = {"state": "UNKNOWN", "reason": "RECEIPT_ABSENT"}
        elif len(group) != 1:
            sources[source] = {"state": "HOLD", "reason": "DUPLICATE_RECEIPT"}
        else:
            try:
                sources[source] = _evaluate(source, group[0], asof, eod_run_id, eod_head_sha)
            except ValueError as failure:
                sources[source] = {"state": "HOLD", "reason": str(failure)}
    return {"schema": SCHEMA, "asof": asof, "eod_run_id": eod_run_id,
            "eod_head_sha": eod_head_sha, "sources": sources,
            "ignored_receipt_count": ignored, "research_only": True,
            "source_authentication": "CALLER_WITNESS_NOT_ATTESTED",
            "decision_influence": "NO_GO", "may_notify": False,
            "may_publish": False, "may_write_sheet": False,
            "may_modify_al": False, "may_trade": False,
            "may_change_score": False, "may_change_stop_target": False,
            "may_clear_market": False}
