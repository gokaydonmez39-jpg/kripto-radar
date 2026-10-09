#!/usr/bin/env python3
"""Operational source-readiness witness; never promotes market-cap or alpha.

The witness distinguishes a missing measured C4.17 MC bridge, exact source
SHA drift, absent unattended data credentials, and mere operator attestations.
It does not request market data, transmit secrets, alter canonical files,
or infer that provider permission equals automated-use entitlement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
SCHEMA = "XRAY_POST_MC_SOURCE_READINESS_WITNESS_V1"
MC_PREFIX = "nasdaq-xray/canonical_mc_bridge_"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
ASOF = re.compile(r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}$")
VERSION = re.compile(r"^v[1-9][0-9]*\.json$")


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def private_credential_classification(env: dict) -> dict:
    """Return public classification only; NEVER write key values to output."""
    alpaca_id = bool(str(env.get("XRAY_ALPACA_DATA_KEY_ID") or "").strip())
    alpaca_secret = bool(str(env.get("XRAY_ALPACA_DATA_SECRET_KEY") or "").strip())
    if alpaca_id and alpaca_secret:
        alpaca = "CREDENTIAL_PAIR_PRESENT_RIGHTS_UNVERIFIED"
    elif alpaca_id or alpaca_secret:
        alpaca = "CREDENTIAL_PAIR_PARTIAL"
    else:
        alpaca = "CREDENTIAL_PAIR_ABSENT"
    massive_key = bool(str(env.get("XRAY_MASSIVE_API_KEY") or "").strip())
    license_claim = str(env.get("XRAY_MASSIVE_NONDISPLAY_LICENSE_OK") or "").lower() == "true"
    proof_shape = bool(re.fullmatch(
        r"[0-9a-fA-F]{64}", str(env.get("XRAY_MASSIVE_LICENSE_EVIDENCE_SHA256") or "")
    ))
    return {
        "alpaca_history": alpaca,
        "massive_shadow": (
            "CREDENTIAL_AND_OPERATOR_ATTESTATION_PRESENT_RIGHTS_UNVERIFIED"
            if massive_key and license_claim and proof_shape else
            "BLOCKED_UNVERIFIED_CREDENTIAL_OR_NONDISPLAY_SCOPE"
        ),
        "bigdata_primary_runner": "NOT_ATTESTED_BY_THIS_WITNESS",
        "automated_use_rights_proven": False,
        "source_promotion_allowed": False,
    }


def summarize(objects: dict, blobs: dict, filenames: list[str], env: dict) -> dict:
    root = objects.get("root") or {}
    master = objects.get("master") or {}
    price = objects.get("price") or {}
    resolver = objects.get("resolver") or {}
    terminal = objects.get("terminal") or {}
    policy = objects.get("policy") or {}
    asof = root.get("asof_et")
    asof_exact = bool(
        isinstance(asof, str) and ASOF.fullmatch(asof)
        and asof == master.get("asof_et") == price.get("asof_et")
        == resolver.get("asof_et")
    )
    price_blob = blobs.get("nasdaq-xray/canonical_current_price_dv30.json")
    price_resolver_sha_exact = bool(
        isinstance(price_blob, str) and HEX40.fullmatch(price_blob)
        and resolver.get("source_price_blob_sha") == price_blob
    )
    try:
        price_count = int(price.get("pass_count", -1))
        resolver_count = int(resolver.get("source_price_pass_count", -2))
        blocked = int(resolver.get("price_blocked_count", -1))
        unknown = int(resolver.get("price_unknown_count", -1))
        master_unknown = int(master.get("unknown_count", -1))
    except (TypeError, ValueError):
        price_count, resolver_count = -1, -2
        blocked = unknown = master_unknown = -1
    scope_exact = bool(
        price_count >= 0 and price_count == resolver_count
        and blocked >= 0 and unknown >= 0 and master_unknown >= 0
        and price.get("unknown_never_pass") is True
        and master.get("unknown_never_pass") is True
        and root.get("execution") == "NONE"
        and root.get("real_money") == "NO-GO"
    )
    policy_mc = ((policy.get("hard_gates") or {}).get("market_cap"))
    policy_primary = ((policy.get("mc") or {}).get("primary"))
    policy_exact = bool(
        policy.get("version") == "C4.17"
        and policy_mc == ">=2000000000 USD"
        and isinstance(policy_primary, str)
        and policy_primary.startswith("Bigdata exact Nasdaq-family")
    )
    current_mc = []
    if asof_exact:
        prefix = MC_PREFIX + asof.replace("-", "") + "_c417_dv30_"
        current_mc = sorted(
            path for path in filenames
            if path.startswith(prefix) and VERSION.fullmatch(path[len(prefix):])
        )
    lineage_exact = asof_exact and price_resolver_sha_exact and scope_exact and policy_exact
    reason = (
        "SOURCE_LINEAGE_OR_POLICY_NOT_EXACT" if not lineage_exact else
        "CURRENT_MC_BRIDGE_ABSENT" if not current_mc else
        "MC_BRIDGE_PRESENT_AUTHORITY_STILL_UNVERIFIED"
    )
    return {
        "schema": SCHEMA,
        "asof_et": asof if isinstance(asof, str) else None,
        "root_asof_equals_master_price_resolver": asof_exact,
        "price_resolver_git_blob_exact": price_resolver_sha_exact,
        "price_resolver_pass_scope_exact": scope_exact,
        "compiled_mc_contract_exact": policy_exact,
        "current_mc_bridge_file_count": len(current_mc),
        "current_mc_bridge_file_presence_only": bool(current_mc),
        "current_mc_primary_measured_proven": False,
        "current_terminal_asof_et": terminal.get("asof_et"),
        "terminal_current_epoch_proven": False,
        "source_status": reason,
        "price_pass_count": price_count,
        "price_symbol_local_blocked": blocked,
        "price_symbol_local_unknown": unknown,
        "master_unknown_count": master_unknown,
        "credentials": private_credential_classification(env),
        "historical_sip_shadow_is_primary": False,
        "sec_shares_shadow_is_primary": False,
        "execution": "NONE",
        "real_money": "NO-GO",
        "alpha_authority": False,
        "candidate_registered": False,
        "phone_receipt_proven": False,
        "unknown_never_pass": True,
    }


def selftest() -> None:
    from copy import deepcopy
    pblob = "a" * 40
    objs = {
        "root": {"asof_et": "2026-10-08", "execution": "NONE", "real_money": "NO-GO"},
        "master": {"asof_et": "2026-10-08", "unknown_never_pass": True,
                   "unknown_count": 72},
        "price": {"asof_et": "2026-10-08", "unknown_never_pass": True,
                  "pass_count": 514},
        "resolver": {"asof_et": "2026-10-08", "source_price_blob_sha": pblob,
                     "source_price_pass_count": 514, "price_blocked_count": 45,
                     "price_unknown_count": 0},
        "terminal": {"asof_et": "2026-10-07"},
        "policy": {"version": "C4.17",
                   "hard_gates": {"market_cap": ">=2000000000 USD"},
                   "mc": {"primary": "Bigdata exact Nasdaq-family listing COMPANY"}},
    }
    blobs = {"nasdaq-xray/canonical_current_price_dv30.json": pblob}
    base = summarize(objs, blobs, [], {})
    assert base["source_status"] == "CURRENT_MC_BRIDGE_ABSENT"
    assert base["price_resolver_git_blob_exact"] is True
    assert base["price_symbol_local_blocked"] == 45
    assert base["credentials"]["alpaca_history"] == "CREDENTIAL_PAIR_ABSENT"
    assert not base["current_mc_primary_measured_proven"] and not base["alpha_authority"]
    with_file = summarize(objs, blobs,
        [MC_PREFIX + "20261008_c417_dv30_v1.json"], {})
    assert with_file["source_status"] == "MC_BRIDGE_PRESENT_AUTHORITY_STILL_UNVERIFIED"
    assert with_file["current_mc_primary_measured_proven"] is False
    for patch in [
        ("root", "asof_et", "2026-10-07"),
        ("price", "asof_et", "2026-10-07"),
        ("resolver", "source_price_blob_sha", "f" * 40),
        ("resolver", "source_price_pass_count", 513),
        ("master", "unknown_never_pass", False),
        ("policy", "version", "C4.18"),
        ("policy", "mc", {}),
    ]:
        case = deepcopy(objs)
        case[patch[0]][patch[1]] = patch[2]
        bad = summarize(case, blobs, [], {})
        assert bad["source_status"] == "SOURCE_LINEAGE_OR_POLICY_NOT_EXACT", patch
        assert bad["current_mc_primary_measured_proven"] is False
    assert summarize(objs, blobs,
        [MC_PREFIX + "20261007_c417_dv30_v28.json"], {})["current_mc_bridge_file_count"] == 0
    assert summarize(objs, blobs,
        [MC_PREFIX + "20261008_c417_dv30_vN.json"], {})["current_mc_bridge_file_count"] == 0
    assert private_credential_classification({
        "XRAY_ALPACA_DATA_KEY_ID": "example"})["alpaca_history"] == "CREDENTIAL_PAIR_PARTIAL"
    both = private_credential_classification({
        "XRAY_ALPACA_DATA_KEY_ID": "example", "XRAY_ALPACA_DATA_SECRET_KEY": "secret"})
    assert both["alpaca_history"] == "CREDENTIAL_PAIR_PRESENT_RIGHTS_UNVERIFIED"
    assert both["automated_use_rights_proven"] is False
    assert git_blob_sha(b"hello") == "b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0"
    print("XRAY_POST_MC_SOURCE_READINESS_SELFTEST=PASS_POSITIVE_NEGATIVE_NO_PRIMARY")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--out", default="/tmp/xray_post_mc_source_readiness.json")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    required = {
        "root": "orchestrator_state.json",
        "master": "canonical_current_master_manifest.json",
        "price": "canonical_current_price_dv30.json",
        "resolver": "canonical_current_resolver_request.json",
        "terminal": "canonical_current_terminal.json",
        "policy": "chatgpt_compiled_policy_v3.json",
    }
    objects = {}
    blobs = {}
    for key, name in required.items():
        b = (ROOT / name).read_bytes()
        obj = json.loads(b)
        if key == "policy":
            obj = json.loads(obj["payload_json"])
        objects[key] = obj
        blobs["nasdaq-xray/" + name] = git_blob_sha(b)
    filenames = [
        str(p.relative_to(REPO)).replace("\\", "/")
        for p in ROOT.glob("canonical_mc_bridge_*.json")
    ]
    report = summarize(objects, blobs, filenames, os.environ)
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("XRAY_POST_MC_SOURCE_READINESS=" + report["source_status"])
    print("XRAY_POST_MC_CREDENTIAL_CLASS=" + report["credentials"]["alpaca_history"])
    print("XRAY_POST_MC_MEASURED_PRIMARY_PROVEN=false")
    if report["source_status"] == "SOURCE_LINEAGE_OR_POLICY_NOT_EXACT":
        raise SystemExit("SOURCE_LINEAGE_OR_POLICY_NOT_EXACT_FAIL_CLOSED")


if __name__ == "__main__":
    main()
