#!/usr/bin/env python3
"""One 50-name, candidate-local SEC PIT source census (zero MC promotion)."""
from __future__ import annotations
import argparse,collections,json,os,time,hashlib
from pathlib import Path
import sec_official_free_mc_transport_probe as sec
from sec_free_mc_multisymbol_pit_audit import map_ciks
from candidate_local_sec_pit_8_producer import source_check
ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
PAGE_SIZE=50
def require(ok,why):
    if not ok:raise ValueError("XRAY_LOCAL_SEC50_"+why)
def page(c,i):
    source_check(c)
    names=sorted(c["candidate_symbols"])
    require(len(names)==404 and names==sorted(set(names)),"SOURCE_SET")
    require(type(i) is int and 0<=i<=8,"PAGE_RANGE")
    return names[i*PAGE_SIZE:(i+1)*PAGE_SIZE]
def selftest():
    names=sorted(["AAPL","MSFT","NVDA","AAON","AMD","AMZN","GOOGL","META"]+[f"T{n:04d}" for n in range(396)])
    c={"schema":"XRAY_CANDIDATE_LOCAL_404_20261013_SOURCE_GATED_V1",
       "cohort_size":404,"candidate_symbols":names,
       "r92_registered":0,"cross_asof_shadow_only":True,
       "execution":"NONE","real_money":"NO-GO"}
    require(len(page(c,0))==50 and len(page(c,8))==4,"PAGE_BOUNDARIES")
    require(sum(len(page(c,i)) for i in range(9))==404,"ALL_404_PARTITION")
    require(len(set(s for i in range(9) for s in page(c,i)))==404,
            "NO_DOUBLE_COUNT")
    for i in (-1,9):
        try:page(c,i)
        except ValueError:pass
        else:raise AssertionError("INVALID_PAGE_ACCEPTED")
    print("XRAY_LOCAL_SEC50_SELFTEST=PASS_EXACT_404_9_DISJOINT_BATCHES")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--cohort",type=Path)
    p.add_argument("--page",type=int,default=0)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:selftest();return
    require(a.cohort and a.out and
            not a.out.resolve().is_relative_to(ROOT.parent.resolve()),"ARGS")
    raw=a.cohort.read_bytes()
    symbols=page(json.loads(raw),a.page)
    user_agent=(os.getenv("XRAY_SEC_USER_AGENT") or "").strip()
    require(sec.valid_operator_contact(user_agent),"SEC_CONTACT")
    result={"schema":"XRAY_CANDIDATE_LOCAL_SEC50_SOURCE_VINTAGES_V1",
            "asof_et":ASOF,"page":a.page,"symbols_requested":symbols,
            "requested_count":len(symbols),"statuses":{},
            "api_calls":0,"source_cohort_sha256":hashlib.sha256(raw).hexdigest(),
            "status_counts":{},"global_unknown_veto":False,
            "primary_price_verified":False,"primary_mc_approved":0,
            "canonical_modified":False,"r92_registered":0,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    def persist():
        result["status_counts"]=dict(sorted(collections.Counter(result["statuses"].values()).items()))
        a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    persist()
    try:
        ticker_map=map_ciks(sec.get_json(
            "https://www.sec.gov/files/company_tickers_exchange.json",user_agent))
        result["api_calls"]+=1
    except ValueError:
        result["transport"]="SEC_TICKER_INDEX_BLOCKED"
        result["statuses"]={s:"UNKNOWN_NO_SEC_INDEX" for s in symbols}
        persist()
        return
    result["transport"]="SEC_TICKER_INDEX_OK"
    for n,sym in enumerate(symbols):
        cik=ticker_map.get(sym)
        if not cik:
            result["statuses"][sym]="UNKNOWN_EXACT_CIK_ROUTE"
            persist();continue
        try:
            facts=sec.get_json("https://data.sec.gov/api/xbrl/companyfacts/CIK"+cik+".json",user_agent)
            result["api_calls"]+=1
            time.sleep(.65)
            subs=sec.get_json("https://data.sec.gov/submissions/CIK"+cik+".json",user_agent)
            result["api_calls"]+=1
            state=sec.select_shares(facts,subs,ASOF,expected_cik=cik)
            result["statuses"][sym]=state.get("status","UNKNOWN")
        except ValueError as err:
            msg=str(err)
            result["statuses"][sym]="UNKNOWN_SEC_TRANSPORT"
            if "HTTP_403" in msg or "HTTP_429" in msg:
                result["transport"]="SEC_FAIR_ACCESS_STOP_NO_RETRY"
                for rest in symbols[n+1:]:
                    result["statuses"][rest]="UNKNOWN_UNATTEMPTED_SEC_STOP"
                persist();break
        persist()
        time.sleep(.65)
    for s in symbols:
        result["statuses"].setdefault(s,"UNKNOWN_NOT_ATTEMPTED")
    persist()
    require(len(result["statuses"])==len(symbols),"SCOPE_LOSS")
    print("XRAY_LOCAL_SEC50_PAGE="+str(a.page))
    print("XRAY_LOCAL_SEC50_REAL_HTTP="+str(result["api_calls"]))
    print("XRAY_LOCAL_SEC50_COUNTS="+json.dumps(result["status_counts"],sort_keys=True))
    print("XRAY_LOCAL_SEC50_NO_MC_PRIMARY_R92=PASS")
if __name__=="__main__":main()
