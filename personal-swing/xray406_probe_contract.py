"""Offline admission contract for the isolated #406 prototype only."""
from __future__ import annotations

import re
from dataclasses import dataclass

REPOSITORY = "gokaydonmez39-jpg/kripto-radar"
STAGING = "xray-406-ci-staging-probe-20261114"
TARGET = "xray-406-writer-probe-20261114"
WORKFLOW = ".github/workflows/xray-nasdaq-477-pr-required-readonly.yml"
CHECK = "xray-477-required-ci"
GITHUB_ACTIONS_APP = 15368
SHA = re.compile(r"[a-f0-9]{40}\Z")


@dataclass(frozen=True)
class Candidate:
    repository: str
    source_branch: str
    target_branch: str
    candidate_sha: str
    observed_source_sha: str
    expected_target_sha: str
    observed_target_sha: str
    merge_base_sha: str


def admission(candidate: Candidate, run: dict, checks: list[dict]) -> str:
    """Admit only a current fast-forward carrying its own real green CI."""
    if (candidate.repository, candidate.source_branch, candidate.target_branch) != (
        REPOSITORY, STAGING, TARGET
    ):
        return "SCOPE_REFUSED"
    refs = (
        candidate.candidate_sha,
        candidate.observed_source_sha,
        candidate.expected_target_sha,
        candidate.observed_target_sha,
        candidate.merge_base_sha,
    )
    if any(not isinstance(value, str) or not SHA.fullmatch(value) for value in refs):
        return "INVALID_SHA"
    if candidate.candidate_sha != candidate.observed_source_sha:
        return "STAGING_HEAD_CHANGED"
    if candidate.expected_target_sha != candidate.observed_target_sha:
        return "TARGET_HEAD_CHANGED"
    if candidate.candidate_sha == candidate.expected_target_sha:
        return "ALREADY_AT_CANDIDATE"
    if candidate.merge_base_sha != candidate.expected_target_sha:
        return "NOT_FAST_FORWARD"
    if (
        run.get("head_sha") != candidate.candidate_sha
        or run.get("head_branch") != STAGING
        or run.get("path") != WORKFLOW
        or run.get("event") != "push"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or (run.get("repository") or {}).get("full_name") != REPOSITORY
        or (run.get("head_repository") or {}).get("full_name") != REPOSITORY
    ):
        return "WORKFLOW_NOT_VERIFIED"
    matches = [item for item in checks if item.get("name") == CHECK]
    if len(matches) != 1:
        return "CHECK_MISSING_OR_AMBIGUOUS"
    item = matches[0]
    if (
        item.get("head_sha") != candidate.candidate_sha
        or item.get("status") != "completed"
        or item.get("conclusion") != "success"
        or (item.get("app") or {}).get("id") != GITHUB_ACTIONS_APP
    ):
        return "CHECK_NOT_VERIFIED"
    return "ALLOW_ISOLATED_FAST_FORWARD"


def require_fixture(value: str) -> None:
    if value != "PASS\n":
        raise ValueError("XRAY_406_PROBE_FIXTURE_REJECTED")
