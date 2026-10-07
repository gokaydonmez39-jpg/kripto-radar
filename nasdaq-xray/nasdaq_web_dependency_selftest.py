#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import price_dv30_phase as p
import price_dv30_recover_from_fullstate as recover
import sina_stage as s

ROOT=Path(__file__).resolve().parent


def fake_complete_bars(exp30,price=10.0,volume=6_000_000.0):
    return {d:(price,volume) for d in exp30}


def test_full_identity_builder_never_calls_web_screener():
    original=s.screener_rows
    def forbidden():
        raise AssertionError("NASDAQ_WEB_SCREENER_CALLED")
    s.screener_rows=forbidden
    try:
        q,disc,meta,excluded=s.build_full_identity_from_directory(
            {"AAA":"AAA Operating Inc.","BBB":"BBB Operating Inc."},
            {},
            {},
        )
    finally:
        s.screener_rows=original
    assert q==["AAA","BBB"],q
    assert excluded=={},excluded
    assert meta["authority"]=="NASDAQTRADER_FULL_IDENTITY_NO_NASDAQ_WEB_MARKET_METADATA",meta
    assert meta["nasdaq_web_screener_used"] is False,meta
    for sym in q:
        row=disc[sym]
        assert row["screener_price"] is None
        assert row["screener_market_cap"] is None
        assert row["screener_volume"] is None
        assert row["industry"] is None


def test_nasdaq_historical_helper_is_nonterminal_disabled():
    bars,meta=p.nasdaq("AAPL","2026-10-06")
    assert bars=={},bars
    assert meta["disabled"] is True,meta
    assert meta["reason"]=="NASDAQ_WEB_AUTOMATION_DISABLED_TOS_AND_PIT",meta
    assert meta["no_pass_or_fail_created"] is True,meta


def test_eval_sina_pass_is_nonterminal_and_yahoo_remains_fail_only():
    exp30=[f"2026-09-{i:02d}" for i in range(2,31)]+["2026-10-06"]
    original_sina,original_yahoo=p.sina,p.yahoo
    try:
        # C4.17 DV30 PASS authority is Rallies primary / Longbridge fallback.
        # A mathematically passing Sina sample is therefore diagnostic only.
        p.sina=lambda sym,asof:(fake_complete_bars(exp30),{"usable":30})
        p.yahoo=lambda sym,asof:(fake_complete_bars(exp30),{"usable":30,"exchangeName":"NMS"})
        _,st,info,prov=p.eval_one("AAA",exp30,"2026-10-06")
        assert st=="UNKNOWN",(st,info,prov)
        assert info["reason"]=="C417_DV30_PRIMARY_OR_FALLBACK_AUTHORITY_REQUIRED",info
        assert info["sina_result"]["reason"]=="SINA_NONAUTHORITATIVE_FOR_C417_DV30_PASS",info
        assert info["yahoo_result"]["proof"]=="EXACT30_MEDIAN_GE_GATE",info

        p.sina=lambda sym,asof:({},{"error":"SINA_TEST_UNAVAILABLE"})
        p.yahoo=lambda sym,asof:(fake_complete_bars(exp30),{"usable":30,"exchangeName":"NMS"})
        _,st,info,prov=p.eval_one("AAA",exp30,"2026-10-06")
        assert st=="UNKNOWN",(st,info,prov)
        assert info["yahoo_result"]["proof"]=="EXACT30_MEDIAN_GE_GATE",info

        low=fake_complete_bars(exp30,price=4.0,volume=20_000_000.0)
        p.yahoo=lambda sym,asof:(low,{"usable":30,"exchangeName":"NMS"})
        _,st,info,prov=p.eval_one("AAA",exp30,"2026-10-06")
        assert st=="FAIL_PRICE",(st,info,prov)
        assert info["source"]=="YAHOO_CHART_FREE_FAIL_ONLY",info
    finally:
        p.sina, p.yahoo=original_sina,original_yahoo


def test_global_sentinel_disabled_not_a_decision():
    stop,meta=recover.global_asof_sentinel_nonterminal(
        ["AAPL","MSFT","NVDA"],"2026-10-06",["x"]*30
    )
    assert stop is False,(stop,meta)
    assert meta["status"]=="DISABLED_NO_SINGLE_SOURCE_GLOBAL_SENTINEL",meta
    assert meta["no_pass_or_fail_created"] is True,meta


def test_current_canonical_pass_has_no_nasdaq_web_dependency():
    j=json.loads((ROOT/"canonical_current_price_dv30.json").read_text(encoding="utf-8"))
    passes=list(j.get("pass_symbols") or [])
    assert len(passes)==int(j.get("pass_count",-1))
    assert hashlib.sha256("\n".join(passes).encode()).hexdigest()==j.get("pass_hash")
    for sym in passes:
        row=(j.get("results") or {}).get(sym) or {}
        assert row.get("status")=="PASS_PRICE_DV30",(sym,row.get("status"))
        src=str((row.get("info") or {}).get("source") or "")
        assert "NASDAQ" not in src.upper(),(sym,src)
    print(json.dumps({
        "current_pass_count":len(passes),
        "current_pass_hash":j.get("pass_hash"),
        "nasdaq_web_pass_dependencies":0,
    },sort_keys=True))


if __name__=="__main__":
    test_full_identity_builder_never_calls_web_screener()
    test_nasdaq_historical_helper_is_nonterminal_disabled()
    test_eval_sina_pass_is_nonterminal_and_yahoo_remains_fail_only()
    test_global_sentinel_disabled_not_a_decision()
    test_current_canonical_pass_has_no_nasdaq_web_dependency()
    print("NASDAQ_WEB_DEPENDENCY_SELFTEST=PASS")
