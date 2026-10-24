#!/usr/bin/env python3
"""Offline-only policy audit for GitHub research source manifests.

Strictly no external network, plug-in install, credentials, payments, order
placement, source ingestion, Sheet writes, push, or modification of live AL.
"""
import json
from pathlib import Path
import re

OLD = "research_github_11_sources_2026_10_24.json"
NEW = "research_mcp_11_sources_2026_10_24.json"
EXPECTED_OLD_PILOTS = {
    "goldmansachs/gs-quant", "shiyu-coder/Kronos", "openbq-org/OpenBB"
}
NEW_FINANCIAL_ACTION_DENIAL = {
    "stripe/ai", "coinbase/agentkit",
    "intuit/quickbooks-online-mcp-server",
    "XeroAPI/xero-mcp-server", "paypal/agent-toolkit"
}
FALSE_FIELDS = (
    "api_connected", "model_installed", "source_rights_verified",
    "point_in_time_verified", "production_eligible", "may_modify_al",
    "may_modify_stop_or_target", "may_write_sheet", "may_emit_alert",
    "may_place_order", "may_use_secrets", "may_send_money"
)

def _deny_if(condition, reason):
    if condition:
        raise ValueError(reason)

def validate_catalogues(old, new):
    _deny_if(not isinstance(old, dict) or not isinstance(new, dict),
             "CATALOGUE_REQUIRED")
    _deny_if(old.get("schema") != "XRAY_GITHUB_11_SOURCE_TRIAGE_V1" or
             new.get("schema") != "XRAY_GITHUB_MCP_11_SOURCE_TRIAGE_V1",
             "BAD_SOURCE_SCHEMA")
    prior, current = old.get("sources"), new.get("sources")
    _deny_if(not isinstance(prior, list) or len(prior) != 11 or
             not isinstance(current, list) or len(current) != 11,
             "SOURCE_COUNT_DRIFT")
    names_old = [s.get("repository") for s in prior]
    names_new = [s.get("repository") for s in current]
    _deny_if(any(not isinstance(n, str) or not n for n in names_old + names_new)
             or len(set(names_old)) != 11 or len(set(names_new)) != 11,
             "MISSING_OR_DUPLICATED_SOURCE")
    pilots = {s["repository"] for s in prior if s.get("decision") == "OFFLINE_PILOT"}
    _deny_if(pilots != EXPECTED_OLD_PILOTS, "RESEARCH_PILOT_SCOPE_CHANGED")
    for key, enabled in old.get("global_controls", {}).items():
        _deny_if(enabled is not False, "OLD_CATALOGUE_LIVE_PERMISSION")
    controls = new.get("global_safety")
    _deny_if(not isinstance(controls, dict) or not controls or
             any(v is not False for v in controls.values()),
             "NEW_CATALOGUE_LIVE_PERMISSION")
    _deny_if(new.get("count_unique_this_round") != 11 or
             new.get("new_unique_excluding_prior_openbb") != 10 or
             set(names_old).intersection(names_new) != {"openbq-org/OpenBB"},
             "OPENBB_DEDUP_INVALID")
    _deny_if(new.get("baseline_authority") != "ALPACA_IEX_XNAS_EOD_ONLY" or
             new.get("state") != "RESEARCH_CANDIDATES_STAGED_NO_PRODUCTION_INGESTION",
             "INVALID_MARKET_AUTHORITY")
    for item in current:
        _deny_if(not re.fullmatch(r"[a-f0-9]{40}", str(item.get("pinned_sha", ""))),
                 "UNPINNED_UPSTREAM_COMMIT")
        _deny_if(item.get("canonical_url") != "https://github.com/" + item["repository"],
                 "INVALID_SOURCE_URL")
        _deny_if(any(item.get(field) is not False for field in FALSE_FIELDS),
                 "SOURCE_PRIVILEGE_ESCALATION")
        _deny_if(not isinstance(item.get("blocking_reason"), str) or
                 not item["blocking_reason"],
                 "MISSING_RISK_EVIDENCE")
        repo = item["repository"]
        if repo in NEW_FINANCIAL_ACTION_DENIAL:
            _deny_if(item.get("decision") != "REJECT_OUT_OF_SCOPE",
                     "MONEY_TOOL_PROMOTION_FORBIDDEN")
        if repo == "alpacahq/alpaca-mcp-server":
            _deny_if(item.get("decision") != "OFFLINE_INTERFACE_REVIEW_ONLY",
                     "TRADING_MCP_PROMOTION_FORBIDDEN")
        if repo == "openbq-org/OpenBB":
            _deny_if(item.get("decision") != "ALREADY_REGISTERED_NO_DUPLICATE",
                     "OPENBB_DOUBLE_REGISTERED")
        if repo == "stefanoamorelli/sec-edgar-mcp":
            _deny_if(item.get("license") != "AGPL-3.0" or
                     item.get("decision") != "OFFLINE_SYNTHETIC_PILOT",
                     "SEC_MCP_RIGHTS_OR_SCOPE_CHANGED")
    return {
        "status": "REVIEW_ONLY_FAIL_CLOSED",
        "old_unique": len(set(names_old)), "new_unique": len(set(names_new)),
        "incremental_unique": 10,
        "old_offline_pilots": len(pilots),
        "new_offline_synthetic_pilots":
            sum(s["decision"] == "OFFLINE_SYNTHETIC_PILOT" for s in current),
        "production_eligible": False, "market_data_retrieved": False,
        "financial_actions_allowed": False, "actual_strategy_alpha_proven": False
    }

def main():
    here = Path(__file__).resolve().parent
    old = json.loads((here / OLD).read_text(encoding="utf-8"))
    new = json.loads((here / NEW).read_text(encoding="utf-8"))
    print(json.dumps(validate_catalogues(old, new), sort_keys=True))

if __name__ == "__main__":
    main()
