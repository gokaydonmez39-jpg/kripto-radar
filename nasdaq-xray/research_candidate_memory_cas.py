#!/usr/bin/env python3
"""Opt-in CAS writer to isolated XRAY research-memory branch, NEVER main.

This code is inert without explicit XRAY_MEMORY_PERSIST_APPROVED=true on a
successful main workflow_run. It uses only GitHub API metadata and an already
existing accepted research receipt, not market-data providers or broker APIs.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from research_candidate_memory import (canonical, ensure, propose,
                                      validate_ledger, sha)
from research_candidate_memory_admission import (
    REPO, WORKFLOW, ARTIFACT, admit)

BRANCH = "xray-research-memory-state"
PATH = "nasdaq-xray/research/symbolic_candidate_memory_ledger_v1.json"
MAX_LEDGER_BYTES = 512 * 1024


def check_authorization(env):
    ensure(env.get("XRAY_MEMORY_PERSIST_APPROVED") == "true",
           "EXPLICIT_OPT_IN_NOT_ENABLED")
    ensure(env.get("GITHUB_EVENT_NAME") == "workflow_run" and
           env.get("GITHUB_REF") == "refs/heads/main" and
           env.get("GITHUB_REPOSITORY") == REPO,
           "MAIN_WORKFLOW_RUN_ONLY")
    ensure(type(env.get("GH_TOKEN")) is str and bool(env.get("GH_TOKEN")),
           "GITHUB_API_CREDENTIAL_MISSING")


def git_blob_sha(content):
    return hashlib.sha1(
        b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    ).hexdigest()


def verified_file_response(obj):
    ensure(type(obj) is dict and obj.get("type") == "file" and
           obj.get("path") == PATH and
           obj.get("encoding") == "base64" and
           type(obj.get("content")) is str and
           type(obj.get("sha")) is str, "PERSISTED_LEDGER_METADATA")
    try:
        raw = base64.b64decode(obj["content"].replace("\n", ""),
                               validate=True)
    except ValueError as e:
        raise ValueError("XRAY_MEMORY_INVALID_GITHUB_B64") from e
    ensure(git_blob_sha(raw) == obj["sha"], "GITHUB_BLOB_SHA_DRIFT")
    ensure(len(raw) < MAX_LEDGER_BYTES, "LEDGER_SIZE_LIMIT")
    try:
        ledger = json.loads(raw)
    except (ValueError,UnicodeDecodeError) as e:
        raise ValueError("XRAY_MEMORY_GITHUB_LEDGER_JSON") from e
    validate_ledger(ledger)
    return raw, ledger


def authorized_proposal(run, artifact, receipt, live_file, *,
                        current_asof, expected_run_id):
    """Pure CAS plan. No I/O, no orders; rejects revision and epoch drift."""
    report = admit(run,receipt,expected_asof=current_asof,
                   artifact=artifact,expected_run_id=expected_run_id)
    old, ledger = verified_file_response(live_file)
    output, status = propose(ledger, receipt)
    ensure(output["alpha_authority"] is False and
           output["execution"] == "NONE" and
           output["real_money"] == "NO-GO", "OUTPUT_AUTHORITY")
    raw = canonical(output) + b"\n"
    ensure(len(raw) < MAX_LEDGER_BYTES, "OUTPUT_LEDGER_SIZE_LIMIT")
    return {
        "status": status,
        "expected_blob_sha": live_file["sha"],
        "new_blob_sha": git_blob_sha(raw),
        "content": raw,
        "old_content": old,
        "run_id": report["run_id"],
        "asof_et": report["asof_et"],
        "watch_count": report["symbolic_watch_count"],
        "entries": len(output["entries"]),
        "alpha_authority": False,
    }


def gh_api(path, payload=None):
    cmd = ["gh", "api", path]
    if payload is not None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/"request.json"
            p.write_bytes(canonical(payload))
            cmd = ["gh", "api", "-X", "PUT", path, "--input", str(p)]
            return json.loads(subprocess.check_output(
                cmd,text=True,stderr=subprocess.PIPE,timeout=50))
    return json.loads(subprocess.check_output(
        cmd,text=True,stderr=subprocess.PIPE,timeout=50))


def obtain_exact_main_receipt(run_id):
    run = gh_api(f"repos/{REPO}/actions/runs/{run_id}")
    listing = gh_api(f"repos/{REPO}/actions/runs/{run_id}/artifacts")
    matches = [x for x in listing.get("artifacts",[])
               if x.get("name") == ARTIFACT and x.get("expired") is False]
    ensure(len(matches)==1, "ARTIFACT_NOT_UNIQUE_OR_EXPIRED")
    with tempfile.TemporaryDirectory() as td:
        subprocess.check_output([
            "gh","run","download",str(run_id),"--repo",REPO,
            "-n",ARTIFACT,"-D",td
        ],text=True,stderr=subprocess.PIPE,timeout=70)
        files=list(Path(td).rglob("*.json"))
        ensure(len(files)==1, "ARTIFACT_FILE_CARDINALITY")
        receipt=json.loads(files[0].read_text(encoding="utf-8"))
    return run,matches[0],receipt


def execute(*, expected_asof, run_id):
    check_authorization(os.environ)
    ensure(type(run_id) is int and run_id>0, "RUN_ID_TYPE")
    run,artifact,receipt = obtain_exact_main_receipt(run_id)
    readpath = f"repos/{REPO}/contents/{PATH}?ref={BRANCH}"
    first = gh_api(readpath)
    plan = authorized_proposal(run,artifact,receipt,first,
                               current_asof=expected_asof,
                               expected_run_id=run_id)
    if plan["status"]=="IDEMPOTENT_NO_CHANGE":
        return {"status":"IDEMPOTENT_NO_COMMIT","entries":plan["entries"],
                "execution":"NONE","real_money":"NO-GO","alpha":False}
    # Double read before the ONE write. Github contents API sha enforces CAS
    # on this dedicated target path, without force-push or updating main.
    second = gh_api(readpath)
    ensure(second.get("sha")==plan["expected_blob_sha"] and
           verified_file_response(second)[0]==plan["old_content"],
           "CONCURRENT_PREIMAGE_CHANGED_NO_WRITE")
    payload = {
        "message": "chore(xray-memory): append exact accepted symbolic EOD "
                   +expected_asof+" no AL",
        "content": base64.b64encode(plan["content"]).decode("ascii"),
        "sha": plan["expected_blob_sha"],
        "branch": BRANCH,
    }
    response = gh_api(f"repos/{REPO}/contents/{PATH}",payload=payload)
    ensure(response.get("content",{}).get("sha")==plan["new_blob_sha"],
           "COMMIT_RESPONSE_BLOB_MISMATCH")
    actual = gh_api(readpath)
    ensure(actual.get("sha")==plan["new_blob_sha"] and
           verified_file_response(actual)[0]==plan["content"],
           "POST_COMMIT_READBACK_MISMATCH")
    return {"status":"CAS_COMMIT_EXACT_READBACK_PASS",
            "branch":BRANCH,"path":PATH,
            "commit_sha":response.get("commit",{}).get("sha"),
            "source_run_id":run_id,"asof_et":expected_asof,
            "entries":plan["entries"],"watch_count":plan["watch_count"],
            "execution":"NONE","real_money":"NO-GO","alpha":False,
            "main_branch_modified":False,"iphone_receipt_attested":False}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--asof",required=True)
    p.add_argument("--run-id",type=int,required=True)
    args=p.parse_args()
    print(json.dumps(execute(expected_asof=args.asof,run_id=args.run_id),
                     sort_keys=True))


if __name__ == "__main__":
    main()
