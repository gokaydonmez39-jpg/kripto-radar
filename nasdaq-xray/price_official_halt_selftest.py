#!/usr/bin/env python3
from __future__ import annotations

from price_dv30_recover_from_fullstate import official_full_session_halt_terminal


def guard(items, status="PASS"):
    return {
        "schema":"XRAY_OFFICIAL_SOURCE_GUARD_V1",
        "sources":{
            "trade_halts":{
                "status":status,
                "url":"https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts",
                "items":items,
            }
        }
    }


def row(sym, halt_date, halt_time, resume_date="", resume_time="", market="NASDAQ"):
    return {
        "IssueSymbol":sym,
        "IssueName":sym,
        "Market":market,
        "HaltDate":halt_date,
        "HaltTime":halt_time,
        "ReasonCode":"T12",
        "ResumptionDate":resume_date,
        "ResumptionTradeTime":resume_time,
    }


def main():
    # WBD-like: halted prior evening, no trading during ASOF, resumes next day.
    wbd=official_full_session_halt_terminal(
        guard([row("WBD","10/05/2026","19:50:00.000","10/07/2026","00:00:01")]),
        "WBD","2026-10-06"
    )
    assert wbd and wbd["proof"]=="NASDAQ_TRADER_FULL_SESSION_HALT",wbd
    assert wbd["decision_direction"]=="FAIL_ONLY_NEVER_PASS",wbd

    # SVA-like: open-ended long-running halt also covers the full ASOF session.
    sva=official_full_session_halt_terminal(
        guard([row("SVA","02/22/2019","16:02:01")]),
        "SVA","2026-10-06"
    )
    assert sva and sva["reason"]=="OFFICIAL_NASDAQ_FULL_SESSION_HALT_NO_ASOF_BAR",sva

    # Intraday halt after the open must not erase a valid earlier ASOF session.
    intraday=official_full_session_halt_terminal(
        guard([row("TEST","10/06/2026","12:00:00.000")]),
        "TEST","2026-10-06"
    )
    assert intraday is None,intraday

    # Halt that resumes during RTH is not a full-session halt.
    resumed=official_full_session_halt_terminal(
        guard([row("TEST","10/05/2026","19:50:00.000","10/06/2026","10:15:00")]),
        "TEST","2026-10-06"
    )
    assert resumed is None,resumed

    # Unknown official feed cannot create a terminal decision.
    unknown=official_full_session_halt_terminal(
        guard([row("TEST","10/05/2026","19:50:00.000")],status="UNKNOWN"),
        "TEST","2026-10-06"
    )
    assert unknown is None,unknown

    # Non-Nasdaq rows are outside this authority path.
    other=official_full_session_halt_terminal(
        guard([row("TEST","10/05/2026","19:50:00.000",market="NYSE")]),
        "TEST","2026-10-06"
    )
    assert other is None,other

    print("XRAY_PRICE_OFFICIAL_HALT_SELFTEST=PASS")


if __name__=="__main__":
    main()
