#!/usr/bin/env python3
"""XRAY v33: FISV/CCC exact260 official-session SIP daily HISTORY witness.

READ ONLY, research-only, GitHub main secrets only; never changes current
candidate/final gate, never persists OHLCV, vendor trade rows, or credentials.
Alpaca historical asof identity mapping can include FISV's former NYSE FI
history. Venue continuity and corporate-action PIT are separate blockers.
"""
from __future__ import annotations
import argparse, collections, datetime as dt, json, math, os, re
import urllib.error, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
UTC=dt.timezone.utc
NY=ZoneInfo("America/New_York")
TARGET=("CCC","FISV")
TRANSFER="2025-11-11"
BASE="https://data.alpaca.markets/v2/stocks/bars"
MAX_PAGES=3
MAX_BYTES=3_000_000
SCHEMA="XRAY_V33_FISV_CCC_260_SIP_HISTORY_SHADOW_V1"

class Unknown(Exception): pass
def require(ok,code):
    if not ok:raise Unknown("XRAY_V33_"+code)

def official260(asof):
    d=dt.date.fromisoformat(asof)
    dates=mcal.get_calendar("NASDAQ").valid_days(
        start_date=d-dt.timedelta(days=410),end_date=d)
    rows=[k.date().isoformat() for k in dates]
    require(len(rows)>=260 and rows[-1]==asof,"OFFICIAL_SESSION_SCOPE")
    return rows[-260:]

def parse_time(raw):
    require(type(raw) is str,"TIME_NOT_STR")
    try:k=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError:raise Unknown("XRAY_V33_TIME_UNREADABLE")
    require(k.tzinfo is not None,"TIME_NO_TZ")
    return k.astimezone(NY).date().isoformat()

def check_bar(row):
    require(type(row) is dict,"ROW_OBJECT")
    require(all(type(row.get(k)) in (int,float) and math.isfinite(row[k]) and row[k]>0
                for k in ("o","h","l","c")),"OHLC_VALUE")
    require(row["l"]<=min(row["o"],row["c"])<=max(row["o"],row["c"])<=row["h"],
            "OHLC_ORDER")
    require(type(row.get("v")) is int and row["v"]>0,"VOLUME_INT")
    return parse_time(row.get("t"))

def evaluate(rows,official_dates,symbol):
    require(symbol in TARGET and type(rows) is list,"SYMBOL_OR_ROWS")
    expected=set(official_dates)
    seen=set(); oldest=0; data_errors=0
    for bar in rows:
        date=check_bar(bar)
        if date in expected:
            require(date not in seen,"DATE_DUPLICATE")
            seen.add(date)
            if symbol=="FISV" and date<TRANSFER:oldest+=1
        elif date>official_dates[-1]:
            raise Unknown("XRAY_V33_FUTURE_BAR")
    missing=expected-seen
    return {"requested_official_sessions":260,
            "observed_official_sessions":len(seen),
            "missing_official_sessions":len(missing),
            "pre_nasdaq_fisv_session_count":oldest if symbol=="FISV" else 0,
            "exact_calendar_260_present":len(missing)==0,
            "corporate_actions_PIT_verified":False,
            "former_NYSE_to_Nasdaq_venue_eligibility_verified":False,
            "full_c417_history_authority":False}

def fetch(*,start,end,asof,key,secret):
    require(bool(key and secret),"RUNNER_SECRET_MISSING")
    params={"symbols":",".join(TARGET),"timeframe":"1Day",
            "start":start,"end":end,"asof":asof,"feed":"sip",
            "adjustment":"raw","sort":"asc","limit":10000}
    data={s:[] for s in TARGET}
    previous=set();token=None;pages=0
    for _ in range(MAX_PAGES):
        q=dict(params)
        if token is not None:q["page_token"]=token
        req=urllib.request.Request(BASE+"?"+urllib.parse.urlencode(q),headers={
          "APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
          "Accept":"application/json","User-Agent":"xray-v33-research-only/1.0"})
        with urllib.request.urlopen(req,timeout=27) as response:
            raw=response.read(MAX_BYTES+1)
        require(len(raw)<=MAX_BYTES,"BODY_TOO_LARGE")
        body=json.loads(raw)
        require(type(body) is dict and type(body.get("bars")) is dict,"BODY_SCHEMA")
        require(set(body["bars"]).issubset(data),"EXTRA_SYMBOL")
        pages+=1;count=0
        for symbol,bars in body["bars"].items():
            require(type(bars) is list,"ROWS_NOT_LIST")
            for row in bars:
                require(type(row) is dict and type(row.get("t")) is str,"BAR_SCHEMA")
                identifier=(symbol,row["t"])
                require(identifier not in previous,"DUPLICATE_PAGE_ROW")
                previous.add(identifier)
                count+=1
            data[symbol].extend(bars)
        nxt=body.get("next_page_token")
        if nxt is None:return data,pages
        require(type(nxt) is str and 0<len(nxt)<2000 and nxt!=token,"CURSOR_INVALID")
        require(count>0,"CURSOR_STALLED")
        token=nxt
    raise Unknown("XRAY_V33_PAGE_LIMIT_EXHAUSTED")

