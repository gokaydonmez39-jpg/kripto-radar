#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
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
PRICE_REL = "nasdaq-xray/canonical_current_price_dv30.json"
MASTER_REL = "nasdaq-xray/canonical_current_master_manifest.json"
REQUEST_REL = "nasdaq-xray/canonical_current_resolver_request.json"
PRICE = REPO / PRICE_REL
MASTER = REPO / MASTER_REL
REQUEST = REPO / REQUEST_REL


def blob_sha(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], cwd=REPO, text=True).strip()


def hash_lines(values) -> str:
    return hashlib.sha256("\n".join(values).encode()).hexdigest()


def relpath(path: Path) -> str:
    return str(path.relative_to(REPO)).replace("\\", "/")


def _status_map(mc: dict) -> dict:
    return {s: (r or {}).get("status") for s, r in sorted((mc.get("results") or {}).items())}


def mc_outcome_snapshot(mc: dict) -> dict:
    return {
        "counts": deepcopy(mc.get("counts") or {}),
        "input_pass_symbols": list(mc.get("input_pass_symbols") or []),
        "primary_pass_symbols": list(mc.get("primary_pass_symbols") or []),
        "primary_fail_symbols": list(mc.get("primary_fail_symbols") or []),
        "fallback_watch_symbols": list(mc.get("fallback_watch_symbols") or []),
        "fallback_fail_symbols": list(mc.get("fallback_fail_symbols") or mc.get("fallback_two_source_fail_symbols") or []),
        "fallback_two_source_fail_symbols": list(mc.get("fallback_two_source_fail_symbols") or mc.get("fallback_fail_symbols") or []),
        "unknown_symbols": list(mc.get("unknown_symbols") or []),
        "state_caps": deepcopy(mc.get("state_caps") or {}),
        "r92_ineligible": list(mc.get("r92_ineligible") or []),
        "current_core_symbols": list(mc.get("current_core_symbols") or []),
        "results": deepcopy(mc.get("results") or {}),
        "result_statuses": _status_map(mc),
    }


def validate_price(price: dict, master: dict) -> tuple[list[str], str]:
    assert price.get("schema") == "XRAY_CANONICAL_PRICE_DV30_V1"
    assert price.get("task_id") == TASK
    assert price.get("execution") == "NONE" and price.get("real_money") == "NO-GO"
    assert price.get("unknown_never_pass") is True
    assert master.get("schema") == "XRAY_CANONICAL_CURRENT_MASTER_MANIFEST_V1"
    assert master.get("task_id") == TASK
    assert master.get("execution") == "NONE" and master.get("real_money") == "NO-GO"
    assert price.get("asof_et") == master.get("asof_et")
    assert price.get("source_master_queue_hash") == master.get("queue_hash")
    assert int(price.get("source_master_count", -1)) == int(master.get("queue_total", -2))
    passes = list(price.get("pass_symbols") or [])
    assert passes == sorted(passes)
    assert len(passes) == len(set(passes)) == int(price.get("pass_count", -1))
    ph = hash_lines(passes)
    assert ph == price.get("pass_hash")
    assert int(price.get("unknown_count", len(price.get("unknown_symbols") or []))) == len(price.get("unknown_symbols") or [])
    return passes, ph


def validate_settlement_witness(path: Path, expected_blob: str, master: dict, asof: str) -> dict:
    assert path.exists()
    assert blob_sha(path) == expected_blob
    j = json.loads(path.read_text())
    assert j.get("schema") == "XRAY_RESOLVER_EPOCH_RESULT_V1"
    assert j.get("status") == "COMMITTED"
    assert j.get("task_id") == TASK
    assert j.get("execution") == "NONE" and j.get("real_money") == "NO-GO"
    assert j.get("asof_et") == asof
    assert j.get("queue_hash") == master.get("queue_hash")
    assert j.get("compiled_policy_hash") == POLICY_HASH
    assert j.get("compiled_policy_version") == POLICY_VERSION
    assert j.get("settlement_status") == "PASS"
    return j


