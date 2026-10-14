#!/usr/bin/env python3
"""Full tracked-source syntax/inventory and candidate-delivery guard audit.

No vendor call, order, signal, workflow dispatch, mutation or deletion.
Only checkout-tracked files count; runtime-generated caches are ignored.
Orphan candidates and identical blobs are diagnostics, never deletion proof.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import yaml

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO / "nasdaq-xray"
SCRIPT_RE = re.compile(r"nasdaq-xray/[A-Za-z0-9_./-]+\.py")

def check(condition, label):
    if not condition:
        raise ValueError("XRAY_REPO_INTEGRITY_" + label)

def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def tracked():
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=REPO)
    return sorted(Path(x.decode("utf-8")) for x in raw.split(b"\0") if x)

def census(paths, read_bytes):
    """Classify every tracked Python, JSON, workflow and generated-bytecode file."""
    errors, notices = [], []
    counts = Counter()
    source_hashes = defaultdict(list)
    scripts = set()
    workflow_sources = {}
    import_edges = {}
    for path in paths:
        name = path.as_posix()
        is_source = name.startswith("nasdaq-xray/") and path.suffix == ".py"
        is_json = name.startswith("nasdaq-xray/") and path.suffix == ".json"
        is_workflow = name.startswith(".github/workflows/") and path.suffix in {".yml", ".yaml"}
        if name.endswith(".pyc") or "/__pycache__/" in name:
            errors.append("TRACKED_COMPILED_BYTECODE:" + name)
        if not (is_source or is_json or is_workflow):
            continue
        kind = "python" if is_source else "json" if is_json else "workflows"
        counts[kind] += 1
        try:
            raw = read_bytes(path)
            check(type(raw) is bytes and raw, "EMPTY_SOURCE")
            source_hashes[sha256(raw)].append(name)
            text = raw.decode("utf-8-sig")
            if is_source:
                scripts.add(name)
                tree = ast.parse(text, filename=name)
                deps = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        deps.update(x.name.split(".")[0] for x in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        deps.add(node.module.split(".")[0])
                import_edges[name] = sorted(deps)
            elif is_json:
                json.loads(text)
            else:
                # BaseLoader preserves GitHub\u0027s YAML 1.2 on: key as a string;
                # SafeLoader in YAML 1.1 treats it as boolean True.
                parsed = yaml.load(text, Loader=yaml.BaseLoader)
                check(isinstance(parsed, dict) and "on" in parsed and
                      isinstance(parsed.get("jobs"), dict) and
                      len(parsed["jobs"]) > 0,
                      "WORKFLOW_YAML_TRIGGER_OR_JOB_MISSING")
                workflow_sources[path.name] = text
        except (OSError, UnicodeError, SyntaxError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
            errors.append("UNREADABLE_OR_INVALID_" + kind.upper() + ":" + name
                          + ":" + type(exc).__name__)
    source_modules = {Path(x).stem for x in scripts}
    used_modules = {dep for deps in import_edges.values() for dep in deps}
    script_mentions = set()
    for name, body in workflow_sources.items():
        for match in SCRIPT_RE.findall(body):
            script_mentions.add(match)
            if match not in scripts:
                notices.append("WORKFLOW_REFERENCE_REQUIRES_REVIEW:" + name + ":" + match)
    # Dynamic imports, subprocesses and manual-only tests are not provable by
    # static inspection: unreferenced here means REVIEW, not deletion.
    orphan_review = sorted(x for x in scripts
                           if Path(x).stem not in used_modules
                           and x not in script_mentions)
    identical = [p for p in source_hashes.values() if len(p) > 1]
    report = {
        "schema": "XRAY_FULL_TRACKED_REPOSITORY_INTEGRITY_AUDIT_V1",
        "tracked_file_count": len(paths),
        "python_ast_parsed_count": counts["python"],
        "json_parsed_count": counts["json"],
        "workflow_examined_count": counts["workflows"],
        "duplicate_file_groups": sorted(identical),
        "statically_unreferenced_python_review_count": len(orphan_review),
        "statically_unreferenced_python_review": orphan_review,
        "workflow_script_reference_count": len(script_mentions),
        "workflow_reference_review": sorted(set(notices)),
        "structural_errors": sorted(set(errors)),
        "no_deletions_inferred_from_static_scan": True,
        "execution": "NONE",
        "real_money": "NO-GO",
    }
    return report, workflow_sources

def research_release_observability(root_asof, terminal_asof, history_unknown,
                                    technical_pending, g9_state):
    """Never confuse a clean repository with a cleared canonical AL gate.

    This is a diagnostic only: not a G9 authority check or release engine.
    """
    blockers = []
    if root_asof != terminal_asof:
        blockers.append("CANONICAL_TERMINAL_ASOF_DRIFT")
    if type(history_unknown) is not int or history_unknown != 0:
        blockers.append("ROOT_HISTORY_NOT_FULLY_RESOLVED")
    if type(technical_pending) is not int or technical_pending != 0:
        blockers.append("CANDIDATE_TECHNICAL_SOURCE_PENDING")
    if g9_state != "PROVEN_FROM_PRIMARY_SOURCE":
        blockers.append("G9_REALTIME_CONSOLIDATED_ENTITLEMENT_UNPROVEN")
    # Even with no diagnostic blockers, this audit cannot attest the full
    # C4.17 FINAL, lifecycle, legal halt or a physical device receipt.
    return {
        "diagnostic_blockers": blockers,
        "status": ("BLOCKED_DIAGNOSTICS" if blockers
                   else "UNATTESTED_FINAL_REQUIRES_FULL_RELEASE_GATES"),
        "production_release_authorized_by_this_audit": False,
        "r92_created_by_this_audit": False,
        "device_receipt_verified_by_this_audit": False,
        "execution": "NONE", "real_money": "NO-GO"
    }


def preopen_stale_noop_topology(raw):
    """Stale workflow runs must skip every source/alert step, not certify data."""
    doc = yaml.load(raw, Loader=yaml.BaseLoader)
    if not isinstance(doc, dict):
        raise ValueError("PREOPEN_YAML_INVALID")
    steps = ((doc.get("jobs") or {}).get("audit") or {}).get("steps")
    if not isinstance(steps, list):
        raise ValueError("PREOPEN_STEPS_INVALID")
    indexed = [i for i, row in enumerate(steps) if
               isinstance(row, dict) and row.get("id") == "epoch_guard"]
    if len(indexed) != 1 or indexed[0] != 1:
        raise ValueError("PREOPEN_EPOCH_GUARD_NOT_FIRST_AFTER_CHECKOUT")
    guard = steps[indexed[0]]
    script = guard.get("run") or ""
    for marker in ("git rev-parse HEAD", "git ls-remote origin refs/heads/main",
                   "valid=false", "valid=true", "SAFE_NOOP_NO_EVIDENCE"):
        if marker not in script:
            raise ValueError("PREOPEN_GUARD_MISSING_" + marker.replace(" ", "_"))
    if "XRAY_PREOPEN_UNEXPECTED_CHECKOUT_SHA_FAIL_CLOSED" not in script:
        raise ValueError("PREOPEN_CHECKOUT_DRIFT_NOT_FATAL")
    trailing = steps[indexed[0]+1:]
    if len(trailing) < 12:
        raise ValueError("PREOPEN_TRUNCATED_STEP_LIST")
    expected = "steps.epoch_guard.outputs.valid == 'true'"
    for step in trailing:
        if not isinstance(step, dict) or step.get("if") != expected:
            raise ValueError("PREOPEN_UNGUARDED_STEP:" +
                             str(step.get("name") or step.get("uses")))
    return {"status": "PASS_EXACT_STALE_NOOP_NO_EVIDENCE",
            "guarded_after_epoch_count": len(trailing),
            "stale_mixed_source_authorization": False,
            "source_execution_requires_current_sha": True}


def source_integrity():
    """One exact source epoch; a complete WATCH is not a complete terminal."""
    candidate_bytes = (ROOT / "sina_candidates.json").read_bytes()
    root = json.loads((ROOT / "orchestrator_state.json").read_text())
    watch = root.get("watch_radar") or {}
    technical = root.get("candidate_technical_funnel") or {}
    ledger = json.loads((ROOT / "delivery_ledger.json").read_text())
    registry = json.loads((ROOT / "canonical_candidate_lifecycle_registry.json").read_text())
    terminal = json.loads((ROOT / "canonical_current_terminal.json").read_text())
    g9 = json.loads((ROOT / "g9_entitlement_authority.json").read_text())
    check(g9.get("execution") == "NONE" and g9.get("real_money") == "NO-GO",
          "G9_STATE_SAFETY")
    count = watch.get("watchlist_count")
    rows = watch.get("watchlist")
    check(root.get("execution") == "NONE" and root.get("real_money") == "NO-GO",
          "ROOT_SAFETY")
    check(type(rows) is list and type(count) is int and
          count == len(rows) == watch.get("price_liquidity_screened_count") and
          watch.get("all_eligible_candidates_tracked") is True and
          watch.get("watchlist_cap") is None, "WATCH_UNTRUNCATED")
    check(sha256(candidate_bytes) == watch.get("source_candidates_sha256") ==
          technical.get("source_candidates_sha256"), "CANDIDATE_SOURCE_SHA")
    check(root.get("asof_et") == watch.get("asof_et") ==
          technical.get("asof_et"), "ROOT_WATCH_TECH_ASOF")
    check(watch.get("watchlist_digest") == technical.get("watchlist_digest"),
          "WATCH_TECH_DIGEST")
    symbols = [v["symbol"] for v in rows]
    check(len(set(symbols)) == count, "DUPLICATE_WATCH")
    results = technical.get("results")
    check(type(results) is dict and set(results).issubset(set(symbols)),
          "TECH_OUT_OF_SCOPE_RESULT")
    completed = sum(type(v) is dict and v.get("terminal_scan") is True
                    and type(v.get("status")) is str and
                    not v["status"].startswith("UNKNOWN_")
                    for v in results.values())
    check(completed == technical.get("evaluated_count") and
          count - completed == technical.get("pending_count") and
          len(results) == technical.get("attempted_count"),
          "TECH_COVERAGE_PARTITION")
    check(ledger.get("schema") == "XRAY_DELIVERY_LEDGER_V1" and
          type(ledger.get("deliveries")) is dict and
          registry.get("schema") == "XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1" and
          type(registry.get("records")) is dict, "DELIVERY_REGISTRY_SCHEMA")
    check(all(x.get("execution") == "NONE" and
              x.get("real_money") == "NO-GO"
              for x in (ledger, registry, terminal)), "DELIVERY_SAFETY")
    return {
        "root_asof_et": root.get("asof_et"),
        "watch_count": count,
        "technical_evaluated": completed,
        "technical_pending": count-completed,
        "lifecycle_record_count": len(registry["records"]),
        "delivery_ledger_count": len(ledger["deliveries"]),
        "terminal_asof_et": terminal.get("asof_et"),
        "terminal_same_asof": terminal.get("asof_et") == root.get("asof_et"),
        "production_readiness": research_release_observability(
            root.get("asof_et"), terminal.get("asof_et"),
            root.get("unknown_count"), count-completed, g9.get("status")),
        "device_receipt_proven": False,
        "r92_issued_by_audit": 0,
    }

def selftest():
    sample = [Path("nasdaq-xray/good.py"), Path("nasdaq-xray/good.json"),
              Path(".github/workflows/good.yml")]
    data = {
        sample[0]: b"import json\nX = 3\n",
        sample[1]: b'{"status":"WATCH"}',
        sample[2]: b"name: audit\non:\n  workflow_dispatch:\njobs:\n  checks:\n    runs-on: ubuntu-latest\n"}
    one, _ = census(sample, data.__getitem__)
    assert not one["structural_errors"] and one["python_ast_parsed_count"] == 1
    assert one["json_parsed_count"] == one["workflow_examined_count"] == 1
    bad = dict(data)
    bad[sample[0]] = b"def wrong(: pass"
    assert any("INVALID_PYTHON" in x for x in
               census(sample, bad.__getitem__)[0]["structural_errors"])
    bad = dict(data)
    bad[sample[1]] = b'{"bad":'
    assert any("INVALID_JSON" in x for x in
               census(sample, bad.__getitem__)[0]["structural_errors"])
    garbage = Path("nasdaq-xray/__pycache__/obsolete.pyc")
    out, _ = census(sample + [garbage], lambda p: data.get(p, b"x"))
    assert any("TRACKED_COMPILED_BYTECODE" in x
               for x in out["structural_errors"])
    blocked = research_release_observability(
        "2026-10-13", "2026-10-07", 220, 4,
        "BLOCKED_STRICT_PERMANENT_ZERO")
    assert blocked["status"] == "BLOCKED_DIAGNOSTICS"
    assert set(blocked["diagnostic_blockers"]) == {
        "CANONICAL_TERMINAL_ASOF_DRIFT",
        "ROOT_HISTORY_NOT_FULLY_RESOLVED",
        "CANDIDATE_TECHNICAL_SOURCE_PENDING",
        "G9_REALTIME_CONSOLIDATED_ENTITLEMENT_UNPROVEN",
    }
    assert blocked["production_release_authorized_by_this_audit"] is False
    no_obvious = research_release_observability(
        "2026-10-13", "2026-10-13", 0, 0,
        "PROVEN_FROM_PRIMARY_SOURCE")
    assert no_obvious["status"] == "UNATTESTED_FINAL_REQUIRES_FULL_RELEASE_GATES"
    assert no_obvious["production_release_authorized_by_this_audit"] is False
    from copy import deepcopy
    workflow = (REPO / ".github/workflows/xray-preopen-source-audit.yml").read_text()
    verified = preopen_stale_noop_topology(workflow)
    assert verified["status"] == "PASS_EXACT_STALE_NOOP_NO_EVIDENCE"
    obj = yaml.load(workflow, Loader=yaml.BaseLoader)
    broken = deepcopy(obj)
    broken["jobs"]["audit"]["steps"][-1].pop("if", None)
    try:
        preopen_stale_noop_topology(yaml.safe_dump(broken))
    except ValueError as exc:
        assert str(exc).startswith("PREOPEN_UNGUARDED_STEP")
    else:
        raise AssertionError("UNGUARDED_STALE_PREOPEN_ACTION_ACCEPTED")
    tampered = deepcopy(obj)
    tampered["jobs"]["audit"]["steps"][1]["run"] = "echo valid=true"
    try:
        preopen_stale_noop_topology(yaml.safe_dump(tampered))
    except ValueError as exc:
        assert str(exc).startswith("PREOPEN_GUARD_MISSING")
    else:
        raise AssertionError("MISSING_SHA_BINDING_ACCEPTED")
    print("XRAY_PREOPEN_STALE_SHA_NOOP_SELFTEST=PASS_ALL_DOWNSTREAM_FENCED")
    print("XRAY_TRACKED_HYGIENE_SELFTEST=PASS_PY_AST_JSON_YAML_AND_PRODUCTION_DIAGNOSTIC_FAIL_CLOSED")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    result, workflows = census(tracked(), lambda p: (REPO / p).read_bytes())
    from all_workflow_schedule_audit import inventory
    schedules = inventory(workflows)
    result["schedule_contract_status"] = schedules["contract_status"]
    result["schedule_count"] = schedules["scheduled_count"]
    result["schedule_blockers"] = schedules["blockers"]
    result["preopen_stale_epoch_topology"] = preopen_stale_noop_topology(
        (REPO / ".github/workflows/xray-preopen-source-audit.yml").read_text())
    result["chain"] = source_integrity()
    result["status"] = ("PASS_SOURCE_STRUCTURE_AND_FAIL_CLOSED_CHAIN"
                        if not result["structural_errors"] and
                        schedules["contract_status"] == "PASS" else "FAIL")
    if args.out:
        check(not args.out.resolve().is_relative_to(REPO.resolve()),
              "NO_REPO_REPORT_WRITE")
        args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("XRAY_REPO_INVENTORY=" + json.dumps({
        k: result[k] for k in
        ("status","python_ast_parsed_count","json_parsed_count",
         "workflow_examined_count","schedule_count",
         "schedule_contract_status","statically_unreferenced_python_review_count",
         "structural_errors")}, sort_keys=True))
    print("XRAY_REPO_CANDIDATE_CHAIN=" + json.dumps(result["chain"],sort_keys=True))
    print("XRAY_PREOPEN_STALE_NOOP_TOPOLOGY=" + json.dumps(result["preopen_stale_epoch_topology"], sort_keys=True))
    print("XRAY_REPO_PRODUCTION_READINESS=" +
          json.dumps(result["chain"]["production_readiness"], sort_keys=True))
    print("XRAY_STATIC_ORPHANS_REVIEW=" + json.dumps(result["statically_unreferenced_python_review"]))
    print("XRAY_EXACT_DUPLICATE_FILES=" + json.dumps(result["duplicate_file_groups"]))
    if result["status"] != "PASS_SOURCE_STRUCTURE_AND_FAIL_CLOSED_CHAIN":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
