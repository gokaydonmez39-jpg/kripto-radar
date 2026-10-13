#!/usr/bin/env python3
"""Runtime runner access inventory for 12 XRAY sources (no network, no secrets).

This is a proof of *config presence only*, not an entitlement validation.
No upstream symbol, vendor record, PRICE, MC, trade, R92, or alpha writes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
INVENTORY=ROOT/"c418_provider_inventory_20261012.json"
SCHEMA="XRAY_PROVIDER_RUNNER_ACCESS_READINESS_V1"
EXPLICIT={
    "ALPACA":{"secrets":("XRAY_ALPACA_API_KEY_ID","XRAY_ALPACA_API_SECRET_KEY"),
       "grant":"XRAY_ALPACA_SIP_HISTORY_RESEARCH_LICENSE_OK",
       "evidence":"XRAY_ALPACA_SIP_HISTORY_LICENSE_EVIDENCE_SHA256"},
    "MASSIVE":{"secrets":("XRAY_MASSIVE_API_KEY",),
       "grant":"XRAY_MASSIVE_UNATTENDED_RESEARCH_LICENSE_OK",
       "evidence":"XRAY_MASSIVE_LICENSE_EVIDENCE_SHA256"},
    "BUSINESSQUANT":{"secrets":("XRAY_BQ_API_KEY",),
       "grant":"XRAY_BQ_UNATTENDED_RESEARCH_LICENSE_OK",
       "evidence":"XRAY_BQ_LICENSE_EVIDENCE_SHA256"},
}
PROVIDERS=frozenset(("SEC_EDGAR","ALPACA","RALLIES","LONGBRIDGE","MASSIVE",
    "FMP","ALPHA_VANTAGE","EODHD","TIINGO","NASDAQ_DATA_LINK_SHARADAR",
    "OPENBB","BUSINESSQUANT"))
SECRET_NAMES=frozenset(
    x for cfg in EXPLICIT.values()
    for x in (*cfg["secrets"],cfg["grant"],cfg["evidence"])
)

def gitblob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def analyze(inv,env,raw):
    rows=inv.get("sources")
    if (inv.get("schema")!="XRAY_C418_PROVIDER_FEASIBILITY_INVENTORY_V1"
        or inv.get("effective_policy")!="C4.17"
        or inv.get("execution")!="NONE" or inv.get("real_money")!="NO-GO"
        or inv.get("unknown_never_pass") is not True
        or inv.get("no_provider_automatically_activated") is not True
        or not isinstance(rows,list) or len(rows)!=12
        or {x.get("id") for x in rows if type(x) is dict}!=PROVIDERS):
        raise ValueError("INVENTORY_SCOPE_OR_POLICY_DRIFT")
    out=[]
    for p in rows:
        sid=p["id"]
        config=EXPLICIT.get(sid)
        record={"id":sid,"runner_key_presence":"NOT_MAPPED",
            "operator_unattended_research_claim":"NOT_MAPPED",
            "operator_evidence_hash_format":"NOT_MAPPED",
            "safe_to_attempt_research_api":False,
            "production_primary_authority":False,
            "independently_verified_legal_rights":False,
            "price_source_pass":False,
            "current_mc_primary_pass":False}
        if config:
            present=all(bool(str(env.get(x,"")).strip()) for x in config["secrets"])
            grant=str(env.get(config["grant"],"")).strip().lower()=="true"
            digest=env.get(config["evidence"],"")
            valid_evidence=(isinstance(digest,str) and
                re.fullmatch("[0-9a-f]{64}",digest) is not None)
            record.update({
                "runner_key_presence":"PRESENT" if present else "MISSING",
                "operator_unattended_research_claim":"CLAIMED" if grant else "NOT_CLAIMED",
                "operator_evidence_hash_format":"VALID_FORMAT" if valid_evidence else "MISSING_OR_INVALID",
                # All 3 are prerequisites for any already-permitted bounded
                # shadow probe. Presence/attestation do not imply rights.
                "safe_to_attempt_research_api":bool(present and grant and valid_evidence),
            })
        elif sid=="SEC_EDGAR":
            record["runner_key_presence"]="PUBLIC_NO_KEY_REQUIRED"
        elif sid=="OPENBB":
            record["runner_key_presence"]="LIBRARY_NOT_DATA_PROVIDER"
        elif sid in ("RALLIES","LONGBRIDGE"):
            record["runner_key_presence"]="CHATGPT_APP_NOT_RUNNER_AUTHORITY"
        out.append(record)
    answer={"schema":SCHEMA,"policy":"C4.17","control":"C4.27",
        "source_inventory_git_blob_sha":gitblob(raw),
        "provider_count":len(out),"providers":sorted(out,key=lambda x:x["id"]),
        "interactive_plugin_access_not_github_runner_access":True,
        "keys_examined_in_memory_not_persisted":True,
        "no_external_http":True,"api_calls":0,"price_not_read":True,
        "filing_acceptance_pit_validated":False,
        "official_rth_volume_validated":False,
        "licensed_non_display_derivative_rights_independently_verified":False,
        "primary_price_created":0,"primary_mc_created":0,"r92_created":0,
        "can_create_primary":False,"can_register_r92":False,
        "go":False,"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    encoded=json.dumps(answer,sort_keys=True)
    for key in SECRET_NAMES:
        value=env.get(key)
        # Nontrivial secret material must not ever appear in result.
        if isinstance(value,str) and len(value)>=8 and value in encoded:
            raise ValueError("SECRET_VALUE_IN_PUBLIC_OUTPUT")
    return answer

def selftest():
    raw=INVENTORY.read_bytes()
    inv=json.loads(raw)
    blank=analyze(inv,{},raw)
    assert len(blank["providers"])==12 and blank["api_calls"]==0
    ids={x["id"]:x for x in blank["providers"]}
    assert ids["ALPACA"]["runner_key_presence"]=="MISSING"
    assert ids["MASSIVE"]["runner_key_presence"]=="MISSING"
    assert ids["BUSINESSQUANT"]["runner_key_presence"]=="MISSING"
    assert ids["RALLIES"]["runner_key_presence"]=="CHATGPT_APP_NOT_RUNNER_AUTHORITY"
    assert all(x["safe_to_attempt_research_api"] is False for x in ids.values())
    base={"XRAY_ALPACA_API_KEY_ID":"SECRET_ALPACA_ID_5678920",
          "XRAY_ALPACA_API_SECRET_KEY":"SECRET_ALPACA_KEY_6789120",
          "XRAY_MASSIVE_API_KEY":"SECRET_MASSIVE_123891",
          "XRAY_BQ_API_KEY":"SECRET_BQ_KEY_125655"}
    creds_only=analyze(inv,base,raw)
    assert all(creds_only["providers"][i]["safe_to_attempt_research_api"] is False
               for i in range(12))
    fully=dict(base)
    for config in EXPLICIT.values():
        fully[config["grant"]]="true"
        fully[config["evidence"]]="e"*64
    yes=analyze(inv,fully,raw)
    y={x["id"]:x for x in yes["providers"]}
    assert all(y[x]["safe_to_attempt_research_api"] is True for x in EXPLICIT)
    assert all(x["production_primary_authority"] is False for x in y.values())
    assert all(x["independently_verified_legal_rights"] is False for x in y.values())
    assert all(x not in json.dumps(yes) for x in base.values())
    for config in EXPLICIT.values():
        bad=dict(fully)
        bad[config["grant"]]="false"
        assert not next(p for p in analyze(inv,bad,raw)["providers"]
                        if p["id"]==next(n for n,v in EXPLICIT.items() if v is config))["safe_to_attempt_research_api"]
        bad=dict(fully)
        bad[config["evidence"]]="INVALID"
        assert not next(p for p in analyze(inv,bad,raw)["providers"]
                        if p["id"]==next(n for n,v in EXPLICIT.items() if v is config))["safe_to_attempt_research_api"]
    import copy
    for mutate in (lambda j:j["sources"].pop(),
                   lambda j:j.update(effective_policy="C4.18"),
                   lambda j:j.update(real_money="GO"),
                   lambda j:j.update(no_provider_automatically_activated=False)):
        x=copy.deepcopy(inv)
        mutate(x)
        try:analyze(x,{},raw)
        except (ValueError,TypeError):pass
        else:raise AssertionError("UNSAFE_PROVIDER_INVENTORY_ACCEPTED")
    print("XRAY_RUNNER_PROVIDER_ACCESS_AUDIT=PASS_12_SOURCES_3_PROBED_10_NEGATIVE_ZERO_ALPHA")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:selftest();return
    if a.out is None or a.out.resolve().is_relative_to(REPO.resolve()):
        p.error("OUTSIDE_REPO_PRIVATE_REPORT_REQUIRED")
    raw=INVENTORY.read_bytes()
    report=analyze(json.loads(raw),os.environ,raw)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("XRAY_RUNNER_PROVIDER_ACCESS_MAP="+",".join(
        x["id"]+":"+x["runner_key_presence"] for x in report["providers"] if x["id"] in EXPLICIT))
    print("XRAY_RUNNER_AUTHORITY_NOT_INFERRED_FROM_SECRET_PRESENCE=PASS")

if __name__=="__main__": main()
