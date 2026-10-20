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
import math
from pathlib import Path

from manual_signal_lifecycle_shadow import (
    CLOSED, STATES, control_event, event, fixtures, iso, validate_candidate,
)

SCHEMA = "XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1"
RESULT = "XRAY_MANUAL_RESEARCH_LIFECYCLE_PROPOSAL_V1"
TASK = "6a825366222081918997094d76e6ae46"


def origin_digest(row: dict) -> str:
    """Canonical JSON fingerprint of the exact immutable R92 origin record."""
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


def canonical_r92_index(pointer: dict) -> dict:
    if not isinstance(pointer, dict) or pointer.get("schema") not in (
            "XRAY_GITHUB_DURABLE_STATE_V2", "XRAY_GITHUB_DURABLE_STATE_V3"):
        raise ValueError("CANONICAL_R92_POINTER_INVALID")
    if (pointer.get("authority") != "GITHUB_CURRENT_POINTER"
            or pointer.get("execution") != "NONE"
            or pointer.get("real_money") != "NO-GO"):
        raise ValueError("CANONICAL_R92_POINTER_SAFETY_INVALID")
    state = pointer.get("state_json")
    if not isinstance(state, dict) or state.get("task_id") != TASK:
        raise ValueError("CANONICAL_R92_TASK_INVALID")
    r92, keys = state.get("r92"), state.get("delivery_keys")
    if not isinstance(r92, list) or not isinstance(keys, list):
        raise ValueError("CANONICAL_R92_REGISTRY_INVALID")
    if len(keys) != len(set(keys)):
        raise ValueError("CANONICAL_R92_DUPLICATE_DELIVERY_KEY")
    index = {}
    for row in r92:
        if (not isinstance(row, dict)
                or row.get("schema") != "XRAY_RESEARCH_CANDIDATE_R92_V1"
                or row.get("execution") != "NONE"
                or row.get("real_money") != "NO-GO"):
            raise ValueError("CANONICAL_R92_RECORD_INVALID")
        key = row.get("delivery_key")
        if not isinstance(key, str) or not key or key not in keys or key in index:
            raise ValueError("CANONICAL_R92_KEY_INVALID_OR_DUPLICATE")
        index[key] = row
    return index


