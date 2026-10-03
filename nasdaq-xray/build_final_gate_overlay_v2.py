#!/usr/bin/env python3
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"canonical_current_final_gate_overlay.json"

FILES={
    "terminal":"canonical_current_terminal.json",
    "pointer":"chatgpt_canonical_state_v2.json",
    "g9_runtime":"strict_g9_runtime_state.json",
    "g9_authority":"g9_entitlement_authority.json",
    "g9_saturation":"g9_search_saturation_20261003.json",
    "g9_registry":"g9_provider_registry_20261003.json",
    "account_gate":"account_gate_contract.json",
    "account_adapter":"account_provider_adapter_contract.json",
}

def path(k):
    return ROOT/FILES[k]

def load(k):
    return json.loads(path(k).read_text())

def blob_sha(k):
    b=path(k).read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def main():
    t,p,gr,ga,gs,greg,ag,aa=[load(k) for k in FILES]

    for name,obj in [
        ("terminal",t),("pointer",p),("g9_runtime",gr),("g9_authority",ga),
        ("g9_saturation",gs),("g9_registry",greg),("account_gate",ag),("account_adapter",aa)
    ]:
        assert obj.get("execution")=="NONE", f"{name}:EXECUTION_NOT_NONE"
        assert obj.get("real_money")=="NO-GO", f"{name}:REAL_MONEY_NOT_NO_GO"

    ps=p.get("state_json") or {}
    assert t.get("asof_et")==ps.get("asof_et"), "TERMINAL_POINTER_ASOF_MISMATCH"

    full=bool(t.get("full_end_to_end_research_pass"))
    g9_pass=gr.get("g9_pass") is True
    persisted_account_status=str(ag.get("current_status") or "UNKNOWN")
    terminal_account_status=str(t.get("account_status") or persisted_account_status)
    account_status=terminal_account_status
    account_pass=account_status in {"PASS","ACCOUNT_PASS"}
    pre_g9=int((t.get("counts") or {}).get("pre_g9_tech_pass") or 0)

    actual_aa=blob_sha("account_adapter")
    bound_aa=(ag.get("adapter_contract") or {}).get("blob_sha")
    account_exact=bound_aa==actual_aa

    actual_sat=blob_sha("g9_saturation")
    actual_reg=blob_sha("g9_registry")
    bound_sat=(ga.get("search_saturation") or {}).get("blob_sha")
    bound_reg=(ga.get("negative_registry") or {}).get("blob_sha")
    sat_count=int(gs.get("unique_provider_paths_reviewed") or 0)
    reg_count=int(greg.get("provider_count") or 0)
    auth_sat_count=int((ga.get("search_saturation") or {}).get("unique_provider_paths_reviewed") or 0)
    auth_reg_count=int((ga.get("negative_registry") or {}).get("provider_count") or 0)
    g9_sha_exact=bound_sat==actual_sat and bound_reg==actual_reg
    g9_count_exact=(sat_count==reg_count==auth_sat_count==auth_reg_count)

    # BLOCKED gates remain fail-closed even when negative-evidence caches advance.
    # A PASS claim is different: current exact bindings are mandatory.
    account_live=(t.get("evidence") or {}).get("account_live_probe") or {}
    account_same_run_attested=(
        account_live.get("provider")=="LONGBRIDGE_DIRECT_OPENAPI"
        and account_live.get("status")=="PASS"
        and account_live.get("same_run_attested") is True
        and account_live.get("network_attempted") is True
        and account_live.get("balance_parseable") is True
        and account_live.get("positions_parseable") is True
        and account_live.get("private_values_persisted") is False
        and account_live.get("secret_values_persisted") is False
        and bool(account_live.get("workflow_run_id"))
    )
    if account_pass:
        assert account_exact, (
            f"ACCOUNT_PASS_REQUIRES_EXACT_ADAPTER_BINDING bound={bound_aa} actual={actual_aa}"
        )
        assert account_same_run_attested, "ACCOUNT_PASS_REQUIRES_SAME_RUN_LIVE_WITNESS"
    if g9_pass:
        assert str(ga.get("status") or "")=="PROVEN", "G9_PASS_REQUIRES_PROVEN_AUTHORITY"
        assert g9_sha_exact, (
            f"G9_PASS_REQUIRES_EXACT_CACHE_BINDINGS sat={bound_sat}/{actual_sat} reg={bound_reg}/{actual_reg}"
        )
        assert g9_count_exact, (
            f"G9_PASS_REQUIRES_EXACT_COUNTS sat={sat_count} reg={reg_count} auth_sat={auth_sat_count} auth_reg={auth_reg_count}"
        )

    binding_safe=((not account_pass or account_exact) and
                  (not g9_pass or (g9_sha_exact and g9_count_exact)))
    assert binding_safe, "FINAL_GATE_BINDING_NOT_FAIL_CLOSED"

    required=["FULL_E2E_RESEARCH_PASS","STRICT_G9_PASS","SAME_RUN_ACCOUNT_PASS"]
    checks={
        "FULL_E2E_RESEARCH_PASS":full,
        "STRICT_G9_PASS":g9_pass,
        "SAME_RUN_ACCOUNT_PASS":account_pass,
    }
    passed=[k for k,v in checks.items() if v]
    blocked=[k for k,v in checks.items() if not v]

    now_utc=datetime.now(timezone.utc)
    now_et=now_utc.astimezone(ZoneInfo("America/New_York"))
    asof=str(t.get("asof_et"))

    out={
        "schema":"XRAY_FINAL_GATE_OVERLAY_V2",
        "generated_on":now_et.date().isoformat(),
        "generated_at_utc":now_utc.isoformat(),
        "asof_et":asof,
        "execution":"NONE",
        "real_money":"NO-GO",
        "alpha_authority":False,
        "binding_protocol":"FAIL_CLOSED_BLOCKED_CACHE_DRIFT_V1",
        "source_terminal":{
            "path":"nasdaq-xray/"+FILES["terminal"],
            "blob_sha":blob_sha("terminal"),
            "full_end_to_end_research_pass":full,
            "terminal_result":t.get("terminal_result"),
        },
        "source_pointer":{
            "path":"nasdaq-xray/"+FILES["pointer"],
            "blob_sha":blob_sha("pointer"),
            "revision":p.get("revision"),
            "status":ps.get("status"),
            "legacy_account_status":ps.get("account_status"),
        },
        "strict_g9":{
            "status":gr.get("status"),
            "g9_pass":g9_pass,
            "provider":gr.get("provider"),
            "adapter_status":gr.get("adapter_status"),
            "authority_path":"nasdaq-xray/"+FILES["g9_authority"],
            "authority_blob_sha":blob_sha("g9_authority"),
            "runtime_path":"nasdaq-xray/"+FILES["g9_runtime"],
            "runtime_blob_sha":blob_sha("g9_runtime"),
            "current_saturation_blob_sha":actual_sat,
            "current_registry_blob_sha":actual_reg,
            "authority_bound_saturation_blob_sha":bound_sat,
            "authority_bound_registry_blob_sha":bound_reg,
            "current_saturation_count":sat_count,
            "current_registry_count":reg_count,
            "authority_saturation_count":auth_sat_count,
            "authority_registry_count":auth_reg_count,
            "negative_cache_binding_exact":g9_sha_exact and g9_count_exact,
            "negative_cache_ahead_while_blocked":(not g9_pass) and not (g9_sha_exact and g9_count_exact),
        },
        "account":{
            "status":account_status,
            "account_pass":account_pass,
            "provider_model":ag.get("provider"),
            "current_adapter":("LONGBRIDGE_DIRECT_OPENAPI" if account_pass else ag.get("current_adapter")),
            "persisted_gate_status":persisted_account_status,
            "same_run_live_witness_attested":account_same_run_attested,
            "live_probe_workflow_run_id":account_live.get("workflow_run_id"),
            "gate_path":"nasdaq-xray/"+FILES["account_gate"],
            "gate_blob_sha":blob_sha("account_gate"),
            "current_adapter_contract_blob_sha":actual_aa,
            "gate_bound_adapter_contract_blob_sha":bound_aa,
            "adapter_binding_exact":account_exact,
            "adapter_drift_while_blocked":(not account_pass) and not account_exact,
        },
        "binding_integrity":{
            "fail_closed_safe":binding_safe,
            "pass_requires_exact_current_bindings":True,
            "g9_pass_binding_exact":(not g9_pass) or (g9_sha_exact and g9_count_exact),
            "account_pass_binding_exact":(not account_pass) or account_exact,
            "blocked_negative_evidence_may_advance_without_creating_pass":True,
        },
        "research_delivery":{
            "independent_of_g9_account":True,
            "pre_g9_tech_pass":pre_g9,
            "current_asof_has_deliverable_candidate":pre_g9>0,
            "reason":"PRE_G9_TECH_PASS_POSITIVE" if pre_g9>0 else "PRE_G9_TECH_PASS_ZERO",
        },
        "true_full_go":{
            "status":"PASS" if all(checks.values()) else "BLOCKED",
            "required":required,
            "passed":passed,
            "blocked":blocked,
        },
        "stale_pointer_fields":{
            "pointer_account_status":ps.get("account_status"),
            "terminal_account_status":t.get("account_status"),
            "interpretation":"Persisted pointer state never creates PASS; current runtime gates control final-gate reporting.",
        },
        "weekend_guard":{
            "current_calendar_date":now_et.date().isoformat(),
            "last_completed_us_rth_asof":asof,
            "asof_advanced_on_weekend":bool(now_et.weekday()>=5 and asof==now_et.date().isoformat()),
        },
        "no_policy_weakening":True,
    }
    OUT.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({
        "overlay":"PASS",
        "schema":out["schema"],
        "asof_et":asof,
        "full_e2e":full,
        "g9_pass":g9_pass,
        "account_pass":account_pass,
        "true_full_go":out["true_full_go"]["status"],
        "pre_g9_tech_pass":pre_g9,
        "binding_fail_closed_safe":binding_safe,
        "g9_negative_cache_exact":g9_sha_exact and g9_count_exact,
        "authority_saturation_count":auth_sat_count,
        "authority_registry_count":auth_reg_count,
        "account_adapter_exact":account_exact,
    },sort_keys=True))

if __name__=="__main__":
    main()
