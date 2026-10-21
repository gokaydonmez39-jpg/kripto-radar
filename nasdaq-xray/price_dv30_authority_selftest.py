#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from price_dv30_recover_from_fullstate import (
    apply_c417_rallies_primary_partition,
    apply_c417_rallies_primary_pass_veto,
    apply_persistent_terminal_fail_overrides,
    c417_rallies_primary_pass_conflicts,
    c417_rallies_primary_path,
    git_blob_sha,
    load_c417_rallies_primary,
    validate_persistent_terminal_fail_override,
)

ROOT=Path(__file__).resolve().parent


def primary_union(primary):
    return (
        set((primary.get("fail_price") or {}).keys())
        | set((primary.get("fail_dv30") or {}).keys())
        | set((primary.get("pass_price_dv30") or {}).keys())
        | set((primary.get("block_current_run") or {}).keys())
    )


def verify_fractional_rallies_volume_guard(asof):
    """Test-only: complete integer RTH samples must pass the mathematical
    partition, but one fractional vendor volume poisons exact30 PASS.
    These synthetic in-memory rows never enter canonical PRICE authority.
    """
    from price_dv30_recover_from_fullstate import (
        build_c417_rallies_newscope_partition,
        expected30,
    )
    symbol="__XRAY_VOLUME_INTEGRITY_TEST_ONLY__"
    days=expected30(asof)
    assert len(days)==30 and days[-1]==asof
    rows=[{"date":day,"close":100.0,"volume":1_000_000.0} for day in days]
    complete,complete_meta=build_c417_rallies_newscope_partition(
        {symbol:rows},asof,[symbol],{}
    )
    assert complete_meta["scope_count"]==1
    assert symbol in complete["pass_price_dv30"]
    assert not complete["block_current_run"]
    contaminated=[dict(row) for row in rows]
    contaminated[4]["volume"]=1_000_000.25
    rejected,rejected_meta=build_c417_rallies_newscope_partition(
        {symbol:contaminated},asof,[symbol],{}
    )
    assert rejected_meta["scope_count"]==1
    assert symbol not in rejected["pass_price_dv30"]
    assert symbol not in rejected["fail_dv30"]
    assert symbol in rejected["block_current_run"]
    block=rejected["block_current_run"][symbol]
    assert block["reason"]=="RALLIES_NEW_SCOPE_NONINTEGRAL_VOLUME_NOT_UNADJUSTED_RTH_PROOF"
    assert block["observed_usable_sessions"]==29
    assert block["missing_sessions"]==[days[4]]
    assert block["nonintegral_volume_sessions"]==[days[4]]
    print("XRAY_RALLIES_FRACTIONAL_VOLUME_RUNTIME_SELFTEST=PASS_POSITIVE_AND_NEGATIVE_TEST_ONLY")


def verify_current_price_cache_partition_safety() -> None:
    """Production baseline must not accept mismatched status/count/hash evidence."""
    import copy
    from price_dv30_recover_from_fullstate import price_snapshot_integrity
    snap = json.loads((ROOT / "canonical_current_price_dv30.json").read_text())
    asof = snap["asof_et"]
    if not price_snapshot_integrity(snap, asof):
        raise RuntimeError("KNOWN_CURRENT_PRICE_SNAPSHOT_FAILED_STRUCTURAL_BASELINE")
    symbol = snap["unknown_symbols"][0]
    forged = copy.deepcopy(snap)
    forged["results"][symbol]["status"] = "PASS_PRICE_DV30"
    if price_snapshot_integrity(forged, asof):
        raise RuntimeError("CORRUPTED_PRICE_STATUS_PARTITION_ACCEPTED")
    forged = copy.deepcopy(snap)
    forged["pass_symbols"] = [symbol]
    forged["pass_count"] = 1
    if price_snapshot_integrity(forged, asof):
        raise RuntimeError("CORRUPTED_PRICE_PASS_SET_ACCEPTED")
    forged = copy.deepcopy(snap)
    forged["counts"]["FAIL_PRICE"] += 1
    forged["counts"]["FAIL_DV30"] -= 1
    if price_snapshot_integrity(forged, asof):
        raise RuntimeError("CORRUPTED_PRICE_COUNT_PARTITION_ACCEPTED")
    forged = copy.deepcopy(snap)
    forged["pass_hash"] = "0" * 64
    if price_snapshot_integrity(forged, asof):
        raise RuntimeError("CORRUPTED_PRICE_PASS_HASH_ACCEPTED")
    print("XRAY_C417_PRICE_CACHED_PARTITION_INTEGRITY=PASS_REAL_SNAPSHOT_FOUR_NEGATIVES")


