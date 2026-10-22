#!/usr/bin/env python3
"""Offline regression: zero, one or two WATCH candidates must not crash digest selftest.

No vendor IO, no execution, no real R92, no output artifact or broker.
"""
import importlib.util
from pathlib import Path

root_dir = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "personal_research_signal_digest", root_dir / "personal_research_signal_digest.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(n):
    symbols = ["AAPL", "NVDA"][:n]
    common = {"asof_et": "2026-10-22", "execution": "NONE",
              "real_money": "NO-GO", "unknown_never_pass": True}
    sha = "a" * 64
    watch_hash = "b" * 64
    candidate_hash = "c" * 64
    watch = dict(common,
                 watchlist=[{"symbol": sym,
                             "classification": "WATCH_LIQUIDITY_PRE_SCREEN_ONLY",
                             "buy_signal": False,
                             "setup_confirmation": "NOT_EVALUATED_HERE"}
                            for sym in symbols],
                 watchlist_count=n, price_liquidity_screened_count=n,
                 all_eligible_candidates_tracked=True, watchlist_cap=None,
                 registered_r92_count=0, orders=[],
                 watchlist_digest=watch_hash, source_candidates_sha256=candidate_hash)
    tech = dict(common, results={sym: {"status": "NO_CONFIRMED_A_B_D_RECENT_TRIGGER"}
                                 for sym in symbols},
                candidate_count=n, attempted_count=n, evaluated_count=n, pending_count=0,
                pending_symbols=[], registered_r92_count=0, final_buy_signal_count=0,
                final_buy_signals=[], automatic_orders=[], watchlist_digest=watch_hash,
                source_candidates_sha256=candidate_hash,
                recent_a_b_d_trigger_symbols=[], recent_a_b_d_trigger_count=0)
    orchestrator = dict(common, watch_radar=watch, candidate_technical_funnel=tech)
    master = dict(common, pass_symbols=["AAPL", "NVDA"], pass_count=2, queue_hash=sha)
    price = dict(common, source_master_queue_hash=sha, source_master_count=2)
    blobs = {"root": "d" * 40, "master": "e" * 40, "price": "f" * 40}
    return orchestrator, master, price, blobs


def main():
    for n in (0, 1, 2):
        root, master, price, blobs = fixture(n)
        report = module.build(root, master, price, blobs)
        if not (report["watchlist_count"] == n
                and report["registered_r92_count"] == 0
                and report["automated_alert_authority"] is False):
            raise AssertionError("INVALID_FIXTURE_OR_FALSE_ALERT:" + str(n))
        module.selftest(root, master, price, blobs)
    print("XRAY_DIGEST_EMPTY_SINGLE_DOUBLE_WATCH_SELFTEST=PASS_3_SIZES"
          "_10_NEGATIVES_EACH_NO_FALSE_BUY")


if __name__ == "__main__":
    main()
