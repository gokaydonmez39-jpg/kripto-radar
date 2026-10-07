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


def main():
    original_root=o.ROOT
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        o.ROOT=root
        try:
            test_immutable_membership_authority(root)
            test_direct_no_web_authority()
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
    print("XRAY_PARTIAL_HISTORY_STALE_STATE_SELFTEST=PASS")


if __name__=="__main__":
    main()