def main():
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    asof=str(master.get("asof_et") or "")
    assert len(asof)==10,asof
    verify_fractional_rallies_volume_guard(asof)
    verify_current_price_cache_partition_safety()
    master_queue=list(master.get("pass_symbols") or [])
    assert master_queue and len(master_queue)==int(master.get("pass_count",-1))

    # New-source runtime admission must deny unverified current Rallies PASS
    # independently of immutable 2026-10-07 historical fixture behavior.
    from price_dv30_recover_from_fullstate import (
        rallies_current_positive_authority_allowed,
        valid_bridge_price_resolution,
    )
    if asof >= "2026-10-12":
        assert rallies_current_positive_authority_allowed(asof) is False
        unverified={
            "decision":"PASS_PRICE_DV30",
            "source":"RALLIES_CANDLESTICK_SCANNER_EXACT30_PRIMARY",
            "proof":"RALLIES_EXACT30_MEDIAN_GE_GATE",
            "known_session_count":30,
            "missing_sessions":[],
            "price":300.0,
            "dv30":1_000_000_000.0,
            "no_synthetic_bar":True,
            "compact_terminal_proof":True,
        }
        assert valid_bridge_price_resolution(unverified,asof) is False
        sample_primary={
            "asof_et":asof,
            "pass_price_dv30":{"AAPL":{
                "asof_close":300.0,"dv30_median":1_000_000_000.0,
                "known_session_count":30,"missing_sessions":[]
            }},
        }
        synthetic={"AAPL":{"status":"UNKNOWN","info":{"reason":"TEST"}}}
        assert apply_c417_rallies_primary_partition(synthetic,sample_primary,["AAPL"])==[]
        assert synthetic["AAPL"]["status"]=="UNKNOWN"
        assert rallies_current_positive_authority_allowed("2026-10-07") is True
        print("XRAY_RALLIES_CURRENT_POSITIVE_RUNTIME_QUARANTINE=PASS_NEGATIVE_PLUS_HISTORY_REPLAY")

    primary,meta=load_c417_rallies_primary(asof)
    if primary is None:
        # Live provider evidence is an INPUT, not a fixture. Do not make the
        # entire factory crash when an expected same-ASOF primary is absent.
        # Invalid or corrupt *present* sources still fail this test.
        current_path=c417_rallies_primary_path(asof)
        if current_path.is_file():
            raise AssertionError("MALFORMED_CURRENT_PRIMARY_MUST_FAIL_CLOSED:"+str(meta))
        assert meta.get("status")=="UNKNOWN",meta
        assert "FileNotFoundError" in str(meta.get("reason")),meta
        from price_dv30_recover_from_fullstate import load_c417_rallies_effective_primary
        effective,emeta=load_c417_rallies_effective_primary(asof,master_queue)
        assert effective is None and emeta.get("status")!="PASS",(emeta,effective)
        # The last immutable completed-session fixture still verifies actual
        # partition semantics without upgrading that old date to this date.
        prior,prior_meta=load_c417_rallies_primary("2026-10-07")
        assert prior is not None and prior_meta.get("status")=="PASS",prior_meta
        assert prior.get("asof_et")!=asof,"CROSS_ASOF_PRIMARY_PROMOTION_FORBIDDEN"
        prior_pass=sorted((prior.get("pass_price_dv30") or {}).keys())
        assert prior_pass,"PRIOR_PRIMARY_REGRESSION_FIXTURE_MISSING"
        materialized={prior_pass[0]:{"status":"UNKNOWN","info":{"reason":"TEST"}}}
        changed=apply_c417_rallies_primary_partition(materialized,prior,[prior_pass[0]])
        assert changed==[prior_pass[0]],changed
        assert materialized[prior_pass[0]]["status"]=="PASS_PRICE_DV30"
        print(json.dumps({
          "C417_DV30_CONTROL_SELFTEST":"PASS",
          "C417_DV30_CURRENT_AUTHORITY":"BLOCKED_MISSING_REAL_ASOF_PRIMARY",
          "asof_et":asof,
          "current_primary_path":str(current_path),
          "current_pass_authority_granted":False,
          "prior_session_fixture_only":prior["asof_et"],
          "no_cross_asof_rebind":True,
          "unknown_never_pass":True
        },sort_keys=True))
        return
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
        # Exact-ASOF primary witness is immutable. A subsequent official
        # identity revision may demote a symbol from MASTER PASS to UNKNOWN
        # without rewriting historic Rallies rows. No current MASTER symbol
        # may lack a primary row; primary-only rows have zero alpha authority.
        assert set(master_queue).issubset(universe), "CURRENT_MASTER_SYMBOL_UNCOVERED_BY_RALLIES_V2"
        assert not (set(master_queue)-universe)
        primary_only=sorted(universe-set(master_queue))

        bridge_path=ROOT/"canonical_resolver_bridge_20261007_c417_dv30_v5.json"
        bridge=json.loads(bridge_path.read_text())
        # Immutable predecessor bridge is scoped to its original queue.
        # Test its genuine historical authority without rebinding it into a
        # revised current master. A cross-queue acceptance is forbidden.
        historical_queue_hash=bridge.get("queue_hash")
        terminal=validate_persistent_terminal_fail_override(
            bridge,"BBCI",asof,historical_queue_hash
        )
        if historical_queue_hash!=master.get("queue_hash"):
            assert validate_persistent_terminal_fail_override(
                bridge,"BBCI",asof,master.get("queue_hash")
            ) is None, "STALE_BRIDGE_CURRENT_QUEUE_REBIND_FORBIDDEN"
        assert terminal is not None,bridge_path
        assert terminal.get("decision")=="FAIL_DV30_INSUFFICIENT_SESSIONS",terminal
        assert terminal.get("proof")=="ALPACA_RALLIES_EXACT_MISSING_SET_MATCH",terminal
        assert terminal.get("known_session_count")==1,terminal
        assert len(terminal.get("missing_sessions") or [])==29,terminal

        applied_rows={"BBCI":{"status":"BLOCK_CURRENT_RUN","info":{"reason":"TEST"}}}
        applied=apply_persistent_terminal_fail_overrides(applied_rows,{"BBCI":terminal})
        assert applied==["BBCI"],applied
        assert applied_rows["BBCI"]["status"]=="FAIL_DV30_INSUFFICIENT_SESSIONS",applied_rows

        protected_rows={"BBCI":{"status":"PASS_PRICE_DV30","info":{"reason":"TEST"}}}
        protected=apply_persistent_terminal_fail_overrides(protected_rows,{"BBCI":terminal})
        assert protected==[],protected
        assert protected_rows["BBCI"]["status"]=="PASS_PRICE_DV30",protected_rows

        bad=json.loads(json.dumps(bridge))
        bad["terminal_override_evidence"]["BBCI"]["rallies"]["missing_sessions"]=(
            bad["terminal_override_evidence"]["BBCI"]["rallies"]["missing_sessions"][:-1]
        )
        assert validate_persistent_terminal_fail_override(
            bad,"BBCI",asof,historical_queue_hash
        ) is None

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

    # A validated same-ASOF fail-only terminal resolution must survive a later
    # primary replay that still has only BLOCK_CURRENT_RUN for the symbol.
    terminal_sym="BBCI" if "BBCI" in bc else block_sym
    terminal_block=bc[terminal_sym]
    terminal_missing=list(terminal_block.get("missing_sessions") or [])
    terminal_known=int(terminal_block.get("observed_usable_sessions") or (30-len(terminal_missing)))
    assert 0 <= terminal_known < 30 and len(terminal_missing)==30-terminal_known,(terminal_sym,terminal_block)
    terminal_results={
      terminal_sym:{
        "status":"FAIL_DV30_INSUFFICIENT_SESSIONS",
        "info":{
          "price":11.0,
          "known_session_count":terminal_known,
          "missing_sessions":terminal_missing,
          "proof":"ALPACA_RALLIES_EXACT_MISSING_SET_MATCH",
          "source":"ALPACA_SIP_RALLIES_MASSIVE_C4_17_NON_G9",
          "no_synthetic_bar":True,
        },
        "provenance":"AUTHENTICATED_TASKSTATE_RESOLVER_BRIDGE",
      }
    }
    terminal_before=json.loads(json.dumps(terminal_results[terminal_sym]))
    terminal_changed=apply_c417_rallies_primary_partition(
        terminal_results,primary,[terminal_sym]
    )
    assert terminal_changed==[],terminal_changed
    assert terminal_results[terminal_sym]==terminal_before,terminal_results[terminal_sym]

    invalid_terminal={
      terminal_sym:{
        "status":"FAIL_DV30_INSUFFICIENT_SESSIONS",
        "info":{
          "price":11.0,
          "known_session_count":terminal_known,
          "missing_sessions":terminal_missing,
          "proof":"INVALID_TEST_PROOF",
          "source":"TEST",
          "no_synthetic_bar":True,
        },
      }
    }
    invalid_changed=apply_c417_rallies_primary_partition(
        invalid_terminal,primary,[terminal_sym]
    )
    assert invalid_changed==[terminal_sym],invalid_changed
    assert invalid_terminal[terminal_sym]["status"]=="BLOCK_CURRENT_RUN",invalid_terminal[terminal_sym]

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
      "historical_primary_only_count_nonalpha":len(universe-set(master_queue)),
      "covered_current_queue_count":len(covered),
      "uncovered_current_queue_count":len(uncovered),
      "pass_count":len(pp),
      "block_count":len(bc),
      "pass_fixture":pass_sym,
      "block_fixture":block_sym,
    },sort_keys=True))


if __name__=="__main__":
    main()
