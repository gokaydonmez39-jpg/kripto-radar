#!/usr/bin/env python3
"""Exact-current HISTORY root cause + bounded real-source recovery witness.

Never fabricates OHLCV, promotes UNKNOWN, creates AL, sends orders, or claims
that one successful source retry means a completed canonical research chain.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path

from sina_transport_rescue import choose as choose_transport_rescue
from sina_state_hash_guard import compute as checksum, seal as seal_state, verify as verify_state_hash

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_ROOT_HISTORY_RECOVERY_MICROAUDIT_V1"
STATIC={
    "SINA_DAILY_LT260_REQUIRES_INDEPENDENT_CONFIRMATION",
    "ASOF_MISSING_REQUIRES_RESOLUTION",
    "EXACT30_INCOMPLETE_NEVER_PASS",
}
TRANSIENT=("SyntaxError:","IndexError:","JSONDecodeError:","TimeoutError:",
           "ConnectionError:","HTTPError:")

def audit(state,root,now):
    if now.tzinfo is None:
        raise ValueError("NAIVE_DIAGNOSTIC_CLOCK")
    if not isinstance(state,dict) or not isinstance(root,dict):
        raise ValueError("ROOT_DATA_NOT_OBJECTS")
    if (state.get("schema")!="XRAY_NASDAQ_SCREENER_SINA_V2"
        or root.get("schema")!="XRAY_ORCHESTRATOR_V1"):
        raise ValueError("ROOT_SCHEMAS_INVALID")
    for o in (state,root):
        if o.get("execution")!="NONE" or o.get("real_money")!="NO-GO":
            raise ValueError("EXECUTION_SAFETY_DRIFT")
    if state.get("unknown_never_pass") is not True:
        raise ValueError("UNKNOWN_PASS_POLICY_DRIFT")
    asof=state.get("asof_et")
    if asof!=root.get("asof_et"):
        raise ValueError("ROOT_SINA_ASOF_DRIFT")
    if not isinstance(asof,str) or dt.date.fromisoformat(asof).isoformat()!=asof:
        raise ValueError("INVALID_ASOF_DATE")
    q=state.get("queue");rows=state.get("results")
    if not isinstance(q,list) or not isinstance(rows,dict):
        raise ValueError("HISTORY_QUEUE_OR_ROWS_MISSING")
    if (len(q)!=len(set(q)) or any(not isinstance(x,str) or not x for x in q)
        or set(q)!=set(rows)
        or state.get("cursor")!=len(q)
        or state.get("queue_total")!=len(q)):
        raise ValueError("HISTORY_QUEUE_PARTITION_NOT_EXACT")
    if state.get("queue_hash")!=hashlib.sha256("\n".join(q).encode()).hexdigest():
        raise ValueError("HISTORY_QUEUE_HASH_MISMATCH")
    hash_integrity=verify_state_hash(state)
    if hash_integrity not in ("PASS_DETERMINISTIC_BLOB_INTERNAL",
                             "LEGACY_HASH_NOT_INDEPENDENTLY_VERIFIABLE"):
        raise ValueError("HISTORY_STATE_HASH_MISMATCH")
    classified=collections.Counter()
    bystatus=collections.Counter()
    for symbol,row in rows.items():
        if not isinstance(row,dict):
            raise ValueError("HISTORY_ROW_NOT_OBJECT")
        status=row.get("status")
        if not isinstance(status,str):
            raise ValueError("HISTORY_STATUS_MISSING")
        bystatus[status]+=1
        if status=="UNKNOWN_STATIC":
            info=row.get("info")
            reason=info.get("reason") if isinstance(info,dict) else None
            if reason not in STATIC:
                raise ValueError("UNKNOWN_STATIC_REASON_UNCLASSIFIED:"+symbol)
            classified[reason]+=1
        elif status=="UNKNOWN_RETRY_EXHAUSTED":
            info=row.get("info")
            if not isinstance(info,str) or not info.startswith(TRANSIENT):
                raise ValueError("UNKNOWN_EXHAUSTED_NONTRANSIENT:"+symbol)
            if type(row.get("attempts")) is not int or row["attempts"]<4:
                raise ValueError("UNKNOWN_EXHAUSTED_WITHOUT_FOUR_ATTEMPTS:"+symbol)
            classified["EXHAUSTED_TRANSIENT_PROVIDER_EXCEPTION"]+=1
        elif status=="UNKNOWN_RETRY":
            classified["UNEXHAUSTED_RETRYABLE_UNKNOWN"]+=1
        elif status.startswith("UNKNOWN"):
            raise ValueError("UNRECOGNIZED_UNKNOWN_CLASS:"+symbol)
    unknown=sum(n for status,n in bystatus.items() if status.startswith("UNKNOWN"))
    if unknown!=state.get("unknown_count"):
        raise ValueError("SINA_UNKNOWN_COUNT_DRIFT")
    remaining=sum(1 for row in rows.values() if row.get("status")=="UNKNOWN_RETRY"
                  and row.get("attempts",99)<4)
    if remaining!=state.get("pending_retry"):
        raise ValueError("SINA_RETRY_COUNTER_DRIFT")
    if sum(bystatus.values())!=len(q):
        raise ValueError("HISTORY_CLASSIFICATION_SUM_DRIFT")
    root_status=root.get("status")
    if root_status=="PARTIAL_HISTORY":
        if state.get("status")!="HISTORY_PARTIAL" or unknown<=0:
            raise ValueError("PARTIAL_HISTORY_INCONSISTENT")
        if unknown!=root.get("unknown_count"):
            raise ValueError("ROOT_UNKNOWN_COUNT_DRIFT")
        if remaining!=root.get("pending_retry"):
            raise ValueError("RETRY_COUNTER_DRIFT")
        root_binding="PARTIAL_COUNTERS_EXACT"
    elif root_status in ("DATA_PLANE_PARTIAL_UNKNOWN",
                         "DATA_PLANE_PASS_CANONICAL_DOWNSTREAM_DEFERRED"):
        # In orchestrator_run.py, post-HISTORY root reports counts under
        # root.history, not at root level. Do not fail a genuinely COMPLETE
        # root simply because it lacks partial-only top-level counters.
        h=root.get("history")
        if (not isinstance(h,dict) or state.get("status")!="HISTORY_COMPLETE"
            or unknown!=0 or remaining!=0
            or h.get("status")!="HISTORY_COMPLETE"
            or h.get("queue_total")!=len(q)
            or h.get("queue_hash")!=state.get("queue_hash")
            or h.get("counts")!=state.get("counts")):
            raise ValueError("COMPLETE_HISTORY_ROOT_BINDING_MISMATCH")
        root_binding="COMPLETE_NESTED_HISTORY_EXACT_NOT_ALPHA"
    else:
        raise ValueError("ROOT_STATUS_UNRECOGNIZED")
    rescue=choose_transport_rescue(state,now)
    exhausted=classified["EXHAUSTED_TRANSIENT_PROVIDER_EXCEPTION"]
    if len(rescue)>min(32,exhausted):
        raise ValueError("RESCUE_OUT_OF_BOUNDS")
    return {
        "schema":SCHEMA,
        "asof_et":asof,
        "root_status":root["status"],
        "root_state_binding":root_binding,
        "source_state_hash_integrity":hash_integrity,
        "source_state_reproducible_hash":hash_integrity=="PASS_DETERMINISTIC_BLOB_INTERNAL",
        "input_symbols":len(q),
        "unknown_count":unknown,
        "known_status_counts":dict(sorted(bystatus.items())),
        "unknown_reason_counts":dict(sorted(classified.items())),
        "source_transport_exception_unknown_count":exhausted,
        "independent_history_or_asof_proof_required_count":(
            classified["SINA_DAILY_LT260_REQUIRES_INDEPENDENT_CONFIRMATION"]
            +classified["ASOF_MISSING_REQUIRES_RESOLUTION"]
            +classified["EXACT30_INCOMPLETE_NEVER_PASS"]),
        "eligible_single_round_real_provider_retries_now":len(rescue),
        "eligible_retry_symbol_count_only":len(rescue),
        "rescue_max_one_per_exact_epoch":True,
        "root_retryable_counter":remaining,
        "existing_root_retry_flag":root.get("history_retryable"),
        "source_proof_full_history_attested":False,
        "full_e2e_research_attested":False,
        "registered_r92_attested":False,
        "real_user_device_receipt_attested":False,
        "alpha_authority":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
        "scope":"ROOT_DIAGNOSTIC_ONLY_NEVER_PRIMARY_MC_OR_HISTORICAL_BAR_ATTESTATION",
    }

def selftest():
    def rec(status,info,attempts=1):
        return {"status":status,"info":info,"attempts":attempts,
                "transport_rescue_round":0,
                "updated_at_utc":"2026-10-09T21:05:00+00:00"}
    rows={"AAA":rec("PASS",{}),
          "BBB":rec("UNKNOWN_RETRY_EXHAUSTED","SyntaxError:HTTP html",4),
          "CCC":rec("UNKNOWN_STATIC",{"reason":"ASOF_MISSING_REQUIRES_RESOLUTION"})}
    queue=sorted(rows)
    s={"schema":"XRAY_NASDAQ_SCREENER_SINA_V2","execution":"NONE",
       "real_money":"NO-GO","unknown_never_pass":True,
       "asof_et":"2026-10-09","status":"HISTORY_PARTIAL",
       "queue":queue,"queue_total":3,"cursor":3,"results":rows,
       "queue_hash":hashlib.sha256("\n".join(queue).encode()).hexdigest(),
       "unknown_count":2,"pending_retry":0}
    seal_state(s)
    r={"schema":"XRAY_ORCHESTRATOR_V1","asof_et":"2026-10-09",
       "execution":"NONE","real_money":"NO-GO",
       "status":"PARTIAL_HISTORY","unknown_count":2,
       "pending_retry":0,"history_retryable":False}
    now=dt.datetime(2026,10,11,17,0,tzinfo=dt.timezone.utc)
    yes=audit(s,r,now)
    assert yes["eligible_single_round_real_provider_retries_now"]==1
    assert yes["independent_history_or_asof_proof_required_count"]==1
    assert yes["unknown_count"]==2 and not yes["alpha_authority"]
    import copy
    cases=[
        (lambda x,y:x.update(asof_et="2026-10-08"),"ROOT_SINA_ASOF_DRIFT"),
        (lambda x,y:x.update(unknown_count=0),"SINA_UNKNOWN_COUNT_DRIFT"),
        (lambda x,y:x["results"]["BBB"].update(status="PASS"),"ROOT_UNKNOWN_COUNT_DRIFT"),
        (lambda x,y:x["results"]["CCC"].update(info={"reason":"FAKE_PASS"}),"UNKNOWN_STATIC_REASON_UNCLASSIFIED"),
        (lambda x,y:x["results"]["BBB"].update(attempts=2),"UNKNOWN_EXHAUSTED_WITHOUT_FOUR_ATTEMPTS"),
        (lambda x,y:x["results"].pop("CCC"),"HISTORY_QUEUE_PARTITION_NOT_EXACT"),
        (lambda x,y:x.update(execution="TRADE"),"EXECUTION_SAFETY_DRIFT"),
        (lambda x,y:y.update(pending_retry=2),"RETRY_COUNTER_DRIFT"),
        (lambda x,y:x.update(state_hash="f"*64),"HISTORY_STATE_HASH_MISMATCH"),
    ]
    for mutation,code in cases:
        x,y=copy.deepcopy(s),copy.deepcopy(r)
        mutation(x,y)
        if code!="HISTORY_STATE_HASH_MISMATCH":
            seal_state(x)  # semantics tested independently from integrity guard
        try:audit(x,y,now)
        except ValueError as ex:
            assert code in str(ex),(code,str(ex))
        else:raise AssertionError("INVALID_HISTORY_MUTATION_WAS_ACCEPTED:"+code)
    # A fully completed source must NEVER be rejected by the partial-only
    # counter expectations; however a falsified COMPLETE claim is rejected.
    good=copy.deepcopy(s)
    good["results"]={key:rec("PASS",{}) for key in queue}
    good["status"]="HISTORY_COMPLETE"
    good["counts"]={"PASS":len(queue)}
    good["unknown_count"]=0
    good["pending_retry"]=0
    seal_state(good)
    full=copy.deepcopy(r)
    full["status"]="DATA_PLANE_PASS_CANONICAL_DOWNSTREAM_DEFERRED"
    full.pop("unknown_count")
    full.pop("pending_retry")
    full["history"]={"status":"HISTORY_COMPLETE",
                     "queue_total":len(queue),
                     "queue_hash":good["queue_hash"],
                     "counts":good["counts"]}
    accepted=audit(good,full,now)
    assert accepted["root_state_binding"]=="COMPLETE_NESTED_HISTORY_EXACT_NOT_ALPHA"
    assert accepted["unknown_count"]==0 and not accepted["full_e2e_research_attested"]
    assert accepted["source_proof_full_history_attested"] is False
    wrong=copy.deepcopy(full)
    wrong["history"]["queue_hash"]="a"*64
    try:audit(good,wrong,now)
    except ValueError as ex:
        assert "COMPLETE_HISTORY_ROOT_BINDING_MISMATCH" in str(ex)
    else:raise AssertionError("FALSE_COMPLETE_ROOT_HASH_ACCEPTED")
    wrong=copy.deepcopy(full)
    wrong["history"]["counts"]={"PASS":1}
    try:audit(good,wrong,now)
    except ValueError as ex:
        assert "COMPLETE_HISTORY_ROOT_BINDING_MISMATCH" in str(ex)
    else:raise AssertionError("FALSE_COMPLETE_ROOT_COUNTS_ACCEPTED")
    old=copy.deepcopy(s)
    old.pop("state_hash_version")
    assert audit(old,r,now)["source_state_hash_integrity"]=="LEGACY_HASH_NOT_INDEPENDENTLY_VERIFIABLE"
    try:audit(s,r,now.replace(tzinfo=None))
    except ValueError:pass
    else:raise AssertionError("NAIVE_CLOCK_ACCEPTED")
    print("XRAY_ROOT_HISTORY_RECOVERY_SELFTEST=PASS_12_NEGATIVES_COMPLETE_SOURCE_NESTED_ROOT_LEGACY_HASH_NO_AL")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:selftest();return
    if not args.out:p.error("--out required")
    d=audit(json.loads((ROOT/"sina_state.json").read_text()),
            json.loads((ROOT/"orchestrator_state.json").read_text()),
            dt.datetime.now(dt.timezone.utc))
    args.out.write_text(json.dumps(d,sort_keys=True,indent=2)+"\n")
    print("XRAY_ROOT_HISTORY_REAL_PROVIDER_RECOVERY_ELIGIBLE="+
          str(d["eligible_single_round_real_provider_retries_now"]))
    print("XRAY_ROOT_HISTORY_INDEPENDENT_PROOF_MISSING="+
          str(d["independent_history_or_asof_proof_required_count"]))
    print("XRAY_ROOT_HISTORY_UNKNOWN_COUNTS="+
          json.dumps(d["unknown_reason_counts"],sort_keys=True))
    print("XRAY_ROOT_HISTORY_STATE_HASH_INTEGRITY="+d["source_state_hash_integrity"])
    print("XRAY_ROOT_HISTORY_ALPHA=NOT_AUTHORIZED")

if __name__=="__main__":main()
