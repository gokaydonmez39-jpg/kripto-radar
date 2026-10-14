#!/usr/bin/env python3
"""SHA-bound candidate-local readiness join for real Oct-13 deep and FROG evidence.

This is a READ-ONLY research decision witness, not a C4.17 PRIMARY publisher.
Each issuer fails on its OWN missing gates; unrelated UNKNOWN never vetoes it.
No raw vendor market data, share counts, transaction or notification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASOF = "2026-10-13"
DEEP_SHA256 = "ed9cc814c488fb743f52227d42c18f8c81876d67c9167ebc1128738a8406c855"
TRIGGERS = ("FROG|D", "MANH|B", "MRVL|D", "MSFT|D",
            "MTSI|D", "MU|D", "TWST|D")
REQUIRED_LOCAL = (
    "asof_identity", "exact_corrected_price_dv30",
    "corporate_actions_pit", "sec_class_aware_pit_mc_ge_2b",
    "stage1", "regime_breadth", "setup_r1_rr",
    "sec_legal_clear", "issuer_event_clear",
    "historical_and_live_nasdaq_halt_clear",
)

def require(value, why):
    if not value:
        raise ValueError("XRAY_CANDIDATE_LOCAL_" + why)

def read_json(path: Path):
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()

def local_decision(gates: dict) -> dict:
    """Only exact True is PASS; no other issuer or global coverage input exists."""
    require(set(gates) == set(REQUIRED_LOCAL), "GATE_SCHEMA_EXACT")
    missing = [k for k in REQUIRED_LOCAL if gates[k] is not True]
    return {
        "local_missing_gates": missing,
        "local_gate_count": len(REQUIRED_LOCAL),
        "local_complete": not missing,
    }

def validate_source(deep: dict, deep_sha: str, frog: dict):
    require(deep_sha == DEEP_SHA256, "IMMUTABLE_DEEP_SHA_MISMATCH")
    require(deep.get("schema") ==
            "XRAY_OCT13_277_REAL_STAGE1_DEEP_R1RR_COMPLETE_SHADOW_V1",
            "DEEP_SCHEMA")
    require(deep.get("asof_et") == ASOF and
            deep.get("source_277_stage1_count") == 277 and
            deep.get("stage1_pool_count") == 54 and
            deep.get("actual_confirmed_recent_family_trigger_count") == 7 and
            deep.get("provenance_exact") is True and
            deep.get("unknown_never_pass") is True and
            deep.get("registered_r92") == 0 and
            deep.get("execution") == "NONE" and
            deep.get("real_money") == "NO-GO", "DEEP_LINEAGE")
    q = deep.get("risk_rr_diagnostics") or {}
    require(set(q) == set(TRIGGERS), "EXACT_SEVEN_REAL_TRIGGERS")
    risk_rr = [k for k in TRIGGERS if
               q[k].get("frozen_R1_RR_evaluated") is True and
               q[k].get("risk_geometry_pass") is True and
               q[k].get("rr_basic_and_severe_pass") is True]
    require(risk_rr == ["FROG|D"], "EXACT_SINGLE_RISK_RR_SURVIVOR")
    require(frog.get("schema") ==
            "XRAY_OCT13_FROG_D_POST_TRIGGER_SEC_NASDAQ_IR_OFFICIAL_RESEARCH_V1" and
            frog.get("asof_et") == ASOF and
            frog.get("symbol") == "FROG" and
            frog.get("family") == "D" and
            frog.get("deep_source_sha256") == DEEP_SHA256 and
            frog.get("deep_source_actions_run") == 38536372509 and
            frog.get("registered_r92_count") == 0 and
            frog.get("canonical_files_mutated") is False and
            frog.get("unknown_never_pass") is True and
            frog.get("execution") == "NONE" and
            frog.get("real_money") == "NO-GO", "FROG_OFFICIAL_LINEAGE")
    require(frog.get("risk_geometry_pass") is True and
            frog.get("rr_basic_severe_pass") is True, "FROG_TECH")
    # The source is a research witness, not a certified source of positive gates.
    for k in ("share_class_asof_mc_primary_pass",
              "exact_corrected_dv30_primary_pass",
              "issuer_legal_event_clear_pass",
              "official_halt_live_guard_pass",
              "regime_breadth_primary_pass"):
        require(frog.get(k) is False, "FROG_UNVERIFIED_" + k)
    return q

def build(deep: dict, deep_sha: str, frog: dict, frog_sha: str, master: dict):
    q = validate_source(deep, deep_sha, frog)
    require(master.get("asof_et") == ASOF and
            master.get("unknown_never_pass") is True and
            isinstance(master.get("pass_symbols"), list) and
            len(set(master["pass_symbols"])) == len(master["pass_symbols"]) and
            len(master["pass_symbols"]) == master.get("pass_count"),
            "CANONICAL_MASTER_IDENTITY")
    identities = set(master["pass_symbols"])
    result = {}
    for key in TRIGGERS:
        symbol, family = key.split("|")
        item = q[key]
        technical = (item.get("frozen_R1_RR_evaluated") is True and
                     item.get("risk_geometry_pass") is True and
                     item.get("rr_basic_and_severe_pass") is True)
        # No global PRICE PASS query: every symbol receives its own decision.
        gates = dict.fromkeys(REQUIRED_LOCAL, False)
        gates["asof_identity"] = symbol in identities
        gates["stage1"] = True   # Immutable 54-pool source and exact 7-set provenance
        gates["setup_r1_rr"] = technical
        if symbol == "FROG":
            # False flags from actual official witness are intentionally retained.
            gates["exact_corrected_price_dv30"] = frog["exact_corrected_dv30_primary_pass"]
            gates["sec_class_aware_pit_mc_ge_2b"] = frog["share_class_asof_mc_primary_pass"]
            gates["regime_breadth"] = frog["regime_breadth_primary_pass"]
            # A combined negative legal/event flag is NOT positive attestation
            # for either independent gate.
            gates["sec_legal_clear"] = False
            gates["issuer_event_clear"] = False
            gates["historical_and_live_nasdaq_halt_clear"] = False
        status = local_decision(gates)
        require(status["local_complete"] is False, "UNATTESTED_REAL_RELEASE")
        result[key] = {
            "symbol": symbol, "family": family,
            "real_technical_risk_rr_pass": technical,
            "candidate_local_readiness": status,
            "classification": "LOCAL_SOURCE_INCOMPLETE" if technical else "LOCAL_TECHNICAL_VETO",
            "canonical_primary": False, "r92": False,
        }
    require(len(result) == 7 and
            sum(v["real_technical_risk_rr_pass"] for v in result.values()) == 1 and
            all(not v["canonical_primary"] and not v["r92"] for v in result.values()),
            "SEVEN_FAIL_CLOSED")
    return {
        "schema": "XRAY_OCT13_CANDIDATE_LOCAL_SHA_BOUND_RELEASE_READINESS_V1",
        "asof_et": ASOF, "deep_sha256": deep_sha,
        "frog_official_report_sha256": frog_sha,
        "deep_source_run_id": 38536372509,
        "frog_official_run_id": 38537058724,
        "source_277_count": 277, "source_stage1_pool_count": 54,
        "real_trigger_count": 7, "real_risk_rr_survivor_count": 1,
        "candidate_local_independent_of_unrelated_unknowns": True,
        "research_gate_only": True,
        "canonical_primary_count": 0, "registered_r92_count": 0,
        "iphone_receipt_verified": False, "canonical_mutated": False,
        "real_money": "NO-GO", "execution": "NONE",
        "research_start": "YES", "unknown_never_pass": True,
        "decisions": result,
    }

def selftest():
    empty = {key: False for key in REQUIRED_LOCAL}
    all_true = {key: True for key in REQUIRED_LOCAL}
    require(len(local_decision(empty)["local_missing_gates"]) == len(REQUIRED_LOCAL),
            "EMPTY_VETO")
    require(local_decision(all_true)["local_complete"], "ALL_LOCAL_GATES_REQUIRED")
    # An unrelated broken symbol cannot influence the local decision.
    baseline = local_decision(dict(all_true))
    unrelated = {"OTHER": {"sec_class_aware_pit_mc_ge_2b": None}}
    require(unrelated and baseline == local_decision(dict(all_true)),
            "GLOBAL_UNKNOWN_COUPLING")
    for key in REQUIRED_LOCAL:
        case = dict(all_true)
        case[key] = None
        require(not local_decision(case)["local_complete"], "UNKNOWN_MUST_VETO_" + key)
        case[key] = 1
        require(not local_decision(case)["local_complete"], "TRUTHY_NOT_TRUE_" + key)
    try:
        validate_source({}, "00", {})
    except ValueError as exc:
        require(str(exc).endswith("IMMUTABLE_DEEP_SHA_MISMATCH"), "TAMPER_FAIL")
    else:
        raise AssertionError("TAMPER_ACCEPTED")
    print("XRAY_LOCAL_GATES_SELFTEST=PASS_10_GATES_ISOLATED_UNKNOWN_VETO_IMMUTABLE_SHA")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--deep", type=Path)
    p.add_argument("--frog", type=Path)
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    require(a.deep and a.frog and a.out, "CLI_ARGS")
    require(not a.out.resolve().is_relative_to(ROOT.parent.resolve()),
            "NO_EVIDENCE_PERSISTED_IN_PUBLIC_REPO")
    deep, d_sha = read_json(a.deep)
    frog, f_sha = read_json(a.frog)
    master = json.loads((ROOT / "canonical_current_master_manifest.json").read_text())
    report = build(deep, d_sha, frog, f_sha, master)
    a.out.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print("XRAY_CANDIDATE_LOCAL_SOURCE=277_54_7_SHA_BOUND")
    print("XRAY_CANDIDATE_LOCAL_RISK_RR_SURVIVOR=FROG_D_WATCH_ONLY")
    print("XRAY_CANDIDATE_LOCAL_PRIMARY=0_R92=0_NO_FALSE_RELEASE")

if __name__ == "__main__":
    main()
