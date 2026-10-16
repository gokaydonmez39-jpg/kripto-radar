#!/usr/bin/env python3
"""Fail-closed GitHub Actions admission for a research-only memory proposal.

GitHub API metadata MUST be fetched with an authenticated token by caller,
and the named artifact MUST be downloaded by `gh run download -n` from that
exact API-verified run. Metadata and receipt alone are insufficient as market
facts; the trusted main workflow performs independent three-artifact proof.
No GitHub writes, vendor API calls, market prices, or execution.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import re

from research_candidate_memory import ensure, verify_receipt

REPO = "gokaydonmez39-jpg/kripto-radar"
WORKFLOW = ".github/workflows/xray-research-operations-acceptance.yml"
ARTIFACT = "xray-personal-research-operations-exact-receipt-no-al"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


def iso_utc(s):
    ensure(type(s) is str, "RUN_TIMESTAMP_TYPE")
    try:
        x = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as ex:
        raise ValueError("XRAY_MEMORY_RUN_TIMESTAMP_INVALID") from ex
    ensure(x.tzinfo is not None and x.utcoffset() == dt.timedelta(0),
           "RUN_TIMESTAMP_UTC")
    return x


def admit(run, receipt, *, expected_asof, artifact=None,
          expected_run_id=None, now_utc=None):
    """Return immutable run provenance only AFTER binding to a trusted run.

    Note: full trust assumes actual `gh api`/`gh run download` performed by
    the pinned CI job, never user-provided simulated run JSON in production.
    """
    ensure(type(run) is dict, "RUN_TYPE")
    ensure(run.get("name") ==
           "XRAY Research Operations Cross-Artifact Acceptance (No AL)",
           "RUN_NAME")
    ensure(run.get("path") == WORKFLOW, "RUN_WORKFLOW")
    ensure(run.get("status") == "completed" and
           run.get("conclusion") == "success", "RUN_NOT_COMPLETE_SUCCESS")
    ensure(run.get("head_branch") == "main" and
           (run.get("head_repository") or {}).get("full_name") == REPO,
           "RUN_BRANCH_OR_REPOSITORY")
    ensure(run.get("repository", {}).get("full_name") == REPO,
           "RUN_REPOSITORY")
    sha = run.get("head_sha")
    ensure(type(sha) is str and SHA40.fullmatch(sha) is not None,
           "RUN_HEAD_SHA")
    run_id = run.get("id")
    ensure(type(run_id) is int and run_id > 0, "RUN_ID")
    if expected_run_id is not None:
        ensure(type(expected_run_id) is int and expected_run_id == run_id,
               "RUN_ID_EVENT_MISMATCH")
    started = iso_utc(run.get("created_at"))
    updated = iso_utc(run.get("updated_at"))
    ensure(updated >= started, "RUN_NEGATIVE_DURATION")
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    ensure(now.tzinfo is not None and now.utcoffset() == dt.timedelta(0)
           and updated <= now + dt.timedelta(minutes=2),
           "RUN_IN_FUTURE")
    ensure(type(expected_asof) is str, "EXPECTED_ASOF")
    asof, families = verify_receipt(receipt)
    ensure(asof == expected_asof, "WRONG_OFFICIAL_COMPLETED_SESSION")
    # Completed source itself must postdate the EOD observation by design.
    ensure(updated.date().isoformat() >= asof, "ACCEPTANCE_BEFORE_ASOF")
    if artifact is not None:
        ensure(type(artifact) is dict and
               artifact.get("name") == ARTIFACT and
               artifact.get("expired") is False and
               type(artifact.get("id")) is int and artifact["id"] > 0 and
               type(artifact.get("size_in_bytes")) is int and
               0 < artifact["size_in_bytes"] <= 1048576 and
               artifact.get("workflow_run", {}).get("id") == run_id,
               "ARTIFACT_METADATA_UNTRUSTED")
    return {
        "status": "AUTHENTICATED_MAIN_WORKFLOW_RECEIPT_RESEARCH_ONLY",
        "run_id": run_id, "run_head_sha": sha,
        "artifact_name": ARTIFACT,
        "asof_et": asof, "symbolic_watch_count": len(families),
        "execution": "NONE", "real_money": "NO-GO",
        "registered_r92": 0, "iphone_receipt_attested": False,
        "alpha_authority": False,
        "authentication_scope": "GITHUB_API_METADATA_AND_EXACT_RUN_ARTIFACT",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True, type=Path)
    p.add_argument("--artifact", required=True, type=Path)
    p.add_argument("--receipt", required=True, type=Path)
    p.add_argument("--asof", required=True)
    p.add_argument("--run-id", required=True, type=int)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    sources = [a.run, a.artifact, a.receipt]
    ensure(a.out.resolve() not in [x.resolve() for x in sources],
           "SOURCE_OVERWRITE_FORBIDDEN")
    run = json.loads(a.run.read_text())
    artifact = json.loads(a.artifact.read_text())
    receipt = json.loads(a.receipt.read_text())
    report = admit(run, receipt, expected_asof=a.asof,
                   artifact=artifact, expected_run_id=a.run_id)
    a.out.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
