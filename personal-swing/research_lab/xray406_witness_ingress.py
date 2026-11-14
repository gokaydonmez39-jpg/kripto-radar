"""Offline preflight for the proposed first live Witness staging boundary.

The caller must bind the metadata to the same authenticated GitHub scheduled
runner and separately verify the current ref and dedicated App. This module
does not call GitHub, request a credential, or authorize a write.
"""
from dataclasses import dataclass
from datetime import datetime

from xray406_witness_acceptance import GUARD, LEDGER, SHA, check_candidate, git, require, utc
from xray406_witness_handoff import REPO, staging_ref
from xray406_witness_session_window import Window
from xray406_witness_stage import BUDGET

SOURCE_PATH = ".github/workflows/xray-resilience-observability.yml"


@dataclass(frozen=True)
class IngressPlan:
    run_id: int
    asof: str
    base: str
    head: str
    guard_blob: str
    ledger_blob: str
    ref: str
    deadline: datetime


def preflight(root, base, head, run, market_window, now):
    require(isinstance(run, dict) and isinstance(market_window, Window)
            and (run.get("repo"), run.get("ref"), run.get("event"), run.get("path"))
            == (REPO, "refs/heads/main", "schedule", SOURCE_PATH)
            and type(run.get("attempt")) is int and run["attempt"] == 1
            and type(run.get("run_id")) is int and run["run_id"] > 0,
            "NATURAL_SOURCE_SCOPE_NOT_VERIFIED")
    started, now = utc(run.get("started_at")), utc(now)
    require(market_window.closes <= started < market_window.cutoff, "NOT_POST_CLOSE_SOURCE")
    checkout = run.get("checkout")
    require(isinstance(checkout, str) and SHA.fullmatch(checkout)
            and isinstance(base, str) and SHA.fullmatch(base), "SOURCE_BASE_NOT_VERIFIED")
    require(not git(root, "merge-base", "--is-ancestor", checkout, base),
            "SOURCE_BASE_NOT_VERIFIED")
    for path in (GUARD, LEDGER):
        require(git(root, "ls-tree", checkout, "--", path)
                == git(root, "ls-tree", base, "--", path), "SOURCE_INPUT_BLOBS_MOVED")
    generated, guard, ledger = check_candidate(root, base, head)
    require(started <= generated <= now, "SOURCE_GENERATION_ORDER")
    deadline = market_window.publication_deadline(generated)
    require(now + BUDGET < deadline, "INGRESS_WINDOW_CLOSED")
    return IngressPlan(run["run_id"], market_window.session, base, head, guard, ledger,
                       staging_ref(head), deadline)