def current_settlement_witness(request: dict, master: dict, price: dict,
                               handoff_path: str, handoff_blob: str) -> tuple[str, str]:
    """Resolve the exact settlement witness without making residual cleanup authoritative.

    Preferred path: the current residual request explicitly carries an already-proven
    witness. When the residual request correctly says settlement_required=false, reuse
    only the exact PASS witness embedded in the selected full-scope MC handoff.
    """
    assert request.get("schema") == "XRAY_RESOLVER_EPOCH_REQUEST_V1"
    assert request.get("task_id") == TASK
    assert request.get("execution") == "NONE" and request.get("real_money") == "NO-GO"
    assert request.get("asof_et") == price.get("asof_et") == master.get("asof_et")
    assert request.get("queue_hash") == master.get("queue_hash")
    assert request.get("compiled_policy_hash") == POLICY_HASH
    assert request.get("compiled_policy_version") == POLICY_VERSION
    assert request.get("source_price_path") == PRICE_REL
    assert request.get("source_price_blob_sha") == blob_sha(PRICE)

    if request.get("settlement_already_proven") is True:
        wp = str(request.get("settlement_bridge_path") or "")
        ws = str(request.get("settlement_bridge_blob_sha") or "")
        assert wp and ws
        validate_settlement_witness(REPO / wp, ws, master, price["asof_et"])
        return wp, ws

    assert request.get("settlement_required") is False
    hp = REPO / handoff_path
    assert hp.exists() and blob_sha(hp) == handoff_blob
    h = json.loads(hp.read_text())
    assert h.get("bridge_role") == "FULL_SCOPE_MC_HANDOFF_PROVENANCE"
    assert h.get("settlement_status") == "PASS"
    wp = str(h.get("settlement_witness_path") or "")
    ws = str(h.get("settlement_witness_blob_sha") or "")
    assert wp and ws
    validate_settlement_witness(REPO / wp, ws, master, price["asof_et"])
    return wp, ws



class UpstreamPending(RuntimeError):
    """Expected fail-closed wait state; never evidence for PASS."""


def require_single_handoff(rows: list[dict], exact_rows: list[dict] | None = None) -> dict:
    selected = exact_rows if exact_rows else rows
    if not selected:
        raise UpstreamPending("FULL_SCOPE_RESOLVER_HANDOFF_PENDING")
    if len(selected) != 1:
        raise AssertionError((
            "AMBIGUOUS_FULL_SCOPE_RESOLVER_HANDOFF",
            [r.get("path") for r in selected],
            [r.get("path") for r in rows],
        ))
    return selected[0]


def full_scope_price_pending_reason(price: dict) -> str | None:
    """Return a fail-closed pending reason while current PRICE/DV30 is unresolved."""
    unknown = int(price.get("unknown_count", len(price.get("unknown_symbols") or [])))
    if unknown != len(price.get("unknown_symbols") or []):
        raise AssertionError("PRICE_UNKNOWN_COUNT_MISMATCH")
    if unknown:
        return "PRICE_DV30_UNKNOWN"
    return None


def selftest() -> None:
    assert full_scope_price_pending_reason({"unknown_count": 0, "unknown_symbols": []}) is None
    assert full_scope_price_pending_reason({"unknown_count": 1, "unknown_symbols": ["GRAL"]}) == "PRICE_DV30_UNKNOWN"
    try:
        full_scope_price_pending_reason({"unknown_count": 2, "unknown_symbols": ["GRAL"]})
    except AssertionError as e:
        assert str(e) == "PRICE_UNKNOWN_COUNT_MISMATCH"
    else:
        raise AssertionError("MISMATCH_MUST_FAIL_CLOSED")
    try:
        require_single_handoff([])
    except UpstreamPending as e:
        assert str(e) == "FULL_SCOPE_RESOLVER_HANDOFF_PENDING"
    else:
        raise AssertionError("EMPTY_HANDOFF_MUST_WAIT_FAIL_CLOSED")
    one = {"path": "one"}
    assert require_single_handoff([one]) is one
    try:
        require_single_handoff([{"path": "a"}, {"path": "b"}])
    except AssertionError as e:
        assert e.args and e.args[0][0] == "AMBIGUOUS_FULL_SCOPE_RESOLVER_HANDOFF"
    else:
        raise AssertionError("AMBIGUOUS_HANDOFF_MUST_FAIL")
    print("MC_PROVENANCE_REBIND_PENDING_SELFTEST=PASS")


