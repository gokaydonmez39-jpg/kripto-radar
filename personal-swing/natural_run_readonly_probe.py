#!/usr/bin/env python3
"""GET-only admission proof for the EXISTING scheduled NASDAQ 477 EOD.

This module NEVER creates Git tags/refs, dispatches a workflow, reads a
market-data provider, accesses private Sheets, issues an order, or notifies
ChatGPT/iOS. An absent/mismatched GitHub source receipt is a failure before
the existing private EOD producer starts. The inactive atomic lease stays
inactive; this proof is necessary but NOT sufficient for FULL_FINAL.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
import json
import os
import sys

import epoch_lease as lease


STATUS = "NATURAL_RUN_GITHUB_READ_ONLY_VERIFIED"
HOLD = "NATURAL_RUN_GITHUB_READ_ONLY_HOLD"


def schedule_runs_path(asof):
    """One tightly scoped GitHub GET for this ASOF and next UTC date.

    The scheduled EOD cannot be authoritative unless it is the sole
    workflow-specific natural run in this bounded date window. In the 10h
    post-close eligibility window, the following session's EOD cannot yet
    have been scheduled. All collisions (including queued/failure) HOLD.
    """
    lease.epoch_tag(asof)
    next_utc=(date.fromisoformat(asof)+timedelta(days=1)).isoformat()
    return ("/actions/workflows/"+lease.WORKFLOW.rsplit("/",1)[-1]+
            "/runs?event=schedule&per_page=100&created="+asof+".."+next_utc)


def verify_unique_natural_epoch(owner, actual, transport):
    """Fail closed if GitHub exposes any duplicate or incomplete run page."""
    try:
        page=transport("GET",schedule_runs_path(owner["asof_et"]))
    except (HTTPError,URLError,TimeoutError,OSError,ValueError,TypeError,KeyError):
        raise lease.LeaseHold("NATURAL_EOD_EPOCH_AMBIGUOUS") from None
    if not isinstance(page,dict):
        raise lease.LeaseHold("NATURAL_EOD_EPOCH_AMBIGUOUS")
    rows=page.get("workflow_runs")
    if (type(page.get("total_count")) is not int or
            page["total_count"]!=1 or type(rows) is not list or len(rows)!=1):
        raise lease.LeaseHold("NATURAL_EOD_EPOCH_AMBIGUOUS")
    listed=rows[0]
    if (not isinstance(listed,dict) or
            type(listed.get("id")) is not int or
            listed["id"]!=owner["run_id"] or
            listed.get("event")!="schedule" or
            listed.get("path")!=lease.WORKFLOW or
            listed.get("head_branch")!="main" or
            listed.get("head_sha")!=owner["source_sha"] or
            listed.get("run_attempt")!=1 or
            not isinstance(listed.get("repository"),dict) or
            listed["repository"].get("full_name")!=lease.REPO or
            listed.get("created_at")!=actual.get("created_at")):
        raise lease.LeaseHold("NATURAL_EOD_EPOCH_AMBIGUOUS")
    return True


def verify_once(runtime, transport, *, now=None, completed_session=None):
    """Validate actual GitHub run identity and epoch uniqueness by TWO GETs.

    Dependency injection is for offline tests; the scheduled CLI uses its
    actual UTC clock, GitHub runner environment and the official XNAS
    session resolver. No success can authorize a private write or delivery.
    """
    lease.require(isinstance(runtime,dict) and callable(transport),
                  "NATURAL_RUN_READ_ONLY_INPUT_INVALID")
    at = now if now is not None else datetime.now(timezone.utc)
    lease.require(isinstance(at,datetime) and at.tzinfo is not None
                  and at.utcoffset() is not None,
                  "NATURAL_RUN_READ_ONLY_CLOCK_INVALID")
    at=at.astimezone(timezone.utc)
    try:
        import daily_job
        asof=(completed_session(at) if completed_session is not None
              else daily_job.current_completed_session(at))
        owner=lease.verified_natural_owner(
            runtime,asof,at,completed_session=completed_session)
    except lease.LeaseHold:
        raise
    except Exception:
        raise lease.LeaseHold("NATURAL_RUN_READ_ONLY_SESSION_UNVERIFIED") from None

    try:
        receipt=transport("GET","/actions/runs/"+str(owner["run_id"]))
    except (HTTPError,URLError,TimeoutError,OSError,ValueError,TypeError,KeyError):
        raise lease.LeaseHold("NATURAL_RUN_READ_ONLY_GET_UNAVAILABLE") from None
    lease.verify_live_natural_run_receipt(owner,receipt,now=at)
    verify_unique_natural_epoch(owner,receipt,transport)
    return {
        "status": STATUS, "asof_et": owner["asof_et"],
        "run_id":owner["run_id"], "source_event":"schedule",
        "writes":0, "orders":False, "lease_issued":False,
        "ab_release_authorized":False, "device_ack":"UNKNOWN",
    }


def main(argv=None):
    """Only --verify is supported, and it performs no mutations."""
    args=sys.argv[1:] if argv is None else argv
    if args!=["--verify"]:
        print(json.dumps({"status":HOLD,"reason_code":"UNSUPPORTED_ACTION",
                          "writes":0,"ab_release_authorized":False}))
        return 3
    runtime=dict(os.environ)
    token=runtime.get("GITHUB_TOKEN","")
    if (runtime.get("GITHUB_REPOSITORY")!=lease.REPO or
            runtime.get("GITHUB_EVENT_NAME")!="schedule" or
            not isinstance(token,str) or not token):
        print(json.dumps({"status":HOLD,"reason_code":"NATURAL_RUN_ENV_UNVERIFIED",
                          "writes":0,"ab_release_authorized":False}))
        return 3
    try:
        result=verify_once(runtime,lease.github_transport(token))
    except Exception:
        # Never log provider exceptions, token, private data or raw bodies.
        print(json.dumps({"status":HOLD,
                          "reason_code":"NATURAL_RUN_RECEIPT_UNVERIFIED",
                          "writes":0,"ab_release_authorized":False,
                          "device_ack":"UNKNOWN"}))
        return 3
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
