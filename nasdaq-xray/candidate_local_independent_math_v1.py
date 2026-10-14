#!/usr/bin/env python3
"""Independent fail-closed arithmetic audit of C4.17 frozen A/B/D levels.

Checks mathematics and recorded stop-breach history. Does not reconstruct
corporate actions or the full historical R1 supply-zone discovery.
No AL, order or R92 authority.
"""
from __future__ import annotations
import copy
import math

THRESHOLDS = {"A": (1.5, 1.1), "B": (2.0, 1.5), "D": (2.0, 1.5)}


def number(v):
    if type(v) not in (float, int) or not math.isfinite(v):
        raise ValueError("INDEPENDENT_GEOMETRY_NONFINITE_OR_NONNUMERIC")
    return float(v)


def equal(a, b):
    return math.isclose(number(a), number(b), rel_tol=1e-10, abs_tol=1e-8)


def require(p, reason):
    if not p:
        raise ValueError("INDEPENDENT_GEOMETRY_" + reason)


def audit(family, source_geometry, final_row, history=None):
    """Derive entry, stop, target coherence, R/R and risk independently of Final."""
    require(family in THRESHOLDS, "UNSUPPORTED_FAMILY")
    row = final_row or {}
    if not isinstance(row.get("levels"), dict):
        return {"status": "UNKNOWN_NO_FROZEN_GEOMETRY",
                "reason": str(row.get("reason") or row.get("result") or "UNKNOWN"),
                "independently_verified": False}
    v = row["levels"]
    a, p, anchor, target = map(number, (v.get("A"), v.get("P"),
                                         v.get("anchor"), v.get("T1")))
    require(a > 0 and p > 0 and anchor > 0 and target > 0, "INVALID_SOURCE_SCALE")
    entry, stop = p + a / 4, anchor - a / 5
    require(stop > 0 and entry > stop, "NO_POSITIVE_RISK")
    expected = {"entry_low": p, "entry_high": entry, "entry_model": entry,
                "chase_limit": p + a / 2, "S0": stop}
    for key, val in expected.items():
        require(equal(v.get(key), val), "PRICE_LEVEL_" + key.upper())
    if source_geometry:
        for key, val in (("P", p), ("anchor", anchor), ("A", a)):
            require(equal(source_geometry.get(key), val), "SOURCE_" + key.upper())
    risk, x = entry - stop, (p - anchor) / a
    risk_pct, risk_atr = risk / entry, risk / a
    g = source_geometry or {}
    if family == "A":
        depth = number(g.get("depth"))
        geom_pass = (0.30 <= x <= 1.07 and 2.15 <= depth <= 4.00
                     and g.get("prelow_near_hl") is True)
    else:
        geom_pass = 0.30 <= x <= 2.05
    risk_pass = bool(geom_pass and 0.75 <= risk_atr <= 2.50
                     and risk_pct <= 0.08)
    basic = (target - entry - .20 * a) / (risk + .20 * a)
    severe = (target - entry - .50 * a) / (risk + .50 * a)
    basic_pass = basic >= THRESHOLDS[family][0]
    severe_pass = severe >= THRESHOLDS[family][1]
    geom = row.get("geometry") or {}
    for key, value in (("x", x), ("risk_atr", risk_atr),
                       ("risk_percent", risk_pct)):
        require(equal(geom.get(key), value), "GEOMETRY_" + key.upper())
    rr = row.get("rr") or {}
    require(equal(rr.get("basic"), basic), "BASIC_RR")
    require(equal(rr.get("severe"), severe), "SEVERE_RR")
    require(rr.get("basic_pass") is basic_pass, "BASIC_PASS_FLAG")
    require(rr.get("severe_pass") is severe_pass, "SEVERE_PASS_FLAG")
    require(row.get("family_geometry_pass") is geom_pass, "FAMILY_FLAG")
    require(row.get("risk_pass") is risk_pass, "RISK_PASS_FLAG")
    meta = row.get("target") or {}
    if meta.get("source") == "STRUCTURAL_ACTIVE_R1_LOWER_BOUND":
        zone = meta.get("zone") or {}
        lower, upper = number(zone.get("lower")), number(zone.get("upper"))
        require(equal(target, lower) and upper >= lower and upper > p,
                "ACTIVE_R1_ZONE")
        overlap = (lower <= entry and upper >= p) or target <= entry
        require(row.get("target_overlap") is overlap, "R1_OVERLAP_FLAG")
    elif meta.get("source") == "SYNTHETIC_P_PLUS_3A_PRICE_DISCOVERY":
        require(equal(target, p + 3 * a) and meta.get("synthetic") is True,
                "SYNTHETIC_TARGET")
    else:
        raise ValueError("INDEPENDENT_GEOMETRY_UNKNOWN_TARGET_SOURCE")
    frozen = row.get("frozen_geometry") or {}
    for key in ("P", "anchor", "A", "S0", "T1", "entry_model"):
        require(equal(frozen.get(key), v[key]), "FROZEN_" + key.upper())
    if history is not None:
        ai = frozen.get("anchor_available_idx")
        require(type(ai) is int and 0 <= ai < len(history), "ANCHOR_AVAILABILITY")
        post = history.iloc[ai + 1:]
        breached_rows = post[post["low"].astype(float) <= stop]
        breached = not breached_rows.empty
        inv = row.get("invalidation") or {}
        require(inv.get("breached") is breached, "STOP_BREACH_FLAG")
        if breached:
            first = breached_rows["date"].iloc[0].date().isoformat()
            require(inv.get("first_breach_date") == first, "STOP_BREACH_DATE")
    return {"status": "PASS_INDEPENDENT_FORMULA_AUDIT",
            "independently_verified": True,
            "scope": "FROZEN_MATH_STOP_BREACH_NOT_INDEPENDENT_R1_DISCOVERY",
            "risk_pct": round(100 * risk_pct, 6),
            "risk_atr": round(risk_atr, 6),
            "basic_rr": round(basic, 6),
            "severe_rr": round(severe, 6),
            "risk_pass": risk_pass,
            "rr_pass": basic_pass and severe_pass}


