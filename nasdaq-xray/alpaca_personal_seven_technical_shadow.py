#!/usr/bin/env python3
"""Noncommercial personal SIP technical recheck; zero orders, zero R92.

Reuse frozen C4.17 weekly/A/B/D/R1 math, never copy OHLCV into public files.
This is a SECONDARY technical observation, not canonical production authority.
"""
import argparse,collections,datetime as dt,json,math,os
from pathlib import Path
import pandas as pd
from alpaca_candidate_local_260_recovery_shadow import source_scope,STATE,blob_sha
from alpaca_free_sip_shadow_guard import request_batch,timestamp_date
from alpaca_full_scope_260_shadow import classify
from alpha_semantics import mechanical_scale_breaks,mechanical_split_suspects
import stage1_shadow as stage
import deep_pre_r1_shadow as deep
import final_tech_shadow as final
from candidate_local_independent_math_v1 import audit as math_audit
from official_first_trade_260_history_guard import fence

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_PERSONAL_SEVEN_SIP_TECHNICAL_SHADOW_V1"
def need(ok,why):
    if not ok:raise ValueError("XRAY_PERSONAL_SEVEN_"+why)
def quality(rows,days,weeks,asof):
    status,n=classify(rows,days,weeks,asof)
    if status!="SHADOW_260_DAILY_52_WEEK_OBSERVED" or n!=260:
        return None,status
    out=[]
    if len(rows)!=260:return None,"UNKNOWN_ROW_COUNT"
    for bar in rows:
        v=bar["v"]
        if type(v) not in (float,int) or not math.isfinite(v) or v<=0 or int(v)!=v:
            return None,"UNKNOWN_NONINTEGER_VOLUME"
        out.append({"date":timestamp_date(bar["t"]).isoformat(),
                    "open":bar["o"],"high":bar["h"],"low":bar["l"],
                    "close":bar["c"],"volume":int(v)})
    if [x["date"] for x in out]!=days:
        return None,"UNKNOWN_OFFICIAL_SESSION_ORDER"
    df=pd.DataFrame(out)
    df["date"]=pd.to_datetime(df["date"])
    if mechanical_scale_breaks(df,260) or mechanical_split_suspects(df,260):
        # Return bars in RAM only for independent event reconciliation.
        # Callers MUST NOT calculate technical PASS until events are checked.
        return df,"UNKNOWN_CORPORATE_ACTION_PIT"
    return df,"HISTORICAL_SIP_260_52_RAW_RESEARCH_ONLY"
def assess(sym,df,qqq,asof,week_last):
    base=stage.weekly_gate(df,asof,week_last)
    eligible,ctx=stage.recent_weekly_context(df,week_last)
    if base.get("weeks",0)<52:
        return "UNKNOWN_52_COMPLETED_WEEKS",0
    if not eligible:
        return "NO_CURRENT_OR_RECENT_WEEKLY_GATE",0
    a,b,d=deep.evaluate_recent_families(df,qqq,eligible)
    patterns={"A":a,"B":b,"D":d}
    passing={k:g for k,g in patterns.items() if g.get("pool") is True and
             g.get("trigger_date") in eligible and
             (k=="A" or k=="D" and g.get("dk3_pre_r1") is True or
              k=="B" and g.get("breakout_confirmed") is True)}
    if not passing:return "NO_CONFIRMED_A_B_D_RECENT_TRIGGER",0
    verified=0
    unresolved=0
    for family,g in passing.items():
        z=final.eval_one(sym,family,g,df,event_status="UNKNOWN",
                         state_cap="WATCH",r92_eligible=False,
                         regime_finalist_status="UNKNOWN")
        checked=math_audit(family,g,z,df)
        if checked.get("independently_verified") is True:
            verified+=1
        else:unresolved+=1
    if unresolved:return "UNKNOWN_FROZEN_TECHNICAL_GEOMETRY",verified
    return "TECHNICAL_FAMILY_RESEARCH_ONLY_RELEASE_GATES_OPEN",verified
