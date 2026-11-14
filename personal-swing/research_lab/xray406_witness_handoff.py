"""Plan an Official Witness publish only after independently collected evidence.

This module is deliberately a planner. It does not grant rights, mint tokens,
mutate GitHub, or retry uncertain writes. Evidence comes from trusted GitHub
readbacks and a monotonic caller. Exact ref comparison must be enforced by
the publisher atomically, not by this earlier read.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from xray406_witness_acceptance import (
    ACTIONS_APP, CHECK, SHA, CheckReceipt, check_candidate, require, utc,
)

REPO = "gokaydonmez39-jpg/kripto-radar"
ACTOR = "xray-406-isolated-ci-pilot[bot]"
CI_PATH = ".github/workflows/xray-nasdaq-477-pr-required-readonly.yml"
STAGING_PREFIX = "refs/heads/xray-406-official-witness-staging/"
MAX_AGE = timedelta(minutes=15)


@dataclass(frozen=True)
class RunReceipt:
    repo: str
    head_repo: str
    ref: str
    head: str
    actor: str
    event: str
    workflow: str
    run_id: int
    attempt: int


@dataclass(frozen=True)
class CheckSource:
    check: CheckReceipt
    run_id: int
    attempt: int
    job_id: int
    details_url: str


@dataclass(frozen=True)
class PublishPlan:
    expected: str
    candidate: str
    guard_blob: str
    ledger_blob: str
    latest_observed_at: datetime


def staging_ref(candidate):
    require(isinstance(candidate, str) and SHA.fullmatch(candidate), "INVALID_CANDIDATE")
    return STAGING_PREFIX + candidate


def plan(root, base, head, run, source, stage_head, target_head, now, cutoff):
    generated, guard, ledger = check_candidate(root, base, head)
    require((run.repo, run.head_repo, run.ref, run.head, run.actor, run.event, run.workflow)
            == (REPO, REPO, staging_ref(head), head, ACTOR, "push", CI_PATH),
            "RUN_SCOPE_MISMATCH")
    require(all(type(v) is int and v > 0 for v in (run.run_id, run.attempt, source.job_id))
            and (source.run_id, source.attempt) == (run.run_id, run.attempt)
            and source.details_url == (
                f"https://github.com/{REPO}/actions/runs/{run.run_id}/job/{source.job_id}"
            ), "CHECK_RUN_BINDING_MISMATCH")
    check = source.check
    require((check.head, check.name, check.app_id, check.conclusion)
            == (head, CHECK, ACTIONS_APP, "success"), "EXACT_CI_NOT_VERIFIED")
    require(stage_head == head and target_head == base, "REF_DRIFT_NO_WRITE")
    finished, now, cutoff = map(utc, (check.finished_at, now, cutoff))
    deadline = min(cutoff, generated + MAX_AGE)
    require(generated <= finished <= now < deadline, "PUBLISH_WINDOW_CLOSED")
    return PublishPlan(base, head, guard, ledger, deadline)
