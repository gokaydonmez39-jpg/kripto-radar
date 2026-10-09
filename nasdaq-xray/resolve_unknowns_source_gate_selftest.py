#!/usr/bin/env python3
"""Regression on legacy resolver: date coverage outranks bar count.

Uses only unit-test placeholders; never emits market observations or AL.
"""
from __future__ import annotations
import ast
from pathlib import Path
from history_transport_cache_guard import official_completed_sessions, exact_recent_sessions

ROOT=Path(__file__).resolve().parent
ASOF="2026-09-30"

def production_classifier(weeks=52):
    tree=ast.parse((ROOT/"resolve_unknowns_fallback.py").read_text(encoding="utf-8"))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="classify")
    scope={"HARD_PRICE":5.0,"HARD_DV30":50_000_000.0,"HARD_HISTORY":260,
           "exact_recent_sessions":exact_recent_sessions,
           "week_count":lambda by,asof:weeks,
           "math":__import__("math")}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),"resolve_unknowns_fallback.py","exec"),scope)
    return scope["classify"]

def main():
    classify=production_classifier()
    insufficient_weeks=production_classifier(weeks=51)
    dates=sorted(official_completed_sessions(ASOF))
    assert len(dates)>=261 and dates[-1]==ASOF
    required=dates[-260:]
    recent30=required[-30:]
    good={d:(10.0,6_000_000.0) for d in required}
    assert exact_recent_sessions(good,ASOF)
    result, info=classify(good,ASOF,recent30,"UNIT_TEST_NOT_REAL_MARKET_DATA")
    assert result=="PASS_HARD_GATES",("BASELINE_260_OFFICIAL_MUST_PASS",result,info)
    result,info=insufficient_weeks(good,ASOF,recent30,"UNIT_TEST_NOT_REAL_MARKET_DATA")
    assert result!="PASS_HARD_GATES",("52_COMPLETED_WEEKLY_REQUIRED",result,info)
    hole={d:(10.0,6_000_000.0) for d in [dates[-261],*required[:90],*required[91:]]}
    assert len(hole)==260 and not exact_recent_sessions(hole,ASOF)
    result,info=classify(hole,ASOF,recent30,"UNIT_TEST_NOT_REAL_MARKET_DATA")
    assert result!="PASS_HARD_GATES",("LEGACY_RESOLVER_OLD_BAR_HIDES_MISSING_OFFICIAL_SESSION",result,info)
    stale={d:(10.0,6_000_000.0) for d in dates[-261:-1]}
    result,info=classify(stale,ASOF,recent30,"UNIT_TEST_NOT_REAL_MARKET_DATA")
    assert result!="PASS_HARD_GATES",("STALE_ASOF",result,info)
    tree=ast.parse((ROOT/"resolve_unknowns_fallback.py").read_text(encoding="utf-8"))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="resolve_symbol")
    scope={"nasdaq_hist":lambda sym,asof:(hole,{}),
           "yahoo_hist":lambda sym,asof:(hole,{}),
           "classify":classify}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),"resolve_unknowns_fallback.py","exec"),scope)
    sym,resolution,unresolved=scope["resolve_symbol"]("UNIT_TEST",{},ASOF,recent30)
    assert sym=="UNIT_TEST" and resolution is None and unresolved is not None, (
        "TWO_PROVIDERS_SAME_TRUNCATED_BARS_FALSE_IPO_FAIL",resolution)
    print("XRAY_LEGACY_RESOLVER_LATEST260_DATE_AUTHORITY=PASS_POSITIVE_MISSING_WEEK_TWO_PROVIDER")

if __name__=="__main__":
    main()
