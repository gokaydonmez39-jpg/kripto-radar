#!/usr/bin/env python3
"""Independent optimizer-safe regression for the deprecated SEC-only MC path.

Synthetic test records only; no SEC/API calls, production writes or orders.
Prove that a filing DATE alone cannot establish pre-close same-day knowledge,
and that share-class/CA-unverified entity shares cannot grant MC PASS or FAIL.
"""
from __future__ import annotations
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sec_mc

ASOF = "2026-10-09"


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise RuntimeError("SEC_MC_LEGACY_PIT_REGRESSION:" + reason)


def fixture(*rows):
    return {"facts": {"dei": {"EntityCommonStockSharesOutstanding": {
        "units": {"shares": list(rows)}}}}}


def fact(filed, val=200_000_000, end="2026-09-30", accession="0000000000-26-000001"):
    return {"end": end, "filed": filed, "form": "10-Q", "val": val, "accn": accession}


def test() -> None:
    prior = fixture(fact("2026-10-08"))
    same_day = fixture(fact(ASOF))
    old_get = sec_mc.get_json
    try:
        # Known preceding-day report remains an available observation (not MC authority).
        previous, error = sec_mc.latest_shares(prior, ASOF)
        require(error is None and previous["filed"] == "2026-10-08", "PREVIOUS_DAY_FACT_REJECTED")

        # Date-only current-day SEC fact has no acceptance clock and may
        # have been filed AFTER 16:00 ET: must NOT be accepted as of RTH close.
        selected, error = sec_mc.latest_shares(same_day, ASOF)
        require(selected is None and error is not None, "SAME_DAY_LOOKAHEAD_ACCEPTED")

        # Contradictory facts of identical accession+filed+measurement
        # cannot be last-write-wins. Preserve UNKNOWN.
        contradictory = fixture(
            fact("2026-10-08", 200_000_000),
            fact("2026-10-08", 300_000_000))
        selected, error = sec_mc.latest_shares(contradictory, ASOF)
        require(selected is None and error is not None, "CONTRADICTORY_SHARES_ACCEPTED")

        sec_mc.get_json = lambda *_a, **_k: copy.deepcopy(prior)
        for px in (12.00, 4.00, 10.50):
            status, info = sec_mc.classify_symbol("TEST", {"price": px, "cik": 320193}, ASOF)
            require(status not in {"PASS_SEC_CONSERVATIVE", "PASS", "FAIL_MC"},
                    "UNVERIFIED_CLASS_OR_CA_WAS_TERMINAL:" + status)
            require(status in {"SHADOW_SEC_MC_CLASS_CA_UNVERIFIED", "UNKNOWN_STATIC"},
                    "UNSAFE_UNEXPECTED_STATUS:" + status)

        # A prior state can carry stale optimistic classifications. It must
        # be demoted BEFORE any fresh incremental work and writeback.
        cached = {
            "A": {"status": "PASS_SEC_CONSERVATIVE", "info": {"market_cap_est": 2.5e9}},
            "B": {"status": "FAIL_MC", "info": {"market_cap_est": 1.2e9}},
            "C": {"status": "UNKNOWN_STATIC", "info": "MISSING"},
        }
        sec_mc.sanitize_legacy_results(cached)
        require(all(x["status"] not in {"PASS_SEC_CONSERVATIVE", "FAIL_MC"}
                    for x in cached.values()), "STALE_OPTIMISTIC_CACHE_RETAINED")
        require(cached["C"]["status"] == "UNKNOWN_STATIC", "UNRELATED_UNKNOWN_CHANGED")
    finally:
        sec_mc.get_json = old_get
    print("XRAY_SEC_LEGACY_PIT=PASS_PRE_CLOSE_UNKNOWN_CLASS_CA_UNKNOWN_DUPLICATE_UNKNOWN_CACHE_FAIL_CLOSED")


if __name__ == "__main__":
    test()
