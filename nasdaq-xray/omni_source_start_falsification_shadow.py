#!/usr/bin/env python3
"""XRAY source-wide start vs FINAL falsification: offline, zero-alpha only.

Checks 12 registered providers, seven immutable Git blobs, the ROOT history,
research launch and frozen C4.17/G9/successor controls. Read-only GitHub runner
inputs, no network/vendor API, third-party install, market bars, secrets,
orders, transactions, PRICE PASS, R92 registration or notification.
A green CI can be a stale safe-noop; it is never sufficient release evidence.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "XRAY_OMNI_SOURCE_RESEARCH_FINAL_START_SHADOW_V1"
FILES = {
    "inventory": "nasdaq-xray/c418_provider_inventory_20261012.json",
    "successor": "nasdaq-xray/source_successor_c418_proposal.json",
    "resolver": "nasdaq-xray/canonical_current_resolver_request.json",
    "master": "nasdaq-xray/canonical_current_master_manifest.json",
    "price": "nasdaq-xray/canonical_current_price_dv30.json",
    "root": "nasdaq-xray/orchestrator_state.json",
    "terminal": "nasdaq-xray/canonical_current_terminal.json",
    "final": "nasdaq-xray/canonical_current_final_gate_overlay.json",
    "g9": "nasdaq-xray/strict_g9_runtime_state.json",
    "research": "nasdaq-xray/research_only_start_20261010.json",
}
BINDINGS = {
    "master": ("source_master_path", "source_master_blob_sha",
               "nasdaq-xray/canonical_current_master_manifest.json"),
    "price": ("source_price_path", "source_price_blob_sha",
              "nasdaq-xray/canonical_current_price_dv30.json"),
    "overlay": ("source_overlay_path", "source_overlay_blob_sha",
                "nasdaq-xray/canonical_current_resolution_overlay.json"),
    "pointer": ("source_pointer_path", "source_pointer_blob_sha",
                "nasdaq-xray/chatgpt_canonical_state_v2.json"),
    "state": ("source_state_path", "source_state_blob_sha",
              "nasdaq-xray/canonical_current_full_state.json"),
    "unknowns": ("source_unknowns_path", "source_unknowns_blob_sha",
                 "nasdaq-xray/canonical_current_unknowns.json"),
    "policy": ("compiled_policy_path", "compiled_policy_blob_sha",
               "nasdaq-xray/chatgpt_compiled_policy_v3.json"),
}
IDS = frozenset({
    "SEC_EDGAR", "ALPACA", "RALLIES", "LONGBRIDGE", "MASSIVE", "FMP",
    "ALPHA_VANTAGE", "EODHD", "TIINGO", "NASDAQ_DATA_LINK_SHARADAR",
    "OPENBB", "BUSINESSQUANT"
})
CODE_ONLY = {
    "Graphify-Labs/graphify": "DEPENDENCY_AST_NO_DATA_RIGHTS",
    "ifixai-ai/iFixAi": "TRAJECTORY_AUDIT_NO_DATA_RIGHTS",
    "elie222/rakazo": "IDEMPOTENT_AGENTS_NO_DATA_RIGHTS",
    "farion1231/cc-switch": "MODEL_FAILOVER_NO_DATA_RIGHTS",
}

def need(flag, tag):
    if not flag:
        raise ValueError("XRAY_OMNI_SOURCE_" + tag)

def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def read_current(root=ROOT):
    base = Path(root).resolve(strict=True)
    a = {}
    for key, rel in FILES.items():
        path = base / rel
        need(path.resolve(strict=True).is_relative_to(base) and
             not path.is_symlink(), "CANONICAL_PATH_" + key)
        raw = path.read_bytes()
        need(len(raw) <= 16_000_000, "OVERSIZED_INPUT_" + key)
        a[key] = json.loads(raw,
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    r = a["resolver"]
    blobs = {}
    for key,(field,sfield,expected) in BINDINGS.items():
        need(r.get(field) == expected, "BOUND_FILE_PATH_" + key)
        path = base / expected
        need(path.resolve(strict=True).is_relative_to(base) and
             not path.is_symlink(), "BOUND_PATH_" + key)
        actual = git_blob(path.read_bytes())
        need(r.get(sfield) == actual, "GIT_SHA_DRIFT_" + key)
        blobs[key] = actual
    return a, blobs

def classify_ci(conclusion, log):
    """A CI 'success' after a stale SHA no-op is NOT readiness."""
    need(type(conclusion) is str and type(log) is str, "CI_INPUT_TYPE")
    if "XRAY_E2E_STALE_INVOCATION=SAFE_NOOP_NO_EVIDENCE" in log:
        return "STALE_SUCCESS_NO_READINESS_EVIDENCE"
    if "XRAY_RELEASE_GATE=NO_GO" in log:
        return "EXPLICIT_FINAL_NO_GO"
    return "CI_STATUS_NOT_SOURCE_OR_ALPHA_AUTHORITY"

def evaluate(a, blobs, latest_session=None):
    need(type(a) is dict and set(a) == set(FILES), "INPUT_SCOPE")
    need(type(blobs) is dict and set(blobs) == set(BINDINGS) and
         all(type(v) is str and len(v) == 40 for v in blobs.values()),
         "SEVEN_GIT_SHA_BINDINGS")
    inv, successor, resolver, m, p, root, terminal, final, g9, research = (
        a[k] for k in FILES)
    need(inv.get("schema") == "XRAY_C418_PROVIDER_FEASIBILITY_INVENTORY_V1"
         and inv.get("effective_policy") == "C4.17"
         and inv.get("successor_status") == "C4.18_PROPOSED_NOT_ACTIVATED"
         and inv.get("unknown_never_pass") is True
         and inv.get("no_provider_automatically_activated") is True,
         "INVENTORY_SCOPE")
    sources = inv.get("sources")
    need(type(sources) is list and len(sources) == 12 and
         all(type(x) is dict for x in sources) and
         {x.get("id") for x in sources} == IDS, "EXACT_12_PROVIDERS")
    need(all(x.get("runner_key_attested") is False and
             x.get("mc_current_exact") is False and
             type(x.get("rights_state")) is str for x in sources),
         "FAKE_LICENSE_OR_MC")
    need(successor.get("effective_production_policy") == "C4.17"
         and successor.get("activation_status") == "PROPOSED_NOT_ACTIVATED"
         and successor.get("can_create_PRIMARY") is False
         and successor.get("can_register_R92") is False
         and successor.get("automated_runner_entitlement_verified") is False,
         "C418_NOT_ACTIVATED")
    need(resolver.get("compiled_policy_version") == "C4.17"
         and resolver.get("status") == "READY"
         and resolver.get("unknown_never_pass") is True
         and resolver.get("execution") == "NONE"
         and resolver.get("real_money") == "NO-GO"
         and all(resolver.get(BINDINGS[k][1]) == blobs[k] for k in BINDINGS),
         "SEVEN_POLICY_SOURCE_SHA_BINDINGS")
    asof = resolver.get("asof_et")
    need(type(asof) is str and
         dt.date.fromisoformat(asof).isoformat() == asof, "ASOF")
    need(m.get("asof_et") == p.get("asof_et") == root.get("asof_et") == asof,
         "MASTER_PRICE_ROOT_ASOF")
    for x in (m,p,terminal):
        need(x.get("execution") == "NONE" and x.get("real_money") == "NO-GO"
             and x.get("unknown_never_pass") is True, "CANONICAL_SAFETY")
    need(type(m.get("unknown_symbols")) is list and
         type(p.get("unknown_symbols")) is list and
         type(p.get("pass_symbols")) is list and
         m.get("unknown_count") == len(m["unknown_symbols"]) and
         p.get("unknown_count") == len(p["unknown_symbols"]) and
         p.get("pass_count") == len(p["pass_symbols"]), "UNKNOWN_PARTITION")
    need(resolver.get("price_unknown_count") == p["unknown_count"] and
         resolver.get("source_price_pass_count") == p["pass_count"] and
         resolver.get("master_unknown_count") == m["unknown_count"],
         "RESOLVER_COUNTER_DRIFT")
    counts = root.get("history_unknown_reason_counts")
    need(root.get("unknown_reason_partition_exact") is True and
         type(counts) is dict and
         all(type(v) is int and v >= 0 for v in counts.values()) and
         sum(counts.values()) == root.get("unknown_count"),
         "ROOT_HISTORY_REASON_PARTITION")
    need(research.get("active") is True
         and research.get("policy") == "C4.17"
         and research.get("mode") == "RESEARCH_ONLY"
         and research.get("execution") == "NONE"
         and research.get("real_money") == "NO-GO"
         and research.get("unknown_never_pass") is True
         and all(research.get(k) is False for k in (
             "automatic_orders","broker_execution","source_rights_bypass",
             "historical_pit_bypass","alpha_threshold_relaxation",
             "final_production_go_claimed")), "RESEARCH_SAFETY")
    need(final.get("asof_et") == terminal.get("asof_et") and
         final.get("alpha_authority") is False and
         final.get("execution") == "NONE" and
         final.get("real_money") == "NO-GO", "TERMINAL_OVERLAY")
    need(g9.get("g9_pass") is False and g9.get("alpha_authority") is False
         and g9.get("status") == "BLOCKED_ENTITLEMENT_AUTHORITY_UNPROVEN",
         "G9_FALSE_AUTHORITY")
    if latest_session is not None:
        need(type(latest_session) is str and asof <= latest_session,
             "FUTURE_ASOF")
    obstacles = ["NO_VERIFIED_PRICE_DV30_SOURCE_RIGHTS",
                 "NO_LICENSED_CURRENT_MC_PIT_AND_INDEPENDENT_ORIGIN"]
    if p["unknown_count"] or p["pass_count"] == 0:
        obstacles.append("PRICE_DV30_UNRESOLVED")
    if root["unknown_count"]:
        obstacles.append("ROOT_HISTORY_UNRESOLVED")
    if m["unknown_count"]:
        obstacles.append("MASTER_IDENTITY_UNRESOLVED")
    if terminal["asof_et"] != asof:
        obstacles.append("CURRENT_TERMINAL_STALE")
    if latest_session is not None and asof != latest_session:
        obstacles.append("LATEST_OFFICIAL_SESSION_STALE")
    obstacles.append("STRICT_G9_LICENSE_NOT_ATTESTED")
    return {
      "schema": SCHEMA,
      "policy": "C4.17",
      "asof_et": asof,
      "inventory_observed_date": inv.get("observed_date"),
      "provider_count": len(sources),
      "providers": [{"id":x["id"],"role":x["role"],
                     "rights_for_primary":False,"can_create_R92":False}
                    for x in sorted(sources,key=lambda z:z["id"])],
      "engineering_repos_are_not_market_providers": CODE_ONLY,
      "exact_git_blob_edges": len(blobs),
      "master_unknown_count": m["unknown_count"],
      "price_unknown_count": p["unknown_count"],
      "price_primary_pass_count": p["pass_count"],
      "root_history_unknown_count": root["unknown_count"],
      "terminal_asof_et": terminal["asof_et"],
      "research_start": "CONFIGURED_READ_ONLY_MONITORING",
      "signal_start": "BLOCKED_NO_PRIMARY_NO_R92",
      "final_release": "NO_GO",
      "blockers": obstacles,
      "new_primary_created": False,
      "new_r92_created": False,
      "notifications_sent": False,
      "market_vendor_calls": 0,
      "unknown_never_pass": True,
      "execution": "NONE",
      "real_money": "NO-GO",
    }

def selftest():
    a, blobs = read_current()
    report = evaluate(a, blobs)
    need(report["provider_count"] == 12 and
         report["exact_git_blob_edges"] == 7 and
         report["signal_start"] == "BLOCKED_NO_PRIMARY_NO_R92" and
         report["research_start"] == "CONFIGURED_READ_ONLY_MONITORING",
         "REAL_CURRENT_NO_ALPHA")
    need(classify_ci("success",
        "XRAY_E2E_STALE_INVOCATION=SAFE_NOOP_NO_EVIDENCE") ==
        "STALE_SUCCESS_NO_READINESS_EVIDENCE", "GREEN_STALE_NOOP")
    need(classify_ci("success", "XRAY_RELEASE_GATE=NO_GO") ==
        "EXPLICIT_FINAL_NO_GO", "RELEASE_GREEN_NO_GO")
    mutations = [
      ("REMOVE_PROVIDER",lambda a,b:a["inventory"]["sources"].pop()),
      ("FORGE_RUNNER_ENTITLEMENT",lambda a,b:a["inventory"]["sources"][0].update(runner_key_attested=True)),
      ("FORGE_MC_PASS",lambda a,b:a["inventory"]["sources"][0].update(mc_current_exact=True)),
      ("ACTIVATE_SUCCESSOR",lambda a,b:a["successor"].update(activation_status="ACTIVATED")),
      ("PROMOTE_SUCCESSOR",lambda a,b:a["successor"].update(can_create_PRIMARY=True)),
      ("FAKE_PRICE_COUNT",lambda a,b:a["resolver"].update(source_price_pass_count=1)),
      ("HIDE_PRICE_UNKNOWN",lambda a,b:a["resolver"].update(price_unknown_count=0)),
      ("FORGE_PRICE_SHA",lambda a,b:a["resolver"].update(source_price_blob_sha="0"*40)),
      ("FORGE_PROOF_SHA",lambda a,b:b.update(price="0"*40)),
      ("FUTURE_ROOT",lambda a,b:a["root"].update(asof_et="2099-01-01")),
      ("ROOT_COUNT_DRIFT",lambda a,b:a["root"].update(unknown_count=99)),
      ("FAKE_G9",lambda a,b:a["g9"].update(g9_pass=True)),
      ("FAKE_FINAL_AUTHORITY",lambda a,b:a["final"].update(alpha_authority=True)),
      ("FORGE_TERMINAL_ASOF",lambda a,b:a["terminal"].update(asof_et=a["resolver"]["asof_et"])),
      ("BROKER_ACTION",lambda a,b:a["research"].update(automatic_orders=True)),
      ("WEAKEN_RISK",lambda a,b:a["research"].update(alpha_threshold_relaxation=True)),
      ("DISABLE_RESEARCH",lambda a,b:a["research"].update(active=False)),
      ("BROKEN_MASTER_UNKNOWN",lambda a,b:a["master"].update(unknown_count=0)),
      ("FAKE_C418_VERSION",lambda a,b:a["resolver"].update(compiled_policy_version="C4.18")),
      ("UNKNOWN_PROVIDER",lambda a,b:a["inventory"]["sources"][0].update(id="FAKE_VENDOR")),
    ]
    for tag, edit in mutations:
        ax,bx=copy.deepcopy(a),copy.deepcopy(blobs)
        edit(ax,bx)
        try:
            evaluate(ax,bx)
        except (ValueError,KeyError,TypeError):
            continue
        raise RuntimeError("XRAY_OMNI_UNSAFE_MUTATION_ACCEPTED_"+tag)
    need(len(mutations)==20,"NEGATIVE_COUNT")
    print("XRAY_OMNI_START=PASS_20_NEGATIVES_12_PROVIDERS_7_SHA_NO_VENDOR_NO_PRIMARY_NO_R92")

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--check-current",action="store_true")
    args=parser.parse_args()
    if args.selftest:
        selftest()
    elif args.check_current:
        a,blobs=read_current()
        report=evaluate(a,blobs)
        print(json.dumps(report,sort_keys=True,ensure_ascii=False,allow_nan=False))
        print("XRAY_OMNI_RESEARCH_START=CONFIGURED_NO_ALPHA")
        print("XRAY_OMNI_FINAL=NO_GO")
    else:
        parser.error("Explicit --selftest or --check-current only")
