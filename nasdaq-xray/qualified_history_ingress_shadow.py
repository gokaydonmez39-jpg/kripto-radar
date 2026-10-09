#!/usr/bin/env python3
"""Zero-dollar history vendor-neutral PRIVATE intake safety gate (C4.17 SHADOW).

This validates 260 real NASDAQ completed-session OHLCV *structure* and 52 completed
week ending dates against the immutable current PRICE pass set. It DOES NOT
license any vendor, fetch market data, issue HISTORY PASS, MC PASS, or R92 AL.
No raw proprietary bars, secrets or independently reconstructible derived price
observations enter artifacts; source CSV files must reside outside the public repo.
C4.18 remains PROPOSED_NOT_ACTIVATED. Execution always NONE; money NO-GO.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from history_transport_cache_guard import (
    cache_path, exact_recent_sessions, official_completed_sessions, read_dates,
)
from current_history_source_request import expected_dates, sha256_lines

REPO = Path(__file__).resolve().parent.parent
PRICE = REPO / "nasdaq-xray/canonical_current_price_dv30.json"
SCHEMA = "XRAY_PRIVATE_HISTORY_514_TRANSPORT_INTAKE_SHADOW_V1"


def git_blob(path: Path) -> str:
    return subprocess.check_output(
        ["git", "hash-object", str(path)], cwd=REPO, text=True,
    ).strip()


def _private(cache: Path) -> bool:
    try:
        return (cache.is_absolute() and
                not cache.resolve().is_relative_to(REPO.resolve()))
    except (OSError, RuntimeError, ValueError):
        return False


def evaluate(price: dict, price_sha: str, cache_dir: Path, *,
             require_qqq: bool = True) -> dict:
    symbols = price.get("pass_symbols")
    if (not isinstance(symbols, list) or not symbols
        or symbols != sorted(set(symbols))
        or len(symbols) != price.get("pass_count")
        or any(not isinstance(s, str) for s in symbols)
        or sha256_lines(symbols) != price.get("pass_hash")
        or price.get("unknown_count") != 0
        or price.get("execution") != "NONE"
        or price.get("real_money") != "NO-GO"
        or price.get("unknown_never_pass") is not True
        or not isinstance(price_sha, str) or len(price_sha) != 40):
        raise ValueError("PRICE_SCOPE_OR_SAFETY_INVALID")
    if not _private(cache_dir):
        raise ValueError("CACHE_IN_PUBLIC_REPO_FORBIDDEN")
    asof = price.get("asof_et")
    required_daily, completed_weeks = expected_dates(asof)
    if len(required_daily) != 260 or len(completed_weeks) != 52:
        raise ValueError("EXCHANGE_CALENDAR_INSUFFICIENT")
    # QQQ is a benchmark: it must be checked but is NOT a member of PRICE 514
    # unless it happens to pass the upstream equity rules.
    targets = sorted(set(symbols) | ({"QQQ"} if require_qqq else set()))
    summary = {
        "missing_file": 0, "invalid_or_unreadable": 0,
        "stale_or_session_gap": 0, "complete_private_transport": 0,
        "future_dated_row": 0, "public_path_violation": 0,
    }
    missing = []
    for sym in targets:
        path = cache_path(cache_dir, sym)
        if not path.exists():
            summary["missing_file"] += 1
            missing.append(sym)
            continue
        if path.resolve().is_relative_to(REPO.resolve()):
            summary["public_path_violation"] += 1
            missing.append(sym)
            continue
        # A future-dated row is a look-ahead problem even though our older
        # transport cache parser intentionally ignores such dates.
        future = False
        try:
            with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as fh:
                rd = csv.DictReader(fh)
                if not rd.fieldnames or "date" not in {x.lower() for x in rd.fieldnames}:
                    raise ValueError("MISSING_DATE")
                dc = next(x for x in rd.fieldnames if x.lower() == "date")
                for row in rd:
                    d = str(row.get(dc) or "")[:10]
                    if d > asof:
                        future = True
                        break
        except Exception:
            summary["invalid_or_unreadable"] += 1
            missing.append(sym)
            continue
        if future:
            summary["future_dated_row"] += 1
            missing.append(sym)
            continue
        dates = read_dates(path, asof)
        if not dates:
            summary["invalid_or_unreadable"] += 1
            missing.append(sym)
            continue
        if not exact_recent_sessions(dates, asof):
            summary["stale_or_session_gap"] += 1
            missing.append(sym)
            continue
        summary["complete_private_transport"] += 1
    tested = len(targets)
    assert sum(summary.values()) == tested, "PARTITION_NOT_EXHAUSTIVE"
    complete = summary["complete_private_transport"] == tested
    # Hard wall: structural cache completeness is NOT provider entitlement,
    # verified exchange lineage, point-in-time split/issuer continuity, or
    # production history authority. No self-reported certificate can change it.
    return {
        "schema": SCHEMA,
        "status": "PRIVATE_TRANSPORT_STRUCTURALLY_COMPLETE_NO_SOURCE_AUTHORITY"
                  if complete else "PRIVATE_TRANSPORT_INCOMPLETE_OR_NOT_PRESENT",
        "asof_et": asof,
        "policy": "C4.17", "control": "C4.27",
        "c418_status": "PROPOSED_NOT_ACTIVATED",
        "price_pass_count": len(symbols),
        "source_price_blob_sha": price_sha,
        "source_price_pass_hash": price["pass_hash"],
        "expected_daily_count": len(required_daily),
        "expected_completed_week_closes": len(completed_weeks),
        "scope_includes_QQQ_benchmark": require_qqq,
        "private_transport_tickers_checked": tested,
        "counts": summary,
        "structural_private_transport_complete": complete,
        "source_vendor_rights_independently_verified": False,
        "source_exchangewide_volume_proven": False,
        "source_share_class_and_corporate_actions_proven": False,
        "current_history_authority_proven": False,
        "canonical_history_pass_created": 0,
        "primary_mc_pass_created": 0,
        "can_register_R92": False,
        "vendor_prices_in_artifact": False,
        "private_raw_bars_committed": False,
        "execution": "NONE", "real_money": "NO-GO",
        "unknown_never_pass": True,
    }


def _write(cache: Path, symbol: str, days: list[str], *,
           bad_volume: bool = False, future: bool = False) -> None:
    target = cache_path(cache, symbol)
    with gzip.open(target, "wt", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=("date", "open", "high", "low", "close", "volume"))
        w.writeheader()
        for i, day in enumerate(days):
            w.writerow({"date": day, "open": "10", "high": "11",
                        "low": "9", "close": "10",
                        "volume": "0" if bad_volume and i == 13 else "125.75"})
        if future:
            w.writerow({"date": "2026-10-09", "open": "10", "high": "11",
                        "low": "9", "close": "10", "volume": "125.75"})


def selftest() -> None:
    import copy
    asof = "2026-10-08"
    syms = ["AAA", "BBB"]
    sha = sha256_lines(syms)
    price = {"asof_et": asof, "pass_symbols": syms, "pass_count": 2,
             "pass_hash": sha, "unknown_count": 0, "unknown_never_pass": True,
             "execution": "NONE", "real_money": "NO-GO"}
    days, weeks = expected_dates(asof)
    assert len(days) == 260 and len(weeks) == 52
    with tempfile.TemporaryDirectory(prefix="xray-private-intake-") as temp:
        cache = Path(temp)
        for sym in ("AAA", "BBB", "QQQ"):
            _write(cache, sym, days)
        clean = evaluate(price, "a" * 40, cache)
        assert clean["structural_private_transport_complete"]
        assert clean["counts"]["complete_private_transport"] == 3
        assert clean["canonical_history_pass_created"] == 0
        assert clean["current_history_authority_proven"] is False
        assert clean["can_register_R92"] is False
        # Claiming a vendor grant in the untrusted price manifest changes nothing.
        claim = dict(price, vendor_entitlement_verified=True,
                     independent_source_proven=True, can_register_R92=True)
        assert evaluate(claim, "a" * 40, cache)["can_register_R92"] is False
        _write(cache, "BBB", days, bad_volume=True)
        assert evaluate(price, "a" * 40, cache)["counts"]["invalid_or_unreadable"] == 1
        _write(cache, "BBB", days[1:])
        assert evaluate(price, "a" * 40, cache)["counts"]["stale_or_session_gap"] == 1
        _write(cache, "BBB", days, future=True)
        assert evaluate(price, "a" * 40, cache)["counts"]["future_dated_row"] == 1
        cache_path(cache, "BBB").unlink()
        assert evaluate(price, "a" * 40, cache)["counts"]["missing_file"] == 1
        for bad in (dict(price, pass_count=99), dict(price, pass_hash="0"*64),
                    dict(price, unknown_count=1), dict(price, execution="REAL"),
                    dict(price, pass_symbols=["AAA", "AAA"])):
            try:
                evaluate(bad, "a"*40, cache)
            except ValueError:
                continue
            raise AssertionError("INVALID_PRICE_ACCEPTED")
        try:
            evaluate(price, "a"*40, REPO / "nasdaq-xray")
        except ValueError as e:
            assert str(e) == "CACHE_IN_PUBLIC_REPO_FORBIDDEN"
        else:
            raise AssertionError("PUBLIC_CACHE_ACCEPTED")
    print("XRAY_PRIVATE_HISTORY_INTAKE_SELFTEST=PASS_COMPLETE_260_52_5_CORRUPT_NEGATIVES_PUBLIC_PATH_BLOCKED_NO_SOURCE_AUTHORITY")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--private-cache-dir", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.private_cache_dir or not args.out:
        ap.error("private cache path and sanitized output path required")
    if not _private(args.out):
        ap.error("sanitized output must remain off public repo as well")
    manifest = json.loads(PRICE.read_text(encoding="utf-8"))
    out = evaluate(manifest, git_blob(PRICE), args.private_cache_dir)
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print("XRAY_PRIVATE_HISTORY_INTAKE=" + out["status"])
    print("XRAY_PRIVATE_HISTORY_INTAKE_COUNTS=" + json.dumps(out["counts"], sort_keys=True))
    print("XRAY_SOURCE_RIGHTS_AND_CANONICAL_AUTHORITY=UNVERIFIED_NO_GO")


if __name__ == "__main__":
    main()
