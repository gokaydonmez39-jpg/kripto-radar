#!/usr/bin/env python3
"""Full 515 corporate-action complete vs all quality comparison (SHADOW).

Provider default complete omits incomplete events. Both views and source
identifiers remain in RAM only; counts and affected ticker names are persisted.
Even all has no publication-time or independent issuer completeness guarantee.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,json,os
from pathlib import Path
from alpaca_full_scope_260_shadow import scope,PRICE,MASTER
from alpaca_full_scope_ca_shadow import request_page,KNOWN_GROUPS,SUBJECT_FIELDS,MAX_PAGES,BATCH_SIZE
from alpaca_free_sip_shadow_guard import blob_sha,sufficient_delay
SCHEMA="XRAY_515_CA_COMPLETE_ALL_INCOMPLETE_SHADOW_V1"
UTC=dt.timezone.utc
SPLITS={"forward_splits","reverse_splits","unit_splits"}

def require(ok,reason):
    if not ok:raise ValueError("XRAY_CA_QUALITY:"+reason)

def collect(targets,start,asof,mode,fetch):
    require(mode in ("complete","all"),"BAD_MODE")
    events={}
    incomplete=collections.Counter()
    fault=None
    pages=0
    for offset in range(0,len(targets),BATCH_SIZE):
        batch=targets[offset:offset+BATCH_SIZE]
        cursor=None;seen=set()
        try:
            for _ in range(MAX_PAGES):
                payload=fetch(batch,start,asof,cursor,mode)
                require(type(payload) is dict and
                        type(payload.get("corporate_actions")) is dict,
                        "MALFORMED_PROVIDER_RESPONSE")
                for group,rows in payload["corporate_actions"].items():
                    require(group in KNOWN_GROUPS and type(rows) is list,
                            "UNKNOWN_VENDOR_CA_SCHEMA")
                    for e in rows:
                        require(type(e) is dict,"INVALID_EVENT_OBJECT")
                        uid=e.get("id")
                        if type(uid) is not str or not uid:
                            incomplete["missing_id"]+=1
                            continue
                        date=e.get("process_date")
                        if type(date) is not str or not start<=date<=asof:
                            incomplete["missing_or_outside_process_date"]+=1
                        subjects={e[k] for k in SUBJECT_FIELDS
                                  if type(e.get(k)) is str and e[k] in targets}
                        if not subjects:
                            incomplete["no_target_symbol"]+=1
                        value=(group,tuple(sorted(subjects)))
                        if uid in events:
                            require(events[uid]==value,"DUPLICATE_EVENT_ID_CONFLICT")
                            continue
                        events[uid]=value
                pages+=1
                nxt=payload.get("next_page_token")
                if nxt in (None,""):
                    cursor=None
                    break
                require(type(nxt) is str and 0<len(nxt)<=2048
                        and nxt not in seen and nxt!=cursor,
                        "INVALID_PAGE_TOKEN")
                seen.add(nxt);cursor=nxt
            else:
                raise ValueError("XRAY_CA_QUALITY:MAX_PAGE_BUDGET")
        except (ValueError,RuntimeError,TypeError,KeyError) as err:
            fault=str(err).split(":")[0][:60]
            break
    return events,incomplete,pages,fault

def compare(targets,completed,all_events,asof):
    a,ai,ap,af=all_events;c,ci,cp,cf=completed
    require(type(targets) is list and targets==sorted(set(targets))
            and len(targets)==515 and "QQQ" in targets,
            "WRONG_515_CANONICAL_SET")
    additional=set(a)-set(c)
    dropped=set(c)-set(a)
    symbols=set();nonsplit=set()
    for uid in additional:
        group,parties=a[uid]
        symbols.update(parties)
        if group!="cash_dividends" and group not in SPLITS:
            nonsplit.update(parties)
    return {
       "schema":SCHEMA,"asof_et":asof,
       "status":("SHADOW_QUALITY_BOTH_515_SCOPES_CLOSED" if
                 af is None and cf is None and not dropped else
                 "UNKNOWN_CA_QUALITY_NOT_CONSISTENT"),
       "source_scope_with_qqq":len(targets),
       "complete_event_ids":len(c),"all_event_ids":len(a),
       "all_not_in_complete":len(additional),
       "complete_missing_from_all":len(dropped),
       "new_all_affected_tickers":sorted(symbols),
       "new_all_nonsplit_affected_tickers":sorted(nonsplit),
       "all_missing_id":ai["missing_id"],
       "all_missing_or_outside_process_date":ai["missing_or_outside_process_date"],
       "all_no_target_symbol":ai["no_target_symbol"],
       "complete_missing_id":ci["missing_id"],
       "all_pages":ap,"complete_pages":cp,
       "all_source_error_class":af,"complete_source_error_class":cf,
       "event_creation_PIT_or_independent_issuer_attested":False,
       "zero_observed_events_proves_no_CA":False,
       "canonical_HISTORY_PASS_created":0,"C417_PRIMARY_MC_created":0,
       "R92_created":False,"GO":False,"execution":"NONE",
       "real_money":"NO-GO","unknown_never_pass":True,
       "provider_raw_events_ids_prices_not_persisted":True}

def selftest():
    targets=sorted(["QQQ"]+[f"ZZ{i:04d}" for i in range(514)])
    rows={"complete":[{"id":"SYN1","symbol":"ZZ0000",
                        "process_date":"2026-01-01"}],
          "all":[{"id":"SYN1","symbol":"ZZ0000",
                  "process_date":"2026-01-01"},
                 {"id":"SYN2","symbol":"ZZ0001",
                  "process_date":None}]}
    def fetch(batch,start,end,cursor,mode):
        return {"corporate_actions":{"name_changes":[
             e for e in rows[mode] if e["symbol"] in batch]},
             "next_page_token":None}
    c=collect(targets,"2025-09-29","2026-10-09","complete",fetch)
    a=collect(targets,"2025-09-29","2026-10-09","all",fetch)
    good=compare(targets,c,a,"2026-10-09")
    require(good["all_not_in_complete"]==1 and
            good["all_missing_or_outside_process_date"]==1 and
            good["new_all_nonsplit_affected_tickers"]==["ZZ0001"] and
            good["canonical_HISTORY_PASS_created"]==0,
            "REAL_INCOMPLETE_NOT_DETECTED")
    bad=compare(targets,a,c,"2026-10-09")
    require(bad["status"]=="UNKNOWN_CA_QUALITY_NOT_CONSISTENT"
            and bad["complete_missing_from_all"]==1,
            "QUALITY_NOT_SUPERSET_MUST_BLOCK")
    rows["all"]=[{"id":"SYN1","symbol":"ZZ0000","process_date":"2026-01-01"},
                 {"id":"SYN1","symbol":"ZZ0001","process_date":"2026-01-01"}]
    clash=collect(targets,"2025-09-29","2026-10-09","all",fetch)
    require(clash[3] is not None,"CONFLICTING_CA_EVENT_MUST_BLOCK")
    def unknown(*args):
        return {"corporate_actions":{"NEW_UNSUPPORTED_TYPE":[]},
                "next_page_token":None}
    require(collect(targets,"2025-09-29","2026-10-09","all",unknown)[3] is not None,
            "UNKNOWN_GROUP_MUST_BLOCK")
    print("XRAY_515_CA_ALL_QUALITY_SELFTEST=PASS_2_POSITIVE_2_NEGATIVE_PYTHON_O_SAFE")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:return selftest()
    require(args.out is not None,"OUT_REQUIRED")
    price=json.loads(PRICE.read_text());master=json.loads(MASTER.read_text())
    asof,targets,daily,weeks=scope(price,master)
    key=os.getenv("XRAY_ALPACA_DATA_KEY_ID","")
    secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY","")
    require(key and secret and sufficient_delay(asof,dt.datetime.now(UTC)),
            "ALPACA_DATA_ACCESS_OR_SETTLEMENT")
    fetch=lambda batch,start,end,cursor,mode:request_page(
        batch,start,end,key,secret,cursor,data_quality=mode)
    complete=collect(targets,daily[0],asof,"complete",fetch)
    all_events=collect(targets,daily[0],asof,"all",fetch)
    result=compare(targets,complete,all_events,asof)
    result["source_price_blob_sha"]=blob_sha(PRICE)
    result["source_master_blob_sha"]=blob_sha(MASTER)
    result["source_price_pass_hash"]=price["pass_hash"]
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_CA_COMPLETE_ALL_515_COUNTS="+json.dumps({
        k:result[k] for k in ("complete_event_ids","all_event_ids",
            "all_not_in_complete","complete_missing_from_all")},sort_keys=True))
    print("XRAY_CA_COMPLETE_ALL_515_STATUS="+result["status"])
    print("XRAY_CA_PRIMARY_MC_HISTORY=ZERO")

if __name__=="__main__":main()
