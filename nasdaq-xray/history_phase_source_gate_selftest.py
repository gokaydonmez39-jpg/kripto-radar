#!/usr/bin/env python3
"""Test the production HISTORY classifier against real Nasdaq session dates.

Synthetic prices exist ONLY in isolated unit-test memory; never a market feed,
research candidate, production artifact, or canonical signal.
"""
from __future__ import annotations
import ast
from datetime import date, timedelta
from pathlib import Path
from history_transport_cache_guard import exact_recent_sessions, official_completed_sessions

ROOT = Path(__file__).resolve().parent
ASOF = "2026-10-08"

def production_classifier():
    source = ROOT.joinpath("history_phase.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename="history_phase.py")
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "classify")
    module = ast.Module(body=[func], type_ignores=[])
    scope = {
        "HARD_DAILY": 260,
        "HARD_WEEKLY": 52,
        # The adversarial input *already* has 52 weekly periods. The daily
        # latest-260 official-session test must be independent of week_count.
        "week_count": lambda by, asof: 52,
        "exact_recent_sessions": exact_recent_sessions,
    }
    exec(compile(module, "history_phase.py", "exec"), scope)
    return scope["classify"], tree

def run():
    classify, tree = production_classifier()
    official = sorted(official_completed_sessions(ASOF))
    assert len(official) >= 261 and official[-1] == ASOF
    required = official[-260:]
    good = {d: (10.0, 1000000.0) for d in required}
    assert exact_recent_sessions(good, ASOF)
    state, info = classify(good, ASOF, "ISOLATED_UNIT_TEST")
    assert state == "PASS_HISTORY", ("valid_260_sessions_should_pass", state, info)

    hole = {d: (10.0, 1000000.0) for d in [official[-261], *required[:100], *required[101:]]}
    assert len(hole) == 260 and ASOF in hole
    assert not exact_recent_sessions(hole, ASOF)
    state, info = classify(hole, ASOF, "ISOLATED_UNIT_TEST")
    assert state != "PASS_HISTORY", ("MISSING_RECENT_OFFICIAL_DATE_PROMOTED_TO_PASS", state, info)

    stale = {d: (10.0, 1000000.0) for d in official[-261:-1]}
    assert len(stale) == 260 and ASOF not in stale
    state, info = classify(stale, ASOF, "ISOLATED_UNIT_TEST")
    assert state != "PASS_HISTORY", ("STALE_ASOF_PROMOTED_TO_PASS", state, info)

    # Two independent feeds may share a missing provider date. This proves
    # data incompleteness, NOT that the issuer never traded on that date.
    eval_node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "eval_one")
    ns = {
        "official_listing_upper_bound_fail": lambda symbol, asof: None,
        "sina": lambda symbol, asof: (hole, {}),
        "nasdaq": lambda symbol, asof: (hole, {}),
        "yahoo": lambda symbol, asof: (hole, {}),
        "eastmoney": lambda symbol, asof: (hole, {}),
        "classify": classify,
        "continuity_composite_pass": lambda *args: None,
        "bridge_resolution": lambda *args: None,
        "aligned_first_bar_upper_bound_fail": lambda *args: None,
    }
    exec(compile(ast.Module(body=[eval_node], type_ignores=[]), "history_phase.py", "exec"), ns)
    _, status, result, _ = ns["eval_one"]("FAKE_SYMBOL_UNIT_TEST", ASOF)
    assert status == "UNKNOWN_HISTORY", ("TWO_SOURCES_SAME_MISSING_BAR_FALSE_FAIL", status, result)

    for name in ("continuity_composite_pass",):
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        calls = {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "exact_recent_sessions" in calls, ("COMPOSITE_CAN_BYPASS_LATEST_260_CHECK", name)
    print("XRAY_HISTORY_PHASE_OFFICIAL_260_SOURCE_GATE=PASS_POSITIVE_MISSING_DAY_STALE_COMPOSITE")

if __name__ == "__main__":
    run()
