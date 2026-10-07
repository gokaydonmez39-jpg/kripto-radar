#!/usr/bin/env python3
"""Create the immutable fail-closed base Event authority for a fresh ASOF.

This bootstrap never creates CLEAN or BLOCK.  It only materializes explicit
UNKNOWN for the exact current Event request so issuer IR / SEC primary probing
can run without inheriting stale prior-ASOF decisions.

EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN != PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from build_event_provenance_rebind import (
    blob_sha,
    build_successor_obj,
    event_semantic_snapshot,
    exact_current_binding,
    next_successor_path,
    select_active_event,
    validate_bridge_scope,
)

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
REQUEST = ROOT / "canonical_current_event_request.json"
TASK = "6a825366222081918997094d76e6ae46"
POLICY_BLOB = "16c50cc8f887a5234a4be23862d7c8d0e564b0ac"
POLICY_HASH = "68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
POLICY_VERSION = "C4.17"


def relpath(path: Path) -> str:
    return str(path.relative_to(REPO)).replace("\\", "/")


def hash_lines(values: list[str]) -> str:
    return hashlib.sha256("\n".join(values).encode()).hexdigest()


def validate_request(req: dict) -> None:
    assert req.get("schema") == "XRAY_EVENT_EPOCH_REQUEST_V1"
    assert req.get("status") == "READY"
    assert req.get("task_id") == TASK
    assert req.get("execution") == "NONE" and req.get("real_money") == "NO-GO"
    assert req.get("unknown_never_pass") is True
    assert req.get("compiled_policy_blob_sha") == POLICY_BLOB
    assert req.get("compiled_policy_hash") == POLICY_HASH
    assert req.get("compiled_policy_version") == POLICY_VERSION
    assert req.get("upstream_coverage_complete") is True

    weekly = sorted(req.get("weekly_scope") or [])
    geometry = sorted(req.get("geometry_scope") or [])
    lifecycle = sorted(req.get("lifecycle_scope") or [])
    assert len(weekly) == int(req.get("weekly_scope_count", -1))
    assert len(geometry) == int(req.get("geometry_scope_count", -1))
    assert len(lifecycle) == int(req.get("lifecycle_scope_count", -1))
    assert len(weekly) == len(set(weekly))
    assert len(geometry) == len(set(geometry))
    assert len(lifecycle) == len(set(lifecycle))
    assert set(geometry) <= set(weekly)
    assert set(lifecycle) <= set(weekly)
    assert hash_lines(weekly) == req.get("weekly_scope_hash")
    assert hash_lines(geometry) == req.get("geometry_scope_hash")
    assert hash_lines(lifecycle) == req.get("lifecycle_scope_hash")
    assert len(req.get("future_horizon_sessions") or []) == 8

    rd = req.get("required_discovery") or {}
    assert rd.get("required") is False
    assert rd.get("role") == "OPTIONAL_ACCELERATOR_ONLY"
    assert rd.get("provider_failure_never_clears_or_blocks") is True
    assert rd.get("geometry_direct_official_fallback_required") is True
    assert rd.get("paid_topup_forbidden") is True

    for key in ("stage1", "regime", "deep_geometry"):
        p = req.get(f"source_{key}_path")
        s = req.get(f"source_{key}_blob_sha")
        assert p and s
        fp = REPO / p
        assert fp.exists() and blob_sha(fp) == s, (key, p, s)


def scope_equivalent_rows(req: dict) -> list[dict]:
    """Same-ASOF/same-policy/same-scope bridges, regardless of source blob rebinding."""
    stamp = str(req["asof_et"]).replace("-", "")
    rows = []
    for path in sorted(ROOT.glob(f"canonical_event_bridge_{stamp}_c417*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            validate_bridge_scope(obj, req)
            rows.append({
                "path": relpath(path),
                "file": path,
                "blob": blob_sha(path),
                "obj": obj,
            })
        except Exception:
            continue
    return rows


def exact_current_rows(req: dict) -> list[dict]:
    request_blob = blob_sha(REQUEST)
    return [
        r for r in scope_equivalent_rows(req)
        if exact_current_binding(r["obj"], req, request_blob)
    ]


def build_base(req: dict, version: int) -> dict:
    weekly = sorted(req.get("weekly_scope") or [])
    geometry = set(req.get("geometry_scope") or [])
    status = {sym: "UNKNOWN" for sym in weekly}
    unresolved = {}
    for sym in weekly:
        unresolved[sym] = {
            "reason": "OPTIONAL_DISCOVERY_PROVIDER_UNAVAILABLE",
            "provider": "PROVIDER_NEUTRAL_ZERO_DOLLAR_DISCOVERY",
            "role": "CURRENT_GEOMETRY_SCOPE" if sym in geometry else "CURRENT_WEEKLY_NON_GEOMETRY_SCOPE",
            "provider_attempted": False,
            "official_confirmation": "PENDING_DIRECT_OFFICIAL_PRIMARY",
            "fail_closed": True,
        }

    affected = sorted(geometry)
    out = {
        "schema": "XRAY_EVENT_EPOCH_RESULT_V1",
        "status": "COMMITTED",
        "authority": f"CANONICAL_EVENT_BRIDGE_C4_17_DV30_OPTIONAL_DISCOVERY_FAIL_CLOSED_BASE_V{version}",
        "task_id": TASK,
        "asof_et": req["asof_et"],
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "compiled_policy_path": req.get("compiled_policy_path"),
        "compiled_policy_blob_sha": req.get("compiled_policy_blob_sha"),
        "compiled_policy_hash": req.get("compiled_policy_hash"),
        "compiled_policy_version": req.get("compiled_policy_version"),
        "weekly_scope": weekly,
        "weekly_scope_count": len(weekly),
        "weekly_scope_hash": req.get("weekly_scope_hash"),
        "geometry_scope": sorted(geometry),
        "geometry_scope_count": len(geometry),
        "geometry_scope_hash": req.get("geometry_scope_hash"),
        "lifecycle_scope": sorted(req.get("lifecycle_scope") or []),
        "lifecycle_scope_count": len(req.get("lifecycle_scope") or []),
        "lifecycle_scope_hash": req.get("lifecycle_scope_hash"),
        "source_stage1_path": req.get("source_stage1_path"),
        "source_stage1_blob_sha": req.get("source_stage1_blob_sha"),
        "source_regime_path": req.get("source_regime_path"),
        "source_regime_blob_sha": req.get("source_regime_blob_sha"),
        "source_deep_geometry_path": req.get("source_deep_geometry_path"),
        "source_deep_geometry_blob_sha": req.get("source_deep_geometry_blob_sha"),
        "source_request_path": "nasdaq-xray/canonical_current_event_request.json",
        "source_request_blob_sha": blob_sha(REQUEST),
        "past_family_c_sessions": list(req.get("past_family_c_sessions") or []),
        "future_horizon_sessions": list(req.get("future_horizon_sessions") or []),
        "event_status_by_symbol": status,
        "confirmed_blocks": {},
        "unresolved": unresolved,
        "clean_discovery_count": 0,
        "confirmed_block_count": 0,
        "unresolved_count": len(weekly),
        "affected_geometry_event_unknown": affected,
        "affected_geometry_event_unknown_count": len(affected),
        "family_c_events": {},
        "discovery_hits": [],
        "pagination_complete": False,
        "coverage_complete": False,
        "partial_data": True,
        "discovery_unavailable_symbols": weekly,
        "provider_unavailable_but_officially_resolved_symbols": [],
        "official_horizon_clearance": {},
        "discovery_proof": {
            "provider": "PROVIDER_NEUTRAL_ZERO_DOLLAR_DISCOVERY",
            "required_by_request": False,
            "mode": "OPTIONAL_ACCELERATOR_UNAVAILABLE_DIRECT_OFFICIAL_PRIMARY_PENDING",
            "provider_call_attempted": False,
            "provider_result": "NOT_REQUIRED_FOR_FAIL_CLOSED_BOOTSTRAP",
            "paid_top_up": False,
            "stale_prior_asof_event_evidence_reused": False,
            "every_uncovered_symbol_explicit_unknown": True,
        },
        "source_policy": {
            "discovery": "OPTIONAL_PROVIDER_NEUTRAL_DISCOVERY_ACCELERATOR",
            "official_confirmation": "ISSUER_IR_OR_SEC_PRIMARY_REQUIRED_TO_CLEAR_OR_BLOCK",
            "provider_unavailable_rule": "DIRECT_OFFICIAL_PRIMARY_BEFORE_GEOMETRY_UNKNOWN",
            "geometry_unknown_rule": "UNRESOLVED_INTERSECT_CURRENT_GEOMETRY_BLOCKS_FULL_E2E",
            "unknown_never_pass": True,
        },
        "semantic_rebind": {
            "rule": "FRESH_CURRENT_ASOF_FAIL_CLOSED_OPTIONAL_DISCOVERY_BOOTSTRAP_V1",
            "current_request_blob_sha": blob_sha(REQUEST),
            "weekly_scope_hash": req.get("weekly_scope_hash"),
            "geometry_scope_hash": req.get("geometry_scope_hash"),
            "lifecycle_scope_hash": req.get("lifecycle_scope_hash"),
            "no_alpha_threshold_change": True,
            "no_event_semantics_change": True,
            "affected_geometry_event_unknown_count": len(affected),
            "no_event_provider_refetch": True,
            "unknown_never_pass": True,
        },
        "rebind_proof": {
            "exact_current_stage1_binding": True,
            "exact_current_regime_binding": True,
            "exact_current_deep_geometry_binding": True,
            "exact_current_request_binding": True,
            "prior_asof_event_semantics_reused": False,
            "optional_discovery_only": True,
            "direct_official_primary_pending": True,
            "no_alpha_threshold_change": True,
            "event_semantics_unchanged": True,
            "unknown_never_pass": True,
        },
        "committed_by": "XRAY_EVENT_FAIL_CLOSED_BASE_BOOTSTRAP",
    }
    return out


def selftest() -> None:
    req = {
        "asof_et": "2026-10-07",
        "weekly_scope": ["AAA", "BBB"],
        "geometry_scope": ["BBB"],
        "lifecycle_scope": [],
        "weekly_scope_count": 2,
        "geometry_scope_count": 1,
        "lifecycle_scope_count": 0,
        "weekly_scope_hash": hash_lines(["AAA", "BBB"]),
        "geometry_scope_hash": hash_lines(["BBB"]),
        "lifecycle_scope_hash": hash_lines([]),
        "source_stage1_path": "s1",
        "source_stage1_blob_sha": "s1sha",
        "source_regime_path": "reg",
        "source_regime_blob_sha": "regsha",
        "source_deep_geometry_path": "deep",
        "source_deep_geometry_blob_sha": "deepsha",
        "compiled_policy_path": "p",
        "compiled_policy_blob_sha": POLICY_BLOB,
        "compiled_policy_hash": POLICY_HASH,
        "compiled_policy_version": POLICY_VERSION,
        "past_family_c_sessions": ["2026-10-06"],
        "future_horizon_sessions": [
            "2026-10-08","2026-10-09","2026-10-12","2026-10-13",
            "2026-10-14","2026-10-15","2026-10-16","2026-10-19",
        ],
    }
    # Avoid filesystem binding in this object-level self-test.
    global REQUEST
    old = REQUEST
    try:
        # build_base only needs REQUEST for its blob; test semantic body with a
        # temporary exact request file under ROOT.
        tmp = ROOT / ".event_base_selftest_request.json"
        tmp.write_text("{}\n", encoding="utf-8")
        REQUEST = tmp
        out = build_base(req, 1)
        assert out["clean_discovery_count"] == 0
        assert out["confirmed_block_count"] == 0
        assert out["unresolved_count"] == 2
        assert out["event_status_by_symbol"] == {"AAA":"UNKNOWN","BBB":"UNKNOWN"}
        assert out["affected_geometry_event_unknown"] == ["BBB"]
        assert out["unresolved"]["BBB"]["fail_closed"] is True
        assert out["source_policy"]["discovery"] == "OPTIONAL_PROVIDER_NEUTRAL_DISCOVERY_ACCELERATOR"
        assert out["discovery_proof"]["paid_top_up"] is False
        request_blob = blob_sha(tmp)
        assert exact_current_binding(out, req, request_blob) is True
        stale = deepcopy(out)
        stale["source_stage1_blob_sha"] = "stale-stage1"
        assert exact_current_binding(stale, req, request_blob) is False
        rebound = build_successor_obj(
            stale,
            "nasdaq-xray/canonical_event_bridge_20261007_c417_dv30_v1.json",
            "predecessor-blob",
            req,
            request_blob,
            2,
        )
        validate_bridge_scope(rebound, req)
        assert exact_current_binding(rebound, req, request_blob) is True
        assert event_semantic_snapshot(rebound) == event_semantic_snapshot(stale)
        assert rebound["event_status_by_symbol"] == stale["event_status_by_symbol"]
        assert rebound["unresolved"] == stale["unresolved"]
    finally:
        REQUEST = old
        try:
            tmp.unlink()
        except Exception:
            pass
    print("EVENT_FAIL_CLOSED_BASE_BOOTSTRAP_SELFTEST=PASS")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    req = json.loads(REQUEST.read_text(encoding="utf-8"))
    validate_request(req)
    request_blob = blob_sha(REQUEST)
    rows = scope_equivalent_rows(req)
    exact_rows = [
        r for r in rows
        if exact_current_binding(r["obj"], req, request_blob)
    ]
    if exact_rows:
        active = select_active_event(exact_rows)
        print(json.dumps({
            "status": "EXACT_CURRENT_EVENT_BRIDGE_EXISTS",
            "path": active["path"],
            "blob_sha": active["blob"],
        }, sort_keys=True))
        return

    # If Event scope/horizon/policy are unchanged but upstream source blobs were
    # deterministically rebuilt, preserve the already-proven Event decisions
    # and create an immutable provenance-only successor. Do not reset valid
    # issuer-primary evidence to UNKNOWN merely because source provenance moved.
    if rows:
        active = select_active_event(rows)
        out_path, version = next_successor_path(req)
        if out_path.exists():
            raise RuntimeError("EVENT_BASE_IMMUTABLE_PATH_CONFLICT")
        obj = build_successor_obj(
            active["obj"], active["path"], active["blob"],
            req, request_blob, version,
        )
        validate_bridge_scope(obj, req)
        assert exact_current_binding(obj, req, request_blob)
        assert event_semantic_snapshot(obj) == event_semantic_snapshot(active["obj"])
        if args.dry_run:
            print(json.dumps({
                "status": "DRY_RUN_BASE_REQUIRED",
                "path": relpath(out_path),
                "version": version,
                "reason": "PROVENANCE_ONLY_EVENT_REBIND_NO_REDISCOVERY",
            }, sort_keys=True))
            return
        out_path.write_text(
            json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "status": "BASE_CANDIDATE_WRITTEN_LOCAL_ONLY",
            "path": relpath(out_path),
            "blob_sha": blob_sha(out_path),
            "weekly_unknown": obj["unresolved_count"],
            "affected_geometry_unknown": obj["affected_geometry_event_unknown_count"],
            "reason": "PROVENANCE_ONLY_EVENT_REBIND_NO_REDISCOVERY",
        }, sort_keys=True))
        return

    out_path, version = next_successor_path(req)
    if out_path.exists():
        raise RuntimeError("EVENT_BASE_IMMUTABLE_PATH_CONFLICT")
    obj = build_base(req, version)
    validate_bridge_scope(obj, req)
    if args.dry_run:
        print(json.dumps({
            "status": "DRY_RUN_BASE_REQUIRED",
            "path": relpath(out_path),
            "version": version,
            "weekly_unknown": obj["unresolved_count"],
            "affected_geometry_unknown": obj["affected_geometry_event_unknown_count"],
        }, sort_keys=True))
        return
    out_path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "BASE_CANDIDATE_WRITTEN_LOCAL_ONLY",
        "path": relpath(out_path),
        "blob_sha": blob_sha(out_path),
        "weekly_unknown": obj["unresolved_count"],
        "affected_geometry_unknown": obj["affected_geometry_event_unknown_count"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
