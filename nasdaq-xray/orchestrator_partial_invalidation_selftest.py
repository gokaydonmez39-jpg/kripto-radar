#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import orchestrator_run as o


def load(root: Path, name: str):
    return json.loads((root/name).read_text())


def test_immutable_membership_authority(root: Path):
    asof="2026-10-06"
    name="master_nasdaq_directory_snapshot_20261006.json"
    snap={
        "schema":"XRAY_NASDAQ_DIRECTORY_SNAPSHOT_V1","asof_et":asof,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
        "authority":"IMMUTABLE_EXACT_ASOF_NASDAQ_DIRECTORY_MEMBERSHIP_SNAPSHOT",
        "applicability":"EXACT_ASOF_MEMBERSHIP_ONLY_NO_FORWARD_CARRY",
        "membership_only":True,"identity_decisions_reused":False,
        "source_queue_classification_ignored":True,
        "source_directory_date":asof,
        "source_directory_footer":"File Creation Time: 10062026 16:00",
        "membership_count":2,"industry_count":0,
        "security_names":{"AAA":"AAA Corp","SPAC":"Example Capital Corp 2 - Class A Ordinary Shares"},
        "industries":{},
    }
    p=root/name
    p.write_text(json.dumps(snap,sort_keys=True)+"\n")
    queue=["AAA"]; unknown=["SPAC"]
    ss={
        "asof_et":asof,"queue":queue,"queue_total":1,
        "queue_hash":o.hash_lines(queue),"raw_identity_total":2,
        "identity_partition_policy":"MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V3_FROZEN_GUARD",
        "identity_unknown_symbols":unknown,
        "identity_unknown_detail":{"SPAC":{"reason":"SPAC_NAME_SUSPECT_OFFICIAL_CLASSIFICATION_UNRESOLVED","unknown_never_pass":True}},
        "discovery_meta":{
            "authority":"IMMUTABLE_EXACT_ASOF_MEMBERSHIP_SNAPSHOT_NO_MARKET_DECISIONS",
            "full_identity":True,
            "identity_partition_policy":"MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V3_FROZEN_GUARD",
            "identity_decisions_reused_from_snapshot":False,
            "membership_snapshot_path":"nasdaq-xray/"+name,
            "membership_snapshot_blob_sha":o.git_blob_sha(p),
            "identity_unknown_count":1,
            "identity_unknown_hash":o.hash_lines(unknown),
            "raw_identity_total":2,"discovery_queue_total":2,
            "official_blank_checks_excluded_count":0,
            "official_blank_checks_excluded_hash":o.hash_lines([]),
        },
    }
    assert o.immutable_membership_partition_ok(ss) is True
    bad=json.loads(json.dumps(ss))
    bad["discovery_meta"]["identity_decisions_reused_from_snapshot"]=True
    assert o.immutable_membership_partition_ok(bad) is False
    bad=json.loads(json.dumps(ss))
    bad["discovery_meta"]["membership_snapshot_blob_sha"]="0"*40
    assert o.immutable_membership_partition_ok(bad) is False
    bad=json.loads(json.dumps(ss))
    bad_snap=json.loads(p.read_text())
    bad_snap["authority"]="WRONG_AUTHORITY"
    p.write_text(json.dumps(bad_snap,sort_keys=True)+"\n")
    bad["discovery_meta"]["membership_snapshot_blob_sha"]=o.git_blob_sha(p)
    assert o.immutable_membership_partition_ok(bad) is False


def test_direct_no_web_authority():
    asof="2026-10-06"
    queue=["AAA"]; unknown=["SPAC"]
    ss={
        "asof_et":asof,
        "official_footer":"File Creation Time: 1006202617:01|||||||",
        "queue":queue,"queue_total":1,"queue_hash":o.hash_lines(queue),
        "raw_identity_total":2,
        "identity_partition_policy":"MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V3_FROZEN_GUARD",
        "identity_unknown_symbols":unknown,
        "identity_unknown_detail":{"SPAC":{
            "reason":"SPAC_NAME_SUSPECT_OFFICIAL_CLASSIFICATION_UNRESOLVED",
            "unknown_never_pass":True,
        }},
        "discovery_meta":{
            "authority":"NASDAQTRADER_FULL_IDENTITY_NO_NASDAQ_WEB_MARKET_METADATA",
            "full_identity":True,
            "nasdaq_web_screener_used":False,
            "identity_partition_policy":"MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V3_FROZEN_GUARD",
            "identity_unknown_count":1,
            "identity_unknown_hash":o.hash_lines(unknown),
            "raw_identity_total":2,
            "discovery_queue_total":2,
            "official_blank_checks_excluded_count":0,
            "official_blank_checks_excluded_hash":o.hash_lines([]),
        },
    }
    assert o.direct_no_web_identity_ok(ss) is True
    bad=json.loads(json.dumps(ss))
    bad["official_footer"]="File Creation Time: 1005202617:01|||||||"
    assert o.direct_no_web_identity_ok(bad) is False
    bad=json.loads(json.dumps(ss))
    bad["discovery_meta"]["nasdaq_web_screener_used"]=True
    assert o.direct_no_web_identity_ok(bad) is False
    bad=json.loads(json.dumps(ss))
    bad["queue_hash"]="0"*64
    assert o.direct_no_web_identity_ok(bad) is False



