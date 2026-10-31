"""A36: read-only, offline, source-grounded NASDAQ PERSONAL dependency and security witness.

Approach inspired by Graphify-Labs/graphify (Apache-2.0), Cloudflare's
security-audit-skill (MIT) and Addy Osmani's agent-skills (MIT). No third-party
code is imported/installed and no full Graphify/Cloudflare runtime is claimed.
No secrets, vendor API, broker, prompts, workflow dispatch or repository writes.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

SCHEMA = "XRAY_NASDAQ_PERSONAL_A36_SOURCE_WITNESS_V1"
ALLOWED = ("personal-swing/", ".github/workflows/")
ACTION = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
CODE_REF = re.compile(r"personal-swing/(?:[A-Za-z_][A-Za-z_0-9]*/)*[A-Za-z_][A-Za-z_0-9]*\.py")
PIN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./-]+)?@[a-f0-9]{40}$")
WEAK_REF = re.compile(r"\b(pull_request_target|id-token:\s*write|actions:\s*write|contents:\s*write)\b")
PERSONAL_WORKFLOW = re.compile(r"(?i)(personal|nasdaq-backtesting-challenger)")


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError("A36_" + code)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def allowed_rel(path: str) -> bool:
    return (type(path) is str and "\\" not in path and "\x00" not in path
            and not path.startswith("/") and
            all(x not in ("", ".", "..") for x in path.split("/"))
            and any(path.startswith(p) for p in ALLOWED))


def scan_sources(sources: dict[str, str], *, commit_sha: str) -> dict:
    """Public/tracked source snapshot only. All edges carry exact source line."""
    need(type(sources) is dict and bool(sources), "EMPTY_CORPUS")
    need(type(commit_sha) is str and re.fullmatch("[a-f0-9]{40}", commit_sha),
         "INVALID_COMMIT")
    need(len(sources) <= 400, "SCOPE_BUDGET")
    py = {k for k in sources if k.startswith("personal-swing/") and k.endswith(".py")}
    workflows = {k for k in sources if k.startswith(".github/workflows/") and
                 k.endswith((".yml", ".yaml"))}
    need(py and workflows, "SCOPE_MISSING_PY_OR_WORKFLOWS")
    nodes, edges, coverage, leads = [], [], [], []
    for filename in sorted(sources):
        body = sources[filename]
        need(allowed_rel(filename) and type(body) is str and
             len(body.encode("utf-8")) <= 900_000, "PATH_OR_SOURCE_BOUND")
        need("\x00" not in body and filename.endswith((".py", ".yml", ".yaml")),
             "UNSUPPORTED_SOURCE")
        lines = body.splitlines()
        content_sha = digest(body.encode("utf-8"))
        nodes.append({"id": filename, "sha256": content_sha, "kind":
                      "python" if filename in py else "workflow"})
        coverage.append({"unit": filename, "sha256": content_sha,
                         "method": "PYTHON_AST" if filename in py else "WORKFLOW_TEXT",
                         "review_status": "STATIC_COVERED_NOT_RUNTIME", "lines": len(lines)})
        if filename in py:
            tree = ast.parse(body, filename=filename)
            for t in ast.walk(tree):
                names = []
                if isinstance(t, ast.Import):
                    names = [a.name for a in t.names]
                elif isinstance(t, ast.ImportFrom) and t.module and t.level == 0:
                    names = [t.module]
                for imp in names:
                    # Only a resolvable SAME-PACKAGE Python import is authoritative.
                    root = imp.split(".")[0]
                    candidate = str(Path(filename).parent / (root + ".py"))
                    if candidate in py:
                        edges.append({"from": filename, "to": candidate,
                                      "relation": "imports", "source_file": filename,
                                      "line": t.lineno, "confidence": "EXTRACTED"})
                    else:
                        # No inference about runtime reachability / stdlib / dynamic imports.
                        continue
        else:
            for match in CODE_REF.finditer(body):
                target = match.group(0)
                line = body.count("\n", 0, match.start()) + 1
                # Workflow content alone can mention paths in comments; classify as
                # candidate rather than claiming runtime invocation.
                line_text = lines[line - 1].strip()
                if line_text.startswith("#"):
                    continue
                if target in py:
                    edges.append({"from": filename, "to": target,
                                  "relation": "mentions_script_not_proven_executes",
                                  "source_file": filename, "line": line,
                                  "confidence": "EXTRACTED"})
                else:
                    leads.append({"source_file": filename, "line": line,
                                  "code": "UNRESOLVED_SCRIPT_REFERENCE",
                                  "verdict": "needs_validation", "severity": None})
            for match in ACTION.finditer(body):
                action = match.group(1)
                line = body.count("\n", 0, match.start()) + 1
                if action.startswith("./"):
                    continue
                if not PIN.fullmatch(action):
                    leads.append({"source_file": filename, "line": line,
                                  "code": "ACTION_NOT_SHA_PINNED",
                                  "verdict": "needs_validation", "severity": None})
            if re.search(r"(?m)^\s*pull_request_target\s*:", body):
                leads.append({"source_file": filename, "line": next(
                    i for i, s in enumerate(lines, 1) if re.search(r"^\s*pull_request_target\s*:", s)),
                    "code": "PR_TARGET_TRUST_BOUNDARY_REVIEW", "verdict": "needs_validation",
                    "severity": None})
    edges = sorted({json.dumps(e, sort_keys=True): e for e in edges}.values(),
                   key=lambda e: (e["source_file"], e["line"], e["to"], e["relation"]))
    need(len(edges) <= 16000, "EDGE_BUDGET")
    for e in edges:
        src, target = e["source_file"], e["to"]
        need(src in sources and target in sources and e["line"] > 0 and
             e["line"] <= len(sources[src].splitlines()), "ORPHAN_EDGE")
        needle = (target if e["relation"].startswith("mentions")
                  else Path(target).stem)
        need(needle in sources[src].splitlines()[e["line"]-1],
             "INVALID_SOURCE_LINE_PROOF")
    coverage_hash = digest(json.dumps(coverage, sort_keys=True).encode())
    return {"schema": SCHEMA, "commit_sha": commit_sha,
            "graph_type": "EXPLICIT_STATIC_WITNESS_NOT_GRAPHIFY_EXECUTION",
            "source_count": len(sources), "python_count": len(py),
            "workflow_count": len(workflows), "nodes": nodes, "edges": edges,
            "coverage_ledger": coverage, "ledger_sha256": coverage_hash,
            "findings": sorted(leads, key=lambda x: (x["source_file"], x["line"], x["code"])),
            "finding_policy": "NO_CONFIRMED_VULN_FROM_STATIC_PATTERN",
            "runtime_reachable_proven": False, "private_data_access": False,
            "network_calls": False, "writes": False, "orders": False,
            "notifications": False, "rule_changes": False}


def validate_report(report: dict, sources: dict[str, str]) -> None:
    need(type(report) is dict and report.get("schema") == SCHEMA,
         "REPORT_SCHEMA")
    need(report.get("source_count") == len(sources) and
         len(report.get("coverage_ledger", [])) == len(sources), "COVERAGE_INCOMPLETE")
    need(report["ledger_sha256"] == digest(json.dumps(
         report["coverage_ledger"], sort_keys=True).encode()), "LEDGER_SHA_DRIFT")
    need({x["unit"] for x in report["coverage_ledger"]} == set(sources),
         "COVERAGE_PATH_DRIFT")
    for row in report["coverage_ledger"]:
        need(row["sha256"] == digest(sources[row["unit"]].encode()),
             "COVERAGE_SOURCE_TAMPER")
    for item in report["findings"]:
        need(set(item) == {"source_file", "line", "code", "verdict", "severity"}
             and item["verdict"] in ("confirmed", "needs_validation", "rejected")
             and item["severity"] is None
             and item["source_file"] in sources, "FINDING_INVALID")
    for edge in report["edges"]:
        need(edge["source_file"] in sources and edge["to"] in sources and
             edge["line"] <= len(sources[edge["source_file"]].splitlines()) and
             edge["line"] > 0, "EDGE_EVIDENCE_INVALID")
    need(report["writes"] is False and report["orders"] is False and
         report["notifications"] is False and
         report["runtime_reachable_proven"] is False,
         "UNAUTHORIZED_CAPABILITY_CLAIM")


def checked_repo_sources(root: Path) -> tuple[str, dict[str, str]]:
    """Only tracked files from checkout. Never follows symlinks or reads secrets."""
    root = root.resolve(strict=True)
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                   text=True).strip()
    need(re.fullmatch("[a-f0-9]{40}", head) is not None, "HEAD_UNTRUSTED")
    sources = {}
    for b in raw.split(b"\x00"):
        if not b:
            continue
        key = b.decode("utf-8")
        if not allowed_rel(key):
            continue
        if key.startswith("personal-swing/") and not key.endswith(".py"):
            continue
        if key.startswith(".github/workflows/") and (
             not key.endswith((".yml", ".yaml")) or not PERSONAL_WORKFLOW.search(key)):
            continue
        src = root / key
        need(not src.is_symlink() and src.resolve(strict=True).is_relative_to(root),
             "LINK_ESCAPE")
        need(src.is_file() and src.stat().st_size <= 900_000, "SOURCE_BUDGET")
        sources[key] = src.read_text(encoding="utf-8")
    return head, sources


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-repo", required=True)
    ap.add_argument("--min-edges", type=int, default=20)
    ap.add_argument("--min-workflow-edges", type=int, default=2)
    args = ap.parse_args()
    head, files = checked_repo_sources(Path(args.audit_repo))
    report = scan_sources(files, commit_sha=head)
    validate_report(report, files)
    w_edges = sum(x["relation"].startswith("mentions") for x in report["edges"])
    need(len(report["edges"]) >= args.min_edges and
         w_edges >= args.min_workflow_edges, "GRAPH_MINIMUM_COVERAGE")
    print(json.dumps({"state": "PASS_STATIC_SOURCE_LEDGER_NOT_SECURITY_CERTIFICATE",
                      "source_sha": head, "sources": report["source_count"],
                      "python": report["python_count"],
                      "workflows": report["workflow_count"],
                      "edges": len(report["edges"]), "workflow_edges": w_edges,
                      "unverified_leads": len(report["findings"]),
                      "ledger_sha256": report["ledger_sha256"],
                      "orders": False, "writes": False, "network_calls": False},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
