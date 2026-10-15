#!/usr/bin/env python3
"""Validate actual GitHub production SIP upstream lineage for read-only WATCH.

The SIP producer legitimately runs from push, schedule, dispatch OR
workflow_run. A consumer must verify its *identity*, branch, sha, success,
and origin -- never merely guess that a workflow_run producer is invalid.
"""
from __future__ import annotations
import argparse
import re

SOURCE_WORKFLOW = "XRAY Personal Full-Universe SIP EOD Coverage (Research Only)"
SOURCE_PATH = ".github/workflows/xray-personal-full-universe-sip-coverage.yml"
ALLOWED_EVENTS = frozenset(("push", "schedule", "workflow_dispatch", "workflow_run"))

def need(ok, code):
    if not ok:
        raise ValueError("XRAY_EARLY_WATCH_UPSTREAM_" + code)

def verify_run(run, repo, *, expected_run_id, expected_head_sha):
    """Return only a verified upstream run ID, never trading permission."""
    need(type(run) is dict and type(repo) is str and
         re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) is not None,
         "INPUT")
    need(type(expected_run_id) is int and expected_run_id > 0 and
         type(expected_head_sha) is str and
         re.fullmatch(r"[a-f0-9]{40}", expected_head_sha) is not None,
         "BOUND_RUN_SHA")
    need(type(run.get("id")) is int and run["id"] == expected_run_id,
         "RUN_ID_MISMATCH")
    need(run.get("head_sha") == expected_head_sha,
         "HEAD_SHA_MISMATCH")
    need(run.get("name") == SOURCE_WORKFLOW and
         run.get("path") == SOURCE_PATH,
         "EXACT_SOURCE_WORKFLOW")
    need(run.get("head_branch") == "main" and
         run.get("event") in ALLOWED_EVENTS and
         run.get("status") == "completed" and
         run.get("conclusion") == "success",
         "TRUSTED_MAIN_SUCCESS_ONLY")
    need(type(run.get("repository")) is dict and
         run["repository"].get("full_name") == repo and
         type(run.get("head_repository")) is dict and
         run["head_repository"].get("full_name") == repo,
         "REPO_OR_FORK")
    return expected_run_id

def selftest():
    from copy import deepcopy
    sha = "a" * 40
    repo = "gokaydonmez39-jpg/kripto-radar"
    common = {
        "id": 38822127532, "head_sha": sha, "name": SOURCE_WORKFLOW,
        "path": SOURCE_PATH, "head_branch": "main",
        "status": "completed", "conclusion": "success",
        "repository": {"full_name":repo},
        "head_repository": {"full_name":repo},
    }
    for event in sorted(ALLOWED_EVENTS):
        good = dict(common, event=event)
        need(verify_run(good,repo,expected_run_id=38822127532,
                        expected_head_sha=sha)==38822127532,
             "VALID_UPSTREAM_REJECTED_"+event)
    base = dict(common,event="workflow_run")
    cases = [
        ("id mismatch",lambda x:x.update(id=123)),
        ("sha mismatch",lambda x:x.update(head_sha="b"*40)),
        ("wrong workflow",lambda x:x.update(name="Research Source Spoof")),
        ("wrong path",lambda x:x.update(path=".github/workflows/fake.yml")),
        ("fork source",lambda x:x["head_repository"].update(full_name="other/repo")),
        ("repo mismatch",lambda x:x["repository"].update(full_name="other/repo")),
        ("not main",lambda x:x.update(head_branch="dev")),
        ("not completed",lambda x:x.update(status="in_progress")),
        ("failed",lambda x:x.update(conclusion="failure")),
        ("skipped",lambda x:x.update(conclusion="skipped")),
        ("PR invocation",lambda x:x.update(event="pull_request")),
        ("missing sha",lambda x:x.pop("head_sha")),
        ("missing origin",lambda x:x.pop("head_repository")),
    ]
    for name,mutate in cases:
        broken=deepcopy(base)
        mutate(broken)
        try:
            verify_run(broken,repo,expected_run_id=38822127532,
                       expected_head_sha=sha)
        except ValueError:
            continue
        raise AssertionError("FORGED_UPSTREAM_ACCEPTED_"+name)
    print("XRAY_EARLY_WATCH_LINEAGE=PASS_4_PRODUCER_EVENTS_13_FORGED_NEGATIVES_NO_AL")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    args=ap.parse_args()
    if args.selftest:
        selftest()
    else:
        ap.error("This module is an explicit, local validation library; pass --selftest")

if __name__=="__main__":
    main()
