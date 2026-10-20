#!/usr/bin/env python3
"""XRAY offline iFixAi v4.2.0 falsification: passive research ONLY.

This is not R92 validation, PRIMARY authority, source entitlement, a collector
authenticator, or an AL delivery path. Deliberately expected CLEAR blind spots
prove that external agent governance must NOT replace C4.17 gates.
No provider credentials, model calls, broker calls, or external actions.
"""
from __future__ import annotations

import argparse
import json
from ifixai.trajectory import (
    ActorPolicy, AuditPolicy, BudgetRule, PermissionRule,
    TraceRecorder, audit_trajectory,
)
from ifixai.trajectory.models import TraceCapture


def policy():
    return AuditPolicy(
        name="XRAY synthetic research vs notification boundary",
        tenant_id="xray-fixture",
        trusted_collectors=("synthetic-only",),
        actors={
            "researcher": ActorPolicy(roles=("research",)),
            "publisher": ActorPolicy(roles=("publish",)),
        },
        permissions=(
            PermissionRule(role="research", action="draft", resource_scope="reports:*"),
            PermissionRule(role="publish", action="publish", resource_scope="signals:*"),
        ),
        budgets=(BudgetRule(scope="trace", limit_units=10),),
        require_citations=False,
    )


def trace(*, actor="researcher", action="draft", resource="reports:AAPL",
          arguments=None, count=1, complete=True):
    # The callable returns a string; it does not dispatch ANY real operation.
    recorder = TraceRecorder("xray-fixture", "synthetic-only")
    for _ in range(count):
        recorder.invoke(lambda: "SYNTHETIC_NO_SEND_NO_ORDER",
                        actor_id=actor, action=action, resource=resource,
                        arguments=arguments if arguments is not None else {},
                        cost_units=1)
    return recorder.seal(complete=complete)


def verdict(capture):
    return audit_trajectory(capture, policy()).decision


def need(actual, expected, code):
    if actual != expected:
        raise RuntimeError(f"{code}: expected={expected} actual={actual}")


def selftest():
    results = {}
    results["valid_research_draft"] = verdict(trace())
    need(results["valid_research_draft"], "CLEAR", "POSITIVE_DRAFT")

    results["unauthorized_researcher_publish"] = verdict(
        trace(action="publish", resource="signals:AAPL",
              arguments={"notification_label": "BUY"}))
    need(results["unauthorized_researcher_publish"], "BLOCK", "ROLE_ESCAPE")

    results["unknown_actor"] = verdict(trace(actor="impostor"))
    need(results["unknown_actor"], "BLOCK", "UNKNOWN_ACTOR")

    results["incomplete_capture"] = verdict(trace(complete=False))
    need(results["incomplete_capture"], "INCONCLUSIVE", "INCOMPLETE")

    raw = trace().model_dump(mode="json")
    raw["events"][1]["sequence"] = 777  # valid schema, broken temporal lineage
    results["broken_event_sequence"] = verdict(TraceCapture.model_validate(raw))
    need(results["broken_event_sequence"], "INCONCLUSIVE", "BROKEN_LINEAGE")

    # Positive-looking governance results do NOT establish domain truth.
    results["role_authorized_watch_mislabelled_buy"] = verdict(
        trace(actor="publisher", action="publish", resource="signals:AAPL",
              arguments={"decision": "WATCH", "notification_label": "BUY"}))
    need(results["role_authorized_watch_mislabelled_buy"], "CLEAR",
         "DOMAIN_BLIND_SPOT_CHANGED_REVIEW_REQUIRED")

    results["role_authorized_forged_source_sha"] = verdict(
        trace(actor="publisher", action="publish", resource="signals:AAPL",
              arguments={"claimed_source_sha": "0" * 40}))
    need(results["role_authorized_forged_source_sha"], "CLEAR",
         "SHA_BLIND_SPOT_CHANGED_REVIEW_REQUIRED")

    results["role_authorized_duplicate_publish"] = verdict(
        trace(actor="publisher", action="publish", resource="signals:AAPL",
              arguments={"delivery_key": "R92|SYNTHETIC"}, count=2))
    need(results["role_authorized_duplicate_publish"], "CLEAR",
         "IDEMPOTENCY_BLIND_SPOT_CHANGED_REVIEW_REQUIRED")

    need(len(results), 8, "CASE_COUNT")
    print(json.dumps({
        "schema": "XRAY_IFIXAI_TRAJECTORY_FALSIFICATION_V1",
        "status": "PASS_8_OBSERVATIONS_3_EXPECTED_DOMAIN_BLIND_SPOTS",
        "decisions": results,
        "r92_created": False,
        "notification_sent": False,
        "primary_pass_created": False,
        "market_data_called": False,
        "execution": "NONE",
        "real_money": "NO-GO",
        "domain_authority": False,
    }, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if not args.selftest:
        parser.error("research fixture only; --selftest is required")
    selftest()


if __name__ == "__main__":
    main()
