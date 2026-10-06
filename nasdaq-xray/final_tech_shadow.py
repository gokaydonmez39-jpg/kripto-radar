#!/usr/bin/env python3
"""XRAY fail-closed final technical engine for C4.17 research candidates.
Consumes deep state and applies frozen geometry, active structural R1, R/R,
extension/reset, lifecycle and corporate-action consistency checks.
No execution, no real-money authority, no G9 authority.
"""
from __future__ import annotations
import json, math, os, hashlib, time, threading, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import akshare as ak
import pandas as pd
from alpha_semantics import (
    wilder_atr, trigger_index, setup_id, session_age,
    nearest_active_resistance, extension_diagnostics, retest_bar,
    apply_split_events, split_consistent_history, mechanical_scale_breaks,
    mechanical_split_suspects,
    history_fingerprint,
)

ROOT=Path(__file__).resolve().parent
DEEP=Path(os.getenv("XRAY_FINAL_DEEP_STATE", str(ROOT/"deep_pre_r1_shadow.json")))
OUT=Path(os.getenv("XRAY_FINAL_OUT", str(ROOT/"final_tech_shadow.json")))
FAMILY_C_ENV=os.getenv("XRAY_FINAL_FAMILY_C_STATE")
FAMILY_C=Path(FAMILY_C_ENV) if FAMILY_C_ENV else None
EVENTS_ENV=os.getenv("XRAY_FINAL_EVENT_STATE")
EVENTS=Path(EVENTS_ENV) if EVENTS_ENV else None
LIFECYCLE=Path(os.getenv("XRAY_FINAL_LIFECYCLE_REGISTRY",str(ROOT/"canonical_candidate_lifecycle_registry.json")))
LIFECYCLE_OUT=Path(os.getenv("XRAY_FINAL_LIFECYCLE_OUT",str(LIFECYCLE)))
TASK_ID="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_FINAL_WORKERS","6"))
PROVIDER_MAX_INFLIGHT=max(1,int(os.getenv("XRAY_FINAL_PROVIDER_MAX_INFLIGHT","3")))
RETRY_DELAYS=(0.0,1.0,2.5)
_PROVIDER_SEM=threading.Semaphore(PROVIDER_MAX_INFLIGHT)
OFFICIAL_IDENTITY_EVIDENCE=ROOT/"history_official_identity_evidence.json"
LEGAL=Path(os.getenv("XRAY_FINAL_LEGAL_STATE",str(ROOT/"canonical_current_legal.json")))
CANDIDATE_LEGAL_GUARD=Path(os.getenv("XRAY_FINAL_CANDIDATE_LEGAL_GUARD",str(ROOT/"canonical_candidate_legal_guard.json")))
SEC_CIK_CACHE=Path(os.getenv("XRAY_SEC_CIK_CACHE",str(ROOT/"sec_ticker_cik_cache.json")))
ADR_RATIO_BRIDGE=Path(os.getenv("XRAY_ADR_RATIO_BRIDGE",str(ROOT/"canonical_adr_ratio_bridge.json")))

def _is_depositary_security_name(name):
    s=str(name or "").upper()
    return any(x in s for x in ("AMERICAN DEPOSITARY","DEPOSITARY SHARE","DEPOSITARY SHARES"," ADR"," ADS"))

def _load_adr_bridge(asof):
    if not ADR_RATIO_BRIDGE.exists():return {}
    try:
        j=json.loads(ADR_RATIO_BRIDGE.read_text())
        if j.get("schema")!="XRAY_ADR_RATIO_BRIDGE_V1" or j.get("asof_et")!=asof:return {}
        if j.get("execution")!="NONE" or j.get("real_money")!="NO-GO":return {}
        return j.get("records") or {}
    except Exception:return {}

def _candidate_legal_scope_hash(symbols):
    xs=sorted(set(str(x) for x in symbols if str(x)))
    return hashlib.sha256(("\n".join(xs)+"\n").encode()).hexdigest()