def current_full_scope_resolver_handoff(master: dict, price: dict, request: dict) -> tuple[str, str]:
    """Select one immutable full-scope MC handoff authority.

    Exact current handoff blobs are preferred. A stale handoff metadata blob may be
    accepted only when the decision-bearing full-scope partition is identical to
    CURRENT PRICE: exact PASS set/hash/count, current BLOCK subset, zero current
    UNKNOWN, exact queue/policy, complete disjoint full partition, and a valid
    settlement witness. Supersession is resolved within this role only.
    """
    stamp = price["asof_et"].replace("-", "")
    current_price_blob = blob_sha(PRICE)
    current_request_blob = blob_sha(REQUEST)
    assert request.get("source_price_path") == PRICE_REL
    assert request.get("source_price_blob_sha") == current_price_blob
    if full_scope_price_pending_reason(price) is not None:
        raise RuntimeError("PRICE_DV30_UNKNOWN_PENDING")

    current_pass = set(price.get("pass_symbols") or [])
    current_blocked = set(price.get("blocked_symbols") or [])
    rows = []

    for p in sorted(ROOT.glob(f"canonical_resolver_bridge_{stamp}_c417_dv30_v*.json")):
        try:
            j = json.loads(p.read_text())
            h = j.get("current_handoff") or {}
            assert j.get("schema") == "XRAY_RESOLVER_EPOCH_RESULT_V1"
            assert j.get("status") == "COMMITTED"
            assert j.get("task_id") == TASK
            assert j.get("execution") == "NONE" and j.get("real_money") == "NO-GO"
            assert j.get("unknown_never_pass") is True
            assert j.get("asof_et") == price.get("asof_et") == master.get("asof_et")
            assert j.get("bridge_role") == "FULL_SCOPE_MC_HANDOFF_PROVENANCE"
            assert j.get("queue_hash") == master.get("queue_hash")
            assert int(j.get("queue_total", -1)) == int(master.get("queue_total", -2))
            assert j.get("compiled_policy_hash") == POLICY_HASH
            assert j.get("compiled_policy_version") == POLICY_VERSION
            assert j.get("coverage_complete") is True
            assert j.get("classification_coverage_complete") is True
            assert j.get("partial_data") is False
            assert j.get("settlement_status") == "PASS"

            compact = j.get("price_resolution_compact") or {}
            groups = [
                set((compact.get("fail_price") or {}).keys()),
                set((compact.get("fail_dv30") or {}).keys()),
                set((compact.get("pass_price_dv30") or {}).keys()),
                set((compact.get("block_current_run") or {}).keys()),
                set(compact.get("unresolved_symbols") or []),
            ]
            flat = set().union(*groups)
            assert sum(len(x) for x in groups) == len(flat)
            assert len(flat) == int(master.get("queue_total", -1))
            full_pass = groups[2]
            full_block = groups[3]
            assert full_pass == current_pass
            assert current_blocked <= full_block

            assert h.get("price_path") == PRICE_REL
            assert int(h.get("pass_count", -1)) == int(price.get("pass_count", -2))
            assert h.get("pass_hash") == price.get("pass_hash")
            assert int(h.get("blocked_count", -1)) == int(price.get("blocked_count", -2))
            assert h.get("no_new_pass_beyond_resolver") is True
            assert h.get("residual_request_path") == REQUEST_REL

            wp = str(j.get("settlement_witness_path") or "")
            ws = str(j.get("settlement_witness_blob_sha") or "")
            assert wp and ws
            validate_settlement_witness(REPO / wp, ws, master, price["asof_et"])

            exact = (
                h.get("price_blob_sha") == current_price_blob
                and h.get("residual_request_blob_sha") == current_request_blob
            )
            semantic = bool(
                current_pass == full_pass
                and current_blocked <= full_block
                and int(price.get("unknown_count", -1)) == 0
            )
            assert exact or semantic
            rows.append({
                "path": relpath(p),
                "blob": blob_sha(p),
                "obj": j,
                "exact": exact,
            })
        except Exception:
            continue

    if not rows:
        raise UpstreamPending("FULL_SCOPE_RESOLVER_HANDOFF_PENDING")

    by_path = {r["path"]: r for r in rows}
    valid = []
    superseded = set()
    for r in rows:
        j = r["obj"]
        sp = j.get("supersedes_resolver_bridge_path")
        ss = j.get("supersedes_resolver_bridge_blob_sha")
        if bool(sp) != bool(ss):
            continue
        if sp:
            pred = by_path.get(sp)
            if pred is None:
                pred_path = REPO / sp
                if not pred_path.exists() or blob_sha(pred_path) != ss:
                    continue
            elif pred["blob"] != ss:
                continue
            superseded.add(sp)
        valid.append(r)

    active = [r for r in valid if r["path"] not in superseded]
    exact_active = [r for r in active if r["exact"]]
    chosen = require_single_handoff(active, exact_active)
    return chosen["path"], chosen["blob"]


