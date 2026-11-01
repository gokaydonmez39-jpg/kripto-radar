#!/usr/bin/env python3
"""A45 zero-write-permission rolling research artifact ledger.

Reconciles authenticated read-only A42/A43/A44 receipts with previous artifact.
No Issues API, repo writes, Sheets, orders or third-party source execution.
Retention remains limited by GitHub Actions artifact retention (30 days).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "XRAY_NASDAQ_A45_ROLLING_ARTIFACT_LEDGER_V1"
SCOPE = "NASDAQ_RESEARCH_ONLY_NO_CRYPTO"
HEX = re.compile(r"^[a-f0-9]{64}$")
VALID = frozenset({
    "SOURCE_PROVENANCE_UNKNOWN",
    "NON_GITHUB_OR_MISSING_URL_MANUAL_PROVENANCE",
    "HOLD_ARCHIVED_DISABLED_OR_UNVERIFIED",
    "HOLD_FORK_PARENT_NOT_VERIFIED",
    "HOLD_LICENSE_REVIEW",
    "SOURCE_PROBE_UNKNOWN",
    "PROVENANCE_RECORDED_TEST_REQUIRED",
})


class Blocked(ValueError):
    pass


def need(ok, why):
    if not ok:
        raise Blocked(why)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def receive(a42, a43, a44):
    need(type(a42) is dict and a42.get("schema") ==
         "XRAY_NASDAQ_CANDIDATE_AUTOPILOT_RECEIPT_V1", "A42_SCHEMA")
    need(a42.get("source") == SCOPE and a42.get("automatic_promotion") is False and
         a42.get("orders") is False and a42.get("private_sheet_writes") is False,
         "A42_SCOPE_OR_SIDE_EFFECT")
    need(type(a43) is dict and a43.get("schema") ==
         "XRAY_NASDAQ_A43_EOD_ADMISSION_V1" and
         a43.get("registry_admission") == "PASS_FOR_READONLY_CANDIDATE_INTAKE" and
         a43.get("production_promotion") is False and
         a43.get("scan_477") is True and a43.get("sheet_readback") is True and
         a43.get("lifecycle_readback") is True and a43.get("panel_readback") is True,
         "A43_MISSING_REAL_EOD_PROOF")
    need(type(a44) is dict and a44.get("schema") ==
         "XRAY_NASDAQ_A44_SOURCE_EVIDENCE_V1" and
         a44.get("scope") == SCOPE and a44.get("automatic_promotion") is False and
         a44.get("network_enabled") is True, "A44_WRONG_SCOPE_OR_OFFLINE")
    need(a42.get("asof") == a43.get("asof_et") == a44.get("asof_et") and
         isinstance(a43.get("asof_et"), str) and
         re.fullmatch(r"\d{4}-\d{2}-\d{2}", a43["asof_et"]),
         "SESSION_ASOF_CONFLICT")
    need(a42.get("registry_sha256") == a44.get("registry_sha256") and
         isinstance(a42.get("registry_sha256"), str) and
         HEX.fullmatch(a42["registry_sha256"]), "REGISTRY_SHA_CONFLICT")
    need(isinstance(a44.get("candidate_receipt_sha256"), str) and
         HEX.fullmatch(a44["candidate_receipt_sha256"]), "A42_RECEIPT_SHA_UNKNOWN")
    need(type(a43.get("run_id")) is int and a43["run_id"] > 0 and
         isinstance(a43.get("log_sha256"), str) and HEX.fullmatch(a43["log_sha256"]) and
         isinstance(a43.get("run_sha"), str) and HEX.fullmatch(a43["run_sha"]),
         "SOURCE_EOD_RUN_IDENTITY")
    rows = a44.get("results")
    need(isinstance(rows, list) and 1 <= len(rows) <= 7, "CANDIDATE_BATCH_BOUND")
    ids = []
    for row in rows:
        need(type(row) is dict and type(row.get("registry_id")) is int and
             1 <= row["registry_id"] <= 284, "SOURCE_ID_INVALID")
        ids.append(row["registry_id"])
        need(row.get("status") in VALID and
             row.get("promotion") == "BLOCKED_PENDING_INDEPENDENT_FUNCTIONAL_AND_PIT_TEST" and
             row.get("run_upstream_code") is False and row.get("broker") is False and
             row.get("license_approved") is False, "PREMATURE_SOURCE_PROMOTION")
    need(len(ids) == len(set(ids)), "REPEATED_SOURCE_IN_ONE_COHORT")
    return {
        "run_id": str(a43["run_id"]), "asof_et": a43["asof_et"],
        "run_sha": a43["run_sha"], "source_log_sha256": a43["log_sha256"],
        "registry_sha256": a42["registry_sha256"],
        "a42_receipt_sha256": a44["candidate_receipt_sha256"],
        "a44_receipt_sha256": digest(a44),
        "results": [{"id": r["registry_id"], "status": r["status"],
                     "upstream_sha": r.get("source_head_sha", "")} for r in rows],
    }


def reconcile(previous, current):
    need(type(current) is dict and isinstance(current.get("run_id"), str) and
         current["run_id"].isdigit(), "CURRENT_RUN_INVALID")
    if previous is None:
        state = {"schema": SCHEMA, "scope": SCOPE,
                 "registry_sha256": current["registry_sha256"],
                 "last_asof_et": "", "total_accepted_epochs": 0,
                 "history_continuity": "UNATTESTED_FIRST_OR_EXPIRED_ARTIFACT",
                 "episodes": {}, "candidate_states": {}}
    else:
        need(type(previous) is dict and previous.get("schema") == SCHEMA and
             previous.get("scope") == SCOPE and
             previous.get("registry_sha256") == current["registry_sha256"],
             "PREVIOUS_ARTIFACT_INVALID_OR_REGISTRY_CHANGED")
        need(type(previous.get("episodes")) is dict and
             type(previous.get("candidate_states")) is dict and
             type(previous.get("total_accepted_epochs")) is int,
             "PREVIOUS_ARTIFACT_MALFORMED")
        need(previous.get("history_continuity") in
             ("UNATTESTED_FIRST_OR_EXPIRED_ARTIFACT", "VERIFIED_ROLLING_FROM_FIRST"),
             "PREVIOUS_CONTINUITY_INVALID")
        state = copy.deepcopy(previous)
    key = current["run_id"]
    summary = {"asof_et": current["asof_et"],
               "sha256": digest(current)}
    if key in state["episodes"]:
        need(state["episodes"][key] == summary,
             "SOURCE_EPOCH_REPLAY_CONFLICT")
        return state, "IDEMPOTENT_REPLAY"
    need(not state["last_asof_et"] or
         current["asof_et"] >= state["last_asof_et"], "STALE_OR_NONMONOTONIC_EOD")
    for record in current["results"]:
        src_id = str(record["id"])
        prev = state["candidate_states"].get(src_id)
        attempts = 0 if not isinstance(prev, dict) else prev.get("observations", 0)
        need(type(attempts) is int and 0 <= attempts < 1000000,
             "CANDIDATE_HISTORY_MALFORMED")
        verified = record["upstream_sha"] if re.fullmatch(
            r"[0-9a-f]{40}", record["upstream_sha"] or "") else (
                prev.get("last_verified_sha", "") if isinstance(prev, dict) else "")
        state["candidate_states"][src_id] = {
            "latest_status": record["status"], "last_asof_et": current["asof_et"],
            "last_verified_sha": verified, "observations": attempts + 1,
            "production_integrated": False,
        }
    state["episodes"][key] = summary
    state["total_accepted_epochs"] += 1
    state["last_asof_et"] = current["asof_et"]
    # Previous rolling snapshots may be lost after a >30-day service outage.
    # The first epoch is honestly marked unverified; never assert full history.
    return state, "NEW_SOURCE_EPOCH_ADMITTED"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--a42", required=True)
    p.add_argument("--a43", required=True)
    p.add_argument("--a44", required=True)
    p.add_argument("--previous")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    a42 = json.loads(Path(args.a42).read_text(encoding="utf-8"))
    a43 = json.loads(Path(args.a43).read_text(encoding="utf-8"))
    a44 = json.loads(Path(args.a44).read_text(encoding="utf-8"))
    # A44 SHA is of the original A42 receipt file bytes, not canonical JSON.
    raw = Path(args.a42).read_bytes()
    need(hashlib.sha256(raw).hexdigest() == a44.get("candidate_receipt_sha256"),
         "A42_RECEIPT_TAMPERED")
    current = receive(a42, a43, a44)
    previous = json.loads(Path(args.previous).read_text(encoding="utf-8")) if args.previous else None
    state, status = reconcile(previous, current)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    print("XRAY_A45_ROLLING_ARTIFACT=" + status +
          ";SOURCES=" + str(len(state["candidate_states"])) +
          ";ACCEPTED_EPOCHS=" + str(state["total_accepted_epochs"]) +
          ";AUTOPROMOTE=FALSE;ISSUE_WRITES=0")


if __name__ == "__main__":
    main()