def _load_candidate_legal_guard(asof):
    """Load exact-bound finalist legal evidence; any binding drift stays UNKNOWN."""
    if not CANDIDATE_LEGAL_GUARD.exists():return {},None,"CANDIDATE_LEGAL_GUARD_MISSING"
    try:
        j=json.loads(CANDIDATE_LEGAL_GUARD.read_text())
        if j.get("schema")!="XRAY_CANDIDATE_LEGAL_GUARD_V1" or j.get("asof_et")!=asof:
            return {},None,"CANDIDATE_LEGAL_GUARD_SCHEMA_OR_ASOF_MISMATCH"
        if j.get("task_id")!=TASK_ID or j.get("execution")!="NONE" or j.get("real_money")!="NO-GO":
            return {},None,"CANDIDATE_LEGAL_GUARD_SAFETY_OR_TASK_MISMATCH"
        if j.get("unknown_never_pass") is not True:
            return {},None,"CANDIDATE_LEGAL_GUARD_UNKNOWN_POLICY_MISMATCH"
        expected_deep=blob_sha(DEEP)
        expected_fc=blob_sha(FAMILY_C) if FAMILY_C is not None and FAMILY_C.exists() else None
        policy_path=ROOT/"chatgpt_compiled_policy_v3.json"
        if (not policy_path.exists()
            or blob_sha(policy_path)!="10d7af14870dfac0dc4566595d95a06f3faa854d"):
            return {},None,"CANDIDATE_LEGAL_GUARD_CURRENT_POLICY_AUTHORITY_DRIFT"
        if j.get("compiled_policy_path")!="nasdaq-xray/chatgpt_compiled_policy_v3.json":
            return {},None,"CANDIDATE_LEGAL_GUARD_POLICY_PATH_MISMATCH"
        if j.get("compiled_policy_blob_sha")!="10d7af14870dfac0dc4566595d95a06f3faa854d":
            return {},None,"CANDIDATE_LEGAL_GUARD_POLICY_BLOB_MISMATCH"
        if j.get("compiled_policy_hash")!="26a95745a50b65e85f6ece24b6501af0994764a84ddd886edb70d1fcd770849c":
            return {},None,"CANDIDATE_LEGAL_GUARD_POLICY_HASH_MISMATCH"
        if j.get("compiled_policy_version")!="C4.17":
            return {},None,"CANDIDATE_LEGAL_GUARD_POLICY_VERSION_MISMATCH"
        if j.get("source_deep_blob_sha")!=expected_deep:
            return {},None,"CANDIDATE_LEGAL_GUARD_DEEP_BINDING_MISMATCH"
        if j.get("source_family_c_blob_sha")!=expected_fc:
            return {},None,"CANDIDATE_LEGAL_GUARD_FAMILY_C_BINDING_MISMATCH"
        if j.get("source_cik_cache_path")!="nasdaq-xray/sec_ticker_cik_cache.json":
            return {},None,"CANDIDATE_LEGAL_GUARD_CIK_CACHE_PATH_MISMATCH"
        if j.get("source_cik_cache_blob_sha")!=blob_sha(SEC_CIK_CACHE):
            return {},None,"CANDIDATE_LEGAL_GUARD_CIK_CACHE_BINDING_MISMATCH"
        # Lifecycle is deliberately diagnostic only. Final mutates the durable
        # registry later in this same run, so requiring its pre-Final blob here
        # would make the just-produced legal guard self-stale after persistence.
        if j.get("source_lifecycle_binding_role")!="DIAGNOSTIC_PRE_FINAL_SCOPE_AUGMENTATION":
            return {},None,"CANDIDATE_LEGAL_GUARD_LIFECYCLE_ROLE_MISMATCH"
        scope=sorted(set(str(x) for x in (j.get("candidate_scope") or [])))
        if int(j.get("candidate_scope_count",-1))!=len(scope):
            return {},None,"CANDIDATE_LEGAL_GUARD_SCOPE_COUNT_MISMATCH"
        if j.get("candidate_scope_hash")!=_candidate_legal_scope_hash(scope):
            return {},None,"CANDIDATE_LEGAL_GUARD_SCOPE_HASH_MISMATCH"
        records=j.get("records") or {}
        if set(records)!=set(scope):
            return {},None,"CANDIDATE_LEGAL_GUARD_RECORD_SCOPE_MISMATCH"
        return records,j,None
    except Exception as exc:
        return {},None,"CANDIDATE_LEGAL_GUARD_PARSE_ERROR:"+type(exc).__name__

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
    cols={str(c).lower():c for c in df.columns};need=["date","open","high","low","close","volume"]
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

def frozen_semantics_binding():
    return {
      "alpha_semantics.py":blob_sha(ROOT/"alpha_semantics.py"),
      "final_tech_shadow.py":blob_sha(Path(__file__).resolve()),
    }

THRESH={
 "A":{"basic":1.5,"severe":1.1},
 "B":{"basic":2.0,"severe":1.5},
 "C":{"basic":2.0,"severe":1.5},
 "D":{"basic":2.0,"severe":1.5},
}
LIFECYCLE_WATCH_STATES={
 "WATCH_RETEST_REQUIRED","WATCH_RECONFIRMATION_REQUIRED",
 "WATCH_CHASE_RETEST_REQUIRED","WATCH_EXTENSION_RESET_REQUIRED",
 "WATCH_REGIME_REVALIDATION_REQUIRED","WATCH_REGIME_UNKNOWN"
}
# Current research-eligible passes and resolvable watches keep frozen geometry
# until explicit invalidation/expiry. R92 validation remains prospective-only:
# registration may start now, but pre-registration observations are never backfilled.
LIFECYCLE_PERSIST_STATES=LIFECYCLE_WATCH_STATES | {
 "PRE_G9_TECH_PASS","WATCH_EVENT_UNKNOWN_OR_BLOCKED",
 "WATCH_MC_FALLBACK_CAP"
}

def lifecycle_state_persists(state):
    """Prospective lifecycle persistence; historical backfill is intentionally excluded."""
    return str(state or "") in LIFECYCLE_PERSIST_STATES

def detailed_legal_required_for_technical_state(state):
    """Detailed SEC review is required only for technically live candidate states.

    A terminal technical FAIL needs no legal waiver to remain FAIL. Technical
    UNKNOWN likewise remains UNKNOWN on its own evidence. This function can
    never create PASS; PRE_G9/WATCH states still require exact legal PASS.
    """
    s=str(state or "")
    return s=="PRE_G9_TECH_PASS" or s.startswith("WATCH_")

def reconcile_final_result_scope(results,fresh_current_keys,registry):
    """Keep only current fresh finalists or still-live lifecycle carries.

    Final evaluation may emit an UNKNOWN row for a lifecycle carry before the
    record is subsequently pruned by the 8-session horizon. Such an expired
    carry must disappear from the final result set as well; otherwise Terminal
    sees an unbacked historical row. This helper never creates PASS and never
    changes a result payload.
    """
    fresh=set(str(x) for x in (fresh_current_keys or []))
    live=set()
    for rec in ((registry or {}).get("records") or {}).values():
        if not isinstance(rec,dict): continue
        sym=str(rec.get("symbol") or ""); fam=str(rec.get("family") or "")
        if sym and fam and lifecycle_state_persists(rec.get("state")):
            live.add(f"{sym}|{fam}")
    keep=fresh|live
    dropped=sorted(set(results)-keep)
    return {k:v for k,v in results.items() if k in keep},dropped

def _empty_lifecycle_registry():
    return {"schema":"XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1",
            "execution":"NONE","real_money":"NO-GO","records":{}}

def load_lifecycle_registry(final_path:Path|None=OUT, sidecar_path:Path|None=LIFECYCLE, asof:str|None=None):
    """Load durable lifecycle state without accepting future-dated evidence.

    A valid sidecar overrides the embedded prior-Final copy. When an ASOF is
    supplied, any registry or record dated later than that ASOF is a fail-closed
    integrity error rather than silently usable look-ahead state.
    """
    registry=_empty_lifecycle_registry()
    for p,embedded in ((final_path,True),(sidecar_path,False)):
        if p is None:
            continue
        p=Path(p)
        if not p.exists():
            continue
        try:
            obj=json.loads(p.read_text())
            cand=(obj.get("lifecycle_registry") or {}) if embedded else obj
            if not (cand.get("schema")==registry["schema"]
                and cand.get("execution")=="NONE" and cand.get("real_money")=="NO-GO"
                and isinstance(cand.get("records"),dict)):
                continue
            if asof:
                src_asof=str(cand.get("asof_et") or obj.get("asof_et") or "")
                if src_asof and src_asof>asof:
                    raise RuntimeError("LIFECYCLE_REGISTRY_FUTURE_ASOF")
                for rec in (cand.get("records") or {}).values():
                    if not isinstance(rec,dict): continue
                    last=str(rec.get("last_asof") or "")
                    if last and last>asof:
                        raise RuntimeError("LIFECYCLE_RECORD_FUTURE_ASOF")
            registry=cand
        except RuntimeError:
            raise
        except Exception:
            continue
    return registry

