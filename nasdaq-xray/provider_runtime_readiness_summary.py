#!/usr/bin/env python3
"""Report *runner prerequisite presence* without treating it as data entitlement.

Consumes the existing XRAY provider_runner_access_audit output. It never sees
credentials, contacts vendors, or opens PRICE/MC data. The report is deliberately
operational: an operator claim plus a formatted hash never establish actual
redistribution, derived data, unattended-usage, or SIP rights.

Only ALPACA, MASSIVE, BUSINESSQUANT are mapped to runner secrets.
Everything else remains NOT_MAPPED/APP_ONLY/LIBRARY/NO_KEY as described by
the existing inventory. No deployment, broker/order or R92 authority.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from provider_runner_access_audit import EXPLICIT, PROVIDERS, SCHEMA as AUDIT_SCHEMA

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "XRAY_PROVIDER_RUNNER_PREREQUISITES_NO_AUTHORITY_V1"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ALLOWED_FLAGS = frozenset({
    "MISSING_GITHUB_RUNNER_KEY",
    "OPERATOR_RESEARCH_GRANT_NOT_CLAIMED",
    "LICENSE_EVIDENCE_SHA256_NOT_CONFIGURED",
})
OTHER_KEY_STATES = frozenset({
    "NOT_MAPPED", "PUBLIC_NO_KEY_REQUIRED", "LIBRARY_NOT_DATA_PROVIDER",
    "CHATGPT_APP_NOT_RUNNER_AUTHORITY",
})


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError("XRAY_PROVIDER_PREREQ_" + code)


def summarize(audit: object) -> dict:
    require(type(audit) is dict and audit.get("schema") == AUDIT_SCHEMA
            and audit.get("policy") == "C4.17"
            and audit.get("control") == "C4.27", "AUDIT_SCHEMA_POLICY")
    require(audit.get("execution") == "NONE"
            and audit.get("real_money") == "NO-GO"
            and audit.get("unknown_never_pass") is True
            and audit.get("no_external_http") is True
            and audit.get("price_not_read") is True
            and audit.get("api_calls") == 0
            and audit.get("can_create_primary") is False
            and audit.get("can_register_r92") is False
            and audit.get("licensed_non_display_derivative_rights_independently_verified") is False
            and audit.get("primary_price_created") == 0
            and audit.get("primary_mc_created") == 0
            and audit.get("r92_created") == 0, "AUDIT_FORGED_AUTHORITY")
    blob = audit.get("source_inventory_git_blob_sha")
    require(type(blob) is str and SHA40.fullmatch(blob) is not None, "SOURCE_SHA")
    rows = audit.get("providers")
    require(type(rows) is list and len(rows) == audit.get("provider_count") == 12
            and all(type(row) is dict for row in rows)
            and {row.get("id") for row in rows} == PROVIDERS
            and len({row["id"] for row in rows}) == len(rows),
            "EXACT_TWELVE_PROVIDER_SCOPE")
    out = []
    for row in sorted(rows, key=lambda x: x["id"]):
        sid = row["id"]
        require(all(row.get(flag) is False for flag in (
            "production_primary_authority",
            "independently_verified_legal_rights",
            "price_source_pass",
            "current_mc_primary_pass")), "SOURCE_FORGED_AUTHORITY")
        key = row.get("runner_key_presence")
        claimed = row.get("operator_unattended_research_claim")
        evidence = row.get("operator_evidence_hash_format")
        ready = row.get("safe_to_attempt_research_api")
        require(type(ready) is bool, "SOURCE_READY_TYPE")
        issues = []
        if sid in EXPLICIT:
            require(key in ("PRESENT", "MISSING")
                    and claimed in ("CLAIMED", "NOT_CLAIMED")
                    and evidence in ("VALID_FORMAT", "MISSING_OR_INVALID"),
                    "SOURCE_BAD_MAPPED_ENUM")
            if key != "PRESENT":
                issues.append("MISSING_GITHUB_RUNNER_KEY")
            if claimed != "CLAIMED":
                issues.append("OPERATOR_RESEARCH_GRANT_NOT_CLAIMED")
            if evidence != "VALID_FORMAT":
                issues.append("LICENSE_EVIDENCE_SHA256_NOT_CONFIGURED")
            require(set(issues).issubset(ALLOWED_FLAGS), "UNKNOWN_PREREQ")
            require(ready is (len(issues) == 0), "SOURCE_PREREQ_DRIFT")
            status = ("CONFIGURED_OPERATOR_PREREQUISITES_ONLY"
                      if not issues else "CONFIGURATION_BLOCKED")
        else:
            require(key in OTHER_KEY_STATES and claimed == "NOT_MAPPED"
                    and evidence == "NOT_MAPPED" and ready is False,
                    "UNMAPPED_SOURCE_CANNOT_PROMOTE")
            status = "NO_RUNNER_VENDOR_PERMISSION_MAPPING"
        out.append({
            "id": sid,
            "status": status,
            "blockers": issues,
            "runner_key_presence_only": key,
            "operator_grant_claim_only": claimed,
            "license_digest_format_only": evidence,
            "safe_to_attempt_research_api_flag_only": ready,
            "vendor_api_probe_performed": False,
            "independent_license_entitlement_verified": False,
            "can_create_PRIMARY": False,
            "can_create_HISTORY_PASS": False,
            "can_register_R92": False,
        })
    counts = {x["status"]: sum(p["status"] == x["status"] for p in out)
              for x in out}
    require(sum(counts.values()) == 12, "COUNT_DRIFT")
    return {
        "schema": SCHEMA,
        "effective_policy": "C4.17",
        "source_inventory_git_blob_sha": blob,
        "provider_count": 12,
        "providers": out,
        "status_counts": dict(sorted(counts.items())),
        "note": "Runner configuration only. Keys and operator-declared license SHA presence never prove vendor rights.",
        "live_vendor_data_fetched": False,
        "external_http_calls": 0,
        "independently_verified_vendor_license": False,
        "primary_created": False,
        "history_pass_created": False,
        "r92_created": False,
        "notifications_sent": False,
        "unknown_never_pass": True,
        "execution": "NONE",
        "real_money": "NO-GO",
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    opts = p.parse_args()
    require(not opts.out.resolve().is_relative_to(ROOT.resolve()),
            "PUBLIC_REPO_OUTPUT_FORBIDDEN")
    try:
        obj = json.loads(opts.audit.read_text(encoding="utf-8"),
                         parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        result = summarize(obj)
    except (OSError, ValueError, KeyError, TypeError):
        print("XRAY_PROVIDER_PREREQUISITES=DATA_BLOCKED_NO_VENDOR_CALLS")
        raise SystemExit(2) from None
    opts.out.parent.mkdir(parents=True, exist_ok=True)
    opts.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("XRAY_PROVIDER_PREREQUISITES=PASS_12_SOURCES_ZERO_VENDOR_CALLS_ZERO_ALPHA")
    for item in result["providers"]:
        if item["id"] in EXPLICIT:
            print("XRAY_RUNNER_" + item["id"] + "=" + item["status"]
                  + ":" + ",".join(item["blockers"] or ("NO_CONFIG_BLOCKER",)))


if __name__ == "__main__":
    main()
