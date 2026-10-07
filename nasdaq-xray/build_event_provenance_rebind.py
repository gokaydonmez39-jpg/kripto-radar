#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
TASK = "6a825366222081918997094d76e6ae46"
POLICY_HASH = "68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
POLICY_VERSION = "C4.17"
POLICY_BLOB = "16c50cc8f887a5234a4be23862d7c8d0e564b0ac"
REQUEST_REL = "nasdaq-xray/canonical_current_event_request.json"
REQUEST = REPO / REQUEST_REL

PROVENANCE_KEYS = {
    "authority",
    "source_stage1_path","source_stage1_blob_sha",
    "source_regime_path","source_regime_blob_sha",
    "source_deep_geometry_path","source_deep_geometry_blob_sha",
    "source_request_path","source_request_blob_sha",
    "supersedes_event_bridge_path","supersedes_event_bridge_blob_sha",
    "semantic_rebind","rebind_proof","committed_by",
}

def blob_sha(path: Path) -> str:
    return subprocess.check_output(["git","hash-object",str(path)], cwd=REPO, text=True).strip()

def relpath(path: Path) -> str:
    return str(path.relative_to(REPO)).replace("\\","/")

def event_semantic_snapshot(obj: dict) -> dict:
    return {k: deepcopy(v) for k,v in obj.items() if k not in PROVENANCE_KEYS}

def validate_request(req: dict) -> None:
    assert req.get("schema")=="XRAY_EVENT_EPOCH_REQUEST_V1"
    assert req.get("status")=="READY"
    assert req.get("task_id")==TASK
    assert req.get("execution")=="NONE" and req.get("real_money")=="NO-GO"
    assert req.get("unknown_never_pass") is True
    assert req.get("compiled_policy_hash")==POLICY_HASH
    assert req.get("compiled_policy_version")==POLICY_VERSION
    assert req.get("compiled_policy_blob_sha")==POLICY_BLOB
    assert req.get("request_scope_complete") is True
    assert len(req.get("weekly_scope") or [])==int(req.get("weekly_scope_count",-1))
    assert len(req.get("geometry_scope") or [])==int(req.get("geometry_scope_count",-1))
    assert len(req.get("lifecycle_scope") or [])==int(req.get("lifecycle_scope_count",-1))
    assert req.get("weekly_scope_hash")
    assert req.get("geometry_scope_hash")
    assert req.get("lifecycle_scope_hash")

