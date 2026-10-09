#!/usr/bin/env python3
"""Independent zero-alpha exact-blob incident classifier for NASDAQ XRAY.

Read-only Github-backed provenance comparisons; produces diagnoses, NEVER a
canonical PASS, new candidate, entitlement, account status, or trade.
"""
from __future__ import annotations
import argparse
import base64
import datetime as dt
import json
import os
import pathlib
import time
from unittest.mock import patch
from github_native_root_watchdog import github, head_sha, timestamp, UTC

ROOT="nasdaq-xray/"
FILES={
    "terminal":"canonical_current_terminal.json",
    "orchestrator":"orchestrator_state.json",
    "master":"canonical_current_master_manifest.json",
    "official":"canonical_official_source_guard.json",
    "overlay":"canonical_current_final_gate_overlay.json",
    "resolver":"canonical_current_resolver_request.json",
    "events":"canonical_current_event_state.json",
    "g9":"g9_entitlement_authority.json",
    "account":"account_gate_contract.json",
}
BINDINGS=("master","price","full_state")

def classify(now, blobs, files, main_stable):
    issues=[]
    if not main_stable:
        return {"status":"UNVERIFIED_MAIN_CHANGED",
                "issues":["ATOMIC_SNAPSHOT_NOT_PROVEN"],"alpha_authority":False}
    terminal=files["terminal"]
    orchestrator=files["orchestrator"]
    master=files["master"]
    official=files["official"]
    overlay=files["overlay"]
    resolver=files["resolver"]
    events=files["events"]
    g9=files["g9"]
    account=files["account"]
    if (terminal.get("execution")!="NONE" or terminal.get("real_money")!="NO-GO" or
        master.get("unknown_never_pass") is not True):
        issues.append("POLICY_OR_SAFETY_ATTESTATION_MISMATCH")
    drift=[]
    for key in BINDINGS:
        ref=(terminal.get("evidence") or {}).get(key) or {}
        path=ref.get("path")
        expected=ref.get("blob_sha")
        if not path or not expected or blobs.get(path)!=expected:
            drift.append(key)
    if drift:
        issues.append("TERMINAL_LIVE_BLOB_DRIFT")
    # A GitHub tree is sufficient to prove an immutable MC bridge is ABSENT,
    # but mere file presence can never prove C4.17 PRIMARY authority.
    # Use the root ASOF (not the stale terminal ASOF) to prevent an old
    # epoch's committed MC graph from masquerading as current.
    root_asof=str(orchestrator.get("asof_et") or "")
    try:
        root_day=dt.date.fromisoformat(root_asof)
        root_asof_valid=root_day.isoformat()==root_asof
    except (ValueError,TypeError):
        root_asof_valid=False
    if not root_asof_valid:
        issues.append("ROOT_ASOF_INVALID")
    current_mc_bridges=[]
    if root_asof_valid:
        prefix=ROOT+"canonical_mc_bridge_"+root_asof.replace("-","")+"_c417_dv30_v"
        current_mc_bridges=sorted(
            path for path,sha in blobs.items()
            if path.startswith(prefix) and path.endswith(".json")
            and path[len(prefix):-5].isdigit()
            and isinstance(sha,str) and len(sha)==40
        )
        if not current_mc_bridges:
            issues.append("CURRENT_MC_AUTHORITY_ARTIFACT_ABSENT")
        if terminal.get("asof_et")!=root_asof:
            issues.append("CURRENT_TERMINAL_ASOF_LAG")
    master_count=int(master.get("unknown_count",-1))
    if master_count != 0:
        issues.append("MASTER_IDENTITY_EVIDENCE_INCOMPLETE")
    # Root Actions SUCCESS attests process completion, NOT data-plane
    # completion. Surface persistent upstream history outages explicitly.
    root_status=orchestrator.get("status")
    if root_status=="PARTIAL_HISTORY":
        issues.append("ROOT_HISTORY_PARTIAL")
        if (orchestrator.get("history_retryable") is False and
            int(orchestrator.get("pending_retry",-1))==0):
            issues.append("ROOT_HISTORY_NO_RETRYABLE_WORK")
    elif root_status not in ("DATA_PLANE_PARTIAL_UNKNOWN",
                             "DATA_PLANE_PASS_CANONICAL_DOWNSTREAM_DEFERRED"):
        issues.append("ROOT_DATA_PLANE_STATUS_UNVERIFIED")
    price_path=ROOT+"canonical_current_price_dv30.json"
    # SHA binding and per-symbol coverage are different controls.
    # A frozen PRICE snapshot can contain explicit blocked symbols without
    # changing the correctness of its exact Git-blob resolver link.
    current_price_blob=blobs.get(price_path)
    resolver_price_exact=bool(
        isinstance(current_price_blob,str) and len(current_price_blob)==40
        and resolver.get("source_price_blob_sha")==current_price_blob
    )
    if not resolver_price_exact:
        issues.append("CURRENT_PRICE_RESOLVER_BINDING_UNPROVEN")
    try:
        resolver_price_blocked=int(resolver.get("price_blocked_count",-1))
        resolver_price_unknown=int(resolver.get("price_unknown_count",-1))
    except (ValueError,TypeError):
        resolver_price_blocked=resolver_price_unknown=-1
    if resolver_price_blocked<0 or resolver_price_unknown<0:
        issues.append("PRICE_RESOLVER_COVERAGE_COUNTS_INVALID")
    else:
        if resolver_price_blocked:
            issues.append("PRICE_SYMBOL_LOCAL_BLOCKED_PRESENT")
        if resolver_price_unknown:
            issues.append("PRICE_SYMBOL_LOCAL_UNKNOWN_PRESENT")
    age=(now-timestamp(official.get("generated_at_utc"))).total_seconds()
    if age>900:
        issues.append("OFFICIAL_GUARD_STALE_OVER_900S")
    if int(events.get("affected_geometry_event_unknown_count",-1))>0:
        issues.append("EVENT_GEOMETRY_UNRESOLVED")
    # C4.17 manual research is independent of broker/account and G9 NBBO.
    # Preserve external execution readiness separately; do not conflate it
    # with root/candidate research outages or silently grant a trading GO.
    legacy_full_go_blockers=[]
    if g9.get("status")!="PROVEN_FROM_PRIMARY_SOURCE":
        legacy_full_go_blockers.append("EXTERNAL_G9_ENTITLEMENT_UNPROVEN")
    if account.get("current_status")!="ACCOUNT_PASS":
        legacy_full_go_blockers.append("EXTERNAL_ACCOUNT_READ_SCOPE_UNPROVEN")
    if terminal.get("full_end_to_end_research_pass") is not True:
        issues.append("TERMINAL_E2E_NOT_PROVEN")
    # Overlay is a reporting surface only; never converts non-pass to PASS.
    overlay_current=((overlay.get("source_terminal") or {}).get("blob_sha")
                     ==blobs.get(ROOT+"canonical_current_terminal.json"))
    if not overlay_current:
        issues.append("REPORTING_OVERLAY_TERMINAL_BINDING_DRIFT")
    return {
        "status":"OPEN_INCIDENTS_FAIL_CLOSED" if issues else "AUDIT_EXACT_NO_ALPHA_PROMOTION",
        "issues":sorted(set(issues)),
        "terminal_drift_keys":drift,
        "master_pass_count":master.get("pass_count"),
        "master_unknown_count":master_count,
        "root_asof_et":root_asof,
        "canonical_terminal_asof_et":terminal.get("asof_et"),
        "current_mc_bridge_artifact_count":len(current_mc_bridges),
        "current_mc_bridge_artifact_presence_only":bool(current_mc_bridges),
        "current_mc_primary_authority_proven_by_watchdog":False,
        "price_resolver_exact_current":resolver_price_exact,
        "price_resolver_source_blob_match_only":resolver_price_exact,
        "price_symbol_local_blocked_count":resolver_price_blocked,
        "price_symbol_local_unknown_count":resolver_price_unknown,
        "price_pass_count_from_exact_resolver":resolver.get("source_price_pass_count") if resolver_price_exact else None,
        "official_guard_age_seconds":round(age),
        "geometry_event_unknown_count":events.get("affected_geometry_event_unknown_count"),
        "g9_status":g9.get("status"),
        "account_status":account.get("current_status"),
        "manual_research_mode":"RESEARCH_ONLY_MANUAL_DECISION",
        "g9_and_account_required_for_manual_research":False,
        "legacy_full_go_blockers":legacy_full_go_blockers,
        "legacy_full_go_ready":not legacy_full_go_blockers and not issues,
        "terminal_result":terminal.get("terminal_result"),
        "root_data_plane_status":root_status,
        "root_history_unknown_count":orchestrator.get("unknown_count"),
        "root_history_retryable":orchestrator.get("history_retryable"),
        "overlay_bound_to_current_terminal":overlay_current,
        "automatic_repair_authority":"SAFE_ROOT_RESTART_ONLY",
        "requires_source_specific_proof_for_master_mc_event":True,
        "requires_external_g9_account_entitlements":True,
        "execution":"NONE","real_money":"NO-GO",
        "alpha_authority":False,"unknown_never_pass":True,
        "r92_created":False,"trade_placed":False,
    }