def mc_provenance_exact(mc: dict, current_price_blob: str,
                        settlement_path: str, settlement_blob: str,
                        handoff_path: str, handoff_blob: str) -> bool:
    return bool(
        mc.get("input_blob_sha") == current_price_blob
        and mc.get("settlement_witness_status") == "PASS"
        and mc.get("settlement_witness_path") == settlement_path
        and mc.get("settlement_witness_blob_sha") == settlement_blob
        and mc.get("resolver_handoff_provenance_path") == handoff_path
        and mc.get("resolver_handoff_provenance_blob_sha") == handoff_blob
    )


def validate_mc_semantics(mc: dict, price: dict, pass_symbols: list[str], pass_hash: str) -> None:
    assert mc.get("schema") == "XRAY_MC_EPOCH_RESULT_V1"
    assert mc.get("status") == "COMMITTED"
    assert mc.get("task_id") == TASK
    assert mc.get("execution") == "NONE" and mc.get("real_money") == "NO-GO"
    assert mc.get("unknown_never_pass") is True
    assert mc.get("asof_et") == price.get("asof_et")
    assert mc.get("input_path") == PRICE_REL
    assert mc.get("input_pass_hash") == pass_hash
    assert int(mc.get("input_count", -1)) == len(pass_symbols)
    assert list(mc.get("input_pass_symbols") or []) == pass_symbols
    assert mc.get("policy_hash") == POLICY_HASH
    assert mc.get("policy_version") == POLICY_VERSION

    primary = set(mc.get("primary_pass_symbols") or [])
    primary_fail = set(mc.get("primary_fail_symbols") or [])
    watch = set(mc.get("fallback_watch_symbols") or [])
    fallback_fail = set(mc.get("fallback_fail_symbols") or mc.get("fallback_two_source_fail_symbols") or [])
    unknown = set(mc.get("unknown_symbols") or [])
    groups = [primary, primary_fail, watch, fallback_fail, unknown]
    for i in range(len(groups)):
        for k in range(i + 1, len(groups)):
            assert not (groups[i] & groups[k])
    expected = set(pass_symbols)
    assert set().union(*groups) == expected

    results = mc.get("results") or {}
    assert set(results) == expected
    assert all((results.get(s) or {}).get("status") == "MC_PASS_PRIMARY" for s in primary)
    assert all((results.get(s) or {}).get("status") == "MC_FAIL_PRIMARY" for s in primary_fail)
    assert all((results.get(s) or {}).get("status") == "MC_PASS_FALLBACK_WATCH" for s in watch)
    assert all((results.get(s) or {}).get("status") == "MC_FAIL_FALLBACK_TWO_SOURCE" for s in fallback_fail)
    assert all((results.get(s) or {}).get("status") == "MC_UNKNOWN" for s in unknown)

    counts = mc.get("counts") or {}
    assert int(counts.get("MC_PASS_PRIMARY", -1)) == len(primary)
    assert int(counts.get("MC_FAIL_PRIMARY", -1)) == len(primary_fail)
    assert int(counts.get("MC_PASS_FALLBACK_WATCH", -1)) == len(watch)
    assert int(counts.get("MC_FAIL_FALLBACK_TWO_SOURCE", counts.get("MC_FAIL_FALLBACK", -1))) == len(fallback_fail)
    assert int(counts.get("MC_UNKNOWN", -1)) == len(unknown)
    assert int(counts.get("TOTAL", -1)) == len(expected)

    assert set(mc.get("current_core_symbols") or []) == (primary | watch)
    caps = mc.get("state_caps") or {}
    assert set(caps) == watch
    assert all(caps.get(s) == "WATCH" for s in watch)
    assert set(mc.get("r92_ineligible") or []) == watch


