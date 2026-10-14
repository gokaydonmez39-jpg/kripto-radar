#!/usr/bin/env python3
"""First R92 registration after independently proven FROG D release.

Eligibility does NOT require a pre-existing lifecycle entry or delivered push.
A verified seven-gate + same-ASOF terminal witness authorizes the FIRST registry
entry. Delivery is a separate pending/acknowledged state; never forge an iPhone
receipt. GitHub writes are separately version-controlled and not made by this
read-only audit. No brokerage orders or vendor market data persisted.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ASOF="2026-10-13"
SYMBOL="FROG"
SETUP="D"
KEY="FROG|D|"+ASOF
ROOT=Path(__file__).resolve().parent
SEVEN=("identity_and_share_class","corrected_rth_close_dv30_condition6",
       "independent_corporate_actions_pit","same_asof_class_market_cap_ge_2b",
       "history_260_52_setup_d_r1_rr_regime","eight_session_official_event_clear",
       "sec_legal_and_historical_live_nasdaq_halt_clear")
SOURCE_KEYS=("sec_cover","ca_price","sec_halt_event_auction","conditional_policy")


def require(v, code):
    if not v:
        raise ValueError("XRAY_FROG_FIRST_REGISTRATION_"+code)


def root_sha(source_sha256):
    require(type(source_sha256) is dict and set(source_sha256)==set(SOURCE_KEYS),
            "SOURCE_SET")
    require(all(type(source_sha256[k]) is str and len(source_sha256[k])==64
                and all(c in "0123456789abcdef" for c in source_sha256[k])
                for k in SOURCE_KEYS),"SOURCE_SHA256")
    return hashlib.sha256(json.dumps(source_sha256,sort_keys=True).encode()).hexdigest()


def release_proved(report):
    """Source truth is independent of lifecycle registration and delivery."""
    need=report.get("seven_official_source_release_gates") or {}
    states=need.get("states") or {}
    return (report.get("schema")=="XRAY_FROG_20261013_CONDITIONAL_R92_MATH_EVIDENCE_REVIEW_V1"
            and report.get("symbol")==SYMBOL and report.get("setup")==SETUP
            and report.get("asof_et")==ASOF
            and report.get("execution")=="NONE" and report.get("real_money")=="NO-GO"
            and set(states)==set(SEVEN)
            and all(states[k]=="PASS" for k in SEVEN)
            and need.get("pass_count")==7 and need.get("required")==7
            and not need.get("missing")
            and report.get("policy_r92_conditional_permission_enabled") is True
            and type(report.get("source_json_sha256")) is dict)


def terminal_proved(report, terminal, compiled):
    """C4.17 live terminal must be separately rebuilt for Oct13, not date-patched."""
    if not release_proved(report):
        return False
    item=(terminal.get("candidate_releases") or {}).get("FROG|D") or {}
    h=root_sha(report["source_json_sha256"])
    return (terminal.get("asof_et")==ASOF
            and terminal.get("compiled_policy_hash")==compiled.get("policy_hash")
            and terminal.get("status") in ("PASS","PRIMARY_PASS")
            and item.get("asof_et")==ASOF
            and item.get("evidence_root_sha256")==h
            and item.get("independent_c417_release_pass") is True
            and item.get("source_gate_pass_count")==7)


def make_first_registration(report, terminal, registry, ledger, compiled):
    """Prepare exact JSON mutations from empty registry, without faking delivery.

    This function can generate the FIRST record, unlike a previous circular
    reader that required a delivered ledger entry before issuing registration.
    The caller must CAS-commit and verify GitHub blobs before alert delivery.
    """
    require(release_proved(report),"SEVEN_INDEPENDENT_PROOFS")
    require(terminal_proved(report,terminal,compiled),"LIVE_C417_TERMINAL")
    require(registry.get("schema")=="XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1"
            and registry.get("execution")=="NONE"
            and registry.get("real_money")=="NO-GO","REGISTRY_SCHEMA")
    require(ledger.get("schema")=="XRAY_DELIVERY_LEDGER_V1"
            and ledger.get("execution")=="NONE"
            and ledger.get("real_money")=="NO-GO","LEDGER_SCHEMA")
    records=registry.get("records")
    deliveries=ledger.get("deliveries")
    require(type(records) is dict and type(deliveries) is dict,"RECORD_MAPS")
    require(registry.get("asof_et") in (ASOF,"2026-10-07") and
            (registry.get("asof_et")==ASOF or not records),"NO_HISTORICAL_ERASURE")
    root=root_sha(report["source_json_sha256"])
    signal="FROG-D-20261013-"+hashlib.sha256((KEY+"|"+root).encode()).hexdigest()[:20]
    record={"symbol":SYMBOL,"setup":SETUP,"asof_et":ASOF,
            "signal_id":signal,"evidence_root_sha256":root,
            "registered_r92":True,"canonical_terminal_pass":True,
            "notification_status":"PENDING_PLATFORM_DELIVERY",
            "execution":"NONE","real_money":"NO-GO"}
    out_registry=copy.deepcopy(registry)
    existing=out_registry["records"].get(KEY)
    if existing is not None:
        require(existing==record,"CONFLICTING_SIGNAL")
    else:
        require(all(x.get("signal_id")!=signal for x in records.values()
                    if type(x) is dict),"DUPLICATE_SIGNAL")
        out_registry["records"][KEY]=record
    out_registry["asof_et"]=ASOF
    out_ledger=copy.deepcopy(ledger)
    existing_pending=(out_ledger.get("pending") or {}).get(KEY)
    pending={"signal_id":signal,"evidence_root_sha256":root,
             "channel":"CHATGPT_ONLY","status":"AWAITING_ACTUAL_PLATFORM_TASK",
             "delivery_confirmed":False}
    if existing_pending is not None:
        require(existing_pending==pending,"CONFLICTING_PENDING")
    else:
        out_ledger.setdefault("pending",{})[KEY]=pending
    require(KEY not in deliveries,"CANNOT_FORGE_OR_REPLACE_DELIVERY")
    return {"registry":out_registry,"ledger":out_ledger,"signal_id":signal,
            "registry_first_write_ready":True,"delivery_receipt_attested":False}


def stage_first_registration_json(report, terminal, registry, ledger, compiled,
                                  registry_output, ledger_output):
    """Actually write BOTH registration and pending-delivery JSON to staging files.

    Does not claim the platform delivered a message; GitHub CAS-commit/readback
    and a separate genuine platform receipt remain downstream operations.
    """
    a=Path(registry_output).resolve()
    b=Path(ledger_output).resolve()
    require(a!=b and a.name.endswith(".json") and b.name.endswith(".json"),
            "DISTINCT_JSON_OUTPUTS")
    require(a.parent.is_dir() and b.parent.is_dir(),"OUTPUT_PARENTS")
    require(not a.exists() and not b.exists(),"REFUSE_REPLACE_EXISTING_STAGED_FILES")
    payload=make_first_registration(report,terminal,registry,ledger,compiled)
    contents=((a,payload["registry"]),(b,payload["ledger"]))
    written=[]
    try:
        for path,doc in contents:
            path.write_text(json.dumps(doc,sort_keys=True,indent=2)+"\n",encoding="utf-8")
            written.append(path)
        for path,doc in contents:
            require(json.loads(path.read_text(encoding="utf-8"))==doc,"STAGE_READBACK")
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return {"registry_staged":str(a),"ledger_pending_staged":str(b),
            "registered_signal_id":payload["signal_id"],
            "delivery_platform_receipt_verified":False}


def read_registration(registry, terminal, compiled, source_sha256):
    """Registered is NOT contingent on a delivered phone message."""
    root=root_sha(source_sha256)
    rec=(registry.get("records") or {}).get(KEY) or {}
    item=(terminal.get("candidate_releases") or {}).get("FROG|D") or {}
    return bool(registry.get("asof_et")==ASOF and
                terminal.get("asof_et")==ASOF and
                terminal.get("compiled_policy_hash")==compiled.get("policy_hash") and
                item.get("independent_c417_release_pass") is True and
                item.get("evidence_root_sha256")==root and
                rec.get("registered_r92") is True and
                rec.get("evidence_root_sha256")==root and
                rec.get("signal_id"))


def selftest():
    from candidate_local_frog_oct13_r92_math_evidence_gate import SCHEMA
    sha={k:"a"*64 for k in SOURCE_KEYS}
    gates={k:"PASS" for k in SEVEN}
    r={"schema":SCHEMA,"symbol":SYMBOL,"setup":SETUP,"asof_et":ASOF,
       "execution":"NONE","real_money":"NO-GO",
       "seven_official_source_release_gates":{
           "states":gates,"pass_count":7,"required":7,"missing":[]},
       "policy_r92_conditional_permission_enabled":True,
       "source_json_sha256":sha}
    compiled={"policy_hash":"b"*64}
    term={"asof_et":ASOF,"compiled_policy_hash":"b"*64,"status":"PASS",
          "candidate_releases":{"FROG|D":{"asof_et":ASOF,
          "source_gate_pass_count":7,"evidence_root_sha256":root_sha(sha),
          "independent_c417_release_pass":True}}}
    registry={"schema":"XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1","asof_et":"2026-10-07",
              "records":{},"execution":"NONE","real_money":"NO-GO"}
    ledger={"schema":"XRAY_DELIVERY_LEDGER_V1","deliveries":{},
            "execution":"NONE","real_money":"NO-GO"}
    # A controlled, synthetic positive UNIT TEST proves the write code is reachable
    # without first requiring a registry or a delivery receipt.
    positive=make_first_registration(r,term,registry,ledger,compiled)
    require(positive["registry_first_write_ready"] is True and
            positive["registry"]["records"][KEY]["registered_r92"] is True and
            not positive["ledger"]["deliveries"] and
            positive["ledger"]["pending"][KEY]["delivery_confirmed"] is False and
            read_registration(positive["registry"],term,compiled,sha),
            "POSITIVE_FIRST_REGISTRATION_WITH_NO_FAKE_PUSH")
    again=make_first_registration(r,term,positive["registry"],positive["ledger"],compiled)
    require(again["registry"]==positive["registry"] and
            again["ledger"]==positive["ledger"],"IDEMPOTENT")
    # Crucial negative tests: no observed-source shortcut, date transplant,
    # mismatched SHA, stale canonical, or faked push entry may pass.
    for bad in SEVEN:
        broken=copy.deepcopy(r)
        broken["seven_official_source_release_gates"]["states"][bad]="UNKNOWN"
        try:make_first_registration(broken,term,registry,ledger,compiled)
        except ValueError:pass
        else:raise AssertionError("MISSING_GATE_ACCEPTED_"+bad)
    stale=copy.deepcopy(term)
    stale["asof_et"]="2026-10-07"
    try:make_first_registration(r,stale,registry,ledger,compiled)
    except ValueError:pass
    else:raise AssertionError("STALE_GLOBAL_TERMINAL_ACCEPTED")
    conflict=copy.deepcopy(term)
    conflict["candidate_releases"]["FROG|D"]["evidence_root_sha256"]="c"*64
    try:make_first_registration(r,conflict,registry,ledger,compiled)
    except ValueError:pass
    else:raise AssertionError("MISMATCHED_LINEAGE_ACCEPTED")
    fraud=copy.deepcopy(ledger)
    fraud["deliveries"][KEY]={"delivery_confirmed":True}
    try:make_first_registration(r,term,registry,fraud,compiled)
    except ValueError:pass
    else:raise AssertionError("FAKE_PREEXISTING_DELIVERY_ACCEPTED")
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        outa=Path(t)/"lifecycle.json"
        outb=Path(t)/"delivery_pending.json"
        staged=stage_first_registration_json(r,term,registry,ledger,compiled,outa,outb)
        require(staged["delivery_platform_receipt_verified"] is False and
                json.loads(outa.read_text())["records"][KEY]["registered_r92"] is True and
                not json.loads(outb.read_text())["deliveries"] and
                json.loads(outb.read_text())["pending"][KEY]["delivery_confirmed"] is False,
                "TRUE_FIRST_WRITE_TO_STAGING_FILES_NO_FAKE_PLATFORM_DELIVERY")
    require(not registry["records"] and not ledger["deliveries"],"NO_TEST_WRITE_SIDE_EFFECTS")
    print("XRAY_FROG_FIRST_REGISTRATION_SELFTEST=PASS_EMPTY_REGISTRY_POSITIVE_7_NEGATIVE_STALE_SHA_NO_PUSH")


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--report",type=Path)
    p.add_argument("--out-registry",type=Path)
    p.add_argument("--out-ledger",type=Path)
    a=p.parse_args()
    if a.selftest:return selftest()
    require(a.report,"REPORT_REQUIRED")
    require(bool(a.out_registry)==bool(a.out_ledger),"BOTH_OUTPUTS_OR_NONE")
    report=json.loads(a.report.read_text())
    registry=json.loads((ROOT/"canonical_candidate_lifecycle_registry.json").read_text())
    terminal=json.loads((ROOT/"canonical_current_terminal.json").read_text())
    ledger=json.loads((ROOT/"delivery_ledger.json").read_text())
    compiled=json.loads((ROOT/"chatgpt_compiled_policy_v3.json").read_text())
    proof=release_proved(report)
    terminal_ok=terminal_proved(report,terminal,compiled) if proof else False
    result={"symbol":SYMBOL,"setup":SETUP,"asof_et":ASOF,
            "independent_seven_gate_pass":proof,
            "same_asof_terminal_pass":terminal_ok,
            "first_registration_ready":bool(proof and terminal_ok),
            "registered_r92_readback":read_registration(registry,terminal,compiled,
                report.get("source_json_sha256",{}))
                if type(report.get("source_json_sha256")) is dict else False,
            "observed_terminal_asof_et":terminal.get("asof_et"),
            "real_money":"NO-GO","execution":"NONE"}
    print(json.dumps(result,sort_keys=True))
    if proof and terminal_ok:
        prepared=make_first_registration(report,terminal,registry,ledger,compiled)
        print("XRAY_FROG_FIRST_REGISTRATION=PREPARED_NO_EXTERNAL_COMMIT_OR_PHONE_RECEIPT")
        print("XRAY_FROG_FIRST_SIGNAL_ID="+prepared["signal_id"])
        if a.out_registry and a.out_ledger:
            written=stage_first_registration_json(report,terminal,registry,ledger,compiled,
                                                  a.out_registry,a.out_ledger)
            print("XRAY_FROG_FIRST_REGISTRATION_STAGED_JSON_FILES="+
                  json.dumps(written,sort_keys=True))
    else:
        print("XRAY_FROG_FIRST_REGISTRATION=NOT_READY_SEVEN_SOURCE_OR_SAME_ASOF_TERMINAL")

if __name__=="__main__":
    main()
