#!/usr/bin/env python3
from __future__ import annotations

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


if __name__=="__main__":
    test_unbound_snapshot_never_authorizes_asof_decision()
    test_explicit_mismatch_fails_closed()
    test_explicit_same_asof_is_shadow_eligible()
    print("MC_ZERO_KEY_PIT_SELFTEST=PASS")