def chunks(names,n=12):
    need(type(names) is list and names==sorted(set(names)) and
         type(n) is int and 1<=n<=12,"EXACT_BATCH_PARTITION")
    out=[names[k:k+n] for k in range(0,len(names),n)]
    need([v for group in out for v in group]==names and
         all(1<=len(group)<=n for group in out),
         "EVERY_PENDING_SYMBOL_RETAINED")
    return out

def run(now,fetch):
    root=json.loads(STATE.read_text())
    asof,names,days,weeks=source_scope(root,now)
    need("QQQ" not in names and names==sorted(set(names)),
         "LATEST_ALL_UNRESOLVED_NO_TRUNCATION")
    result={"schema":SCHEMA,"asof_et":asof,"scope_count":len(names),
       "source_state_git_blob_sha":blob_sha(STATE),
       "source":"ALPACA_HISTORICAL_SIP_PERSONAL_NONCOMMERCIAL",
       "statuses":{},"benchmark_status":"UNKNOWN","api_batch_count":0,
       "pending_symbol_truncation":False,
       "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
       "no_raw_market_data_exported":True,"canonical_files_mutated":False,
       "canonical_price_promoted":False,"canonical_history_promoted":False,
       "primary_mc_promoted":False,"true_r92_count":0,
       "final_buy_signals":[],"iphone_receipt_attested":False}
    if not names:
        result["benchmark_status"]="NOT_REQUIRED_NO_PENDING"
        result["counts"]={}
        return result
    start=days[0]+"T00:00:00Z"
    end=(dt.date.fromisoformat(asof)+dt.timedelta(days=1)).isoformat()+"T00:00:00Z"
    try:
        qbars=fetch(["QQQ"],start,end,asof)
        result["api_batch_count"]+=1
        need(type(qbars) is dict and set(qbars)=={"QQQ"},
             "BENCHMARK_SOURCE_SCOPE")
        qqq,qstate=quality(qbars["QQQ"],days,weeks,asof)
    except Exception:
        qqq=None
        qstate="UNKNOWN_QQQ_PROVIDER_OR_SCOPE"
    if qstate!="HISTORICAL_SIP_260_52_RAW_RESEARCH_ONLY":
        qqq=None
    result["benchmark_status"]=qstate
    if qqq is None:
        result["statuses"]={sym:"UNKNOWN_QQQ_260_52" for sym in names}
        result["counts"]={"UNKNOWN_QQQ_260_52":len(names)}
        return result
    last_weeks=stage.build_week_last(asof)
    groups=chunks(names)
    for i,block in enumerate(groups):
        try:
            raw=fetch(block,start,end,asof)
            result["api_batch_count"]+=1
            need(type(raw) is dict and set(raw)==set(block),
                 "PROVIDER_BATCH_SCOPE")
        except Exception as exc:
            for sym in block:
                result["statuses"][sym]="UNKNOWN_BATCH_TRANSPORT_OR_SCOPE"
            if "429" in str(exc) or "RATE_LIMIT" in str(exc):
                for remainder in groups[i+1:]:
                    for sym in remainder:
                        result["statuses"][sym]="UNKNOWN_RATE_LIMIT_NOT_QUERIED"
                break
            continue
        for sym in block:
            try:
                listing=fence(sym,asof)
                if listing and listing["own_listed_history_short"]:
                    result["statuses"][sym]="FAIL_OFFICIAL_LISTED_HISTORY_LT260"
                    continue
                df,history=quality(raw[sym],days,weeks,asof)
                if df is None:
                    result["statuses"][sym]=history
                    continue
                if history=="UNKNOWN_CORPORATE_ACTION_PIT":
                    corrected,ca_status,events=stage.split_consistent_history(sym,df,260)
                    from candidate_local_full_technical_funnel_v1 import _history_ok
                    if not str(ca_status).startswith("PASS") or not _history_ok(corrected,days):
                        result["statuses"][sym]="UNKNOWN_CORPORATE_ACTION_PIT"
                        continue
                    df=corrected
                status,count=assess(sym,df,qqq,asof,last_weeks)
                result["statuses"][sym]=status
            except Exception:
                result["statuses"][sym]="UNKNOWN_SECONDARY_ENGINE_OR_PROVIDER"
        del raw
    need(set(result["statuses"])==set(names),
         "EXACT_ALL_PENDING_STATUS_PARTITION")
    result["counts"]=dict(sorted(collections.Counter(
        result["statuses"].values()).items()))
    return result

