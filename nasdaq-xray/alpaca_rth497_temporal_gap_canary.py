#!/usr/bin/env python3
"""Bounded 8-symbol original SIP 30Min gap clustering, research only.

No 497-symbol replay, zero fill, individual raw bars/identities in outputs,
canonical data mutation, personal trade execution or market GO promotion.
"""
from __future__ import annotations
import argparse
from collections import Counter
from alpaca_price_gap_minute_witness import observe as minute_observe, WITNESS_CODES
from alpaca_rth_trade_gap_witness import probe as trade_probe, STATES as TRADE_STATES
import datetime as dt
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo
from alpaca_full_universe_asof_sip_availability import historical_request_window, sha
from alpaca_personal_price_current_exact30 import dates30
from alpaca_rth_minute_integrity_shadow import official_window
from alpaca_sip_30min_rth_lower_bound_pilot import stamp, data_check
from alpaca_sip_paginated_transport_shadow import SYMBOL_RE
from source_epoch_freshness_guard import last_complete_session

SCHEMA="XRAY_RTH497_TEMPORAL_CLUSTER_RESEARCH_V1"
PARENT="XRAY_PERSONAL_JOINT_HISTORY_DAILY30_EXACT_RTH30_BOUND_V1"
ROOT=Path(__file__).resolve().parent
NY=ZoneInfo("America/New_York")
CANARY=8
MAX_CALLS=16
MAX_MINUTE_WITNESS_CALLS=12
MAX_TRADE_PRINT_WITNESS_CALLS=8
MAX_BYTES=3500000
PARENT_RUN=None  # Never bind an archival workflow run as current.

def need(ok,why):
    if not ok: raise ValueError("XRAY_RTH497_TEMPORAL_"+why)

