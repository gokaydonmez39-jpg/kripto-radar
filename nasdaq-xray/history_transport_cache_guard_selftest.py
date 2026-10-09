#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import gzip
import tempfile
from datetime import date, timedelta
from pathlib import Path

import history_transport_cache_guard as g


ASOF = "2026-10-06"


def write_cache(root: Path, sym: str, dates: list[str]) -> None:
    p = g.cache_path(root, sym)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date","open","high","low","close","volume"])
        w.writeheader()
        for i, d in enumerate(dates):
            px = 100.0 + i * 0.01
            w.writerow({"date":d,"open":px,"high":px+1,"low":px-1,"close":px+0.2,"volume":1000000+i})


def daily_ending(end: str, n: int) -> list[str]:
    # Completed Nasdaq sessions are not simply Monday-Friday: Labor Day,
    # Good Friday, Juneteenth, unscheduled closures etc must be omitted.
    import pandas_market_calendars as mcal
    d=date.fromisoformat(end)
    start=d-timedelta(days=n*3+60)
    idx=mcal.get_calendar("NASDAQ").valid_days(
        start_date=start.isoformat(),end_date=end)
    out=[x.date().isoformat() for x in idx]
    assert len(out)>=n,("INSUFFICIENT_ACTUAL_SESSIONS",len(out),n)
    return out[-n:]


def fixtures():
    history = {
        "task_id": g.TASK,
        "asof_et": ASOF,
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "unknown_count": 0,
        "pass_symbols": ["A","ECHO"],
    }
    legal = {
        "task_id": g.TASK,
        "asof_et": ASOF,
        "execution": "NONE",
        "real_money": "NO-GO",
        "counts": {"UNKNOWN_LEGAL": 0},
        "pass_symbols": ["A","ECHO"],
    }
    identity = {
        "records": {
            "ECHO": {
                "mode": "OFFICIAL_TICKER_CONTINUITY_COMPOSITE_HISTORY",
                "predecessor_symbol": "SATS",
                "effective_date": "2026-06-24",
                "cusip_unchanged": True,
            }
        }
    }
    return history, legal, identity


def make_good_cache(root: Path):
    write_cache(root, "A", daily_ending(ASOF, 300))
    write_cache(root, "QQQ", daily_ending(ASOF, 320))
    echo_dates = [d for d in daily_ending(ASOF, 150) if d >= "2026-06-24"]
    write_cache(root, "ECHO", echo_dates)
    sats_dates = [d for d in daily_ending("2026-06-23", 240) if d < "2026-06-24"]
    write_cache(root, "SATS", sats_dates)


def test_complete_exact_asof_cache_passes():
    h,l,i = fixtures()
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        make_good_cache(root)
        ok, detail=g.evaluate(root,h,l,i,require_qqq=True)
        assert ok is True, detail
        assert detail["reason"]=="EXACT_ASOF_TRANSPORT_CACHE_COMPLETE",detail
        assert detail["missing_count"]==0,detail


def test_stale_qqq_fails():
    h,l,i = fixtures()
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        make_good_cache(root)
        write_cache(root,"QQQ",daily_ending("2026-10-05",320))
        ok, detail=g.evaluate(root,h,l,i,require_qqq=True)
        assert ok is False,detail
        assert detail["missing"]["QQQ"].startswith("ASOF_MISSING:"),detail


def test_missing_continuity_predecessor_fails():
    h,l,i = fixtures()
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        make_good_cache(root)
        g.cache_path(root,"SATS").unlink()
        ok, detail=g.evaluate(root,h,l,i,require_qqq=True)
        assert ok is False,detail
        assert detail["missing"]["ECHO"].startswith("PREDECESSOR_CACHE_MISSING_OR_INVALID:"),detail


def test_legal_scope_outside_history_fails():
    h,l,i = fixtures()
    l=copy.deepcopy(l)
    l["pass_symbols"].append("BAD")
    with tempfile.TemporaryDirectory() as td:
        ok, detail=g.evaluate(Path(td),h,l,i,require_qqq=True)
        assert ok is False and detail["reason"]=="LEGAL_SCOPE_NOT_HISTORY_PASS",(ok,detail)


def test_current_cache_lt260_fails():
    h,l,i = fixtures()
    h["pass_symbols"]=["A"]
    l["pass_symbols"]=["A"]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        write_cache(root,"A",daily_ending(ASOF,259))
        write_cache(root,"QQQ",daily_ending(ASOF,320))
        ok, detail=g.evaluate(root,h,l,{"records":{}},require_qqq=True)
        assert ok is False,detail
        assert detail["missing"]["A"]=="CURRENT_LT260:259",detail


