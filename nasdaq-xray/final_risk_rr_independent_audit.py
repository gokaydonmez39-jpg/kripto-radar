#!/usr/bin/env python3
"""Independent deterministic audit of C4.17 Final frozen risk/R1/RR geometry.

This script deliberately does NOT import final_tech_shadow.py.  It recomputes the
decision-bearing arithmetic from the committed Final artifact so implementation
and audit cannot silently share the same runtime functions.

SHADOW AUDIT ONLY. EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_FINAL = ROOT / "canonical_current_final_tech.json"
DEFAULT_HISTORY_MANIFEST = ROOT / "canonical_deep_history_cache_manifest.json"
THRESH = {
    "A": {"basic": 1.5, "severe": 1.1},
    "B": {"basic": 2.0, "severe": 1.5},
    "C": {"basic": 2.0, "severe": 1.5},
    "D": {"basic": 2.0, "severe": 1.5},
}


def git_blob_sha(path: Path) -> str:
    b = path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode() + b).hexdigest()


def close(a, b, tol=1e-11):
    try:
        return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)
    except Exception:
        return False


def rr(entry_model: float, s0: float, t1: float, atr: float, cost_mult: float) -> float:
    cost = cost_mult * atr
    entry = entry_model + cost
    stop = s0 - cost
    target = t1 - cost
    den = entry - stop
    return (target - entry) / den if den > 0 else float("-inf")


def family_geometry_pass(family: str, x: float, frozen: dict) -> bool:
    return family_geometry_pass_independent(family, x, frozen)


def independent_history_rows(symbol: str, final_obj: dict, manifest: dict) -> tuple[list[dict], list[str], dict]:
    """Load exact committed OHLCV without importing production alpha code."""
    mismatches: list[str] = []
    entries = {}
    entries.update(manifest.get("entries") or {})
    entries.update(manifest.get("support_entries") or {})
    rec = entries.get(symbol)
    diag = {"symbol": symbol, "cache_path": None, "cache_blob_sha": None, "fingerprint_match": False}
    if not isinstance(rec, dict):
        return [], ["history_manifest_symbol_missing"], diag
    rel = str(rec.get("path") or "")
    p = (ROOT.parent / rel).resolve()
    diag["cache_path"] = rel
    if not p.exists():
        return [], ["history_cache_file_missing"], diag
    actual_blob = git_blob_sha(p)
    diag["cache_blob_sha"] = actual_blob
    if actual_blob != rec.get("blob_sha"):
        mismatches.append("history_cache_blob_mismatch")

    rows: list[dict] = []
    try:
        with gzip.open(p, "rt", encoding="utf-8-sig", newline="") as fh:
            rdr = csv.DictReader(fh)
            names = {str(x).lower(): x for x in (rdr.fieldnames or [])}
            needed = ("date", "open", "high", "low", "close", "volume")
            if any(x not in names for x in needed):
                return [], mismatches + ["history_cache_columns_missing"], diag
            for raw in rdr:
                d = str(raw.get(names["date"]) or "")[:10]
                if not d or d > str(final_obj.get("asof_et") or ""):
                    continue
                try:
                    row = {"date": d}
                    for c in needed[1:]:
                        row[c] = float(raw.get(names[c]))
                except Exception:
                    return [], mismatches + ["history_cache_non_numeric_row"], diag
                if not all(math.isfinite(float(row[c])) for c in needed[1:]):
                    return [], mismatches + ["history_cache_nonfinite_row"], diag
                rows.append(row)
    except Exception as exc:
        return [], mismatches + ["history_cache_read_error:" + type(exc).__name__], diag
    rows.sort(key=lambda x: x["date"])
    if len({x["date"] for x in rows}) != len(rows):
        mismatches.append("history_cache_duplicate_dates")
    if not rows or rows[-1]["date"] != final_obj.get("asof_et"):
        mismatches.append("history_cache_asof_mismatch")

    # Recompute the committed fingerprint contract independently.
    fp_rows = [
        [r["date"], *[format(float(r[c]), ".12g") for c in ("open", "high", "low", "close", "volume")]]
        for r in rows[-320:]
    ]
    raw = json.dumps(fp_rows, separators=(",", ":"), ensure_ascii=True).encode()
    fp = {
        "schema": "XRAY_ALPHA_HISTORY_FINGERPRINT_V1",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows": len(fp_rows),
        "first_date": fp_rows[0][0] if fp_rows else None,
        "last_date": fp_rows[-1][0] if fp_rows else None,
        "lookback": 320,
    }
    expected_fp = (final_obj.get("history_fingerprint_by_symbol") or {}).get(symbol)
    manifest_fp = rec.get("fingerprint")
    diag["fingerprint_match"] = bool(fp == expected_fp == manifest_fp)
    if not diag["fingerprint_match"]:
        mismatches.append("history_fingerprint_binding_mismatch")
    return rows, mismatches, diag


def independent_wilder_atr(rows: list[dict], n: int = 14) -> list[float | None]:
    """Wilder ATR: first TR undefined, first n valid TRs seed by SMA."""
    out: list[float | None] = [None] * len(rows)
    if len(rows) <= n:
        return out
    tr: list[float | None] = [None]
    for i in range(1, len(rows)):
        h, l, pc = float(rows[i]["high"]), float(rows[i]["low"]), float(rows[i-1]["close"])
        tr.append(max(abs(h-l), abs(h-pc), abs(l-pc)))
    valid = [x for x in tr if x is not None]
    if len(valid) < n:
        return out
    seed_index = n
    seed = sum(float(x) for x in tr[1:n+1]) / n
    out[seed_index] = seed
    prev = seed
    for i in range(seed_index + 1, len(rows)):
        x = tr[i]
        if x is None:
            continue
        prev = ((n - 1) * prev + float(x)) / n
        out[i] = prev
    return out


def independent_retest_bar(row: dict, P: float, entry_high: float) -> bool:
    return float(row["low"]) <= entry_high and float(row["close"]) > P and float(row["close"]) <= entry_high


def independent_tight_base_exists(rows: list[dict], t: int) -> bool:
    """Only the base/compression geometry needed by the extension reset rule."""
    if t < 26 or t >= len(rows):
        return False
    atr = independent_wilder_atr(rows, 14)
    A = atr[t-1]
    if A is None or not math.isfinite(float(A)) or float(A) <= 0:
        return False
    tr = [None]
    for i in range(1, len(rows)):
        h, l, pc = float(rows[i]["high"]), float(rows[i]["low"]), float(rows[i-1]["close"])
        tr.append(max(abs(h-l), abs(h-pc), abs(l-pc)))
    for n in (5, 10, 15, 20):
        if t < n + 20:
            continue
        base = rows[t-n:t]
        bh = max(float(x["high"]) for x in base)
        bl = min(float(x["low"]) for x in base)
        width = (bh - bl) / float(A)
        last5 = [float(x) for x in tr[t-5:t] if x is not None]
        prev20 = [float(x) for x in tr[t-25:t-5] if x is not None]
        if len(last5) == 5 and len(prev20) == 20:
            m5 = sum(last5) / 5.0
            m20 = sum(prev20) / 20.0
            if 0.30 <= width <= 2.05 and m20 > 0 and m5 <= 0.8 * m20:
                return True
    return False


def independent_history_semantics(row: dict, vals: dict, final_obj: dict, manifest: dict) -> tuple[list[str], dict]:
    """Recompute level construction, trigger-1 ATR, lifecycle, extension and result precedence."""
    symbol = str(row.get("symbol") or "")
    if not symbol:
        # Current Final result key is injected by audit_row below.
        symbol = str(row.get("_audit_symbol") or "")
    rows, mismatches, diag = independent_history_rows(symbol, final_obj, manifest)
    diag.update({
        "trigger_index": None, "atr_trigger_minus_1": None, "lifecycle_recomputed": None,
        "extension_veto_recomputed": None, "result_recomputed": None,
    })
    if not rows:
        return mismatches, diag

    frozen = row.get("frozen_geometry") or {}
    # Frozen construction invariants are direct C4.17 geometry contracts.
    expected_entry = vals["P"] + 0.25 * vals["A"]
    expected_chase = vals["P"] + 0.50 * vals["A"]
    expected_s0 = vals["anchor"] - 0.20 * vals["A"]
    if not close(vals["entry_low"], vals["P"]):
        mismatches.append("entry_low_not_P")
    if not close(vals["entry_high"], expected_entry):
        mismatches.append("entry_high_not_P_plus_0p25A")
    if not close(vals["entry_model"], expected_entry):
        mismatches.append("entry_model_not_P_plus_0p25A")
    if not close(vals["chase_limit"], expected_chase):
        mismatches.append("chase_limit_not_P_plus_0p50A")
    if not close(vals["S0"], expected_s0):
        mismatches.append("S0_not_anchor_minus_0p20A")

    trigger_date = str(frozen.get("trigger_date") or row.get("trigger_date") or "")
    dates = [x["date"] for x in rows]
    if trigger_date not in dates:
        mismatches.append("trigger_date_not_in_history")
        return mismatches, diag
    ti = dates.index(trigger_date)
    diag["trigger_index"] = ti
    if ti <= 0:
        mismatches.append("trigger_minus_1_unavailable")
    else:
        atr = independent_wilder_atr(rows, 14)
        A1 = atr[ti-1] if ti-1 < len(atr) else None
        diag["atr_trigger_minus_1"] = A1
        if A1 is None or not close(vals["A"], A1, 1e-10):
            mismatches.append(f"ATR14_trigger_minus_1:calc={A1!r}:stored={vals['A']!r}")

    # Anchor availability and S0 breach are independently derived from committed history.
    ai = frozen.get("anchor_available_idx")
    if not isinstance(ai, int) or ai < 0 or ai >= len(rows) or ai > ti:
        mismatches.append("anchor_available_idx_invalid")
        breached = bool((row.get("invalidation") or {}).get("breached"))
        breach_date = (row.get("invalidation") or {}).get("first_breach_date")
    else:
        breaches = [x for x in rows[ai+1:] if float(x["low"]) <= vals["S0"]]
        breached = bool(breaches)
        breach_date = breaches[0]["date"] if breaches else None
        stored_inv = row.get("invalidation") or {}
        if bool(stored_inv.get("breached")) != breached:
            mismatches.append("S0_breach_flag")
        if stored_inv.get("first_breach_date") != breach_date:
            mismatches.append("S0_first_breach_date")

    asof = str(final_obj.get("asof_et") or "")
    if asof not in dates:
        mismatches.append("asof_not_in_history")
        return mismatches, diag
    age = dates.index(asof) - ti
    close_now = float(rows[-1]["close"])
    current_retest = bool(age > 0 and age <= 5 and independent_retest_bar(rows[-1], vals["P"], vals["entry_high"]))
    if bool(row.get("current_retest")) != current_retest:
        mismatches.append("current_retest")
    if breached:
        lifecycle = "INVALIDATED_S0"
    elif age > 8:
        lifecycle = "EXPIRED_HORIZON"
    elif close_now < vals["P"]:
        lifecycle = "RECONFIRMATION_REQUIRED"
    elif close_now <= vals["entry_high"]:
        if age == 0:
            lifecycle = "ENTRY_BAND"
        elif current_retest:
            lifecycle = "RETEST_ENTRY_BAND"
        elif age <= 5:
            lifecycle = "RETEST_REQUIRED"
        else:
            lifecycle = "EXPIRED_RETEST_WINDOW"
    elif close_now < vals["chase_limit"]:
        lifecycle = "RETEST_REQUIRED" if age <= 5 else "EXPIRED_RETEST_WINDOW"
    else:
        lifecycle = "CHASE_NO_VALID_FILL"
    diag["lifecycle_recomputed"] = lifecycle
    if str(row.get("lifecycle") or "") != lifecycle:
        mismatches.append(f"lifecycle:calc={lifecycle}:stored={row.get('lifecycle')!r}")

    pivot_extension = close_now / vals["P"] - 1.0 if vals["P"] > 0 else float("inf")
    move3 = None
    reset = False
    if len(rows) >= 4:
        move3 = (close_now - float(rows[-4]["close"])) / vals["A"]
        for i in range(max(0, len(rows)-3), len(rows)-1):
            if independent_retest_bar(rows[i], vals["P"], vals["entry_high"]):
                reset = True
                break
        if not reset:
            for candidate_t in (len(rows)-2, len(rows)-1):
                if candidate_t >= 0 and independent_tight_base_exists(rows, candidate_t):
                    reset = True
                    break
    extension_veto = bool(pivot_extension >= 0.08 or (move3 is not None and move3 > 2.0 and not reset))
    diag["extension_veto_recomputed"] = extension_veto
    geom = row.get("geometry") or {}
    if not close(pivot_extension, geom.get("pivot_extension")):
        mismatches.append("pivot_extension")
    stored_move3 = geom.get("move3_atr")
    if move3 is None:
        if stored_move3 is not None:
            mismatches.append("move3_atr")
    elif not close(move3, stored_move3):
        mismatches.append("move3_atr")
    if bool(geom.get("reset_between_tminus3_and_t")) != reset:
        mismatches.append("extension_reset")
    if bool(row.get("extension_veto")) != extension_veto:
        mismatches.append("extension_veto")

    # Independent result precedence using recomputed technical booleans and stored nontechnical status.
    family = str(row.get("family") or "")
    x = (vals["P"] - vals["anchor"]) / vals["A"]
    family_geometry_pass = family_geometry_pass_independent(family, x, frozen)
    risk_atr = (vals["entry_model"] - vals["S0"]) / vals["A"]
    risk_pct = (vals["entry_model"] - vals["S0"]) / vals["entry_model"] if vals["entry_model"] > 0 else float("inf")
    risk_pass = bool(family_geometry_pass and 0.75 <= risk_atr <= 2.50 and risk_pct <= 0.08)
    basic = rr(vals["entry_model"], vals["S0"], vals["T1"], vals["A"], 0.10)
    severe = rr(vals["entry_model"], vals["S0"], vals["T1"], vals["A"], 0.25)
    rr_pass = bool(basic >= THRESH[family]["basic"] and severe >= THRESH[family]["severe"])
    target_overlap = bool(frozen.get("target_overlap") or vals["T1"] <= vals["entry_high"])
    event_pass = row.get("event_status") == "CLEAN_DISCOVERY"
    regime_status = str(row.get("regime_finalist_status") or "")
    regime_pass = regime_status == "PASS"
    entry_ready = lifecycle in {"ENTRY_BAND", "RETEST_ENTRY_BAND"}
    hard_pass = bool(risk_pass and rr_pass and not target_overlap and not extension_veto and entry_ready and event_pass and regime_pass and not breached)
    mc_cap_blocks = bool(row.get("state_cap") == "WATCH" or row.get("r92_eligible") is False)
    if hard_pass and mc_cap_blocks:
        expected_result = "WATCH_MC_FALLBACK_CAP"
    elif hard_pass:
        expected_result = "PRE_G9_TECH_PASS"
    elif lifecycle == "INVALIDATED_S0":
        expected_result = "FAIL_INVALIDATED_S0"
    elif lifecycle in {"EXPIRED_RETEST_WINDOW", "EXPIRED_HORIZON"}:
        expected_result = "FAIL_EXPIRED"
    elif not risk_pass:
        expected_result = "FAIL_RISK_GEOMETRY"
    elif target_overlap:
        expected_result = "FAIL_R1_ENTRY_OVERLAP"
    elif not rr_pass:
        expected_result = "FAIL_RR"
    elif not event_pass:
        expected_result = "WATCH_EVENT_UNKNOWN_OR_BLOCKED"
    elif regime_status == "UNKNOWN":
        expected_result = "WATCH_REGIME_UNKNOWN"
    elif not regime_pass:
        expected_result = "WATCH_REGIME_REVALIDATION_REQUIRED"
    elif lifecycle == "CHASE_NO_VALID_FILL" and age <= 5:
        expected_result = "WATCH_CHASE_RETEST_REQUIRED"
    elif extension_veto and age <= 5:
        expected_result = "WATCH_EXTENSION_RESET_REQUIRED"
    elif lifecycle == "CHASE_NO_VALID_FILL":
        expected_result = "FAIL_CHASE"
    elif extension_veto:
        expected_result = "FAIL_EXTENSION"
    elif lifecycle == "RETEST_REQUIRED":
        expected_result = "WATCH_RETEST_REQUIRED"
    elif lifecycle == "RECONFIRMATION_REQUIRED":
        expected_result = "WATCH_RECONFIRMATION_REQUIRED"
    else:
        expected_result = "FAIL_OTHER"
    diag["result_recomputed"] = expected_result
    if str(row.get("result") or "") != expected_result:
        mismatches.append(f"result_precedence:calc={expected_result}:stored={row.get('result')!r}")
    if bool(row.get("technical_hard_pass")) != hard_pass:
        mismatches.append("technical_hard_pass")
    if bool(row.get("pre_g9_tech_pass")) != bool(hard_pass and not mc_cap_blocks):
        mismatches.append("pre_g9_tech_pass")
    return mismatches, diag


def family_geometry_pass_independent(family: str, x: float, frozen: dict) -> bool:
    if family == "A":
        src = frozen.get("source_geometry") or frozen.get("geometry") or {}
        try:
            depth = float(src.get("depth"))
        except Exception:
            return False
        return 0.30 <= x <= 1.07 and 2.15 <= depth <= 4.00 and src.get("prelow_near_hl") is True
    return 0.30 <= x <= 2.05


def structural_zone_audit(row: dict, vals: dict) -> tuple[list[str], dict]:
    """Audit stored R1-zone semantics without importing production alpha code.

    The 120-session sensitivity is diagnostic only: C4.17 does not impose a
    120-session age cutoff on BASE_HIGH resistance, so it never changes PASS.
    """
    frozen = row.get("frozen_geometry") or {}
    zone = frozen.get("target_zone")
    source = str(frozen.get("target_source") or "")
    trigger_date = str(frozen.get("trigger_date") or row.get("trigger_date") or "")
    mismatches: list[str] = []
    diag = {
        "target_source": source,
        "zone_kind": None,
        "zone_lower": None,
        "zone_upper": None,
        "point_count": 0,
        "legacy_gt120_confirmed_idx_points": 0,
        "oldest_occurrence_date": None,
        "recent120_lower": None,
        "recent120_upper": None,
        "recent120_overlap": None,
        "lower_changed_without_legacy_gt120": False,
        "diagnostic_only_non_authority": True,
    }
    if source.startswith("SYNTHETIC_"):
        if zone is not None:
            mismatches.append("synthetic_target_has_structural_zone")
        return mismatches, diag
    if source != "STRUCTURAL_ACTIVE_R1_LOWER_BOUND":
        mismatches.append("unknown_target_source:" + source)
        return mismatches, diag
    if not isinstance(zone, dict):
        mismatches.append("structural_target_zone_missing")
        return mismatches, diag

    lower = zone.get("lower")
    upper = zone.get("upper")
    try:
        lower = float(lower)
        upper = float(upper)
    except Exception:
        mismatches.append("structural_zone_bounds_non_numeric")
        return mismatches, diag
    diag["zone_kind"] = zone.get("kind")
    diag["zone_lower"] = lower
    diag["zone_upper"] = upper
    if not (math.isfinite(lower) and math.isfinite(upper) and lower <= upper):
        mismatches.append("structural_zone_bounds_invalid")
    if not close(vals["T1"], lower):
        mismatches.append(f"r1_lower_not_T1:lower={lower!r}:T1={vals['T1']!r}")
    if zone.get("active") is not True:
        mismatches.append("selected_r1_zone_not_active")
    if not (upper > vals["entry_low"]):
        mismatches.append("selected_r1_not_eligible_above_entry_low")

    expected_overlap = not (upper < vals["entry_low"] or lower > vals["entry_high"])
    if bool(row.get("target_overlap")) != expected_overlap:
        mismatches.append("structural_zone_overlap_formula")

    dates = list(zone.get("occurrence_dates") or [])
    if dates:
        diag["oldest_occurrence_date"] = sorted(str(x) for x in dates)[0]
        if trigger_date and any(str(d) >= trigger_date for d in dates):
            mismatches.append("r1_occurrence_not_strictly_pretrigger")

    breakout = zone.get("breakout_unconfirmed_role_change")
    if breakout and trigger_date and str(breakout) >= trigger_date:
        mismatches.append("r1_breakout_role_change_lookahead")
    broken = zone.get("broken_at")
    if broken is not None and zone.get("active") is True:
        mismatches.append("active_zone_has_broken_at")

    points = list(zone.get("points") or [])
    diag["point_count"] = len(points)
    if points:
        try:
            prices = [float(p["price"]) for p in points]
            conf = [int(p["confirmed_idx"]) for p in points]
            point_dates = [str(p["date"]) for p in points]
        except Exception:
            mismatches.append("structural_zone_point_shape")
            return mismatches, diag
        if not close(min(prices), lower):
            mismatches.append("structural_zone_lower_not_min_point")
        if not close(max(prices), upper):
            mismatches.append("structural_zone_upper_not_max_point")
        if int(zone.get("active_from_idx", -1)) != max(conf):
            mismatches.append("structural_zone_active_from_not_latest_confirmation")
        if sorted(set(point_dates)) != sorted(set(str(x) for x in dates)):
            mismatches.append("structural_zone_occurrence_dates_not_point_dates")
        if trigger_date and any(d >= trigger_date for d in point_dates):
            mismatches.append("r1_point_date_not_strictly_pretrigger")

        latest = max(conf)
        legacy = [p for p in points if latest - int(p["confirmed_idx"]) > 120]
        recent = [p for p in points if latest - int(p["confirmed_idx"]) <= 120]
        diag["legacy_gt120_confirmed_idx_points"] = len(legacy)
        if recent:
            rp = [float(p["price"]) for p in recent]
            rlo, rhi = min(rp), max(rp)
            diag["recent120_lower"] = rlo
            diag["recent120_upper"] = rhi
            diag["recent120_overlap"] = not (
                rhi < vals["entry_low"] or rlo > vals["entry_high"]
            )
            diag["lower_changed_without_legacy_gt120"] = not close(rlo, lower)
    return mismatches, diag


def audit_row(key: str, row: dict, final_obj: dict, history_manifest: dict) -> dict:
    family = str(row.get("family") or "")
    if family not in THRESH:
        return {"key": key, "status": "MISMATCH", "mismatches": ["UNKNOWN_FAMILY"]}

    frozen = row.get("frozen_geometry") or {}
    levels = row.get("levels") or {}
    needed = ("A", "P", "anchor", "entry_low", "entry_model", "entry_high", "chase_limit", "S0", "T1")
    vals = {}
    missing = []
    for name in needed:
        raw = frozen.get(name, levels.get(name))
        try:
            vals[name] = float(raw)
        except Exception:
            missing.append(name)
    if missing:
        return {"key": key, "status": "MISMATCH", "mismatches": ["MISSING_NUMERIC:" + ",".join(missing)]}

    A = vals["A"]
    if not math.isfinite(A) or A <= 0:
        return {"key": key, "status": "MISMATCH", "mismatches": ["ATR_NONPOSITIVE"]}

    x = (vals["P"] - vals["anchor"]) / A
    risk_atr = (vals["entry_model"] - vals["S0"]) / A
    risk_pct = (
        (vals["entry_model"] - vals["S0"]) / vals["entry_model"]
        if vals["entry_model"] > 0
        else float("inf")
    )
    basic = rr(vals["entry_model"], vals["S0"], vals["T1"], A, 0.10)
    severe = rr(vals["entry_model"], vals["S0"], vals["T1"], A, 0.25)
    target_overlap = bool(frozen.get("target_overlap") or vals["T1"] <= vals["entry_high"])
    geom_pass = family_geometry_pass(family, x, frozen)
    risk_pass = bool(geom_pass and 0.75 <= risk_atr <= 2.50 and risk_pct <= 0.08)
    rr_pass = bool(basic >= THRESH[family]["basic"] and severe >= THRESH[family]["severe"])

    mismatches = []
    geometry = row.get("geometry") or {}
    stored_rr = row.get("rr") or {}
    checks = [
        ("x", x, geometry.get("x")),
        ("risk_atr", risk_atr, geometry.get("risk_atr")),
        ("risk_percent", risk_pct, geometry.get("risk_percent")),
        ("rr_basic", basic, stored_rr.get("basic")),
        ("rr_severe", severe, stored_rr.get("severe")),
    ]
    for name, calc, stored in checks:
        if not close(calc, stored):
            mismatches.append(f"{name}:calc={calc!r}:stored={stored!r}")

    if bool(row.get("risk_pass")) != risk_pass:
        mismatches.append(f"risk_pass:calc={risk_pass}:stored={row.get('risk_pass')!r}")
    if bool(row.get("target_overlap")) != target_overlap:
        mismatches.append(
            f"target_overlap:calc={target_overlap}:stored={row.get('target_overlap')!r}"
        )
    if bool(stored_rr.get("basic_pass")) != (basic >= THRESH[family]["basic"]):
        mismatches.append("rr_basic_pass")
    if bool(stored_rr.get("severe_pass")) != (severe >= THRESH[family]["severe"]):
        mismatches.append("rr_severe_pass")

    expected_risk_block = risk_pct > 0.08 or not geom_pass or not (0.75 <= risk_atr <= 2.50)
    blockers = set(row.get("diagnostic_blockers") or [])
    if (risk_pct > 0.08) != ("RISK_PERCENT_GT_8PCT" in blockers):
        mismatches.append("risk_percent_blocker_vector")
    if target_overlap != ("R1_ENTRY_BAND_OVERLAP" in blockers):
        mismatches.append("r1_overlap_blocker_vector")
    if (basic < THRESH[family]["basic"]) != ("RR_BASIC_BELOW_THRESHOLD" in blockers):
        mismatches.append("rr_basic_blocker_vector")
    if (severe < THRESH[family]["severe"]) != ("RR_SEVERE_BELOW_THRESHOLD" in blockers):
        mismatches.append("rr_severe_blocker_vector")

    stored_result = str(row.get("result") or "")
    if expected_risk_block and stored_result != "FAIL_RISK_GEOMETRY":
        mismatches.append(
            f"risk_precedence:expected=FAIL_RISK_GEOMETRY:stored={stored_result}"
        )

    zone_mismatches, zone_diag = structural_zone_audit(row, vals)
    mismatches.extend(zone_mismatches)
    audit_row_obj = dict(row)
    audit_row_obj["_audit_symbol"] = key.split("|", 1)[0]
    history_mismatches, history_diag = independent_history_semantics(
        audit_row_obj, vals, final_obj, history_manifest
    )
    mismatches.extend(history_mismatches)
    blockers_sorted = list(row.get("diagnostic_blockers") or [])

    return {
        "key": key,
        "symbol": key.split("|", 1)[0],
        "family": family,
        "status": "PASS" if not mismatches else "MISMATCH",
        "stored_result": stored_result,
        "decision_inputs": {
            "trigger_date": row.get("trigger_date"),
            "P": vals["P"],
            "entry_low": vals["entry_low"],
            "entry_high": vals["entry_high"],
            "entry_model": vals["entry_model"],
            "chase_limit": vals["chase_limit"],
            "anchor": vals["anchor"],
            "S0": vals["S0"],
            "ATR": A,
            "risk_percent": risk_pct,
            "R1_target_source": (frozen.get("target_source")),
            "R1_lower": ((frozen.get("target_zone") or {}).get("lower", vals["T1"])),
            "R1_upper": ((frozen.get("target_zone") or {}).get("upper", vals["T1"])),
            "target_overlap": target_overlap,
            "RR_BASIC": basic,
            "RR_SEVERE": severe,
            "lifecycle": row.get("lifecycle"),
            "extension_veto": bool(row.get("extension_veto")),
            "event_status": row.get("event_status"),
            "state_cap": row.get("state_cap"),
            "r92_eligible": row.get("r92_eligible"),
            "exact_blockers": blockers_sorted,
        },
        "r1_zone_audit": zone_diag,
        "history_semantics_audit": history_diag,
        "recomputed": {
            "x": x,
            "risk_atr": risk_atr,
            "risk_percent": risk_pct,
            "rr_basic": basic,
            "rr_severe": severe,
            "target_overlap": target_overlap,
            "family_geometry_pass": geom_pass,
            "risk_pass": risk_pass,
            "rr_pass": rr_pass,
        },
        "mismatches": mismatches,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", default=str(DEFAULT_FINAL))
    ap.add_argument("--history-manifest", default=str(DEFAULT_HISTORY_MANIFEST))
    ap.add_argument("--out")
    args = ap.parse_args()

    final_path = Path(args.final)
    obj = json.loads(final_path.read_text())
    history_manifest_path = Path(args.history_manifest)
    history_manifest = json.loads(history_manifest_path.read_text())
    assert obj.get("schema") == "XRAY_FINAL_TECH_SHADOW_V1"
    assert obj.get("execution") == "NONE"
    assert obj.get("real_money") == "NO-GO"
    assert obj.get("unknown_never_pass") is True
    assert history_manifest.get("schema") == "XRAY_CANONICAL_DEEP_HISTORY_CACHE_MANIFEST_V1"
    assert history_manifest.get("asof_et") == obj.get("asof_et")
    assert history_manifest.get("execution") == "NONE" and history_manifest.get("real_money") == "NO-GO"
    assert history_manifest.get("unknown_never_pass") is True

    rows = [
        audit_row(k, v or {}, obj, history_manifest)
        for k, v in sorted((obj.get("results") or {}).items())
    ]
    bad = [r for r in rows if r["status"] != "PASS"]
    independently_risk_failed = [
        r["key"] for r in rows
        if not bool((r.get("recomputed") or {}).get("risk_pass"))
    ]
    independently_rr_failed = [
        r["key"] for r in rows
        if not bool((r.get("recomputed") or {}).get("rr_pass"))
    ]

    out = {
        "schema": "XRAY_FINAL_RISK_RR_INDEPENDENT_AUDIT_V1",
        "asof_et": obj.get("asof_et"),
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "alpha_authority": False,
        "decision_authority": False,
        "source_final_path": str(final_path).replace("\\", "/"),
        "source_final_blob_sha": git_blob_sha(final_path),
        "source_history_manifest_path": str(history_manifest_path).replace("\\", "/"),
        "source_history_manifest_blob_sha": git_blob_sha(history_manifest_path),
        "row_count": len(rows),
        "mismatch_count": len(bad),
        "independently_risk_failed_count": len(independently_risk_failed),
        "independently_risk_failed": independently_risk_failed,
        "independently_rr_failed_count": len(independently_rr_failed),
        "independently_rr_failed": independently_rr_failed,
        "history_semantics_mismatch_count": sum(
            1 for r in rows
            if any(
                x.startswith(("entry_", "chase_", "S0_", "ATR14_", "history_", "lifecycle", "current_retest", "S0_breach", "S0_first", "pivot_extension", "move3_atr", "extension_", "result_precedence", "technical_hard_pass", "pre_g9_tech_pass"))
                for x in (r.get("mismatches") or [])
            )
        ),
        "legacy_gt120_r1_point_row_count": sum(
            1 for r in rows
            if int(((r.get("r1_zone_audit") or {}).get("legacy_gt120_confirmed_idx_points") or 0)) > 0
        ),
        "legacy_gt120_changes_lower_row_count": sum(
            1 for r in rows
            if (r.get("r1_zone_audit") or {}).get("lower_changed_without_legacy_gt120") is True
        ),
        "rows": rows,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(out, sort_keys=True, indent=2) + "\n")
    print(json.dumps({
        "status": "PASS" if not bad else "FAIL",
        "rows": len(rows),
        "mismatch_count": len(bad),
        "independently_risk_failed_count": len(independently_risk_failed),
        "independently_rr_failed_count": len(independently_rr_failed),
        "source_final_blob_sha": out["source_final_blob_sha"],
        "source_history_manifest_blob_sha": out["source_history_manifest_blob_sha"],
        "history_semantics_mismatch_count": out["history_semantics_mismatch_count"],
    }, sort_keys=True))
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
