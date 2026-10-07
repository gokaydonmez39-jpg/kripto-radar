#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from price_dv30_recover_from_fullstate import (
    apply_c417_rallies_primary_partition,
    apply_c417_rallies_primary_pass_veto,
    c417_rallies_primary_pass_conflicts,
    c417_rallies_primary_path,
    git_blob_sha,
    load_c417_rallies_primary,
)

ROOT=Path(__file__).resolve().parent


def primary_union(primary):
    return (
        set((primary.get("fail_price") or {}).keys())
        | set((primary.get("fail_dv30") or {}).keys())
        | set((primary.get("pass_price_dv30") or {}).keys())
        | set((primary.get("block_current_run") or {}).keys())
    )


def main():
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    asof=str(master.get("asof_et") or "")
    assert len(asof)==10,asof
    master_queue=list(master.get("pass_symbols") or [])
    assert master_queue and len(master_queue)==int(master.get("pass_count",-1))

    primary,meta=load_c417_rallies_primary(asof)
    assert primary is not None,meta
    assert meta.get("status")=="PASS",meta
    assert primary.get("asof_et")==asof,primary.get("asof_et")
    assert primary.get("authority")=="C4.17_RALLIES_EXACT30_PRIMARY"
    assert primary.get("execution")=="NONE" and primary.get("real_money")=="NO-GO"
    assert primary.get("unknown_never_pass") is True
    assert len(primary.get("expected30") or [])==30
    assert (primary.get("expected30") or [])[-1]==asof
    assert (primary.get("thresholds") or {}).get("price")==">=5"
    assert (primary.get("thresholds") or {}).get("dv30")=="median exactly30 Close*Volume >=50000000"

    fp=primary.get("fail_price") or {}
    fd=primary.get("fail_dv30") or {}
    pp=primary.get("pass_price_dv30") or {}
    bc=primary.get("block_current_run") or {}
    groups=[set(fp),set(fd),set(pp),set(bc)]
    assert all(not (groups[i]&groups[j]) for i in range(len(groups)) for j in range(i+1,len(groups)))
    universe=set().union(*groups)
    assert len(universe)==int(primary.get("symbol_count",-1))
    assert (primary.get("counts") or {})=={
      "FAIL_PRICE":len(fp),
      "FAIL_DV30":len(fd),
      "PASS_PRICE_DV30":len(pp),
      "BLOCK_CURRENT_RUN":len(bc),
    }
    if asof=="2026-10-07":
        selected=c417_rallies_primary_path(asof)
        expected=ROOT/"evidence"/"rallies_dv30_20261007_classification_v2.json"
        assert selected==expected,(selected,expected)
        assert meta.get("path")==str(expected),meta
        assert meta.get("blob_sha")==git_blob_sha(expected),meta
        assert int(primary.get("symbol_count",-1))==3185,primary.get("symbol_count")
        assert (primary.get("counts") or {})=={
          "FAIL_PRICE":1304,
          "FAIL_DV30":1246,
          "PASS_PRICE_DV30":510,
          "BLOCK_CURRENT_RUN":125,
        },primary.get("counts")
        assert set(master_queue)==universe,"CURRENT_MASTER_NOT_EXACTLY_COVERED_BY_RALLIES_V2"

    current=set(master_queue)
    covered=sorted(current & universe)
    uncovered=sorted(current - universe)
    assert covered,"CURRENT_QUEUE_HAS_NO_RALLIES_PRIMARY_COVERAGE"
    assert pp,"RALLIES_PRIMARY_PASS_FIXTURE_MISSING"
    assert bc,"RALLIES_PRIMARY_BLOCK_FIXTURE_MISSING"

    pass_sym="AAPL" if "AAPL" in pp else sorted(pp)[0]
    block_sym="GRAL" if "GRAL" in bc else sorted(bc)[0]
    uncovered_sym=uncovered[0] if uncovered else "__UNBOUND_TEST__"

    materialized={
      pass_sym:{"status":"UNKNOWN","info":{"reason":"TEST"}},
      block_sym:{"status":"UNKNOWN","info":{"reason":"TEST"}},
      uncovered_sym:{"status":"UNKNOWN","info":{"reason":"TEST"}},
    }
    changed=apply_c417_rallies_primary_partition(
        materialized,primary,[pass_sym,block_sym,uncovered_sym]
    )
    assert pass_sym in changed and block_sym in changed,changed
    assert uncovered_sym not in changed,changed
    assert materialized[pass_sym]["status"]=="PASS_PRICE_DV30",materialized[pass_sym]
    assert materialized[pass_sym]["info"]["known_session_count"]==30,materialized[pass_sym]
    assert materialized[pass_sym]["info"]["price"]>=5,materialized[pass_sym]
    assert materialized[pass_sym]["info"]["dv30"]>=50_000_000,materialized[pass_sym]
    assert materialized[block_sym]["status"]=="BLOCK_CURRENT_RUN",materialized[block_sym]
    assert materialized[uncovered_sym]["status"]=="UNKNOWN",materialized[uncovered_sym]

    synthetic_price={"asof_et":asof,"pass_symbols":[pass_sym,block_sym]}
    conflicts,conflict_meta=c417_rallies_primary_pass_conflicts(
        synthetic_price,[pass_sym,block_sym]
    )
    assert conflict_meta.get("status")=="PASS",conflict_meta
    assert conflicts==[block_sym],conflicts

    fake_results={
      pass_sym:{"status":"PASS_PRICE_DV30","info":{"source":"RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9"}},
      block_sym:{"status":"PASS_PRICE_DV30","info":{"source":"TEST_UNAUTHORIZED_PASS"}},
    }
    vetoed=apply_c417_rallies_primary_pass_veto(fake_results,primary)
    assert vetoed==[block_sym],vetoed
    assert fake_results[pass_sym]["status"]=="PASS_PRICE_DV30",fake_results[pass_sym]
    assert fake_results[block_sym]["status"]=="BLOCK_CURRENT_RUN",fake_results[block_sym]

    if "GRAL" in bc:
        gral=bc["GRAL"]
        assert gral.get("observed_usable_sessions")==29,gral
        assert gral.get("missing_sessions")==["2026-09-23"],gral

    print(json.dumps({
      "C417_DV30_PASS_AUTHORITY_SELFTEST":"PASS",
      "asof_et":asof,
      "primary_symbol_count":len(universe),
      "current_queue_count":len(master_queue),
      "covered_current_queue_count":len(covered),
      "uncovered_current_queue_count":len(uncovered),
      "pass_count":len(pp),
      "block_count":len(bc),
      "pass_fixture":pass_sym,
      "block_fixture":block_sym,
    },sort_keys=True))


if __name__=="__main__":
    main()
