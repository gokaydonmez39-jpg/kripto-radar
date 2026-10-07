#!/usr/bin/env python3
"""Shadow-only zero-dollar MC successor audit for current C4.17 UNKNOWNs.

This tool never changes production MC classifications. It measures whether current
same-ASOF evidence is sufficient for a future policy successor test and records
the exact missing evidence when it is not.

EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
TERMINAL = ROOT / "canonical_current_terminal.json"
PRICE = ROOT / "canonical_current_price_dv30.json"
NASDAQ_PIT = ROOT / "nasdaq_screener_pit_current.json"
SEC_PROBE = ROOT / "sec_companyfacts_probe.json"
OUT = ROOT / "mc_zero_dollar_successor_shadow_audit.json"
POLICY_VERSION = "C4.17"
TASK_ID = "6a825366222081918997094d76e6ae46"
PASS_FLOOR = 2_100_000_000.0
FAIL_CEILING = 2_000_000_000.0


def readj(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob(path: Path) -> str:
    return subprocess.check_output(
        ["git", "hash-object", str(path)], cwd=REPO, text=True
    ).strip()


def select_active_mc_row(rows: list[dict]) -> dict:
    """Return the single unsuperseded exact-current MC authority row."""
    by_rel = {str(r["rel"]): r for r in rows}
    superseded = set()
    for row in rows:
        obj = row["obj"]
        sp = obj.get("supersedes_mc_bridge_path")
        ss = obj.get("supersedes_mc_bridge_blob_sha")
        if bool(sp) != bool(ss):
            raise AssertionError("MC_SUPERSESSION_PAIR_INCOMPLETE")
        if sp:
            prev = by_rel.get(str(sp))
            if prev is None or str(prev["blob"]) != str(ss):
                raise AssertionError("MC_SUPERSESSION_PREDECESSOR_MISMATCH")
            superseded.add(str(sp))
    active = [r for r in rows if str(r["rel"]) not in superseded]
    if len(active) != 1:
        raise AssertionError(f"MC_ACTIVE_HEAD_COUNT:{len(active)}")
    return active[0]


def select_current_mc(price: dict) -> tuple[Path, str, str, dict]:
    asof = str(price.get("asof_et") or "")
    assert asof
    price_blob = git_blob(PRICE)
    pass_hash = str(price.get("pass_hash") or "")
    pass_count = int(price.get("pass_count", -1))
    rows = []
    pattern = f"canonical_mc_bridge_{asof.replace('-', '')}_*.json"
    for mc_path in sorted(ROOT.glob(pattern)):
        try:
            obj = readj(mc_path)
        except Exception:
            continue
        exact = (
            obj.get("schema") == "XRAY_MC_EPOCH_RESULT_V1"
            and obj.get("status") == "COMMITTED"
            and obj.get("asof_et") == asof
            and obj.get("policy_version") == POLICY_VERSION
            and obj.get("task_id") == TASK_ID
            and obj.get("execution") == "NONE"
            and obj.get("real_money") == "NO-GO"
            and obj.get("unknown_never_pass") is True
            and obj.get("input_blob_sha") == price_blob
            and obj.get("input_pass_hash") == pass_hash
            and int(obj.get("input_count", -1)) == pass_count
            and int((obj.get("counts") or {}).get("TOTAL", -1)) == pass_count
        )
        if exact:
            rows.append({
                "path": mc_path,
                "rel": "nasdaq-xray/" + mc_path.name,
                "blob": git_blob(mc_path),
                "obj": obj,
            })
    if not rows:
        raise AssertionError("NO_EXACT_CURRENT_MC_AUTHORITY")
    row = select_active_mc_row(rows)
    return row["path"], row["rel"], row["blob"], row["obj"]


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) and x > 0 else None
    except Exception:
        return None


def band(v):
    x = finite(v)
    if x is None:
        return "MISSING"
    if x < FAIL_CEILING:
        return "LT_2B"
    if x < PASS_FLOOR:
        return "BORDERLINE_2P0_TO_2P1B"
    return "GE_2P1B"


def sec_transport_status(probe: dict) -> str:
    rows = []
    for endpoint in ("aapl_companyfacts", "ticker_map"):
        for rec in (probe.get(endpoint) or {}).values():
            if isinstance(rec, dict):
                rows.append(rec)
    if rows and all("403" in str(r.get("error") or "") for r in rows):
        return "BLOCKED_HTTP_403"
    if any(finite(r.get("status")) == 200 for r in rows):
        return "AVAILABLE"
    return "UNPROVEN"


def classify_shadow_candidate(mc_rec: dict, nq_rec: dict | None) -> tuple[str, list[str]]:
    """Return a shadow-only candidate class and exact missing conditions.

    No return value from this function is a production C4.17 classification.
    """
    rmc = finite(mc_rec.get("rallies_market_cap_usd"))
    lmc = finite(mc_rec.get("longbridge_market_cap_usd"))
    nq = nq_rec or {}
    nmc = finite(nq.get("nasdaq_market_cap_usd"))
    pit_ok = (
        nq.get("shadow_eligible") is True
        and nq.get("close_match") is True
        and nq.get("status") == "SHADOW_ELIGIBLE"
    )
    missing = []
    if not pit_ok:
        missing.append("EXACT_SAME_ASOF_POST_CLOSE_NASDAQ_PIT")
    if nmc is None:
        missing.append("NASDAQ_MARKET_CAP_OBSERVATION")
    if rmc is None:
        missing.append("RALLIES_MARKET_CAP")
    if lmc is None:
        missing.append("LONGBRIDGE_MARKET_CAP")

    if missing:
        return "INSUFFICIENT_EXACT_PIT_OR_SOURCE_EVIDENCE", missing

    vals = [rmc, lmc, nmc]
    if all(v < FAIL_CEILING for v in vals):
        return "SHADOW_FAIL_CANDIDATE_THREE_SOURCE_SUB_2B", [
            "POLICY_SUCCESSOR_NOT_ACTIVE",
            "SHARE_CLASS_AND_CORPORATE_ACTION_CROSSCHECK_REQUIRED",
        ]
    if all(v >= PASS_FLOOR for v in vals):
        return "SHADOW_WATCH_CANDIDATE_THREE_SOURCE_GE_2P1B", [
            "POLICY_SUCCESSOR_NOT_ACTIVE",
            "PIT_TIMING_REPLAY_TEST_REQUIRED",
            "SHARE_CLASS_AND_CORPORATE_ACTION_CROSSCHECK_REQUIRED",
        ]
    return "SHADOW_UNRESOLVED_BORDERLINE_OR_CONFLICT", [
        "POLICY_SUCCESSOR_NOT_ACTIVE",
        "BORDERLINE_OR_SOURCE_CONFLICT_REQUIRES_MORE_EVIDENCE",
    ]


def selftest() -> None:
    high = {
        "rallies_market_cap_usd": 3_000_000_000,
        "longbridge_market_cap_usd": 3_100_000_000,
    }
    low = {
        "rallies_market_cap_usd": 1_800_000_000,
        "longbridge_market_cap_usd": 1_700_000_000,
    }
    high_pit = {
        "nasdaq_market_cap_usd": 3_050_000_000,
        "shadow_eligible": True,
        "close_match": True,
        "status": "SHADOW_ELIGIBLE",
    }
    low_pit = {
        "nasdaq_market_cap_usd": 1_750_000_000,
        "shadow_eligible": True,
        "close_match": True,
        "status": "SHADOW_ELIGIBLE",
    }
    stale_pit = dict(high_pit, shadow_eligible=False, status="UNKNOWN")
    st, miss = classify_shadow_candidate(high, high_pit)
    assert st == "SHADOW_WATCH_CANDIDATE_THREE_SOURCE_GE_2P1B", (st, miss)
    st, miss = classify_shadow_candidate(low, low_pit)
    assert st == "SHADOW_FAIL_CANDIDATE_THREE_SOURCE_SUB_2B", (st, miss)
    st, miss = classify_shadow_candidate(high, stale_pit)
    assert st == "INSUFFICIENT_EXACT_PIT_OR_SOURCE_EVIDENCE", (st, miss)
    assert "EXACT_SAME_ASOF_POST_CLOSE_NASDAQ_PIT" in miss
    assert band(1_999_999_999) == "LT_2B"
    assert band(2_050_000_000) == "BORDERLINE_2P0_TO_2P1B"
    assert band(2_100_000_000) == "GE_2P1B"
    r1={"rel":"nasdaq-xray/mc_v1.json","blob":"aaa","obj":{}}
    r2={"rel":"nasdaq-xray/mc_v2.json","blob":"bbb","obj":{
        "supersedes_mc_bridge_path":"nasdaq-xray/mc_v1.json",
        "supersedes_mc_bridge_blob_sha":"aaa",
    }}
    assert select_active_mc_row([r1,r2])["rel"]=="nasdaq-xray/mc_v2.json"
    try:
        select_active_mc_row([r1,{"rel":"nasdaq-xray/mc_other.json","blob":"ccc","obj":{}}])
    except AssertionError as e:
        assert str(e)=="MC_ACTIVE_HEAD_COUNT:2"
    else:
        raise AssertionError("MC_AMBIGUOUS_HEAD_SELFTEST_DID_NOT_FAIL")
    print("MC_ZERO_DOLLAR_SUCCESSOR_SHADOW_AUDIT_SELFTEST=PASS")


def main() -> None:
    terminal = readj(TERMINAL) if TERMINAL.exists() else {}
    price = readj(PRICE)
    pit = readj(NASDAQ_PIT)
    sec = readj(SEC_PROBE)

    assert int(price.get("unknown_count", -1)) == 0
    mc_path, mc_rel, mc_sha, mc = select_current_mc(price)
    evidence = (terminal.get("evidence") or {}).get("mc") or {}
    terminal_binding_current = (
        terminal.get("asof_et") == price.get("asof_et")
        and evidence.get("path") == mc_rel
        and evidence.get("blob_sha") == mc_sha
    )

    unknown = list(mc.get("unknown_symbols") or [])
    assert len(unknown) == int((mc.get("counts") or {}).get("MC_UNKNOWN", -1))
    assert set(unknown) <= set((mc.get("results") or {}).keys())

    pit_records = pit.get("records") or {}
    rows = {}
    shadow_counts = Counter()
    mc_reason_counts = Counter()
    pit_reason_counts = Counter()
    for sym in sorted(unknown):
        rec = (mc.get("results") or {}).get(sym) or {}
        nq = pit_records.get(sym) or {}
        shadow_class, missing = classify_shadow_candidate(rec, nq)
        reason = str(rec.get("reason") or "UNSPECIFIED")
        mc_reason_counts[reason] += 1
        pit_reason_counts[str(nq.get("reason") or "MISSING")] += 1
        shadow_counts[shadow_class] += 1
        rows[sym] = {
            "production_status_before": rec.get("status"),
            "production_status_after": rec.get("status"),
            "production_classification_applied": False,
            "current_c417_resolution": "NO_CHANGE_MC_UNKNOWN",
            "mc_reason": reason,
            "rallies_exchange": rec.get("rallies_exchange"),
            "rallies_market_cap_usd": finite(rec.get("rallies_market_cap_usd")),
            "rallies_band": band(rec.get("rallies_market_cap_usd")),
            "longbridge_exchange": rec.get("longbridge_exchange"),
            "longbridge_market_cap_usd": finite(rec.get("longbridge_market_cap_usd")),
            "longbridge_band": band(rec.get("longbridge_market_cap_usd")),
            "relative_difference": rec.get("relative_difference"),
            "nasdaq_pit_status": nq.get("status") or "MISSING",
            "nasdaq_pit_reason": nq.get("reason") or "MISSING",
            "nasdaq_market_cap_usd": finite(nq.get("nasdaq_market_cap_usd")),
            "nasdaq_band": band(nq.get("nasdaq_market_cap_usd")),
            "nasdaq_close_match": nq.get("close_match"),
            "nasdaq_shadow_eligible": nq.get("shadow_eligible") is True,
            "shadow_successor_candidate": shadow_class,
            "missing_or_required_evidence": missing,
        }

    production_changes = sum(
        1 for r in rows.values()
        if r["production_status_before"] != r["production_status_after"]
    )
    exact_pit_unknowns = sum(
        1 for r in rows.values() if r["nasdaq_shadow_eligible"] is True
    )
    out = {
        "schema": "XRAY_MC_ZERO_DOLLAR_SUCCESSOR_SHADOW_AUDIT_V1",
        "task_id": TASK_ID,
        "asof_et": price["asof_et"],
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "alpha_authority": False,
        "production_policy_version": POLICY_VERSION,
        "production_policy_changed": False,
        "production_classification_applied": False,
        "production_changes": production_changes,
        "source_terminal_path": "nasdaq-xray/canonical_current_terminal.json",
        "source_terminal_blob_sha": git_blob(TERMINAL) if TERMINAL.exists() else None,
        "source_terminal_asof_et": terminal.get("asof_et"),
        "terminal_binding_current": terminal_binding_current,
        "source_price_path": "nasdaq-xray/canonical_current_price_dv30.json",
        "source_price_blob_sha": git_blob(PRICE),
        "source_mc_path": mc_rel,
        "source_mc_blob_sha": mc_sha,
        "source_nasdaq_pit_path": "nasdaq-xray/nasdaq_screener_pit_current.json",
        "source_nasdaq_pit_blob_sha": git_blob(NASDAQ_PIT),
        "source_sec_probe_path": "nasdaq-xray/sec_companyfacts_probe.json",
        "source_sec_probe_blob_sha": git_blob(SEC_PROBE),
        "sec_transport_status": sec_transport_status(sec),
        "unknown_count": len(unknown),
        "unknown_symbols": sorted(unknown),
        "exact_same_asof_post_close_nasdaq_pit_unknown_count": exact_pit_unknowns,
        "mc_reason_counts": dict(sorted(mc_reason_counts.items())),
        "nasdaq_pit_reason_counts": dict(sorted(pit_reason_counts.items())),
        "shadow_candidate_counts": dict(sorted(shadow_counts.items())),
        "rows": rows,
        "successor_activation": "FORBIDDEN_SHADOW_ONLY",
        "required_before_any_future_policy_migration": [
            "PIT_TIMING_AND_HISTORICAL_ASOF_REPLAY",
            "SHARE_CLASS_AMBIGUITY",
            "DUAL_CLASS_COMPANIES",
            "ADR_AND_FOREIGN_ISSUERS",
            "SPLIT_REVERSE_SPLIT",
            "ATM_NEW_ISSUANCE",
            "BUYBACKS",
            "STALE_SHARE_COUNT",
            "SEC_TAG_CONFLICTS",
            "CORPORATE_ACTION_CONFLICTS",
            "BORDERLINE_2B_CASES",
            "OUT_OF_SAMPLE_AND_HISTORICAL_REPLAY",
        ],
    }
    assert production_changes == 0
    assert set(rows) == set(unknown)
    assert out["production_policy_changed"] is False
    OUT.write_text(json.dumps(out, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "unknown_count": len(unknown),
        "production_changes": production_changes,
        "sec_transport_status": out["sec_transport_status"],
        "exact_pit_unknown_count": exact_pit_unknowns,
        "shadow_candidate_counts": out["shadow_candidate_counts"],
    }, sort_keys=True))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