def load_valid_mc_rows(price: dict, pass_symbols: list[str], pass_hash: str, master: dict):
    stamp = price["asof_et"].replace("-", "")
    rows = []
    for p in sorted(ROOT.glob(f"canonical_mc_bridge_{stamp}_c417_dv30_v*.json")):
        try:
            j = json.loads(p.read_text())
            validate_mc_semantics(j, price, pass_symbols, pass_hash)
            wp = str(j.get("settlement_witness_path") or "")
            ws = str(j.get("settlement_witness_blob_sha") or "")
            assert j.get("settlement_witness_status") == "PASS"
            assert wp and ws
            validate_settlement_witness(REPO / wp, ws, master, price["asof_et"])
            rows.append({"path": relpath(p), "file": p, "blob": blob_sha(p), "obj": j})
        except Exception:
            continue
    assert rows, "NO_VALID_MC_AUTHORITY_FOR_PROVENANCE_REBIND"
    return rows


def select_active_mc(rows):
    """Mirror Post-MC authority selection.

    A successor is eligible when its direct predecessor exists in the same
    structurally/current-semantics row set with the exact recorded blob. An
    older intermediate row whose own predecessor is no longer current-valid is
    not itself active; it must not invalidate a newer exact successor that
    names that intermediate row directly.
    """
    by_path = {r["path"]: r for r in rows}
    valid = []
    for r in rows:
        j = r["obj"]
        sp = j.get("supersedes_mc_bridge_path")
        ss = j.get("supersedes_mc_bridge_blob_sha")
        if not sp and not ss:
            valid.append(r)
            continue
        if not sp or not ss:
            continue
        pred = by_path.get(sp)
        if pred is None:
            continue
        if pred["blob"] != ss:
            continue
        valid.append(r)

    superseded = {
        r["obj"].get("supersedes_mc_bridge_path")
        for r in valid
        if r["obj"].get("supersedes_mc_bridge_path")
        and r["obj"].get("supersedes_mc_bridge_blob_sha")
    }
    active = [r for r in valid if r["path"] not in superseded]
    assert len(active) == 1, (
        "AMBIGUOUS_ACTIVE_MC_AUTHORITY",
        [r["path"] for r in active],
        [r["path"] for r in valid],
    )
    return active[0]


def next_successor_path(price: dict, rows) -> tuple[Path, int]:
    stamp = price["asof_et"].replace("-", "")
    versions = []
    rx = re.compile(rf"^canonical_mc_bridge_{stamp}_c417_dv30_v(\d+)\.json$")
    for r in rows:
        m = rx.match(r["file"].name)
        if m:
            versions.append(int(m.group(1)))
    assert versions
    version = max(versions) + 1
    return ROOT / f"canonical_mc_bridge_{stamp}_c417_dv30_v{version}.json", version


def build_successor_obj(predecessor: dict, predecessor_path: str, predecessor_blob: str,
                        current_price_blob: str, settlement_path: str, settlement_blob: str,
                        version: int, resolver_handoff_path: str | None = None,
                        resolver_handoff_blob: str | None = None) -> dict:
    out = deepcopy(predecessor)
    before = mc_outcome_snapshot(predecessor)

    out["authority"] = "POST_MC_C417_DV30_PROVENANCE_REBIND_NO_REMEASUREMENT"
    out["input_blob_sha"] = current_price_blob
    out["settlement_witness_status"] = "PASS"
    out["settlement_witness_path"] = settlement_path
    out["settlement_witness_blob_sha"] = settlement_blob
    if resolver_handoff_path and resolver_handoff_blob:
        out["resolver_handoff_provenance_path"] = resolver_handoff_path
        out["resolver_handoff_provenance_blob_sha"] = resolver_handoff_blob
    out["committed_by"] = "XRAY_POST_MC_PROVENANCE_REBIND_FACTORY"
    out["bridge_revision"] = version
    out["supersedes_mc_bridge_path"] = predecessor_path
    out["supersedes_mc_bridge_blob_sha"] = predecessor_blob
    out["semantic_repair"] = {
        "type": "PROVENANCE_ONLY_CURRENT_PRICE_BLOB_REBIND_NO_MC_REMEASUREMENT",
        "predecessor_path": predecessor_path,
        "predecessor_blob_sha": predecessor_blob,
        "predecessor_input_blob_sha": predecessor.get("input_blob_sha"),
        "current_input_blob_sha": current_price_blob,
        "input_pass_hash": predecessor.get("input_pass_hash"),
        "input_count": predecessor.get("input_count"),
        "added_to_mc": [],
        "removed_from_mc": [],
        "overlap": predecessor.get("input_count"),
        "settlement_witness_rebound_to_current_resolver_request": True,
        "resolver_full_scope_handoff_rebound": bool(resolver_handoff_path and resolver_handoff_blob),
        "no_mc_classification_change": True,
        "no_threshold_change": True,
        "no_market_cap_remeasurement": True,
        "fallback_watch_preserved": True,
        "r92_ineligible_preserved": True,
        "unknown_never_pass": True,
        "rationale": f"CURRENT_PROVENANCE_REBIND_WITH_IDENTICAL_{predecessor.get('input_count')}_PASS_SET;IMMUTABLE_SUCCESSOR_ONLY",
    }
    audit = deepcopy(predecessor.get("audit") or {})
    audit.update({
        "input_exact_current_dv30_pass_set": True,
        "exact_current_price_blob_rebind": True,
        "mc_results_unchanged": True,
        "pass_manufactured": False,
        "no_threshold_weakening": True,
        "provenance_only_rebind_no_remeasurement": True,
        "fallback_watch_preserved": True,
        "r92_ineligible_preserved": True,
        "resolver_full_scope_handoff_exact": bool(resolver_handoff_path and resolver_handoff_blob),
    })
    out["audit"] = audit

    assert mc_outcome_snapshot(out) == before, "MC_OUTCOME_MUTATION_FORBIDDEN"
    return out


