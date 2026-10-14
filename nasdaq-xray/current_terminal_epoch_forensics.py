#!/usr/bin/env python3
"""Exact-source, read-only explanation of a stale canonical XRAY terminal.

A last-authoritative terminal must never be rewritten to the research ASOF
without a complete current C4.17 MC/HISTORY/LEGAL/FINAL proof chain.
This module reports CURRENT diagnostic blockers without minting AL/R92.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASK = "6a825366222081918997094d76e6ae46"
SCHEMA = "XRAY_CURRENT_TERMINAL_EPOCH_FORENSICS_V1"
FILES = {
    "orchestrator": ROOT / "orchestrator_state.json",
    "master": ROOT / "canonical_current_master_manifest.json",
    "price": ROOT / "canonical_current_price_dv30.json",
    "history": ROOT / "canonical_current_history.json",
    "terminal": ROOT / "canonical_current_terminal.json",
}


def need(ok, why):
    if not ok:
        raise ValueError("XRAY_CURRENT_EPOCH_" + why)


def blob(path):
    b = path.read_bytes()
    return hashlib.sha1((f"blob {len(b)}" + chr(0)).encode() + b).hexdigest()


def collect(root):
    documents = {}
    proof = {}
    for name, original in FILES.items():
        path = root / original.name
        raw = path.read_bytes()
        documents[name] = json.loads(raw)
        proof[name] = {
            "path": "nasdaq-xray/" + path.name,
            "git_blob_sha": hashlib.sha1(
                (f"blob {len(raw)}" + chr(0)).encode() + raw
            ).hexdigest(),
        }
    return assess(documents, proof)


def assess(d, proof):
    for name in FILES:
        need(name in d and isinstance(d[name], dict), "MISSING_" + name.upper())
        row = d[name]
        need(row.get("task_id") == TASK, "TASK_ID_" + name.upper())
        need(row.get("execution") == "NONE"
             and row.get("real_money") == "NO-GO", "SAFETY_" + name.upper())
        need(isinstance(row.get("asof_et"), str) and
             len(row["asof_et"]) == 10, "ASOF_" + name.upper())
    root, master, price = (d["orchestrator"], d["master"], d["price"])
    last_history, last_terminal = d["history"], d["terminal"]
    asof = root["asof_et"]
    # The daily root may legitimately advance while canonical master/price
    # remain on the last settled session. Diagnose this as a BLOCKER rather
    # than throwing before a read-only stale-terminal report can be emitted.
    # Master and PRICE must STILL form an internally exact single epoch.
    need(master["asof_et"] == price["asof_et"], "MASTER_PRICE_EPOCH_DRIFT")
    root_epoch_aligned = master["asof_et"] == asof
    if not root_epoch_aligned:
        need(asof > master["asof_et"], "ROOT_OLDER_THAN_CANONICAL_SOURCES")
    need(master.get("queue_hash") == price.get("source_master_queue_hash") and
         (not root_epoch_aligned or root.get("queue_hash") == master.get("queue_hash")),
         "MASTER_PRICE_QUEUE_HASH_MISMATCH")
    scope = master.get("queue_total")
    need(type(scope) is int and scope > 0 and
         price.get("source_master_count") == scope and
         (not root_epoch_aligned or root.get("queue_total") == scope),
         "MASTER_PRICE_QUEUE_COUNT_MISMATCH")
    symbols = master.get("pass_symbols")
    need(isinstance(symbols, list) and len(symbols) == scope and
         symbols == sorted(set(symbols)) and
         master.get("pass_count") == scope and
         hashlib.sha256("\n".join(symbols).encode()).hexdigest() ==
             master["queue_hash"], "MASTER_QUEUE_INTEGRITY")
    rows = price.get("results")
    need(isinstance(rows, dict) and len(rows) == scope,
         "PRICE_FULL_SCOPE_PARTITION_MISSING")
    need(set(rows) == set(symbols), "PRICE_MASTER_SYMBOL_SET_MISMATCH")
    need(all(isinstance(v, dict) for v in rows.values()),
         "PRICE_RESULT_RECORD_INVALID")
    counts = collections.Counter(v.get("status") for v in rows.values())
    need(all(isinstance(k, str) and
             (k in {"UNKNOWN", "PASS_PRICE_DV30", "BLOCK_CURRENT_RUN"}
              or k.startswith("FAIL_")) for k in counts),
         "PRICE_RESULT_STATUS_INVALID")
    need(price.get("counts") == dict(counts), "PRICE_COUNTS_MISMATCH")
    unknown = price.get("unknown_symbols")
    passing = price.get("pass_symbols")
    blocked = price.get("blocked_symbols")
    need(isinstance(unknown, list) and unknown == sorted(set(unknown)) and
         set(unknown) == {s for s, v in rows.items()
                          if v.get("status") == "UNKNOWN"},
         "PRICE_UNKNOWN_SET_MISMATCH")
    need(price.get("unknown_count") == len(unknown),
         "PRICE_UNKNOWN_COUNT_MISMATCH")
    need(isinstance(passing, list) and passing == sorted(set(passing)) and
         set(passing) == {s for s, v in rows.items()
                          if v.get("status") == "PASS_PRICE_DV30"} and
         price.get("pass_count") == len(passing) and
         price.get("pass_hash") ==
             hashlib.sha256("\n".join(passing).encode()).hexdigest(),
         "PRICE_PASS_PARTITION_MISMATCH")
    need(isinstance(blocked, list) and blocked == sorted(set(blocked)) and
         set(blocked) == {s for s, v in rows.items()
                          if v.get("status") == "BLOCK_CURRENT_RUN"} and
         price.get("blocked_count", len(blocked)) == len(blocked),
         "PRICE_BLOCK_PARTITION_MISMATCH")
    need(not (set(passing) & (set(blocked) | set(unknown))),
         "PRICE_PARTITION_OVERLAP")
    need(last_history["asof_et"] <= asof and last_terminal["asof_et"] <= asof,
         "FUTURE_DOWNSTREAM_EPOCH")
    reasons = collections.Counter(
        str((rows[s].get("info") or {}).get("reason") or "UNSPECIFIED")
        for s in unknown
    )
    tech = root.get("candidate_technical_funnel") or {}
    watch = root.get("watch_radar") or {}
    total_watch = watch.get("watchlist_count")
    done = tech.get("evaluated_count")
    pending = tech.get("pending_count")
    need(type(total_watch) is int and type(done) is int and
         type(pending) is int and done + pending == total_watch,
         "CANDIDATE_PARTITION")
    pending_syms = tech.get("pending_symbols") or []
    need(len(pending_syms) == pending and
         len(set(pending_syms)) == pending, "PENDING_SET_MISMATCH")
    blockers = []
    if not root_epoch_aligned:
        blockers.append("ROOT_MASTER_PRICE_EPOCH_DRIFT")
    if root.get("unknown_count") != 0:
        blockers.append("ROOT_HISTORY_NOT_FULLY_RESOLVED")
    if master.get("unknown_count") != 0:
        blockers.append("MASTER_IDENTITY_UNRESOLVED")
    if len(unknown):
        blockers.append("PRICE_DV30_PRIMARY_SOURCE_UNRESOLVED")
    if last_history["asof_et"] < asof:
        blockers.append("HISTORY_NOT_CURRENT_ASOF")
    if last_terminal["asof_et"] < asof:
        blockers.append("TERMINAL_NOT_CURRENT_ASOF")
    if pending:
        blockers.append("RESEARCH_TECHNICAL_PENDING")
    # This artifact never evaluates or bypasses independent MC/G9/Event/R92 gates.
    return {
        "schema": SCHEMA,
        "source_asof_et": asof,
        "canonical_master_asof_et": master["asof_et"],
        "canonical_price_asof_et": price["asof_et"],
        "current_root_master_price_epoch_aligned": root_epoch_aligned,
        "last_authoritative_terminal_asof_et": last_terminal["asof_et"],
        "last_canonical_history_asof_et": last_history["asof_et"],
        "latest_master_unknown_count": master.get("unknown_count"),
        "latest_price_unknown_count": len(unknown),
        "latest_price_unknown_reason_counts": dict(sorted(reasons.items())),
        "current_price_primary_pass_count": (price.get("pass_count")
                                              if root_epoch_aligned else None),
        "previous_epoch_price_pass_count": (price.get("pass_count")
                                             if not root_epoch_aligned else None),
        "root_history_unknown_count": root.get("unknown_count"),
        "research_watch_count": total_watch,
        "research_evaluated_count": done,
        "research_pending_count": pending,
        "research_pending_symbols": pending_syms,
        "current_asof_terminal_generated": False,
        "historical_terminal_not_current_evidence": last_terminal["asof_et"] != asof,
        "diagnostic_blockers": blockers,
        "status": ("MIXED_SOURCE_EPOCH_FAIL_CLOSED_LAST_TERMINAL_STALE"
                   if not root_epoch_aligned else
                   "CURRENT_UPSTREAM_BLOCKED_LAST_TERMINAL_STALE"
                   if blockers else "UPSTREAM_DIAGNOSTICS_ONLY_FINAL_UNATTESTED"),
        "source_git_blobs": proof,
        "canonical_terminal_overwritten": False,
        "mc_primary_approved_by_report": False,
        "g9_approved_by_report": False,
        "r92_created_by_report": False,
        "iphone_delivery_proven_by_report": False,
        "execution": "NONE",
        "real_money": "NO-GO",
    }


def selftest():
    symbols = ["AAPL", "BSP"]
    def base(name, asof):
        return {"task_id": TASK, "asof_et": asof,
                "execution": "NONE", "real_money": "NO-GO"}
    root = base("root", "2026-10-13")
    queue_hash = hashlib.sha256("\n".join(symbols).encode()).hexdigest()
    root.update(queue_total=2, queue_hash=queue_hash, unknown_count=1,
                watch_radar={"watchlist_count": 2},
                candidate_technical_funnel={
                    "evaluated_count": 1, "pending_count": 1,
                    "pending_symbols": ["BSP"]})
    master = base("master", "2026-10-13")
    master.update(queue_total=2, queue_hash=queue_hash, unknown_count=1,
                  pass_count=2, pass_symbols=symbols)
    price = base("price", "2026-10-13")
    price.update(source_master_count=2, source_master_queue_hash=queue_hash,
                 results={"AAPL": {"status": "UNKNOWN",
                                    "info": {"reason": "AUTHENTICATED_SIP_RESOLVER_BRIDGE_REQUIRED"}},
                          "BSP": {"status": "FAIL_DV30"}},
                 unknown_symbols=["AAPL"], unknown_count=1,
                 counts={"UNKNOWN": 1, "FAIL_DV30": 1},
                 pass_count=0, pass_symbols=[],
                 pass_hash=hashlib.sha256(b"").hexdigest(),
                 blocked_count=0, blocked_symbols=[])
    docs = {"orchestrator": root, "master": master, "price": price,
            "history": base("history", "2026-10-07"),
            "terminal": base("terminal", "2026-10-07")}
    proof = {k: {"path": k, "git_blob_sha": "a" * 40} for k in FILES}
    actual = assess(docs, proof)
    need(actual["status"] == "CURRENT_UPSTREAM_BLOCKED_LAST_TERMINAL_STALE"
         and actual["latest_price_unknown_reason_counts"] ==
             {"AUTHENTICATED_SIP_RESOLVER_BRIDGE_REQUIRED": 1}
         and actual["diagnostic_blockers"] ==
             ["ROOT_HISTORY_NOT_FULLY_RESOLVED",
              "MASTER_IDENTITY_UNRESOLVED",
              "PRICE_DV30_PRIMARY_SOURCE_UNRESOLVED",
              "HISTORY_NOT_CURRENT_ASOF",
              "TERMINAL_NOT_CURRENT_ASOF",
              "RESEARCH_TECHNICAL_PENDING"], "SOURCE_STALE_CAUSAL_MAP")
    import copy
    for label, change in (
        ("unknown_underreport", lambda v: v["price"].update(unknown_count=0)),
        ("unknown_missing_row", lambda v: v["price"]["results"].pop("AAPL")),
        ("root_price_asof", lambda v: v["price"].update(asof_et="2026-10-07")),
        ("queue_hash", lambda v: v["master"].update(queue_hash="OTHER")),
        ("terminal_future", lambda v: v["terminal"].update(asof_et="2026-10-14")),
        ("candidate_partition", lambda v: v["orchestrator"]["candidate_technical_funnel"].update(evaluated_count=2)),
        ("master_price_epoch", lambda v: v["price"].update(asof_et="2026-10-12")),
        ("unsafe_execution", lambda v: v["price"].update(execution="LIVE")),
        ("master_queue_drift", lambda v: v["master"]["pass_symbols"].__setitem__(0, "ZZZ")),
        ("pass_count_lie", lambda v: v["price"].update(pass_count=1)),
        ("counts_lie", lambda v: v["price"]["counts"].update(UNKNOWN=0)),
        ("pass_hash_lie", lambda v: v["price"].update(pass_hash="0" * 64)),
        ("unrecognized_status", lambda v: v["price"]["results"]["BSP"].update(status="PASS")),
        ("blocked_set_lie", lambda v: v["price"].update(blocked_symbols=["BSP"])),
    ):
        tampered = copy.deepcopy(docs)
        change(tampered)
        try:
            assess(tampered, proof)
        except ValueError:
            pass
        else:
            raise AssertionError("MALFORMED_FORENSICS_ACCEPTED_" + label)
    # A rollover on the root alone must emit a meaningful blocker report.
    # It may never import stale canonical PRICE into the current epoch.
    mixed = copy.deepcopy(docs)
    mixed["orchestrator"]["asof_et"] = "2026-10-14"
    mixed["orchestrator"]["queue_hash"] = "new-session-unsettled"
    mixed["orchestrator"]["queue_total"] = 3186
    mixed["orchestrator"]["unknown_count"] = 3185
    mixed_result = assess(mixed, proof)
    need(mixed_result["status"] ==
         "MIXED_SOURCE_EPOCH_FAIL_CLOSED_LAST_TERMINAL_STALE"
         and mixed_result["current_root_master_price_epoch_aligned"] is False
         and mixed_result["current_price_primary_pass_count"] is None
         and mixed_result["previous_epoch_price_pass_count"] == 0
         and mixed_result["diagnostic_blockers"][0] ==
         "ROOT_MASTER_PRICE_EPOCH_DRIFT"
         and "ROOT_HISTORY_NOT_FULLY_RESOLVED" in
         mixed_result["diagnostic_blockers"]
         and mixed_result["r92_created_by_report"] is False,
         "MIXED_EPOCH_FAIL_CLOSED_DIAGNOSTIC")
    # A canonical input from the FUTURE relative to root is corruption.
    mixed_bad = copy.deepcopy(docs)
    mixed_bad["orchestrator"]["asof_et"] = "2026-10-12"
    try:
        assess(mixed_bad, proof)
    except ValueError as exc:
        need("ROOT_OLDER_THAN_CANONICAL_SOURCES" in str(exc),
             "MIXED_EPOCH_NEGATIVE_REASON")
    else:
        raise AssertionError("BACKWARD_ROOT_EPOCH_ACCEPTED")
    ready = copy.deepcopy(docs)
    ready["orchestrator"]["unknown_count"] = 0
    ready["master"]["unknown_count"] = 0
    ready["price"]["unknown_count"] = 0
    ready["price"]["unknown_symbols"] = []
    ready["price"]["results"]["AAPL"] = {"status": "PASS_PRICE_DV30"}
    ready["price"]["counts"] = {"PASS_PRICE_DV30": 1, "FAIL_DV30": 1}
    ready["price"]["pass_count"] = 1
    ready["price"]["pass_symbols"] = ["AAPL"]
    ready["price"]["pass_hash"] = hashlib.sha256(b"AAPL").hexdigest()
    ready["history"]["asof_et"] = ready["terminal"]["asof_et"] = "2026-10-13"
    ready["orchestrator"]["candidate_technical_funnel"].update(
        evaluated_count=2, pending_count=0, pending_symbols=[])
    clear = assess(ready, proof)
    need(clear["status"] == "UPSTREAM_DIAGNOSTICS_ONLY_FINAL_UNATTESTED"
         and clear["r92_created_by_report"] is False
         and clear["g9_approved_by_report"] is False, "DIAGNOSTIC_NEVER_FINAL_PASS")
    print("XRAY_CURRENT_EPOCH_FORENSICS_SELFTEST=PASS_MIXED_EPOCH_DIAGNOSTIC_15_NEGATIVES_NO_ALPHA")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--out")
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    need(bool(args.out), "EPHEMERAL_OUT_REQUIRED")
    destination = Path(args.out).resolve()
    need(ROOT not in destination.parents and destination != ROOT,
         "NO_REPO_PUBLICATION_WITHOUT_CANONICAL_AUTHORITY")
    result = collect(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("XRAY_CURRENT_EPOCH_FORENSICS_COUNTS=" +
          json.dumps({k: result[k] for k in (
              "source_asof_et", "last_authoritative_terminal_asof_et",
              "latest_master_unknown_count", "latest_price_unknown_count",
              "latest_price_unknown_reason_counts", "root_history_unknown_count",
              "research_watch_count", "research_evaluated_count",
              "research_pending_count", "diagnostic_blockers", "status"
          )}, sort_keys=True))
    print("XRAY_CURRENT_EPOCH_REPORT_NO_ALPHA=PASS_EPHEMERAL_READ_ONLY")


if __name__ == "__main__":
    main()
