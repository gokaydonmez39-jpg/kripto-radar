#!/usr/bin/env python3
"""C4.17 A/B/D + R1/RR source-bound research on 7 real SIP Stage1 pools.

No legal, event, issuer-class MC, or R92 authority. Uses actual Oct13 SIP
260-session daily OHLCV and QQQ, current week-at-trigger and existing alpha
functions. Raw source/levels are never exported to public GitHub.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,time,urllib.error
from pathlib import Path
import pandas as pd
import candidate_local_oct13_stage1_sip28_shadow as stage
import deep_pre_r1_shadow as deep
import final_tech_shadow as final

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
STAGE_SHA="114c04313f9763d485977a5b698986bef70363b2bbb613b7df31ad0c5597454d"
def need(value,msg):
    if not value:raise ValueError("XRAY_DEEP7_"+msg)
def select(path):
    b=path.read_bytes()
    need(hashlib.sha256(b).hexdigest()==STAGE_SHA,"FROZEN_STAGE1_SHA")
    x=json.loads(b)
    need(x.get("schema")=="XRAY_OCT13_28_REAL_SIP_260_STAGE1_RESEARCH_SHADOW_V1"
         and x.get("asof_et")==ASOF and x.get("r92_registered")==0
         and x.get("source_277_json_sha256")==stage.SOURCE_SHA,"STAGE1_SOURCE")
    syms=sorted(s for s,d in x["status_by_symbol"].items()
      if d.get("status")=="STAGE1_RESEARCH_POOL_ONLY")
    need(len(x["status_by_symbol"])==28 and len(syms)==7,"STAGE1_SEVEN")
    return syms

def quality(df,days):
    return (len(df)==260 and
            [x.date().isoformat() for x in df["date"]]==days and
            all(df[c].notna().all() and (df[c]>0).all() for c in
                ("open","high","low","close","volume")))

def build_df(symbol,keys,days):
    daily=stage.one(symbol,keys,days)
    if len(daily)!=260 or set(daily)!=set(days):
        return None
    return pd.DataFrame([daily[d] for d in days]).reset_index(drop=True)

def eval_one(sym,df,qqq,weekly):
    if df is None or not quality(df,stage.exact260()):
        return {"status":"UNKNOWN_HISTORY_260_INCOMPLETE"}
    if (stage.mechanical_scale_breaks(df,260) or
        stage.mechanical_split_suspects(df)):
        return {"status":"UNKNOWN_CORP_ACTION_ASOF_UNRESOLVED"}
    eligible,ctx=stage.stage.recent_weekly_context(df,weekly)
    if not eligible:
        return {"status":"WEEKLY_TRIGGER_CONTEXT_NOT_PASS","families":{}}
    a,b,d=deep.evaluate_recent_families(df,qqq,eligible)
    family={"A":a,"B":b,"D":d}
    results={}
    for label,g in family.items():
        row={"deep_pool":bool(g.get("pool")),
             "recent_trigger":bool(g.get("trigger_date")),
             "actual_deep_trigger_confirmed":bool(
                 g.get("trigger_date") and g.get("pool") and
                 (label!="D" or g.get("dk3_pre_r1") is True)),
             "final_evaluated":False}
        if row["actual_deep_trigger_confirmed"]:
            try:
                final_result=final.eval_one(sym,label,g,df,
                  event_status="UNKNOWN",state_cap="WATCH",
                  r92_eligible=False,regime_finalist_status="UNKNOWN")
                row.update({"final_evaluated":True,
                    "technical_result":final_result.get("result"),
                    "risk_geometry_pass":bool(final_result.get("risk_pass")),
                    "rr_basic_and_severe_pass":bool(
                        final_result.get("rr",{}).get("basic_pass") and
                        final_result.get("rr",{}).get("severe_pass")),
                    "local_event_clean_unproven":True,
                    "local_regime_pass_unproven":True,
                    "mc_would_be_watch_only":True})
            except (ValueError,TypeError,KeyError,IndexError,RuntimeError):
                row["technical_result"]="UNKNOWN_R1_RR_GEOMETRY"
        results[label]=row
    return {"status":"DEEP_RESEARCH_EVALUATED_NOT_RELEASE",
            "eligible_trigger_dates":len(eligible),
            "families":results,
            "confirmed_recent_triggers":sum(r["actual_deep_trigger_confirmed"]
                                            for r in results.values()),
            "r1_rr_evaluated":sum(r["final_evaluated"] for r in results.values())}

def selftest():
    dates=stage.exact260()
    need(len(dates)==260 and dates[-1]==ASOF,"CALENDAR")
    need(eval_one("AAPL",None,None,{})["status"]=="UNKNOWN_HISTORY_260_INCOMPLETE",
         "BAD_HISTORY_NEVER_SETUP")
    print("XRAY_DEEP7_SELFTEST=PASS_NO_FAKE_WEEKLY_OR_R1_RR")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--stage1",type=Path);ap.add_argument("--out",type=Path)
    arg=ap.parse_args()
    if arg.selftest:selftest();return
    need(arg.stage1 and arg.out and
         not arg.out.resolve().is_relative_to(ROOT.parent.resolve()),"OUTPUT")
    syms=select(arg.stage1)
    dates=stage.exact260()
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    need(key and secret,"CREDENTIALS")
    report={"schema":"XRAY_OCT13_7_TRUE_SIP_DEEP_ABD_R1RR_SHADOW_V1",
       "asof_et":ASOF,"source_stage1_json_sha256":STAGE_SHA,
       "symbols":syms,"rows":{},"counts":{},"provider_calls":0,
       "benchmark_qqq_asof_verified":False,
       "source":"ALPACA_HISTORICAL_SIP_GITHUB_RUNNER",
       "raw_market_data_persisted":False,
       "issuer_class_mc_primary_proven":False,
       "official_legal_event_halt_proven":False,
       "stage1_regime_breadth_primary_proven":False,
       "registered_r92_count":0,"real_iphone_receipt_proven":False,
       "canonical_mutated":False,"execution":"NONE","real_money":"NO-GO",
       "unknown_never_pass":True}
    def save():
        report["counts"]=dict(sorted(collections.Counter(
           x["status"] for x in report["rows"].values()).items()))
        arg.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    save()
    report["provider_calls"]+=1
    try:
        qqq=build_df("QQQ",(key,secret),dates)
        need(qqq is not None and quality(qqq,dates),"QQQ_260")
        report["benchmark_qqq_asof_verified"]=True
    except (ValueError,TypeError,urllib.error.URLError,TimeoutError):
        report["benchmark_transport"]="UNKNOWN_BENCHMARK_UNAVAILABLE"
        for sym in syms:report["rows"][sym]={"status":"UNKNOWN_QQQ_260_UNVERIFIED"}
        save()
        return
    week_last=stage.stage.build_week_last(ASOF)
    for sym in syms:
        report["provider_calls"]+=1
        try:
            df=build_df(sym,(key,secret),dates)
            report["rows"][sym]=eval_one(sym,df,qqq,week_last)
        except urllib.error.HTTPError as err:
            report["rows"][sym]={"status":"UNKNOWN_HTTP_"+str(err.code)}
            if err.code==429:
                report["stop_reason"]="RATE_LIMIT_STOP"
                save();break
        except (urllib.error.URLError,ValueError,TypeError,RuntimeError,KeyError,IndexError):
            report["rows"][sym]={"status":"UNKNOWN_DEEP_MODEL_OR_SOURCE"}
        save();time.sleep(.6)
    for sym in syms:
        report["rows"].setdefault(sym,{"status":"UNKNOWN_NOT_ATTEMPTED"})
    save()
    need(len(report["rows"])==7 and sum(report["counts"].values())==7,
         "FULL_7_DISJOINT")
    print("XRAY_DEEP7_REAL_SIP_HTTP="+str(report["provider_calls"]))
    print("XRAY_DEEP7_RESULTS="+json.dumps(report["counts"],sort_keys=True))
    print("XRAY_DEEP7_CONFIRMED_TRIGGER_COUNT="+str(sum(
        r.get("confirmed_recent_triggers",0) for r in report["rows"].values())))
    print("XRAY_DEEP7_NO_R92=PASS")
if __name__=="__main__":main()