def validate_bridge_scope(bridge: dict, req: dict) -> None:
    assert bridge.get("schema")=="XRAY_EVENT_EPOCH_RESULT_V1"
    assert bridge.get("status")=="COMMITTED"
    assert bridge.get("task_id")==TASK
    assert bridge.get("execution")=="NONE" and bridge.get("real_money")=="NO-GO"
    assert bridge.get("unknown_never_pass") is True
    assert bridge.get("asof_et")==req.get("asof_et")
    assert bridge.get("compiled_policy_hash")==POLICY_HASH
    assert bridge.get("compiled_policy_version")==POLICY_VERSION
    assert bridge.get("compiled_policy_blob_sha")==POLICY_BLOB
    assert bridge.get("weekly_scope_count")==req.get("weekly_scope_count")
    assert bridge.get("weekly_scope_hash")==req.get("weekly_scope_hash")
    assert bridge.get("geometry_scope_count")==req.get("geometry_scope_count")
    assert bridge.get("geometry_scope_hash")==req.get("geometry_scope_hash")
    sr=bridge.get("semantic_rebind") or {}
    opr=bridge.get("official_primary_refresh") or {}
    proof=bridge.get("rebind_proof") or {}
    direct_primary_refresh=(sr.get("rule")=="OPTIONAL_DISCOVERY_DIRECT_OFFICIAL_PRIMARY_RESOLUTION_V1")
    legacy_official_primary_successor=bool(
        sr.get("event_decisions_changed_with_new_primary_evidence") is True
        and sr.get("event_policy_semantics_unchanged") is True
        and proof.get("direct_official_primary_reverification") is True
        and bridge.get("committed_by")=="OPENAI_FOREGROUND_ZERO_DOLLAR_ISSUER_PRIMARY_PROBE"
        and "OFFICIAL_PRIMARY_SUCCESSOR" in str(bridge.get("authority") or "")
    )
    if opr or direct_primary_refresh or legacy_official_primary_successor:
        if opr:
            assert opr.get("schema")=="XRAY_EVENT_OFFICIAL_PRIMARY_REFRESH_V1"
            assert opr.get("lifecycle_scope_hash")==req.get("lifecycle_scope_hash")
            assert opr.get("weekly_scope_hash")==req.get("weekly_scope_hash")
            assert opr.get("geometry_scope_hash")==req.get("geometry_scope_hash")
            assert opr.get("no_alpha_threshold_change") is True
            assert opr.get("official_primary_only") is True
            assert opr.get("unknown_never_pass") is True
            resolved=set(opr.get("resolved_symbols") or [])
        else:
            assert sr.get("lifecycle_scope_hash")==req.get("lifecycle_scope_hash")
            assert sr.get("weekly_scope_hash")==req.get("weekly_scope_hash")
            assert sr.get("geometry_scope_hash")==req.get("geometry_scope_hash")
            assert sr.get("no_alpha_threshold_change") is True
            assert sr.get("no_event_horizon_change") is True
            if direct_primary_refresh:
                assert sr.get("decisions_changed_only_with_primary_evidence") is True
            else:
                assert legacy_official_primary_successor
            resolved=set(bridge.get("provider_unavailable_but_officially_resolved_symbols") or [])
            if "official_resolved_count" in sr:
                assert int(sr.get("official_resolved_count",-1))==len(resolved)
        geometry=set(req.get("geometry_scope") or [])
        assert resolved and resolved<=geometry
        assert resolved==set(bridge.get("provider_unavailable_but_officially_resolved_symbols") or [])
        clearance=bridge.get("official_horizon_clearance") or {}
        status=bridge.get("event_status_by_symbol") or {}
        horizon=set(req.get("future_horizon_sessions") or [])
        horizon_end=max(horizon or {""})
        for sym in resolved:
            rec=clearance.get(sym) or {}
            st=status.get(sym)
            assert st in {"CLEAN_DISCOVERY","BLOCK_CONFIRMED_8SESSION"}
            assert rec.get("authority") in {"ISSUER_IR_PRIMARY","SEC_PRIMARY"}
            assert rec.get("official_source_url")
            dt=str(rec.get("next_event_date") or rec.get("event_date") or "")[:10]
            if st=="CLEAN_DISCOVERY":
                assert dt and dt>horizon_end
            else:
                assert dt in horizon
    else:
        assert sr.get("lifecycle_scope_hash")==req.get("lifecycle_scope_hash")
        assert sr.get("weekly_scope_hash")==req.get("weekly_scope_hash")
        assert sr.get("geometry_scope_hash")==req.get("geometry_scope_hash")
        assert sr.get("no_alpha_threshold_change") is True
        assert sr.get("no_event_semantics_change") is True
    assert list(bridge.get("past_family_c_sessions") or [])==list(req.get("past_family_c_sessions") or [])
    assert list(bridge.get("future_horizon_sessions") or [])==list(req.get("future_horizon_sessions") or [])
    rd=req.get("required_discovery") or {}
    sp=bridge.get("source_policy") or {}
    if rd.get("required") is False or rd.get("role")=="OPTIONAL_ACCELERATOR_ONLY":
        assert sp.get("discovery")=="OPTIONAL_PROVIDER_NEUTRAL_DISCOVERY_ACCELERATOR"
        assert sp.get("official_confirmation")=="ISSUER_IR_OR_SEC_PRIMARY_REQUIRED_TO_CLEAR_OR_BLOCK"
        assert sp.get("provider_unavailable_rule")=="DIRECT_OFFICIAL_PRIMARY_BEFORE_GEOMETRY_UNKNOWN"
        assert sp.get("unknown_never_pass") is True

