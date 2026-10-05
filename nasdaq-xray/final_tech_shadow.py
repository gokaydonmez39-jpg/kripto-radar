#!/usr/bin/env python3
"""XRAY fail-closed final technical shadow engine.
Consumes deep_pre_r1_shadow.json and applies common geometry/R1/RR/chase/extension.
Historical resistance is deliberately conservative: nearest ANY prior daily high above
trigger close, which can only reduce target space versus a looser R1 interpretation.
Synthetic P+3A is permitted only when trigger close is above every prior recorded high.
No signal, no G9 authority, no R92 registration.
"""
from __future__ import annotations
import json, math, os, hashlib, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import akshare as ak
import pandas as pd

ROOT=Path(__file__).resolve().parent
DEEP=Path(os.getenv("XRAY_FINAL_DEEP_STATE", str(ROOT/"deep_pre_r1_shadow.json")))
OUT=Path(os.getenv("XRAY_FINAL_OUT", str(ROOT/"final_tech_shadow.json")))
FAMILY_C_ENV=os.getenv("XRAY_FINAL_FAMILY_C_STATE")
FAMILY_C=Path(FAMILY_C_ENV) if FAMILY_C_ENV else None
TASK_ID="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_FINAL_WORKERS","6"))
PROVIDER_MAX_INFLIGHT=max(1,int(os.getenv("XRAY_FINAL_PROVIDER_MAX_INFLIGHT","3")))
RETRY_DELAYS=(0.0,1.0,2.5)
_PROVIDER_SEM=threading.Semaphore(PROVIDER_MAX_INFLIGHT)
OFFICIAL_IDENTITY_EVIDENCE=ROOT/"history_official_identity_evidence.json"

def _retryable(exc):
    s=str(exc).lower()
    return any(x in s for x in ("timed out","timeout","connection reset","remote end closed","too many requests","rate limit","429","500","502","503","504"))

def _call_with_retry(fn):
    last=None
    for delay in RETRY_DELAYS:
        if delay:time.sleep(delay)
        try:
            with _PROVIDER_SEM:return fn()
        except Exception as e:
            last=e
            if not _retryable(e):raise
    assert last is not None
    raise last

def _official_records():
    try:
        j=json.loads(OFFICIAL_IDENTITY_EVIDENCE.read_text())
        if j.get("schema")=="XRAY_HISTORY_OFFICIAL_IDENTITY_EVIDENCE_V1" and j.get("evidence_only") is True and j.get("alpha_authority") is False:
            return j.get("records") or {}
    except Exception:pass
    return {}

OFFICIAL_RECORDS=_official_records()

def _normalize_sina(df):
    if df is None or df.empty:return None
    cols={str(c).lower():c for c in df.columns};need=["date","high","low","close"]
    if any(k not in cols for k in need):return None
    x=df[[cols[k] for k in need]].copy();x.columns=need
    x["date"]=pd.to_datetime(x["date"],errors="coerce")
    for k in need[1:]:x[k]=pd.to_numeric(x[k],errors="coerce")
    return x.dropna().drop_duplicates("date",keep="last").sort_values("date")

def _sina_history(sym):return _normalize_sina(_call_with_retry(lambda:ak.stock_us_daily(symbol=sym,adjust="")))

def load_history(sym,asof):
    cur=_sina_history(sym);rec=OFFICIAL_RECORDS.get(sym) or {}
    if rec.get("mode")=="OFFICIAL_TICKER_CONTINUITY_COMPOSITE_HISTORY" and rec.get("cusip_unchanged") is True:
        pred=rec.get("predecessor_symbol");eff=rec.get("effective_date")
        if pred and eff and cur is not None:
            p=_sina_history(pred)
            if p is not None:
                eff_ts=pd.Timestamp(eff);asof_ts=pd.Timestamp(asof)
                cur2=cur[(cur["date"]>=eff_ts)&(cur["date"]<=asof_ts)];pred2=p[p["date"]<eff_ts]
                if not cur2.empty and cur2["date"].dt.date.max().isoformat()==asof:
                    return pd.concat([pred2,cur2],ignore_index=True).sort_values("date").drop_duplicates("date",keep="last").reset_index(drop=True),"SINA_OFFICIAL_TICKER_CONTINUITY_COMPOSITE"
    if cur is None:return None,"SINA_EMPTY"
    return cur[cur["date"]<=pd.Timestamp(asof)].reset_index(drop=True),"SINA_US_DAILY"
