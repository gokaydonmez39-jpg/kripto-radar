#!/usr/bin/env python3
"""Read-only, exact-ASOF 514 PRICE + QQQ / 260 NASDAQ-session Alpaca SIP audit.

Real provider bars exist in ephemeral memory ONLY. Outputs are counts, error
classes, and the symbol IDs requiring remediation. Does NOT prove license,
adjusted split/issuer continuity, C4.17 PRIMARY HISTORY, MC, G9, R92, GO,
account, notification delivery or entitlement. No trading or writes to main.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import json
import math
import os
from pathlib import Path

from alpaca_free_sip_shadow_guard import (
    request_batch, timestamp_date, sufficient_delay, blob_sha,
)
from current_history_source_request import expected_dates, sha256_lines

ROOT=Path(__file__).resolve().parent
MASTER=ROOT/"canonical_current_master_manifest.json"
PRICE=ROOT/"canonical_current_price_dv30.json"
SCHEMA="XRAY_ALPACA_CURRENT_515_EXACT260_SIP_SHADOW_V1"
BATCH_SIZE=32
UTC=dt.timezone.utc


def scope(price,master):
    asof=price.get("asof_et")
    if (asof!=master.get("asof_et") or price.get("unknown_never_pass") is not True
            or master.get("unknown_never_pass") is not True):
        raise ValueError("CURRENT_MASTER_PRICE_ASOF_DRIFT")
    for doc in (price,master):
        if doc.get("execution")!="NONE" or doc.get("real_money")!="NO-GO":
            raise ValueError("SOURCE_SAFETY_CHANGED")
    symbols=price.get("pass_symbols")
    if (not isinstance(symbols,list) or not symbols
            or symbols!=sorted(set(symbols)) or len(symbols)!=price.get("pass_count")
            or sha256_lines(symbols)!=price.get("pass_hash")
            or not set(symbols).issubset(set(master.get("pass_symbols") or []))):
        raise ValueError("PRICE_SCOPE_SYMBOL_HASH_OR_MASTER_INVALID")
    for label in ("unknown","blocked"):
        data=price.get(label+"_symbols",[])
        if (not isinstance(data,list) or data!=sorted(set(data))
                or price.get(label+"_count",0)!=len(data) or set(data)&set(symbols)):
            raise ValueError("PRICE_"+label.upper()+"_PARTITION_INVALID")
    daily,weeks=expected_dates(asof)
    if len(daily)!=260 or len(weeks)!=52 or daily[-1]!=asof:
        raise ValueError("OFFICIAL_260_52_CALENDAR_INVALID")
    targets=sorted(set(symbols)|{"QQQ"})
    return asof,targets,daily,weeks


def classify(rows,required_daily,required_weeks,asof):
    """Symbol-local result; incomplete/malformed bar NEVER gains HISTORY PASS."""
    if not isinstance(rows,list):
        return "BAD_PROVIDER_ROWS",0
    observed=set()
    official=set(required_daily)
    for row in rows:
        if not isinstance(row,dict):
            return "MALFORMED_BAR",0
        try:
            day=timestamp_date(row["t"]).isoformat()
            nums=[row[k] for k in ("o","h","l","c","v")]
            if (any(isinstance(v,bool) or not isinstance(v,(int,float))
                    or not math.isfinite(v) for v in nums)):
                return "NONFINITE_OHLCV",0
            o,h,l,c,v=nums
            if not (h>=max(o,l,c)>0 and 0<l<=min(o,c)
                    and v>0):
                return "INVALID_OHLCV_OR_ZERO_VOLUME",0
            if day in observed:
                return "DUPLICATE_SESSION",0
            if day>asof:
                return "FUTURE_LOOKAHEAD",0
            if day not in official:
                return "NON_OFFICIAL_SESSION",0
            observed.add(day)
        except (KeyError,TypeError,ValueError,OverflowError):
            return "TIMESTAMP_OR_OHLCV_PARSE_ERROR",0
    count=len(observed)
    if not observed:
        return "NO_BAR",0
    if not official.issubset(observed):
        return "MISSING_EXACT_COMPLETED_SESSIONS",count
    if not set(required_weeks).issubset(observed):
        return "MISSING_52_COMPLETED_WEEK_CLOSES",count
    return "SHADOW_260_DAILY_52_WEEK_OBSERVED",count


def audit(asof,targets,daily,weeks,batch_fetch,*,now):
    if now.tzinfo is None or not sufficient_delay(asof,now):
        raise ValueError("SIP_20MIN_OFFICIAL_CLOSE_HOLDBACK_NOT_MET")
    if (len(targets)!=len(set(targets)) or targets!=sorted(targets)
            or "QQQ" not in targets or len(daily)!=260 or len(weeks)!=52):
        raise ValueError("UNTRUSTED_TARGET_SCOPE")
    counters=collections.Counter()
    missing_by_reason={}
    measured=0
    transport_error=None
    start=daily[0]+"T00:00:00Z"
    end=(dt.date.fromisoformat(asof)+dt.timedelta(days=1)).isoformat()+"T00:00:00Z"
    for i in range(0,len(targets),BATCH_SIZE):
        batch=targets[i:i+BATCH_SIZE]
        try:
            raw=batch_fetch(batch,start,end)
            if not isinstance(raw,dict) or any(s not in batch for s in raw):
                raise ValueError("VENDOR_FOREIGN_SYMBOL_OR_BAD_SCOPE")
        except (RuntimeError,ValueError,TimeoutError,OSError) as exc:
            # Never print provider response or any secret; explicit partial scope.
            code=str(exc)
            transport_error=(code if code.startswith(("ALPACA_HTTP_","ALPACA_PAGE_"))
                             else "PROVIDER_TRANSPORT_OR_SCHEMA_UNVERIFIED")
            break
        for symbol in batch:
            category,count=classify(raw.get(symbol,[]),daily,weeks,asof)
            counters[category]+=1
            measured+=1
            if category!="SHADOW_260_DAILY_52_WEEK_OBSERVED":
                missing_by_reason[symbol]=category
        del raw
    counters["UNCHECKED_DUE_TO_TRANSPORT"]+=len(targets)-measured
    return {
        "schema":SCHEMA,"asof_et":asof,"policy":"C4.17","control":"C4.27",
        "status":("SHADOW_FULL_515_SCOPE_MEASURED_NO_AUTHORITY"
                  if measured==len(targets) and transport_error is None
                  else "SHADOW_INCOMPLETE_TRANSPORT_OR_SCOPE"),
        "expected_scope_count":len(targets),"measured_scope_count":measured,
        "contains_qqq_benchmark":True,
        "expected_daily_sessions":260,"required_completed_week_closes":52,
        "batch_size":BATCH_SIZE,"batches_attempted":(measured+BATCH_SIZE-1)//BATCH_SIZE+
                 (1 if transport_error else 0),
        "counts":dict(sorted(counters.items())),
        "unverified_symbols":missing_by_reason,
        "transport_error_class":transport_error,
        "api_feed":"sip","api_timeframe":"1Day","api_adjustment":"raw",
        "source_market_data_rights_independently_attested":False,
        "corporate_action_adjustment_and_share_class_attested":False,
        "current_c417_history_primary_authority":False,
        "canonical_history_pass_created":0,"primary_mc_pass_created":0,
        "strict_g9_pass":False,"account_pass":False,"r92_created":False,
        "vendor_ohlcv_in_artifact":False,"vendor_raw_bars_persisted":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
    }


def selftest():
    from zoneinfo import ZoneInfo
    from alpaca_free_sip_shadow_guard import EST
    asof="2026-10-09"
    daily,weeks=expected_dates(asof)
    assert len(daily)==260 and len(weeks)==52
    def bar(day):
        stamp=dt.datetime.combine(dt.date.fromisoformat(day),dt.time(0),EST)
        return {"t":stamp.astimezone(UTC).isoformat(),"o":10.,
                "h":11.,"l":9.,"c":10.5,"v":1000}
    good=[bar(d) for d in daily]
    assert classify(good,daily,weeks,asof)==("SHADOW_260_DAILY_52_WEEK_OBSERVED",260)
    assert classify(good[:-1],daily,weeks,asof)[0]=="MISSING_EXACT_COMPLETED_SESSIONS"
    assert classify([],daily,weeks,asof)==("NO_BAR",0)
    for corrupted in (
        good+[good[0]],
        [dict(good[0],v=0)]+good[1:],
        [dict(good[0],t="2026-09-29T16:00:00-04:00")]+good[1:],
        [dict(good[0],c=40.0)]+good[1:],
        [dict(good[0],v=float("nan"))]+good[1:],
        good+[bar("2026-10-10")],
    ):
        assert classify(corrupted,daily,weeks,asof)[0]!="SHADOW_260_DAILY_52_WEEK_OBSERVED"
    fake_master={"asof_et":asof,"unknown_never_pass":True,
                 "pass_symbols":["AAA","BBB"],"execution":"NONE","real_money":"NO-GO"}
    fake_price={"asof_et":asof,"unknown_never_pass":True,
                "pass_symbols":["AAA","BBB"],"pass_count":2,
                "pass_hash":sha256_lines(["AAA","BBB"]),
                "unknown_count":0,"blocked_count":0,
                "execution":"NONE","real_money":"NO-GO"}
    a,t,d,w=scope(fake_price,fake_master)
    assert t==["AAA","BBB","QQQ"] and d==daily and w==weeks
    def mock_fetch(batch,start,end):
        assert set(batch)<=set(t) and "2025-09-29" in start
        assert end=="2026-10-10T00:00:00Z"
        return {symbol:good for symbol in batch if symbol!="BBB"}
    now=dt.datetime(2026,10,10,20,tzinfo=UTC)
    out=audit(a,t,d,w,mock_fetch,now=now)
    assert out["measured_scope_count"]==3
    assert out["counts"]["SHADOW_260_DAILY_52_WEEK_OBSERVED"]==2
    assert out["unverified_symbols"]=={"BBB":"NO_BAR"}
    assert out["current_c417_history_primary_authority"] is False
    assert out["canonical_history_pass_created"]==0
    assert out["vendor_raw_bars_persisted"] is False
    def fail(*args):
        raise RuntimeError("ALPACA_HTTP_429")
    blocked=audit(a,t,d,w,fail,now=now)
    assert blocked["counts"]["UNCHECKED_DUE_TO_TRANSPORT"]==3
    assert blocked["transport_error_class"]=="ALPACA_HTTP_429"
    assert blocked["status"]=="SHADOW_INCOMPLETE_TRANSPORT_OR_SCOPE"
    print("XRAY_ALPACA_515_EXACT260_SELFTEST=PASS_POSITIVE_6_NEGATIVE_3_SCOPE_AND_TRANSPORT_NO_PRIMARY")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:
        selftest();return
    if not args.out:
        p.error("--out required")
    price=json.loads(PRICE.read_text())
    master=json.loads(MASTER.read_text())
    asof,targets,daily,weeks=scope(price,master)
    key=os.getenv("XRAY_ALPACA_DATA_KEY_ID","").strip()
    secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY","").strip()
    if not key or not secret:
        raise SystemExit("XRAY_ALPACA_515=BLOCKED_PRIVATE_CREDENTIALS_UNAVAILABLE")
    def real(batch,start,end):
        return request_batch(batch,start,end,key,secret)
    result=audit(asof,targets,daily,weeks,real,now=dt.datetime.now(UTC))
    result["source_price_blob_sha"]=blob_sha(PRICE)
    result["source_master_blob_sha"]=blob_sha(MASTER)
    result["source_price_pass_hash"]=price["pass_hash"]
    result["price_pass_count"]=price["pass_count"]
    # Only count-only/symbol IDs; no raw bars, no prices, no per-bar timestamps.
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("XRAY_ALPACA_515_SHADOW_STATUS="+result["status"])
    print("XRAY_ALPACA_515_SHADOW_COUNTS="+json.dumps(result["counts"],sort_keys=True))
    print("XRAY_ALPACA_515_SHADOW_MEASURED="+str(result["measured_scope_count"]))


if __name__=="__main__":
    main()
