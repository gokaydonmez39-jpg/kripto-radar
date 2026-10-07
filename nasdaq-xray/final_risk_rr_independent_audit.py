#!/usr/bin/env python3
"""Independent deterministic audit of C4.17 Final frozen risk/R1/RR geometry.

This script deliberately does NOT import final_tech_shadow.py.  It recomputes the
decision-bearing arithmetic from the committed Final artifact so implementation
and audit cannot silently share the same runtime functions.

SHADOW AUDIT ONLY. EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_FINAL = ROOT / "canonical_current_final_tech.json"
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
    if family == "A":
        src = frozen.get("source_geometry") or frozen.get("geometry") or {}
        depth = src.get("depth")
        prelow = src.get("prelow_near_hl")
        try:
            depth = float(depth)
        except Exception:
            return False
        return 0.30 <= x <= 1.07 and 2.15 <= depth <= 4.00 and prelow is True
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


def audit_row(key: str, row: dict) -> dict:
    family = str(row.get("family") or "")
    if family not in THRESH:
        return {"key": key, "status": "MISMATCH", "mismatches": ["UNKNOWN_FAMILY"]}

    frozen = row.get("frozen_geometry") or {}
    levels = row.get("levels") or {}
    needed = ("A", "P", "anchor", "entry_low", "entry_model", "entry_high", "S0", "T1")
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
    ap.add_argument("--out")
    args = ap.parse_args()

    final_path = Path(args.final)
    obj = json.loads(final_path.read_text())
    assert obj.get("schema") == "XRAY_FINAL_TECH_SHADOW_V1"
    assert obj.get("execution") == "NONE"
    assert obj.get("real_money") == "NO-GO"
    assert obj.get("unknown_never_pass") is True

    rows = [audit_row(k, v or {}) for k, v in sorted((obj.get("results") or {}).items())]
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
        "row_count": len(rows),
        "mismatch_count": len(bad),
        "independently_risk_failed_count": len(independently_risk_failed),
        "independently_risk_failed": independently_risk_failed,
        "independently_rr_failed_count": len(independently_rr_failed),
        "independently_rr_failed": independently_rr_failed,
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
    }, sort_keys=True))
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
