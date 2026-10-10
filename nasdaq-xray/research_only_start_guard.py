#!/usr/bin/env python3
"""Validate explicit production start of research-only monitoring, NOT signal GO.

This is an operational safety assertion. It cannot authorize market-data
rights, raise MC/HISTORY/PIT status, register R92 or send an order/alert.
"""
from __future__ import annotations
import argparse
import json
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent
NAME="research_only_start_20261010.json"
MUST_FALSE=(
 "automatic_orders","broker_execution","source_rights_bypass",
 "historical_pit_bypass","alpha_threshold_relaxation",
 "current_primary_mc_attested","current_terminal_completed_attested",
 "notification_device_receipt_attested","final_production_go_claimed",
)
ALLOWED={
 "schema":"XRAY_RESEARCH_ONLY_START_V1","mode":"RESEARCH_ONLY",
 "policy":"C4.17","control":"C4.27","execution":"NONE",
 "real_money":"NO-GO",
 "delivery_policy":"ONLY_SOURCE_VALIDATED_REGISTERED_R92_NO_FAKE_DEVICE_RECEIPT",
 "watch_workflow":"xray-research-watch-radar.yml",
 "delivery_workflow":"nasdaq-xray-delivery.yml",
 "manual_research_workflow":"xray-manual-decision-research-shadow.yml",
}

def validate(j):
    if not isinstance(j,dict) or any(j.get(k)!=v for k,v in ALLOWED.items()):
        raise ValueError("RESEARCH_LAUNCH_POLICY_INVALID")
    if j.get("active") is not True or j.get("unknown_never_pass") is not True:
        raise ValueError("RESEARCH_LAUNCH_NOT_ACTIVE_OR_UNKNOWN_UNSAFE")
    if any(j.get(k) is not False for k in MUST_FALSE):
        raise ValueError("RESEARCH_LAUNCH_UNSAFE_AUTHORITY_CLAIM")
    if j.get("target_branch")!="main" or j.get("target_repository")!="gokaydonmez39-jpg/kripto-radar":
        raise ValueError("RESEARCH_LAUNCH_WRONG_TARGET")
    if j.get("user_intent")!="MANUAL_RESEARCH_ONLY_NEVER_BROKER_AUTOMATION":
        raise ValueError("RESEARCH_LAUNCH_USER_INTENT_DRIFT")
    return True

def blob_sha(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\\0"+raw).hexdigest()

def build(root=ROOT):
    launch_raw=(root/NAME).read_bytes()
    c=json.loads(launch_raw)
    validate(c)
    refs={}
    for key,path in (
      ("price","canonical_current_price_dv30.json"),
      ("master","canonical_current_master_manifest.json"),
      ("terminal","canonical_current_terminal.json"),
    ):
      b=(root/path).read_bytes()
      data=json.loads(b)
      if data.get("execution")!="NONE" or data.get("real_money")!="NO-GO":
          raise RuntimeError("CANONICAL_EXECUTION_UNSAFE:"+key)
      refs[key]={"asof_et":data.get("asof_et"),"blob_sha":blob_sha(b)}
    epoch_aligned=refs["price"]["asof_et"]==refs["master"]["asof_et"]==refs["terminal"]["asof_et"]
    return {
      "schema":"XRAY_RESEARCH_MONITORING_START_WITNESS_V1",
      "operational_status":"RESEARCH_MONITORING_START_CONFIGURED",
      "current_signal_release":"NOT_ATTESTED",
      "input_epochs_aligned":epoch_aligned,
      "readback":refs,
      "start_config_blob_sha":blob_sha(launch_raw),
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "primary_mc_attested":False,
      "alpha_go":False,
      "orders":[],"buy_candidates":[],
      "delivery_receipt_attested":False,
      "ci_success_means_signal_ready":False,
    }

def selftest():
    c=json.loads((ROOT/NAME).read_text())
    assert validate(c) is True
    for k in MUST_FALSE:
        invalid=dict(c); invalid[k]=True
        try: validate(invalid)
        except ValueError:pass
        else:raise AssertionError("UNSAFE_START_ACCEPTED:"+k)
    for k in ("active","unknown_never_pass"):
        invalid=dict(c);invalid[k]=False
        try:validate(invalid)
        except ValueError:pass
        else:raise AssertionError("DISABLED_OR_UNSAFE_START_ACCEPTED:"+k)
    for k in ALLOWED:
        invalid=dict(c);invalid[k]="BAD"
        try:validate(invalid)
        except ValueError:pass
        else:raise AssertionError("POLICY_DRIFT_ACCEPTED:"+k)
    r=build()
    assert r["execution"]=="NONE" and r["real_money"]=="NO-GO"
    assert r["alpha_go"] is False and r["orders"]==[]
    assert r["current_signal_release"]=="NOT_ATTESTED"
    print("XRAY_RESEARCH_START_SELFTEST=PASS_24_NEGATIVES_NO_TRADING_NO_SIGNAL_GO")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out")
    a=p.parse_args()
    if a.selftest:selftest()
    else:
        if not a.out:p.error("--out required")
        j=build()
        Path(a.out).write_text(json.dumps(j,sort_keys=True,indent=2)+"\n")
        print("XRAY_RESEARCH_MONITORING="+j["operational_status"])
        print("XRAY_RESEARCH_RELEASE="+j["current_signal_release"])
        print("XRAY_RESEARCH_EPOCH_ALIGNED="+str(j["input_epochs_aligned"]).lower())

if __name__=="__main__":main()
