#!/usr/bin/env python3
"""Fail-closed persistent manual research follow-up proposal; never orders or push claims.

Takes an already-registered canonical candidate plus independently verified bars
(or fresh official controls). Does NOT fetch prices, register AL, or deliver alerts.
All mutations are proposed to a temporary output: a separate CAS-safe publisher
must verify fresh canonical registry/current evidence before committing.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path

from manual_signal_lifecycle_shadow import (
    CLOSED, STATES, control_event, event, fixtures, iso, validate_candidate,
)

SCHEMA = "XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1"
RESULT = "XRAY_MANUAL_RESEARCH_LIFECYCLE_PROPOSAL_V1"
TASK = "6a825366222081918997094d76e6ae46"


def proposal(registry: dict, observation: dict, observed_at_utc: str) -> dict:
    if not isinstance(registry, dict) or registry.get("schema") != SCHEMA:
        raise ValueError("REGISTRY_SCHEMA_INVALID")
    if (registry.get("execution") != "NONE" or registry.get("real_money") != "NO-GO"
            or registry.get("unknown_never_pass") is not True
            or registry.get("task_id") != TASK):
        raise ValueError("REGISTRY_SAFETY_INVALID")
    records = registry.get("records")
    if not isinstance(records, dict):
        raise ValueError("REGISTRY_RECORDS_INVALID")
    if not isinstance(observation, dict):
        raise ValueError("OBSERVATION_FORMAT_INVALID")
    if set(observation) - set(records):
        raise ValueError("UNREGISTERED_CANDIDATE_EVENT_REJECTED")
    current = iso(observed_at_utc).isoformat()
    updated = copy.deepcopy(registry)
    pending = []
    for delivery_key in sorted(records):
        rec = copy.deepcopy(records[delivery_key])
        if not isinstance(rec, dict):
            raise ValueError("RECORD_INVALID")
        candidate = rec.get("manual_candidate")
        if not candidate:
            # Historical registry shapes are NOT silently converted or alerted.
            if delivery_key in observation:
                raise ValueError("LEGACY_UNVERIFIED_REGISTRATION")
            continue
        if rec.get("registration_status") != "REGISTERED_QUALIFIED_RESEARCH":
            raise ValueError("REGISTRATION_NOT_VERIFIED")
        if candidate.get("delivery_key") != delivery_key:
            raise ValueError("DELIVERY_KEY_DRIFT")
        validate_candidate(candidate)
        if rec.get("candidate_asof_et") != candidate["source_asof_et"]:
            raise ValueError("CANDIDATE_ASOF_MISMATCH")
        previous = rec.get("followup") or {}
        if previous:
            if previous.get("delivery_key") != delivery_key or previous.get("status") not in STATES:
                raise ValueError("PREVIOUS_FOLLOWUP_INVALID")
        # Dedup means delivery-confirmed, not merely classified. Keep every
        # unacknowledged alert pending across retries and workflow restarts.
        existing_pending = rec.get("pending_notifications") or {}
        if not isinstance(existing_pending, dict):
            raise ValueError("PENDING_NOTIFICATION_LEDGER_INVALID")
        for pending_key, pending_note in sorted(existing_pending.items()):
            if (not isinstance(pending_key, str) or len(pending_key) != 64
                    or not isinstance(pending_note, dict)
                    or pending_note.get("delivery_key") != delivery_key
                    or pending_note.get("alert_dedup_key") != pending_key
                    or pending_note.get("notification_status") != "PENDING_NOT_DELIVERED"
                    or pending_note.get("orders") != []):
                raise ValueError("PENDING_NOTIFICATION_RECORD_INVALID")
            pending.append(copy.deepcopy(pending_note))
        evidence = observation.get(delivery_key, {})
        if not isinstance(evidence, dict):
            raise ValueError("OBSERVATION_INVALID")
        if set(evidence) - {"bar", "official_control"}:
            raise ValueError("UNKNOWN_OBSERVATION_FIELDS")
        if evidence.get("bar") is not None and evidence.get("official_control") is not None:
            raise ValueError("AMBIGUOUS_BAR_AND_CONTROL")
        if evidence.get("bar") is not None:
            result = event(candidate, evidence["bar"], previous or None, observed_at_utc=current)
        else:
            result = control_event(candidate, previous or None, observed_at_utc=current,
                                   official_control=evidence.get("official_control"))
        # The classifier explicitly preserves terminal states and emits no orders.
        if result.get("orders") != [] or result.get("user_notification_delivered") is True:
            raise ValueError("LIFECYCLE_SAFETY_VIOLATED")
        if result.get("transition") == "TERMINAL_STATE_LOCKED":
            continue
        if result.get("transition") == "NO_BAR_NO_NEW_CONTROL":
            continue
        dedup = list(rec.get("alert_dedup_keys") or [])
        if len(dedup) != len(set(dedup)):
            raise ValueError("DUPLICATED_REGISTRY_ALERT_KEYS")
        if result.get("alert"):
            key = result.get("alert_dedup_key")
            if not isinstance(key, str) or len(key) != 64:
                raise ValueError("MISSING_ALERT_DEDUP_HASH")
            if key not in dedup:
                dedup.append(key)
                note={"delivery_key": delivery_key, "symbol": candidate["symbol"],
                      "status": result["status"], "alert_dedup_key": key,
                      "notification_status": "PENDING_NOT_DELIVERED", "orders": []}
                existing_pending[key] = note
                pending.append(copy.deepcopy(note))
        rec["followup"] = result
        rec["pending_notifications"] = existing_pending
        rec["alert_dedup_keys"] = dedup
        updated["records"][delivery_key] = rec
    return {"schema": RESULT, "asof_observed_utc": current, "execution": "NONE",
            "real_money": "NO-GO", "unknown_never_pass": True,
            "registry": updated, "pending_alerts": pending,
            "user_delivery_confirmed": False, "orders": [],
            "registered_record_count": len(records)}


def tests() -> None:
    c, b = fixtures()
    empty = {"schema": SCHEMA, "task_id": TASK, "asof_et": "2026-10-08",
             "execution": "NONE", "real_money": "NO-GO",
             "unknown_never_pass": True, "records": {}}
    r = proposal(empty, {}, "2026-10-08T19:10:00Z")
    assert r["registered_record_count"] == 0 and r["pending_alerts"] == []
    good = copy.deepcopy(empty)
    good["records"][c["delivery_key"]] = {
        "registration_status": "REGISTERED_QUALIFIED_RESEARCH",
        "candidate_asof_et": c["source_asof_et"],
        "manual_candidate": c,
    }
    fresh = proposal(good, {c["delivery_key"]: {"bar": b}}, "2026-10-08T19:10:00Z")
    assert len(fresh["pending_alerts"]) == 1
    assert fresh["pending_alerts"][0]["notification_status"] == "PENDING_NOT_DELIVERED"
    repeated = proposal(fresh["registry"], {c["delivery_key"]: {"bar": b}},
                        "2026-10-08T19:10:00Z")
    assert len(repeated["pending_alerts"]) == 1
    assert repeated["pending_alerts"][0] == fresh["pending_alerts"][0]
    # No delivery receipt exists: the alert MUST NOT disappear just because
    # the same bar was classified twice. A downstream publisher uses the
    # stable alert_dedup_key for idempotent delivery attempts.
    after = proposal(repeated["registry"], {}, "2026-10-16T20:00:00Z")
    assert len(after["pending_alerts"]) == 2
    assert set(x["status"] for x in after["pending_alerts"]) == {
        "ENTRY_ZONE_TOUCHED", "EXPIRED"}
    repeated_expiry = proposal(after["registry"], {}, "2026-10-17T20:00:00Z")
    assert len(repeated_expiry["pending_alerts"]) == 2
    assert repeated_expiry["pending_alerts"] == after["pending_alerts"]
    for bad in (
        {"missing_registered_key": {"bar": b}},
        {c["delivery_key"]: {"bar": {**b, "source_authorized": False}}},
        {c["delivery_key"]: {"bar": b, "official_control": {}}},
    ):
        try:
            proposal(good, bad, "2026-10-08T19:10:00Z")
        except ValueError:
            pass
        else:
            raise AssertionError("UNAUTHORIZED_OBSERVATION_ADMITTED")
    badregistry = copy.deepcopy(good)
    badregistry["records"][c["delivery_key"]]["manual_candidate"]["manual_approved"] = False
    try:
        proposal(badregistry, {}, "2026-10-08T19:10:00Z")
    except ValueError:
        pass
    else:
        raise AssertionError("UNQUALIFIED_CANDIDATE_REGISTERED")
    print("XRAY_MANUAL_FOLLOWUP_PERSISTENT_PROPOSAL_SELFTEST=PASS")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--registry", default="nasdaq-xray/canonical_candidate_lifecycle_registry.json")
    p.add_argument("--observations")
    p.add_argument("--observed-at-utc")
    p.add_argument("--out")
    a = p.parse_args()
    if a.selftest:
        tests()
        return
    if not a.observed_at_utc or not a.out:
        raise SystemExit("OBSERVATION_TIME_AND_OUT_REQUIRED")
    registry = json.loads(Path(a.registry).read_text())
    events = json.loads(Path(a.observations).read_text()) if a.observations else {}
    result = proposal(registry, events, a.observed_at_utc)
    Path(a.out).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("XRAY_FOLLOWUP_PROPOSAL_ONLY_NO_DELIVERY count="
          + str(len(result["pending_alerts"])))


if __name__ == "__main__":
    main()