def main() -> None:
    price = json.loads(PRICE.read_text())
    master = json.loads(MASTER.read_text())
    request = json.loads(REQUEST.read_text())
    pass_symbols, pass_hash = validate_price(price, master)
    current_price_blob = blob_sha(PRICE)
    pending_reason = full_scope_price_pending_reason(price)
    if pending_reason is not None:
        print("ready=false")
        print("created=false")
        print("pending_reason=" + pending_reason)
        print("unknown_count=" + str(int(price.get("unknown_count", 0))))
        print("unknown_symbols=" + ",".join(sorted(price.get("unknown_symbols") or [])))
        print("reason=UPSTREAM_PRICE_DV30_UNKNOWN_FAIL_CLOSED")
        return
    try:
        handoff_path, handoff_blob = current_full_scope_resolver_handoff(master, price, request)
    except UpstreamPending as e:
        print("ready=false")
        print("created=false")
        print("pending_reason=" + str(e))
        print("reason=UPSTREAM_RESOLVER_HANDOFF_PENDING_FAIL_CLOSED")
        return
    settlement_path, settlement_blob = current_settlement_witness(
        request, master, price, handoff_path, handoff_blob
    )

    rows = load_valid_mc_rows(price, pass_symbols, pass_hash, master)
    active = select_active_mc(rows)
    predecessor = active["obj"]

    if mc_provenance_exact(
        predecessor, current_price_blob,
        settlement_path, settlement_blob,
        handoff_path, handoff_blob,
    ):
        print("ready=true")
        print("created=false")
        print("path=" + active["path"])
        print("predecessor_path=" + active["path"])
        print("price_blob_sha=" + current_price_blob)
        print("pass_count=" + str(len(pass_symbols)))
        print("reason=EXACT_CURRENT_MC_ALREADY_EXISTS")
        return

    out_path, version = next_successor_path(price, rows)
    assert not out_path.exists(), ("SUCCESSOR_PATH_ALREADY_EXISTS", relpath(out_path))
    successor = build_successor_obj(
        predecessor,
        active["path"],
        active["blob"],
        current_price_blob,
        settlement_path,
        settlement_blob,
        version,
        handoff_path,
        handoff_blob,
    )
    validate_mc_semantics(successor, price, pass_symbols, pass_hash)
    assert successor["input_blob_sha"] == current_price_blob
    assert successor["supersedes_mc_bridge_blob_sha"] == active["blob"]
    assert successor["resolver_handoff_provenance_path"] == handoff_path
    assert successor["resolver_handoff_provenance_blob_sha"] == handoff_blob
    assert mc_outcome_snapshot(successor) == mc_outcome_snapshot(predecessor)

    out_path.write_text(json.dumps(successor, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    generated_blob = blob_sha(out_path)

    print("ready=true")
    print("created=true")
    print("path=" + relpath(out_path))
    print("predecessor_path=" + active["path"])
    print("predecessor_blob_sha=" + active["blob"])
    print("generated_blob_sha=" + generated_blob)
    print("price_blob_sha=" + current_price_blob)
    print("pass_count=" + str(len(pass_symbols)))
    print("reason=PROVENANCE_ONLY_REBIND_NO_MC_REMEASUREMENT")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
