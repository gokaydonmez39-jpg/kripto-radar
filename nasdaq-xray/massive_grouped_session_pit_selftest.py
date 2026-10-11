#!/usr/bin/env python3
"""Falsification tests for exact official grouped daily-bar close.
No network and no actual provider OHLCV; NEVER confers HISTORY/MC/R92 authority.
"""
from __future__ import annotations
import copy
from datetime import datetime,timezone
from massive_grouped_history_resume import read_day,official_grouped_close_ms

def require(ok,reason):
    if not ok:raise AssertionError("GROUPED_EOD_PIT_TEST:"+reason)

def payload(day,stamp):
    return {"status":"OK","adjusted":False,"resultsCount":2,"results":[
        {"T":"QQQ","o":10,"h":11,"l":9,"c":10,"v":100,"t":stamp},
        {"T":"TEST","o":2,"h":3,"l":1,"c":2,"v":200,"t":stamp}
    ]}

def reject(label,day,ts):
    try:read_day(payload(day,ts),day,["QQQ","TEST"])
    except ValueError:return
    raise RuntimeError("GROUPED_EOD_PIT_FALSE_ACCEPT:"+label)

def main():
    # 2026-10-09 normal 16:00 New York RTH close, EDT.
    octclose=int(datetime(2026,10,9,20,tzinfo=timezone.utc).timestamp()*1000)
    require(official_grouped_close_ms("2026-10-09")==octclose,"OCT_DST")
    require(set(read_day(payload("2026-10-09",octclose),"2026-10-09",["TEST","QQQ"]))=={"TEST","QQQ"},"OCT_OK")
    # Friday after Thanksgiving is 13:00 New York, 18:00 UTC.
    halfclose=int(datetime(2026,11,27,18,tzinfo=timezone.utc).timestamp()*1000)
    require(official_grouped_close_ms("2026-11-27")==halfclose,"OFFICIAL_HALF_DAY")
    require(len(read_day(payload("2026-11-27",halfclose),"2026-11-27",["QQQ","TEST"]))==2,"HALF_DAY_OK")
    # After Nov 1 DST transition, close moves to 21:00 UTC.
    winclose=int(datetime(2026,11,2,21,tzinfo=timezone.utc).timestamp()*1000)
    require(official_grouped_close_ms("2026-11-02")==winclose,"WINTER_DST")
    require(len(read_day(payload("2026-11-02",winclose),"2026-11-02",["QQQ","TEST"]))==2,"WINTER_OK")
    reject("INTRADAY_SAME_UTC_DATE","2026-10-09",octclose-3600000)
    reject("LATE_SAME_UTC_DATE","2026-10-09",octclose+3600000)
    reject("MIDNIGHT_UTC_NOT_MARKET_CLOSE","2026-10-09",octclose-20*3600000)
    reject("HALF_DAY_MISLABELED_FULL_CLOSE","2026-11-27",halfclose+3*3600000)
    reject("WINTER_DST_ONE_HOUR_EARLY","2026-11-02",winclose-3600000)
    reject("WINTER_DST_ONE_HOUR_LATE","2026-11-02",winclose+3600000)
    reject("FRIDAY_ROW_REUSED_MON","2026-11-02",halfclose)
    reject("SATURDAY_NO_SESSION","2026-10-10",octclose)
    reject("THANKSGIVING_CLOSED","2026-11-26",halfclose)
    reject("UTC_NEXT_CALENDAR_DAY","2026-10-09",octclose+86400000)
    reject("BOOLEAN_TIMESTAMP","2026-10-09",True)
    reject("FLOAT_TIMESTAMP","2026-10-09",float(octclose))
    print("XRAY_GROUPED_OFFICIAL_CLOSE_PIT_SELFTEST=PASS_3_POSITIVE_12_NEGATIVE_PYTHON_O_SAFE_NO_PROVIDER_NO_HISTORY_AUTHORITY")

if __name__=="__main__":main()
