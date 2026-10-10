#!/usr/bin/env python3
"""Official 260-session IPO upper-bound regression; no market data."""
import json
import ast
from pathlib import Path
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
def run():
    evidence=json.loads((ROOT/"history_official_identity_evidence.json").read_text())
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    assert evidence["schema"]=="XRAY_HISTORY_OFFICIAL_IDENTITY_EVIDENCE_V1"
    assert evidence["execution"]=="NONE" and evidence["real_money"]=="NO-GO"
    assert evidence["alpha_authority"] is False
    assert price["asof_et"]=="2026-10-09"
    assert {"FRVO","BSP","EQPT"}<=set(price["pass_symbols"])
    for symbol,first in (("FRVO","2026-05-13"),("BSP","2026-07-01"),("EQPT","2026-01-23")):
        rec=evidence["records"][symbol]
        assert rec["mode"]=="OFFICIAL_LISTING_UPPER_BOUND_FAIL_ONLY"
        assert rec["earliest_public_trading_date"]==first
        assert len(rec["sources"])>=2
        if symbol=="EQPT":
            assert "https://www.nasdaq.com/press-release/equipmentshare-debuts-nasdaq-eqpt-advancing-digital-transformation-construction-2026" in rec["sources"]
        days=mcal.get_calendar("NYSE").schedule(start_date=first,end_date=price["asof_et"])
        assert 0<len(days)<260,(symbol,len(days))
    # Official Nasdaq ECA2025-559: same common shares traded as SOLSV
    # when-issued from 2025-10-20, then SOLS regular-way on 2025-10-30.
    # Reject a registry that incorrectly treats 2025-10-30 as the
    # earliest public trading date. This remains FAIL_ONLY (<260).
    sols=evidence["records"]["SOLS"]
    assert sols["mode"]=="OFFICIAL_LISTING_UPPER_BOUND_FAIL_ONLY"
    assert sols["earliest_public_trading_date"]=="2025-10-20",sols
    assert sols["regular_way_trading_date"]=="2025-10-30",sols
    assert sols["predecessor_when_issued_symbol"]=="SOLSV",sols
    assert "https://classic.nasdaqtrader.com/TraderNews.aspx?id=ECA2025-559" in sols["sources"]
    sessions=mcal.get_calendar("NASDAQ").valid_days(
        start_date=sols["earliest_public_trading_date"],
        end_date=price["asof_et"])
    assert 0<len(sessions)<260,len(sessions)
    source=(ROOT/"history_phase.py").read_text()
    tree=ast.parse(source)
    names={x.name for x in tree.body if isinstance(x,ast.FunctionDef)}
    assert {"official_listing_upper_bound_fail","eval_one"}<=names
    # RED: Nasdaq HISTORY upper bounds must use the same official Nasdaq
    # calendar as 260/52 guards, not a different exchange calendar.
    for function in ("official_listing_upper_bound_fail",
                     "aligned_first_bar_upper_bound_fail"):
        fnode=next(x for x in tree.body
                   if isinstance(x,ast.FunctionDef) and x.name==function)
        part=ast.get_source_segment(source,fnode)
        assert 'mcal.get_calendar("NASDAQ")' in part, (
            "WRONG_EXCHANGE_CALENDAR_FOR_NASDAQ_HISTORY",function)
    fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="eval_one")
    assert isinstance(fn.body[0],ast.Assign)
    assert isinstance(fn.body[0].value,ast.Call)
    assert isinstance(fn.body[0].value.func,ast.Name)
    assert fn.body[0].value.func.id=="official_listing_upper_bound_fail"
    # Execute the production functions in isolation, not just a static record check.
    # This imports no vendor SDK and reads no market bars or credentials.
    from datetime import datetime, timedelta
    sandbox={"OFFICIAL_RECORDS":evidence["records"],"mcal":mcal,
             "HARD_DAILY":260,"HARD_WEEKLY":52,
             "datetime":datetime,"timedelta":timedelta}
    funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and
           n.name in {"week_count","official_listing_upper_bound_fail"}]
    assert len(funcs)==2
    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(ROOT/"history_phase.py"),"exec"),sandbox)
    for sym in ("BSP","EQPT","FRVO"):
        witness=sandbox["official_listing_upper_bound_fail"](sym,"2026-10-09")
        assert witness is not None,("PRODUCTION_HISTORY_FAIL_BOUND_MISSING",sym)
        assert witness["proof"]=="OFFICIAL_LISTING_DATE_HISTORY_UPPER_BOUND"
        assert witness["max_possible_daily_bars"]<260
        assert witness["max_possible_completed_weeks"]<52
        assert witness["thresholds"]=={"daily":260,"weekly_completed":52}
    assert sandbox["official_listing_upper_bound_fail"]("AAPL","2026-10-09") is None
    print("XRAY_BSP_EQPT_FRVO_OFFICIAL_260_FAIL_ONLY=PASS_PRODUCTION_FUNCTION_ZERO_VENDOR_NO_HISTORY_PASS")
if __name__=="__main__":
    run()
