"""Classify a Witness write outcome from two matching ref reads and Git objects.

This classifier never publishes or requests a retry. It must be run on evidence
from the actual fixed ref and independently fetched immutable objects.
"""
from dataclasses import dataclass
import subprocess

from xray406_witness_acceptance import GUARD, LEDGER, SHA, check_candidate, git, require

OVERLAY = "nasdaq-xray/canonical_current_final_gate_overlay.json"


@dataclass(frozen=True)
class Verdict:
    status: str
    first_visibility_proven: bool = False
    retry_allowed: bool = False


def _ancestor(root, first, second):
    result = subprocess.run(
        ["git", "--no-replace-objects", "-C", str(root), "merge-base",
         "--is-ancestor", first, second],
        check=False, capture_output=True, timeout=30,
    )
    require(result.returncode in (0, 1), "ANCESTRY_UNAVAILABLE")
    return result.returncode == 0


def _witness_blobs(root, rev):
    return tuple(git(root, "ls-tree", rev, "--", path) for path in (GUARD, LEDGER))


def classify(root, base, candidate, first_ref, second_ref, write_outcome):
    require(write_outcome in ("confirmed_non_fast_forward", "unknown"),
            "OUTCOME_NOT_IN_SCOPE")
    require(all(isinstance(x, str) and SHA.fullmatch(x)
                for x in (base, candidate, first_ref, second_ref)), "INVALID_REF_READ")
    check_candidate(root, base, candidate)
    if first_ref != second_ref:
        return Verdict("HOLD_REF_MOVED_DURING_READBACK")
    observed = second_ref
    if not _ancestor(root, base, observed):
        return Verdict("HOLD_BASE_NOT_ON_TARGET")
    if _ancestor(root, candidate, observed):
        if write_outcome == "confirmed_non_fast_forward":
            return Verdict("HOLD_REJECTION_AND_CANDIDATE_REACHABLE")
        if _witness_blobs(root, candidate) != _witness_blobs(root, observed):
            return Verdict("HOLD_CANDIDATE_REACHABLE_WITNESS_PATHS_MOVED")
        return Verdict("CANDIDATE_REACHABLE_VISIBILITY_UNPROVEN")
    if observed == base:
        return Verdict("HOLD_TARGET_AT_BASE_NO_ACCEPTANCE")
    if _witness_blobs(root, base) != _witness_blobs(root, observed):
        return Verdict("HOLD_CONCURRENT_WITNESS_CHANGE")
    paths = set(git(root, "diff-tree", "--no-commit-id", "--name-only", "-r",
                    "--no-renames", "-z", base, observed).split(b"\0")[:-1])
    if paths == {OVERLAY.encode()} and write_outcome == "confirmed_non_fast_forward":
        return Verdict("HOLD_OVERLAY_ADVANCED_WITNESS_INTACT")
    return Verdict("HOLD_TARGET_ADVANCED_NO_ACCEPTANCE")
