#!/usr/bin/env python3
"""P0 split-ratio mathematical replay, 11 real symbols, 260 sessions.

Consumes the exact SHA-bound real 515 dual raw/split artifact, re-fetches
personal delayed Alpaca SIP raw + split daily bars and official Alpaca split
CA old_rate/new_rate with process dates. Replays the compounded split factor
for each of 260 sessions and independently checks OHLC + inverse volume.

This is SAME-VENDOR numerical evidence. It does not establish independent
SEC issuer CUSIP, PIT publication time, personal automation entitlements,
PRIMARY MC, HISTORY PRIMARY, R92, AL or production GO. Raw bars, split
amounts, source event IDs and prices NEVER leave process memory.
"""
from __future__ import annotations
import argparse,datetime as dt,decimal,json,math,os
from pathlib import Path
from alpaca_full_scope_260_shadow import scope,PRICE,MASTER,classify
from alpaca_free_sip_shadow_guard import blob_sha,request_batch,timestamp_date,sufficient_delay
from alpaca_full_scope_ca_shadow import request_page,MAX_PAGES,KNOWN_GROUPS
from decimal import Decimal,InvalidOperation

SCHEMA="XRAY_P0_11_SPLIT_FACTOR_FULL_260_MATHEMATICAL_REPLAY_SHADOW_V1"
DUAL_SCHEMA="XRAY_ALPACA_515_DUAL_RAW_SPLIT_SHADOW_V1"
SPLIT_GROUPS=frozenset(("forward_splits","reverse_splits","unit_splits"))
FULL="SHADOW_260_DAILY_52_WEEK_OBSERVED"
SPLIT="SHADOW_SPLIT_RESTATEMENT_NUMERICALLY_CONSISTENT"

def require(cond,why):
    if not cond:raise ValueError("XRAY_P0_SPLIT_RATIO:"+why)

def dec(x):
    require(type(x) in (float,int,str) and not isinstance(x,bool),
            "NON_NUMERIC_RATIO")
    try:v=Decimal(str(x))
    except InvalidOperation as e:raise ValueError("XRAY_P0_SPLIT_RATIO:INVALID_DECIMAL") from e
    require(v.is_finite() and v>0,"NONPOSITIVE_OR_INFINITE_VALUE")
    return v

def events(symbol,first,asof,fetch):
    seen_ids=set();seen_pages=set();tok=None;actual=[]
    for _ in range(MAX_PAGES):
        response=fetch([symbol],first,asof,tok)
        require(type(response) is dict and type(response.get("corporate_actions")) is dict,
                "CA_RESPONSE_INVALID")
        groups=response["corporate_actions"]
        for group,rows in groups.items():
            require(group in KNOWN_GROUPS and type(rows) is list,"UNKNOWN_CA_GROUP")
            for row in rows:
                require(type(row) is dict and type(row.get("id")) is str and row["id"],
                        "INVALID_EVENT_ID")
                require(row["id"] not in seen_ids,"DUPLICATE_EVENT_ID")
                seen_ids.add(row["id"])
                process=row.get("process_date")
                require(type(process) is str and len(process)==10 and
                        first<=process<=asof,"OUT_OF_RANGE_EVENT_DATE")
                # Multi-issuer merger/rename events may include multiple
                # parties; for SPLIT require direct traded ticker subject.
                if group not in SPLIT_GROUPS:continue
                require(row.get("symbol")==symbol,"SPLIT_TICKER_IDENTITY_MISMATCH")
                new=dec(row.get("new_rate"));old=dec(row.get("old_rate"))
                factor=new/old
                require(factor.is_finite() and factor>0,"BAD_SPLIT_FACTOR")
                require(row.get("ex_date") in (None,process),
                        "PROCESS_EX_DATE_CONFLICT")
                actual.append((process,factor))
        nxt=response.get("next_page_token")
        if nxt in (None,""):
            return sorted(actual)
        require(type(nxt) is str and 0<len(nxt)<=2048 and
                nxt not in seen_pages and nxt!=tok,"CA_CURSOR_LOOP")
        seen_pages.add(nxt);tok=nxt
    raise ValueError("XRAY_P0_SPLIT_RATIO:CA_PAGE_BUDGET")

def matched_factor(origin,split,factor,*,volume=False):
    a=dec(origin);b=dec(split)
    wanted=a*factor if volume else a/factor
    # Vendor price rounding tolerance 0.5 cent OR 0.075% maximum,
    # volume integer rounding tolerance 2 units OR 0.075%; any larger
    # discrepancy must be marked UNKNOWN, not accepted as adjusted.
    absolute=Decimal("2") if volume else Decimal("0.005")
    relative=Decimal("0.00075")
    tolerance=max(absolute, abs(wanted)*relative)
    return abs(b-wanted)<=tolerance