def test_frozen_canonical_without_snapshot(root: Path):
    """One positive exact canonical partition and hostile drift mutations."""
    import copy
    asof="2026-10-07"
    q=["OPER"]
    unknown=["SPAC"]
    policy="MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD"
    dm={
      "authority":"CANONICAL_FROZEN_FULL_IDENTITY_SAME_ASOF",
      "full_identity":True,"identity_partition_policy":policy,
      "raw_identity_total":2,"discovery_queue_total":2,
      "identity_unknown_count":1,"identity_unknown_hash":o.hash_lines(unknown),
      "official_blank_checks_excluded_count":0,
      "official_blank_checks_excluded_hash":o.hash_lines([]),
      "frozen_identity_path":"nasdaq-xray/canonical_current_full_state.json",
      "frozen_manifest_path":"nasdaq-xray/canonical_current_master_manifest.json",
      "frozen_queue_hash":o.hash_lines(q),
    }
    detail={"SPAC":{"reason":"SPAC_NAME_SUSPECT_OFFICIAL_CLASSIFICATION_UNRESOLVED","unknown_never_pass":True}}
    source={
      "schema":"XRAY_NASDAQ_SCREENER_SINA_V2","asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "identity_partition_policy":policy,"queue":q,"queue_hash":o.hash_lines(q),
      "queue_total":1,"raw_identity_total":2,"identity_unknown_symbols":unknown,
      "identity_unknown_detail":detail,"security_names":{"OPER":"Operating Common"},
      "discovery":{"OPER":{"industry":"Technology"}},"discovery_meta":dm,
    }
    manifest={
      "schema":"XRAY_CANONICAL_CURRENT_MASTER_MANIFEST_V1","asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "identity_partition_policy":policy,"source_state_blob_sha":None,
      "queue_hash":o.hash_lines(q),"pass_symbols":q,"pass_count":1,
      "unknown_symbols":unknown,"unknown_count":1,"raw_identity_total":2,
      "completion_proof":{"identity_partition_policy_exact":True,
                          "identity_unknown_partition_exact":True},
    }
    for key,prefix in [("sec_spac_proof","master_sec_spac_proof_"),
                       ("asof_identity_proof","master_asof_identity_proof_")]:
        name=prefix+"20261007.json"
        (root/name).write_text(json.dumps({"asof_et":asof,"execution":"NONE",
                                            "real_money":"NO-GO","unknown_never_pass":True}))
        sha=o.git_blob_sha(root/name)
        manifest[key]={"path":"nasdaq-xray/"+name,"blob_sha":sha}
        dm[key+"_blob_sha"]=sha
    (root/"canonical_current_full_state.json").write_text(json.dumps(source))
    manifest["source_state_blob_sha"]=o.git_blob_sha(root/"canonical_current_full_state.json")
    (root/"canonical_current_master_manifest.json").write_text(json.dumps(manifest))
    ss=dict(source)
    ss["discovery_meta"]=dict(dm)
    assert o.frozen_identity_partition_ok(ss), "EXACT_FROZEN_CANONICAL_SHOULD_PASS"
    bad=copy.deepcopy(ss)
    bad["identity_unknown_detail"]["SPAC"]["unknown_never_pass"]=False
    assert not o.frozen_identity_partition_ok(bad),"UNKNOWN_MUST_NOT_PROMOTE"
    bad=copy.deepcopy(ss)
    bad["discovery_meta"]["sec_spac_proof_blob_sha"]="0"*40
    assert not o.frozen_identity_partition_ok(bad),"SEC_PROOF_DRIFT_MUST_BLOCK"
    bad=copy.deepcopy(ss)
    bad["queue"]=["OPER","SPAC"]
    assert not o.frozen_identity_partition_ok(bad),"UNPROVEN_SPAC_CANNOT_ENTER_QUEUE"
    manifest["source_state_blob_sha"]="0"*40
    (root/"canonical_current_master_manifest.json").write_text(json.dumps(manifest))
    assert not o.frozen_identity_partition_ok(ss),"FULL_STATE_BLOB_DRIFT_MUST_BLOCK"