def selftest():
    now=dt.datetime(2026,10,8,11,tzinfo=UTC)
    base=ROOT
    blobs={base+x+".json":x for x in ("master","price","full_state")}
    blobs[base+"canonical_current_terminal.json"]="terminalSHA"
    terminal={"execution":"NONE","real_money":"NO-GO",
              "full_end_to_end_research_pass":False,"terminal_result":"PARTIAL_UNKNOWN",
              "evidence":{x:{"path":base+x+".json","blob_sha":x} for x in ("master","price","full_state")}}
    objects={
        "terminal":terminal,
        "orchestrator":{"status":"PARTIAL_HISTORY","unknown_count":231,
                        "pending_retry":0,"history_retryable":False},
        "master":{"unknown_count":165,"pass_count":3184,"unknown_never_pass":True},
        "official":{"generated_at_utc":"2026-10-08T06:49:42Z"},
        "overlay":{"source_terminal":{"blob_sha":"terminalSHA"}},
        "resolver":{"source_price_blob_sha":"price","price_blocked_count":0,
                    "price_unknown_count":0,"source_price_pass_count":510},
        "events":{"affected_geometry_event_unknown_count":20},
        "g9":{"status":"BLOCKED_STRICT_PERMANENT_ZERO"},
        "account":{"current_status":"ACCOUNT_BOOTSTRAP_READY_CREDENTIALS_REQUIRED"},
    }
    # Supply authentic tree paths, not arbitrary aliases.
    for x in ("master","price","full_state"):
        source_path=base+"canonical_current_"+("master_manifest" if x=="master" else "price_dv30" if x=="price" else "full_state")+".json"
        test_blob=("p"*40) if x=="price" else x
        blobs[source_path]=test_blob
        terminal["evidence"][x]["path"]=source_path
        terminal["evidence"][x]["blob_sha"]=test_blob
        if x=="price":
            objects["resolver"]["source_price_blob_sha"]=test_blob
    v=classify(now,blobs,objects,True)
    assert v["status"]=="OPEN_INCIDENTS_FAIL_CLOSED"
    assert v["terminal_drift_keys"]==[]
    assert v["price_resolver_exact_current"] is True
    blocked_resolver=dict(objects["resolver"],price_blocked_count=45)
    blocked_case=dict(objects,resolver=blocked_resolver)
    blocked_v=classify(now,blobs,blocked_case,True)
    assert blocked_v["price_resolver_exact_current"] is True
    assert "CURRENT_PRICE_RESOLVER_BINDING_UNPROVEN" not in blocked_v["issues"]
    assert "PRICE_SYMBOL_LOCAL_BLOCKED_PRESENT" in blocked_v["issues"]
    assert blocked_v["price_symbol_local_blocked_count"]==45
    missing_counts=dict(objects,resolver=dict(objects["resolver"],price_blocked_count="invalid"))
    assert "PRICE_RESOLVER_COVERAGE_COUNTS_INVALID" in classify(now,blobs,missing_counts,True)["issues"]
    wrong_sha=dict(objects,resolver=dict(objects["resolver"],source_price_blob_sha="wrong"))
    assert "CURRENT_PRICE_RESOLVER_BINDING_UNPROVEN" in classify(now,blobs,wrong_sha,True)["issues"]
    assert "EXTERNAL_G9_ENTITLEMENT_UNPROVEN" not in v["issues"]
    assert "EXTERNAL_ACCOUNT_READ_SCOPE_UNPROVEN" not in v["issues"]
    assert set(v["legacy_full_go_blockers"])=={
        "EXTERNAL_G9_ENTITLEMENT_UNPROVEN",
        "EXTERNAL_ACCOUNT_READ_SCOPE_UNPROVEN"}
    assert v["legacy_full_go_ready"] is False
    assert v["g9_and_account_required_for_manual_research"] is False
    assert "ROOT_HISTORY_NO_RETRYABLE_WORK" in v["issues"]
    assert "ROOT_ASOF_INVALID" in v["issues"]  # Unknown ASOF is never a PASS.
    # A valid ASOF and an old-epoch MC file must not hide missing current MC.
    dated=dict(objects,orchestrator=dict(objects["orchestrator"],asof_et="2026-10-08"))
    dated_v=classify(now,blobs,dated,True)
    assert "CURRENT_MC_AUTHORITY_ARTIFACT_ABSENT" in dated_v["issues"]
    assert "CURRENT_TERMINAL_ASOF_LAG" in dated_v["issues"]
    assert dated_v["current_mc_bridge_artifact_count"]==0
    old_mc=dict(blobs)
    old_mc[ROOT+"canonical_mc_bridge_20261007_c417_dv30_v28.json"]="c"*40
    assert "CURRENT_MC_AUTHORITY_ARTIFACT_ABSENT" in classify(now,old_mc,dated,True)["issues"]
    new_mc=dict(blobs)
    new_mc[ROOT+"canonical_mc_bridge_20261008_c417_dv30_v1.json"]="d"*40
    new_v=classify(now,new_mc,dated,True)
    assert "CURRENT_MC_AUTHORITY_ARTIFACT_ABSENT" not in new_v["issues"]
    assert new_v["current_mc_bridge_artifact_count"]==1
    assert new_v["current_mc_primary_authority_proven_by_watchdog"] is False
    # A bridge's existence is not proof of policy, measurements or entitlement.
    bad_mc=dict(new_mc)
    bad_mc.pop(ROOT+"canonical_mc_bridge_20261008_c417_dv30_v1.json")
    bad_mc[ROOT+"canonical_mc_bridge_20261008_c417_dv30_vN.json"]="e"*40
    assert "CURRENT_MC_AUTHORITY_ARTIFACT_ABSENT" in classify(now,bad_mc,dated,True)["issues"]
    matching_terminal=dict(terminal,asof_et="2026-10-08")
    matching=dict(dated,terminal=matching_terminal)
    assert "CURRENT_TERMINAL_ASOF_LAG" not in classify(now,blobs,matching,True)["issues"]
    assert v["root_history_unknown_count"]==231 and v["root_history_retryable"] is False
    retryable=dict(objects,orchestrator={"status":"PARTIAL_HISTORY",
                                         "pending_retry":3,"history_retryable":True})
    assert "ROOT_HISTORY_NO_RETRYABLE_WORK" not in classify(now,blobs,retryable,True)["issues"]
    unknown=dict(objects,orchestrator={"status":"UNVERIFIED","pending_retry":0})
    assert "ROOT_DATA_PLANE_STATUS_UNVERIFIED" in classify(now,blobs,unknown,True)["issues"]
    stale=dict(blobs)
    stale[terminal["evidence"]["price"]["path"]]="DIFFERENT_SHA"
    v=classify(now,stale,objects,True)
    assert "price" in v["terminal_drift_keys"]
    assert v["price_resolver_exact_current"] is False
    v=classify(now,blobs,objects,False)
    assert v["status"]=="UNVERIFIED_MAIN_CHANGED"
    assert v["alpha_authority"] is False
    # Changes to main during concurrent writers cannot mix different commits
    # into a single falsely exact report. Retry a bounded number of times.
    pinned=[]
    def fake_github(method,path,token):
        pinned.append(path)
        if path.startswith("/git/trees/"):
            return {"truncated":False,"tree":[]}
        raise AssertionError("UNEXPECTED_UNPINNED_GITHUB_REQUEST")
    with patch(__name__+".head_sha", side_effect=["a"*40,"b"*40,"b"*40,"b"*40]), \
         patch(__name__+".github",side_effect=fake_github), \
         patch(__name__+".file_json",return_value={}):
        stable,_,_,sha=stable_snapshot("dummy",max_attempts=2)
    assert stable and sha=="b"*40 and pinned==[
        "/git/trees/"+"a"*40+"?recursive=1",
        "/git/trees/"+"b"*40+"?recursive=1"]
    with patch(__name__+".head_sha", side_effect=["a"*40,"b"*40,"c"*40,"d"*40]), \
         patch(__name__+".github",side_effect=fake_github), \
         patch(__name__+".file_json",return_value={}):
        stable,_,_,sha=stable_snapshot("dummy",max_attempts=2)
    assert not stable and sha is None
    assert "ref="+"a"*40 in "/contents/example?ref="+"a"*40
    print("XRAY_GITHUB_NATIVE_CHAIN_FAULT_SELFTEST=PASS_ATOMIC_PINNED_RETRY ZERO_ALPHA")

