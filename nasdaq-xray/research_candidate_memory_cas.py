#!/usr/bin/env python3
"""Opt-in CAS writer to isolated XRAY research-memory branch, NEVER main.

This code is inert without explicit XRAY_MEMORY_PERSIST_APPROVED=true on a
successful main workflow_run. It uses only GitHub API metadata and an already
existing accepted research receipt, not market-data providers or broker APIs.
"""
from __future__ import annotations
import argparse
import base64
import binascii
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
    # Two explicit owner-controlled repository vars, including exactly the
    # approved code commit. A future main change disarms persistence again.
    approved=env.get("XRAY_MEMORY_RELEASE_COMMIT_SHA")
    running=env.get("GITHUB_SHA")
    ensure(type(approved) is str and len(approved)==40 and
           all(c in "0123456789abcdef" for c in approved) and
           approved==running,"EXACT_RELEASE_SHA_NOT_APPROVED")
    source=env.get("XRAY_MEMORY_EVENT_SOURCE_RUN_ID")
    ensure(type(source) is str and source.isascii() and
           source.isdecimal() and int(source)>0,
           "TRUSTED_WORKFLOW_EVENT_SOURCE_MISSING")


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
    except (ValueError, binascii.Error) as e:
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


def readonly_delta_from_authenticated_plan(plan):
    """Summarize REAL isolated-branch member/family changes, without writing.

    Caller MUST supply authorized_proposal() output from a verified GitHub
    preimage and separately authenticated same-ASOF receipt. A first snapshot
    is a baseline, not a claim that each ticker is a newly discovered setup.
    """
    ensure(type(plan) is dict and
           plan.get("status") in ("NEW_ACCEPTED_SESSION",
                                  "IDEMPOTENT_NO_CHANGE") and
           type(plan.get("content")) is bytes and
           type(plan.get("old_content")) is bytes and
           type(plan.get("expected_blob_sha")) is str and
           type(plan.get("new_blob_sha")) is str and
           git_blob_sha(plan["old_content"]) == plan["expected_blob_sha"] and
           git_blob_sha(plan["content"]) == plan["new_blob_sha"],
           "DELTA_UNTRUSTED_CAS_PLAN")
    try:
        previous=json.loads(plan["old_content"])
        proposed=json.loads(plan["content"])
    except (ValueError,UnicodeDecodeError) as ex:
        raise ValueError("XRAY_MEMORY_DELTA_INVALID_JSON") from ex
    validate_ledger(previous)
    validate_ledger(proposed)
    before=previous["entries"]
    after=proposed["entries"]
    status=plan["status"]
    if status=="NEW_ACCEPTED_SESSION":
        ensure(len(after)==len(before)+1 and
               after[:-1]==before and
               after[-1]["asof_et"]==plan.get("asof_et") and
               after[-1]["source_run_ids"] and
               after[-1]["prev_entry_sha256"]==
                   (before[-1]["entry_sha256"] if before else "0"*64),
               "DELTA_APPEND_ONLY_EXACT")
        events=after[-1]["watch_events"]
    else:
        ensure(after==before and
               bool(before) and
               before[-1]["asof_et"]==plan.get("asof_et"),
               "DELTA_IDEMPOTENT_NOT_EQUAL")
        events=[]
    present=after[-1]["watch_families"] if after else {}
    prior=before[-1]["watch_families"] if before else {}
    ensure(plan.get("entries")==len(after) and
           plan.get("watch_count")==len(present) and
           plan.get("alpha_authority") is False,
           "DELTA_COUNTER_OR_AUTHORITY")
    kinds={
        "WATCH_FIRST_OBSERVED":[],
        "WATCH_NOT_OBSERVED_IN_NEXT_ACCEPTED_SESSION":[],
        "WATCH_FAMILY_CHANGED":[]}
    for item in events:
        ensure(type(item) is dict and item.get("event") in kinds and
               item.get("reason_authority")==
                   "SYMBOLIC_MEMBERSHIP_DIFF_ONLY" and
               item.get("confirmed_invalidation") is False and
               item.get("r92") is False and item.get("al") is False,
               "DELTA_NO_ALPHA_OR_INFERRED_INVALIDATION")
        kinds[item["event"]].append(item)
    has_previous=bool(before)
    return {
        "schema":"XRAY_RESEARCH_WATCH_DELTA_READONLY_V1",
        "status":("BASELINE_ONLY_NO_PRIOR_SESSION" if not has_previous
                 else status),
        "asof_et":plan["asof_et"],
        "prior_asof_et":before[-1]["asof_et"] if has_previous else None,
        "source_acceptance_run_id":plan["run_id"],
        "prior_ledger_blob_sha":plan["expected_blob_sha"],
        "proposed_ledger_blob_sha":plan["new_blob_sha"],
        "prior_ledger_entry_count":len(before),
        "proposed_ledger_entry_count":len(after),
        "prior_watch_count":len(prior),
        "current_watch_count":len(present),
        "prior_accepted_session_attested":has_previous,
        "newly_observed_since_prior":(
            kinds["WATCH_FIRST_OBSERVED"] if has_previous else []),
        "no_longer_observed_since_prior":
            kinds["WATCH_NOT_OBSERVED_IN_NEXT_ACCEPTED_SESSION"],
        "family_changed_since_prior":kinds["WATCH_FAMILY_CHANGED"],
        "unchanged_symbol_count":(
            sum(prior.get(sym)==present[sym] for sym in present
                if sym in prior) if has_previous else 0),
        "first_snapshot_is_not_delta":not has_previous,
        "raw_market_data_included":False,
        "persistence_executed":False,
        "notification_sent":False,
        "alpha_authority":False,"r92_authority":False,
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,
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
    ensure(run_id==int(os.environ["XRAY_MEMORY_EVENT_SOURCE_RUN_ID"]),
           "EVENT_SOURCE_RUN_ID_MISMATCH")
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
