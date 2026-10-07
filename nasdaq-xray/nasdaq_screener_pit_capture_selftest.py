#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone

import nasdaq_screener_pit_capture as m


def price_state():
    return {
        "asof_et":"2026-10-07",
        "execution":"NONE",
        "real_money":"NO-GO",
        "unknown_never_pass":True,
        "pass_symbols":["AAA","BBB","CCC"],
        "results":{
            "AAA":{"info":{"price":100.00}},
            "BBB":{"info":{"price":50.00}},
            "CCC":{"info":{"price":25.00}},
        },
    }


def rows():
    return [
        {"symbol":"AAA","lastsale":"$100.00","marketCap":"3000000000"},
        {"symbol":"BBB","lastsale":"$55.00","marketCap":"4000000000"},
        {"symbol":"CCC","lastsale":"$25.00","marketCap":"0"},
    ]


def test_same_session_post_close_is_per_symbol_fail_closed():
    state=m.build_state(
        rows(),
        price_state(),
        now_utc=datetime(2026,10,7,21,30,tzinfo=timezone.utc),
        source_url=m.URL,
    )
    assert state["same_session_post_close"] is True,state
    assert state["eligible_symbols"]==["AAA"],state["eligible_symbols"]
    assert state["eligible_count"]==1,state
    assert state["unknown_count"]==2,state
    assert state["records"]["AAA"]["shadow_eligible"] is True
    assert state["records"]["BBB"]["reason"]=="NASDAQ_LASTSALE_RTH_CLOSE_MISMATCH"
    assert state["records"]["CCC"]["reason"]=="NASDAQ_MARKET_CAP_MISSING_OR_NONPOSITIVE"
    assert state["alpha_authority"] is False
    assert state["production_mc_authority_changed"] is False


def test_preclose_never_binds():
    state=m.build_state(
        rows(),
        price_state(),
        now_utc=datetime(2026,10,7,18,0,tzinfo=timezone.utc),
        source_url=m.URL,
    )
    assert state["same_session_post_close"] is False,state
    assert state["eligible_count"]==0,state
    assert set(state["reason_counts"])=={"CAPTURE_NOT_SAME_ASOF_POST_CLOSE"},state["reason_counts"]


def test_later_date_never_backfills_prior_asof():
    state=m.build_state(
        rows(),
        price_state(),
        now_utc=datetime(2026,10,8,21,30,tzinfo=timezone.utc),
        source_url=m.URL,
    )
    assert state["same_session_post_close"] is False,state
    assert state["eligible_count"]==0,state


def test_close_match_tolerance():
    ok,meta=m.close_match(100.01,100.00)
    assert ok is True,(ok,meta)
    ok2,meta2=m.close_match(100.05,100.00)
    assert ok2 is False,(ok2,meta2)


if __name__=="__main__":
    test_same_session_post_close_is_per_symbol_fail_closed()
    test_preclose_never_binds()
    test_later_date_never_backfills_prior_asof()
    test_close_match_tolerance()
    print("NASDAQ_SCREENER_PIT_CAPTURE_SELFTEST=PASS")
