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


def audit_row(key: str, row: dict) -> dict:
    family = str(row.get("family") or "")
    if family not in THRESH:
        return {"key": key, "status": "MISMATCH", "mismatches": ["UNKNOWN_FAMILY"]}

    frozen = row.get("frozen_geometry") or {}
    levels = row.get("levels") or {}
    needed = ("A", "P", "anchor", "entry_model", "entry_high", "S0", "T1")
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

    return {
        "key": key,
        "symbol": key.split("|", 1)[0],
        "family": family,
        "status": "PASS" if not mismatches else "MISMATCH",
        "stored_result": stored_result,
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