def blob_sha(p:Path):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def relpath(p:Path):
    try:return str(p.relative_to(ROOT.parent)).replace("\\","/")
    except Exception:return str(p)

THRESH={
 "A":{"basic":1.5,"severe":1.1},
 "B":{"basic":2.0,"severe":1.5},
 "C":{"basic":2.0,"severe":1.5},
 "D":{"basic":2.0,"severe":1.5},
}

def hist(sym,asof):
    try:
        x,src=load_history(sym,asof)
        if x is None or x.empty:return sym,None,"EMPTY",None
        last=x["date"].dt.date.max().isoformat()
        if last!=asof:return sym,None,f"ASOF_MISSING:{last}",None
        if len(x)<260:return sym,None,f"LT260:{len(x)}",None
        return sym,x,None,src
    except Exception as e:return sym,None,f"{type(e).__name__}:{str(e)[:160]}",None

def eval_one(sym,fam,g,df,event_status,state_cap="NORMAL",r92_eligible=True):
    A=float(g["A"]);P=float(g["P"]);anchor=float(g["anchor"])
    close=float(df.close.iloc[-1])
    if not all(math.isfinite(v) for v in [A,P,anchor,close]) or A<=0:
        return {"result":"UNKNOWN","reason":"NONFINITE_GEOMETRY"}

    entry_low=P
    entry_high=P+0.25*A
    entry_model=entry_high
    chase=P+0.50*A
    S0=anchor-0.20*A
    x=(P-anchor)/A
    risk_atr=(entry_model-S0)/A
    risk_pct=(entry_model-S0)/entry_model if entry_model>0 else float("inf")

    if close<P: lifecycle="RECONFIRMATION_REQUIRED"
    elif close<=entry_high: lifecycle="ENTRY_BAND"
    elif close<chase: lifecycle="RETEST_REQUIRED"
    else: lifecycle="CHASE_NO_VALID_FILL"

    pivot_extension=(close/P)-1 if P>0 else float("inf")
    recent3=df.iloc[-3:]
    move3=(close-float(recent3.low.min()))/A if len(recent3)==3 else 0
    extension_veto=bool(pivot_extension>=0.08 or move3>2.0)

    prior=df.iloc[:-1]
    highs=[float(v) for v in prior.high if math.isfinite(float(v)) and float(v)>close]
    nearest=min(highs) if highs else None
    prior_max=float(prior.high.max()) if len(prior) else float("nan")
    price_discovery=bool(math.isfinite(prior_max) and close>prior_max)

    synthetic=False
    if nearest is not None:
        T1=nearest
        target_source="CONSERVATIVE_NEAREST_PRIOR_DAILY_HIGH"
    elif price_discovery:
        T1=P+3*A
        synthetic=True
        target_source="SYNTHETIC_P_PLUS_3A_PRICE_DISCOVERY"
    else:
        return {
          "result":"UNKNOWN","reason":"R1_UNRESOLVED",
          "levels":{"A":A,"P":P,"anchor":anchor,"close":close}
        }

    def rr(cost_mult):
        cost=cost_mult*A
        E=entry_model+cost
        S=S0-cost
        T=T1-cost
        den=E-S
        return (T-E)/den if den>0 else float("-inf")

    basic=rr(0.10); severe=rr(0.25)
    th=THRESH[fam]
    risk_pass=bool(0.30<=x<=2.05 and 0.75<=risk_atr<=2.50 and risk_pct<=0.08)
    rr_pass=bool(basic>=th["basic"] and severe>=th["severe"])
    target_overlap=bool(T1<=entry_high)
    event_pass=(event_status=="CLEAN_DISCOVERY")

    hard_pass=bool(
      risk_pass and rr_pass and not target_overlap and not extension_veto
      and lifecycle=="ENTRY_BAND" and event_pass
    )
    mc_cap_blocks=bool(state_cap=="WATCH" or not r92_eligible)
    if hard_pass and mc_cap_blocks:
        result="WATCH_MC_FALLBACK_CAP"
    elif hard_pass:
        result="PRE_G9_TECH_PASS"
    elif lifecycle=="RETEST_REQUIRED":
        result="WATCH_RETEST_REQUIRED"
    elif lifecycle=="RECONFIRMATION_REQUIRED":
        result="WATCH_RECONFIRMATION_REQUIRED"
    elif lifecycle=="CHASE_NO_VALID_FILL":
        result="FAIL_CHASE"
    elif not event_pass:
        result="WATCH_EVENT_UNKNOWN_OR_BLOCKED"
    elif extension_veto:
        result="FAIL_EXTENSION"
    elif not risk_pass:
        result="FAIL_RISK_GEOMETRY"
    elif target_overlap:
        result="FAIL_R1_ENTRY_OVERLAP"
    elif not rr_pass:
        result="FAIL_RR"
    else:
        result="FAIL_OTHER"

    return {
      "result":result,"family":fam,"event_status":event_status,
      "levels":{"A":A,"P":P,"anchor":anchor,"close":close,
                "entry_low":entry_low,"entry_high":entry_high,
                "entry_model":entry_model,"chase_limit":chase,"S0":S0,"T1":T1},
      "geometry":{"x":x,"risk_atr":risk_atr,"risk_percent":risk_pct,
                  "pivot_extension":pivot_extension,"move3_atr":move3},
      "lifecycle":lifecycle,
      "target":{"source":target_source,"synthetic":synthetic,"price_discovery":price_discovery,
                "prior_max_high":prior_max},
      "rr":{"basic":basic,"basic_threshold":th["basic"],"basic_pass":basic>=th["basic"],
            "severe":severe,"severe_threshold":th["severe"],"severe_pass":severe>=th["severe"]},
      "risk_pass":risk_pass,"extension_veto":extension_veto,"target_overlap":target_overlap,
      "technical_hard_pass":hard_pass,
      "state_cap":state_cap,"r92_eligible":bool(r92_eligible),
      "pre_g9_tech_pass":bool(hard_pass and not mc_cap_blocks),
      "authority":"SHADOW_ONLY"
    }

