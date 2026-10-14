#!/usr/bin/env python3
"""Reproducible personal-study scan: exact ROOT 2026-10-13 cohort.

A full cohort is covered only when every validated slice has been measured and
an independent reducer verifies exact symbol sets/hashes. Every Alpaca
historical SIP value stays in process memory; only classifications and
source lineage are archived. Separate from C4.17 production and R92.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
import time
from pathlib import Path

from alpaca_free_sip_shadow_guard import (
    request_batch,sufficient_delay,timestamp_date,blob_sha,EST,UTC)
from current_history_source_request import expected_dates,sha256_lines
from alpaca_sip_paginated_transport_shadow import MAX_PAGES
import sec_official_free_mc_transport_probe as sec

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
POLICY=ROOT/"personal_research_technical_policy_v1.json"
STATE=ROOT/"sina_state.json"
LIMIT_MAX=32
UNKNOWN_PREFIX="UNKNOWN_"
def need(ok,code):
    if not ok:raise ValueError("PERSONAL_SCOPE_"+code)
def sha(s):
    return hashlib.sha256("\n".join(s).encode()).hexdigest()

def load():
    state=json.loads(STATE.read_text())
    policy=json.loads(POLICY.read_text())
    need(policy["schema"]=="XRAY_PERSONAL_RESEARCH_TECHNICAL_AUTHORITY_V1"
         and policy["activation"]=="RESEARCH_OUTPUT_ONLY_NOT_PRODUCTION_SWITCH"
         and policy["can_create_r92"] is True
         and policy.get("r92_registration_mode")=="INDEPENDENT_C417_RELEASE_APPROVAL_REQUIRED"
         and policy.get("r92_creation_requires_all_candidate_local_and_compiled_gates") is True
         and policy.get("can_update_compiled_C417_alpha") is True
         and policy.get("can_override_canonical_unknown") is True
         and policy.get("observational_evidence_never_equivalent_to_release_primary") is True
         and policy.get("canonical_unknown_override_semantics")=="ONLY_AFTER_NEW_EXACT_SAME_ASOF_PRIMARY_EVIDENCE_IS_INDEPENDENTLY_VERIFIED"
         and policy["can_override_canonical_unknown"] is False
         and policy["unknown_never_pass"] is True,"POLICY")
    queue=state.get("queue")
    rows=state.get("results")
    need(state.get("asof_et")==ASOF and state.get("status")=="HISTORY_PARTIAL"
         and state.get("unknown_never_pass") is True,"SOURCE_ASOF")
    need(type(queue) is list and queue==sorted(set(queue))
         and type(rows) is dict and set(rows)==set(queue)
         and len(queue)==state["queue_total"]==state["unknown_count"]==3185
         and all(str(rows[x].get("status","")).startswith("UNKNOWN") for x in queue),
         "CANONICAL_UNIVERSE")
    daily,weeks=expected_dates(ASOF)
    need(len(daily)==260 and daily[-1]==ASOF and len(weeks)==52
         and set(weeks).issubset(daily),"CALENDAR")
    return state,policy,queue,daily,weeks

def analyze(rows,daily,weeks):
    if not isinstance(rows,list):return "UNKNOWN_MISSING_PROVIDER_ROWS",None
    seen={}
    for row in rows:
        if not isinstance(row,dict):return "UNKNOWN_PROVIDER_BAR_FORMAT",None
        try:
            day=timestamp_date(row["t"]).isoformat()
            vals=[row[k] for k in ("o","h","l","c")]
            volume=row["v"]
        except (ValueError,KeyError,TypeError,AttributeError,OverflowError):
            return "UNKNOWN_DATE_OR_OHLC",None
        if not (all(type(v) in (float,int) and math.isfinite(v) and v>0 for v in vals)
                and type(volume) is int and volume>0):
            return "UNKNOWN_BAD_INTEGER_OHLCV",None
        o,h,l,c=vals
        if l>min(o,c) or h<max(o,c,l):
            return "UNKNOWN_OHLC_INTEGRITY",None
        if day in seen or day>ASOF:
            return "UNKNOWN_DUPLICATE_OR_LOOKAHEAD",None
        seen[day]=(c,volume)
    if not set(daily).issubset(seen):
        return "UNKNOWN_INSUFFICIENT_260_OFFICIAL_SESSIONS",None
    if not set(weeks).issubset(seen):
        return "UNKNOWN_MISSING_COMPLETED_52_WEEK_CLOSES",None
    expected30=daily[-30:]
    vals=sorted(seen[d][0]*seen[d][1] for d in expected30)
    dv=(vals[14]+vals[15])/2
    close=seen[ASOF][0]
    if close<5:return "TECH_FAIL_PRICE",{"dv":dv,"close":close}
    if dv<50_000_000:return "TECH_FAIL_DV30",{"dv":dv,"close":close}
    return ("PERSONAL_TECH_PRIMARY_HISTORY260_WEEK52_PRICE_DV30",
            {"dv":dv,"close":close})

def sec_share_math(symbol,close,asof,cik_map,ua):
    # Foreign or ambiguous issuer/class identities are not guessed.
    cik=cik_map.get(symbol)
    if not cik:return "MC_UNKNOWN_CIK_ROUTE"
    try:
        facts=sec.get_json("https://data.sec.gov/api/xbrl/companyfacts/CIK"+cik+".json",ua)
        time.sleep(0.36)
        sub=sec.get_json("https://data.sec.gov/submissions/CIK"+cik+".json",ua)
        time.sleep(0.36)
        a=sec.select_shares(facts,sub,asof,expected_cik=cik)
    except (ValueError,RuntimeError,TimeoutError) as exc:
        code=str(exc)
        if code in ("SEC_HTTP_403","SEC_HTTP_429"):
            raise RuntimeError("SEC_FAIR_ACCESS_HALT")
        return "MC_UNKNOWN_SEC_TRANSPORT"
    if a.get("status")!="SHADOW_SHARES_VINTAGE_ONLY":
        return "MC_UNKNOWN_"+str(a.get("reason","SEC_SHARES"))
    if not (isinstance(close,(float,int)) and math.isfinite(close) and close>0):
        return "MC_UNKNOWN_PRICE"
    # Match selected SEC observation date; never use future fact or a
    # different accession. SEC DEI entity shares are NOT proven listed-class
    # shares when dual-class/ADR/corporate-action details are absent.
    obs=a["observation_date"]
    candidates=[]
    for row in (((facts.get("facts") or {}).get("dei") or {})
                 .get("EntityCommonStockSharesOutstanding") or {}).get("units",{}).get("shares",[]):
        if row.get("end")==obs and type(row.get("val")) is int:
            try:filing=dt.date.fromisoformat(row["filed"])
            except (KeyError,TypeError,ValueError):continue
            if filing<=dt.date.fromisoformat(asof):candidates.append(row)
    if not candidates:
        return "MC_UNKNOWN_NO_MATCHING_SEC_OBSERVATION"
    vintages=sorted((r.get("filed",""),r.get("accn",""),r["val"]) for r in candidates)
    selected=max(v[0] for v in vintages)
    values={r[2] for r in vintages if r[0]==selected}
    if len(values)!=1:return "MC_UNKNOWN_SEC_VINTAGE_CONFLICT"
    mc=next(iter(values))*close
    if not math.isfinite(mc) or mc<=0:return "MC_UNKNOWN_ARITHMETIC"
    # The result reports a numerical classification but cannot claim
    # complete equity classes or an exchange-verified settlement close.
    if mc>=2_000_000_000:return "MC_MATH_ABOVE_2B_CLASS_PIT_UNRESOLVED"
    return "MC_MATH_BELOW_2B_CLASS_PIT_UNRESOLVED"

def cik_index(payload):
    fields=payload.get("fields")
    data=payload.get("data")
    need(type(fields) is list and type(data) is list,"SEC_MAP_SHAPE")
    need(all(k in fields for k in ("cik","ticker","exchange")),"SEC_MAP_FIELDS")
    ci,ti,ex=(fields.index(k) for k in ("cik","ticker","exchange"))
    map={}
    for rec in data:
        if not isinstance(rec,list) or len(rec)<=max(ci,ti,ex):continue
        sym=rec[ti];exch=rec[ex];cik=rec[ci]
        if exch not in ("Nasdaq","NASDAQ") or type(sym) is not str:continue
        if sym in map:map[sym]=None
        elif type(cik) is int and cik>0:map[sym]=str(cik).zfill(10)
    return map

def scan(offset,limit,do_mc=False,now=None,fetch=None,sec_fetch=None):
    state,policy,queue,daily,weeks=load()
    need(type(offset) is int and 0<=offset<len(queue)
         and type(limit) is int and 1<=limit<=LIMIT_MAX,"BOUNDS")
    symbols=queue[offset:offset+limit]
    need(len(symbols)==limit,"LAST_CHUNK_TRUNCATION")
    if now is None:now=dt.datetime.now(UTC)
    need(sufficient_delay(ASOF,now),"DELAY_NOT_ELAPSED")
    if fetch is None:
        key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or
             os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
        secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or
                os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
        need(key and secret,"ALPACA_PRIVATE_KEYS_MISSING")
        start=(dt.date.fromisoformat(daily[0])-dt.timedelta(days=8)).isoformat()
        start+="T00:00:00-04:00"
        end="2026-10-13T16:30:00-04:00"
        need(dt.datetime.fromisoformat(end)<now,"FUTURE_END")
        fetch=lambda syms:request_batch(syms,start,end,key,secret)
    cohort=fetch(symbols)
    need(type(cohort) is dict and set(cohort)<=set(symbols),"FOREIGN_SYMBOL")
    statuses={}
    metrics={}
    for sym in symbols:
        label,m=analyze(cohort.get(sym),daily,weeks)
        statuses[sym]=label
        if m is not None:metrics[sym]=m
    mc={}
    if do_mc:
        ua=os.getenv("XRAY_SEC_USER_AGENT","")
        need(sec.valid_operator_contact(ua),"SEC_CONTACT_REQUIRED")
        cik=cik_index((sec_fetch or sec.get_json)(
            "https://www.sec.gov/files/company_tickers_exchange.json",ua))
        for sym in symbols:
            if sym not in metrics or statuses[sym]!="PERSONAL_TECH_PRIMARY_HISTORY260_WEEK52_PRICE_DV30":
                mc[sym]="MC_NOT_EVALUATED_PRICE_HISTORY_NONPASS"
                continue
            try:mc[sym]=sec_share_math(sym,metrics[sym]["close"],ASOF,cik,ua)
            except RuntimeError as exc:
                if str(exc)=="SEC_FAIR_ACCESS_HALT":
                    mc[sym]="MC_UNKNOWN_SEC_FAIR_ACCESS_STOP"
                    for later in symbols[symbols.index(sym)+1:]:
                        mc[later]="MC_NOT_ATTEMPTED_FAIR_ACCESS_STOP"
                    break
                raise
    counts=dict(sorted(collections.Counter(statuses.values()).items()))
    mc_counts=dict(sorted(collections.Counter(mc.values()).items()))
    return {"schema":"XRAY_PERSONAL_RESEARCH_SLICE_ASOF260_V1",
        "asof_et":ASOF,"scope_total":len(queue),
        "source_sina_git_blob_sha":blob_sha(STATE),
        "source_technical_policy_git_blob_sha":blob_sha(POLICY),
        "source_sina_unknown":state["unknown_count"],
        "offset":offset,"slice_count":limit,"slice_symbols":symbols,
        "slice_sha256":sha(symbols),
        "scope_sha256":sha(queue),
        "daily_first":daily[0],"daily_last":daily[-1],
        "daily_count":len(daily),"completed_week_count":len(weeks),
        "source":"ALPACA_HISTORICAL_SIP_RAW_1DAY",
        "source_settlement_rth_volume_independently_attested":False,
        "source_corporate_actions_fully_reconciled":False,
        "mc_sec_dei_entity_shares_class_reconciled":False,
        "technical_research_only":True,"counts":counts,"statuses":statuses,
        "mc_requested":do_mc,"mc_counts":mc_counts,"mc_statuses":mc,
        "same_asof_sec_mc_only":True,
        "research_primary_statuses_do_not_create_c417_pass":True,
        "canonical_root_modified":False,"canonical_master_modified":False,
        "canonical_price_modified":False,"canonical_mc_modified":False,
        "canonical_history_modified":False,"r92_created":False,
        "strict_g9_pass":False,"account_pass":False,
        "full_cohort_coverage_claimed":False,"vendor_raw_bars_persisted":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def scan_all(*,do_mc=False,deadline_seconds=1260):
    state,policy,queue,daily,weeks=load()
    all_status={}
    all_mc={}
    done=0
    chunks=0
    errors=[]
    started=time.monotonic()
    for offset in range(0,len(queue),LIMIT_MAX):
        if time.monotonic()-started>=deadline_seconds:
            errors.append({"offset":offset,"remaining":len(queue)-offset,"reason":"BOUNDED_RUNNER_BUDGET_REACHED"})
            break
        limit=min(LIMIT_MAX,len(queue)-offset)
        try:
            part=scan(offset,limit,do_mc)
        except (RuntimeError,ValueError) as exc:
            # Preserve an explicit partial footprint and do not hammer a
            # blocked provider or skip a failed cohort.
            why=str(exc)
            errors.append({"offset":offset,"remaining":len(queue)-offset,
                           "reason":why if why.startswith((
                               "ALPACA_","SEC_","PERSONAL_SCOPE_"))
                           else "UPSTREAM_SOURCE_STOP"})
            break
        need(part["slice_symbols"]==queue[offset:offset+limit]
             and part["slice_count"]==limit
             and part["source_sina_git_blob_sha"]==blob_sha(STATE)
             and part["source_technical_policy_git_blob_sha"]==blob_sha(POLICY),
             "SLICE_EXACTNESS")
        need(not(set(part["statuses"])&set(all_status))
             and set(part["statuses"])==set(part["slice_symbols"]),
             "DUPLICATE_OR_MISSING")
        all_status.update(part["statuses"])
        all_mc.update(part["mc_statuses"])
        chunks+=1
        done+=limit
        # Lower vendor request pressure; cannot bypass a quota cliff.
        time.sleep(0.6)
    coverage=done==len(queue) and set(all_status)==set(queue)
    remain=queue[done:]
    return {"schema":"XRAY_PERSONAL_FULL_3185_EPOCH_STATUS_V1",
            "asof_et":ASOF,
            "source_sina_git_blob_sha":blob_sha(STATE),
            "source_technical_policy_git_blob_sha":blob_sha(POLICY),
            "source_root_unknown_before":state["unknown_count"],
            "source_root_scope_sha256":sha(queue),
            "scope_total":len(queue),"attempted_count":done,
            "remaining_count":len(remain),
            "remaining_scope_sha256":sha(remain),
            "completed_chunk_count":chunks,
            "coverage_complete":coverage,
            "source_errors":errors,
            "symbols_status_count":len(all_status),
            "symbol_statuses":all_status,
            "history_dv30_counts":dict(sorted(collections.Counter(
                all_status.values()).items())),
            "mc_requested":do_mc,
            "mc_status_count":len(all_mc),
            "mc_counts":dict(sorted(collections.Counter(all_mc.values()).items())),
            "mc_statuses":all_mc,
            "exact260_history_required":260,
            "exact52_completed_weeks_required":52,
            "real_provider_value_scope_verified":coverage,
            "corporate_action_class_chain_verified":False,
            "official_rth_daily_volume_lineage_independently_attested":False,
            "can_be_c417_primary":False,
            "can_register_r92":False,
            "no_canonical_artifacts_mutated":True,
            "raw_vendor_ohlcv_persisted":False,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def selftest():
    state,p,queue,daily,weeks=load()
    def bar(day):
        stamp=dt.datetime.combine(dt.date.fromisoformat(day),dt.time(),
                tzinfo=EST).astimezone(UTC).isoformat()
        return {"t":stamp,"o":25,"h":26,"l":24,"c":25,"v":4_000_000}
    bars=[bar(day) for day in daily]
    yes,m=analyze(bars,daily,weeks)
    need(yes=="PERSONAL_TECH_PRIMARY_HISTORY260_WEEK52_PRICE_DV30"
         and m["dv"]==100_000_000,"POSITIVE")
    case=[
       (bars[:-1],"UNKNOWN_INSUFFICIENT_260_OFFICIAL_SESSIONS"),
       (bars+[bars[-1]],"UNKNOWN_DUPLICATE_OR_LOOKAHEAD"),
       (bars[:-1]+[dict(bars[-1],v=1.5)],"UNKNOWN_BAD_INTEGER_OHLCV"),
       (bars[:-1]+[dict(bars[-1],h=2)],"UNKNOWN_OHLC_INTEGRITY"),
       (bars[:-1]+[dict(bars[-1],t="2026-10-14T04:00:00+00:00")],
        "UNKNOWN_DUPLICATE_OR_LOOKAHEAD"),
       (None,"UNKNOWN_MISSING_PROVIDER_ROWS")]
    for obj,expected in case:
        need(analyze(obj,daily,weeks)[0]==expected,"NEGATIVE_"+expected)
    not_liquid=[dict(x,c=1.0,o=1.0,h=1.1,l=0.9) for x in bars]
    need(analyze(not_liquid,daily,weeks)[0]=="TECH_FAIL_PRICE","PRICE_FAIL")
    low_dv=[dict(x,v=200_000) for x in bars]
    need(analyze(low_dv,daily,weeks)[0]=="TECH_FAIL_DV30","DV_FAIL")
    cohort={s:bars for s in queue[:4]}
    out=scan(0,4,now=dt.datetime(2026,10,14,tzinfo=UTC),
             fetch=lambda syms:{s:cohort[s] for s in syms})
    need(out["slice_count"]==4 and
         out["counts"]=={"PERSONAL_TECH_PRIMARY_HISTORY260_WEEK52_PRICE_DV30":4}
         and out["source_sina_unknown"]==3185 and
         out["r92_created"] is False and not out["full_cohort_coverage_claimed"],
         "FIXTURE_NO_PROMOTION")
    print("XRAY_PERSONAL_FULL_SCOPE_SELFTEST=PASS_2_POSITIVE_8_NEGATIVE_SLICE_SHA")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--offset",type=int,default=0)
    ap.add_argument("--limit",type=int,default=32)
    ap.add_argument("--sec-mc",action="store_true")
    ap.add_argument("--all",action="store_true")
    ap.add_argument("--deadline-seconds",type=int,default=1260)
    ap.add_argument("--out",type=Path)
    a=ap.parse_args()
    if a.selftest:
        need(a.out is None,"SELFTEST_OUTPUT")
        selftest();return
    need(a.out is not None and
         not a.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "REPORT_MUST_STAY_EPHEMERAL")
    need(60<=a.deadline_seconds<=1500,"RUNNER_BUDGET_INVALID")
    result=(scan_all(do_mc=a.sec_mc,deadline_seconds=a.deadline_seconds)
            if a.all else scan(a.offset,a.limit,a.sec_mc))
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("XRAY_PERSONAL_SLICE_COUNTS="+json.dumps(result["counts"],sort_keys=True))
    print("XRAY_PERSONAL_MC_COUNTS="+json.dumps(result["mc_counts"],sort_keys=True))
    print("XRAY_PERSONAL_NO_R92_PRIMARY_PRODUCTION=PASS")

if __name__=="__main__":main()
