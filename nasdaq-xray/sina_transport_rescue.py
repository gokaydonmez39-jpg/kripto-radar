#!/usr/bin/env python3
"""Bounded, one-time real-source retry of expired transient Sina exceptions.

Does not synthesize OHLCV, relax thresholds, change policy or promote UNKNOWN.
Eligibility is decided using the recorded failed attempt timestamp and exact
same state epoch; ordinary insufficient-history responses are never retried.
"""
from __future__ import annotations
import datetime as dt

TRANSIENT=("SyntaxError:","IndexError:","JSONDecodeError:","TimeoutError:","ConnectionError:","HTTPError:")
MIN_COOLDOWN_SECONDS=1800
MAX_PER_RUN=32

def parse_time(text):
    try:
        t=dt.datetime.fromisoformat(str(text).replace("Z","+00:00"))
        return t.astimezone(dt.timezone.utc) if t.tzinfo else None
    except (ValueError,OverflowError):
        return None

def choose(state,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError("NAIVE_NOW")
    now=now.astimezone(dt.timezone.utc)
    if state.get("execution")!="NONE" or state.get("real_money")!="NO-GO" or state.get("unknown_never_pass") is not True:
        raise ValueError("SAFETY_HEADER_INVALID")
    queue=state.get("queue")
    rows=state.get("results")
    if not isinstance(queue,list) or not isinstance(rows,dict) or len(queue)!=len(set(queue)):
        raise ValueError("QUEUE_INVALID")
    if state.get("cursor")!=len(queue) or state.get("queue_total")!=len(queue):
        return []
    if not set(rows).issubset(set(queue)):
        raise ValueError("RESULT_OUTSIDE_QUEUE")
    eligible=[]
    for symbol in sorted(rows):
        row=rows[symbol]
        if not isinstance(row,dict) or row.get("status")!="UNKNOWN_RETRY_EXHAUSTED":
            continue
        if row.get("transport_rescue_round",0)!=0:
            continue
        info=row.get("info")
        if not isinstance(info,str) or not info.startswith(TRANSIENT):
            continue
        at=parse_time(row.get("updated_at_utc"))
        if at is None or (now-at).total_seconds()<MIN_COOLDOWN_SECONDS:
            continue
        eligible.append(symbol)
    return eligible[:MAX_PER_RUN]

def selftest():
    from copy import deepcopy
    t=dt.datetime(2026,10,9,12,47,tzinfo=dt.timezone.utc)
    old="2026-10-09T11:35:00+00:00"
    def rec(status,info,rescue=0,time=old):
        return {"status":status,"info":info,"attempts":4,
                "updated_at_utc":time,"transport_rescue_round":rescue}
    state={
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
        "queue":["A","B","C","D","E","F","G","H"],"queue_total":8,"cursor":8,
        "results":{
            "A":rec("UNKNOWN_RETRY_EXHAUSTED","SyntaxError:provider returned html"),
            "B":rec("UNKNOWN_RETRY_EXHAUSTED","IndexError:index out of range"),
            "C":rec("UNKNOWN_STATIC",{"reason":"SINA_DAILY_LT260_REQUIRES_INDEPENDENT_CONFIRMATION"}),
            "D":rec("UNKNOWN_RETRY_EXHAUSTED","SyntaxError:already done",rescue=1),
            "E":rec("UNKNOWN_RETRY_EXHAUSTED","SyntaxError:too recent",time="2026-10-09T12:45:00Z"),
            "F":rec("PASS",{"price":20}),
            "G":rec("UNKNOWN_RETRY_EXHAUSTED","ValueError:deterministic invalid"),
            "H":rec("UNKNOWN_RETRY_EXHAUSTED","TimeoutError:timed out")
        }
    }
    assert choose(state,t)==["A","B","H"]
    for mutation in [
        lambda s:s.update(cursor=7),
        lambda s:s.update(execution="ORDER"),
        lambda s:s.update(unknown_never_pass=False),
        lambda s:s["results"].update({"OUTSIDE":{"status":"PASS"}}),
        lambda s:s["queue"].append("A"),
    ]:
        bad=deepcopy(state);mutation(bad)
        try:part=choose(bad,t)
        except ValueError:continue
        assert part==[],part
    assert choose(state,dt.datetime(2026,10,9,11,50,tzinfo=dt.timezone.utc))==[]
    assert MAX_PER_RUN<=32
    print("XRAY_SINA_TRANSPORT_RESCUE_SELFTEST=PASS_EXACT_EPOCH_COOLDOWN_ONCE_5_NEGATIVE_NO_ALPHA")

if __name__=="__main__":
    selftest()