def main():
    d=json.loads(DEEP.read_text())
    asof=d["asof_et"]
    if d.get("task_id")!=TASK_ID or d.get("execution")!="NONE" or d.get("real_money")!="NO-GO":
        raise RuntimeError("DEEP_SAFETY_OR_TASK_MISMATCH")
    candidates=[]
    state_caps=d.get("state_caps") or {}
    r92_ineligible=set(d.get("r92_ineligible") or [])
    for sym,r in (d.get("results") or {}).items():
        if r.get("A",{}).get("pool"): candidates.append((sym,"A",r["A"],r.get("event_status")))
        if r.get("B",{}).get("breakout_confirmed"): candidates.append((sym,"B",r["B"],r.get("event_status")))
        if r.get("D",{}).get("dk3_pre_r1"): candidates.append((sym,"D",r["D"],r.get("event_status")))
    family_c_count=0
    if FAMILY_C is not None and FAMILY_C.exists():
        fc=json.loads(FAMILY_C.read_text())
        if fc.get("task_id")!=TASK_ID or fc.get("asof_et")!=asof:
            raise RuntimeError("FAMILY_C_ASOF_OR_TASK_MISMATCH")
        if fc.get("execution")!="NONE" or fc.get("real_money")!="NO-GO":
            raise RuntimeError("FAMILY_C_SAFETY_MISMATCH")
        for sym,g in sorted((fc.get("confirmed") or {}).items()):
            if not g.get("confirmed"):
                continue
            candidates.append((sym,"C",g,g.get("event_status","CLEAN_DISCOVERY")))
            family_c_count+=1
    syms=sorted(set(x[0] for x in candidates))
    data={};errors={};history_source={} 
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(hist,s,asof):s for s in syms}
        for fut in as_completed(futs):
            s,x,e,src=fut.result()
            if x is None:errors[s]=e
            else:
                data[s]=x
                history_source[s]=src

    results={}
    for sym,fam,g,event in candidates:
        key=f"{sym}|{fam}"
        if sym not in data:
            results[key]={"result":"UNKNOWN","reason":"HISTORY:"+errors.get(sym,"MISSING"),"state_cap":state_caps.get(sym,"NORMAL"),"r92_eligible":sym not in r92_ineligible}
        else:
            results[key]=eval_one(sym,fam,g,data[sym],event,state_caps.get(sym,"NORMAL"),sym not in r92_ineligible)

    passes=[k for k,v in results.items() if v.get("pre_g9_tech_pass")]
    watches=[k for k,v in results.items() if str(v.get("result","")).startswith("WATCH_")]
    fails=[k for k,v in results.items() if str(v.get("result","")).startswith("FAIL_")]
    out={
      "schema":"XRAY_FINAL_TECH_SHADOW_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "input_confirmed_family_candidates":len(candidates),
      "family_c_confirmed_input_count":family_c_count,
      "pre_g9_tech_pass_count":len(passes),"pre_g9_tech_pass":passes,
      "watch_count":len(watches),"watch":watches,
      "fail_count":len(fails),"fail":fails,
      "state_caps":{s:state_caps.get(s,"NORMAL") for s in syms},
      "r92_ineligible":sorted(r92_ineligible & set(syms)),
      "history_source_by_symbol":history_source,
      "source_deep_path":relpath(DEEP),"source_deep_blob_sha":blob_sha(DEEP),
      "source_family_c_path":relpath(FAMILY_C) if FAMILY_C is not None and FAMILY_C.exists() else None,
      "source_family_c_blob_sha":blob_sha(FAMILY_C) if FAMILY_C is not None and FAMILY_C.exists() else None,
      "source_compiled_policy_hash":d.get("source_mc_policy_hash"),
      "source_compiled_policy_version":d.get("source_mc_policy_version"),
      "results":results,
      "policy_semantics_exact":False,
      "semantic_audit_status":"BLOCKED_KNOWN_GAPS",
      "semantic_known_gaps":[
        "R1_IMPLEMENTATION_USES_NEAREST_ANY_PRIOR_DAILY_HIGH_NOT_CERTIFIED_ELIGIBLE_ACTIVE_RESISTANCE",
        "RETEST_FROZEN_5_SESSION_LIFECYCLE_NOT_IMPLEMENTED",
        "FAMILY_A_PRELOW_NEAR_HL_0P5A_GATE_NOT_EXPLICITLY_BOUND_TO_C4_17",
        "EXTENSION_RESET_SEMANTICS_NOT_IMPLEMENTED",
        "CORPORATE_ACTION_ADJUSTMENT_RECONCILIATION_NOT_PROVEN"
      ],
      "remaining_nontech_gates":["OFFICIAL_EVENT_FINAL_REVIEW","ACCOUNT_GATE","G9","DELIVERY_PROOF"],
      "authority":"EXTERNAL_SHADOW_NO_SIGNAL"
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps(dict({k:out[k] for k in ["input_confirmed_family_candidates","pre_g9_tech_pass_count","watch_count","fail_count"]},provider_max_inflight=PROVIDER_MAX_INFLIGHT,retry_delays=RETRY_DELAYS),sort_keys=True))

if __name__=="__main__":
    main()