def monotonic_weekly_scope_shrink(predecessor: dict, req: dict) -> list[str]:
    """Return removed non-geometry symbols for a safe same-ASOF scope shrink.

    This is deliberately narrow: no additions, identical geometry/lifecycle and
    identical Event windows/policy. It changes only which weekly non-geometry
    symbols remain in scope; retained symbol decisions are never changed.
    """
    assert predecessor.get("schema") == "XRAY_EVENT_EPOCH_RESULT_V1"
    assert predecessor.get("status") == "COMMITTED"
    assert predecessor.get("task_id") == TASK
    assert predecessor.get("execution") == "NONE" and predecessor.get("real_money") == "NO-GO"
    assert predecessor.get("unknown_never_pass") is True
    assert predecessor.get("asof_et") == req.get("asof_et")
    assert predecessor.get("compiled_policy_hash") == POLICY_HASH
    assert predecessor.get("compiled_policy_version") == POLICY_VERSION
    assert predecessor.get("compiled_policy_blob_sha") == POLICY_BLOB
    assert list(predecessor.get("past_family_c_sessions") or []) == list(req.get("past_family_c_sessions") or [])
    assert list(predecessor.get("future_horizon_sessions") or []) == list(req.get("future_horizon_sessions") or [])

    old_weekly = set(predecessor.get("weekly_scope") or [])
    new_weekly = set(req.get("weekly_scope") or [])
    assert new_weekly < old_weekly, "NOT_STRICT_WEEKLY_SCOPE_SHRINK"
    removed = sorted(old_weekly - new_weekly)

    old_geometry = set(predecessor.get("geometry_scope") or [])
    new_geometry = set(req.get("geometry_scope") or [])
    old_lifecycle = set(predecessor.get("lifecycle_scope") or [])
    new_lifecycle = set(req.get("lifecycle_scope") or [])
    assert old_geometry == new_geometry
    assert old_lifecycle == new_lifecycle
    assert not (set(removed) & new_geometry)
    assert not (set(removed) & new_lifecycle)

    status = predecessor.get("event_status_by_symbol") or {}
    assert set(status) == old_weekly
    assert new_weekly <= set(status)
    unresolved = predecessor.get("unresolved") or {}
    assert set(unresolved) <= old_weekly
    assert int(predecessor.get("unresolved_count", -1)) == len(unresolved)
    return removed


def load_monotonic_shrink_rows(req: dict):
    stamp = str(req["asof_et"]).replace("-", "")
    rows = []
    for p in sorted(ROOT.glob(f"canonical_event_bridge_{stamp}_c417*.json")):
        try:
            j = json.loads(p.read_text())
            removed = monotonic_weekly_scope_shrink(j, req)
            rows.append({"path": relpath(p), "file": p, "blob": blob_sha(p), "obj": j, "removed": removed})
        except Exception:
            continue
    return rows


def _filter_symbol_container(value, keep: set[str]):
    if isinstance(value, dict):
        return {k: deepcopy(v) for k, v in value.items() if k in keep}
    if isinstance(value, list):
        return [deepcopy(x) for x in value if not isinstance(x, str) or x in keep]
    return deepcopy(value)


