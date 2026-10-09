#!/usr/bin/env python3
"""Fail closed on UTC cron crossing into Saturday/Sunday America/New_York.

GitHub cron is UTC. Monday 00:35 UTC is Sunday evening EDT/EST.
Conservatively allow 23 DST-safe hourly slots per US weekday for the
supplementary pre-MC, post-MC, final workflows; the separate root is
hourly, guarded by real NY weekday, and is the preferred full-hour path.
No synthetic market data or alpha authority.
"""
from __future__ import annotations
import datetime as dt
import re
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
NY = ZoneInfo("America/New_York")
FILES = {
    "xray-canonical-current-pre-mc.yml":35,
    "xray-canonical-current-post-mc.yml":50,
    "xray-canonical-current-final.yml":53,
}

def crons(text):
    return re.findall(r'^\s*- cron:\s*"([^"]+)"\s*$', text, re.MULTILINE)

def fires(schedule, t):
    minute, hours, day, month, weekday = schedule.split()
    assert day == month == "*", "UNEXPECTED_CRON_SCOPE"
    wanted=int(minute)
    dow=(t.weekday()+1)%7 # cron Sunday=0, Python Monday=0
    if "-" in weekday:
        a,b=map(int,weekday.split("-"))
    else:
        a=b=int(weekday)
    if "-" in hours:
        start,end=map(int,hours.split("-"))
    else:
        start=end=int(hours)
    return t.minute==wanted and start<=t.hour<=end and a<=dow<=b

def selftest():
    for name,minute in FILES.items():
        source=(ROOT/".github"/"workflows"/name).read_text(encoding="utf-8")
        entries=crons(source)
        expected=[f"{minute} 5-23 * * 1-5",f"{minute} 0-3 * * 2-6"]
        assert entries==expected, "UTC_WEEKEND_CROSSOVER_CRON_NOT_REPAIRED:"+name+":"+repr(entries)
        for year in (2026,2027):
            clock=dt.datetime(year,1,1,tzinfo=dt.timezone.utc)
            limit=dt.datetime(year+1,1,1,tzinfo=dt.timezone.utc)
            count=0
            while clock<limit:
                at=clock.replace(minute=minute)
                if any(fires(expr,at) for expr in entries):
                    assert at.astimezone(NY).weekday()<5, "GITHUB_CRON_RAN_ON_NY_WEEKEND:"+name+":"+str(at)
                    count+=1
                clock+=dt.timedelta(hours=1)
            assert count>5000, "FALLBACK_CRON_MISSING_MOST_WEEKDAYS:"+name
        # Explicit regression: Oct 12 UTC 00 is still Sunday evening NY.
        sunday=dt.datetime(2026,10,12,0,minute,tzinfo=dt.timezone.utc)
        assert sunday.astimezone(NY).weekday()==6
        assert not any(fires(expr,sunday) for expr in entries)
        friday=dt.datetime(2026,10,10,3,minute,tzinfo=dt.timezone.utc)
        assert friday.astimezone(NY).weekday()==4
        assert any(fires(expr,friday) for expr in entries)
    print("XRAY_FALLBACK_CRON_NY_WEEKEND_SELFTEST=PASS_3_WORKFLOWS_2026_2027_DST_UTC_BOUNDARY_NO_ALPHA")

if __name__=="__main__":
    selftest()
