#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import orchestrator_run as o


def load(root: Path, name: str):
    return json.loads((root/name).read_text())


def main():
    original_root=o.ROOT
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        o.ROOT=root
        try:
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
