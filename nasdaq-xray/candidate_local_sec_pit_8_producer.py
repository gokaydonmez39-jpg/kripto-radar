#!/usr/bin/env python3
"""Eight candidate-local SEC filing vintages; no universe MC/global-UNKNOWN veto."""
from __future__ import annotations
import argparse,collections,hashlib,json,os,time
from pathlib import Path
import sec_official_free_mc_transport_probe as sec
from sec_free_mc_multisymbol_pit_audit import map_ciks

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
CANARIES=("AAPL","MSFT","NVDA","AAON","AMD","AMZN","GOOGL","META")
MAP_URL="https://www.sec.gov/files/company_tickers_exchange.json"

def need(value,msg):
    if not value: raise ValueError("XRAY_LOCAL_SEC8_"+msg)

def source_check(cohort):
    need(cohort.get("schema")=="XRAY_CANDIDATE_LOCAL_404_20261013_SOURCE_GATED_V1"
         and cohort.get("cohort_size")==404,"PROVEN_404")
    syms=set(cohort["candidate_symbols"])
    need(set(CANARIES).issubset(syms),"REAL_COHORT_CANARIES")
    need(cohort["r92_registered"]==0 and cohort["cross_asof_shadow_only"]
         and cohort["execution"]=="NONE" and cohort["real_money"]=="NO-GO",
         "READ_ONLY_SOURCE")
    return True

def selftest():
    x={"schema":"XRAY_CANDIDATE_LOCAL_404_20261013_SOURCE_GATED_V1",
       "cohort_size":404,"candidate_symbols":list(CANARIES),
       "r92_registered":0,"cross_asof_shadow_only":True,
       "execution":"NONE","real_money":"NO-GO"}
    need(source_check(x),"COHORT_POSITIVE")
    for field,bad in (("cohort_size",403),("r92_registered",1),
                      ("cross_asof_shadow_only",False),
                      ("execution","TRADE")):
        c=dict(x);c[field]=bad
        try:source_check(c)
        except ValueError:pass
        else:raise AssertionError("NEGATIVE_ACCEPTED_"+field)
    print("XRAY_LOCAL_SEC8_SELFTEST=PASS_COHORT_GATES_NO_MC_PRIMARY")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--cohort",type=Path)
    ap.add_argument("--out",type=Path)
    a=ap.parse_args()
    if a.selftest:selftest();return
    need(a.cohort and a.out and not
         a.out.resolve().is_relative_to(ROOT.parent.resolve()),"ARGS")
    raw=a.cohort.read_bytes()
    source_check(json.loads(raw))
    ua=(os.getenv("XRAY_SEC_USER_AGENT") or "").strip()
    need(sec.valid_operator_contact(ua),"SEC_CONTACT_REQUIRED")
    result={"schema":"XRAY_CANDIDATE_LOCAL_SEC8_OCT13_REAL_PIT_SHADOW_V1",
       "asof_et":ASOF,"input_cohort_sha256":hashlib.sha256(raw).hexdigest(),
       "source_cohort_count":404,"exact_canaries":list(CANARIES),
       "http_calls":0,"results":{},"class_counts":{},
       "global_unknown_not_a_veto":True,
       "issuer_cik_current_not_historical_pit":True,
       "price_c417_primary_13oct_attested":False,
       "class_corporate_action_pit_reconciled":False,
       "issuer_mc_primary_count":0,
       "canonical_changed":False,"r92_registered":0,
       "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    def save():
        result["class_counts"]=dict(sorted(collections.Counter(
            v.get("status","UNKNOWN") for v in result["results"].values()).items()))
        a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    save()
    try:
        mapped=map_ciks(sec.get_json(MAP_URL,ua))
        result["http_calls"]+=1
    except ValueError as err:
        result["transport"]="SEC_OFFICIAL_INDEX_UNAVAILABLE"
        save()
        print("XRAY_LOCAL_SEC8_INDEX_BLOCKED_FAIL_CLOSED")
        return
    result["transport"]="SEC_OFFICIAL_INDEX_AVAILABLE"
    for sym in CANARIES:
        cik=mapped.get(sym)
        row={"status":"UNKNOWN_OFFICIAL_CIK_ROUTE" if not cik else
             "UNKNOWN_OFFICIAL_SEC_PIT_PENDING",
             "cik_route_matched":bool(cik)}
        result["results"][sym]=row
        if cik:
            try:
                facts=sec.get_json("https://data.sec.gov/api/xbrl/companyfacts/CIK"+cik+".json",ua)
                result["http_calls"]+=1;time.sleep(.6)
                sub=sec.get_json("https://data.sec.gov/submissions/CIK"+cik+".json",ua)
                result["http_calls"]+=1
                answer=sec.select_shares(facts,sub,ASOF,expected_cik=cik)
                row["status"]=answer.get("status","UNKNOWN")
                row["reason"]=answer.get("reason","UNKNOWN_SOURCE_REASON")
                row["shares_filing_date"]=answer.get("selected_filing_date")
                row["source_acceptance_bound"]=bool(answer.get("accession_present"))
                row["raw_shares_not_emitted"]=True
            except ValueError as err:
                reason=str(err)
                row["status"]="UNKNOWN_SEC_TRANSPORT"
                row["reason"]="FAIR_ACCESS_STOP" if ("403" in reason or "429" in reason) else "OFFICIAL_SOURCE_UNAVAILABLE"
                if row["reason"]=="FAIR_ACCESS_STOP":
                    result["transport"]="FAIR_ACCESS_STOP_NO_BYPASS"
                    save();break
        save();time.sleep(.6)
    for sym in CANARIES:
        result["results"].setdefault(sym,{"status":"UNKNOWN_NOT_ATTEMPTED_UPSTREAM_BLOCK"})
    save()
    need(len(result["results"])==8 and sum(result["class_counts"].values())==8,
         "FULL_COHORT_AUDIT_PARTITION")
    print("XRAY_LOCAL_SEC8_TRUE_OFFICIAL_HTTP_CALLS="+str(result["http_calls"]))
    print("XRAY_LOCAL_SEC8_RESULT_CLASSES="+json.dumps(result["class_counts"],sort_keys=True))
    print("XRAY_LOCAL_SEC8_MC_PRIMARY_0_R92_0_NO_GLOBAL_VETO=PASS")
if __name__=="__main__":main()
