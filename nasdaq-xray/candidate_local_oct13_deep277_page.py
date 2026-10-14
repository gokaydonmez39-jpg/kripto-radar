#!/usr/bin/env python3
"""Actual Oct13 A/B/D and R1/RR, bounded to a real Stage1 28-symbol page.

An individual symbol's external unknown never blocks other symbols;
only its OWN 260/52, corporate actions, setup, QQQ regime, risk and source
evidence applies. Neither source coverage nor setup research implies R92.
"""
import argparse,collections,hashlib,json,os,time,urllib.error
from pathlib import Path
import candidate_local_oct13_stage1_277_remaining as pipeline
import candidate_local_oct13_deep7_r1rr_shadow as deep7

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
STAGE1_SCHEMA="XRAY_20261013_277_STAGE1_SIP_PAGE_RESEARCH_V1"
def require(ok,code):
    if not ok:raise ValueError("XRAY_LOCAL_DEEP277_"+code)
def sha(b):return hashlib.sha256(b).hexdigest()

def scope(source_path,stage_path,index):
    names=pipeline.scoped_symbols(source_path,index)
    raw=stage_path.read_bytes()
    doc=json.loads(raw)
    require(doc.get("schema")==STAGE1_SCHEMA and doc.get("asof_et")==ASOF
            and doc.get("page")==index and doc.get("source_277_json_sha256")==pipeline.SOURCE_SHA
            and doc.get("target_symbols")==names
            and set(doc["status_by_symbol"])==set(names)
            and doc.get("r92_registered")==0 and doc.get("execution")=="NONE"
            and doc.get("real_money")=="NO-GO",
            "STAGE1_EXACT_SOURCE_NOT_SAME_SYMBOL")
    pools=sorted(s for s in names if
                 doc["status_by_symbol"][s].get("status")=="STAGE1_RESEARCH_POOL_ONLY")
    return names,pools,sha(raw)

def selftest():
    require(len(pipeline.base.exact260())==260,"EXACT_260")
    require(9*28+25==277,"SOURCE_PAGE_PARTITION")
    require(deep7.eval_one("AAPL",None,None,{})["status"]=="UNKNOWN_HISTORY_260_INCOMPLETE",
            "BAD_HISTORY_NOT_TRIGGER")
    print("XRAY_LOCAL_DEEP277_SELFTEST=PASS_UNKNOWN_NO_A_B_D_TRIGGER")

def run(index,source,stage,out):
    require(out and not out.resolve().is_relative_to(ROOT.parent.resolve()),
            "NO_RAW_VENDOR_EXPORT")
    names,pools,stage_sha=scope(source,stage,index)
    report={
      "schema":"XRAY_20261013_LOCAL_277_DEEP_ABD_R1RR_PAGE_SHADOW_V1",
      "asof_et":ASOF,"page":index,"source_277_json_sha256":pipeline.SOURCE_SHA,
      "stage1_page_sha256":stage_sha,
      "source_page_scope":names,"stage1_real_pool_symbols":pools,
      "stage1_pool_count":len(pools),"evaluations":{},"counts":{},
      "qqq_260_source_valid":False,"actual_sip_http_calls":0,
      "confirmed_A_B_D_recent_triggers":0,"frozen_R1_RR_evaluated":0,
      "source_vendor":"ALPACA_HISTORICAL_SIP",
      "raw_ohlcv_exported":False,"other_global_unknown_blocks_local":False,
      "official_nasdaq_halt_safety_asof_verified":False,
      "issuer_sec_events_legal_asof_verified":False,
      "issuer_share_class_mc_primary_asof_verified":False,
      "r92_registered":0,"iphone_receipt_verified":False,
      "canonical_mutated":False,"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    def save():
        report["counts"]=dict(sorted(collections.Counter(
           r["status"] for r in report["evaluations"].values()).items()))
        report["confirmed_A_B_D_recent_triggers"]=sum(
           r.get("confirmed_recent_triggers",0) for r in report["evaluations"].values())
        report["frozen_R1_RR_evaluated"]=sum(
           r.get("r1_rr_evaluated",0) for r in report["evaluations"].values())
        out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    save()
    if not pools:
        print("XRAY_LOCAL_DEEP277_PAGE="+str(index)+"_NO_STAGE1_POOLS")
        return
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or
         os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or
            os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    require(key and secret,"RUNNER_SIP_KEY_UNAVAILABLE")
    dates=pipeline.base.exact260()
    report["actual_sip_http_calls"]+=1
    try:
        qqq=deep7.build_df("QQQ",(key,secret),dates)
        require(qqq is not None and deep7.quality(qqq,dates),"QQQ_REAL_260")
        report["qqq_260_source_valid"]=True
    except (urllib.error.HTTPError,urllib.error.URLError,ValueError,TypeError,TimeoutError):
        for sym in pools:
            report["evaluations"][sym]={"status":"UNKNOWN_QQQ_BENCHMARK_260"}
        save()
        return
    weekly=pipeline.base.stage.build_week_last(ASOF)
    for sym in pools:
        report["actual_sip_http_calls"]+=1
        try:
            bars=deep7.build_df(sym,(key,secret),dates)
            report["evaluations"][sym]=deep7.eval_one(sym,bars,qqq,weekly)
        except urllib.error.HTTPError as ex:
            report["evaluations"][sym]={"status":"UNKNOWN_PROVIDER_HTTP_"+str(ex.code)}
            if ex.code==429:
                report["provider_stop"]="FAIR_ACCESS_RATE_LIMIT"
                save()
                break
        except (urllib.error.URLError,ValueError,KeyError,TypeError,
                TimeoutError,RuntimeError,IndexError,OverflowError):
            report["evaluations"][sym]={"status":"UNKNOWN_DEEP_SOURCE_OR_GEOMETRY"}
        save()
        time.sleep(.65)
    for sym in pools:
        report["evaluations"].setdefault(sym,
              {"status":"UNKNOWN_NOT_ATTEMPTED_AFTER_PROVIDER_STOP"})
    save()
    require(set(report["evaluations"])==set(pools)
            and sum(report["counts"].values())==len(pools),
            "NO_POOL_LOSS")
    print("XRAY_LOCAL_DEEP277_PAGE="+str(index))
    print("XRAY_LOCAL_DEEP277_ACTUAL_HTTP="+str(report["actual_sip_http_calls"]))
    print("XRAY_LOCAL_DEEP277_CONFIRMED_ABD_TRIGGERS="+str(report["confirmed_A_B_D_recent_triggers"]))
    print("XRAY_LOCAL_DEEP277_R1RR_EVALUATED="+str(report["frozen_R1_RR_evaluated"]))
    print("XRAY_LOCAL_DEEP277_NO_FALSE_R92=PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--page",type=int)
    ap.add_argument("--source",type=Path)
    ap.add_argument("--stage1",type=Path)
    ap.add_argument("--out",type=Path)
    a=ap.parse_args()
    if a.selftest:selftest();return
    require(a.page is not None and a.source and a.stage1 and a.out,"CLI")
    run(a.page,a.source,a.stage1,a.out)
if __name__=="__main__":main()