def verify_one(symbol,raw,split,split_events,daily,weeks,asof):
    require(type(raw) is list and type(split) is list,"BAD_BAR_LISTS")
    rs,rc=classify(raw,daily,weeks,asof)
    ss,sc=classify(split,daily,weeks,asof)
    require(rs==ss==FULL and rc==sc,"260_52_DAILY_CLASSIFICATION_NOT_PASS")
    def to_map(rows):
        result={}
        for x in rows:
            require(type(x) is dict and type(x.get("t")) is str,
                    "BAR_SCHEMA")
            day=timestamp_date(x["t"]).isoformat()
            require(day in daily and day not in result,
                    "BAD_OR_DUPLICATED_SESSION_DATE")
            result[day]=x
        return result
    r=to_map(raw);s=to_map(split)
    require(set(r)==set(s)==set(daily),"RAW_SPLIT_DATE_SET_MISMATCH")
    require(type(split_events) is list and split_events,
            "RESTATED_WITHOUT_SPLIT_CA_EVENTS")
    require(all(type(x) is tuple and len(x)==2 and
                type(x[0]) is str and daily[0]<=x[0]<=asof and
                type(x[1]) is Decimal and x[1]>0
                for x in split_events),"BAD_CA_EVENTS")
    changed=0;max_residual=Decimal("0")
    for day in daily:
        factor=Decimal(1)
        for process,ratio in split_events:
            if process>day:factor*=ratio
        for key in ("o","h","l","c"):
            require(key in r[day] and key in s[day],
                    "BAR_OHLC_MISSING")
            require(matched_factor(r[day][key],s[day][key],factor),
                    "SPLIT_FACTOR_OHLC_NOT_REPRODUCIBLE")
        require(matched_factor(r[day]["v"],s[day]["v"],factor,volume=True),
                "SPLIT_FACTOR_VOLUME_NOT_REPRODUCIBLE")
        if factor!=1:changed+=1
    require(changed>0,"NO_REAL_SPLIT_RESTATEMENT_WITHIN_260")
    return {"classification":"SHADOW_260_SESSIONS_SPLIT_RATIO_MATHEMATICAL_REPLAY",
            "official_260_session_pair_proven":True,
            "vendor_CA_process_ratios_replayed":True,
            "ratio_events_seen":len(split_events),
            "price_volume_factor_math_pass":True,
            "issuer_official_CA_independent":False}

def audit(dual,fetch_bars,fetch_events):
    price=json.loads(PRICE.read_text());master=json.loads(MASTER.read_text())
    asof,targets,daily,weeks=scope(price,master)
    require(dual.get("schema")==DUAL_SCHEMA and
            dual.get("asof_et")==asof and
            dual.get("ticker_identity_mapping_asof_et")==asof and
            dual.get("source_price_blob_sha")==blob_sha(PRICE) and
            dual.get("source_master_blob_sha")==blob_sha(MASTER) and
            dual.get("source_price_pass_hash")==price.get("pass_hash") and
            dual.get("status")=="SHADOW_DUAL_ADJUSTMENT_SCOPE_MEASURED_NO_PIT_AUTHORITY"
            and dual.get("scope_with_qqq")==515 and
            dual.get("measured_scope")==515 and
            dual.get("unresolved_symbols")=={} and
            dual.get("production_HISTORY_PASS_created")==0
            and dual.get("C417_PRIMARY_MC_created")==0
            and dual.get("GO") is False,
            "SOURCE_515_IMMUTABLE_SCOPE_UNPROVEN")
    changed=dual.get("numeric_restatement_symbols")
    require(type(changed) is list and len(changed)==11 and
            changed==sorted(set(changed)) and
            set(changed).issubset(set(targets)-{"QQQ"}) and
            all(dual["source_symbol_statuses"][sym].get("dual_classification")==SPLIT
                for sym in changed),"EXACT_11_NUMERIC_RESTATEMENT_SCOPE")
    outcome={}
    for symbol in changed:
        try:
            original=fetch_bars(symbol,daily[0],asof,"raw")
            adjusted=fetch_bars(symbol,daily[0],asof,"split")
            announces=events(symbol,daily[0],asof,fetch_events)
            outcome[symbol]=verify_one(symbol,original,adjusted,announces,daily,weeks,asof)
        except (ValueError,RuntimeError,TypeError,KeyError,OverflowError,InvalidOperation):
            outcome[symbol]={"classification":"UNKNOWN_SPLIT_FACTOR_CA_OR_BAR_PIT",
                             "price_volume_factor_math_pass":False,
                             "issuer_official_CA_independent":False}
    passed=[s for s,x in outcome.items() if x["price_volume_factor_math_pass"]]
    return {"schema":SCHEMA,"asof_et":asof,
            "source_dual_raw_split_run":38178676524,
            "source_price_blob_sha":blob_sha(PRICE),
            "source_master_blob_sha":blob_sha(MASTER),
            "source_price_pass_hash":price["pass_hash"],
            "full_515_scope_bound":515,
            "split_restatement_cohort":len(changed),
            "verified_split_factor_math":len(passed),
            "unresolved_split_factor_math":len(changed)-len(passed),
            "per_symbol_status":{s:{"classification":x["classification"],
                    "price_volume_factor_math_pass":x["price_volume_factor_math_pass"]}
                    for s,x in outcome.items()},
            "status":"SAME_VENDOR_SPLIT_FACTOR_ARITHMETIC_REPLAY_RESEARCH_ONLY",
            "vendor_raw_prices_shares_or_CA_event_ids_persisted":False,
            "issuer_filing_publication_time_independently_attested":False,
            "C417_PRIMARY_MC_created":0,"canonical_HISTORY_PASS_created":0,
            "R92_created":False,"GO":False,"execution":"NONE",
            "real_money":"NO-GO","unknown_never_pass":True}

