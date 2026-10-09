#!/usr/bin/env python3
"""Prospective WATCH follow-up: 2/3/5/8-session outcome metrics, never AL.

The driver accepts PRIVATE, operator-licensed future OHLCV measurements only.
It writes aggregate metrics, never raw vendor market data or a trade instruction.
Synthetic scenarios occur strictly inside --selftest and cannot be counted live.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path

SCHEMA="XRAY_FORWARD_WATCH_PAPER_METRICS_V1"
HORIZONS=(2,3,5,8)


def finite(v):
    return type(v) in (int,float) and math.isfinite(v)


def parse_utc(value):
    if not isinstance(value,str):return None
    try:
        v=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return v.astimezone(dt.timezone.utc) if v.tzinfo else None
    except (ValueError,OverflowError):return None


def measure(watch,private,expected_session_dates):
    """Fail-closed: only real prospective registrations and subsequent sessions."""
    errors=[]
    def require(ok,reason):
        if not ok:errors.append(reason)
    require(isinstance(watch,dict) and watch.get("current_source_ready") is True
            and watch.get("status")=="PROSPECTIVE_RESEARCH_WATCH_ONLY",
            "WATCH_ORIGINAL_SOURCE_NOT_LIVE_VERIFIED")
    require(watch.get("alpha_authority") is False
            and watch.get("buy_candidates")==[]
            and watch.get("execution")=="NONE"
            and watch.get("real_money")=="NO-GO",
            "WATCH_SAFETY_INVALID")
    require(isinstance(private,dict) and private.get("schema")=="XRAY_PRIVATE_FORWARD_OBSERVATION_V1"
            and private.get("synthetic_fixture") is False,
            "PROVIDER_EVIDENCE_ORIGIN_INVALID")
    require(private.get("aggregation_rights_verified") is True
            and private.get("provenance_witness_verified") is True
            and private.get("corporate_actions_adjustment_basis_verified") is True
            and private.get("official_calendar_witness_verified") is True,
            "SOURCE_RIGHTS_OR_CORPORATE_ACTIONS_UNKNOWN")
    registered=parse_utc(private.get("registered_at_utc"))
    captured=parse_utc(private.get("captured_at_utc"))
    require(registered is not None and captured is not None
            and registered<=captured,"REGISTRATION_CLOCK_INVALID")
    origin=str(watch.get("asof_et") or "")
    require(private.get("asof_et")==origin,"ORIGIN_ASOF_MISMATCH")
    records=(watch.get("preentry_watch") or [])+(watch.get("prebreakout_b_armed_watch") or [])
    valid_keys={(r.get("symbol"),r.get("setup")) for r in records}
    require((private.get("symbol"),private.get("setup")) in valid_keys,
            "WATCH_CANDIDATE_NOT_PRE_REGISTERED")
    reference=private.get("reference_close")
    require(finite(reference) and reference>0,"REFERENCE_CLOSE_INVALID")
    costs=private.get("roundtrip_cost_bps")
    require(finite(costs) and 0<=costs<=500,"EXPLICIT_COST_BASIS_MISSING")
    rows=private.get("future_sessions") or []
    require(isinstance(rows,list) and len(rows)==8,"EXACT_EIGHT_FUTURE_SESSIONS_REQUIRED")
    require(isinstance(expected_session_dates,list) and len(expected_session_dates)==8
            and len(set(expected_session_dates))==8 and expected_session_dates==sorted(expected_session_dates)
            and all(isinstance(x,str) and x>origin for x in expected_session_dates),
            "OFFICIAL_EIGHT_SESSION_CALENDAR_INVALID")
    if isinstance(rows,list) and len(rows)==8 and isinstance(expected_session_dates,list) and len(expected_session_dates)==8:
        for i,row in enumerate(rows):
            if not isinstance(row,dict):
                errors.append("INVALID_SESSION_ROW");continue
            require(row.get("date")==expected_session_dates[i],"GAP_OR_OUT_OF_ORDER_SESSION")
            completed=parse_utc(row.get("completed_at_utc"))
            require(registered is not None and completed is not None and completed>registered
                    and captured is not None and completed<=captured,
                    "FORWARD_LOOKAHEAD_OR_INCOMPLETE_SESSION")
            c,h,l=(row.get(k) for k in ("close","high","low"))
            require(all(finite(x) for x in (c,h,l)) and l>0 and l<=c<=h,
                    "OHLC_VALIDITY_INVALID")
    if errors:
        return {"schema":SCHEMA,"status":"BLOCKED_FORWARD_EVIDENCE_INVALID",
                "reason_codes":sorted(set(errors)),
                "measured":False,"horizons":{},
                "execution":"NONE","real_money":"NO-GO","alpha_authority":False,
                "buy_candidates":[],"orders":[]}
    ref=float(reference)
    returns={}
    for h in HORIZONS:
        block=rows[:h]
        end=float(block[-1]["close"])
        high=max(float(r["high"]) for r in block)
        low=min(float(r["low"]) for r in block)
        closes=[ref]+[float(r["close"]) for r in block]
        peak=closes[0];max_drawdown=0.0
        for p in closes[1:]:
            peak=max(peak,p)
            max_drawdown=min(max_drawdown,p/peak-1)
        gross=end/ref-1
        net=gross-float(costs)/10000
        returns[str(h)]={
            "paper_close_to_close_net_return_pct":round(net*100,6),
            "paper_max_favorable_excursion_pct":round((high/ref-1)*100,6),
            "paper_max_adverse_excursion_pct":round((low/ref-1)*100,6),
            "paper_max_close_drawdown_pct":round(max_drawdown*100,6),
            "paper_net_positive":net>0,
        }
    return {"schema":SCHEMA,"status":"OPERATOR_ATTESTED_PAPER_OUTCOMES_NOT_TRADE_FILLS",
            "reason_codes":[],"measured":True,"horizons":returns,
            "policy":"C4.17_UNCHANGED","setup":private["setup"],
            "execution":"NONE","real_money":"NO-GO","alpha_authority":False,
            "buy_candidates":[],"orders":[],
            "limitations":"Paper outcomes, not realized fills, and operator proofs do not alone establish an independently audited win rate."}


def selftest():
    import copy
    watch={"current_source_ready":True,"status":"PROSPECTIVE_RESEARCH_WATCH_ONLY",
           "alpha_authority":False,"buy_candidates":[],"execution":"NONE","real_money":"NO-GO",
           "asof_et":"2026-10-07","preentry_watch":[{"symbol":"FIX","setup":"D"}],
           "prebreakout_b_armed_watch":[]}
    days=["2026-10-08","2026-10-09","2026-10-12","2026-10-13",
          "2026-10-14","2026-10-15","2026-10-16","2026-10-19"]
    registration="2026-10-07T21:00:00Z"
    private={
        "schema":"XRAY_PRIVATE_FORWARD_OBSERVATION_V1","synthetic_fixture":False,
        "aggregation_rights_verified":True,"provenance_witness_verified":True,
        "corporate_actions_adjustment_basis_verified":True,"official_calendar_witness_verified":True,
        "registered_at_utc":registration,"captured_at_utc":"2026-10-19T21:00:00Z",
        "asof_et":"2026-10-07","symbol":"FIX","setup":"D",
        "reference_close":100.0,"roundtrip_cost_bps":20.0,
        "future_sessions":[{"date":day,"high":103+i,"low":98+i,
             "close":100+i,"completed_at_utc":day+"T21:00:00Z"}
             for i,day in enumerate(days)]
    }
    ok=measure(watch,private,days)
    assert ok["measured"] and list(ok["horizons"])==["2","3","5","8"]
    assert ok["horizons"]["2"]["paper_close_to_close_net_return_pct"]==0.8
    assert ok["buy_candidates"]==[] and ok["orders"]==[]
    for segment,key,value in [
        ("watch","current_source_ready",False),
        ("private","aggregation_rights_verified",False),
        ("private","provenance_witness_verified",False),
        ("private","corporate_actions_adjustment_basis_verified",False),
        ("private","synthetic_fixture",True),
        ("private","asof_et","2026-10-08"),
        ("private","symbol","WRONG"),
        ("private","reference_close",float("nan")),
        ("private","roundtrip_cost_bps",None),
        ("private","registered_at_utc","2026-10-20T21:00:00Z"),
    ]:
        a=copy.deepcopy(watch);b=copy.deepcopy(private)
        (a if segment=="watch" else b)[key]=value
        assert not measure(a,b,days)["measured"],(segment,key)
    a=copy.deepcopy(private);a["future_sessions"][2]["date"]="2026-10-16"
    assert not measure(watch,a,days)["measured"]
    a=copy.deepcopy(private);a["future_sessions"][0]["low"]=float("inf")
    assert not measure(watch,a,days)["measured"]
    print("XRAY_FORWARD_WATCH_METRICS_SELFTEST=PASS_POSITIVE_12_NEGATIVE_NO_ALPHA")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--watch",type=Path)
    ap.add_argument("--private-source",type=Path)
    ap.add_argument("--official-eight-sessions",type=Path)
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:
        selftest();return
    if not args.out:ap.error("--out required")
    if not all((args.watch,args.private_source,args.official_eight_sessions)):
        result={"schema":SCHEMA,"status":"FORWARD_EVIDENCE_NOT_CONFIGURED",
                "measured":False,"horizons":{},
                "execution":"NONE","real_money":"NO-GO","alpha_authority":False,
                "buy_candidates":[],"orders":[],
                "explanation":"No real future-session data/automated-use-rights proof. No backfilled or simulated performance."}
    else:
        watch=json.loads(args.watch.read_text())
        evidence=json.loads(args.private_source.read_text())
        calendar=json.loads(args.official_eight_sessions.read_text())
        result=measure(watch,evidence,calendar)
    # The only durable output is aggregate metrics; raw OHLC and reference close
    # MUST NOT be written to repository, Actions artifact or GitHub issue.
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_FORWARD_WATCH_METRICS="+result["status"])
    print("XRAY_FORWARD_WATCH_ALPHA=FALSE")
if __name__=="__main__":
    main()