def proposal(registry: dict, observation: dict, observed_at_utc: str, *, canonical_pointer: dict | None = None) -> dict:
    if not isinstance(registry, dict) or registry.get("schema") != SCHEMA:
        raise ValueError("REGISTRY_SCHEMA_INVALID")
    if (registry.get("execution") != "NONE" or registry.get("real_money") != "NO-GO"
            or registry.get("unknown_never_pass") is not True
            or registry.get("task_id") != TASK):
        raise ValueError("REGISTRY_SAFETY_INVALID")
    records = registry.get("records")
    if not isinstance(records, dict):
        raise ValueError("REGISTRY_RECORDS_INVALID")
    if records and canonical_pointer is None:
        raise ValueError("CANONICAL_R92_POINTER_REQUIRED")
    index = canonical_r92_index(canonical_pointer) if records else {}
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
        origin = index.get(delivery_key)
        if (not isinstance(origin, dict)
                or origin.get("symbol") != candidate["symbol"]
                or origin.get("asof_et") != candidate.get("source_asof_et")
                or origin.get("setup") not in ("A", "B", "C", "D")
                or origin.get("setup") != candidate.get("setup")):
            raise ValueError("CANONICAL_R92_ORIGIN_MISMATCH")
        if rec.get("origin_r92_sha256") != origin_digest(origin):
            raise ValueError("CANONICAL_R92_ORIGIN_HASH_MISMATCH")
        # A matching delivery key and canonical row digest must not license
        # locally invented entry, stop, or profit-target geometry.
        for local, registered in (("entry_low", "entry_low"),
                                  ("entry_high", "entry_high"),
                                  ("stop", "stop"), ("target", "r1")):
            src = origin.get(registered)
            value = candidate.get(local)
            if (type(src) not in (int, float)
                    or type(value) not in (int, float)
                    or not math.isfinite(src) or not math.isfinite(value)
                    or float(src) != float(value)):
                raise ValueError("CANONICAL_R92_LEVEL_DRIFT")
        registered_at = iso(origin.get("registered_at_utc"))
        if iso(candidate.get("origin_at_utc")) < registered_at:
            raise ValueError("CANDIDATE_ORIGIN_PREDATES_R92_REGISTRATION")
        # An expiry is a material user notification, never a calendar guess.
        # Existing R92 rows lacking a fixed expiry may still be monitored,
        # but must not fabricate EXPIRED from local-only candidate metadata.
        source_expiry = origin.get("expires_at_utc")
        requested_expiry = iso(candidate.get("expires_at_utc"))
        if source_expiry is not None:
            if iso(source_expiry) != requested_expiry:
                raise ValueError("CANONICAL_R92_EXPIRY_MISMATCH")
        expiry_due_without_source = (
            source_expiry is None and iso(current) >= requested_expiry)
        if rec.get("candidate_asof_et") != candidate["source_asof_et"]:
            raise ValueError("CANDIDATE_ASOF_MISMATCH")
        previous = rec.get("followup") or {}
        if previous:
            if previous.get("delivery_key") != delivery_key or previous.get("status") not in STATES:
                raise ValueError("PREVIOUS_FOLLOWUP_INVALID")
        # Pending notifications may only replay a previously classified
        # material event for this immutable candidate. Never surface orphan
        # queue rows or a fabricated SOURCE_STALE / unrelated symbol.
        issued_keys = rec.get("alert_dedup_keys") or []
        if (not isinstance(issued_keys, list)
                or len(issued_keys) != len(set(issued_keys))
                or any(not isinstance(k, str) or len(k) != 64 for k in issued_keys)):
            raise ValueError("PENDING_NOTIFICATION_DEDUP_LEDGER_INVALID")
        material_states = STATES - {"MONITORING", "SOURCE_STALE"}
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
            if (pending_key not in issued_keys
                    or pending_note.get("symbol") != candidate["symbol"]
                    or pending_note.get("status") not in material_states):
                raise ValueError("PENDING_NOTIFICATION_RECORD_UNBOUND")
            pending.append(copy.deepcopy(pending_note))
        if expiry_due_without_source:
            # Material EXPIRED is unproven. Freeze future classification but
            # retain every independently classified earlier queued notice.
            updated["records"][delivery_key] = rec
            continue
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
    # Stable sort prevents retry order changing when a new terminal alert
    # joins an older unacknowledged entry alert.
    pending.sort(key=lambda note: (note["delivery_key"], note["alert_dedup_key"]))
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
    # RED: a fabricated manual registry must not count as a canonical R92.
    try:
        proposal(good, {c["delivery_key"]: {"bar": b}}, "2026-10-08T19:10:00Z")
    except ValueError as exc:
        if str(exc) != "CANONICAL_R92_POINTER_REQUIRED":
            raise
    else:
        raise RuntimeError("FORGED_MANUAL_REGISTRY_ADMITTED_WITHOUT_CANONICAL_R92")

    # Offline-only synthetic canonical fixture: never production R92 evidence.
    c["setup"] = "A"
    origin = {"schema": "XRAY_RESEARCH_CANDIDATE_R92_V1",
              "delivery_key": c["delivery_key"], "symbol": c["symbol"],
              "setup": "A", "asof_et": c["source_asof_et"],
              "entry_low": c["entry_low"], "entry_high": c["entry_high"],
              "stop": c["stop"], "r1": c["target"],
              "registered_at_utc": c["origin_at_utc"],
              "expires_at_utc": c["expires_at_utc"],
              "execution": "NONE", "real_money": "NO-GO"}
    canonical = {"schema": "XRAY_GITHUB_DURABLE_STATE_V3",
                 "authority": "GITHUB_CURRENT_POINTER",
                 "execution": "NONE", "real_money": "NO-GO",
                 "state_json": {"task_id": TASK, "r92": [origin],
                                "delivery_keys": [c["delivery_key"]]}}
    good["records"][c["delivery_key"]]["origin_r92_sha256"] = origin_digest(origin)
    def bound_proposal(reg, obs, stamp, *, pointer=canonical):
        return proposal(reg, obs, stamp, canonical_pointer=pointer)

    # RED: a matching R92 key/hash must never license locally invented levels.
    # Both counterfeit shapes remain valid LONG geometry, masking the drift.
    for field, counterfeit in (("stop", 90.0), ("target", 110.0),
                               ("entry_low", 101.0), ("entry_high", 103.5)):
        forged = copy.deepcopy(good)
        forged["records"][c["delivery_key"]]["manual_candidate"][field] = counterfeit
        try:
            bound_proposal(forged, {}, "2026-10-08T19:10:00Z")
        except ValueError as exc:
            if str(exc) != "CANONICAL_R92_LEVEL_DRIFT":
                raise
        else:
            raise RuntimeError("FORGED_MANUAL_R92_LEVEL_ADMITTED:" + field)

    fresh = bound_proposal(good, {c["delivery_key"]: {"bar": b}}, "2026-10-08T19:10:00Z")
    assert len(fresh["pending_alerts"]) == 1
    assert fresh["pending_alerts"][0]["notification_status"] == "PENDING_NOT_DELIVERED"
    repeated = bound_proposal(fresh["registry"], {c["delivery_key"]: {"bar": b}},
                        "2026-10-08T19:10:00Z")
    assert len(repeated["pending_alerts"]) == 1
    assert repeated["pending_alerts"][0] == fresh["pending_alerts"][0]
    # No delivery receipt exists: the alert MUST NOT disappear just because
    # the same bar was classified twice. A downstream publisher uses the
    # stable alert_dedup_key for idempotent delivery attempts.
    after = bound_proposal(repeated["registry"], {}, "2026-10-16T20:00:00Z")
    assert len(after["pending_alerts"]) == 2
    assert set(x["status"] for x in after["pending_alerts"]) == {
        "ENTRY_ZONE_TOUCHED", "EXPIRED"}
    repeated_expiry = bound_proposal(after["registry"], {}, "2026-10-17T20:00:00Z")
    assert len(repeated_expiry["pending_alerts"]) == 2
    assert repeated_expiry["pending_alerts"] == after["pending_alerts"]
    for bad in (
        {"missing_registered_key": {"bar": b}},
        {c["delivery_key"]: {"bar": {**b, "source_authorized": False}}},
        {c["delivery_key"]: {"bar": b, "official_control": {}}},
    ):
        try:
            bound_proposal(good, bad, "2026-10-08T19:10:00Z")
        except ValueError:
            pass
        else:
            raise AssertionError("UNAUTHORIZED_OBSERVATION_ADMITTED")
    # RED: a forged pending notice with no dedup event must never rehydrate.
    unproven = copy.deepcopy(good)
    fake_key = "f" * 64
    unproven["records"][c["delivery_key"]]["pending_notifications"] = {
        fake_key: {"delivery_key": c["delivery_key"], "symbol": "OTHER",
                   "status": "STOP_LEVEL_TOUCHED", "alert_dedup_key": fake_key,
                   "notification_status": "PENDING_NOT_DELIVERED", "orders": []}}
    try:
        bound_proposal(unproven, {}, "2026-10-08T19:10:00Z")
    except ValueError as exc:
        if str(exc) != "PENDING_NOTIFICATION_RECORD_UNBOUND":
            raise
    else:
        raise RuntimeError("ORPHAN_OR_FORGED_PENDING_FOLLOWUP_ACCEPTED")
    # Even a previously issued pending key may never be replayed under an
    # unrelated symbol or a non-user-notifiable state.
    for field, value in (("symbol", "OTHER"), ("status", "SOURCE_STALE")):
        modified = copy.deepcopy(fresh["registry"])
        rec = modified["records"][c["delivery_key"]]
        first_pending = next(iter(rec["pending_notifications"].values()))
        first_pending[field] = value
        try:
            bound_proposal(modified, {}, "2026-10-08T19:11:00Z")
        except ValueError as exc:
            if str(exc) != "PENDING_NOTIFICATION_RECORD_UNBOUND":
                raise
        else:
            raise RuntimeError("FALSIFIED_PENDING_NOTE_ACCEPTED:" + field)
    # RED: an arbitrary local expiry must not fabricate a terminal
    # "candidate expired" event unrelated to immutable R92 provenance.
    premature = copy.deepcopy(good)
    premature["records"][c["delivery_key"]]["manual_candidate"][
        "expires_at_utc"] = "2026-10-08T19:05:00Z"
    try:
        bound_proposal(premature, {}, "2026-10-08T19:10:00Z")
    except ValueError as exc:
        if str(exc) != "CANONICAL_R92_EXPIRY_MISMATCH":
            raise
    else:
        raise RuntimeError("UNVERIFIED_EARLY_EXPIRY_ADMITTED")

    # Even when the original R92 does not store an expiry, the classifier
    # may not mint an EXPIRED notice based only on a local timer.
    no_expiry = copy.deepcopy(canonical)
    no_expiry["state_json"]["r92"][0].pop("expires_at_utc")
    old_registry = copy.deepcopy(good)
    old_registry["records"][c["delivery_key"]]["origin_r92_sha256"] = origin_digest(
        no_expiry["state_json"]["r92"][0])
    freeze = bound_proposal(
        old_registry, {}, "2026-10-16T20:00:00Z", pointer=no_expiry)
    if freeze["pending_alerts"] or freeze["registry"] != old_registry:
        raise RuntimeError("UNPROVEN_EXPIRY_CHANGED_STATE_OR_ALERTED")
    # RED follow-up to expiry guard: never discard already-verified pending
    # notices simply because this separate expiry proof is unavailable.
    pending_on_expiry = copy.deepcopy(fresh["registry"])
    pending_on_expiry["records"][c["delivery_key"]]["origin_r92_sha256"] = origin_digest(
        no_expiry["state_json"]["r92"][0])
    try:
        retained = bound_proposal(pending_on_expiry, {},
                                  "2026-10-16T20:00:00Z", pointer=no_expiry)
    except ValueError as exc:
        raise RuntimeError("UNVERIFIED_EXPIRY_BLOCKED_OLDER_PENDING_NOTICES") from exc
    if (len(retained["pending_alerts"]) != 1 or
            retained["pending_alerts"][0]["status"] != "ENTRY_ZONE_TOUCHED"):
        raise RuntimeError("PENDING_EVENT_LOST_WHILE_EXPIRY_UNVERIFIED")
    # A manual source clock may not be backdated before actual R92 registration.
    late = copy.deepcopy(canonical)
    late["state_json"]["r92"][0]["registered_at_utc"] = "2026-10-08T18:30:00Z"
    shifted = copy.deepcopy(good)
    shifted["records"][c["delivery_key"]]["origin_r92_sha256"] = origin_digest(
        late["state_json"]["r92"][0])
    try:
        bound_proposal(shifted, {}, "2026-10-08T19:10:00Z", pointer=late)
    except ValueError as exc:
        if str(exc) != "CANDIDATE_ORIGIN_PREDATES_R92_REGISTRATION":
            raise
    else:
        raise RuntimeError("BACKDATED_R92_LIFECYCLE_ORIGIN_ADMITTED")
    # No pointer, no key, mismatched setup and forged origin digest are all
    # rejected even when the manual registration label says REGISTERED.
    for mutation, expected in (
        (lambda p: p["state_json"].update(r92=[]), "CANONICAL_R92_ORIGIN_MISMATCH"),
        (lambda p: p["state_json"]["r92"][0].update(setup="D"), "CANONICAL_R92_ORIGIN_MISMATCH"),
        (lambda p: p["state_json"]["r92"][0].update(symbol="OTHER"), "CANONICAL_R92_ORIGIN_MISMATCH"),
    ):
        broken = copy.deepcopy(canonical)
        mutation(broken)
        try:
            bound_proposal(good, {}, "2026-10-08T19:10:00Z", pointer=broken)
        except ValueError as exc:
            if str(exc) != expected:
                raise
        else:
            raise RuntimeError("FORGED_CANONICAL_ORIGIN_WAS_ACCEPTED")
    tampered = copy.deepcopy(good)
    tampered["records"][c["delivery_key"]]["origin_r92_sha256"] = "0" * 64
    try:
        bound_proposal(tampered, {}, "2026-10-08T19:10:00Z")
    except ValueError as exc:
        if str(exc) != "CANONICAL_R92_ORIGIN_HASH_MISMATCH":
            raise
    else:
        raise RuntimeError("FORGED_R92_ORIGIN_DIGEST_ACCEPTED")
    badregistry = copy.deepcopy(good)
    badregistry["records"][c["delivery_key"]]["manual_candidate"]["manual_approved"] = False
    try:
        bound_proposal(badregistry, {}, "2026-10-08T19:10:00Z")
    except ValueError:
        pass
    else:
        raise AssertionError("UNQUALIFIED_CANDIDATE_REGISTERED")
    print("XRAY_MANUAL_FOLLOWUP_PERSISTENT_PROPOSAL_SELFTEST=PASS")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--registry", default="nasdaq-xray/canonical_candidate_lifecycle_registry.json")
    p.add_argument("--canonical-pointer", default="nasdaq-xray/chatgpt_canonical_state_v2.json")
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
    pointer = json.loads(Path(a.canonical_pointer).read_text())
    result = proposal(registry, events, a.observed_at_utc, canonical_pointer=pointer)
    Path(a.out).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("XRAY_FOLLOWUP_PROPOSAL_ONLY_NO_DELIVERY count="
          + str(len(result["pending_alerts"])))


if __name__ == "__main__":
    main()
