#!/usr/bin/env python3
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"canonical_current_final_gate_overlay.json"

PATHS={
    "terminal": ROOT/"canonical_current_terminal.json",
    "pointer": ROOT/"chatgpt_canonical_state_v2.json",
    "g9_runtime": ROOT/"strict_g9_runtime_state.json",
    "g9_authority": ROOT/"g9_entitlement_authority.json",
    "g9_saturation": ROOT/"g9_search_saturation_20261003.json",
    "g9_registry": ROOT/"g9_provider_registry_20261003.json",
    "account_gate": ROOT/"account_gate_contract.json",
    "account_adapter": ROOT/"account_provider_adapter_contract.json",
}

def load(p):
    return json.loads(p.read_text())

def blob_sha(p):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\\0".encode()+b).hexdigest()

def main():
    t=load(PATHS["terminal"])
    p=load(PATHS["pointer"])
    gr=load(PATHS["g9_runtime"])
    ga=load(PATHS["g9_authority"])
    gs=load(PATHS["g9_saturation"])
    greg=load(PATHS["g9_registry"])
    ag=load(PATHS["account_gate"])
    aa=load(PATHS["account_adapter"])

    assert t.get("execution")=="NONE" and t.get("real_money")=="NO-GO"
    assert p.get("execution")=="NONE" and p.get("real_money")=="NO-GO"
    assert gr.get("execution")=="NONE" and gr.get("real_money")=="NO-GO"
    assert ga.get("execution")=="NONE" and ga.get("real_money")=="NO-GO"
    assert gs.get("execution")=="NONE" and gs.get("real_money")=="NO-GO"
    assert greg.get("execution")=="NONE" and greg.get("real_money")=="NO-GO"
    assert ag.get("execution")=="NONE" and ag.get("real_money")=="NO-GO"
    assert aa.get("execution")=="NONE" and aa.get("real_money")=="NO-GO"

    ps=p.get("state_json") or {}
    assert t.get("asof_et")==ps.get("asof_et"), "TERMINAL_POINTER_ASOF_MISMATCH"

    actual_aa=blob_sha(PATHS["account_adapter"])
    bound_aa=(ag.get("adapter_contract") or {}).get("blob_sha")
    assert bound_aa==actual_aa, f"ACCOUNT_ADAPTER_BINDING_MISMATCH bound={bound_aa} actual={actual_aa}"

    actual_sat=blob_sha(PATHS["g9_saturation"])
    bound_sat=(ga.get("search_saturation") or {}).get("blob_sha")
    assert bound_sat==actual_sat, f"G9_SATURATION_BINDING_MISMATCH bound={bound_sat} actual={actual_sat}"

    actual_reg=blob_sha(PATHS["g9_registry"])
    bound_reg=(ga.get("negative_registry") or {}).get("blob_sha")
    assert bound_reg==actual_reg, f"G9_REGISTRY_BINDING_MISMATCH bound={bound_reg} actual={actual_reg}"

    sat_count=int(gs.get("unique_provider_paths_reviewed") or 0)
    reg_count=int(greg.get("provider_count") or 0)
    auth_count=int((ga.get("current_evidence") or {}).get("reviewed_provider_paths") or 0)
    assert sat_count==reg_count==auth_count, (
        f"G9_PROVIDER_COUNT_BINDING_MISMATCH saturation={sat_count} registry={reg_count} authority={auth_count}"
    )

    full=bool(t.get("full_end_to_end_research_pass"))
    g9_pass=gr.get("g9_pass") is True
    account_status=str(ag.get("current_status") or "UNKNOWN")
    account_pass=account_status in {"PASS","ACCOUNT_PASS"}
    pre_g9=int((t.get("counts") or {}).get("pre_g9_tech_pass") or 0)

    required=["FULL_E2E_RESEARCH_PASS","STRICT_G9_PASS","SAME_RUN_ACCOUNT_PASS"]
    passed=[]
    blocked=[]
    for name,ok in [
        ("FULL_E2E_RESEARCH_PASS",full),
        ("STRICT_G9_PASS",g9_pass),
        ("SAME_RUN_ACCOUNT_PASS",account_pass),
    ]:
        (passed if ok else blocked).append(name)

    now_et=datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
    weekend=now_et.weekday()>=5
    asof=str(t.get("asof_et"))

    out={
      "schema":"XRAY_FINAL_GATE_OVERLAY_V1",
      "generated_on":now_et.date().isoformat(),
      "generated_at_utc":datetime.now(timezone.utc).isoformat(),
      "asof_et":asof,
      "execution":"NONE",
      "real_money":"NO-GO",
      "alpha_authority":False,
      "source_terminal":{
        "path":"nasdaq-xray/canonical_current_terminal.json",
        "blob_sha":blob_sha(PATHS["terminal"]),
        "full_end_to_end_research_pass":full,
        "terminal_result":t.get("terminal_result"),
      },
      "source_pointer":{
        "path":"nasdaq-xray/chatgpt_canonical_state_v2.json",
        "blob_sha":blob_sha(PATHS["pointer"]),
        "revision":p.get("revision"),
        "status":ps.get("status"),
        "legacy_account_status":ps.get("account_status"),
      },
      "strict_g9":{
        "status":gr.get("status"),
        "g9_pass":g9_pass,
        "provider":gr.get("provider"),
        "adapter_status":gr.get("adapter_status"),
        "authority_path":"nasdaq-xray/g9_entitlement_authority.json",
        "authority_blob_sha":blob_sha(PATHS["g9_authority"]),
        "runtime_path":"nasdaq-xray/strict_g9_runtime_state.json",
        "runtime_blob_sha":blob_sha(PATHS["g9_runtime"]),
        "saturation_path":"nasdaq-xray/g9_search_saturation_20261003.json",
        "saturation_blob_sha":actual_sat,
        "registry_path":"nasdaq-xray/g9_provider_registry_20261003.json",
        "registry_blob_sha":actual_reg,
        "provider_paths_reviewed":sat_count,
        "provider_registry_count":reg_count,
        "authority_reviewed_count":auth_count,
      },
      "account":{
        "status":account_status,
        "account_pass":account_pass,
        "provider_model":ag.get("provider"),
        "current_adapter":ag.get("current_adapter"),
        "gate_path":"nasdaq-xray/account_gate_contract.json",
        "gate_blob_sha":blob_sha(PATHS["account_gate"]),
        "adapter_contract_path":"nasdaq-xray/account_provider_adapter_contract.json",
        "adapter_contract_blob_sha":actual_aa,
      },
      "research_delivery":{
        "independent_of_g9_account":True,
        "pre_g9_tech_pass":pre_g9,
        "current_asof_has_deliverable_candidate":pre_g9>0,
        "reason":"PRE_G9_TECH_PASS_POSITIVE" if pre_g9>0 else "PRE_G9_TECH_PASS_ZERO",
      },
      "true_full_go":{
        "status":"PASS" if full and g9_pass and account_pass else "BLOCKED",
        "required":required,
        "passed":passed,
        "blocked":blocked,
      },
      "stale_pointer_fields":{
        "pointer_account_status":ps.get("account_status"),
        "terminal_account_status":t.get("account_status"),
        "interpretation":"Pointer account field is legacy final-gate state unless refreshed by canonical CAS. Current terminal plus exact-bound ACCOUNT contract govern gate reporting; persisted state never creates PASS.",
      },
      "weekend_guard":{
        "current_calendar_date":now_et.date().isoformat(),
        "last_completed_us_rth_asof":asof,
        "asof_advanced_on_weekend":bool(weekend and asof==now_et.date().isoformat()),
      },
      "no_policy_weakening":True,
    }
    OUT.write_text(json.dumps(out,indent=2,sort_keys=False)+"\n")
    print(json.dumps({
      "overlay":"PASS",
      "asof_et":asof,
      "full_e2e":full,
      "g9_pass":g9_pass,
      "account_pass":account_pass,
      "true_full_go":out["true_full_go"]["status"],
      "pre_g9_tech_pass":pre_g9,
    },sort_keys=True))

if __name__=="__main__":
    main()