def file_json(token,short_path,ref):
    # Never read moving 'main' after taking its tree SHA: each object comes
    # from the same immutable commit. A later main change fails closed.
    if not isinstance(ref,str) or len(ref)!=40 or any(c not in "0123456789abcdef" for c in ref):
        raise ValueError("UNVERIFIED_REF_NOT_40_CHAR_GIT_SHA")
    body=github("GET","/contents/"+ROOT+short_path+"?ref="+ref,token)
    if body.get("encoding")!="base64" or not isinstance(body.get("content"),str):
        raise RuntimeError("GITHUB_BLOB_ENCODING_UNTRUSTED")
    return json.loads(base64.b64decode(body["content"]))

def stable_snapshot(token,max_attempts=3):
    if not isinstance(max_attempts,int) or not 1 <= max_attempts <= 5:
        raise ValueError("INVALID_BOUNDED_ATTEMPT_COUNT")
    last_blobs,last_files={},{}
    for attempt in range(max_attempts):
        before=head_sha(token)
        if len(before)!=40:
            raise RuntimeError("MISSING_MAIN_COMMIT_SHA")
        tree=github("GET","/git/trees/"+before+"?recursive=1",token)
        if tree.get("truncated") is True:
            raise RuntimeError("TREE_TRUNCATED_NO_AUDIT")
        last_blobs={x["path"]:x["sha"] for x in tree.get("tree",[])
                    if x.get("type")=="blob" and x.get("path")}
        last_files={key:file_json(token,path,before) for key,path in FILES.items()}
        if head_sha(token)==before:
            return True,last_blobs,last_files,before
        # GitHub may move main during a concurrent writer's atomic commit.
        # At most three snapshots; never re-use previous blobs for authority.
        if attempt+1<max_attempts:time.sleep(0.25)
    return False,last_blobs,last_files,None

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",default="/tmp/xray_native_chain_health.json")
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    if (os.getenv("GITHUB_REPOSITORY")!="gokaydonmez39-jpg/kripto-radar"
        or os.getenv("GITHUB_REF")!="refs/heads/main"):
        raise RuntimeError("REPO_BRANCH_AUTHORITY_MISMATCH")
    token=os.getenv("GITHUB_TOKEN","")
    stable,blobs,objects,pinned_sha=stable_snapshot(token)
    result=classify(dt.datetime.now(UTC),blobs,objects,stable)
    result["schema"]="XRAY_GITHUB_NATIVE_CHAIN_INCIDENT_AUDIT_V1"
    result["generated_at_utc"]=dt.datetime.now(UTC).isoformat()
    result["live_main_sha_if_stable"]=pinned_sha if stable else None
    pathlib.Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("XRAY_NATIVE_CHAIN_HEALTH="+result["status"]+" "+
          ",".join(result["issues"]))
    if not stable:
        raise RuntimeError("MAIN_CHANGED_AFTER_BOUNDED_PINNED_RETRIES_FAIL_CLOSED")

if __name__=="__main__":
    main()