def persist_lifecycle_registry(registry:dict,path:Path|None=None):
    """Persist and exact-readback JSON before any downstream final artifact is emitted."""
    p=Path(path) if path is not None else LIFECYCLE_OUT
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(registry,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    try:
        reread=json.loads(p.read_text())
    except Exception as exc:
        raise RuntimeError("LIFECYCLE_REGISTRY_READBACK_PARSE_FAIL") from exc
    if reread!=registry:
        raise RuntimeError("LIFECYCLE_REGISTRY_ROUNDTRIP_MISMATCH")
    return reread

def hist(sym,asof):
    try:
        x,src=load_history(sym,asof)
        if x is None or x.empty:return sym,None,"EMPTY",None
        last=x["date"].dt.date.max().isoformat()
        if last!=asof:return sym,None,f"ASOF_MISSING:{last}",None
        if len(x)<260:return sym,None,f"LT260:{len(x)}",None
        return sym,x,None,src
    except Exception as e:return sym,None,f"{type(e).__name__}:{str(e)[:160]}",None

def _trigger_date(fam,g):
    return str(g.get("trigger_date") or g.get("breakout_session") or "")

def candidate_corporate_action_reconcile(sym,df,drow=None):
    """Candidate-scoped price-scale integrity.

    Mechanical factor-like gaps are discovery triggers, not corporate-action proof.
    The shared split reconciler validates any provider-declared split against raw
    OHLC and otherwise preserves legitimate market/news gaps. Finalist-level
    material legal/corporate-action risk is handled separately by the mandatory
    exact-ASOF candidate legal guard; do not double-count an ordinary price gap as
    an unverified corporate action here.
    """
    x=df.reset_index(drop=True)
    if drow is not None:
        inherited_status=drow.get("corporate_action_status")
        if inherited_status is not None and not str(inherited_status).startswith("PASS"):
            return x,inherited_status,[],False

    severe=mechanical_scale_breaks(x,260)
    fractional=mechanical_split_suspects(x,260)
    if severe or fractional:
        x2,status,events=split_consistent_history(sym,x)
        if not str(status).startswith("PASS"):
            return x2.reset_index(drop=True),status,events,True
        return x2.reset_index(drop=True),status,events,True

    return x,"PASS_NO_LOCAL_SPLIT_DISCONTINUITY",[],False

def _frozen_geometry(sym,fam,g,df):
    td=_trigger_date(fam,g)
    if not td:return None,{"result":"UNKNOWN","reason":"TRIGGER_DATE_MISSING"}
    ti=trigger_index(df,td)
    if ti is None or ti<1:return None,{"result":"UNKNOWN","reason":"TRIGGER_DATE_NOT_IN_HISTORY","trigger_date":td}
    atr=wilder_atr(df,14)
    if ti-1>=len(atr) or pd.isna(atr.iloc[ti-1]):
        return None,{"result":"UNKNOWN","reason":"ATR_TRIGGER_MINUS1_MISSING","trigger_date":td}
    A=float(atr.iloc[ti-1]);P=float(g["P"]);anchor=float(g["anchor"])
    if not all(math.isfinite(v) for v in (A,P,anchor)) or A<=0:
        return None,{"result":"UNKNOWN","reason":"NONFINITE_GEOMETRY"}
    entry_low=P;entry_high=P+0.25*A;entry_model=entry_high;chase=P+0.50*A;S0=anchor-0.20*A
    if fam in {"A","D"}:
        hld=str(g.get("hl_date") or "")
        hi=trigger_index(df,hld) if hld else None
        if hi is None or hi+2>ti:
            return None,{"result":"UNKNOWN","reason":"ANCHOR_AVAILABILITY_UNRESOLVED","trigger_date":td,"hl_date":hld}
        anchor_available_idx=hi+2
    else:
        # B/C anchor is the completed base/consolidation low known at trigger-1 close.
        anchor_available_idx=ti-1
    anchor_available_date=df["date"].iloc[anchor_available_idx].date().isoformat()
    r1=nearest_active_resistance(df,ti,A,entry_low,entry_high,entry_model)
    trigger_close=float(df["close"].iloc[ti])
    synthetic=False
    if r1["status"]=="PASS":
        T1=float(r1["T1"]); target_source="STRUCTURAL_ACTIVE_R1_LOWER_BOUND"; target_overlap=bool(r1["target_overlap"])
        zone=r1.get("zone")
    else:
        prior_max=r1.get("prior_max_high")
        price_discovery=bool(prior_max is not None and math.isfinite(float(prior_max)) and trigger_close>float(prior_max))
        if not price_discovery:
            return None,{"result":"UNKNOWN","reason":"R1_UNRESOLVED_NO_ELIGIBLE_ACTIVE_RESISTANCE",
                         "trigger_date":td,"r1_status":r1["status"]}
        T1=P+3*A; synthetic=True;target_source="SYNTHETIC_P_PLUS_3A_PRICE_DISCOVERY";target_overlap=False;zone=None
    frozen={
      "setup_id":setup_id(sym,fam,td,P,anchor,A),"symbol":sym,"family":fam,"trigger_date":td,
      "A":A,"P":P,"anchor":anchor,"entry_low":entry_low,"entry_high":entry_high,
      "entry_model":entry_model,"chase_limit":chase,"S0":S0,"T1":T1,
      "anchor_available_idx":anchor_available_idx,"anchor_available_date":anchor_available_date,
      "target_source":target_source,"target_zone":zone,"target_overlap":target_overlap,
      "synthetic_target":synthetic,"source_geometry":g,
    }
    return frozen,None

def eval_one(sym,fam,g,df,event_status,state_cap="NORMAL",r92_eligible=True,frozen=None,recorded_before=False,
             regime_finalist_status="PASS"):
    if frozen is None:
        frozen,err=_frozen_geometry(sym,fam,g,df)
        if err:return err
    A=float(frozen["A"]);P=float(frozen["P"]);anchor=float(frozen["anchor"])
    entry_low=float(frozen["entry_low"]);entry_high=float(frozen["entry_high"])
    entry_model=float(frozen["entry_model"]);chase=float(frozen["chase_limit"])
    S0=float(frozen["S0"]);T1=float(frozen["T1"]);td=str(frozen["trigger_date"])
    close=float(df.close.iloc[-1]);asof=df.date.iloc[-1].date().isoformat()
    age=session_age(df,td,asof)
    if age is None:return {"result":"UNKNOWN","reason":"LIFECYCLE_SESSION_AGE_UNKNOWN","trigger_date":td}
    ti=trigger_index(df,td)
    if ti is None:return {"result":"UNKNOWN","reason":"TRIGGER_DATE_NOT_IN_HISTORY","trigger_date":td}

    # C4.17 hard invalidation begins only after ANCHOR_AVAILABLE_AT.
    # This includes trigger-day lows for B/C, and any pre-trigger sessions after
    # a confirmed A/D HL became available.
    ai=frozen.get("anchor_available_idx")
    if not isinstance(ai,int) or ai<0 or ai>=len(df) or ai>ti:
        return {"result":"UNKNOWN","reason":"ANCHOR_AVAILABILITY_INDEX_INVALID","trigger_date":td}
    post=df.iloc[ai+1:]
    breach_rows=post[post["low"].astype(float)<=S0]
    breached=not breach_rows.empty
    breach_date=None if not breached else breach_rows.date.iloc[0].date().isoformat()

    current_retest=bool(age>0 and age<=5 and retest_bar(df.iloc[-1],P,entry_high))
    if breached:
        lifecycle="INVALIDATED_S0"
    elif age>8:
        lifecycle="EXPIRED_HORIZON"
    elif close<P:
        lifecycle="RECONFIRMATION_REQUIRED"
    elif close<=entry_high:
        if age==0:lifecycle="ENTRY_BAND"
        elif current_retest:lifecycle="RETEST_ENTRY_BAND"
        elif age<=5:lifecycle="RETEST_REQUIRED"
        else:lifecycle="EXPIRED_RETEST_WINDOW"
    elif close<chase:
        lifecycle="RETEST_REQUIRED" if age<=5 else "EXPIRED_RETEST_WINDOW"
    else:
        lifecycle="CHASE_NO_VALID_FILL"

    ext=extension_diagnostics(df,A,P,entry_high)
    extension_veto=bool(ext["extension_veto"])
    x=(P-anchor)/A
    risk_atr=(entry_model-S0)/A
    risk_pct=(entry_model-S0)/entry_model if entry_model>0 else float("inf")

    def rr(cost_mult):
        cost=cost_mult*A;E=entry_model+cost;S=S0-cost;T=T1-cost;den=E-S
        return (T-E)/den if den>0 else float("-inf")
    basic=rr(0.10);severe=rr(0.25);th=THRESH[fam]
    if fam=="A":
        depth=g.get("depth")
        try: depth=float(depth)
        except Exception: depth=float("nan")
        family_geometry_pass=bool(
            0.30<=x<=1.07
            and math.isfinite(depth) and 2.15<=depth<=4.00
            and g.get("prelow_near_hl") is True
        )
    else:
        family_geometry_pass=bool(0.30<=x<=2.05)
    risk_pass=bool(family_geometry_pass and 0.75<=risk_atr<=2.50 and risk_pct<=0.08)
    rr_pass=bool(basic>=th["basic"] and severe>=th["severe"])
    target_overlap=bool(frozen.get("target_overlap") or T1<=entry_high)
    event_pass=(event_status=="CLEAN_DISCOVERY")
    entry_ready=lifecycle in {"ENTRY_BAND","RETEST_ENTRY_BAND"}
    historical_new=bool(age>3 and not recorded_before)
    # R92/R93 is prospective-only, but that restriction governs observation
    # accounting, not current research eligibility. A still-valid setup first
    # discovered on session 4/5 may be a current PRE_G9 research candidate;
    # prior bars simply cannot be backfilled into validation statistics.
    r92_backfill_allowed=False
    regime_pass=(regime_finalist_status=="PASS")
    hard_pass=bool(risk_pass and rr_pass and not target_overlap and not extension_veto
                   and entry_ready and event_pass and regime_pass and not breached)
    mc_cap_blocks=bool(state_cap=="WATCH" or not r92_eligible)
    synthetic_cap=bool(frozen.get("synthetic_target"))

    if hard_pass and mc_cap_blocks: result="WATCH_MC_FALLBACK_CAP"
    elif hard_pass: result="PRE_G9_TECH_PASS"
    elif lifecycle=="INVALIDATED_S0": result="FAIL_INVALIDATED_S0"
    elif lifecycle in {"EXPIRED_RETEST_WINDOW","EXPIRED_HORIZON"}: result="FAIL_EXPIRED"
    elif not event_pass: result="WATCH_EVENT_UNKNOWN_OR_BLOCKED"
    elif regime_finalist_status=="UNKNOWN": result="WATCH_REGIME_UNKNOWN"
    elif not regime_pass: result="WATCH_REGIME_REVALIDATION_REQUIRED"
    elif lifecycle=="CHASE_NO_VALID_FILL" and age<=5: result="WATCH_CHASE_RETEST_REQUIRED"
    elif extension_veto and age<=5: result="WATCH_EXTENSION_RESET_REQUIRED"
    elif lifecycle=="CHASE_NO_VALID_FILL": result="FAIL_CHASE"
    elif extension_veto: result="FAIL_EXTENSION"
    elif lifecycle=="RETEST_REQUIRED": result="WATCH_RETEST_REQUIRED"
    elif lifecycle=="RECONFIRMATION_REQUIRED": result="WATCH_RECONFIRMATION_REQUIRED"
    elif not risk_pass: result="FAIL_RISK_GEOMETRY"
    elif target_overlap: result="FAIL_R1_ENTRY_OVERLAP"
    elif not rr_pass: result="FAIL_RR"
    else: result="FAIL_OTHER"

    return {
      "result":result,"family":fam,"event_status":event_status,"setup_id":frozen["setup_id"],
      "trigger_date":td,"lifecycle_age_sessions":age,
      "levels":{"A":A,"P":P,"anchor":anchor,"close":close,"entry_low":entry_low,
                "entry_high":entry_high,"entry_model":entry_model,"chase_limit":chase,"S0":S0,"T1":T1},
      "geometry":{"x":x,"risk_atr":risk_atr,"risk_percent":risk_pct,
                  "pivot_extension":ext["pivot_extension"],"move3_atr":ext["move3_atr"],
                  "reset_between_tminus3_and_t":ext["reset_between_tminus3_and_t"]},
      "lifecycle":lifecycle,"current_retest":current_retest,
      "observation_mode":"PROSPECTIVE_RECORDED" if recorded_before else ("DISCOVERED_HISTORICAL" if historical_new else "CURRENT_DISCOVERY"),
      "invalidation":{"breached":breached,"first_breach_date":breach_date},
      "target":{"source":frozen["target_source"],"synthetic":synthetic_cap,
                "zone":frozen.get("target_zone")},
      "rr":{"basic":basic,"basic_threshold":th["basic"],"basic_pass":basic>=th["basic"],
            "severe":severe,"severe_threshold":th["severe"],"severe_pass":severe>=th["severe"]},
      "risk_pass":risk_pass,"family_geometry_pass":family_geometry_pass,
      "extension_veto":extension_veto,"target_overlap":target_overlap,
      "technical_hard_pass":hard_pass,"regime_finalist_status":regime_finalist_status,
      "discovered_after_trigger":bool(age>0 and not recorded_before),
      "historical_discovery_age_gt3":historical_new,
      "r92_backfill_allowed":r92_backfill_allowed,
      "r92_observation_rule":"REGISTER_NOW_OBSERVE_FUTURE_ONLY_NO_BACKFILL",
      "state_cap":state_cap,"r92_eligible":bool(r92_eligible),
      "price_discovery_cap":synthetic_cap,
      "research_tier_cap":"ORANGE" if synthetic_cap else None,
      "pre_g9_tech_pass":bool(hard_pass and not mc_cap_blocks),
      "frozen_geometry":frozen,"authority":"C4_17_DETERMINISTIC_TECHNICAL"
    }

def _run_embedded_semantic_selftest():
    p=ROOT/"test_alpha_semantics.py"
    if not p.exists():raise RuntimeError("ALPHA_SEMANTIC_SELFTEST_MISSING")
    cp=subprocess.run([sys.executable,str(p)],cwd=str(ROOT.parent),text=True,capture_output=True,timeout=60)
    if cp.returncode!=0:
        tail=(cp.stdout+"\n"+cp.stderr)[-4000:]
        raise RuntimeError("ALPHA_SEMANTIC_SELFTEST_FAIL:"+tail.replace("\n"," | "))
    return "PASS"

def _regime_finalist_status(deep,sym):
    regime=str(deep.get("regime") or "UNKNOWN")
    if regime not in {"STRONG","MIXED","WEAK"}:
        return "UNKNOWN"
    row=(deep.get("results") or {}).get(sym)
    if isinstance(row,dict):
        st=str(row.get("regime_finalist_status") or "")
        if st in {"PASS","FAIL","UNKNOWN"}: return st
        if row.get("regime_finalist_pass") is True: return "PASS"
        if row.get("regime_finalist_pass") is False: return "FAIL"
    lr=(deep.get("lifecycle_revalidation") or {}).get(sym) or {}
    st=str(lr.get("regime_finalist_status") or lr.get("status") or "")
    return st if st in {"PASS","FAIL","UNKNOWN"} else "UNKNOWN"

def _regime_finalist_allowed(deep,sym):
    return _regime_finalist_status(deep,sym)=="PASS"

def _fresh_deep_family_confirmed(deep,sym,fam):
    """Fresh Final scope must exactly match Deep's event+RS confirmed sets.

    Raw per-symbol geometry flags may still be true for an event-blocked name.
    Such a row is not a fresh finalist. Only an already-recorded lifecycle setup
    may survive separately through the frozen lifecycle path.
    """
    fields={
      "A":"a_geometry_rs_event_pass",
      "B":"b_breakout_rs_event_pass",
      "D":"d_dk3_pre_r1",
    }
    field=fields.get(fam)
    return bool(field and sym in set(deep.get(field) or []))

def main():
    semantic_selftest_status=_run_embedded_semantic_selftest()
    d=json.loads(DEEP.read_text());asof=d["asof_et"]
    if d.get("task_id")!=TASK_ID or d.get("execution")!="NONE" or d.get("real_money")!="NO-GO":
        raise RuntimeError("DEEP_SAFETY_OR_TASK_MISMATCH")
    if not LEGAL.exists():raise RuntimeError("LEGAL_STATE_MISSING")
    legal=json.loads(LEGAL.read_text())
    if legal.get("asof_et")!=asof or legal.get("execution")!="NONE" or legal.get("real_money")!="NO-GO":
        raise RuntimeError("LEGAL_STATE_SAFETY_OR_ASOF_MISMATCH")
    adr_bridge=_load_adr_bridge(asof)
    candidate_legal_records,candidate_legal_guard,candidate_legal_guard_error=_load_candidate_legal_guard(asof)
    state_caps=d.get("state_caps") or {};r92_ineligible=set(d.get("r92_ineligible") or [])
    event_map={}
    if EVENTS is not None and EVENTS.exists():
        ev=json.loads(EVENTS.read_text())
        if ev.get("asof_et")!=asof:raise RuntimeError("FINAL_EVENT_ASOF_MISMATCH")
        event_map=ev.get("event_status_by_symbol") or {}

    registry=load_lifecycle_registry(asof=asof)
    old_records=registry.get("records") or {}
    current_frozen_binding=frozen_semantics_binding()

    candidates=[];regime_filtered_out=[]
    for sym,r in (d.get("results") or {}).items():
        event=event_map.get(sym,r.get("event_status"))
        allowed=_regime_finalist_allowed(d,sym)
        for fam,flag in (("A",r.get("A",{}).get("pool")),("B",r.get("B",{}).get("breakout_confirmed")),("D",r.get("D",{}).get("dk3_pre_r1"))):
            if not flag: continue
            # A raw geometry flag alone is insufficient. Fresh finalist scope is
            # the exact Deep event+RS confirmed set. Event-blocked/unknown rows
            # can only persist through an already-recorded lifecycle setup.
            if not _fresh_deep_family_confirmed(d,sym,fam):
                continue
            if allowed:
                candidates.append((sym,fam,r[fam],event))
            else:
                regime_filtered_out.append(f"{sym}|{fam}")
    family_c_count=0
    if FAMILY_C is not None and FAMILY_C.exists():
        fc=json.loads(FAMILY_C.read_text())
        if fc.get("task_id")!=TASK_ID or fc.get("asof_et")!=asof:raise RuntimeError("FAMILY_C_ASOF_OR_TASK_MISMATCH")
        if fc.get("execution")!="NONE" or fc.get("real_money")!="NO-GO":raise RuntimeError("FAMILY_C_SAFETY_MISMATCH")
        for sym,g in sorted((fc.get("confirmed") or {}).items()):
            if not g.get("confirmed"): continue
            if _regime_finalist_allowed(d,sym):
                candidates.append((sym,"C",g,event_map.get(sym,g.get("event_status","CLEAN_DISCOVERY"))));family_c_count+=1
            else:
                regime_filtered_out.append(f"{sym}|C")

    # Existing prospective frozen setups have priority over newly discovered geometry
    # for the same symbol/family. A new trigger may take over only after the prior
    # frozen setup actually fails/expires in this evaluation.
    fresh_candidates=list(candidates)
    fresh_current_candidate_keys=sorted(set(f"{sym}|{fam}" for sym,fam,_g,_event in fresh_candidates))
    frozen_candidates=[]
    deep_scope=set((d.get("results") or {}).keys())
    for rec in old_records.values():
        sym=rec.get("symbol");fam=rec.get("family")
        if not sym or fam not in THRESH:continue
        if not lifecycle_state_persists(rec.get("state")):continue
        # A prospectively recorded frozen setup survives current weekly/deep-scope
        # changes until its explicit S0/event/expiry lifecycle says otherwise.
        if rec.get("state_cap") is not None:
            state_caps.setdefault(sym,rec.get("state_cap"))
        if rec.get("r92_eligible") is False:
            r92_ineligible.add(sym)
        g=rec.get("source_geometry")
        if isinstance(g,dict):
            lr=(d.get("lifecycle_revalidation") or {}).get(sym) or {}
            current_event=event_map.get(sym,lr.get("event_status",rec.get("event_status")))
            frozen_candidates.append((sym,fam,g,current_event))
    candidates=frozen_candidates+fresh_candidates

    syms=sorted(set(x[0] for x in candidates));data={};errors={};history_source={};history_fps={}
    expected_history_fps=d.get("history_fingerprint_by_symbol") or {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(hist,s,asof):s for s in syms}
        for fut in as_completed(futs):
            s,x,e,src=fut.result()
            if x is None:errors[s]=e
            else:
                fp=history_fingerprint(x,asof)
                exp=expected_history_fps.get(s)
                if exp is None:
                    errors[s]="HISTORY_FINGERPRINT_BINDING_MISSING"
                elif fp!=exp:
                    errors[s]="HISTORY_FINGERPRINT_MISMATCH"
                else:
                    data[s]=x;history_source[s]=src;history_fps[s]=fp

    corporate_action_errors={}; corporate_action_verification={}
    for s in list(data):
        drow=(d.get("results") or {}).get(s)
        x2,ca_status,split_events,lookup=candidate_corporate_action_reconcile(s,data[s],drow)
        corporate_action_verification[s]={
            "status":ca_status,"split_events":split_events,
            "candidate_scoped_external_lookup":lookup,
        }
        if not str(ca_status).startswith("PASS"):
            corporate_action_errors[s]=ca_status or "MISSING"
            continue
        data[s]=x2

    results={};new_records=dict(old_records)
    seen=set()
    for sym,fam,g,event in candidates:
        pair=(sym,fam,_trigger_date(fam,g),float(g.get("P",float("nan"))),float(g.get("anchor",float("nan"))))
        if pair in seen:continue
        seen.add(pair);key=f"{sym}|{fam}"
        if sym not in data:
            results[key]={"result":"UNKNOWN","reason":"HISTORY:"+errors.get(sym,"MISSING"),"state_cap":state_caps.get(sym,"NORMAL"),"r92_eligible":sym not in r92_ineligible}
            continue
        lrow=(legal.get("results") or {}).get(sym) or {}
        if lrow.get("status")!="PASS_LEGAL":
            results[key]={"result":"UNKNOWN","reason":"LEGAL_IDENTITY_NOT_PASS","legal_status":lrow.get("status")}
            continue
        # Global LEGAL is only the shell/identity screen. Detailed SEC review
        # is finalist-local, but it must not erase a terminal technical FAIL.
        # Evaluate technical geometry first; only live PRE_G9/WATCH states need
        # exact detailed legal PASS before they remain live.
        cg=(candidate_legal_records or {}).get(sym) or {}
        secname=lrow.get("security_name")
        if _is_depositary_security_name(secname):
            ar=adr_bridge.get(sym) or {}
            if ar.get("status")!="PASS" or ar.get("ratio_review_complete") is not True:
                results[key]={"result":"UNKNOWN","reason":"ADR_RATIO_REVIEW_REQUIRED",
                              "security_name":secname,"adr_ratio_bridge_status":ar.get("status")}
                continue
        if sym in corporate_action_errors:
            results[key]={"result":"UNKNOWN","reason":"CORPORATE_ACTION_NOT_VERIFIED",
                          "corporate_action_status":corporate_action_errors[sym],
                          "state_cap":state_caps.get(sym,"NORMAL"),"r92_eligible":sym not in r92_ineligible}
            continue
        frozen,err=_frozen_geometry(sym,fam,g,data[sym])
        if err:
            results[key]=err;continue
        prior=old_records.get(frozen["setup_id"])
        prior_recorded=bool(prior)
        # Frozen levels are reusable only when they were produced by the exact
        # current frozen-geometry implementation. A semantic repair migrates the
        # record by recomputing levels, while preserving prospective-record status.
        if (prior and isinstance(prior.get("frozen_geometry"),dict)
            and prior.get("frozen_semantics_blobs")==current_frozen_binding):
            frozen=prior["frozen_geometry"]
        regime_status=_regime_finalist_status(d,sym)
        res=eval_one(sym,fam,g,data[sym],event,state_caps.get(sym,"NORMAL"),sym not in r92_ineligible,
                     frozen,recorded_before=prior_recorded,regime_finalist_status=regime_status)
        res["candidate_legal_review_status"]=cg.get("status")
        res["candidate_legal_review_reason"]=cg.get("reason")
        res["candidate_legal_risk_flags"]=sorted(set(cg.get("risk_flags") or []))
        res["candidate_legal_hard_flags"]=sorted(set(cg.get("hard_legal_flags") or []))
        res["candidate_legal_latest_periodic"]=cg.get("latest_periodic")
        technical_prelegal_result=str(res.get("result") or "")
        if detailed_legal_required_for_technical_state(technical_prelegal_result) and cg.get("status")!="PASS":
            res={
              **res,
              "result":"UNKNOWN",
              "reason":"DETAILED_LEGAL_REVIEW_NOT_PROVEN",
              "technical_prelegal_result":technical_prelegal_result,
              "technical_prelegal_pass":bool(res.get("pre_g9_tech_pass")),
              "pre_g9_tech_pass":False,
              "candidate_legal_status":cg.get("status") or "MISSING",
              "candidate_legal_reason":cg.get("reason"),
            }
        existing=results.get(key)
        existing_live=bool(existing and existing.get("observation_mode")=="PROSPECTIVE_RECORDED"
                           and not str(existing.get("result","")).startswith("FAIL_")
                           and existing.get("result")!="UNKNOWN")
        if not existing_live:
            results[key]=res
        state=str(res.get("result") or "")
        if lifecycle_state_persists(state):
            new_records[frozen["setup_id"]]={
              "setup_id":frozen["setup_id"],"symbol":sym,"family":fam,"trigger_date":frozen["trigger_date"],
              "state":state,"last_asof":asof,"frozen_geometry":frozen,"source_geometry":g,
              "frozen_semantics_blobs":current_frozen_binding,
              "event_status":event,"state_cap":state_caps.get(sym,"NORMAL"),"r92_eligible":sym not in r92_ineligible
            }
        elif frozen["setup_id"] in new_records:
            new_records[frozen["setup_id"]]["state"]=state
            new_records[frozen["setup_id"]]["last_asof"]=asof
            new_records[frozen["setup_id"]]["frozen_geometry"]=frozen
            new_records[frozen["setup_id"]]["frozen_semantics_blobs"]=current_frozen_binding

    # Drop records that are safely beyond both retest and model horizons.
    pruned={}
    for sid,rec in new_records.items():
        sym=rec.get("symbol")
        if sym in data:
            age=session_age(data[sym],str(rec.get("trigger_date")),asof)
            if age is not None and age>8:continue
        pruned[sid]=rec
    registry={"schema":"XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1","task_id":TASK_ID,"asof_et":asof,
              "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
              "records":dict(sorted(pruned.items()))}
    # Durable prospective setup state. This must be written before the final
    # artifact so the workflow can atomically persist the registry alongside
    # the terminal/final artifacts. Without this file, frozen retest levels are
    # lost between runs even though the final artifact embeds a copy.
    persist_lifecycle_registry(registry)

    # A lifecycle-only row can be evaluated before its record is pruned for
    # expiry. Reconcile the emitted result scope after pruning so downstream
    # Terminal never receives an unbacked historical carry.
    results,pruned_final_result_keys=reconcile_final_result_scope(
        results,fresh_current_candidate_keys,registry
    )

    passes=[k for k,v in results.items() if v.get("pre_g9_tech_pass")]
    watches=[k for k,v in results.items() if str(v.get("result","")).startswith("WATCH_")]
    regime_revalidation_unknown=sorted(k for k,v in results.items() if v.get("result")=="WATCH_REGIME_UNKNOWN")
    fails=[k for k,v in results.items() if str(v.get("result","")).startswith("FAIL_")]
    lifecycle_semantics_exact=all(
        rec.get("frozen_semantics_blobs")==current_frozen_binding
        for rec in registry.get("records",{}).values()
    )
    corporate_semantics_unresolved=sorted(
        k for k,v in results.items()
        if str(v.get("reason","")).startswith("CORPORATE_ACTION")
        or str(v.get("corporate_action_status","")).startswith("UNKNOWN")
    )
    history_binding_unresolved=sorted(
        k for k,v in results.items()
        if "HISTORY_FINGERPRINT" in str(v.get("reason",""))
    )
    semantic_known_gaps=[]
    if not lifecycle_semantics_exact:
        semantic_known_gaps.append("FROZEN_LIFECYCLE_PERSISTENCE_BINDING_NOT_EXACT")
    if corporate_semantics_unresolved:
        semantic_known_gaps.append("CORPORATE_ACTION_RECONCILIATION_UNPROVEN_FOR_FINALISTS")
    if history_binding_unresolved:
        semantic_known_gaps.append("CROSS_PHASE_HISTORY_BINDING_UNPROVEN_FOR_FINALISTS")
    policy_semantics_exact=bool(
        semantic_selftest_status=="PASS"
        and lifecycle_semantics_exact
        and not corporate_semantics_unresolved
        and not history_binding_unresolved
    )
    if semantic_selftest_status!="PASS":
        semantic_audit_status="BLOCKED_SELFTEST"
    elif not lifecycle_semantics_exact:
        semantic_audit_status="BLOCKED_LIFECYCLE_PERSISTENCE"
    elif corporate_semantics_unresolved:
        semantic_audit_status="BLOCKED_CORPORATE_ACTION_RECONCILIATION"
    elif history_binding_unresolved:
        semantic_audit_status="BLOCKED_CROSS_PHASE_HISTORY_BINDING"
    else:
        semantic_audit_status="PASS_IMPLEMENTATION_CONFORMANCE"
    out={
      "schema":"XRAY_FINAL_TECH_SHADOW_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "input_confirmed_family_candidates":len(results),"family_c_confirmed_input_count":family_c_count,
      "fresh_current_candidate_keys":fresh_current_candidate_keys,
      "fresh_current_candidate_count":len(fresh_current_candidate_keys),
      "pruned_final_result_keys":pruned_final_result_keys,
      "regime_filtered_out":sorted(set(regime_filtered_out)),
      "regime_revalidation_unknown_count":len(regime_revalidation_unknown),
      "regime_revalidation_unknown":regime_revalidation_unknown,
      "pre_g9_tech_pass_count":len(passes),"pre_g9_tech_pass":sorted(passes),
      "watch_count":len(watches),"watch":sorted(watches),"fail_count":len(fails),"fail":sorted(fails),
      "state_caps":{s:state_caps.get(s,"NORMAL") for s in syms},
      "r92_ineligible":sorted(r92_ineligible & set(syms)),"history_source_by_symbol":history_source,
      "history_fingerprint_by_symbol":history_fps,
      "history_fingerprint_semantics":"RAW_OR_OFFICIAL_COMPOSITE_ASOF_TAIL320_V1",
      "corporate_action_verification":corporate_action_verification,
      "source_deep_path":relpath(DEEP),"source_deep_blob_sha":blob_sha(DEEP),
      "source_family_c_path":relpath(FAMILY_C) if FAMILY_C is not None and FAMILY_C.exists() else None,
      "source_family_c_blob_sha":blob_sha(FAMILY_C) if FAMILY_C is not None and FAMILY_C.exists() else None,
      "source_legal_path":relpath(LEGAL),"source_legal_blob_sha":blob_sha(LEGAL),
      "candidate_legal_guard_path":relpath(CANDIDATE_LEGAL_GUARD) if CANDIDATE_LEGAL_GUARD.exists() else None,
      "candidate_legal_guard_blob_sha":blob_sha(CANDIDATE_LEGAL_GUARD) if CANDIDATE_LEGAL_GUARD.exists() else None,
      "candidate_legal_guard_exact_binding":bool(candidate_legal_guard is not None and candidate_legal_guard_error is None),
      "candidate_legal_guard_binding_error":candidate_legal_guard_error,
      "detailed_legal_review_exact":bool(candidate_legal_guard is not None and candidate_legal_guard_error is None) and all(
          ((candidate_legal_records or {}).get(str(k).split("|",1)[0]) or {}).get("status")=="PASS"
          for k,v in results.items()
          if detailed_legal_required_for_technical_state(v.get("result"))
          or detailed_legal_required_for_technical_state(v.get("technical_prelegal_result"))
      ),
      "adr_ratio_bridge_path":relpath(ADR_RATIO_BRIDGE) if ADR_RATIO_BRIDGE.exists() else None,
      "adr_ratio_bridge_blob_sha":blob_sha(ADR_RATIO_BRIDGE) if ADR_RATIO_BRIDGE.exists() else None,
      "lifecycle_registry":registry,
      "lifecycle_frozen_semantics_binding":current_frozen_binding,
      "lifecycle_semantics_exact":lifecycle_semantics_exact,
      "source_compiled_policy_hash":d.get("source_mc_policy_hash"),"source_compiled_policy_version":d.get("source_mc_policy_version"),
      "source_workflow_sha":os.getenv("GITHUB_SHA"),
      "semantic_impl_blobs":{
        "alpha_semantics.py":blob_sha(ROOT/"alpha_semantics.py"),
        "stage1_shadow.py":blob_sha(ROOT/"stage1_shadow.py"),
        "deep_pre_r1_shadow.py":blob_sha(ROOT/"deep_pre_r1_shadow.py"),
        "family_c_engine.py":blob_sha(ROOT/"family_c_engine.py"),
        "regime_breadth_shadow.py":blob_sha(ROOT/"regime_breadth_shadow.py"),
        "final_tech_shadow.py":blob_sha(Path(__file__).resolve())
      },
      "results":results,
      "policy_semantics_exact":policy_semantics_exact,
      "embedded_semantic_selftest":semantic_selftest_status,
      "semantic_audit_status":semantic_audit_status,
      "semantic_known_gaps":semantic_known_gaps,
      "corporate_semantics_unresolved_finalists":corporate_semantics_unresolved,
      "semantic_repairs":["ACTIVE_STRUCTURAL_R1_TRIGGER_MINUS1","FROZEN_RETEST_5_SESSION_REGISTRY",
                          "S0_POST_TRIGGER_BREACH","EXTENSION_CLOSE_T_MINUS_CLOSE_TMINUS3_WITH_RETEST_RESET",
                          "TRIGGER_MINUS1_WILDER_ATR","FAMILY_A_0P5A_INHERITED_CANONICAL_RULE",
                          "SPLIT_EVENT_RECONCILIATION","FINALIST_FRACTIONAL_SPLIT_VERIFICATION",
                          "ADR_RATIO_FAIL_CLOSED_BRIDGE","REGIME_FINALIST_GATE_ALL_FAMILIES",
                          "LIFECYCLE_REGIME_REVALIDATION_PRESERVED"],
      "remaining_nontech_gates":["OFFICIAL_EVENT_FINAL_REVIEW","ACCOUNT_GATE","G9","DELIVERY_PROOF"],
      "authority":"C4_17_DETERMINISTIC_TECHNICAL_FAIL_CLOSED"
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps(dict({k:out[k] for k in ["input_confirmed_family_candidates","pre_g9_tech_pass_count","watch_count","fail_count"]},
                          lifecycle_records=len(registry["records"]),provider_max_inflight=PROVIDER_MAX_INFLIGHT,retry_delays=RETRY_DELAYS),sort_keys=True))

if __name__=="__main__":
    main()
