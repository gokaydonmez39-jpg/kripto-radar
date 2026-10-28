#!/usr/bin/env python3
"""A20: deterministic, read-only START attestor for the *personal* NASDAQ radar.

A GitHub event chain GO is not alpha, broker execution, SIP price coverage,
a validated iPhone receipt, or proof that the next finished EOD has run.
All API reads are public-repository metadata, never private market records.
"""
from __future__ import annotations
from datetime import datetime
import json
import os
import sys
from urllib.request import Request, urlopen

REPO = "gokaydonmez39-jpg/kripto-radar"
RUNS = {
    "eod": 40668287074,
    "a14": 40668438065,
    "private_readback": 40667234654,
    "resilience": 40660732531,
}
RULESET = 26024575
RUN_NAMES = {
    "eod": "XRAY Personal 477 EOD Daily Health (Research Only)",
    "a14": "XRAY Personal NASDAQ A14 Private Evidence Shadow (No Trades)",
    "private_readback": "XRAY Personal NASDAQ A14 Private Evidence Shadow (No Trades)",
    "resilience": "XRAY Resilience + Official Witnesses",
}
# Scientific attribution is a set of analytical checks, not a claim of
# scientists' endorsement or of independently demonstrated alpha.
SCIENTIFIC_AXES = (
    ("Einstein", "Separate data-source failures from strategy failures"),
    ("Euler", "477-universe completeness and bounded computational work"),
    ("Gauss", "Missingness, variance and uncertainty before inference"),
    ("Newton", "Observable dated GitHub evidence before GO"),
    ("Leibniz", "Immutable policy and scope invariants"),
    ("Turing", "Deterministic ordinary and optimized regression tests"),
    ("Shannon", "IEX single-exchange signal/noise provenance distinction"),
    ("Bayes", "Never treat zero matured trades as positive posterior proof"),
    ("Popper", "Counterexamples and independent negative tests"),
    ("Feynman", "EOD to private readback to science traceability"),
    ("Lamport", "GitHub event origin, commit and temporal consistency"),
    ("Deming", "Repeatable CI and private source quality control"),
    ("Kahneman", "Block overconfidence from passing synthetic tests"),
    ("Thorp", "Separate theoretical stop/target from real fills and costs"),
    ("Simons", "Pre-registration, benchmark and unseen holdout required"),
    ("Taleb", "Gap, double-touch and left-tail risk remains monitored"),
)


class FinalGateError(ValueError):
    pass


def need(condition, code):
    if not condition:
        raise FinalGateError(code)


def _completed(item, name, event):
    return (type(item) is dict and item.get("name") == name and
            item.get("event") == event and item.get("status") == "completed" and
            item.get("conclusion") == "success" and
            type(item.get("id")) is int)


def _job_success(jobs, name):
    return (type(jobs) is list and
            len([j for j in jobs if type(j) is dict and j.get("name") == name]) == 1 and
            next(j for j in jobs if type(j) is dict and j.get("name") == name
                 ).get("conclusion") == "success")