def build_scope_shrink_successor_obj(predecessor: dict, predecessor_path: str, predecessor_blob: str,
                                     req: dict, request_blob: str, version: int) -> dict:
    removed = monotonic_weekly_scope_shrink(predecessor, req)
    keep = set(req.get("weekly_scope") or [])
    out = deepcopy(predecessor)

    out["authority"] = f"CANONICAL_EVENT_BRIDGE_C4_17_DV30_MONOTONIC_WEEKLY_SCOPE_SHRINK_V{version}"
    out["weekly_scope"] = list(req.get("weekly_scope") or [])
    out["weekly_scope_count"] = int(req.get("weekly_scope_count", len(out["weekly_scope"])))
    out["weekly_scope_hash"] = req.get("weekly_scope_hash")
    out["geometry_scope"] = list(req.get("geometry_scope") or [])
    out["geometry_scope_count"] = int(req.get("geometry_scope_count", len(out["geometry_scope"])))
    out["geometry_scope_hash"] = req.get("geometry_scope_hash")
    out["lifecycle_scope"] = list(req.get("lifecycle_scope") or [])
    out["lifecycle_scope_count"] = int(req.get("lifecycle_scope_count", len(out["lifecycle_scope"])))
    out["lifecycle_scope_hash"] = req.get("lifecycle_scope_hash")

    for key in (
        "event_status_by_symbol",
        "unresolved",
        "discovery_hits",
        "official_horizon_clearance",
        "discovery_unavailable_symbols",
        "provider_unavailable_but_officially_resolved_symbols",
        "confirmed_blocks",
    ):
        if key in out:
            out[key] = _filter_symbol_container(out.get(key), keep)

    status = out.get("event_status_by_symbol") or {}
    unresolved = out.get("unresolved") or {}
    geometry = set(out.get("geometry_scope") or [])
    affected = sorted(s for s, st in status.items() if st == "UNKNOWN" and s in geometry)
    out["unresolved_count"] = len(unresolved)
    out["clean_discovery_count"] = sum(1 for st in status.values() if st == "CLEAN_DISCOVERY")
    out["confirmed_block_count"] = sum(1 for st in status.values() if st == "BLOCK_CONFIRMED_8SESSION")
    out["affected_geometry_event_unknown"] = affected
    out["affected_geometry_event_unknown_count"] = len(affected)

    for key in ("source_stage1_path","source_stage1_blob_sha",
                "source_regime_path","source_regime_blob_sha",
                "source_deep_geometry_path","source_deep_geometry_blob_sha"):
        out[key] = req.get(key)
    out["source_request_path"] = REQUEST_REL
    out["source_request_blob_sha"] = request_blob
    out["supersedes_event_bridge_path"] = predecessor_path
    out["supersedes_event_bridge_blob_sha"] = predecessor_blob
    out["committed_by"] = "XRAY_FINAL_EVENT_SCOPE_SHRINK_FACTORY"

    old_proof = deepcopy(predecessor.get("rebind_proof") or {})
    old_proof.update({
        "exact_current_stage1_binding": True,
        "exact_current_regime_binding": True,
        "exact_current_deep_geometry_binding": True,
        "provenance_only_current_request_rebind": False,
        "monotonic_weekly_scope_shrink": True,
        "removed_symbols": removed,
        "removed_symbols_non_geometry": True,
        "removed_symbols_non_lifecycle": True,
        "retained_symbol_event_decisions_unchanged": True,
        "no_event_provider_refetch": True,
        "no_alpha_threshold_change": True,
        "event_semantics_unchanged": True,
        "remaining_unresolved_count": len(unresolved),
        "remaining_geometry_event_unknown_count": len(affected),
    })
    out["rebind_proof"] = old_proof
    out["semantic_rebind"] = {
        "rule": "MONOTONIC_WEEKLY_SCOPE_SHRINK_NON_GEOMETRY_ONLY_V1",
        "current_request_blob_sha": request_blob,
        "predecessor_weekly_scope_count": int(predecessor.get("weekly_scope_count", -1)),
        "current_weekly_scope_count": int(req.get("weekly_scope_count", -1)),
        "removed_symbols": removed,
        "weekly_scope_hash": req.get("weekly_scope_hash"),
        "geometry_scope_hash": req.get("geometry_scope_hash"),
        "lifecycle_scope_hash": req.get("lifecycle_scope_hash"),
        "no_weekly_symbol_addition": True,
        "geometry_scope_unchanged": True,
        "lifecycle_scope_unchanged": True,
        "retained_symbol_event_decisions_unchanged": True,
        "no_alpha_threshold_change": True,
        "no_event_semantics_change": True,
        "affected_geometry_event_unknown_count": len(affected),
        "predecessor_path": predecessor_path,
        "predecessor_blob_sha": predecessor_blob,
        "no_event_provider_refetch": True,
    }

    assert set(out.get("event_status_by_symbol") or {}) == keep
    assert set(out.get("unresolved") or {}) <= keep
    assert int(out.get("unresolved_count", -1)) == len(out.get("unresolved") or {})
    assert int(out.get("affected_geometry_event_unknown_count", -1)) == len(affected)
    for sym in keep:
        assert (out.get("event_status_by_symbol") or {}).get(sym) == (predecessor.get("event_status_by_symbol") or {}).get(sym)
    return out


