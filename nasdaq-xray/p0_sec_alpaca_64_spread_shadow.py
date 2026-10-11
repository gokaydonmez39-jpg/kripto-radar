#!/usr/bin/env python3
"""64 deterministically spread current PRICE-pass NASDAQ symbols: free SEC MC.

Official current Nasdaq SEC ticker-CIK route; filing acceptance/PIT issuer
shares; one completed Alpaca historical SIP raw close. All evidence remains
research-only: issuer shares != listed-class shares, CA and post-filing
issuance not PIT attested, independent market cap absent, no C4.17 PRIMARY,
HISTORY, AL, R92, GO or money execution. No raw vendor OHLCV or share counts
are retained or written to public GitHub artifacts.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,json,os,time
from pathlib import Path
from alpaca_full_scope_260_shadow import scope,PRICE,MASTER
from alpaca_free_sip_shadow_guard import request_batch,blob_sha,sufficient_delay
from sec_free_mc_multisymbol_pit_audit import SEC_MAP,map_ciks
from sec_official_free_mc_transport_probe import get_json,valid_operator_contact
from p0_sec_alpaca_personal_mc_canary import measure

HERE=Path(__file__).resolve().parent
SCHEMA="XRAY_PERSONAL_SEC_ALPACA_64_DISTRIBUTED_MC_SHADOW_V1"
N=64
SEC_GAP_SECONDS=0.65
SUCCESS="SHADOW_SEC_PIT_AND_SIP_CLOSE_ARITHMETIC_VERIFIED_CLASS_CA_UNPROVEN"

def require(ok,label):
    if not ok:raise ValueError("XRAY_PERSONAL_MC_64:"+label)

def spread(price,master,sec_map):
    asof,targets,daily,weeks=scope(price,master)
    stocks=price["pass_symbols"]
    require(len(stocks)>=N and "QQQ" not in stocks,"SMALL_OR_WRONG_COHORT")
    picks=[stocks[(i*(len(stocks)-1))//(N-1)] for i in range(N)]
    require(len(picks)==len(set(picks))==N and picks==sorted(picks),
            "NONDETERMINISTIC_SAMPLE")
    require(isinstance(sec_map,dict),"OFFICIAL_CIK_ROUTE_NOT_DICT")
    routes={}
    missing=[]
    for sym in picks:
        cik=sec_map.get(sym)
        if isinstance(cik,str) and len(cik)==10 and cik.isdigit():
            routes[sym]=cik
        else:
            missing.append(sym)
    require(len(routes)+len(missing)==N,"SEC_MAP_PARTITION_GAP")
    return asof,picks,routes,missing

def shard_price_scope(price,master,sec_map,shard):
    """Bound all current PRICE symbols to exactly four disjoint slices."""
    from current_history_source_request import sha256_lines
    require(type(shard) is int and 0<=shard<4,"INVALID_FULL_SCOPE_SHARD")
    asof=price.get("asof_et")
    all_symbols=price.get("pass_symbols")
    master_symbols=master.get("pass_symbols")
    require(asof=="2026-10-09" and master.get("asof_et")==asof
            and type(all_symbols) is list and
            all_symbols==sorted(set(all_symbols))
            and len(all_symbols)==price.get("pass_count")==514
            and sha256_lines(all_symbols)==price.get("pass_hash")
            and type(master_symbols) is list and
            set(all_symbols).issubset(set(master_symbols))
            and all(x.get("unknown_never_pass") is True and
                    x.get("execution")=="NONE" and
                    x.get("real_money")=="NO-GO"
                    for x in (price,master)),
            "FULL_PRICE_SCOPE_IDENTITY_OR_SAFETY_UNVERIFIED")
    partitions=[all_symbols[i::4] for i in range(4)]
    require(sorted(map(len,partitions))==[128,128,129,129]
            and len(set().union(*(set(x) for x in partitions)))==514
            and sum(map(len,partitions))==514,
            "FULL_514_SHARD_UNION_NOT_EXACT")
    picks=partitions[shard]
    routes={t:sec_map[t] for t in picks if
            isinstance(sec_map.get(t),str) and len(sec_map[t])==10 and
            sec_map[t].isdigit()}
    missing=[t for t in picks if t not in routes]
    return asof,picks,routes,missing

def classify(price,master,asof,picks,routes,missing,sip_fetch,sec_fetch,*,expected_count=N):
    outcome={sym:{"status":"UNKNOWN_OFFICIAL_CIK_MAPPING",
                  "above_2b_derived_issuer_shadow":None,
                  "C417_PRIMARY":False} for sym in missing}
    bars={}
    batches=0
    for i in range(0,len(routes),32):
        group=sorted(routes)[i:i+32]
        try:
            batch=sip_fetch(group,asof)
            require(isinstance(batch,dict) and not(set(batch)-set(group)),
                    "ALPACA_SCOPE_MISMATCH")
            for sym in group:
                bars[sym]=batch.get(sym,[])
        except (ValueError,RuntimeError,TimeoutError,TypeError):
            for sym in group:
                bars[sym]=None
        batches+=1
    halted=False
    attempted=0
    for sym,cik in sorted(routes.items()):
        if halted:
            outcome[sym]={"status":"UNKNOWN_SEC_FAIR_ACCESS_STOP",
                          "above_2b_derived_issuer_shadow":None,"C417_PRIMARY":False}
            continue
        if bars.get(sym) is None:
            outcome[sym]={"status":"UNKNOWN_ALPACA_SIP_TRANSPORT",
                          "above_2b_derived_issuer_shadow":None,"C417_PRIMARY":False}
            continue
        try:
            facts,sub=sec_fetch(sym,cik)
            attempted+=1
            x=measure(price,master,facts,sub,bars[sym],asof,symbol=sym,cik=cik)
            require(x["C417_PRIMARY_MC"] is False and x["GO"] is False
                    and x["numeric_shares_price_or_marketcap_persisted"] is False,
                    "IMPROPER_PRIMARY_SINGLE_RESULT")
            outcome[sym]={"status":x["status"],
                          "above_2b_derived_issuer_shadow":x["calculated_MC_above_2B_unadjusted"],
                          "sec_vintage_age_days":x["SEC_share_age_days"],
                          "C417_PRIMARY":False}
        except (ValueError,RuntimeError,KeyError,TypeError) as exc:
            code=str(exc)
            if "SEC_HTTP_429" in code or "SEC_HTTP_403" in code:
                halted=True
            outcome[sym]={"status":("UNKNOWN_SEC_FAIR_ACCESS_STOP" if halted else
                                   "UNKNOWN_SEC_DIMENSIONAL_CLASS_OR_PIT_SHARES"),
                          "above_2b_derived_issuer_shadow":None,
                          "C417_PRIMARY":False}
    require(set(outcome)==set(picks) and len(outcome)==expected_count and expected_count==len(picks),"SAMPLE_UNRESOLVED_SET")
    counts=collections.Counter(x["status"] for x in outcome.values())
    return {"schema":SCHEMA,"asof_et":asof,
            "sampling":"64_EVENLY_SPACED_LEXICOGRAPHIC_CURRENT_PRICE_PASS",
            "source_price_pass_count":price["pass_count"],
            "sampled_count":expected_count,"sampled_symbols":picks,
            "matched_official_SEC_CIK":len(routes),
            "unmatched_official_SEC_CIK":len(missing),
            "attempted_SEC_issuer_requests":attempted,
            "SIP_multi_ticker_batches":batches,
            "official_SEC_fair_access_halted":halted,
            "outcomes":outcome,"status_counts":dict(sorted(counts.items())),
            "status":"SHADOW_64_SYMBOLS_EXACT_ACCOUNTING_NO_MC_PRIMARY",
            "price_source_git_blob_sha":blob_sha(PRICE),
            "master_source_git_blob_sha":blob_sha(MASTER),
            "ticker_symbol_mapping_asof_et":asof,
            "licensed_non_display_and_reuse_rights_attested":False,
            "independent_issuer_mc_crosscheck":False,
            "stock_class_CUSIP_issuer_CA_reconciled":False,
            "raw_vendor_OHLCV_SEC_share_counts_archived":False,
            "production_C417_PRIMARY_MC_created":0,
            "production_HISTORY_PASS_created":0,
            "AL_R92_created":False,"GO":False,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def selftest():
    from copy import deepcopy
    from current_history_source_request import sha256_lines
    asof="2026-10-09"
    stocks=[f"TEST{i:04d}" for i in range(130)]
    p={"asof_et":asof,"pass_symbols":stocks,"pass_count":len(stocks),
       "pass_hash":sha256_lines(stocks),"execution":"NONE",
       "real_money":"NO-GO","unknown_never_pass":True}
    m={"asof_et":asof,"pass_symbols":stocks,
       "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    cmap={sym:f"{10000+i:010d}" for i,sym in enumerate(stocks)}
    d,picks,routes,missing=spread(p,m,cmap)
    require(d==asof and len(picks)==64 and not missing and len(routes)==64,
            "POSITIVE_SPREAD_64")
    mm=deepcopy(cmap);mm.pop(picks[1]);mm.pop(picks[3])
    _,picks2,routes2,missing2=spread(p,m,mm)
    require(picks2==picks and len(missing2)==2 and len(routes2)==62,
            "MISSING_CIK_STAYS_MISSING")
    def deny(name,fn):
        try:fn()
        except (ValueError,RuntimeError):return
        raise AssertionError("SEC_64_SCOPE_FALSE_ACCEPT:"+name)
    pp=deepcopy(p);pp["pass_hash"]="0"*64
    deny("PRICE_HASH",lambda:spread(pp,m,cmap))
    pp=deepcopy(p);pp["execution"]="TRADE"
    deny("EXECUTION",lambda:spread(pp,m,cmap))
    pp=deepcopy(p);pp["asof_et"]="2026-10-08"
    deny("PRICE_ASOF",lambda:spread(pp,m,cmap))
    mm2=deepcopy(m);mm2["pass_symbols"]=[]
    deny("MASTER_SET",lambda:spread(p,mm2,cmap))
    pp=deepcopy(p);pp["pass_symbols"]=stocks[:40];pp["pass_count"]=40
    pp["pass_hash"]=sha256_lines(pp["pass_symbols"])
    deny("UNDER_MIN_64",lambda:spread(pp,m,cmap))
    # The SEC+SIP transport cannot produce PASS from invented remote values.
    def fail_source(sym,cik):
        raise ValueError("UNKNOWN_NO_OFFICIAL_SEC")
    fake=classify(p,m,asof,picks,routes,missing,
                  lambda batch,day:{sym:[] for sym in batch},
                  fail_source)
    require(fake["sampled_count"]==64 and
            fake["production_C417_PRIMARY_MC_created"]==0
            and fake["status_counts"]["UNKNOWN_SEC_DIMENSIONAL_CLASS_OR_PIT_SHARES"]==64,
            "ALL_UNKNOWN_STAYS_UNKNOWN")
    whole=sorted(f"TEST{i:04d}" for i in range(514))
    big=dict(p,pass_symbols=whole,pass_count=514,
             pass_hash=sha256_lines(whole))
    allmap={sym:f"{2000+i:010d}" for i,sym in enumerate(whole)}
    allshards=[shard_price_scope(big,dict(m,pass_symbols=whole),allmap,k)[1]
               for k in range(4)]
    require(sorted(map(len,allshards))==[128,128,129,129]
            and set().union(*(set(x) for x in allshards))==set(whole),
            "FULL_514_DISJOINT_PARTITION_SELFTEST")
    badbig=deepcopy(big);badbig["pass_hash"]="0"*64
    deny("FULL_514_HASH_CHANGED",lambda:
         shard_price_scope(badbig,dict(m,pass_symbols=whole),allmap,0))
    print("XRAY_PERSONAL_MC_64_COHORT_SELFTEST=PASS_4_POSITIVE_6_NEGATIVE_PYTHON_O_SAFE_NO_PRIMARY")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    ap.add_argument("--full-shard",type=int,choices=[0,1,2,3])
    args=ap.parse_args()
    if args.selftest:return selftest()
    require(args.out is not None,"EXPLICIT_OUTPUT_PATH_REQUIRED")
    price=json.loads(PRICE.read_text());master=json.loads(MASTER.read_text())
    asof=price["asof_et"]
    key=os.getenv("XRAY_ALPACA_DATA_KEY_ID","")
    secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY","")
    ua=os.getenv("XRAY_SEC_USER_AGENT","")
    require(valid_operator_contact(ua) and key and secret,
            "PERSONAL_FREE_API_OR_SEC_OFFICIAL_OPERATOR_MISSING")
    require(sufficient_delay(asof,dt.datetime.now(dt.timezone.utc)),
            "SIP_HOLDBACK_BEFORE_ASOF_CLOSE")
    mapped=map_ciks(get_json(SEC_MAP,ua))
    asof,picks,routes,missing=(spread(price,master,mapped) if args.full_shard is None
              else shard_price_scope(price,master,mapped,args.full_shard))
    nextday=(dt.date.fromisoformat(asof)+dt.timedelta(days=1)).isoformat()
    last_call=[0.0]
    def sec_fetch(sym,cik):
        objects=[]
        for url in (f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                    f"https://data.sec.gov/submissions/CIK{cik}.json"):
            remaining=SEC_GAP_SECONDS-(time.monotonic()-last_call[0])
            if remaining>0:time.sleep(remaining)
            last_call[0]=time.monotonic()
            objects.append(get_json(url,ua))
        return tuple(objects)
    def sip_fetch(symbols,stamp):
        return request_batch(symbols,stamp+"T00:00:00Z",
                             nextday+"T00:00:00Z",key,secret,
                             adjustment="raw",asof=stamp)
    result=classify(price,master,asof,picks,routes,missing,sip_fetch,sec_fetch,
                    expected_count=len(picks))
    if args.full_shard is not None:
        result["schema"]="XRAY_PERSONAL_SEC_ALPACA_FULL_514_MC_FOUR_SHARD_SHADOW_V1"
        result["status"]="SHADOW_EXACT_FULL_514_PARTIAL_SHARD_NO_PRIMARY"
        result["sampling"]="FULL_514_EXACT_UNION_FOUR_SHARDS"
        result["shard"]=args.full_shard
        result["shard_total"]=4
        result["source_scope_pass_count"]=price["pass_count"]
        result["full_514_PRIMARY_claim"]=False
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_PERSONAL_MC_64_STATUS="+result["status"])
    print("XRAY_PERSONAL_MC_64_COUNTS="+json.dumps(result["status_counts"],sort_keys=True))
    print("XRAY_PERSONAL_MC_64_PRIMARY=0_NOT_C417")

if __name__=="__main__":main()
