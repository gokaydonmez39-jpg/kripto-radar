#!/usr/bin/env python3
"""Offline opening-readiness fan-in regression; no provider, broker or GitHub IO.

An upstream burst cannot cancel an executing preopen proof. Queued successors
must be checked against current main after all source audits and before any
release-looking public evidence artifact is uploaded.
"""
from __future__ import annotations

from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parent.parent
            / ".github/workflows/xray-preopen-source-audit.yml")


def need(ok: bool, name: str) -> None:
    if not ok:
        raise ValueError("XRAY_PREOPEN_FANIN_" + name)


def check(raw: str) -> None:
    need(isinstance(raw, str) and raw.count("\nconcurrency:\n") == 1
         and raw.count("\njobs:\n") == 1, "WORKFLOW_STRUCTURE")
    triggers, tail = raw.split("\nconcurrency:\n", 1)
    concurrency, jobs = tail.split("\njobs:\n", 1)
    need("xray-preopen-source-audit-v1-" in concurrency
         and "github.event_name == 'pull_request'" in concurrency
         and "github.event.pull_request.number || 'production'" in concurrency,
         "PR_PRODUCTION_ISOLATION")
    need("cancel-in-progress: false" in concurrency
         and "cancel-in-progress: true" not in concurrency
         and "queue: max" in concurrency, "NONPREEMPTIVE_ONE_SUCCESSOR")
    need("\n  schedule:\n" in triggers
         and all(x in triggers for x in (
             'cron: "5 12 * * 1-5"', 'cron: "25 12 * * 1-5"',
             'cron: "5 13 * * 1-5"', 'cron: "15 13 * * 1-5"',
             'cron: "15 14 * * 1-5"')), "EXISTING_PREOPEN_SCHEDULE")
    need("  workflow_run:\n" in triggers
         and all(x in triggers for x in (
             '"XRAY Canonical Current Pre-MC Factory"',
             '"XRAY Canonical Current Post-MC Factory"',
             '"XRAY Canonical Current Final Factory"')),
         "UPSTREAM_FANIN")
    need("  pull_request:\n" in triggers
         and '"nasdaq-xray/preopen_fanin_nonpreemptive_selftest.py"' in triggers,
         "PR_OFFLINE_CI_ENABLED")
    need(jobs.count("  preopen-fanin-offline:\n") == 1
         and jobs.count("  audit:\n") == 1,
         "SEPARATE_PRODUCTION_AND_TEST_JOBS")
    offline, prod = jobs.split("  audit:\n", 1)
    need("if: github.event_name == 'pull_request'" in offline
         and "python -O nasdaq-xray/preopen_fanin_nonpreemptive_selftest.py" in offline
         and "python nasdaq-xray/preopen_fanin_nonpreemptive_selftest.py" in offline,
         "PR_TEST_REGRESSIONS")
    need("secrets." not in offline and "urllib" not in offline
         and "run: python nasdaq-xray/official_source_guard.py" not in offline,
         "NO_PROVIDER_ON_PR")
    need("if: github.event_name != 'pull_request'" in prod,
         "PRODUCTION_DOES_NOT_RUN_ON_PR")
    # A start-only HEAD check can become stale during long CI fan-in.
    need('now_main="$(git ls-remote origin refs/heads/main | cut -f1)"' in prod
         and 'if [[ "$now_main" != "$XRAY_EXPECTED_SHA" ]]; then' in prod,
         "START_MAIN_SHA_GUARD")
    verified = prod.find("      - name: Current NASDAQ official preopen truth report")
    fence = prod.find("      - name: Fence completed preopen audit to still-current main before artifact publication")
    upload = prod.find("      - name: Upload public operational counts only")
    need(0 <= verified < fence < upload, "PUBLISH_GUARD_ORDER")
    fence_step = prod[fence:upload]
    need("id: publish" in fence_step
         and 'actual_main="$(git ls-remote origin refs/heads/main | cut -f1)"' in fence_step
         and 'if [[ "$actual_main" != "$GITHUB_SHA" ]]; then' in fence_step
         and 'echo "current=false" >> "$GITHUB_OUTPUT"' in fence_step
         and 'echo "current=true" >> "$GITHUB_OUTPUT"' in fence_step,
         "SECOND_MAIN_SHA_GUARD")
    upload_step = prod[upload:]
    need("if: steps.epoch_guard.outputs.valid == 'true' && steps.publish.outputs.current == 'true'" in upload_step,
         "STALE_RELEASE_UPLOAD_SUPPRESSED")
    need("XRAY_PREOPEN_PUBLISH_CURRENT_MAIN_SHA=PASS_NO_ALPHA_AUTHORITY" in fence_step,
         "NO_FALSE_ALPHA_CLAIM")


def selftest() -> None:
    import re
    raw = WORKFLOW.read_text(encoding="utf-8")
    check(raw)
    negatives = (
        ("CANCEL", "cancel-in-progress: false", "cancel-in-progress: true"),
        ("QUEUE", "queue: max", "queue: 0"),
        ("PR_COLLISION", "github.event.pull_request.number || 'production'",
         "'production'"),
        ("UPSTREAM", '"XRAY Canonical Current Pre-MC Factory"',
         '"Unrelated Synthetic Pipeline"'),
        ("PREOPEN_CRON", 'cron: "15 14 * * 1-5"',
         'cron: "0 0 * * 0"'),
        ("PR_AUDIT", "if: github.event_name != 'pull_request'",
         "if: github.event_name == 'pull_request'"),
        ("START_SHA", 'if [[ "$now_main" != "$XRAY_EXPECTED_SHA" ]]; then',
         'if [[ "$now_main" == "$XRAY_EXPECTED_SHA" ]]; then'),
        ("SECOND_SHA", 'if [[ "$actual_main" != "$GITHUB_SHA" ]]; then',
         'if [[ "$actual_main" == "$GITHUB_SHA" ]]; then'),
        ("SUPPRESS", "steps.publish.outputs.current == 'true'",
         "steps.publish.outputs.current != 'true'"),
        ("DELETION", 'echo "current=false" >> "$GITHUB_OUTPUT"',
         'echo "stale=true" >> "$GITHUB_OUTPUT"'),
    )
    for label,old,new in negatives:
        need(raw.count(old)==1,"FIXTURE_ANCHOR_"+label)
        changed=raw.replace(old,new,1)
        try:check(changed)
        except ValueError:pass
        else:raise AssertionError("FALSE_GREEN_PREOPEN_FANIN_"+label)
    print("XRAY_PREOPEN_FANIN=PASS_NONPREEMPTIVE_QUEUE_MAIN_SHA_DOUBLE_FENCE_10_NEGATIVES_NO_HTTP_NO_R92")


if __name__ == "__main__":
    selftest()
