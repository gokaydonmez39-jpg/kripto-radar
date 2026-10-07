#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import mc_zero_key as m


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
    test_unbound_snapshot_never_authorizes_asof_decision()
    test_explicit_mismatch_fails_closed()
    test_explicit_same_asof_is_shadow_eligible()
    test_preclose_pit_file_never_loads()
    test_exact_asof_pit_loader_accepts_only_explicit_shadow_rows()
    print("MC_ZERO_KEY_PIT_SELFTEST=PASS")
