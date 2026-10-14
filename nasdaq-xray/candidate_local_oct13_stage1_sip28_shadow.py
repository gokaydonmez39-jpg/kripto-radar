#!/usr/bin/env python3
"""28 ticker actual 260-session Alpaca SIP Stage1 observation, no false R92.

Select first 28 sorted symbols of exact immutable 277 source-intersection.
Reuse existing compiled Stage1 weekly/pool mechanics on 260 official daily bars.
No historical raw bars persisted. Unverified splits and stale data => UNKNOWN.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,hashlib,json,os,time
import urllib.error,urllib.parse,urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import pandas_market_calendars as mcal
import stage1_shadow as stage
from alpha_semantics import mechanical_scale_breaks,mechanical_split_suspects,drawdown_metrics,find_recent_b_trigger,NEW_TRIGGER_DISCOVERY_MAX_AGE

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
SOURCE_SHA="c05669e7fbd0a91c3f6fb9f652c330157066496747132dcfc291d121d99fb26c"
N=28
NY=ZoneInfo("America/New_York")
def need(ok,code):
    if not ok:raise ValueError("XRAY_LOCAL_STAGE1_"+code)

def source(path):
    raw=path.read_bytes()
    need(hashlib.sha256(raw).hexdigest()==SOURCE_SHA,"EXACT_277_SOURCE_SHA")
    d=json.loads(raw)
    need(d["schema"]=="XRAY_OCT13_LOCAL_404_SIP_SEC_HISTORY_REAL_SOURCE_ROLLUP_V1"
         and d["asof_et"]==ASOF and d["source_overlap_count"]==277
         and d["exact_page_and_current_blob_coverage_verified"] is True
         and d["canonical_pass_created"] is False,"SOURCE_277_AUTHORITY")
    names=d["source_overlap_symbols"]
    need(len(names)==len(set(names))==277 and names==sorted(names),"SOURCE_SYMBOL_SET")
    return names[:N]

def exact260():
    d=[x.date().isoformat() for x in mcal.get_calendar("NASDAQ").valid_days(
      start_date="2025-07-01",end_date=ASOF)]
    last=d[-260:]
    need(len(last)==260 and len(set(last))==260 and last[-1]==ASOF,"OFFICIAL260")
    return last

def one(sym,keys,days):
    first=dt.datetime.combine(dt.date.fromisoformat(days[0]),dt.time(0),tzinfo=NY)
    end=dt.datetime.combine(dt.date.fromisoformat(ASOF)+dt.timedelta(days=1),dt.time(0),tzinfo=NY)
    p={"symbols":sym,"timeframe":"1Day","feed":"sip","adjustment":"raw",
       "sort":"asc","limit":"1000","start":first.isoformat(),"end":end.isoformat()}
    req=urllib.request.Request("https://data.alpaca.markets/v2/stocks/bars?"+urllib.parse.urlencode(p),
      headers={"APCA-API-KEY-ID":keys[0],"APCA-API-SECRET-KEY":keys[1],
               "Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=24) as res:
        raw=res.read(350001)
    need(len(raw)<=350000,"BARS_BODY_MAX")
    obj=json.loads(raw)
    need(type(obj) is dict and type(obj.get("bars")) is dict and
         set(obj["bars"]).issubset({sym}) and not obj.get("next_page_token"),
         "BARS_SINGLE_SYMBOL_UNPAGINATED")
    bars=obj["bars"].get(sym,[])
    need(type(bars) is list,"BARS_LIST")
    rows={}
    for b in bars:
        need(type(b) is dict and type(b.get("t")) is str,"BAR_TIMESTAMPS")
        moment=dt.datetime.fromisoformat(b["t"].replace("Z","+00:00"))
        need(moment.tzinfo is not None,"TZ_AWARE")
        date=moment.astimezone(NY).date().isoformat()
        if date not in days:continue
        need(date not in rows,"DUPLICATE_OFFICIAL_DAY")
        c={}
        for key,col in (("o","open"),("h","high"),("l","low"),("c","close"),("v","volume")):
            value=b.get(key)
            need(type(value) in (int,float) and float(value)>0,"POSITIVE_OHLCV")
            c[col]=float(value)
        need(c["low"]<=min(c["open"],c["close"]) and
             c["high"]>=max(c["open"],c["close"]),"OHLC_ORDER")
        need(type(b.get("v")) in (int,float) and b["v"]==int(b["v"]),"INTEGER_VOLUME")
        c["date"]=pd.Timestamp(date)
        rows[date]=c
    return rows

def assess(rows,days,weekly):
    if len(rows)!=260 or set(rows)!=set(days):
        return {"status":"UNKNOWN_INCOMPLETE_260_SIP",
                "valid_days":len(rows),"weekly_pass":False}
    df=pd.DataFrame(rows[d] for d in days).reset_index(drop=True)
    if mechanical_scale_breaks(df,260) or mechanical_split_suspects(df):
        return {"status":"UNKNOWN_CORPORATE_ACTION_PIT_NOT_RECONCILED",
                "valid_days":260,"weekly_pass":False}
    w=stage.weekly_gate(df,ASOF,weekly)
    if not w.get("pass"):
        return {"status":"STAGE1_RESEARCH_WEEKLY_FAIL",
                "valid_days":260,"completed_weeks":w.get("weeks"),
                "weekly_pass":False}
    close=df["close"]
    ma=close.rolling(50).mean()
    top=df["high"].rolling(20).max()
    trend=bool(pd.notna(ma.iloc[-1]) and pd.notna(ma.iloc[-21])
       and close.iloc[-1]>ma.iloc[-1]>ma.iloc[-21]
       and .88*top.iloc[-1]<=close.iloc[-1]<=top.iloc[-1])
    base=stage.base_pool(df)
    recent=find_recent_b_trigger(df,NEW_TRIGGER_DISCOVERY_MAX_AGE)
    dd=drawdown_metrics(df)
    down=bool(dd.get("current_drawdown_252") is not None and
        (dd["current_drawdown_252"]<=-.15 or dd["max_drawdown_close_120"]<=-.20))
    return {"status":"STAGE1_RESEARCH_POOL_ONLY" if (trend or base or recent or down)
            else "STAGE1_RESEARCH_WEEKLY_PASS_NO_POOL",
            "valid_days":260,"completed_weeks":w.get("weeks"),"weekly_pass":True,
            "a_trend_pool":trend,"b_tight_base_windows":len(base),
            "b_recent_trigger_detected":bool(recent),
            "d_drawdown_pool":down,
            "setup_r1_rr_final_verified":False}

def selftest():
    dates=exact260()
    need(len(dates)==260 and dates[-1]==ASOF,"TEST_OFFICIAL_DATE")
    need(assess({},dates,{})["status"]=="UNKNOWN_INCOMPLETE_260_SIP",
         "TEST_INCOMPLETE_NEVER_PASS")
    need(source is not None and one is not None,"TEST_PIPELINE")
    print("XRAY_LOCAL_STAGE1_28_SELFTEST=PASS_NO_SYNTHETIC_260_OR_PRIMARY")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--source",type=Path);p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:selftest();return
    need(args.source and args.out and
       not args.out.resolve().is_relative_to(ROOT.parent.resolve()),"EPHEMERAL_OUTPUT")
    symbols=source(args.source)
    dates=exact260()
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    need(bool(key and secret),"RUNNER_HISTORICAL_SIP_CREDENTIALS")
    weekly=stage.build_week_last(ASOF)
    report={"schema":"XRAY_OCT13_28_REAL_SIP_260_STAGE1_RESEARCH_SHADOW_V1",
      "asof_et":ASOF,"source_277_json_sha256":SOURCE_SHA,
      "source_selection":"FIRST_28_SORTED_OF_277_SHA_PINNED",
      "target_symbols":symbols,"status_by_symbol":{},
      "actual_provider_calls":0,"result_counts":{},
      "source_is_historical_sip":True,
      "raw_ohlcv_persisted":False,
      "corporate_actions_asof_proven":False,
      "regime_breadth_verified":False,
      "setup_families_r1_rr_verified":False,
      "legal_event_halt_verified":False,
      "sec_class_aware_mc_primary_verified":False,
      "canonical_primary_created":False,
      "r92_registered":0,"iphone_receipt_verified":False,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    def save():
        report["result_counts"]=dict(sorted(collections.Counter(
             x["status"] for x in report["status_by_symbol"].values()).items()))
        args.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    save()
    for s in symbols:
        report["actual_provider_calls"]+=1
        try:
            b=one(s,(key,secret),dates)
            report["status_by_symbol"][s]=assess(b,dates,weekly)
        except urllib.error.HTTPError as err:
            report["status_by_symbol"][s]={"status":"UNKNOWN_HTTP_"+str(err.code)}
            if err.code==429:
                report["provider_stop"]="RATE_LIMIT_STOP"
                save();break
        except (urllib.error.URLError,ValueError,TimeoutError,RuntimeError,KeyError,TypeError):
            report["status_by_symbol"][s]={"status":"UNKNOWN_PROVIDER_OR_BAR_INTEGRITY"}
        save()
        time.sleep(.6)
    for s in symbols:
        report["status_by_symbol"].setdefault(s,{"status":"UNKNOWN_NOT_ATTEMPTED"})
    save()
    need(len(report["status_by_symbol"])==N and
         sum(report["result_counts"].values())==N,"EXACT28_COMPLETE_OR_EXPLICIT_UNKNOWN")
    print("XRAY_LOCAL_STAGE1_28_ACTUAL_SIP_HTTP="+str(report["actual_provider_calls"]))
    print("XRAY_LOCAL_STAGE1_28_COUNTS="+json.dumps(report["result_counts"],sort_keys=True))
    print("XRAY_LOCAL_STAGE1_28_SHADOW_NOT_R92=PASS")
if __name__=="__main__":main()
