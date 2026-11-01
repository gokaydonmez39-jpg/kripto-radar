#!/usr/bin/env python3
"""A46 deterministic, ledger-driven candidate queue with no upstream execution.

At most seven NEW candidates per admitted EOD (not calendar weekdays).
After all 249 eligible candidates are observed, retries unknown outcomes.
No autonomous integration, commands, PR merge, Secrets, Issues or broker use.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

from autopilot import BATCH, EXCLUDED, ORDER, SCOPE, GateError, parse_registry

STATE_SCHEMA = "XRAY_NASDAQ_A45_ROLLING_ARTIFACT_LEDGER_V1"
QUEUE_SCHEMA = "XRAY_NASDAQ_A46_LEDGER_QUEUE_V1"
RETRY_STATES = frozenset({"SOURCE_PROBE_UNKNOWN", "SOURCE_PROVENANCE_UNKNOWN"})
MAX_RETRY_OBSERVATIONS = 3


def need(condition, reason):
    if not condition:
        raise GateError(reason)


def registry_digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_state(raw: bytes, registry_sha: str) -> dict:
    doc = json.loads(raw)
    need(isinstance(doc, dict) and doc.get("schema") == STATE_SCHEMA and
         doc.get("scope") == SCOPE and
         doc.get("registry_sha256") == registry_sha, "PREVIOUS_LEDGER_CONTRACT")
    need(type(doc.get("total_accepted_epochs")) is int and
         doc["total_accepted_epochs"] >= 0, "PREVIOUS_EPOCH_COUNT")
    states, episodes = doc.get("candidate_states"), doc.get("episodes")
    need(isinstance(states, dict) and isinstance(episodes, dict), "PREVIOUS_STATE_SHAPE")
    need(len(states) <= 284 and len(episodes) <= 10000, "PREVIOUS_LEDGER_OVERSIZE")
    for key, record in states.items():
        need(key.isdigit() and 1 <= int(key) <= 284 and
             isinstance(record, dict) and
             record.get("production_integrated") is False and
             isinstance(record.get("latest_status"), str) and
             isinstance(record.get("last_asof_et"), str) and
             type(record.get("observations")) is int and
             1 <= record["observations"] <= 1000000, "UNSAFE_PREVIOUS_CANDIDATE")
    return doc


def select_queue(raw_registry: bytes, *, asof: dt.date,
                 previous_raw: bytes | None = None,
                 upstream_run_id: int | None = None) -> dict:
    need(type(asof) is dt.date and asof.weekday() < 5, "DATE_NOT_US_WEEKDAY")
    need(type(upstream_run_id) is int and upstream_run_id > 0, "SOURCE_RUN_REQUIRED")
    entries = parse_registry(raw_registry)
    ordered = sorted((r for r in entries if r["recomputed_tier"] in ORDER),
                     key=lambda r: (ORDER.index(r["recomputed_tier"]), r["registry_id"]))
    sha = registry_digest(raw_registry)
    prev_sha = ""
    prev_states = {}
    if previous_raw is not None:
        previous = read_state(previous_raw, sha)
        prev_sha = hashlib.sha256(previous_raw).hexdigest()
        need(str(upstream_run_id) not in previous["episodes"],
             "SOURCE_EOD_ALREADY_ADMITTED_REPLAY")
        need(not previous.get("last_asof_et") or
             asof.isoformat() >= previous["last_asof_et"], "QUEUE_STALE_EOD")
        prev_states = previous["candidate_states"]
    unseen = [r for r in ordered if str(r["registry_id"]) not in prev_states]
    selected = unseen[:BATCH]
    mode = "NEXT_UNSEEN"
    if len(selected) < BATCH:
        retries = [r for r in ordered if str(r["registry_id"]) in prev_states and
                   prev_states[str(r["registry_id"])]["latest_status"] in RETRY_STATES and
                   prev_states[str(r["registry_id"])]["observations"] < MAX_RETRY_OBSERVATIONS]
        retries.sort(key=lambda r: (prev_states[str(r["registry_id"])]["last_asof_et"],
                                    r["registry_id"]))
        seen_ids = {r["registry_id"] for r in selected}
        for row in retries:
            if len(selected) >= BATCH:
                break
            if row["registry_id"] not in seen_ids:
                selected.append(row)
                seen_ids.add(row["registry_id"])
        if not unseen:
            mode = "RETRY_UNCERTAIN"
        else:
            mode = "LAST_UNSEEN_PLUS_RETRIES"
    if not selected:
        # Safe periodic non-promotional rechecks, oldest first.
        selected = sorted(ordered,
                          key=lambda r: (prev_states[str(r["registry_id"])]["last_asof_et"],
                                         ORDER.index(r["recomputed_tier"]), r["registry_id"]))[:BATCH]
        mode = "PERIODIC_SOURCE_RECHECK"
    need(1 <= len(selected) <= BATCH and
         all(r["recomputed_tier"] not in EXCLUDED for r in selected),
         "QUEUE_CONTAINS_HOLD_OR_OVERFLOW")
    ids = [r["registry_id"] for r in selected]
    return {
        "schema": QUEUE_SCHEMA,
        "asof_et": asof.isoformat(),
        "source_run_id": upstream_run_id,
        "registry_sha256": sha,
        "previous_state_sha256": prev_sha,
        "selected_ids": ids,
        "remaining_unseen_before": len(unseen),
        "mode": mode,
        "automatic_promotion": False,
        "execution": "NONE",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--registry", required=True)
    p.add_argument("--previous")
    p.add_argument("--asof", required=True)
    p.add_argument("--source-run-id", type=int, required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    previous = Path(args.previous).read_bytes() if args.previous else None
    selected = select_queue(Path(args.registry).read_bytes(),
                            asof=dt.date.fromisoformat(args.asof),
                            previous_raw=previous,
                            upstream_run_id=args.source_run_id)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(selected, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    print("XRAY_A46_QUEUE=PASS;MODE=%s;COUNT=%d;UNSEEN=%d;AUTOPROMOTE=FALSE" %
          (selected["mode"], len(selected["selected_ids"]),
           selected["remaining_unseen_before"]))


if __name__ == "__main__":
    main()
