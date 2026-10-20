#!/usr/bin/env python3
"""Graphify-compatible, *non-authoritative* immutable XRAY source-edge extractor.

Source: Graphify-Labs/graphify 0.9.93, pinned upstream
b90b9df7949bd04a15b40a1624af85d0a9cfdf04, Apache-2.0.
Graphify itself is NOT imported, installed or executed by this shadow.
No model calls, market-data API calls, network traffic, browser, hooks or servers.
Only explicit, validated C4.17 resolver path↔Git-SHA edges are emitted.
The output is a Graphify validate.py-compatible extraction (nodes/edges),
NOT a C4.17/PRIMARY/HISTORY/MC/R92 evidence authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

SCHEMA = "XRAY_GRAPHIFY_C417_SHA_LINEAGE_SHADOW_V1"
UPSTREAM = "b90b9df7949bd04a15b40a1624af85d0a9cfdf04"
REL_RESOLVER = "nasdaq-xray/canonical_current_resolver_request.json"
REL_POLICY = "nasdaq-xray/chatgpt_compiled_policy_v3.json"
ALLOWED = {
    "master": "nasdaq-xray/canonical_current_master_manifest.json",
    "overlay": "nasdaq-xray/canonical_current_resolution_overlay.json",
    "pointer": "nasdaq-xray/chatgpt_canonical_state_v2.json",
    "price": "nasdaq-xray/canonical_current_price_dv30.json",
    "state": "nasdaq-xray/canonical_current_full_state.json",
    "unknowns": "nasdaq-xray/canonical_current_unknowns.json",
}
VALID_SHA = re.compile(r"[a-f0-9]{40}\Z")

def need(ok, code):
    if not ok:
        raise ValueError("XRAY_GRAPHIFY_LINEAGE_" + code)

def safe_file(root, rel):
    need(type(rel) is str and rel in set(ALLOWED.values()) | {REL_POLICY, REL_RESOLVER},
         "UNALLOWLISTED_FILE")
    base = root.resolve(strict=True)
    actual = (root / rel).resolve(strict=True)
    need(actual.is_relative_to(base) and actual.is_file()
         and not (root / rel).is_symlink(), "ESCAPED_OR_MISSING_FILE")
    return actual

def sha_git(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def read_bound(root, rel, expected):
    need(type(expected) is str and VALID_SHA.fullmatch(expected), "BAD_SHA")
    content = safe_file(root, rel).read_bytes()
    need(sha_git(content) == expected, "SHA_DRIFT:" + rel)
    return content

def build(root):
    root = Path(root)
    resolver_raw = safe_file(root, REL_RESOLVER).read_bytes()
    resolver = json.loads(resolver_raw)
    need(type(resolver) is dict, "RESOLVER_BAD_TYPE")
    asof = resolver.get("asof_et")
    need(type(asof) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}", asof),
         "ASOF_BAD_FORMAT")
    need(resolver.get("compiled_policy_version") == "C4.17"
         and resolver.get("execution") == "NONE"
         and resolver.get("real_money") == "NO-GO"
         and resolver.get("unknown_never_pass") is True
         and resolver.get("status") == "READY", "C417_RESOLVER_SAFETY")
    need(resolver.get("compiled_policy_path") == REL_POLICY, "POLICY_PATH_DRIFT")
    policy_raw = read_bound(root, REL_POLICY, resolver.get("compiled_policy_blob_sha"))
    policy = json.loads(policy_raw)
    rules = json.loads(policy["payload_json"])
    need(policy.get("policy_hash") == resolver.get("compiled_policy_hash")
         and policy.get("execution") == "NONE"
         and policy.get("real_money") == "NO-GO"
         and rules.get("version") == "C4.17"
         and rules.get("unknown_never_pass") is True, "C417_POLICY_DRIFT")

    nodes = [
        {"id": "xray:c417:resolver", "label": REL_RESOLVER,
         "file_type": "concept", "source_file": REL_RESOLVER,
         "git_blob_sha": sha_git(resolver_raw)},
        {"id": "xray:c417:policy", "label": REL_POLICY,
         "file_type": "concept", "source_file": REL_POLICY,
         "git_blob_sha": sha_git(policy_raw)},
    ]
    edges = [{
        "source": "xray:c417:resolver", "target": "xray:c417:policy",
        "relation": "depends_on_exact_sha", "confidence": "EXTRACTED",
        "source_file": REL_RESOLVER,
    }]
    for name, path in sorted(ALLOWED.items()):
        need(resolver.get("source_" + name + "_path") == path, "PATH_DRIFT:" + name)
        expected = resolver.get("source_" + name + "_blob_sha")
        body = read_bound(root, path, expected)
        # Same-ASOF gate only where the input schema guarantees ASOF.
        if name in ("master", "price"):
            data = json.loads(body)
            need(data.get("asof_et") == asof
                 and data.get("execution") == "NONE"
                 and data.get("real_money") == "NO-GO"
                 and data.get("unknown_never_pass") is True,
                 "PRIMARY_ASOF_OR_SAFETY_DRIFT:" + name)
        id_ = "xray:c417:artifact:" + name
        nodes.append({"id": id_, "label": path, "file_type": "concept",
                      "source_file": path, "git_blob_sha": expected})
        edges.append({"source": "xray:c417:resolver", "target": id_,
                      "relation": "depends_on_exact_sha",
                      "confidence": "EXTRACTED", "source_file": REL_RESOLVER})
    need(len(nodes) == 8 and len(edges) == 7, "EDGE_COUNT_DRIFT")
    need(len({x["id"] for x in nodes}) == len(nodes)
         and {e["source"] for e in edges} == {"xray:c417:resolver"}
         and {e["target"] for e in edges} == {n["id"] for n in nodes[1:]},
         "GRAPH_INVALID")
    return {
        "schema": SCHEMA, "graphify_upstream_git_sha": UPSTREAM,
        "graphify_runtime_executed": False,
        "data_semantics": "EXPLICIT_C417_SOURCE_SHA_ONLY_NO_DAG_INFERENCE",
        "asof_et": asof, "nodes": nodes, "edges": edges,
        "confidence_rule": "ONLY_SHA_VERIFIED_BINDINGS_ARE_EXTRACTED",
        "source_authority_promoted": False, "primary_pass_created": False,
        "r92_created": False, "notifications_sent": False,
        "can_override_c417": False, "unknown_never_pass": True,
        "execution": "NONE", "real_money": "NO-GO",
        "status": "SHA_BOUND_SHADOW_ONLY",
    }

def selftest():
    with tempfile.TemporaryDirectory(prefix="xray-graphify-test-") as tmp:
        root = Path(tmp)
        (root / "nasdaq-xray").mkdir()
        docs = {
            "master": {"asof_et": "2026-10-19", "execution": "NONE",
                       "real_money": "NO-GO", "unknown_never_pass": True},
            "price": {"asof_et": "2026-10-19", "execution": "NONE",
                      "real_money": "NO-GO", "unknown_never_pass": True},
        }
        q = {"asof_et": "2026-10-19",
             "compiled_policy_version": "C4.17", "execution": "NONE",
             "real_money": "NO-GO", "unknown_never_pass": True,
             "status": "READY", "compiled_policy_hash": "offline-synthetic-only",
             "compiled_policy_path": REL_POLICY}
        pp = {"execution": "NONE", "real_money": "NO-GO",
              "policy_hash": "offline-synthetic-only",
              "payload_json": json.dumps({"version": "C4.17", "unknown_never_pass": True})}
        path_policy = root / REL_POLICY
        path_policy.write_text(json.dumps(pp))
        q["compiled_policy_blob_sha"] = sha_git(path_policy.read_bytes())
        for name, rel in ALLOWED.items():
            file = root / rel
            file.write_text(json.dumps(docs.get(name, {"historical": True})))
            q["source_" + name + "_path"] = rel
            q["source_" + name + "_blob_sha"] = sha_git(file.read_bytes())
        (root / REL_RESOLVER).write_text(json.dumps(q))
        ok = build(root)
        need(ok["status"] == "SHA_BOUND_SHADOW_ONLY"
             and len(ok["nodes"]) == 8 and len(ok["edges"]) == 7
             and not ok["primary_pass_created"] and not ok["r92_created"],
             "GOOD_FIXTURE_REJECTED")
        def bad(mutator, reason):
            before = (root / REL_RESOLVER).read_bytes()
            try:
                obj = json.loads(before)
                mutator(obj)
                (root / REL_RESOLVER).write_text(json.dumps(obj))
                try:
                    build(root)
                except ValueError as ex:
                    need(reason in str(ex), "WRONG_NEGATIVE_REASON:" + str(ex))
                else:
                    raise RuntimeError("FAIL_OPEN:" + reason)
            finally:
                (root / REL_RESOLVER).write_bytes(before)
        bad(lambda o:o.update(source_price_blob_sha="0" * 40), "SHA_DRIFT")
        bad(lambda o:o.update(source_price_path="../.env"), "PATH_DRIFT")
        bad(lambda o:o.update(compiled_policy_blob_sha="0" * 40), "SHA_DRIFT")
        bad(lambda o:o.update(asof_et="2026-10-18"), "PRIMARY_ASOF")
        bad(lambda o:o.update(unknown_never_pass=False), "C417_RESOLVER")
        bad(lambda o:o.update(compiled_policy_version="C4.18"), "C417_RESOLVER")
        bad(lambda o:o.update(source_master_blob_sha="not-a-sha"), "BAD_SHA")
        # A forged valid SHA cannot make the underlying file pass.
        old = (root / ALLOWED["master"]).read_bytes()
        try:
            (root / ALLOWED["master"]).write_bytes(old + b" ")
            try:
                build(root)
            except ValueError as ex:
                need("SHA_DRIFT" in str(ex), "FORGED_SOURCE_NOT_SHA_BLOCKED")
            else:
                raise RuntimeError("FAIL_OPEN_MUTATED_FILE")
        finally:
            (root / ALLOWED["master"]).write_bytes(old)
    print("XRAY_GRAPHIFY_SHA_LINEAGE=PASS_8_NEGATIVES_NO_PRIMARY_NO_R92_ZERO_VENDOR")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    data = build(args.root)
    result = json.dumps(data, sort_keys=True, indent=2) + "\n"
    if args.out is None:
        print(result, end="")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(result, encoding="utf-8")

if __name__ == "__main__":
    main()
