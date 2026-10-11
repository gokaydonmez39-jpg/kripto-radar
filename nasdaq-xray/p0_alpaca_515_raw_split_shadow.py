#!/usr/bin/env python3
"""515 full-scope Alpaca raw/split-adjusted dual history parity; research only.

Exact canonical PRICE+MASTER/ASOF, both requests SIP 1Day with *explicit*
symbol mapping ASOF. Never publishes OHLCV, raw prices, share counts or
market caps. An internally consistent split adjustment is NOT an issuer
PIT/corporate-action attestation, a full 52-week PRIMARY history source,
C4.17 PRIMARY, R92, GO, or a right to redistribute market data.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import json
import math
import os
from pathlib import Path
from alpaca_full_scope_260_shadow import scope,classify,BATCH_SIZE,PRICE,MASTER
from alpaca_free_sip_shadow_guard import request_batch,timestamp_date,sufficient_delay,blob_sha

SCHEMA="XRAY_ALPACA_515_DUAL_RAW_SPLIT_SHADOW_V1"
FULL="SHADOW_260_DAILY_52_WEEK_OBSERVED"
SHORT="MISSING_EXACT_COMPLETED_SESSIONS"
MATCH="SHADOW_NO_RESTATEMENT_SEEN"
RESTATED="SHADOW_SPLIT_RESTATEMENT_NUMERICALLY_CONSISTENT"
BAD="UNKNOWN_DUAL_ADJUSTMENT_PROVENANCE"
UTC=dt.timezone.utc

def require(ok,reason):
    if not ok:raise ValueError("XRAY_ALPACA_DUAL_SPLIT:"+reason)

def compare(raw,adjusted,official,weekdays,asof):
    rstat,rcount=classify(raw,official,weekdays,asof)
    astat,acount=classify(adjusted,official,weekdays,asof)
    if (rstat not in (FULL,SHORT) or astat!=rstat or
            rcount!=acount):
        return BAD,0,rstat,astat
    try:
        r={timestamp_date(x["t"]).isoformat():x for x in raw}
        a={timestamp_date(x["t"]).isoformat():x for x in adjusted}
        if set(r)!=set(a) or len(r)!=len(raw) or len(a)!=len(adjusted):
            return BAD,0,rstat,astat
        changed=0
        for day in r:
            v=r[day];w=a[day]
            orig=[float(v[k]) for k in ("o","h","l","c","v")]
            adj=[float(w[k]) for k in ("o","h","l","c","v")]
            if not all(math.isfinite(x) and x>0 for x in orig+adj):
                return BAD,0,rstat,astat
            if all(math.isclose(x,y,rel_tol=1e-9,abs_tol=1e-9)
                   for x,y in zip(orig,adj)):
                continue
            q=adj[3]/orig[3]
            if not math.isfinite(q) or q<=0:
                return BAD,0,rstat,astat
            # One split factor must apply consistently to every OHLC.
            if any(abs((adj[k]/orig[k])/q-1)>0.025 for k in range(4)):
                return BAD,0,rstat,astat
            # Alpaca split adjustment is intended to alter volume inversely.
            # Roundoff may affect integer daily volumes; >2.5% unexplained
            # divergence is UNKNOWN, never silently PASS.
            if abs(adj[4]/orig[4]*q-1)>0.025:
                return BAD,0,rstat,astat
            changed+=1
        return (RESTATED if changed else MATCH),changed,rstat,astat
    except (KeyError,ValueError,TypeError,OverflowError,ZeroDivisionError):
        return BAD,0,rstat,astat

def audit(asof,targets,daily,weeks,fetch,now):
    require(now.tzinfo is not None and sufficient_delay(asof,now),
            "RTH_PROVIDER_SETTLEMENT_HOLDBACK")
    require(targets==sorted(set(targets)) and "QQQ" in targets
            and len(daily)==260 and len(weeks)==52 and daily[-1]==asof,
            "SCOPE_CALENDAR_OR_ASOF")
    start=daily[0]+"T00:00:00Z"
    end=(dt.date.fromisoformat(asof)+dt.timedelta(days=1)).isoformat()+"T00:00:00Z"
    counts=collections.Counter();base=collections.Counter()
    codes={};mismatch={};changes={};measured=0;failure=None
    for offset in range(0,len(targets),BATCH_SIZE):
        batch=targets[offset:offset+BATCH_SIZE]
        try:
            raw=fetch(batch,start,end,asof,"raw")
            split=fetch(batch,start,end,asof,"split")
            require(isinstance(raw,dict) and isinstance(split,dict) and
                    not(set(raw)-set(batch)) and not(set(split)-set(batch)),
                    "FOREIGN_SYMBOL_OR_BAD_PROVIDER_RESPONSE")
        except (RuntimeError,ValueError,TypeError,KeyError):
            failure="UNKNOWN_PROVIDER_DUAL_FETCH_OR_SCHEMA"
            break
        for sym in batch:
            state,changed,rstatus,astatus=compare(
                raw.get(sym,[]),split.get(sym,[]),daily,weeks,asof)
            counts[state]+=1;base[rstatus]+=1;measured+=1
            codes[sym]={"dual_classification":state,
                        "raw_calendar_classification":rstatus,
                        "split_calendar_classification":astatus}
            if state==BAD:
                mismatch[sym]="SPLIT_RAW_PARITY_OR_CALENDAR_INVALID"
            elif changed:
                changes[sym]="SPLIT_ADJUSTMENT_APPLIED_NUMERICALLY"
        del raw,split
    counts["UNCHECKED_DUE_TO_TRANSPORT"]+=len(targets)-measured
    return {
        "schema":SCHEMA,"asof_et":asof,"scope_with_qqq":len(targets),
        "measured_scope":measured,"feed":"sip","timeframe":"1Day",
        "raw_adjustment":"raw","comparison_adjustment":"split",
        "ticker_identity_mapping_asof_et":asof,
        "official_daily_sessions":len(daily),"official_week_closes":len(weeks),
        "counts":dict(sorted(counts.items())),
        "raw_calendar_counts":dict(sorted(base.items())),
        "source_symbol_statuses":codes,"unresolved_symbols":mismatch,
        "numeric_restatement_symbols":sorted(changes),
        "numeric_restatement_count":len(changes),
        "transport_failure_class":failure,
        "status":("SHADOW_DUAL_ADJUSTMENT_SCOPE_MEASURED_NO_PIT_AUTHORITY"
                  if measured==len(targets) and failure is None else
                  "SHADOW_INCOMPLETE_DUAL_SOURCE"),
        "provider_action_event_published_at_PIT_verified":False,
        "historical_stock_identity_issuer_CUSIP_reconciled":False,
        "split_adj_ca_publication_and_issuer_verified":False,
        "license_to_automate_independently_attested":False,
        "production_HISTORY_PASS_created":0,
        "C417_PRIMARY_MC_created":0,
        "R92_created":False,"GO":False,
        "price_volume_bars_or_event_data_persisted":False,
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True
    }

def selftest():
    from zoneinfo import ZoneInfo
    NY=ZoneInfo("America/New_York")
    asof="2026-10-09"
    dates=["2026-10-07","2026-10-08","2026-10-09"]
    weekly=["2026-10-09"]
    def bar(day,open=10.0,high=11.0,low=9.0,close=10.0,volume=1000):
        t=dt.datetime.combine(dt.date.fromisoformat(day),dt.time(0),NY)
        return {"t":t.astimezone(UTC).isoformat(),
                "o":open,"h":high,"l":low,"c":close,"v":volume}
    original=[bar(d) for d in dates]
    # Purely synthetic and no provider records. A comparison alone is not
    # permitted to mint HISTORY PASS. audit() rejects fake 3-session horizons.
    try:
        audit(asof,["QQQ"],dates,weekly,lambda *a:{"QQQ":original},
              dt.datetime(2026,10,10,18,tzinfo=UTC))
    except ValueError:
        pass
    else:
        raise AssertionError("FAKE_THREE_SESSION_SCOPE_ACCEPTED")
    # The isolated classifier receives the complete 260/52 official contract.
    from current_history_source_request import expected_dates
    daily,weeks=expected_dates(asof)
    limited=compare(original,original,daily,weeks,asof)
    require(limited[0]==MATCH and limited[2]==SHORT and limited[3]==SHORT,
            "SHORT_STAYS_SHORT_NOT_HISTORY_PASS")
    base=[bar(d) for d in daily]
    require(compare(base,base,daily,weeks,asof)[0]==MATCH,
            "IDENTICAL_POSITIVE")
    changed=[dict(v) for v in base]
    changed[0]=dict(changed[0],o=5.0,h=5.5,l=4.5,c=5.0,v=2000)
    assert_status=compare(base,changed,daily,weeks,asof)
    require(assert_status[0]==RESTATED and assert_status[1]==1,
            "SYNTHETIC_2_TO_1_RESTATEMENT")
    invalid=[dict(v) for v in changed]
    invalid[0]=dict(invalid[0],v=1000)
    require(compare(base,invalid,daily,weeks,asof)[0]==BAD,
            "SPLIT_VOLUME_RATIO_MISMATCH")
    invalid=[dict(v) for v in changed]
    invalid[0]=dict(invalid[0],o=10.0)
    require(compare(base,invalid,daily,weeks,asof)[0]==BAD,
            "SPLIT_OHLC_FACTOR_MISMATCH")
    require(compare(base,changed[:-1],daily,weeks,asof)[0]==BAD,
            "SPLIT_MISSING_LATEST_SESSION")
    invalid=[dict(v) for v in changed]
    invalid[0]=dict(invalid[0],t="2026-10-09T20:00:00Z")
    require(compare(base,invalid,daily,weeks,asof)[0]==BAD,
            "INTRADAY_FALSE_DAILY_TIMESTAMP")
    invalid=[dict(v) for v in changed]
    invalid[0]=dict(invalid[0],v=0)
    require(compare(base,invalid,daily,weeks,asof)[0]==BAD,
            "ZERO_VOLUME_FALSE_ACCEPT")
    print("XRAY_ALPACA_DUAL_RAW_SPLIT_SELFTEST=PASS_2_POSITIVE_6_NEGATIVE_PYTHON_O_SAFE_NO_PRIMARY")

def main():
    arg=argparse.ArgumentParser()
    arg.add_argument("--selftest",action="store_true")
    arg.add_argument("--out",type=Path)
    args=arg.parse_args()
    if args.selftest:return selftest()
    require(args.out is not None,"OUTPUT_PATH_REQUIRED")
    price=json.loads(PRICE.read_text());master=json.loads(MASTER.read_text())
    asof,targets,daily,weeks=scope(price,master)
    key=os.getenv("XRAY_ALPACA_DATA_KEY_ID","")
    secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY","")
    require(key and secret,"SECRET_DATA_KEYS_MISSING")
    result=audit(asof,targets,daily,weeks,
                 lambda batch,start,end,date,adj:request_batch(
                     batch,start,end,key,secret,adjustment=adj,asof=date),
                 dt.datetime.now(UTC))
    result["source_price_blob_sha"]=blob_sha(PRICE)
    result["source_master_blob_sha"]=blob_sha(MASTER)
    result["source_price_pass_hash"]=price["pass_hash"]
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_ALPACA_515_RAW_SPLIT_STATUS="+result["status"])
    print("XRAY_ALPACA_515_RAW_SPLIT_COUNTS="+json.dumps(result["counts"],sort_keys=True))
    print("XRAY_ALPACA_515_RAW_SPLIT_NO_PRIMARY=true")

if __name__=="__main__":main()
