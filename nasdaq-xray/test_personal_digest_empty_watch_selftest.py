#!/usr/bin/env python3
"""Offline regression: zero, one or two WATCH candidates must not crash digest selftest.

No vendor IO, no execution, no real R92, no output artifact or broker.
"""
import importlib.util
import json
from pathlib import Path
import subprocess

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
    tech = dict(common, results={sym: {"status": "NO_CONFIRMED_A_B_D_RECENT_TRIGGER", "terminal_scan": True}
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



def producer_mixed_status_adversarial():
    """Reproduce official producer's legitimate terminal + retryable split."""
    import copy
    root, master, price, blobs = fixture(2)
    tech = root["candidate_technical_funnel"]
    tech["results"]["AAPL"] = {
        "status": "UNKNOWN_FROZEN_TECHNICAL_GEOMETRY",
        "terminal_scan": False,
        "confirmed_families": ["A"],
        "family_results": {
            "A": {
                "final_AL": False,
                "diagnostic_only_not_trade_signal": True,
                "independent_geometry_audit": {"status": "UNKNOWN",
                                               "independently_verified": False},
                "diagnostic_blockers": [],
            }
        },
        "technical_observation_ready": False,
    }
    tech["pending_count"] = 1
    tech["evaluated_count"] = 1
    tech["pending_symbols"] = ["AAPL"]
    tech["recent_a_b_d_trigger_symbols"] = ["AAPL"]
    tech["recent_a_b_d_trigger_count"] = 1
    out = module.build(root, master, price, blobs)
    if not (out["technical_pending_symbols"] == ["AAPL"]
            and out["research_setup_candidate_count"] == 0
            and out["registered_r92_count"] == 0
            and out["automated_alert_authority"] is False):
        raise AssertionError("FALSE_PROMOTION_OR_PENDING_LOSS")
    if not (out["recent_technical_triggers"][0]["status"] ==
            "TRIGGER_OBSERVED_NOT_APPROVED"
            and out["recent_technical_triggers"][0]["unresolved_or_rejected"]):
        raise AssertionError("UNEXPLAINED_PENDING_TRIGGER")
    for label, mutate in (
        ("PENDING_COUNT_TAMPER", lambda t: t.update(pending_count=0)),
        ("PENDING_KEY_DROPPED", lambda t: t.update(pending_symbols=[])),
        ("FAKE_TERMINAL", lambda t:
             t["results"]["AAPL"].update(terminal_scan=True)),
        ("UNREVIEWED_STATUS", lambda t:
             t["results"]["AAPL"].update(status="UNKNOWN_FAKE_APPROVAL")),
    ):
        a = copy.deepcopy(root)
        mutate(a["candidate_technical_funnel"])
        try:
            module.build(a, master, price, blobs)
        except ValueError:
            pass
        else:
            raise AssertionError("FALSE_MIXED_SOURCE_PASS_" + label)

    b = copy.deepcopy(root)
    t = b["candidate_technical_funnel"]
    t["results"]["AAPL"]["status"] = "WATCH_TRIGGER_WITH_FINAL_GATE_BLOCKERS"
    t["results"]["AAPL"]["terminal_scan"] = True
    t["results"]["AAPL"]["family_results"]["A"]["diagnostic_blockers"] = [
        "EVENT_PENDING"]
    t["pending_count"] = 0
    t["evaluated_count"] = 2
    t["pending_symbols"] = []
    out2 = module.build(b, master, price, blobs)
    if not (out2["research_setup_candidate_count"] == 0 and
            out2["recent_technical_triggers"][0]["status"] ==
            "TRIGGER_OBSERVED_NOT_APPROVED" and
            "EVENT_PENDING" in out2["recent_technical_triggers"][0][
                "unresolved_or_rejected"]):
        raise AssertionError("FALSE_BLOCKED_WATCH_PROMOTION")


def current_public_source_contract_smoke():
    """Prove real checked-out canonical public source is internally coherent.

    This never reads Sheets, user credentials, live vendor bars, or alerts;
    NEVER publishes the resulting report.
    """
    paths = {
        "root": root_dir / "orchestrator_state.json",
        "master": root_dir / "canonical_current_master_manifest.json",
        "price": root_dir / "canonical_current_price_dv30.json",
    }
    source = {k: json.loads(path.read_text(encoding="utf-8"))
              for k, path in paths.items()}
    blobs = {k: subprocess.check_output(
        ["git", "hash-object", str(path)], text=True,
        cwd=root_dir.parent).strip() for k, path in paths.items()}
    report = module.build(source["root"], source["master"],
                          source["price"], blobs)
    if not (report["asof_et"] == source["root"]["asof_et"]
            and report["technical_pending_symbols"] ==
                sorted(source["root"]["candidate_technical_funnel"]["pending_symbols"])
            and report["registered_r92_count"] == 0
            and report["research_setup_candidate_count"] == 0
            and report["automated_alert_authority"] is False
            and report["no_raw_ohlcv_or_levels_exported"] is True
            and report["execution"] == "NONE"
            and report["orders"] == []):
        raise AssertionError("CANONICAL_PUBLIC_RESEARCH_UNSAFE_OR_DRIFTED")
    if any(not row["unresolved_or_rejected"]
           for row in report["recent_technical_triggers"]
           if row["status"] == "TRIGGER_OBSERVED_NOT_APPROVED"):
        raise AssertionError("CANONICAL_REJECTED_TRIGGER_NO_REASON")
    module.selftest(source["root"], source["master"],
                    source["price"], blobs)


def main():
    for n in (0, 1, 2):
        root, master, price, blobs = fixture(n)
        report = module.build(root, master, price, blobs)
        if not (report["watchlist_count"] == n
                and report["registered_r92_count"] == 0
                and report["automated_alert_authority"] is False):
            raise AssertionError("INVALID_FIXTURE_OR_FALSE_ALERT:" + str(n))
        module.selftest(root, master, price, blobs)
    producer_mixed_status_adversarial()
    current_public_source_contract_smoke()
    print("XRAY_DIGEST_EMPTY_SINGLE_DOUBLE_WATCH_SELFTEST=PASS_3_SIZES"
          "_10_NEGATIVES_EACH_NO_FALSE_BUY")


if __name__ == "__main__":
    main()