def test_weekend_duplicate_and_invalid_bars_fail():
    h,l,i = fixtures()
    h["pass_symbols"]=["A"]
    l["pass_symbols"]=["A"]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        good=daily_ending(ASOF,300)
        write_cache(root,"QQQ",daily_ending(ASOF,320))
        # Even with >=260 plausible observations, tampering must fail closed.
        for injected in ("2026-10-04","2026-09-07",good[-1],"NOT_A_DATE"):
            write_cache(root,"A",good+[injected])
            ok,detail=g.evaluate(root,h,l,{"records":{}},require_qqq=True)
            assert not ok and detail["missing"]["A"]=="CACHE_MISSING_OR_INVALID",detail


def test_recent_calendar_gap_hidden_by_older_dates_fails():
    # >=260 distinct valid dates and a fresh ASOF do NOT mean the latest
    # 260 official sessions are fully covered.
    h,l,i=fixtures()
    h["pass_symbols"]=["A"];l["pass_symbols"]=["A"]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        dates=daily_ending(ASOF,300)
        omitted=dates[-100]
        write_cache(root,"A",[d for d in dates if d!=omitted])
        write_cache(root,"QQQ",daily_ending(ASOF,320))
        ok,detail=g.evaluate(root,h,l,{"records":{}},require_qqq=True)
        assert not ok and detail["missing"]["A"]=="CURRENT_RECENT_260_OR_52_WEEK_GAP",detail


def test_qqq_recent_gap_hidden_by_old_days_fails():
    h,l,i=fixtures()
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        make_good_cache(root)
        q=daily_ending(ASOF,320)
        write_cache(root,"QQQ",[d for d in q if d!=q[-100]])
        ok,detail=g.evaluate(root,h,l,i,require_qqq=True)
        assert not ok and detail["missing"]["QQQ"]=="CURRENT_RECENT_260_OR_52_WEEK_GAP",detail


def test_predecessor_composite_recent_gap_hidden_by_old_days_fails():
    h,l,i=fixtures()
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        make_good_cache(root)
        predecessor=daily_ending("2026-06-23",240)
        write_cache(root,"SATS",[d for d in predecessor if d!=predecessor[-15]])
        ok,detail=g.evaluate(root,h,l,i,require_qqq=True)
        assert not ok and detail["missing"]["ECHO"]=="COMPOSITE_RECENT_260_OR_52_WEEK_GAP",detail


def test_zero_or_corrupt_ohlcv_fails():
    # Safety regression: official dates alone cannot certify actual OHLCV.
    h,l,_=fixtures()
    h["pass_symbols"]=["A"];l["pass_symbols"]=["A"]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        write_cache(root,"A",daily_ending(ASOF,300))
        write_cache(root,"QQQ",daily_ending(ASOF,320))
        p=g.cache_path(root,"A")
        with gzip.open(p,"rt",encoding="utf-8",newline="") as fh:
            reader=csv.DictReader(fh)
            names=list(reader.fieldnames)
            base=list(reader)
        for field,bad in (("volume","0"),("close","nan"),("high","1"),
                          ("low","1000000"),("open","-5"),("volume","infinity")):
            rows=copy.deepcopy(base)
            rows[-1][field]=bad
            with gzip.open(p,"wt",encoding="utf-8",newline="") as fh:
                writer=csv.DictWriter(fh,fieldnames=names)
                writer.writeheader()
                writer.writerows(rows)
            ok,detail=g.evaluate(root,h,l,{"records":{}},require_qqq=True)
            assert not ok and detail["missing"]["A"]=="CACHE_MISSING_OR_INVALID", (field,bad,detail)


if __name__=="__main__":
    test_weekend_duplicate_and_invalid_bars_fail()
    test_zero_or_corrupt_ohlcv_fails()
    test_complete_exact_asof_cache_passes()
    test_stale_qqq_fails()
    test_missing_continuity_predecessor_fails()
    test_legal_scope_outside_history_fails()
    test_current_cache_lt260_fails()
    test_recent_calendar_gap_hidden_by_older_dates_fails()
    test_qqq_recent_gap_hidden_by_old_days_fails()
    test_predecessor_composite_recent_gap_hidden_by_old_days_fails()
    print("HISTORY_TRANSPORT_CACHE_GUARD_SELFTEST=PASS_RECENT260_52WEEKS_3_NEW_NEGATIVE")
