#!/usr/bin/env python3
"""Personal Nasdaq EOD setup digest, deliberately separate from C4.17/R92.

Zero vendor IO. Uses the already-built exact-ASOF root research WATCH and
technical funnel. Triggers are observations; rejected geometry is never BUY.
The digest is small, stable, provenance-bound and suitable for safe read-only
review. No broker, no market execution, no device notification receipt.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent
SCHEMA = "XRAY_PERSONAL_EOD_RESEARCH_DIGEST_V1"
SHA = re.compile(r"[0-9a-f]{40}\Z")
S256 = re.compile(r"[0-9a-f]{64}\Z")
VALID_RESULT = frozenset((
    "NO_CONFIRMED_A_B_D_RECENT_TRIGGER",
    "NO_CURRENT_OR_RECENT_WEEKLY_GATE",
    "TECHNICAL_GEOMETRY_NOT_APPROVED",
    "UNKNOWN_260_OFFICIAL_HISTORY",
    "TECHNICAL_FAMILY_RESEARCH_ONLY_RELEASE_GATES_OPEN",
))
NO_BUY = {"execution": "NONE", "real_money": "NO-GO",
          "broker": False, "orders": [], "registered_r92_count": 0,
          "certified_C417_AL_signal_count": 0,
          "iphone_receipt_attested": False, "unknown_never_pass": True}


def require(condition, code):
    if not condition:
        raise ValueError("XRAY_PERSONAL_EOD_DIGEST_" + code)


def sha256_lines(xs):
    return hashlib.sha256("\n".join(xs).encode()).hexdigest()


def build(root, master, price, blob_ids):
    require(all(SHA.fullmatch(blob_ids.get(k, "")) for k in
                ("root", "master", "price")), "EXACT_GIT_BLOBS")
    asof = root.get("asof_et")
    watch = root.get("watch_radar") or {}
    tech = root.get("candidate_technical_funnel") or {}
    require(isinstance(asof, str) and re.fullmatch(r"20\d\d-\d\d-\d\d", asof)
            and asof == watch.get("asof_et") == tech.get("asof_et")
            == master.get("asof_et") == price.get("asof_et"), "SAME_ASOF")
    require(all(d.get("execution") == "NONE" and
                d.get("real_money") == "NO-GO" for d in
                (root, watch, tech, master, price)), "RESEARCH_EXECUTION_ONLY")
    require(all(d.get("unknown_never_pass") is True for d in
                (watch, tech, master, price)), "UNKNOWN_NEVER_PASS")
    require(master.get("pass_count") == len(master.get("pass_symbols", []))
            and master.get("pass_symbols") ==
                sorted(set(master.get("pass_symbols", []))), "MASTER_MEMBERS")
    require(price.get("source_master_queue_hash") == master.get("queue_hash")
            and price.get("source_master_count") == master.get("pass_count"),
            "PRICE_MASTER_LINK")
    wrows = watch.get("watchlist")
    trows = tech.get("results")
    require(isinstance(wrows, list) and isinstance(trows, dict)
            and len(wrows) == watch.get("watchlist_count")
            == watch.get("price_liquidity_screened_count")
            == tech.get("candidate_count") == tech.get("attempted_count")
            and tech.get("evaluated_count") + tech.get("pending_count")
                == len(wrows)
            and watch.get("all_eligible_candidates_tracked") is True
            and watch.get("watchlist_cap") is None
            and watch.get("registered_r92_count") == 0
            and tech.get("registered_r92_count") == 0
            and tech.get("final_buy_signal_count") == 0
            and tech.get("final_buy_signals") == []
            and tech.get("automatic_orders") == []
            and watch.get("orders") == [], "NO_FALSE_ALPHA_OR_TRUNCATION")
    digest = watch.get("watchlist_digest", "")
    require(S256.fullmatch(digest) and digest == tech.get("watchlist_digest")
            and S256.fullmatch(watch.get("source_candidates_sha256", ""))
            and watch.get("source_candidates_sha256") ==
                tech.get("source_candidates_sha256"), "EXACT_WATCH_TECH_LINEAGE")
    names = [row.get("symbol") for row in wrows if isinstance(row, dict)]
    require(len(names) == len(wrows) and len(set(names)) == len(names)
            and all(isinstance(s, str) and re.fullmatch("[A-Z0-9.]+", s)
                    for s in names)
            and set(names).issubset(set(master["pass_symbols"]))
            and set(trows) == set(names), "WATCH_SYMBOL_PROVENANCE")
    require(all(row["classification"] == "WATCH_LIQUIDITY_PRE_SCREEN_ONLY"
                and row.get("buy_signal") is False
                and row.get("setup_confirmation") == "NOT_EVALUATED_HERE"
                for row in wrows), "WATCH_NEVER_BUY")
    statuses = Counter(row.get("status") for row in trows.values())
    require(set(statuses).issubset(VALID_RESULT)
            and sum(statuses.values()) == len(names)
            and statuses.get("UNKNOWN_260_OFFICIAL_HISTORY", 0)
                == tech.get("pending_count")
            and sorted(tech.get("pending_symbols", [])) ==
                sorted(s for s in names
                       if trows[s].get("status") == "UNKNOWN_260_OFFICIAL_HISTORY"),
            "TECHNICAL_PARTITION_EXACT")
    trigger = tech.get("recent_a_b_d_trigger_symbols", [])
    require(isinstance(trigger, list)
            and len(trigger) == len(set(trigger)) ==
                tech.get("recent_a_b_d_trigger_count")
            and set(trigger).issubset(set(names)), "TRIGGER_SET_EXACT")
    triggers, setups = [], []
    for sym in trigger:
        item = trows[sym]
        families = item.get("confirmed_families")
        fr = item.get("family_results") or {}
        require(item.get("status") in (
                    "TECHNICAL_GEOMETRY_NOT_APPROVED",
                    "TECHNICAL_FAMILY_RESEARCH_ONLY_RELEASE_GATES_OPEN")
                and isinstance(families, list) and families
                and set(families) == set(fr)
                and set(families).issubset({"A", "B", "C", "D"}),
                "TRIGGER_FAMILY_PROVENANCE")
        blockers, audited = set(), True
        for family in families:
            record = fr[family]
            audit = record.get("independent_geometry_audit") or {}
            require(record.get("final_AL") is False
                    and record.get("diagnostic_only_not_trade_signal") is True,
                    "OBSERVATION_NOT_BUY")
            audited = audited and (
                audit.get("status") == "PASS_INDEPENDENT_FORMULA_AUDIT"
                and audit.get("independently_verified") is True)
            blockers.update(record.get("diagnostic_blockers") or [])
        # A family-trigger scan by itself never clears event, regime or RR.
        eligible = (item.get("status") ==
                    "TECHNICAL_FAMILY_RESEARCH_ONLY_RELEASE_GATES_OPEN"
                    and item.get("technical_observation_ready") is True
                    and audited and not blockers)
        out = {
            "symbol": sym,
            "families": sorted(families),
            "source": item.get("history_source"),
            "math_formula_audited": bool(audited),
            "status": ("RESEARCH_SETUP_CANDIDATE" if eligible
                       else "TRIGGER_OBSERVED_NOT_APPROVED"),
            "technical_source_confidence": "LIMITED_SECONDARY_EOD",
            "unresolved_or_rejected": sorted(blockers),
            "not_a_trade_or_R92": True,
        }
        triggers.append(out)
        if eligible:
            setups.append(sym)
    require(len(triggers) == tech["recent_a_b_d_trigger_count"],
            "TRIGGER_COUNT_CHANGED")
    # Even a research candidate cannot be a genuine R92; it needs separate
    # source/event/MC validation for any future independent notification.
    return {
        "schema": SCHEMA,
        "asof_et": asof,
        "status": ("PERSONAL_RESEARCH_SETUP_CANDIDATES_AVAILABLE" if setups
                   else "PERSONAL_LIQUIDITY_WATCH_AND_REJECTED_TRIGGERS"),
        "mode": "PERSONAL_NONCOMMERCIAL_RESEARCH_ONLY",
        "source_epoch_blobs": dict(blob_ids),
        "source_candidates_sha256": watch["source_candidates_sha256"],
        "watchlist_digest": digest,
        "watchlist_count": len(names),
        "technical_evaluated_count": tech["evaluated_count"],
        "technical_pending_symbols": sorted(tech["pending_symbols"]),
        "technical_state_counts": dict(sorted(statuses.items())),
        "research_setup_candidate_symbols": sorted(setups),
        "research_setup_candidate_count": len(setups),
        "recent_technical_trigger_count": len(triggers),
        "recent_technical_triggers": sorted(triggers, key=lambda x: x["symbol"]),
        "liquidity_watch_symbols": names,
        "source_confidence": {
            "grade": "LOW",
            "rationale": "Existing SINA price observations and calendar-bound formula audits; independent original RTH volume, split lineage, primary MC and event clearance unproven",
            "source_quality_not_probability": True,
        },
        "automated_alert_authority": False,
        "candidate_setup_is_not_R92": True,
        "no_raw_ohlcv_or_levels_exported": True,
        **NO_BUY,
    }


def mutation_watch_case(root, master, *, false_buy=False):
    """Construct a valid-shaped WATCH fixture even when live WATCH is empty.

    This changes only the local deep-copied negative-test input. It never
    fabricates a production watchlist or a research candidate.
    """
    symbol = (master.get("pass_symbols") or ["AAPL"])[0]
    row = {"symbol": symbol,
           "classification": "WATCH_LIQUIDITY_PRE_SCREEN_ONLY",
           "buy_signal": bool(false_buy),
           "setup_confirmation": "NOT_EVALUATED_HERE"}
    n = 1 if false_buy else 2
    watch = root["watch_radar"]
    tech = root["candidate_technical_funnel"]
    watch["watchlist"] = [deepcopy(row) for _ in range(n)]
    watch["watchlist_count"] = n
    watch["price_liquidity_screened_count"] = n
    tech["candidate_count"] = n
    tech["attempted_count"] = n
    tech["evaluated_count"] = n
    tech["pending_count"] = 0
    tech["pending_symbols"] = []
    tech["results"] = {symbol: {"status": "NO_CONFIRMED_A_B_D_RECENT_TRIGGER"}}
    tech["recent_a_b_d_trigger_symbols"] = []
    tech["recent_a_b_d_trigger_count"] = 0


def selftest(root, master, price, blobs):
    result = build(root, master, price, blobs)
    require(result["watchlist_count"] == len(
        root["watch_radar"]["watchlist"])
        and result["certified_C417_AL_signal_count"] == 0
        and result["automated_alert_authority"] is False
        and result["no_raw_ohlcv_or_levels_exported"] is True,
        "POSITIVE")
    # Producer-pending rows must stay non-buy, and every rejected research
    # trigger must expose at least one diagnostic blocker for downstream QA.
    require(sorted(result["technical_pending_symbols"]) ==
            sorted(root["candidate_technical_funnel"]["pending_symbols"]),
            "TEST_ORIGINAL_PENDING_SET_NOT_PRESERVED")
    require(all(row["status"] != "TRIGGER_OBSERVED_NOT_APPROVED"
                or bool(row["unresolved_or_rejected"])
                for row in result["recent_technical_triggers"]),
            "TEST_UNEXPLAINED_REJECTED_TRIGGER")

    for label, change in (
        ("ASOF", lambda a,b,c:a.update(asof_et="2026-09-01")),
        ("NO_AL", lambda a,b,c:a["watch_radar"].update(registered_r92_count=1)),
        ("DUP_TICKER", lambda a,b,c:mutation_watch_case(a, b, false_buy=False)),
        ("FALSE_BUY", lambda a,b,c:mutation_watch_case(a, b, false_buy=True)),
        ("SOURCE", lambda a,b,c:a["candidate_technical_funnel"].update(
            watchlist_digest="INVALID_DIGEST")),
        ("TRUNCATE", lambda a,b,c:a["watch_radar"].update(watchlist_cap=100)),
        ("PENDING", lambda a,b,c:a["candidate_technical_funnel"].update(
            pending_count=a["candidate_technical_funnel"]["pending_count"] + 1)),
        ("PRICE", lambda a,b,c:c.update(source_master_count=b["pass_count"] + 1)),
        ("MASTER", lambda a,b,c:b["pass_symbols"].append("INVALID!")),
        ("TRIGGER", lambda a,b,c:a["candidate_technical_funnel"][
            "recent_a_b_d_trigger_symbols"].append("UNPROVEN")),
    ):
        a,b,c = deepcopy(root),deepcopy(master),deepcopy(price)
        change(a,b,c)
        try:
            build(a,b,c,blobs)
        except ValueError as exc:
            expected = {
                "DUP_TICKER": "XRAY_PERSONAL_EOD_DIGEST_WATCH_SYMBOL_PROVENANCE",
                "FALSE_BUY": "XRAY_PERSONAL_EOD_DIGEST_WATCH_NEVER_BUY",
            }.get(label)
            if expected is not None and str(exc) != expected:
                raise AssertionError("WRONG_NEGATIVE_CAUSE_" + label) from exc
        else:
            raise AssertionError("FALSE_RESEARCH_DIGEST_PASS_"+label)
    print("XRAY_PERSONAL_RESEARCH_DIGEST_SELFTEST=PASS_10_MUTATIONS_NO_VENDOR_NO_FALSE_BUY")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    files = {"root": ROOT/"orchestrator_state.json",
             "master": ROOT/"canonical_current_master_manifest.json",
             "price": ROOT/"canonical_current_price_dv30.json"}
    blobs = {k: subprocess.check_output(["git","hash-object",str(path)],
        cwd=ROOT.parent, text=True).strip() for k,path in files.items()}
    j = {k: json.loads(path.read_text()) for k,path in files.items()}
    if a.selftest:
        require(a.out is None, "NO_TEST_ARTIFACT")
        selftest(j["root"], j["master"], j["price"], blobs)
        return
    require(a.out is not None, "OUTPUT_REQUIRED")
    report = build(j["root"], j["master"], j["price"], blobs)
    a.out.write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                sort_keys=True)+"\n")
    print("XRAY_PERSONAL_RESEARCH_WATCH=" + str(report["watchlist_count"]))
    print("XRAY_PERSONAL_RESEARCH_TRIGGERS=" + str(report["recent_technical_trigger_count"]))
    print("XRAY_PERSONAL_RESEARCH_SETUPS=" + str(report["research_setup_candidate_count"]))
    print("XRAY_PERSONAL_RESEARCH_DATA_CONFIDENCE=" + report["source_confidence"]["grade"])


if __name__ == "__main__":
    main()