def sample_from_parent(p,now):
    """Prioritize four *actual* integrity gaps and four ambiguous controls.

    The parent artifact must come from a separately authenticated successful
    main GH run. Four missing-slot symbols are not allowed to disappear into
    the 415 research-high proxy population. No original OHLCV is stored.
    """
    need(type(p) is dict and type(now) is dt.datetime and
         now.tzinfo is not None and now.utcoffset() is not None,
         "INPUT")
    asof=p.get("asof_et")
    need(type(asof) is str and asof==last_complete_session(now),
         "FRESH_ASOF")
    need(p.get("schema")==PARENT and p.get("joint_cohort_count")==497
         and p.get("rth_incomplete_or_unknown_count")==4
         and p.get("rth_ambiguous_shadow_count")==78
         and p.get("rth_lower_bound_ge50m_shadow_count")==415
         and p.get("rth_integrity_cause_counts")=={
           "EARLY_AND_FULL_BAR_COUNTS_EXACT":4}
         and p.get("source_stop_class") is None
         and p.get("partial_research_never_promotes_strict_rth") is True
         and p.get("source_rights_not_inferred") is True
         and p.get("vendor_ohlcv_persisted") is False
         and p.get("registered_R92_count")==0
         and p.get("official_c417_primary_dv30_attested") is False
         and p.get("official_RTH_close_auction_volume_attested") is False
         and p.get("official_RTH_corrections_attested") is False
         and p.get("execution")=="NONE" and p.get("real_money")=="NO-GO",
         "PARENT_PROVENANCE")
    labels=p.get("classifications")
    causes=p.get("symbol_rth_integrity_failure_codes")
    partial=p.get("partial_missing_slot_research_by_symbol")
    need(type(labels) is dict and type(causes) is dict and
         type(partial) is dict and len(labels)==497 and
         set(causes)==set(partial) and len(causes)==4 and
         all(x=="EARLY_AND_FULL_BAR_COUNTS_EXACT" for x in causes.values()),
         "PARENT_EXACT_FOUR_INTEGRITY_GAPS")
    syms=sorted(labels)
    need(all(type(s) is str and SYMBOL_RE.fullmatch(s) for s in syms)
         and p.get("joint_history260_daily30_cohort_sha256")==sha(syms),
         "PARENT_SHA")
    high=sorted(s for s,v in labels.items()
                if v=="LOWER_BOUND_GE_50M_SHADOW")
    mid=sorted(s for s,v in labels.items()
               if v=="AMBIGUOUS_BETWEEN_BOUNDS_SHADOW")
    unknown=sorted(s for s,v in labels.items()
               if v=="UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW")
    need(len(high)==415 and len(mid)==78 and len(unknown)==4
         and unknown==sorted(causes)
         and all(partial[s].startswith("PARTIAL_OBSERVED_RTH_BARLOW_")
                 for s in unknown),
         "STRICT_415_78_4_DISJOINT_PARTITION")
    # Disperse ambiguity controls, avoid re-querying the 415 proxy highs.
    middle=[mid[(len(mid)-1)*i//3] for i in range(4)]
    selected=sorted(unknown+middle)
    need(len(set(selected))==CANARY and len(selected)==8,
         "TARGETED_CANARY_CARDINALITY")
    return asof,selected,dates30(asof)


def retrieve(symbols,days,asof,now,credentials,opener=urllib.request.urlopen):
    need(type(symbols) is list and len(symbols)==CANARY
         and symbols==sorted(set(symbols))
         and all(SYMBOL_RE.fullmatch(s) for s in symbols)
         and type(days) is list and len(days)==30 and days[-1]==asof
         and type(credentials) is tuple and len(credentials)==2
         and all(type(x) is str and x for x in credentials),
         "RETRIEVAL_SCOPE")
    _,end=historical_request_window(asof,now)
    start=dt.datetime.combine(dt.date.fromisoformat(days[0]),
                              dt.time(),NY).isoformat(timespec="seconds")
    need(start<end,"TIME_WINDOW")
    results={s:[] for s in symbols}
    used={s:set() for s in symbols}
    tokens=set()
    token=None
    count=0
    for _ in range(MAX_CALLS):
        q={"symbols":",".join(symbols),"timeframe":"30Min","feed":"sip",
           "adjustment":"raw","sort":"asc","start":start,"end":end,
           "limit":"10000","asof":asof}
        if token is not None:q["page_token"]=token
        req=urllib.request.Request(
          "https://data.alpaca.markets/v2/stocks/bars?"+
            urllib.parse.urlencode(q),
          headers={"APCA-API-KEY-ID":credentials[0],
                   "APCA-API-SECRET-KEY":credentials[1],
                   "Accept":"application/json"})
        count+=1
        try:
            with opener(req,timeout=40) as response:
                need(response.status==200,"HTTP_NON200")
                raw=response.read(MAX_BYTES+1)
        except urllib.error.HTTPError as exc:
            raise RuntimeError("ALPACA_HTTP_"+str(exc.code)) from exc
        except (urllib.error.URLError,TimeoutError,OSError) as exc:
            raise RuntimeError("ALPACA_NETWORK_OR_TIMEOUT") from exc
        need(len(raw)<=MAX_BYTES,"RESPONSE_OVERSIZE")
        try:doc=json.loads(raw)
        except (TypeError,ValueError) as exc:
            raise ValueError("XRAY_RTH497_TEMPORAL_JSON_INVALID") from exc
        need(type(doc) is dict and type(doc.get("bars")) is dict,
             "RESPONSE_SCHEMA")
        added=0
        for sym,bars in doc["bars"].items():
            need(sym in results and type(bars) is list,
                 "FOREIGN_OR_INVALID_SYMBOL")
            for bar in bars:
                need(type(bar) is dict and type(bar.get("t")) is str
                     and bar["t"] and bar["t"] not in used[sym],
                     "DUPLICATE_OR_INVALID_BAR")
                used[sym].add(bar["t"])
                results[sym].append(bar)
                added+=1
                need(len(results[sym])<=1100,"SYMBOL_ROWS_UNBOUNDED")
        nxt=doc.get("next_page_token")
        if nxt is None:return results,count
        need(type(nxt) is str and 0<len(nxt)<2048 and nxt not in tokens
             and added>0,"PAGINATION_NO_PROGRESS")
        tokens.add(nxt)
        token=nxt
    raise ValueError("XRAY_RTH497_TEMPORAL_BUDGET_EXHAUSTED_NO_PROMOTION")

def classify_aggregates(asof,syms,days,bars,calls,*,parent_run_id=0):
    need(len(syms)==CANARY and syms==sorted(set(syms))
         and type(bars) is dict and set(bars)==set(syms)
         and len(days)==30 and days[-1]==asof,"AGGREGATE_INPUT")
    grid={}
    windows={}
    for day in days:
        start,close,minutes=official_window(day)
        need(minutes in (210,390) and minutes%30==0,"SESSION_LENGTH")
        windows[day]=(start,close)
        for i in range(minutes//30):
            when=start+dt.timedelta(minutes=30*i)
            need(when not in grid,"DUPLICATE_OFFICIAL_SLOT")
            grid[when]=(day,i)
    late=Counter()
    older=Counter()
    nlate=0
    nolder=0
    pairs=0
    full=0
    empty=0
    for sym in syms:
        need(type(bars[sym]) is list,"BAR_LIST")
        got=set()
        for bar in bars[sym]:
            t=stamp(bar)
            if t in grid:
                need(t not in got,"DUPLICATE_RTH_SLOT")
                data_check(bar)
                got.add(t)
            elif any(a<=t<b for a,b in windows.values()):
                raise ValueError("XRAY_RTH497_TEMPORAL_OFFGRID_RTH")
        if not got:empty+=1
        missing=set(grid)-got
        if not missing:full+=1
        sessions=set()
        for moment in missing:
            day,index=grid[moment]
            sessions.add(day)
            (late if day==asof else older)[index]+=1
        pairs+=len(sessions)
        nlate+=int(asof in sessions)
        nolder+=int(any(s!=asof for s in sessions))
    total=sum(late.values())+sum(older.values())
    out={"schema":SCHEMA,"asof_et":asof,"parent_run_id":parent_run_id,
         "cohort_size":497,"sample_size":CANARY,
         "selection":"TARGETED_FOUR_GAPS_PLUS_FOUR_AMBIGUITY_CONTROLS",
         "sample_digest_sha256":sha(syms),
         "source":"ALPACA_DELAYED_HISTORICAL_SIP_30MIN",
         "source_api_calls":calls,"call_budget":MAX_CALLS,
         "sample_missing_30min_slots":total,
         "latest_session_missing_slots":sum(late.values()),
         "earlier_sessions_missing_slots":sum(older.values()),
         "latest_missing_official_slot_indices":dict(sorted(late.items())),
         "earlier_missing_official_slot_indices":dict(sorted(older.items())),
         "symbols_missing_latest":nlate,"symbols_missing_earlier":nolder,
         "symbol_session_missing_pairs":pairs,
         "fully_complete_sample_symbols":full,"symbols_zero_rth_observed":empty,
         "no_missing_bar_zero_fill":True,
         "no_full_universe_extrapolation":True,
         "no_outage_causation_claim":True,
         "raw_vendor_ohlcv_stored":False,
         "official_rth_integrity_pass":False,
         "official_auction_verified":False,
         "source_rights_not_inferred":True,
         "canonical_unchanged":True,"watch_created":False,
         "registered_R92_count":0,
         "execution":"NONE","real_money":"NO-GO"}
    need(total==sum(late.values())+sum(older.values())
         and 0<=calls<=MAX_CALLS and 0<=nlate<=CANARY
         and 0<=nolder<=CANARY,"AGGREGATE_ACCOUNTING")
    return out

def probe_only_actual_missing_rth_slots(asof,days,bar_map,parent,credentials,
                                        *,observer=minute_observe,
                                        budget=MAX_MINUTE_WITNESS_CALLS,
                                        trade_observer=trade_probe,
                                        trade_budget=MAX_TRADE_PRINT_WITNESS_CALLS):
    """Extra 1Min SIP only for previously missing 30Min slots in four gaps.

    This second TIMEFRAME is a same-provider diagnostic, not independent
    auction/trade-condition evidence; it never repairs 30Min/DV30 or persists
    vendor bars. An injected observer is used for offline negative tests.
    """
    errors=parent.get("symbol_rth_integrity_failure_codes")
    need(type(errors) is dict and len(errors)==4 and
         all(x=="EARLY_AND_FULL_BAR_COUNTS_EXACT" for x in errors.values())
         and set(errors).issubset(bar_map) and
         type(budget) is int and 0<=budget<=12 and
         type(trade_budget) is int and 0<=trade_budget<=8 and
         type(credentials) is tuple and len(credentials)==2 and
         all(type(v) is str and v for v in credentials),
         "MINUTE_WITNESS_TARGET_SCOPE_OR_BUDGET")
    grid=set()
    for day in days:
        start,close,minutes=official_window(day)
        need(minutes in (210,390) and minutes%30==0,
             "MINUTE_WITNESS_OFFICIAL_GRID")
        grid.update(start+dt.timedelta(minutes=i*30)
                    for i in range(minutes//30))
    counter=[0]
    counts=Counter()
    trade_counts=Counter()
    trade_used=0
    missing_total=0
    for sym in sorted(errors):
        got=set()
        for row in bar_map[sym]:
            t=stamp(row)
            if t in grid:got.add(t)
        missing=sorted(grid-got)
        missing_total+=len(missing)
        for slot in missing:
            if counter[0]>=budget:
                counts["MINUTE_GLOBAL_BUDGET_BLOCKED"]+=1
            else:
                value=observer(sym,slot,asof,credentials,counter,budget)
                need(value in WITNESS_CODES and 0<=counter[0]<=budget,
                     "MINUTE_WITNESS_RESULT_CODE_OR_CALL_OVERRUN")
                counts[value]+=1
            if trade_used>=trade_budget:
                trade_counts["TRADE_WITNESS_BUDGET_BLOCKED_NO_CALL"]+=1
            else:
                # Official historical single-stock trades API; same Alpaca SIP
                # source is a transport crosscheck, not licensed primary proof.
                result=trade_observer(sym,slot,asof,credentials)
                need(result in TRADE_STATES,"TRADE_WITNESS_ENUM_ONLY")
                if result!="TRADE_SCOPE_REJECTED_NO_CALL":
                    trade_used+=1
                trade_counts[result]+=1
    need(sum(counts.values())==missing_total and
         sum(trade_counts.values())==missing_total and
         0<=trade_used<=trade_budget,
         "GAP_VS_MINUTE_VS_TRADE_EXACT_PARTITION")
    return {
        "minute_witness_target_group":"FOUR_RTH_INTEGRITY_GAPS_ONLY",
        "minute_witness_30min_missing_slots_total":missing_total,
        "minute_witness_source_api_calls":counter[0],
        "minute_witness_call_budget":budget,
        "minute_witness_result_counts":dict(sorted(counts.items())),
        "minute_witness_present_not_canonical_repair_count":
            counts.get("MINUTE_BAR_PRESENT_COARSE_BAR_MISSING_SHADOW",0)+
            counts.get("MULTI_ROUTE_MINUTE_VALID_BAR_OBSERVED_SHADOW",0),
        "minute_witness_no_independent_venue_or_trade_conditions":True,
        "minute_witness_vendor_rows_persisted":False,
        "minute_witness_can_upgrade_c417_or_r92":False,
        "historical_trade_witness_source_api_calls":trade_used,
        "historical_trade_witness_call_budget":trade_budget,
        "historical_trade_witness_result_counts":dict(sorted(trade_counts.items())),
        "historical_trade_sample_present_no_volume_authority_count":
            trade_counts.get("TRADE_RECORD_PRESENT_AGGREGATE_BAR_MISSING_RESEARCH_ONLY",0),
        "historical_trade_prints_vendor_rows_persisted":False,
        "historical_trade_source_rights_and_sale_conditions_verified":False,
        "historical_trade_witness_can_upgrade_c417_or_r92":False
    }


def selftest():
    from copy import deepcopy
    asof="2026-10-15"
    now=dt.datetime(2026,10,15,23,30,tzinfo=dt.timezone.utc)
    names=[f"X{i:03}" for i in range(497)]
    classes={s:("LOWER_BOUND_GE_50M_SHADOW" if i<415 else
                "AMBIGUOUS_BETWEEN_BOUNDS_SHADOW" if i<493 else
                "UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW")
             for i,s in enumerate(names)}
    gaps=names[493:]
    p={"schema":PARENT,"asof_et":asof,"joint_cohort_count":497,
       "joint_history260_daily30_cohort_sha256":sha(names),
       "rth_incomplete_or_unknown_count":4,
       "rth_ambiguous_shadow_count":78,
       "rth_lower_bound_ge50m_shadow_count":415,
       "rth_integrity_cause_counts":{"EARLY_AND_FULL_BAR_COUNTS_EXACT":4},
       "source_stop_class":None,
       "partial_research_never_promotes_strict_rth":True,
       "source_rights_not_inferred":True,"vendor_ohlcv_persisted":False,
       "registered_R92_count":0,
       "official_c417_primary_dv30_attested":False,
       "official_RTH_close_auction_volume_attested":False,
       "official_RTH_corrections_attested":False,
       "execution":"NONE","real_money":"NO-GO",
       "classifications":classes,
       "symbol_rth_integrity_failure_codes":
            dict.fromkeys(gaps,"EARLY_AND_FULL_BAR_COUNTS_EXACT"),
       "partial_missing_slot_research_by_symbol":
            dict.fromkeys(gaps,
                "PARTIAL_OBSERVED_RTH_BARLOW_NOTIONAL_PROXY_INDETERMINATE")}
    _,syms,days=sample_from_parent(p,now)
    need(len(syms)==CANARY and syms==sorted(syms),"SAMPLE_SORT")
    need(set(gaps).issubset(syms) and len(set(syms)-set(gaps))==4,
         "EXACT_FOUR_INTEGRITY_GAPS_TARGETED")
    for change in (lambda x:x.update(asof_et="2026-10-14"),
                   lambda x:x.update(registered_R92_count=1),
                   lambda x:x.update(joint_history260_daily30_cohort_sha256="x"*64),
                   lambda x:x["classifications"].pop(names[0])):
        bad=deepcopy(p);change(bad)
        try:sample_from_parent(bad,now)
        except ValueError:pass
        else:raise AssertionError("INVALID_PARENT_ACCEPTED")
    original={s:[] for s in syms}
    for day in days:
        start,_,minutes=official_window(day)
        for index in range(minutes//30):
            bar={"t":(start+dt.timedelta(minutes=index*30)).isoformat(),
                 "o":10,"h":11,"l":9,"c":10,"v":1000}
            for sym in syms:original[sym].append(bar)
    need(classify_aggregates(asof,syms,days,original,1)[
        "fully_complete_sample_symbols"]==8,"COMPLETE_FIXTURE")
    changed=deepcopy(original)
    start,_,_=official_window(asof)
    missing={start,start+dt.timedelta(minutes=30)}
    for sym in syms:
        changed[sym]=[bar for bar in changed[sym]
                      if dt.datetime.fromisoformat(bar["t"]) not in missing]
    first,_,_=official_window(days[2])
    changed[syms[0]]=[bar for bar in changed[syms[0]]
                      if dt.datetime.fromisoformat(bar["t"])!=first]
    report=classify_aggregates(asof,syms,days,changed,2)
    need(report["latest_session_missing_slots"]==16
         and report["earlier_sessions_missing_slots"]==1
         and report["symbols_missing_latest"]==8
         and report["symbols_missing_earlier"]==1
         and report["symbol_session_missing_pairs"]==9
         and report["latest_missing_official_slot_indices"]=={0:8,1:8}
         and not report["watch_created"]
         and report["registered_R92_count"]==0,"COMMON_DAY_GAP_PROOF")
    for corrupt in (lambda x:x[syms[0]].append(x[syms[0]][0]),
                    lambda x:x[syms[0]][0].update(v=0),
                    lambda x:x[syms[0]][0].update(
                      t="2026-10-15T14:31:00+00:00")):
        bad=deepcopy(original);corrupt(bad)
        try:classify_aggregates(asof,syms,days,bad,1)
        except ValueError:pass
        else:raise AssertionError("BAD_SOURCE_ACCEPTED")
    class Reply:
        status=200
        def __init__(self,j):self.data=json.dumps(j).encode()
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,n):return self.data[:n]
    def mock(req,timeout):
        q=urllib.parse.parse_qs(urllib.parse.urlparse(req.full_url).query)
        need(q["feed"]==["sip"] and q["timeframe"]==["30Min"]
             and q["symbols"]==[",".join(syms)]
             and q["adjustment"]==["raw"],"REQUEST_GUARD")
        need("FAKE_SECRET" not in req.full_url,"URL_SECRET_LEAK")
        return Reply({"bars":dict.fromkeys(syms,[]),"next_page_token":None})
    rows,count=retrieve(syms,days,asof,now,
                        ("FAKE_ID","FAKE_SECRET"),opener=mock)
    need(count==1 and len(rows)==8 and all(not x for x in rows.values()),
         "MOCK_TRANSPORT")
    # Check first missing slot of each of the four REAL parent gap identities
    # using a mocked 1Min SIP observer (zero external requests in PR CI).
    target=deepcopy(original)
    for sym in gaps:
        target[sym]=target[sym][1:]
    simulated=[]
    def fake_minute(sym,slot,date,keys,count,budget):
        need(sym in gaps and date==asof and slot.tzinfo is not None
             and count[0]<budget,"MINUTE_FIXTURE_EXACT_TARGET")
        count[0]+=1
        simulated.append(sym)
        return "MINUTE_BAR_PRESENT_COARSE_BAR_MISSING_SHADOW"
    checked=probe_only_actual_missing_rth_slots(
        asof,days,target,p,("FAKE_ID","FAKE_SECRET"),
        observer=fake_minute,budget=4,
        trade_observer=lambda *args:"NO_TRADE_RECORD_RETURNED_STILL_UNKNOWN",
        trade_budget=4)
    need(checked["minute_witness_source_api_calls"]==4 and
         checked["minute_witness_present_not_canonical_repair_count"]==4 and
         len(simulated)==4 and
         checked["minute_witness_can_upgrade_c417_or_r92"] is False,
         "FOUR_TARGETED_GAP_ONE_MINUTE_POSITIVE_NOT_PRIMARY")
    checked=probe_only_actual_missing_rth_slots(
        asof,days,target,p,("FAKE_ID","FAKE_SECRET"),
        observer=fake_minute,budget=2,
        trade_observer=lambda *args:"NO_TRADE_RECORD_RETURNED_STILL_UNKNOWN",
        trade_budget=2)
    need(checked["minute_witness_source_api_calls"]==2 and
         checked["minute_witness_result_counts"].get(
             "MINUTE_GLOBAL_BUDGET_BLOCKED")==2,
         "TARGETED_MINUTE_BUDGET_EXACT")
    need(checked["historical_trade_witness_source_api_calls"]==2 and
         checked["historical_trade_witness_result_counts"].get(
             "TRADE_WITNESS_BUDGET_BLOCKED_NO_CALL")==2 and
         checked["historical_trade_witness_can_upgrade_c417_or_r92"] is False,
         "TARGETED_TRADE_PRINT_BUDGET_EXACT")
    unauthorized=deepcopy(p)
    unauthorized["symbol_rth_integrity_failure_codes"].pop(gaps[0])
    try:
        probe_only_actual_missing_rth_slots(
            asof,days,target,unauthorized,("FAKE_ID","FAKE_SECRET"),
            observer=fake_minute,
            trade_observer=lambda *args:"NO_TRADE_RECORD_RETURNED_STILL_UNKNOWN")
    except ValueError:pass
    else:raise AssertionError("FORGED_GAP_SOURCE_ACCEPTED")
    print("XRAY_RTH497_TEMPORAL_CANARY_SELFTEST=PASS_8_SYMBOL_16_CALL_SHA_TIME_NEGATIVES_NO_ALPHA")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--parent",type=Path)
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:selftest();return
    need(args.parent is not None and args.parent.is_file()
         and args.out is not None
         and not args.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "EPHEMERAL_OUTPUT_ONLY")
    now=dt.datetime.now(dt.timezone.utc)
    source=json.loads(args.parent.read_text())
    asof,syms,days=sample_from_parent(source,now)
    credentials=(os.getenv("XRAY_ALPACA_DATA_KEY_ID","").strip(),
                 os.getenv("XRAY_ALPACA_DATA_SECRET_KEY","").strip())
    need(all(credentials),"RUNNER_CREDENTIALS_REQUIRED")
    parent_run_text=os.getenv("XRAY_AUTHENTICATED_RTH_PARENT_RUN_ID","")
    need(parent_run_text.isascii() and parent_run_text.isdecimal()
         and int(parent_run_text)>0,"EXACT_AUTHENTICATED_PARENT_RUN_REQUIRED")
    bars,calls=retrieve(syms,days,asof,now,credentials)
    out=classify_aggregates(asof,syms,days,bars,calls,
         parent_run_id=int(parent_run_text))
    # Only previously missing 30Min windows get a second, bounded 1Min
    # same-SIP-provider transport check. Not a substitute for official DV30.
    out.update(probe_only_actual_missing_rth_slots(
        asof,days,bars,source,credentials))
    args.out.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("XRAY_RTH497_TEMPORAL_CANARY="+json.dumps({
       "asof":asof,"canary":len(syms),
       "api_calls":calls,
       "latest_missing":out["latest_session_missing_slots"],
       "earlier_missing":out["earlier_sessions_missing_slots"],
       "latest_slots":out["latest_missing_official_slot_indices"],
       "minute_calls":out["minute_witness_source_api_calls"],
       "minute_windows_found":out["minute_witness_present_not_canonical_repair_count"],
       "trade_calls":out["historical_trade_witness_source_api_calls"],
       "trade_sample_present":out["historical_trade_sample_present_no_volume_authority_count"],
       "zero_alpha":True},sort_keys=True))

if __name__=="__main__":main()
