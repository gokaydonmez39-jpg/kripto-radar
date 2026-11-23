#!/usr/bin/env python3
"""One-way, schedule-only NASDAQ 477 Git tag FIRST-CLAIM canary.

This is a narrow live experiment on the existing six-job EOD workflow, NOT a
second EOD writer, a retry, a release gate, or proof of private Sheet delivery.
The canonical Google first-claim/write path stays unchanged and authoritative.
No tag/ref POST is possible until the real GitHub runner is independently
verified as the current official XNAS scheduled source. No custom ASOF input.
Never print provider bodies, credentials, symbols, prices, or URLs.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sys

import daily_job
import epoch_lease as lease

SLOT = "XRAY_PERSONAL_477_SCHEDULED_EPOCH_TAG_CANARY_V1"
PASS = "FIRST_CLAIM_READBACK_VERIFIED_NOT_EOD"
HOLD = "CANARY_HOLD_NO_TAG_AUTHORITY"


def run(environment, *, transport=None, now=None, completed_session=None):
    """Only a natural main/schedule/attempt-one EOD may try a first-claim.

    Injected clock/transport/session are exclusively for offline tests.
    A provider conflict, timeout, revoked ruleset or second scheduled run
    never retries either Git POST and never authorizes downstream Sheets.
    """
    lease.require(isinstance(environment, dict), "CANARY_ENV_INVALID")
    at = now if now is not None else datetime.now(timezone.utc)
    lease.require(isinstance(at, datetime) and at.tzinfo is not None and
                  at.utcoffset() is not None, "CANARY_CLOCK_INVALID")
    at = at.astimezone(timezone.utc)
    session = (completed_session(at) if completed_session is not None
               else daily_job.current_completed_session(at))
    lease.require(isinstance(session, str), "CANARY_CURRENT_ASOF_UNVERIFIED")
    owner = lease.verified_natural_owner(
        environment, session, at, completed_session=completed_session)
    # Never call the provider with a missing/forged token. No output of token.
    token = environment.get("GITHUB_TOKEN")
    lease.require(isinstance(token, str) and bool(token),
                  "CANARY_TOKEN_UNAVAILABLE")
    actual = lease.acquire_first_claim(
        owner, transport if transport is not None
        else lease.github_transport(token),
        now=at, runtime_env=environment if now is not None else None)
    lease.require(
        type(actual) is dict and actual.get("state") == PASS and
        actual.get("asof_et") == session and
        actual.get("run_id") == owner["run_id"] and
        actual.get("sheet_writes") == 0 and
        actual.get("orders") is False and
        actual.get("ab_release_authorized") is False and
        actual.get("device_ack") == "UNKNOWN",
        "CANARY_POST_READBACK_INVALID")
    return {
        "schema": SLOT, "status": PASS, "asof_et": session,
        "run_id": owner["run_id"], "git_tag_verified": True,
        "sheet_writes": 0, "orders": False,
        "ab_release_authorized": False, "device_ack": "UNKNOWN",
    }


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    # A runner may not choose an ASOF, enter replay mode or invoke a
    # different Git write endpoint. Always reject unexpected arguments.
    if args != ["--schedule-canary"]:
        print(json.dumps({"schema": SLOT, "status": HOLD,
                          "reason_code": "CANARY_UNSUPPORTED_ACTION",
                          "sheet_writes": 0, "orders": False,
                          "ab_release_authorized": False,
                          "device_ack": "UNKNOWN"}, sort_keys=True))
        return 3
    try:
        result = run(dict(os.environ))
        print(json.dumps(result, sort_keys=True))
    except Exception:
        # Run this advisory canary once, never retry. A failed canary does
        # not conceal/mutate source data or suppress canonical Google CAS.
        # Do not print arbitrary provider/HTTP errors; static state only.
        print(json.dumps({"schema": SLOT, "status": HOLD,
                          "reason_code": "LIVE_PROTECTED_TAG_FIRST_CLAIM_UNVERIFIED",
                          "sheet_writes": 0, "orders": False,
                          "ab_release_authorized": False,
                          "device_ack": "UNKNOWN"}, sort_keys=True))
    # Advisory-only experimental witness: preserve the original six-job
    # EOD production source and its own mandatory fail-closed validation.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
