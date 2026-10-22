#!/usr/bin/env python3
"""Offline terminal PRICE candidate-partition regression (zero provider IO)."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

from build_current_terminal import (
    candidate_local_research_ready,
    terminal_price_partition_exact,
)


def need(condition, reason):
    if not condition:
        raise RuntimeError("TERMINAL_PRICE_PARTITION_SELFTEST_" + reason)


def fixture():
    names = ["AAPL", "MSFT", "ZZZZ"]
    master = {
        "asof_et": "2026-10-21",
        "queue_total": len(names),
        "queue_hash": "a" * 64,
        "pass_symbols": names,
    }
    price = {
        "asof_et": master["asof_et"],
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "source_master_count": len(names),
        "source_master_queue_hash": master["queue_hash"],
        "results": {
            "AAPL": {"status": "PASS_PRICE_DV30"},
            "MSFT": {"status": "UNKNOWN"},
            "ZZZZ": {"status": "FAIL_PRICE"},
        },
        "counts": {"PASS_PRICE_DV30": 1, "UNKNOWN": 1, "FAIL_PRICE": 1},
        "pass_symbols": ["AAPL"],
        "pass_count": 1,
        "pass_hash": sha256(b"AAPL").hexdigest(),
        "unknown_symbols": ["MSFT"],
        "unknown_count": 1,
        "blocked_symbols": [],
        "blocked_count": 0,
    }
    return price, master


def check():
    price, master = fixture()
    need(terminal_price_partition_exact(price, master),
         "UNRELATED_UNKNOWN_MUST_NOT_CORRUPT_EXACT_PARTITION")
    need(price["unknown_symbols"] == ["MSFT"]
         and price["results"]["MSFT"]["status"] == "UNKNOWN",
         "UNKNOWN_MUST_REMAIN_UNKNOWN")

    legal_key = "AAPL|A"
    final = {
        "results": {legal_key: {"candidate_legal_review_status": "PASS"}},
        "policy_semantics_exact": True,
        "lifecycle_semantics_exact": True,
        "candidate_legal_guard_exact_binding": True,
    }
    need(candidate_local_research_ready({legal_key}, {"status": "PASS"},
                                        final, True),
         "LOCAL_CANDIDATE_BLOCKED_BY_UNRELATED_UNKNOWN")
    need(not candidate_local_research_ready(set(), {"status": "PASS"},
                                            final, True),
         "ZERO_CANDIDATE_NOT_READY")
    need(not candidate_local_research_ready({legal_key}, {"status": "UNKNOWN"},
                                            final, True),
         "HALT_GUARD_MUST_FAIL_CLOSED")
    need(not candidate_local_research_ready({legal_key}, {"status": "PASS"},
                                            final, False),
         "MISSING_ALPHA_SOURCE_PROVENANCE")
    tampered_final = deepcopy(final)
    tampered_final["results"][legal_key]["candidate_legal_review_status"] = "UNKNOWN"
    need(not candidate_local_research_ready({legal_key}, {"status": "PASS"},
                                            tampered_final, True),
         "UNKNOWN_LEGAL_MUST_NOT_PASS")

    mutations = (
        ("UNKNOWN_COUNT", lambda p, m: p.update(unknown_count=0)),
        ("UNKNOWN_ROW", lambda p, m: p["results"]["MSFT"].update(status="PASS_PRICE_DV30")),
        ("PASS_SET", lambda p, m: p.update(pass_symbols=["AAPL", "MSFT"])),
        ("PASS_HASH", lambda p, m: p.update(pass_hash="0" * 64)),
        ("SOURCE_QUEUE", lambda p, m: p.update(source_master_queue_hash="b" * 64)),
        ("WRONG_EPOCH", lambda p, m: p.update(asof_et="2026-10-20")),
        ("MASTER_SCOPE", lambda p, m: m.update(pass_symbols=["AAPL", "MSFT"])),
        ("UNLISTED_RESULT", lambda p, m: p["results"].update(OTHER={"status": "UNKNOWN"})),
        ("BAD_SOURCE_COUNT", lambda p, m: p.update(source_master_count=2)),
        ("FAKE_PARTITION", lambda p, m: p["counts"].update(UNKNOWN=0)),
        ("NEGATIVE_BROKER_MODE", lambda p, m: p.update(execution="LIVE")),
        ("BAD_UNKNOWN_NEVER_PASS", lambda p, m: p.update(unknown_never_pass=False)),
    )
    for name, mutate in mutations:
        bad_price, bad_master = deepcopy(price), deepcopy(master)
        mutate(bad_price, bad_master)
        need(not terminal_price_partition_exact(bad_price, bad_master),
             "CORRUPT_" + name)

    no_pass = deepcopy(price)
    no_pass["results"]["AAPL"]["status"] = "UNKNOWN"
    no_pass.update(
        counts={"UNKNOWN": 2, "FAIL_PRICE": 1},
        pass_symbols=[], pass_count=0,
        pass_hash=sha256(b"").hexdigest(),
        unknown_symbols=["AAPL", "MSFT"], unknown_count=2,
    )
    need(terminal_price_partition_exact(no_pass, master),
         "ZERO_PASS_STRUCTURAL_PARTITION_VALID_BUT_NO_ALPHA")
    need(not candidate_local_research_ready(set(), {"status": "PASS"},
                                            final, True),
         "ZERO_PASS_NO_LOCAL_CANDIDATE")
    print("XRAY_TERMINAL_PRICE_PARTITION=PASS_12_NEGATIVES_LOCAL_POSITIVE_ZERO_PASS_NO_HTTP_NO_R92")


if __name__ == "__main__":
    check()