def selftest():
    from current_history_source_request import expected_dates
    dates,weeks=expected_dates("2026-10-13")
    from zoneinfo import ZoneInfo
    def midnight_et_utc(day):
        t=dt.datetime.combine(dt.date.fromisoformat(day),dt.time(),
                              ZoneInfo("America/New_York"))
        return t.astimezone(dt.timezone.utc).isoformat()
    bars=[{"t":midnight_et_utc(day),"o":10,"h":11,
           "l":9,"c":10.5,"v":100} for day in dates]
    valid,status=quality(bars,dates,weeks,"2026-10-13")
    need(valid is not None and len(valid)==260,"FULL_260_HISTORY")
    bad=[dict(x) for x in bars];bad[0]["v"]=0.5
    x,error=quality(bad,dates,weeks,"2026-10-13")
    need(x is None and error=="UNKNOWN_NONINTEGER_VOLUME",
         "FRACTIONAL_VOLUME_NOT_PROMOTED")
    bad=[dict(x) for x in bars];bad.pop()
    x,error=quality(bad,dates,weeks,"2026-10-13")
    need(x is None and error=="MISSING_EXACT_COMPLETED_SESSIONS",
         "MISSING_DATE_NOT_PROMOTED")
    # Artificial 2x gap must stay UNKNOWN until issuer-event evidence
    # separately reconciles it, regardless of syntactically valid OHLCV.
    suspect=[dict(row) for row in bars]
    for i in range(130,len(suspect)):
        for k in ("o","h","l","c"):
            suspect[i][k]=suspect[i][k]*2.0
    unresolved,reason=quality(suspect,dates,weeks,"2026-10-13")
    need(unresolved is not None and reason=="UNKNOWN_CORPORATE_ACTION_PIT",
         "MECHANICAL_GAP_CANNOT_SKIP_CA_PIT")
    samples=["SYM%03d"%i for i in range(120)]
    groups=chunks(samples)
    need(len(groups)==10 and [s for group in groups for s in group]==samples,
         "NO_TOP_N_OR_GLOBAL_11_CEILING")
    print("XRAY_PERSONAL_TECH_SELFTEST=PASS_ALL_120_NO_TRUNCATION_SPLIT_PIT_3_NEGATIVES_NO_R92")
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out",type=Path)
    opts=parser.parse_args()
    if opts.selftest:return selftest()
    need(opts.out is not None and not opts.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "NO_PUBLIC_VENDOR_DERIVED_ARTIFACT")
    key=os.getenv("XRAY_ALPACA_DATA_KEY_ID") or os.getenv("XRAY_ALPACA_API_KEY_ID")
    secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or os.getenv("XRAY_ALPACA_API_SECRET_KEY")
    need(bool(key and secret),"NO_RUNNER_KEYS")
    r=run(dt.datetime.now(dt.timezone.utc),lambda scope,start,end,asof:
       request_batch(scope,start,end,key,secret,adjustment="raw",asof=asof))
    opts.out.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n")
    print("XRAY_PERSONAL_SEVEN_TECH_COUNTS="+json.dumps(r["counts"],sort_keys=True))
    print("XRAY_PERSONAL_SEVEN_TECH_STATUSES="+json.dumps(r["statuses"],sort_keys=True))
    print("XRAY_PERSONAL_SEVEN_CANONICAL_AL_R92=0")
if __name__=="__main__":main()
