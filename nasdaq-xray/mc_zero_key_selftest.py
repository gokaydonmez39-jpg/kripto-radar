#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import mc_zero_key as m


def test_partial_support_history_never_builds_ready_mc_shadow():
    cc={
        "schema":"XRAY_SINA_CANDIDATES_V2",
        "task_id":m.TASK_ID,
        "execution":"NONE",
        "real_money":"NO-GO",
        "asof_et":"2026-10-06",
        "candidate_count":1,
        "candidates":{"AAA":{}},
    }
    ready,reason=m.upstream_history_gate(
        {"status":"HISTORY_PARTIAL","asof_et":"2026-10-06"},cc
    )
    assert ready is False and reason=="WAITING_UPSTREAM_HISTORY",(ready,reason)
    tomb=m.waiting_upstream_state(
        {"status":"HISTORY_PARTIAL","asof_et":"2026-10-06"},cc,reason
    )
    assert tomb["status"]=="WAITING_UPSTREAM_HISTORY",tomb
    assert tomb["alpha_authority"] is False and tomb["unknown_never_pass"] is True,tomb
    assert tomb["unresolved_count"]==1,tomb
    assert tomb["direct_nasdaq_conservative_pass_count"]==0,tomb


def test_complete_exact_bound_support_history_can_reach_shadow_evaluation():
    cc={
        "schema":"XRAY_SINA_CANDIDATES_V2",
        "task_id":m.TASK_ID,
        "execution":"NONE",
        "real_money":"NO-GO",
        "asof_et":"2026-10-06",
        "candidate_count":1,
        "candidates":{"AAA":{}},
    }
    ready,reason=m.upstream_history_gate(
        {"status":"HISTORY_COMPLETE","asof_et":"2026-10-06"},cc
    )
    assert ready is True and reason=="READY",(ready,reason)


def test_unbound_snapshot_never_authorizes_asof_decision():
    ok,meta=m.nasdaq_snapshot_binding(
        {
            "asof_et":"2026-10-06",
            "updated_at_utc":"2026-10-07T13:43:29+00:00",
            "discovery_meta":{"authority":"CANONICAL_FROZEN_FULL_IDENTITY_SAME_ASOF"},
        },
        "2026-10-06",
    )
    assert ok is False, (ok,meta)
    assert meta["status"]=="UNBOUND",meta
    assert meta["reason"]=="NASDAQ_SCREENER_MARKET_DATA_ASOF_MISSING",meta


def test_explicit_mismatch_fails_closed():
    ok,meta=m.nasdaq_snapshot_binding(
        {"discovery_meta":{"market_data_asof_et":"2026-10-07"}},
        "2026-10-06",
    )
    assert ok is False,(ok,meta)
    assert meta["status"]=="ASOF_MISMATCH",meta


def test_explicit_same_asof_is_shadow_eligible():
    ok,meta=m.nasdaq_snapshot_binding(
        {"discovery_meta":{"screener_market_data_asof_et":"2026-10-06"}},
        "2026-10-06",
    )
    assert ok is True,(ok,meta)
    assert meta=={"status":"EXACT_ASOF","observed_asof":"2026-10-06"},meta


def test_preclose_pit_file_never_loads():
    old=m.NASDAQ_PIT
    try:
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"pit.json"
            m.NASDAQ_PIT=p
            p.write_text(json.dumps({
                "schema":"XRAY_NASDAQ_SCREENER_PIT_SHADOW_V1",
                "execution":"NONE",
                "real_money":"NO-GO",
                "unknown_never_pass":True,
                "alpha_authority":False,
                "production_mc_authority_changed":False,
                "asof_et":"2026-10-06",
                "same_session_post_close":False,
                "eligible_count":0,
                "records":{},
            }))
            rows,meta=m.load_nasdaq_pit("2026-10-06")
            assert rows=={},rows
            assert meta["status"]=="UNBOUND",meta
    finally:
        m.NASDAQ_PIT=old


def test_exact_asof_pit_loader_accepts_only_explicit_shadow_rows():
    old=m.NASDAQ_PIT
    try:
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"pit.json"
            m.NASDAQ_PIT=p
            p.write_text(json.dumps({
                "schema":"XRAY_NASDAQ_SCREENER_PIT_SHADOW_V1",
                "execution":"NONE",
                "real_money":"NO-GO",
                "unknown_never_pass":True,
                "alpha_authority":False,
                "production_mc_authority_changed":False,
                "asof_et":"2026-10-06",
                "same_session_post_close":True,
                "eligible_count":1,
                "records":{
                    "AAA":{
                        "status":"SHADOW_ELIGIBLE",
                        "shadow_eligible":True,
                        "close_match":True,
                        "eligible_asof_et":"2026-10-06",
                        "rebased_market_cap_usd":3000000000,
                    },
                    "BBB":{
                        "status":"UNKNOWN",
                        "shadow_eligible":False,
                        "close_match":False,
                        "eligible_asof_et":None,
                        "rebased_market_cap_usd":4000000000,
                    },
                },
            }))
            rows,meta=m.load_nasdaq_pit("2026-10-06")
            assert sorted(rows)==["AAA"],rows
            assert meta["status"]=="PASS",meta
            assert meta["eligible_count"]==1,meta
            assert meta["alpha_authority"] is False,meta
    finally:
        m.NASDAQ_PIT=old


if __name__=="__main__":
    test_partial_support_history_never_builds_ready_mc_shadow()
    test_complete_exact_bound_support_history_can_reach_shadow_evaluation()
    test_unbound_snapshot_never_authorizes_asof_decision()
    test_explicit_mismatch_fails_closed()
    test_explicit_same_asof_is_shadow_eligible()
    test_preclose_pit_file_never_loads()
    test_exact_asof_pit_loader_accepts_only_explicit_shadow_rows()
    print("MC_ZERO_KEY_PIT_SELFTEST=PASS")