def selftest():
    a, p, anchor, target = 4.0, 100.0, 96.0, 120.0
    entry, stop = p + a / 4, anchor - a / 5
    risk = entry - stop
    basic = (target - entry - .20 * a) / (risk + .20 * a)
    severe = (target - entry - .50 * a) / (risk + .50 * a)
    row = {
        "levels": {"A": a, "P": p, "anchor": anchor, "T1": target,
                   "entry_low": p, "entry_high": entry, "entry_model": entry,
                   "chase_limit": p + a / 2, "S0": stop},
        "frozen_geometry": {"A": a, "P": p, "anchor": anchor, "T1": target,
                            "S0": stop, "entry_model": entry},
        "geometry": {"x": 1.0, "risk_atr": risk / a,
                     "risk_percent": risk / entry},
        "rr": {"basic": basic, "severe": severe,
               "basic_pass": True, "severe_pass": True},
        "target": {"source": "STRUCTURAL_ACTIVE_R1_LOWER_BOUND",
                   "zone": {"lower": target, "upper": 121.0}},
        "target_overlap": False, "family_geometry_pass": True,
        "risk_pass": True}
    for family in THRESHOLDS:
        src = {"P": p, "anchor": anchor, "A": a}
        if family == "A":
            src.update({"depth": 3.0, "prelow_near_hl": True})
        require(audit(family, src, row)["independently_verified"],
                "VALID_" + family)
    for field, key, wrong in (("levels", "S0", stop + .001),
                              ("rr", "severe", severe + .001),
                              ("geometry", "risk_percent", .10),
                              ("rr", "basic_pass", False),
                              ("target", "source", "INVALID")):
        bad = copy.deepcopy(row)
        bad[field][key] = wrong
        try:
            audit("D", {"P": p, "anchor": anchor, "A": a}, bad)
        except ValueError:
            pass
        else:
            raise AssertionError("INDEPENDENT_AUDIT_FALSE_PASS:" + key)
    for source_key in ("P", "anchor", "A"):
        incorrect_source = {"P": p, "anchor": anchor, "A": a}
        incorrect_source[source_key] += .01
        try:
            audit("D", incorrect_source, row)
        except ValueError:
            pass
        else:
            raise AssertionError("INDEPENDENT_AUDIT_FALSE_SOURCE_PASS:" + source_key)
    require(not audit("D", {}, {"result": "UNKNOWN",
                               "reason": "NO_R1"})["independently_verified"],
            "UNKNOWN_MUST_NOT_PASS")
    print("XRAY_INDEPENDENT_C417_A_B_D_ENTRY_STOP_TARGET_RR_SELFTEST=PASS")


if __name__ == "__main__":
    selftest()