def selftest() -> None:
    base = {
        "schema": "XRAY_EVENT_EPOCH_RESULT_V1",
        "status": "COMMITTED",
        "task_id": TASK,
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "asof_et": "2026-10-06",
        "compiled_policy_hash": POLICY_HASH,
        "compiled_policy_version": POLICY_VERSION,
        "compiled_policy_blob_sha": POLICY_BLOB,
        "past_family_c_sessions": ["2026-10-06"],
        "future_horizon_sessions": ["2026-10-07"],
        "weekly_scope": ["A","B"],
        "weekly_scope_count": 2,
        "geometry_scope": ["A"],
        "lifecycle_scope": [],
        "event_status_by_symbol": {"A":"UNKNOWN","B":"UNKNOWN"},
        "unresolved": {"A":{},"B":{}},
        "unresolved_count": 2,
    }
    req = {
        "asof_et": "2026-10-06",
        "past_family_c_sessions": ["2026-10-06"],
        "future_horizon_sessions": ["2026-10-07"],
        "weekly_scope": ["A"],
        "geometry_scope": ["A"],
        "lifecycle_scope": [],
    }
    assert monotonic_weekly_scope_shrink(base, req) == ["B"]
    bad_add = deepcopy(req); bad_add["weekly_scope"] = ["A","C"]
    try:
        monotonic_weekly_scope_shrink(base, bad_add)
    except AssertionError:
        pass
    else:
        raise AssertionError("WEEKLY_ADDITION_MUST_NOT_SHRINK_REBIND")
    bad_geom = deepcopy(req); bad_geom["weekly_scope"] = ["B"]; bad_geom["geometry_scope"] = ["B"]
    try:
        monotonic_weekly_scope_shrink(base, bad_geom)
    except AssertionError:
        pass
    else:
        raise AssertionError("REMOVING_GEOMETRY_SYMBOL_MUST_FAIL")
    print("EVENT_SCOPE_SHRINK_SELFTEST=PASS")


def load_valid_rows(req: dict):
    stamp=str(req["asof_et"]).replace("-","")
    rows=[]
    for p in sorted(ROOT.glob(f"canonical_event_bridge_{stamp}_c417*.json")):
        try:
            j=json.loads(p.read_text())
            validate_bridge_scope(j,req)
            rows.append({"path":relpath(p),"file":p,"blob":blob_sha(p),"obj":j})
        except Exception:
            continue
    return rows

def select_active_event(rows):
    by_path={r["path"]:r for r in rows}
    valid=[]
    for r in rows:
        j=r["obj"]
        sp=j.get("supersedes_event_bridge_path")
        ss=j.get("supersedes_event_bridge_blob_sha")
        if not sp and not ss:
            valid.append(r)
            continue
        if not sp or not ss:
            continue
        pred=by_path.get(sp)
        if pred is not None:
            if pred["blob"]!=ss:
                continue
        else:
            pred_file=REPO/sp
            if not pred_file.exists() or blob_sha(pred_file)!=ss:
                continue
        valid.append(r)
    superseded={
        r["obj"].get("supersedes_event_bridge_path")
        for r in valid
        if r["obj"].get("supersedes_event_bridge_path")
        and r["obj"].get("supersedes_event_bridge_blob_sha")
    }
    active=[r for r in valid if r["path"] not in superseded]
    assert len(active)==1,(
        "AMBIGUOUS_ACTIVE_EVENT_AUTHORITY",
        [r["path"] for r in active],
        [r["path"] for r in valid],
    )
    return active[0]

def exact_current_binding(bridge: dict, req: dict, request_blob: str) -> bool:
    return bool(
        bridge.get("source_stage1_path")==req.get("source_stage1_path")
        and bridge.get("source_stage1_blob_sha")==req.get("source_stage1_blob_sha")
        and bridge.get("source_regime_path")==req.get("source_regime_path")
        and bridge.get("source_regime_blob_sha")==req.get("source_regime_blob_sha")
        and bridge.get("source_deep_geometry_path")==req.get("source_deep_geometry_path")
        and bridge.get("source_deep_geometry_blob_sha")==req.get("source_deep_geometry_blob_sha")
        and bridge.get("source_request_path")==REQUEST_REL
        and bridge.get("source_request_blob_sha")==request_blob
    )

def next_successor_path(req: dict) -> tuple[Path,int]:
    stamp=str(req["asof_et"]).replace("-","")
    rx=re.compile(rf"^canonical_event_bridge_{stamp}_c417_dv30_v(\d+)\.json$")
    versions=[]
    for p in ROOT.glob(f"canonical_event_bridge_{stamp}_c417_dv30_v*.json"):
        m=rx.match(p.name)
        if m:
            versions.append(int(m.group(1)))
    version=(max(versions) if versions else 0)+1
    return ROOT/f"canonical_event_bridge_{stamp}_c417_dv30_v{version}.json",version