def main():
    original_root=o.ROOT
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        o.ROOT=root
        try:
            test_immutable_membership_authority(root)
            test_direct_no_web_authority()
            test_frozen_canonical_without_snapshot(root)
            # Seed deliberately stale prior-ASOF files; invalidation must replace all of them.
            (root/"mc_zero_key_state.json").write_text(
                json.dumps({"schema":"XRAY_MC_ZERO_KEY_V2","asof_et":"2026-09-30",
                            "current_core_zero_key":["STALE"],"unresolved_count":0})+"\n"
            )
            for name in ["production_core_state.json","stage1_shadow.json",
                         "regime_breadth_shadow.json","deep_pre_r1_shadow.json"]:
                (root/name).write_text(json.dumps({"asof_et":"2026-09-30","status":"STALE_PASS"})+"\n")

            summary=o.invalidate_downstream_for_partial_history({"asof_et":"2026-10-06"})
            assert set(summary)=={
                "mc_zero_key_state.json","production_core_state.json","stage1_shadow.json",
                "regime_breadth_shadow.json","deep_pre_r1_shadow.json"
            },summary

            mc=load(root,"mc_zero_key_state.json")
            assert mc["schema"]=="XRAY_MC_ZERO_KEY_V3",mc
            assert mc["status"]=="WAITING_UPSTREAM_HISTORY",mc
            assert mc["asof_et"]=="2026-10-06",mc
            assert mc["alpha_authority"] is False and mc["pit_safe_shadow"] is True,mc
            assert mc["current_core_zero_key"]==[],mc
            assert mc["unresolved_count"]==1,mc
            assert "STALE" not in json.dumps(mc),mc

            core=load(root,"production_core_state.json")
            assert core["status"]=="WAITING_UPSTREAM_HISTORY",core
            assert core["current_core_count"]==0 and core["current_core_mc_pass"]==[],core
            assert core["alpha_authority"] is False,core

            for name in ["stage1_shadow.json","regime_breadth_shadow.json","deep_pre_r1_shadow.json"]:
                obj=load(root,name)
                assert obj["status"]=="WAITING_UPSTREAM_HISTORY",(name,obj)
                assert obj["asof_et"]=="2026-10-06",(name,obj)
                assert obj["alpha_authority"] is False,(name,obj)

            source=(Path(o.__file__).with_name("production_core_build.py")).read_text()
            for token in [
                "MC_STATE_SCHEMA_MISMATCH","MC_STATE_NOT_READY",
                "MC_STATE_SAFETY_MISMATCH","MC_STATE_PIT_AUTHORITY_MISMATCH",
            ]:
                assert token in source,token
        finally:
            o.ROOT=original_root
    # No-progress retry must not spin 16 times once all candidates are
    # classified UNKNOWN_STATIC or UNKNOWN_RETRY_EXHAUSTED.
    retry,reason=o.history_retry_plan({
        "status":"HISTORY_PARTIAL","queue_total":3183,"cursor":3183,
        "pending_retry":0,"unknown_count":231})
    assert retry is False and reason=="NO_RETRYABLE_HISTORY_WORK_REMAINS"
    assert o.history_retry_plan({"status":"HISTORY_PARTIAL","queue_total":3183,
        "cursor":3000,"pending_retry":0})==(True,"NEW_HISTORY_SCOPE_REMAINS")
    assert o.history_retry_plan({"status":"HISTORY_PARTIAL","queue_total":3183,
        "cursor":3183,"pending_retry":3})==(True,"RETRYABLE_HISTORY_UNKNOWN_REMAINS")
    assert o.history_retry_plan({"status":"HISTORY_COMPLETE","queue_total":3183,
        "cursor":3183,"pending_retry":0})==(False,"COMPLETE")
    for invalid in ({"queue_total":0,"cursor":0,"pending_retry":0},
                    {"queue_total":1,"cursor":2,"pending_retry":0},
                    {"queue_total":1,"cursor":1,"pending_retry":-1}):
        try:o.history_retry_plan(invalid)
        except ValueError:pass
        else:raise AssertionError("INVALID_HISTORY_PROGRESS_ACCEPTED")
    print("XRAY_HISTORY_RETRY_PROGRESS_SELFTEST=PASS_4_POSITIVE_3_NEGATIVE")
    print("XRAY_PARTIAL_HISTORY_STALE_STATE_SELFTEST=PASS")


if __name__=="__main__":
    main()
