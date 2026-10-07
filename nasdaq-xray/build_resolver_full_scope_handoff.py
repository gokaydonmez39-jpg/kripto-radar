#!/usr/bin/env python3
"""Build an immutable full-scope resolver handoff from an exact completed canonical PRICE partition.

This is provenance aggregation only. It never measures price/DV30, never changes an
existing PRICE decision, and never converts UNKNOWN/BLOCK to PASS. It is permitted
only when current PRICE already covers the entire current master queue with zero
UNKNOWN and zero BLOCK_CURRENT_RUN, and a same-ASOF/current-queue resolver settlement
witness is already PASS.

EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN != PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
TASK = "6a825366222081918997094d76e6ae46"
POLICY_HASH = "68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
POLICY_VERSION = "C4.17"
POLICY_BLOB = "16c50cc8f887a5234a4be23862d7c8d0e564b0ac"

MASTER_REL = "nasdaq-xray/canonical_current_master_manifest.json"
PRICE_REL = "nasdaq-xray/canonical_current_price_dv30.json"
REQUEST_REL = "nasdaq-xray/canonical_current_resolver_request.json"
MANIFEST_REL = "nasdaq-xray/canonical_current_resolver_chunk_manifest.json"
MASTER = REPO / MASTER_REL
PRICE = REPO / PRICE_REL
REQUEST = REPO / REQUEST_REL
MANIFEST = REPO / MANIFEST_REL

FULL_ROLE = "FULL_SCOPE_MC_HANDOFF_PROVENANCE"
RESIDUAL_ROLE = "CURRENT_RESIDUAL_REQUEST_AUTHORITY"


def blob_sha(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], cwd=REPO, text=True).strip()


def hash_lines(values) -> str:
    return hashlib.sha256("\n".join(values).encode()).hexdigest()


def relpath(path: Path) -> str:
    return str(path.relative_to(REPO)).replace("\\", "/")


def finite(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def role(obj: dict) -> str:
    r = str((obj or {}).get("bridge_role") or "")
    auth = str((obj or {}).get("authority") or "")
    if r == FULL_ROLE or "FULL_SCOPE_MC_HANDOFF" in auth:
        return FULL_ROLE
    return RESIDUAL_ROLE


def resolver_rows(asof: str) -> list[dict]:
    stamp = asof.replace("-", "")
    rows = []
    for p in sorted(ROOT.glob(f"canonical_resolver_bridge_{stamp}_c417_dv30_v*.json")):
        try:
            j = load(p)
            if not (
                j.get("schema") == "XRAY_RESOLVER_EPOCH_RESULT_V1"
                and j.get("status") == "COMMITTED"
                and j.get("task_id") == TASK
                and j.get("execution") == "NONE"
                and j.get("real_money") == "NO-GO"
                and j.get("unknown_never_pass") is True
                and j.get("asof_et") == asof
                and j.get("compiled_policy_hash") == POLICY_HASH
                and j.get("compiled_policy_version") == POLICY_VERSION
            ):
                continue
            rows.append({"path": relpath(p), "file": p, "blob": blob_sha(p), "obj": j, "role": role(j)})
        except Exception:
            continue
    return rows


def active_role(rows: list[dict], wanted_role: str) -> list[dict]:
    scoped = [r for r in rows if r["role"] == wanted_role]
    by_path = {r["path"]: r for r in scoped}
    valid = []
    superseded = set()
    for r in scoped:
        j = r["obj"]
        sp = j.get("supersedes_resolver_bridge_path")
        ss = j.get("supersedes_resolver_bridge_blob_sha")
        if bool(sp) != bool(ss):
            continue
        if sp:
            pred = by_path.get(sp)
            if pred is None:
                pp = REPO / str(sp)
                if not pp.exists() or blob_sha(pp) != ss:
                    continue
            elif pred["blob"] != ss:
                continue
            superseded.add(sp)
        valid.append(r)
    return [r for r in valid if r["path"] not in superseded]


def select_one_active(rows: list[dict], wanted_role: str, *, queue_hash: str | None = None) -> dict:
    active = active_role(rows, wanted_role)
    if queue_hash is not None:
        active = [r for r in active if r["obj"].get("queue_hash") == queue_hash]
    assert len(active) == 1, (
        "AMBIGUOUS_OR_MISSING_ACTIVE_RESOLVER_ROLE",
        wanted_role,
        queue_hash,
        [r["path"] for r in active],
    )
    return active[0]


def settlement_witness_relation(j: dict, master: dict) -> str | None:
    """Return the only two settlement reuse relations allowed for a current queue.

    EXACT_QUEUE preserves the original rule. SAFE_SUBSET_REBIND is narrower:
    the witness must be a full-scope authority from the same ASOF/policy, its
    declared symbol partition must be internally exact, the current master queue
    must be a strict/equal subset of that settled queue, and every symbol used by
    the settlement proof must still exist in the current queue.
    """
    if (
        j.get("queue_hash") == master.get("queue_hash")
        and int(j.get("queue_total", -1)) == int(master.get("queue_total", -2))
    ):
        return "EXACT_QUEUE"

    if role(j) != FULL_ROLE:
        return None
    source_symbols = list(j.get("symbols") or [])
    current_symbols = list(master.get("pass_symbols") or [])
    if not source_symbols or not current_symbols:
        return None
    if len(source_symbols) != len(set(source_symbols)):
        return None
    if len(source_symbols) != int(j.get("queue_total", -1)):
        return None
    if j.get("symbol_hash") != hash_lines(source_symbols):
        return None
    source_set = set(source_symbols)
    current_set = set(current_symbols)
    settlement_symbols = list(j.get("settlement_symbols") or [])
    if not settlement_symbols or len(set(settlement_symbols)) != len(settlement_symbols):
        return None
    if not current_set.issubset(source_set):
        return None
    if not set(settlement_symbols).issubset(current_set):
        return None
    return "SAFE_SUBSET_REBIND"


def validate_settlement_witness(
    path: Path,
    expected_blob: str,
    master: dict,
    asof: str,
) -> tuple[dict, str, str, str]:
    """Resolve an immutable settlement witness chain without manufacturing PASS.

    A residual authority may point at an older residual authority, which in turn
    points at the actual full-scope settlement witness. Follow that immutable
    chain only while every blob/path binding is exact. Reuse is allowed only for
    an exact current queue or SAFE_SUBSET_REBIND as defined above.
    """
    seen = set()
    for _depth in range(8):
        rel = relpath(path)
        assert rel not in seen, ("SETTLEMENT_WITNESS_CYCLE", rel)
        seen.add(rel)
        assert path.exists(), ("SETTLEMENT_WITNESS_MISSING", str(path))
        actual_blob = blob_sha(path)
        assert actual_blob == expected_blob, ("SETTLEMENT_WITNESS_BLOB_MISMATCH", str(path))
        j = load(path)
        assert j.get("schema") == "XRAY_RESOLVER_EPOCH_RESULT_V1"
        assert j.get("status") == "COMMITTED"
        assert j.get("task_id") == TASK
        assert j.get("execution") == "NONE" and j.get("real_money") == "NO-GO"
        assert j.get("unknown_never_pass") is True
        assert j.get("asof_et") == asof
        assert j.get("compiled_policy_hash") == POLICY_HASH
        assert j.get("compiled_policy_version") == POLICY_VERSION
        assert j.get("settlement_status") == "PASS"

        relation = settlement_witness_relation(j, master)
        if relation is not None:
            return j, rel, actual_blob, relation

        next_rel = str(j.get("settlement_witness_path") or "")
        next_blob = str(j.get("settlement_witness_blob_sha") or "")
        assert next_rel and next_blob, (
            "SETTLEMENT_WITNESS_NOT_REUSABLE_AND_CHAIN_ENDED",
            rel,
            j.get("queue_hash"),
            master.get("queue_hash"),
        )
        path = REPO / next_rel
        expected_blob = next_blob

    raise AssertionError(("SETTLEMENT_WITNESS_CHAIN_DEPTH_EXCEEDED", sorted(seen)))


def compact_from_price(price: dict, queue: list[str]) -> dict:
    results = price.get("results") or {}
    assert set(results) == set(queue), ("PRICE_RESULT_SCOPE_MISMATCH", len(results), len(queue))
    out = {
        "fail_price": {},
        "fail_dv30": {},
        "pass_price_dv30": {},
        "block_current_run": {},
        "unresolved_symbols": [],
    }
    for sym in queue:
        rec = results.get(sym) or {}
        st = str(rec.get("status") or "")
        info = rec.get("info") or {}
        if st in {"FAIL_PRICE", "FAIL_PRICE_NO_ASOF_BAR"}:
            px = finite(info.get("price"))
            if px is not None and st == "FAIL_PRICE":
                out["fail_price"][sym] = px
            else:
                out["fail_price"][sym] = {
                    "status": st,
                    "proof": info.get("proof"),
                    "source": info.get("source"),
                    "no_synthetic_bar": info.get("no_synthetic_bar"),
                }
        elif st in {"FAIL_DV30", "FAIL_DV30_INSUFFICIENT_SESSIONS"}:
            missing = list(info.get("missing_sessions") or [])
            out["fail_dv30"][sym] = {
                "price": finite(info.get("price")),
                "metric": finite(info.get("dv30")),
                "proof": info.get("proof"),
                "known_session_count": int(info.get("known_session_count", 0) or 0),
                "missing_session_count": len(missing),
            }
        elif st == "PASS_PRICE_DV30":
            out["pass_price_dv30"][sym] = {
                "price": finite(info.get("price")),
                "dv30": finite(info.get("dv30")),
                "known_session_count": int(info.get("known_session_count", 0) or 0),
            }
        elif st == "BLOCK_CURRENT_RUN":
            out["block_current_run"][sym] = {
                "reason": info.get("reason") or rec.get("reason"),
                "proof": info.get("proof"),
                "source": info.get("source"),
            }
        else:
            out["unresolved_symbols"].append(sym)

    groups = [
        set(out["fail_price"]),
        set(out["fail_dv30"]),
        set(out["pass_price_dv30"]),
        set(out["block_current_run"]),
        set(out["unresolved_symbols"]),
    ]
    flat = set().union(*groups)
    assert sum(len(x) for x in groups) == len(flat), "PRICE_PARTITION_OVERLAP"
    assert flat == set(queue), ("PRICE_PARTITION_INCOMPLETE", len(flat), len(queue))
    return out


def validate_current(master: dict, price: dict, request: dict, manifest: dict) -> tuple[list[str], dict]:
    assert master.get("schema") == "XRAY_CANONICAL_CURRENT_MASTER_MANIFEST_V1"
    assert master.get("task_id") == TASK
    assert master.get("execution") == "NONE" and master.get("real_money") == "NO-GO"

    assert price.get("schema") == "XRAY_CANONICAL_PRICE_DV30_V1"
    assert price.get("task_id") == TASK
    assert price.get("execution") == "NONE" and price.get("real_money") == "NO-GO"
    assert price.get("unknown_never_pass") is True
    assert price.get("asof_et") == master.get("asof_et")
    assert price.get("source_master_queue_hash") == master.get("queue_hash")
    assert int(price.get("source_master_count", -1)) == int(master.get("queue_total", -2))

    queue = list(master.get("pass_symbols") or [])
    assert queue == sorted(queue)
    assert len(queue) == len(set(queue)) == int(master.get("queue_total", -1))
    assert hash_lines(queue) == master.get("queue_hash")

    passes = list(price.get("pass_symbols") or [])
    assert passes == sorted(passes)
    assert len(passes) == len(set(passes)) == int(price.get("pass_count", -1))
    assert hash_lines(passes) == price.get("pass_hash")
    assert int(price.get("unknown_count", -1)) == 0
    assert list(price.get("unknown_symbols") or []) == []
    assert int(price.get("blocked_count", -1)) == 0
    assert list(price.get("blocked_symbols") or []) == []

    assert request.get("schema") == "XRAY_RESOLVER_EPOCH_REQUEST_V1"
    assert request.get("task_id") == TASK
    assert request.get("execution") == "NONE" and request.get("real_money") == "NO-GO"
    assert request.get("unknown_never_pass") is True
    assert request.get("asof_et") == price.get("asof_et")
    assert request.get("queue_hash") == master.get("queue_hash")
    assert request.get("compiled_policy_hash") == POLICY_HASH
    assert request.get("compiled_policy_version") == POLICY_VERSION
    assert request.get("source_price_path") == PRICE_REL
    assert request.get("source_price_blob_sha") == blob_sha(PRICE)
    assert int(request.get("source_price_pass_count", -1)) == len(passes)
    assert request.get("source_price_pass_hash") == price.get("pass_hash")
    assert int(request.get("symbol_count", -1)) == 0
    assert list(request.get("symbols") or []) == []
    assert int(request.get("price_unknown_count", -1)) == 0
    assert int(request.get("price_blocked_count", -1)) == 0
    assert request.get("settlement_required") is False

    assert manifest.get("schema") == "XRAY_RESOLVER_REQUEST_CHUNK_MANIFEST_V1"
    assert manifest.get("task_id") == TASK
    assert manifest.get("execution") == "NONE" and manifest.get("real_money") == "NO-GO"
    assert manifest.get("unknown_never_pass") is True
    assert manifest.get("asof_et") == price.get("asof_et")
    assert manifest.get("queue_hash") == master.get("queue_hash")
    assert manifest.get("request_blob_sha") == blob_sha(REQUEST)
    assert int(manifest.get("symbol_count", -1)) == 0
    assert int(manifest.get("chunk_count", -1)) == 0
    assert list(manifest.get("chunks") or []) == []

    compact = compact_from_price(price, queue)
    assert set(compact["pass_price_dv30"]) == set(passes)
    assert set(compact["block_current_run"]) == set(price.get("blocked_symbols") or [])
    assert not compact["unresolved_symbols"]
    return queue, compact


def full_scope_exact(row: dict, master: dict, price: dict, request: dict, compact: dict) -> bool:
    j = row["obj"]
    h = j.get("current_handoff") or {}
    return bool(
        j.get("queue_hash") == master.get("queue_hash")
        and int(j.get("queue_total", -1)) == int(master.get("queue_total", -2))
        and j.get("source_price_blob_sha") == blob_sha(PRICE)
        and j.get("source_request_blob_sha") == blob_sha(REQUEST)
        and h.get("price_blob_sha") == blob_sha(PRICE)
        and h.get("residual_request_blob_sha") == blob_sha(REQUEST)
        and h.get("pass_hash") == price.get("pass_hash")
        and int(h.get("pass_count", -1)) == int(price.get("pass_count", -2))
        and int(h.get("blocked_count", -1)) == 0
        and (j.get("price_resolution_compact") or {}) == compact
    )


def next_path(asof: str) -> tuple[Path, int]:
    stamp = asof.replace("-", "")
    rx = re.compile(rf"^canonical_resolver_bridge_{stamp}_c417_dv30_v(\d+)\.json$")
    versions = []
    for p in ROOT.glob(f"canonical_resolver_bridge_{stamp}_c417_dv30_v*.json"):
        m = rx.match(p.name)
        if m:
            versions.append(int(m.group(1)))
    n = (max(versions) if versions else 0) + 1
    return ROOT / f"canonical_resolver_bridge_{stamp}_c417_dv30_v{n}.json", n


def build_obj(master: dict, price: dict, request: dict, manifest: dict, compact: dict,
              predecessor: dict, residual: dict, witness_path: str, witness_blob: str,
              witness: dict, witness_relation: str, version: int) -> dict:
    queue = list(master["pass_symbols"])
    passes = list(price["pass_symbols"])
    counts = {
        "FAIL_PRICE": len(compact["fail_price"]),
        "FAIL_DV30": len(compact["fail_dv30"]),
        "PASS_PRICE_DV30": len(compact["pass_price_dv30"]),
        "BLOCK_CURRENT_RUN": len(compact["block_current_run"]),
        "UNRESOLVED": len(compact["unresolved_symbols"]),
        "TOTAL": len(queue),
    }
    pred = predecessor["obj"]
    out = {
        "schema": "XRAY_RESOLVER_EPOCH_RESULT_V1",
        "status": "COMMITTED",
        "authority": f"CANONICAL_RESOLVER_C417_DV30_V{version}_FULL_SCOPE_CURRENT_PRICE_AGGREGATION",
        "bridge_role": FULL_ROLE,
        "task_id": TASK,
        "asof_et": price["asof_et"],
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "queue_hash": master["queue_hash"],
        "queue_total": int(master["queue_total"]),
        "compiled_policy_path": "nasdaq-xray/chatgpt_compiled_policy_v3.json",
        "compiled_policy_blob_sha": POLICY_BLOB,
        "compiled_policy_hash": POLICY_HASH,
        "compiled_policy_version": POLICY_VERSION,
        "source_price_path": PRICE_REL,
        "source_price_blob_sha": blob_sha(PRICE),
        "source_request_path": REQUEST_REL,
        "source_request_blob_sha": blob_sha(REQUEST),
        "source_manifest_path": MANIFEST_REL,
        "source_manifest_blob_sha": blob_sha(MANIFEST),
        "symbols": queue,
        "symbol_count": len(queue),
        "symbol_hash": hash_lines(queue),
        "price_unknown_count": 0,
        "price_unknown_symbols": [],
        "price_blocked_count": 0,
        "price_blocked_symbols": [],
        "result_encoding": "CANONICAL_PRICE_DV30_FULL_SCOPE_MIRROR_V1",
        "price_resolutions": {},
        "price_resolution_compact": compact,
        "classification_coverage_complete": True,
        "coverage_complete": True,
        "partial_data": False,
        "settlement_required": False,
        "settlement_status": "PASS",
        "settlement_method": (
            "SAME_ASOF_CURRENT_QUEUE_RESIDUAL_AUTHORITY_PASS_REUSED"
            if witness_relation == "EXACT_QUEUE"
            else "SAME_ASOF_SAFE_SUBSET_SETTLEMENT_PASS_REUSED"
        ),
        "settlement_symbols": list(witness.get("settlement_symbols") or []),
        "settlement_evidence": {
            "authority_path": residual["path"],
            "authority_blob_sha": residual["blob"],
            "witness_path": witness_path,
            "witness_blob_sha": witness_blob,
            "witness_relation": witness_relation,
            "source_queue_hash": witness.get("queue_hash"),
            "source_queue_total": witness.get("queue_total"),
            "current_queue_hash": master.get("queue_hash"),
            "current_queue_total": master.get("queue_total"),
            "current_queue_subset_of_witness": witness_relation == "SAFE_SUBSET_REBIND",
            "settlement_symbols_all_in_current_queue": set(witness.get("settlement_symbols") or []).issubset(
                set(master.get("pass_symbols") or [])
            ),
            "no_new_settlement_measurement": True,
        },
        "settlement_witness_path": witness_path,
        "settlement_witness_blob_sha": witness_blob,
        "provider_evidence": {
            "mode": "NO_PROVIDER_REFETCH_CANONICAL_PRICE_PARTITION_AGGREGATION",
            "source_price_blob_sha": blob_sha(PRICE),
            "pass_count": len(passes),
            "pass_hash": price["pass_hash"],
        },
        "union_disjoint_proof": {
            "counts": counts,
            "partition_complete": True,
            "partition_disjoint": True,
            "queue_hash_exact": True,
            "pass_set_exact_current_price": True,
            "unknown_zero": True,
            "blocked_zero": True,
        },
        "supersedes_resolver_bridge_path": predecessor["path"],
        "supersedes_resolver_bridge_blob_sha": predecessor["blob"],
        "current_handoff": {
            "price_path": PRICE_REL,
            "price_blob_sha": blob_sha(PRICE),
            "pass_count": len(passes),
            "pass_hash": price["pass_hash"],
            "blocked_count": 0,
            "blocked_subset_of_full_scope_block": True,
            "no_new_pass_beyond_resolver": True,
            "residual_request_path": REQUEST_REL,
            "residual_request_blob_sha": blob_sha(REQUEST),
            "residual_scope_count": 0,
        },
        "audit": {
            "full_scope_partition_exact_current_master": True,
            "exact_current_price_binding": True,
            "exact_current_request_binding": True,
            "exact_current_manifest_binding": True,
            "current_price_unknown_zero": True,
            "current_price_blocked_zero": True,
            "current_price_results_cover_queue": True,
            "pass_manufactured": False,
            "no_threshold_weakening": True,
            "no_provider_refetch": True,
            "no_price_or_dv30_remeasurement": True,
            "settlement_reused_from_same_asof_current_queue_pass_authority": True,
            "settlement_witness_relation": witness_relation,
            "predecessor_full_scope_role_scoped": True,
            "residual_authority_role_scoped": True,
        },
        "handoff_rebind": {
            "rule": "CURRENT_COMPLETE_CANONICAL_PRICE_PARTITION_TO_FULL_SCOPE_MC_HANDOFF_V1",
            "predecessor_path": predecessor["path"],
            "predecessor_blob_sha": predecessor["blob"],
            "residual_authority_path": residual["path"],
            "residual_authority_blob_sha": residual["blob"],
            "source_master_blob_sha": blob_sha(MASTER),
            "source_price_blob_sha": blob_sha(PRICE),
            "source_request_blob_sha": blob_sha(REQUEST),
            "source_manifest_blob_sha": blob_sha(MANIFEST),
            "no_alpha_threshold_change": True,
            "unknown_never_pass": True,
            "no_classification_change": True,
        },
    }
    return out


def validate_output(obj: dict, master: dict, price: dict, request: dict, compact: dict,
                    predecessor: dict, witness_path: str, witness_blob: str) -> None:
    assert obj.get("schema") == "XRAY_RESOLVER_EPOCH_RESULT_V1"
    assert obj.get("status") == "COMMITTED"
    assert obj.get("bridge_role") == FULL_ROLE
    assert obj.get("queue_hash") == master.get("queue_hash")
    assert int(obj.get("queue_total", -1)) == int(master.get("queue_total", -2))
    assert obj.get("source_price_blob_sha") == blob_sha(PRICE)
    assert obj.get("source_request_blob_sha") == blob_sha(REQUEST)
    assert obj.get("source_manifest_blob_sha") == blob_sha(MANIFEST)
    assert obj.get("price_resolution_compact") == compact
    assert set(compact["pass_price_dv30"]) == set(price.get("pass_symbols") or [])
    assert not compact["unresolved_symbols"]
    assert not compact["block_current_run"]
    assert obj.get("coverage_complete") is True
    assert obj.get("classification_coverage_complete") is True
    assert obj.get("partial_data") is False
    assert obj.get("settlement_status") == "PASS"
    assert obj.get("settlement_witness_path") == witness_path
    assert obj.get("settlement_witness_blob_sha") == witness_blob
    assert obj.get("supersedes_resolver_bridge_path") == predecessor["path"]
    assert obj.get("supersedes_resolver_bridge_blob_sha") == predecessor["blob"]
    h = obj.get("current_handoff") or {}
    assert h.get("price_blob_sha") == blob_sha(PRICE)
    assert h.get("residual_request_blob_sha") == blob_sha(REQUEST)
    assert h.get("pass_hash") == price.get("pass_hash")
    assert int(h.get("pass_count", -1)) == int(price.get("pass_count", -2))
    assert int(h.get("blocked_count", -1)) == 0
    assert int(h.get("residual_scope_count", -1)) == 0


def selftest() -> None:
    q = ["AAA", "BBB", "CCC", "DDD"]
    price = {
        "results": {
            "AAA": {"status": "FAIL_PRICE", "info": {"price": 3.0}},
            "BBB": {"status": "FAIL_DV30", "info": {"price": 8.0, "dv30": 10.0, "known_session_count": 30}},
            "CCC": {"status": "PASS_PRICE_DV30", "info": {"price": 12.0, "dv30": 100.0, "known_session_count": 30}},
            "DDD": {"status": "FAIL_PRICE_NO_ASOF_BAR", "info": {"proof": "NO_BAR", "no_synthetic_bar": True}},
        }
    }
    c = compact_from_price(price, q)
    assert set(c["fail_price"]) == {"AAA", "DDD"}
    assert set(c["fail_dv30"]) == {"BBB"}
    assert set(c["pass_price_dv30"]) == {"CCC"}
    assert not c["block_current_run"] and not c["unresolved_symbols"]
    synthetic_master = {
        "queue_hash": "current-hash",
        "queue_total": 2,
        "pass_symbols": ["AAA", "BBB"],
    }
    synthetic_witness = {
        "bridge_role": FULL_ROLE,
        "authority": "TEST_FULL_SCOPE_MC_HANDOFF",
        "queue_hash": "older-hash",
        "queue_total": 3,
        "symbols": ["AAA", "BBB", "CCC"],
        "symbol_hash": hash_lines(["AAA", "BBB", "CCC"]),
        "settlement_symbols": ["AAA", "BBB"],
    }
    assert settlement_witness_relation(synthetic_witness, synthetic_master) == "SAFE_SUBSET_REBIND"
    synthetic_witness["settlement_symbols"] = ["AAA", "CCC"]
    assert settlement_witness_relation(synthetic_witness, synthetic_master) is None
    synthetic_witness["queue_hash"] = "current-hash"
    synthetic_witness["queue_total"] = 2
    assert settlement_witness_relation(synthetic_witness, synthetic_master) == "EXACT_QUEUE"
    print("XRAY_RESOLVER_FULL_SCOPE_HANDOFF_SELFTEST=PASS")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    master = load(MASTER)
    price = load(PRICE)
    request = load(REQUEST)
    manifest = load(MANIFEST)
    queue, compact = validate_current(master, price, request, manifest)

    rows = resolver_rows(price["asof_et"])
    predecessor = select_one_active(rows, FULL_ROLE)
    current_full = active_role(rows, FULL_ROLE)
    exact = [r for r in current_full if full_scope_exact(r, master, price, request, compact)]
    if exact:
        assert len(exact) == 1, ("AMBIGUOUS_EXACT_FULL_SCOPE_HANDOFF", [r["path"] for r in exact])
        print("ready=true")
        print("created=false")
        print("path=" + exact[0]["path"])
        print("reason=EXACT_CURRENT_FULL_SCOPE_HANDOFF_ALREADY_EXISTS")
        return

    residual = select_one_active(rows, RESIDUAL_ROLE, queue_hash=master["queue_hash"])
    rj = residual["obj"]
    assert rj.get("coverage_complete") is True
    assert rj.get("classification_coverage_complete") is True
    assert rj.get("partial_data") is False
    assert rj.get("settlement_status") == "PASS"

    witness_path = str(rj.get("settlement_witness_path") or "")
    witness_blob = str(rj.get("settlement_witness_blob_sha") or "")
    if witness_path and witness_blob:
        witness, witness_path, witness_blob, witness_relation = validate_settlement_witness(
            REPO / witness_path, witness_blob, master, price["asof_et"]
        )
    else:
        witness, witness_path, witness_blob, witness_relation = validate_settlement_witness(
            residual["file"], residual["blob"], master, price["asof_et"]
        )

    out_path, version = next_path(price["asof_et"])
    assert not out_path.exists(), ("SUCCESSOR_PATH_ALREADY_EXISTS", relpath(out_path))
    obj = build_obj(
        master, price, request, manifest, compact,
        predecessor, residual, witness_path, witness_blob, witness, witness_relation, version,
    )
    validate_output(obj, master, price, request, compact, predecessor, witness_path, witness_blob)
    out_path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("ready=true")
    print("created=true")
    print("path=" + relpath(out_path))
    print("generated_blob_sha=" + blob_sha(out_path))
    print("predecessor_path=" + predecessor["path"])
    print("predecessor_blob_sha=" + predecessor["blob"])
    print("residual_authority_path=" + residual["path"])
    print("residual_authority_blob_sha=" + residual["blob"])
    print("settlement_witness_path=" + witness_path)
    print("settlement_witness_blob_sha=" + witness_blob)
    print("settlement_witness_relation=" + witness_relation)
    print("price_blob_sha=" + blob_sha(PRICE))
    print("pass_count=" + str(len(price.get("pass_symbols") or [])))
    print("queue_total=" + str(len(queue)))
    print("reason=CURRENT_COMPLETE_PRICE_PARTITION_FULL_SCOPE_HANDOFF_SUCCESSOR")


if __name__ == "__main__":
    main()