def build_successor_obj(predecessor: dict, predecessor_path: str, predecessor_blob: str,
                        req: dict, request_blob: str, version: int) -> dict:
    before=event_semantic_snapshot(predecessor)
    out=deepcopy(predecessor)
    out["authority"]=f"CANONICAL_EVENT_BRIDGE_C4_17_DV30_PROVENANCE_REBIND_V{version}"
    for key in ("source_stage1_path","source_stage1_blob_sha",
                "source_regime_path","source_regime_blob_sha",
                "source_deep_geometry_path","source_deep_geometry_blob_sha"):
        out[key]=req.get(key)
    out["source_request_path"]=REQUEST_REL
    out["source_request_blob_sha"]=request_blob
    out["supersedes_event_bridge_path"]=predecessor_path
    out["supersedes_event_bridge_blob_sha"]=predecessor_blob
    out["committed_by"]="XRAY_FINAL_EVENT_PROVENANCE_REBIND_FACTORY"
    old_proof=deepcopy(predecessor.get("rebind_proof") or {})
    old_proof.update({
        "exact_current_stage1_binding":True,
        "exact_current_regime_binding":True,
        "exact_current_deep_geometry_binding":True,
        "provenance_only_current_request_rebind":True,
        "no_event_provider_refetch":True,
        "no_alpha_threshold_change":True,
        "event_semantics_unchanged":True,
    })
    out["rebind_proof"]=old_proof
    out["semantic_rebind"]={
        "rule":"SAME_ASOF_IDENTICAL_WEEKLY_GEOMETRY_LIFECYCLE_AND_EVENT_HORIZON;EVENT_DECISIONS_REUSED;SOURCE_BLOBS_REBOUND_ONLY",
        "current_request_blob_sha":request_blob,
        "weekly_scope_hash":req.get("weekly_scope_hash"),
        "geometry_scope_hash":req.get("geometry_scope_hash"),
        "lifecycle_scope_hash":req.get("lifecycle_scope_hash"),
        "no_alpha_threshold_change":True,
        "no_event_semantics_change":True,
        "affected_geometry_event_unknown_count":int(predecessor.get("affected_geometry_event_unknown_count",0)),
        "predecessor_path":predecessor_path,
        "predecessor_blob_sha":predecessor_blob,
        "no_event_provider_refetch":True,
    }
    assert event_semantic_snapshot(out)==before,"EVENT_SEMANTICS_MUTATION_FORBIDDEN"
    return out

def main() -> None:
    req=json.loads(REQUEST.read_text())
    validate_request(req)
    request_blob=blob_sha(REQUEST)
    rows=load_valid_rows(req)
    shrink_mode=False
    if rows:
        active=select_active_event(rows)
    else:
        shrink_rows=load_monotonic_shrink_rows(req)
        if not shrink_rows:
            print("ready=false")
            print("created=false")
            print("pending_reason=EVENT_DISCOVERY_REQUIRED_NO_EQUIVALENT_BRIDGE")
            print("request_blob_sha="+request_blob)
            print("reason=UPSTREAM_EVENT_DISCOVERY_PENDING_FAIL_CLOSED")
            return
        active=select_active_event(shrink_rows)
        shrink_mode=True
    pred=active["obj"]
    if not shrink_mode and exact_current_binding(pred,req,request_blob):
        print("ready=true")
        print("created=false")
        print("path="+active["path"])
        print("request_blob_sha="+request_blob)
        print("reason=EXACT_CURRENT_EVENT_BRIDGE_ALREADY_EXISTS")
        return
    out_path,version=next_successor_path(req)
    assert not out_path.exists(),("SUCCESSOR_PATH_ALREADY_EXISTS",relpath(out_path))
    if shrink_mode:
        out=build_scope_shrink_successor_obj(pred,active["path"],active["blob"],req,request_blob,version)
    else:
        out=build_successor_obj(pred,active["path"],active["blob"],req,request_blob,version)
    validate_bridge_scope(out,req)
    assert exact_current_binding(out,req,request_blob)
    if not shrink_mode:
        assert event_semantic_snapshot(out)==event_semantic_snapshot(pred)
    out_path.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print("ready=true")
    print("created=true")
    print("path="+relpath(out_path))
    print("predecessor_path="+active["path"])
    print("predecessor_blob_sha="+active["blob"])
    print("generated_blob_sha="+blob_sha(out_path))
    print("request_blob_sha="+request_blob)
    print("reason="+("MONOTONIC_WEEKLY_SCOPE_SHRINK_NON_GEOMETRY_ONLY" if shrink_mode else "PROVENANCE_ONLY_EVENT_REBIND_NO_REDISCOVERY"))

if __name__=="__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
