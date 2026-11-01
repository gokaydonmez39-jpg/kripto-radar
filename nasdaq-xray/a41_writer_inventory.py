#!/usr/bin/env python3
"""A41 offline-only inventory of GitHub workflow writers (advisory, fail-closed).

No GitHub/API/network calls, no writes to the repository, and no protection
changes.  A zero exit means a static *screen*, not branch protection approval.
Exit 3 = HOLD, exit 2 = cannot inventory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import yaml

SCHEMA = "XRAY_NASDAQ_A41_WORKFLOW_WRITER_INVENTORY_V1"
PUSH = re.compile(r"\bgit\s+(?:-[cC]\s+\S+\s+)*push\b", re.I)
MAIN = re.compile(r"\bHEAD:(?:refs/heads/)?main\b|\brefs/heads/main\b|\borigin\s+main\b", re.I)
GIT_COMMIT = re.compile(r"\bgit\s+(?:-[cC]\s+\S+\s+)*commit\b", re.I)
GH_MUTATION = re.compile(r"\bgh\s+(?:workflow\s+run|pr\s+create|api\b.*(?:-X\s*|--method[=\s]*)(?:POST|PUT|PATCH|DELETE))", re.I)
API_MUTATION = re.compile(r"\b(?:requests|httpx)\.(?:post|put|patch|delete)\s*\(|\bgithub\.rest\.[\w.]+\.(?:create|update|delete|merge)\s*\(", re.I)
PR_ACTION = re.compile(r"peter-evans/create-pull-request|gh\s+pr\s+create", re.I)


class AuditError(ValueError):
    pass


def grants(value):
    if value is None or value == "read-all":
        return []
    if value == "write-all":
        return ["*"]
    if not isinstance(value, dict):
        raise AuditError("PERMISSIONS_INVALID")
    return sorted(str(k) for k, v in value.items() if v == "write")


def analyze(path):
    if path.is_symlink():
        raise AuditError("SYMLINK_WORKFLOW")
    raw = path.read_bytes()
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise AuditError("YAML_PARSE_ERROR") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), dict) or not doc["jobs"]:
        raise AuditError("WORKFLOW_JOBS_INVALID")
    writes = set(grants(doc.get("permissions")))
    direct, unknown = [], []
    for job_name, job in doc["jobs"].items():
        if not isinstance(job, dict):
            raise AuditError("JOB_INVALID")
        writes.update(grants(job.get("permissions", doc.get("permissions"))))
        steps = job.get("steps", [])
        if steps is None:
            steps = []
        if not isinstance(steps, list):
            raise AuditError("STEPS_INVALID")
        for number, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                raise AuditError("STEP_INVALID")
            run = step.get("run", "")
            if run is None:
                run = ""
            if not isinstance(run, str):
                raise AuditError("SCRIPT_INVALID")
            uses = str(step.get("uses", ""))
            for line_number, line in enumerate(run.splitlines(), 1):
                site = {"job": str(job_name), "step": number, "script_line": line_number}
                if PUSH.search(line):
                    if MAIN.search(line):
                        direct.append(site)
                    else:
                        unknown.append({**site, "reason": "PUSH_TARGET_UNKNOWN"})
                if GH_MUTATION.search(line) or API_MUTATION.search(line):
                    unknown.append({**site, "reason": "API_MUTATION_REVIEW"})
            if PR_ACTION.search(uses + "\n" + run):
                unknown.append({"job": str(job_name), "step": number,
                                "reason": "PR_AUTOMATION_REVIEW"})
            if "actions/github-script@" in uses.lower() and writes:
                unknown.append({"job": str(job_name), "step": number,
                                "reason": "DYNAMIC_GITHUB_SCRIPT_WITH_WRITE_PERMISSION"})
    return {
        "name": path.name, "sha256": hashlib.sha256(raw).hexdigest(),
        "write_permissions": sorted(writes),
        "direct_main_push_sites": direct,
        "unreviewed_mutation_sites": unknown,
        "requires_migration": bool(direct),
        "requires_manual_review": bool(writes or direct or unknown),
    }


def inventory(root):
    folder = root / ".github" / "workflows"
    if not folder.is_dir():
        raise AuditError("WORKFLOW_DIRECTORY_MISSING")
    files = sorted(p for p in folder.iterdir()
                   if p.is_file() and p.suffix.lower() in (".yml", ".yaml"))
    if not files:
        raise AuditError("NO_WORKFLOWS")
    rows, errors = [], []
    for path in files:
        try:
            rows.append(analyze(path))
        except (AuditError, OSError) as exc:
            errors.append({"name": path.name, "reason": str(exc)})
    direct = [row for row in rows if row["requires_migration"]]
    unknown = [row for row in rows if row["requires_manual_review"]]
    status = ("HOLD_UNREADABLE_WORKFLOWS" if errors else
              "HOLD_DIRECT_MAIN_WRITERS" if direct else
              "HOLD_WRITABLE_OR_UNREVIEWED" if unknown else
              "PASS_STATIC_NO_WRITERS")
    return {
        "schema": SCHEMA, "status": status,
        "scope": "NASDAQ_GITHUB_WORKFLOW_STATIC_ONLY",
        "auto_fix": False, "ruleset_changed": False,
        "workflow_count": len(files), "scanned_count": len(rows),
        "direct_main_writer_count": len(direct),
        "direct_main_push_sites": sum(len(r["direct_main_push_sites"]) for r in rows),
        "manual_review_count": len(unknown),
        "errors": errors, "workflows": rows,
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        result = inventory(args.root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    except (AuditError, OSError) as exc:
        print("XRAY_A41=BLOCKED:" + str(exc), file=sys.stderr)
        return 2
    print("XRAY_A41=" + result["status"] +
          ";WORKFLOWS=" + str(result["workflow_count"]) +
          ";WRITER_WORKFLOWS=" + str(result["direct_main_writer_count"]) +
          ";PUSH_SITES=" + str(result["direct_main_push_sites"]) +
          ";MANUAL_REVIEW=" + str(result["manual_review_count"]))
    return 0 if result["status"] == "PASS_STATIC_NO_WRITERS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
