#!/usr/bin/env python3
"""Read-only manual-workflow terminal/master source-binding incident witness.

Does NOT repair mismatched C4.17 terminal evidence, upgrade an archive to
current, emit trading signals or suppress a failed upstream workflow.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

from manual_decision_report import may_use_frozen_blob

SCHEMA="XRAY_MANUAL_SOURCE_DRIFT_FORENSIC_V1"
H40=re.compile(r"[a-f0-9]{40}\\Z")


def need(ok,why):
    if not ok:
        raise ValueError("XRAY_MANUAL_DRIFT_"+why)


def blob(data):
    return hashlib.sha1(
        b"blob "+str(len(data)).encode("ascii")+bytes([0])+data).hexdigest()


def audit(terminal,master,policy,master_bytes):
    need(all(type(obj) is dict for obj in (terminal,master,policy))
         and type(master_bytes) is bytes,"INPUT_TYPES")
    need(terminal.get("execution")==master.get("execution")==
         policy.get("execution")=="NONE" and
         terminal.get("real_money")==master.get("real_money")==
         policy.get("real_money")=="NO-GO" and
         terminal.get("compiled_policy_version")==
         policy.get("parent_policy_version")=="C4.17" and
         policy.get("alpha_thresholds_unchanged") is True and
         policy.get("parent_pipeline_unchanged") is True and
         policy.get("broker_trade_access_allowed") is False and
         policy.get("unknown_never_pass") is True,
         "SAFETY_POLICY")
    bound=(terminal.get("evidence") or {}).get("master") or {}
    need(bound.get("path")==
         "nasdaq-xray/canonical_current_master_manifest.json" and
         type(bound.get("blob_sha")) is str and
         H40.fullmatch(bound["blob_sha"]) is not None,
         "TERMINAL_MASTER_BINDING")
    actual=blob(master_bytes)
    # The exact Git blob SHA is computed from original bytes. Never
    # reserialize the JSON to compare sha or change a provenance source.
    try:
        terminal_day=dt.date.fromisoformat(terminal["asof_et"])
        master_day=dt.date.fromisoformat(master["asof_et"])
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError("XRAY_MANUAL_DRIFT_ASOF_BAD") from exc
    need(terminal_day.isoformat()==terminal["asof_et"] and
         master_day.isoformat()==master["asof_et"],
         "ASOF_FORMAT")
    delta=(master_day-terminal_day).days
    same_sha=actual==bound["blob_sha"]
    archive_allowed=(not same_sha and
        may_use_frozen_blob("master",master,terminal_day.isoformat()))
    exact_current=(same_sha and delta==0)
    if exact_current:
        state="EXACT_TERMINAL_MASTER_SOURCE_BINDING_ONLY"
    elif archive_allowed:
        state="ARCHIVAL_TERMINAL_SOURCE_ALLOWED_NOT_CURRENT_RELEASE"
    else:
        state="SOURCE_INTEGRITY_BLOCKED"
    return {
        "schema":SCHEMA,
        "status":state,
        "terminal_asof_et":terminal_day.isoformat(),
        "current_master_asof_et":master_day.isoformat(),
        "day_delta_master_minus_terminal":delta,
        "terminal_bound_master_blob_sha":bound["blob_sha"],
        "actual_current_master_blob_sha":actual,
        "source_blob_exact":same_sha,
        "archival_replay_allowed_by_existing_guard":archive_allowed,
        "current_terminal_master_binding_exact":exact_current,
        "source_drift_fail_closed":state=="SOURCE_INTEGRITY_BLOCKED",
        "root_cause_diagnosis":
            "TERMINAL_OLDER_THAN_CURRENT_MASTER_OUTSIDE_EXISTING_ARCHIVE_WINDOW"
            if state=="SOURCE_INTEGRITY_BLOCKED" and delta>0
            else "SHA_MISMATCH_WITHOUT_APPROVED_ARCHIVAL_REPLAY"
            if state=="SOURCE_INTEGRITY_BLOCKED"
            else "ARCHIVAL_CONTEXT_ONLY_NO_SAME_SESSION_RELEASE"
            if archive_allowed else "ONLY_THIS_SOURCE_BINDING_EXACT",
        "reporting_cannot_establish_current_c417_release":True,
        "canonical_terminal_mutated":False,
        "manual_workflow_failure_suppressed":False,
        "repair_autonomously_authorized":False,
        "signal_count":0,
        "model_trained":False,
        "alpha_authority":False,
        "r92_authority":False,
        "device_delivery_attested":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path(__file__).resolve().parent)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    paths=[args.root/name for name in (
        "canonical_current_terminal.json","canonical_current_master_manifest.json",
        "manual_decision_policy_v1.json")]
    need(args.out.resolve() not in [p.resolve() for p in paths],
         "NO_SOURCE_OVERWRITE")
    terminal=json.loads(paths[0].read_text())
    bb=paths[1].read_bytes()
    master=json.loads(bb)
    policy=json.loads(paths[2].read_text())
    result=audit(terminal,master,policy,bb)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+chr(10))
    print(json.dumps({
        "status":result["status"],
        "day_delta":result["day_delta_master_minus_terminal"],
        "source_exact":result["source_blob_exact"],
        "alpha_authority":False,"execution":"NONE","real_money":"NO-GO"
    },sort_keys=True))


if __name__=="__main__":
    main()
