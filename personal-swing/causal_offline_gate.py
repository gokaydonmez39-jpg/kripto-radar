#!/usr/bin/env python3
"""XRAY offline causal experiment admission gate. No network or trading.

NOT a causal learner, licensed market-data authenticator, exchange-calendar oracle,
profitability test, execution engine or production signal authority.
"""
from datetime import date, datetime
import math
import re

SCHEMA = "XRAY_CAUSAL_OFFLINE_ADMISSION_V1"
UPSTREAM_COMMIT = "0d1fae061b2445a51d0c8b75fc565d897dd54fb7"
REQUIRED_EVIDENCE = (
    "license_reviewed", "data_entitlement_attested",
    "xnas_calendar_attested", "ticker_pit_attested",
    "corporate_actions_attested", "provider_basis_attested",
    "source_publication_pit_attested", "private_data_local_only",
)

def _utc(value):
    if not isinstance(value, str) or not (value.endswith("Z") or value.endswith("+00:00")):
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_UTC_TIMESTAMP") from exc
    if t.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    return t

def _day(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_SESSION")
    try:
        d = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_SESSION") from exc
    if d.isoformat() != value:
        raise ValueError("NONCANONICAL_SESSION")
    return d

def admission_check(manifest, rows):
    """Fail closed and NEVER authorize live signal generation.

    Externally attested calendar, licensing and data vendor identity are inputs,
    not facts established by the asserted booleans in the manifest.
    Every feature and label includes actual availability timestamps.
    """
    if not isinstance(manifest, dict) or not isinstance(rows, list):
        raise ValueError("MANIFEST_AND_ROWS_REQUIRED")
    if manifest.get("schema") != SCHEMA:
        raise ValueError("INVALID_SCHEMA")
    if manifest.get("upstream_sha") != UPSTREAM_COMMIT:
        raise ValueError("UNREVIEWED_UPSTREAM_REVISION")
    if manifest.get("mode") != "ISOLATED_OFFLINE_NO_EXECUTION":
        raise ValueError("OFFLINE_MODE_REQUIRED")
    if any(manifest.get(s) is not True for s in REQUIRED_EVIDENCE):
        raise ValueError("MISSING_EXTERNAL_ATTESTATION")
    if any(manifest.get(s) is not False for s in (
            "network_enabled", "broker_enabled", "write_private_sheet",
            "may_emit_alert", "may_promote_al")):
        raise ValueError("FORBIDDEN_SIDE_EFFECT")
    digest = manifest.get("data_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("DATA_DIGEST_REQUIRED")
    calendar = manifest.get("official_xnas_sessions")
    if not isinstance(calendar, list) or len(calendar) < 500:
        raise ValueError("MIN_500_EXTERNAL_SESSIONS")
    cds = [_day(s) for s in calendar]
    if cds != sorted(set(cds)):
        raise ValueError("UNSORTED_OR_DUPLICATED_SESSIONS")
    if len(rows) != len(calendar):
        raise ValueError("MISSING_OR_EXTRA_SESSION_ROW")
    boundary = manifest.get("test_start")
    if boundary not in calendar:
        raise ValueError("UNVERIFIED_HOLDOUT_BOUNDARY")
    boundary_i = calendar.index(boundary)
    embargo = manifest.get("embargo_sessions")
    if isinstance(embargo, bool) or not isinstance(embargo, int) or embargo < 15:
        raise ValueError("INSUFFICIENT_15_SESSION_EMBARGO")
    feature_names = manifest.get("registered_features")
    if (not isinstance(feature_names, list) or not 1 <= len(feature_names) <= 20
            or len(set(feature_names)) != len(feature_names)
            or not all(isinstance(k, str) and k and k not in ("target", "label")
                       for k in feature_names)):
        raise ValueError("INVALID_PREREGISTERED_FEATURES")
    ix = {d: i for i, d in enumerate(calendar)}
    train = holdout = purged = 0
    for i, r in enumerate(rows):
        if not isinstance(r, dict) or r.get("session") != calendar[i]:
            raise ValueError("ROW_SESSION_OR_ORDER_MISMATCH")
        cutoff = _utc(r.get("decision_cutoff_utc"))
        if cutoff.date() < cds[i] or cutoff.date() > date.fromordinal(cds[i].toordinal() + 1):
            raise ValueError("IMPOSSIBLE_DECISION_CUTOFF")
        xs = r.get("features")
        if not isinstance(xs, dict) or set(xs) != set(feature_names):
            raise ValueError("FEATURE_SCHEMA_DRIFT")
        for v in xs.values():
            if (not isinstance(v, dict) or type(v.get("value")) not in (int, float)
                    or not math.isfinite(v["value"])):
                raise ValueError("MISSING_OR_BAD_FEATURE")
            if _utc(v.get("known_at_utc")) > cutoff:
                raise ValueError("FUTURE_FEATURE_LEAK")
        outcome = r.get("outcome_session")
        if outcome is None:
            if r.get("label") is not None or r.get("label_known_at_utc") is not None:
                raise ValueError("UNVERIFIED_OUTCOME_LABEL")
            continue
        if outcome not in ix or not 1 <= ix[outcome] - i <= 15:
            raise ValueError("INVALID_FUTURE_OUTCOME_SESSION")
        label = r.get("label")
        if type(label) not in (int, float) or not math.isfinite(label):
            raise ValueError("INVALID_OUTCOME_LABEL")
        label_time = _utc(r.get("label_known_at_utc"))
        if label_time <= cutoff or label_time.date() < _day(outcome):
            raise ValueError("OUTCOME_LABEL_LOOKAHEAD")
        if i >= boundary_i:
            holdout += 1
        elif ix[outcome] < boundary_i - embargo:
            train += 1
        else:
            purged += 1
    if train < 100 or holdout < 30:
        raise ValueError("INSUFFICIENT_TRAIN_OR_OOS")
    return {
        "schema": SCHEMA, "decision": "OFFLINE_EXPERIMENT_INPUT_ELIGIBLE_ONLY",
        "rows": len(rows), "train": train, "holdout": holdout, "purged": purged,
        "causality_proven": False, "alpha_proven": False,
        "production_enabled": False, "broker_enabled": False,
        "alerts_enabled": False, "attestations_externally_verified_by_this_code": False
    }