def report(asof,status,stats=None,pages=0):
    stats=stats or {}
    return {"schema":SCHEMA,"asof_et":asof,"status":status,
      "sample_size":2,"official_sessions_required_each":260,
      "source":"ALPACA_HISTORICAL_SIP_RAW_READONLY",
      "source_returned_for_all_two":len(stats)==2,
      "histories":stats,"page_requests":pages,"page_cap":MAX_PAGES,
      "no_raw_vendor_bars_persisted":True,
      "mapping_asof_used":True,
      "cross_venue_legacy_history_review_required":True,
      "corporate_action_PIT_proven":False,
      "runner_source_rights_attested":False,
      "canonical_price_or_history_changed":False,
      "technical_candidate_promoted":False,
      "C417_PASS":False,"G9_PASS":False,"R92_created":False,
      "iphone_receipt":False,"broker":False,"orders":False,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def selftest():
    import copy
    dates=official260("2026-10-22")
    assert len(dates)==260 and dates[-1]=="2026-10-22"
    def fixture(d):
        t=dt.datetime.combine(dt.date.fromisoformat(d),dt.time(0),NY)
        return {"t":t.isoformat(),"o":10,"h":11,"l":9,"c":10.5,"v":10000}
    good=[fixture(d) for d in dates]
    a=evaluate(good,dates,"FISV")
    b=evaluate(good,dates,"CCC")
    assert a["exact_calendar_260_present"] and b["exact_calendar_260_present"]
    assert a["pre_nasdaq_fisv_session_count"]>0 and b["pre_nasdaq_fisv_session_count"]==0
    assert a["full_c417_history_authority"] is False
    missing=evaluate(good[:-1],dates,"CCC")
    assert missing["missing_official_sessions"]==1 and not missing["exact_calendar_260_present"]
    failures=[
      lambda z:z.append(copy.deepcopy(z[0])),
      lambda z:z[0].update(v=0),
      lambda z:z[0].update(v=5.5),
      lambda z:z[0].update(h=4),
      lambda z:z[0].update(t="no-date"),
      lambda z:z[0].update(t="2026-10-23T00:00:00-04:00"),
      lambda z:z[0].update(o=0),
      lambda z:z[0].update(c=float("nan")),
    ]
    n=0
    for change in failures:
        v=copy.deepcopy(good);change(v)
        try:evaluate(v,dates,"CCC")
        except Unknown:n+=1
        else:raise AssertionError("MUTATION_ACCEPTED")
    assert n==8
    assert MAX_PAGES<=3 and SCHEMA.endswith("SHADOW_V1")
    print("XRAY_V33_FISV_CCC_260_OFFLINE=PASS_3_POSITIVE_8_NEGATIVE_NO_ALPHA")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:selftest();return
    if not args.out:ap.error("--out required")
    from source_epoch_freshness_guard import last_complete_session
    now=dt.datetime.now(UTC)
    root=json.loads((ROOT/"orchestrator_state.json").read_text())
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    asof=root.get("asof_et")
    status="BLOCKED"
    try:
        require(all(x.get("asof_et")==asof for x in (root,master,price)),
                "SOURCE_EPOCH_DRIFT")
        require(last_complete_session(now)==asof,"STALE_CURRENT_EPOCH")
        require(all(x.get("execution")=="NONE" and x.get("real_money")=="NO-GO"
                    for x in (root,master,price)),"POLICY")
        technical=root.get("candidate_technical_funnel") or {}
        require(all(technical.get("results",{}).get(s,{}).get("status")==
                    "UNKNOWN_260_OFFICIAL_HISTORY" for s in TARGET),
                "UNKNOWN_SCOPE_CHANGED")
        dates=official260(asof)
        start=dt.datetime.combine(dt.date.fromisoformat(dates[0]),dt.time(0),NY)
        close=dt.datetime.combine(dt.date.fromisoformat(asof),dt.time(16,1),NY)
        require(close.astimezone(UTC)<=now-dt.timedelta(minutes=15),
                "SIP_DELAY_NOT_MATURE")
        key=os.getenv("XRAY_ALPACA_DATA_KEY_ID") or os.getenv("XRAY_ALPACA_API_KEY_ID") or ""
        secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or os.getenv("XRAY_ALPACA_API_SECRET_KEY") or ""
        if not key or not secret:
            result=report(asof,"BLOCKED_RUNNER_CREDENTIALS_NOT_CONFIGURED")
        else:
            d,pages=fetch(start=start.astimezone(UTC).isoformat(),
                          end=close.astimezone(UTC).isoformat(),
                          asof=asof,key=key,secret=secret)
            stats={s:evaluate(d[s],dates,s) for s in TARGET}
            complete=all(x["exact_calendar_260_present"] for x in stats.values())
            result=report(asof,"RESEARCH_260_DATE_COVERAGE_SHADOW_ONLY" if complete
                          else "UNKNOWN_260_SOURCE_DATE_GAPS",stats,pages)
    except Unknown as exc:
        code=str(exc)
        status=code if re.fullmatch(r"XRAY_V33_[A-Z0-9_]{1,80}",code) else "XRAY_V33_UNCLASSIFIED"
        result=report(asof,status)
    except urllib.error.HTTPError as exc:
        label={401:"401_AUTH",403:"403_POLICY_OR_DELAY",429:"429_QUOTA"}.get(exc.code,"HTTP_OTHER")
        result=report(asof,"BLOCKED_"+label)
    except (urllib.error.URLError,OSError,TimeoutError,ValueError,KeyError,TypeError):
        result=report(asof,"BLOCKED_NETWORK_OR_RESPONSE_UNKNOWN")
    assert result["C417_PASS"] is False and result["R92_created"] is False
    assert result["canonical_price_or_history_changed"] is False
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_V33_FISV_CCC_260_COUNTS_ONLY="+json.dumps(result,sort_keys=True))

if __name__=="__main__":main()