def selftest():
    # Entirely synthetic, no actual vendor/share/MC data.
    r=[("2026-10-08",Decimal(2)),("2026-10-09",Decimal("1.5"))]
    for day,want in [
        ("2026-10-07",Decimal(3)),
        ("2026-10-08",Decimal("1.5")),
        ("2026-10-09",Decimal(1))]:
        f=Decimal(1)
        for d,q in r:
            if d>day:f*=q
        require(f==want,"STRICT_PROCESS_DAY_OFF_BY_ONE")
        require(matched_factor(100,100/f,f),"PROPORTIONAL_PRICE_"+day)
        require(matched_factor(100,100*f,f,volume=True),"INV_VOLUME_"+day)
    def negative(name,fn):
        try:fn()
        except (ValueError,TypeError):return
        raise AssertionError("FALSE_FACTOR_PASS:"+name)
    require(not matched_factor(100,50,Decimal(3)),"FALSE_RATIO_CANNOT_PASS")
    require(not matched_factor(100,100,Decimal(2)),"MISSING_SPLIT_ADJUSTMENT")
    require(not matched_factor(100,200,Decimal(2),volume=False),
            "FLIPPED_PRICE_FACTOR")
    require(not matched_factor(100,50,Decimal(2),volume=True),
            "FLIPPED_VOLUME_FACTOR")
    negative("ZERO_RATIO",lambda:dec(0))
    negative("NAN_RATIO",lambda:dec(float("nan")))
    negative("STRING_POISON",lambda:dec("nothing"))
    negative("BOOLEAN_FACTOR",lambda:dec(True))
    test_event={"id":"SYNTH_ONLY","symbol":"FAKE",
                "process_date":"2026-10-08","ex_date":"2026-10-08",
                "old_rate":1,"new_rate":2}
    def re(ev,group="forward_splits"):
        return events("FAKE","2026-10-01","2026-10-09",
                      lambda *args:{"corporate_actions":{group:[ev]},
                                  "next_page_token":None})
    require(re(test_event)==[("2026-10-08",Decimal(2))],
            "EXACT_CA_RATIO_POSITIVE")
    negative("CA_TICKER",lambda:re(dict(test_event,symbol="OTHER")))
    negative("CA_WRONG_PROCESS",lambda:re(dict(test_event,process_date="2026-10-10")))
    negative("CA_EX_DATE",lambda:re(dict(test_event,ex_date="2026-10-09")))
    negative("CA_RATE_ZERO",lambda:re(dict(test_event,new_rate=0)))
    negative("CA_UNKNOWN_GROUP",lambda:re(test_event,group="UNKNOWN_EVENT"))
    print("XRAY_P0_11_SPLIT_RATIO_REPLAY_SELFTEST=PASS_4_POSITIVE_13_NEGATIVE_PYTHON_O_SAFE_NO_PRIMARY")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--dual",type=Path)
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:return selftest()
    require(args.dual is not None and args.out is not None,"INPUT_OUTPUT_PATH_REQUIRED")
    key=os.getenv("XRAY_ALPACA_DATA_KEY_ID","")
    secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY","")
    require(key and secret,"ALPACA_PERSONAL_API_PRIVATE_KEYS_MISSING")
    p=json.loads(PRICE.read_text())
    asof=p["asof_et"]
    require(sufficient_delay(asof,dt.datetime.now(dt.timezone.utc)),
            "SIP_RTH_CLOSE_HOLDBACK_NOT_MET")
    data=json.loads(args.dual.read_text())
    def bars(symbol,start,end,adjustment):
        one=(dt.date.fromisoformat(end)+dt.timedelta(days=1)).isoformat()
        return request_batch([symbol],start+"T00:00:00Z",
            one+"T00:00:00Z",key,secret,adjustment=adjustment,asof=end)[symbol]
    def actions(batch,start,end,token):
        return request_page(batch,start,end,key,secret,token)
    out=audit(data,bars,actions)
    args.out.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("XRAY_P0_11_SPLIT_RATIO_STATUS="+out["status"])
    print("XRAY_P0_11_SPLIT_RATIO_VERIFIED="+str(out["verified_split_factor_math"]))
    print("XRAY_P0_11_SPLIT_RATIO_UNKNOWN="+str(out["unresolved_split_factor_math"]))
    print("XRAY_P0_11_SPLIT_RATIO_PRIMARY_CREATED=0")

if __name__=="__main__":main()
