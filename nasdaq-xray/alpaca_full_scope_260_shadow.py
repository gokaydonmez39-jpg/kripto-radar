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
    scheduled_unknown_cohort, bounded_sip_end, ranked_root_pass_unknown,
)
from current_history_source_request import expected_dates, sha256_lines
from alpaca_sip_paginated_transport_shadow import MAX_PAGES
from alpaca_sip_request_pacer import PACER, SipRequestPacer

ROOT=Path(__file__).resolve().parent
MASTER=ROOT/"canonical_current_master_manifest.json"
PRICE=ROOT/"canonical_current_price_dv30.json"
SCHEMA="XRAY_ALPACA_CURRENT_515_EXACT260_SIP_SHADOW_V1"
BATCH_SIZE=32
UTC=dt.timezone.utc


def scope(price,master,*,rotate_unknown=False,rotation_session=None,ordered_unknown=None):
    asof=price.get("asof_et")
    if (asof!=master.get("asof_et") or price.get("unknown_never_pass") is not True
            or master.get("unknown_never_pass") is not True):
        raise ValueError("CURRENT_MASTER_PRICE_ASOF_DRIFT")
    for doc in (price,master):
        if doc.get("execution")!="NONE" or doc.get("real_money")!="NO-GO":
            raise ValueError("SOURCE_SAFETY_CHANGED")
    symbols=price.get("pass_symbols")
    if (not isinstance(symbols,list)
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
    if symbols:
        targets=sorted(set(symbols)|{"QQQ"})
    else:
        # Zero PRICE PASS must not create a blanket no-data bootstrap deadlock.
        # Source diagnostics may study bounded canonical UNKNOWN symbols ONLY;
        # they cannot be classified as PRICE, HISTORY or MC PRIMARY.
        unknown=price.get("unknown_symbols")
        result_rows=price.get("results")
        if (type(unknown) is not list or unknown!=sorted(set(unknown))
                or type(price.get("unknown_count")) is not int
                or price["unknown_count"]!=len(unknown)
                or not set(unknown).issubset(set(master.get("pass_symbols") or []))
                or type(result_rows) is not dict
                or any(type(result_rows.get(s)) is not dict
                       or result_rows[s].get("status")!="UNKNOWN"
                       for s in unknown)):
            raise ValueError("ZERO_PASS_UNKNOWN_SOURCE_PROVENANCE_INVALID")
        targets=(scheduled_unknown_cohort(
            unknown,asof,batch_size=BATCH_SIZE,
            rotation_session=rotation_session,
            ordered_source_research_symbols=ordered_unknown)
            if rotate_unknown else unknown[:BATCH_SIZE])
    return asof,targets,daily,weeks


def zero_scope_report(asof,daily,weeks):
    """No PRICE survivors => no QQQ-only HISTORY probe and no provider calls."""
    return {
      "schema":SCHEMA,"asof_et":asof,"policy":"C4.17","control":"C4.27",
      "status":"BLOCKED_ZERO_PRICE_PASS_NO_260_HISTORY_REQUEST",
      "expected_scope_count":0,"measured_scope_count":0,
      "contains_qqq_benchmark":False,
      "expected_daily_sessions":len(daily),
      "required_completed_week_closes":len(weeks),
      "batch_size":BATCH_SIZE,"batches_attempted":0,
      "counts":{},"unverified_symbols":{},"transport_error_class":None,
      "api_feed":"sip","api_timeframe":"1Day","api_adjustment":"raw",
      "source_market_data_rights_independently_attested":False,
      "corporate_action_adjustment_and_share_class_attested":False,
      "current_c417_history_primary_authority":False,
      "canonical_history_pass_created":0,"primary_mc_pass_created":0,
      "strict_g9_pass":False,"account_pass":False,"r92_created":False,
      "vendor_ohlcv_in_artifact":False,"vendor_raw_bars_persisted":False,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
    }


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


def audit(asof,targets,daily,weeks,batch_fetch,*,now,
          zero_pass_unknown=False):
    if now.tzinfo is None or not sufficient_delay(asof,now):
        raise ValueError("SIP_20MIN_OFFICIAL_CLOSE_HOLDBACK_NOT_MET")
    # ROOT-PASS-first priority deliberately differs from alphabetical order.
    # Only the zero-PASS research lane may preserve that exact source order;
    # ordinary PRICE-PASS / full-cohort paths retain alphabetical strictness.
    if (len(targets)!=len(set(targets))
            or (not zero_pass_unknown and targets!=sorted(targets))
            or len(daily)!=260 or len(weeks)!=52
            or type(zero_pass_unknown) is not bool
            or (zero_pass_unknown and
                (not targets or len(targets)>BATCH_SIZE or "QQQ" in targets))
            or (not zero_pass_unknown and "QQQ" not in targets)):
        raise ValueError("UNTRUSTED_TARGET_SCOPE")
    counters=collections.Counter()
    missing_by_reason={}
    measured=0
    transport_error=None
    start=daily[0]+"T00:00:00Z"
    end=bounded_sip_end(asof,now,
         (dt.date.fromisoformat(asof)+dt.timedelta(days=1)).isoformat()+"T00:00:00Z")
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
        "status":(("SHADOW_ZERO_PRICE_PASS_UNKNOWN_260_SOURCE_MEASURED_NO_AUTHORITY"
                   if zero_pass_unknown else
                   "SHADOW_FULL_515_SCOPE_MEASURED_NO_AUTHORITY")
                  if measured==len(targets) and transport_error is None
                  else "SHADOW_INCOMPLETE_TRANSPORT_OR_SCOPE"),
        "expected_scope_count":len(targets),"measured_scope_count":measured,
        "contains_qqq_benchmark":not zero_pass_unknown,
        "zero_price_pass_unknown_research_only":zero_pass_unknown,
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
    no_equity=dict(fake_price,pass_symbols=[],pass_count=0,
                   pass_hash=sha256_lines([]),unknown_count=2,
                   unknown_symbols=["AAA","BBB"])
    no_equity_master=dict(fake_master)
    no_equity["results"]={s:{"status":"UNKNOWN"} for s in ["AAA","BBB"]}
    za,zt,zd,zw=scope(no_equity,no_equity_master)
    assert za==asof and zt==["AAA","BBB"] and len(zd)==260
    now=dt.datetime(2026,10,10,20,tzinfo=UTC)
    def unknown_fetch(batch,start,end):
        return {sym:good for sym in batch}
    researched=audit(za,zt,zd,zw,unknown_fetch,now=now,
                     zero_pass_unknown=True)
    assert researched["status"]=="SHADOW_ZERO_PRICE_PASS_UNKNOWN_260_SOURCE_MEASURED_NO_AUTHORITY"
    assert researched["measured_scope_count"]==2
    assert researched["zero_price_pass_unknown_research_only"] is True
    assert researched["current_c417_history_primary_authority"] is False
    assert researched["canonical_history_pass_created"]==0
    assert researched["r92_created"] is False
    # Noncanonical or forged UNKNOWN status must never authorize data collection.
    import copy
    for name,mutate in (
        ("BAD_COUNT",lambda p:p.update(unknown_count=3)),
        ("FORGED_PASS",lambda p:p["results"]["AAA"].update(status="PASS")),
        ("BAD_ORDER",lambda p:p.update(unknown_symbols=["BBB","AAA"])),
        ("FOREIGN",lambda p:p.update(unknown_symbols=["AAA","ZZZ"])),
        ("MISSING_RESULTS",lambda p:p.update(results={})),
        ("BAD_PASS_HASH",lambda p:p.update(pass_hash="0"*64)),
    ):
        bad=copy.deepcopy(no_equity)
        mutate(bad)
        try:scope(bad,no_equity_master)
        except ValueError:pass
        else:raise AssertionError("UNAUTHORIZED_ZERO_PASS_SOURCE:"+name)
    # The original canonical PRICE unknown cohort must rotate over verified
    # official Nasdaq sessions, not repeatedly scan the same 32 symbols.
    asof_rotation="2026-10-20"
    names=[f"X{i:03d}" for i in range(49)]
    frozen={
        "asof_et":asof_rotation,
        "pass_symbols":[],"pass_count":0,"pass_hash":sha256_lines([]),
        "unknown_symbols":names,"unknown_count":len(names),
        "blocked_count":0,
        "results":{name:{"status":"UNKNOWN"} for name in names},
        "unknown_never_pass":True,"execution":"NONE","real_money":"NO-GO"}
    master_rotation={"asof_et":asof_rotation,
                     "pass_symbols":names,"unknown_never_pass":True,
                     "execution":"NONE","real_money":"NO-GO"}
    _,first,_,_=scope(frozen,master_rotation,rotate_unknown=True,
                      rotation_session="2026-10-20")
    _,second,_,_=scope(frozen,master_rotation,rotate_unknown=True,
                       rotation_session="2026-10-21")
    assert first==names[:32] and second==names[32:]
    # Research ROOT-PASS priority is a bijection of canonical UNKNOWN, not an
    # alphabetic set. Previously scope() selected a legitimate ranked slice
    # but audit() rejected it before bounded HTTP even began.
    prioritized=list(reversed(names))
    _,ranked,ranked_days,ranked_weeks=scope(
        frozen,master_rotation,rotate_unknown=True,
        rotation_session="2026-10-20",ordered_unknown=prioritized)
    assert ranked==prioritized[:32] and ranked!=sorted(ranked)
    ranked_bars=[bar(day) for day in ranked_days]
    def ranked_memory_fetch(batch,start,end):
        assert batch==ranked and len(batch)==32
        return {sym:ranked_bars for sym in batch}
    ranked_result=audit(
        asof_rotation,ranked,ranked_days,ranked_weeks,ranked_memory_fetch,
        now=dt.datetime(2026,10,21,22,10,tzinfo=UTC),
        zero_pass_unknown=True)
    assert ranked_result["measured_scope_count"]==32
    assert ranked_result["status"]=="SHADOW_ZERO_PRICE_PASS_UNKNOWN_260_SOURCE_MEASURED_NO_AUTHORITY"
    assert ranked_result["canonical_history_pass_created"]==0
    assert ranked_result["current_c417_history_primary_authority"] is False
    assert ranked_result["r92_created"] is False
    assert ranked_result["vendor_raw_bars_persisted"] is False
    # Normal PRICE-PASS lane must still reject this unordered source cohort.
    try:audit(
        asof_rotation,ranked+["QQQ"],ranked_days,ranked_weeks,
        ranked_memory_fetch,now=dt.datetime(2026,10,21,22,10,tzinfo=UTC))
    except ValueError:pass
    else:raise AssertionError("ORDINARY_PRICE_PASS_SCOPE_UNSORTED_ACCEPTED")
    for invalid in ("2026-10-22","2026-10-24","2026-10-19"):
        try:scope(frozen,master_rotation,rotate_unknown=True,
                  rotation_session=invalid)
        except ValueError:pass
        else:raise AssertionError("STALE_OR_CLOSED_SIP_ROTATION_ACCEPTED:"+invalid)
    z=zero_scope_report(za,zd,zw)
    assert z["status"]=="BLOCKED_ZERO_PRICE_PASS_NO_260_HISTORY_REQUEST"
    assert z["r92_created"] is False and z["current_c417_history_primary_authority"] is False
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
    # If latest NASDAQ session just ended, the requested calendar next-day
    # boundary would still be in the future: enforce 20-minute holdback.
    early=dt.datetime(2026,10,9,22,10,tzinfo=UTC)
    expected_cutoff=(early-dt.timedelta(minutes=20)).isoformat()
    def capped_fetch(batch,start,end):
        assert end==expected_cutoff, ("RECENT_SIP_END",end,expected_cutoff)
        return {symbol:good for symbol in batch}
    capped=audit(a,t,d,w,capped_fetch,now=early)
    assert capped["measured_scope_count"]==3
    assert capped["canonical_history_pass_created"]==0
    blocked=audit(a,t,d,w,fail,now=now)
    assert blocked["counts"]["UNCHECKED_DUE_TO_TRANSPORT"]==3
    assert blocked["transport_error_class"]=="ALPACA_HTTP_429"
    assert blocked["status"]=="SHADOW_INCOMPLETE_TRANSPORT_OR_SCOPE"
    # Exact per-page quota telemetry must count even the first provider attempt.
    virtual=[0.0]
    pacer=SipRequestPacer(clock=lambda: virtual[0],
                          sleeper=lambda delay: virtual.__setitem__(0,virtual[0]+delay))
    assert pacer.request_attempts==0
    pacer.pace();pacer.pace()
    assert pacer.request_attempts==2 and virtual[0]>=pacer.interval
    print("XRAY_ALPACA_515_EXACT260_SELFTEST=PASS_ZERO_PASS_UNKNOWN_SOURCE_MEASURED_6_ADVERSARIAL_NO_VENDOR_NO_PRIMARY_HTTP_PAGE_COUNTER")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    p.add_argument("--rotate-unknown",action="store_true",
                   help="Existing scheduled research-only official XNAS rotation")
    args=p.parse_args()
    if args.selftest:
        selftest();return
    if not args.out:
        p.error("--out required")
    price=json.loads(PRICE.read_text())
    master=json.loads(MASTER.read_text())
    rotation_session=None
    if args.rotate_unknown:
        from source_epoch_freshness_guard import last_complete_session
        rotation_session=last_complete_session(dt.datetime.now(UTC))
    ordered_unknown=(ranked_root_pass_unknown(
        price["unknown_symbols"],master,price)
        if args.rotate_unknown and price.get("pass_count")==0 else None)
    asof,targets,daily,weeks=scope(
        price,master,rotate_unknown=args.rotate_unknown,
        rotation_session=rotation_session,ordered_unknown=ordered_unknown)
    if not targets:
        # Only when even canonical UNKNOWN is empty is source reading empty.
        # Empty scope never creates benchmark-only history evidence.
        result=zero_scope_report(asof,daily,weeks)
    else:
        key=os.getenv("XRAY_ALPACA_DATA_KEY_ID","").strip()
        secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY","").strip()
        if not key or not secret:
            raise SystemExit("XRAY_ALPACA_515=BLOCKED_PRIVATE_CREDENTIALS_UNAVAILABLE")
        def real(batch,start,end):
            return request_batch(batch,start,end,key,secret,adjustment="raw",asof=asof)
        result=audit(asof,targets,daily,weeks,real,now=dt.datetime.now(UTC),
                     zero_pass_unknown=price["pass_count"]==0)
    result["api_symbol_mapping_asof_et"]=asof
    result["security_identity_lineage_independently_verified"]=False
    result["source_price_blob_sha"]=blob_sha(PRICE)
    result["source_master_blob_sha"]=blob_sha(MASTER)
    result["source_price_pass_hash"]=price["pass_hash"]
    result["price_pass_count"]=price["pass_count"]
    result["research_rotation_session"]=rotation_session
    result["price_unknown_count"]=price.get("unknown_count",0)
    result["price_unknown_research_remaining"]=(
        max(0,price["unknown_count"]-len(targets))
        if price["pass_count"]==0 else 0)
    # Stock identifiers and hashes are safe to archive; vendor OHLCV never is.
    # These fields allow the NEXT real scheduled run to prove that its selected
    # 32 symbols differ from the first slice, with exact PRICE/MASTER blob SHAs.
    result["research_symbols"]=list(targets)
    result["research_symbols_sha256"]=sha256_lines(targets)
    result["research_rotation_distinct_from_initial_32"]=bool(
        args.rotate_unknown and price["pass_count"]==0
        and targets!=price["unknown_symbols"][:BATCH_SIZE])
    result["api_http_page_attempts"]=PACER.request_attempts
    result["api_http_page_budget"]=MAX_PAGES*math.ceil(len(targets)/BATCH_SIZE)
    result["api_http_min_pacing_interval_seconds"]=PACER.interval
    if result["api_http_page_attempts"]>result["api_http_page_budget"]:
        raise RuntimeError("XRAY_SIP_PAGE_QUOTA_ATTEMPTS_EXCEEDED_FAIL_CLOSED")
    # Only count-only/symbol IDs; no raw bars, no prices, no per-bar timestamps.
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("XRAY_ALPACA_515_SHADOW_STATUS="+result["status"])
    print("XRAY_ALPACA_515_SHADOW_COUNTS="+json.dumps(result["counts"],sort_keys=True))
    print("XRAY_ALPACA_515_SHADOW_MEASURED="+str(result["measured_scope_count"]))
    print("XRAY_ALPACA_515_SOURCE_SCOPE_SYMBOLS="+",".join(targets))
    print("XRAY_ALPACA_515_SOURCE_SCOPE_SHA256="+result["research_symbols_sha256"])
    print("XRAY_ALPACA_515_ROTATION_SESSION="+str(result["research_rotation_session"]))
    print("XRAY_ALPACA_515_ROTATION_DISTINCT_FIRST32="+str(result["research_rotation_distinct_from_initial_32"]))
    print("XRAY_ALPACA_515_HTTP_PAGE_ATTEMPTS="+str(result["api_http_page_attempts"])+
          "_MAX="+str(result["api_http_page_budget"])+
          "_PACE_SECONDS="+str(result["api_http_min_pacing_interval_seconds"]))


if __name__=="__main__":
    main()