def final_gate(bundle):
    """Report independent operational START and statistical alpha release."""
    need(type(bundle) is dict, "BAD_EVIDENCE_BUNDLE")
    need(set(bundle) == {"branch", "ruleset", "runs", "jobs"},
         "BAD_EVIDENCE_KEYS")
    branch, rules, runs, jobs = (bundle["branch"], bundle["ruleset"],
                                bundle["runs"], bundle["jobs"])
    need(type(runs) is dict and set(runs) == set(RUNS), "RUN_EVIDENCE_INCOMPLETE")
    need(type(jobs) is dict and set(jobs) == set(RUNS), "JOB_EVIDENCE_INCOMPLETE")
    need(type(branch) is dict and type(rules) is dict, "SECURITY_EVIDENCE_MISSING")
    eod, a14, readback, resilience = (runs[k] for k in RUNS)
    checks = {
        "main_protected": branch.get("name") == "main" and branch.get("protected") is True,
        "no_force_push_or_delete": (rules.get("enforcement") == "active" and
                                    {z.get("type") for z in rules.get("rules", [])
                                     if type(z) is dict} >= {"deletion", "non_fast_forward"}),
        "eod_workflow_completed": _completed(eod, RUN_NAMES["eod"], "push") and
                                  eod.get("id") == RUNS["eod"],
        "a14_triggered_by_eod": _completed(a14, RUN_NAMES["a14"], "workflow_run") and
                                a14.get("id") == RUNS["a14"] and
                                a14.get("head_sha") == eod.get("head_sha") and
                                type(a14.get("head_sha")) is str and
                                len(a14["head_sha"]) == 40,
        "private_real_source_readback": (
            _completed(readback, RUN_NAMES["private_readback"], "push") and
            readback.get("id") == RUNS["private_readback"] and
            _job_success(jobs["private_readback"], "private-one-time-real-source-readback")),
        "resilience_persist_recovered": (
            _completed(resilience, RUN_NAMES["resilience"], "schedule") and
            resilience.get("id") == RUNS["resilience"] and
            type(resilience.get("run_attempt")) is int and
            resilience.get("run_attempt") >= 2 and
            _job_success(jobs["resilience"], "resilience")),
        "eod_security_and_private_preflight": (
            _job_success(jobs["eod"], "offline-guard") and
            _job_success(jobs["eod"], "private-sheets-auth-preflight") and
            _job_success(jobs["eod"], "daily-private-scan")),
        "a14_research_chain_completed": (
            _job_success(jobs["a14"], "configuration-readiness") and
            _job_success(jobs["a14"], "private-research-after-eod")),
    }
    try:
        dt0 = datetime.fromisoformat(eod["created_at"].replace("Z", "+00:00"))
        dt1 = datetime.fromisoformat(a14["created_at"].replace("Z", "+00:00"))
        checks["a14_follows_eod_time"] = (dt0.tzinfo is not None and
                                          dt1.tzinfo is not None and dt1 >= dt0)
    except (KeyError, ValueError, AttributeError, TypeError):
        checks["a14_follows_eod_time"] = False
    ready = all(checks.values())
    return {
        "schema": "XRAY_PERSONAL_NASDAQ_A20_FINAL_START_V1",
        "research_radar_start": "START_ARMED" if ready else "HOLD",
        "checks": checks,
        "failing_checks": [k for k, ok in checks.items() if not ok],
        "scientific_review_axes": len(SCIENTIFIC_AXES),
        "private_readback_class": "VERIFIED_JOB_SUCCESS" if checks["private_real_source_readback"]
                                  else "UNVERIFIED",
        "last_completed_477_eod_data": "NOT_ATTESTED_BY_THIS_GATE",
        "next_post_close_a14_private_data_run": "NOT_YET_OBSERVED",
        "strategy_alpha_release": "HOLD_UNDERPOWERED_NO_INDEPENDENT_HOLDOUT",
        "mature_outcome_proven": False,
        "real_fill_proven": False,
        "broker_access": False,
        "orders": False,
        "automatic_rule_change": False,
        "device_receipt_proven": False,
        "execution": "NONE",
        "immutable_one_time_evidence": True,
    }


def get_json(path, token):
    req = Request("https://api.github.com/repos/" + REPO + "/" + path,
                  headers={"Accept": "application/vnd.github+json",
                           "Authorization": "Bearer " + token,
                           "X-GitHub-Api-Version": "2022-11-28",
                           "User-Agent": "XRAY-Personal-NASDAQ-A20-Start-Gate"})
    with urlopen(req, timeout=18) as response:
        return json.load(response)


def main():
    try:
        need(os.environ.get("GITHUB_REPOSITORY") == REPO, "OTHER_REPOSITORY")
        need(os.environ.get("GITHUB_REF") == "refs/heads/main", "NOT_MAIN_BRANCH")
        need(os.environ.get("GITHUB_REF_PROTECTED") == "true",
             "GITHUB_REF_NOT_PROTECTED")
        token = os.environ.get("GITHUB_TOKEN", "")
        need(bool(token), "GITHUB_ACTIONS_READ_TOKEN_MISSING")
        bundle = {
            "branch": get_json("branches/main", token),
            "ruleset": get_json(f"rulesets/{RULESET}", token),
            "runs": {n: get_json(f"actions/runs/{id}", token)
                     for n, id in RUNS.items()},
            "jobs": {n: get_json(f"actions/runs/{id}/jobs?per_page=100", token
                                 ).get("jobs") for n, id in RUNS.items()},
        }
        result = final_gate(bundle)
        print(json.dumps(result, sort_keys=True))
        # HOLD is intentionally non-success for this final-start attestor.
        return 0 if result["research_radar_start"] == "START_ARMED" else 3
    except Exception as exc:
        # Never print API response, private token, URLs, candidate data,
        # symbol identities, spreadsheet ID, or exception message.
        print(json.dumps({"schema": "XRAY_PERSONAL_NASDAQ_A20_FINAL_START_V1",
                          "research_radar_start": "HOLD",
                          "reason": type(exc).__name__,
                          "orders": False, "execution": "NONE"}, sort_keys=True))
        return 3


if __name__ == "__main__":
    sys.exit(main())
