"""XRAY personal three-layer V1. Pure research contracts; no I/O or authority."""
from __future__ import annotations
from datetime import date
from math import isfinite
import re

SYSTEM="XRAY_NASDAQ_PERSONAL"
HORIZONS=(1,5,12)
SHA=re.compile(r"[0-9a-f]{64}")
SYMBOL=re.compile(r"[A-Z][A-Z0-9.\-]{0,14}")
def _date(x):
    if type(x) is not str: raise ValueError("INVALID_ASOF")
    try: d=date.fromisoformat(x)
    except ValueError as e: raise ValueError("INVALID_ASOF") from e
    if d.isoformat()!=x: raise ValueError("INVALID_ASOF")
    return x
def _number(x, positive=False):
    if type(x) not in (int,float) or not isfinite(x) or (positive and x<=0):
        raise ValueError("INVALID_NUMBER")
    return float(x)
def _sha(x):
    if type(x) is not str or not SHA.fullmatch(x): raise ValueError("INVALID_SHA")
    return x
def _symbol(x):
    if type(x) is not str or not SYMBOL.fullmatch(x): raise ValueError("INVALID_SYMBOL")
    return x
def _bar(o,h,l,c):
    o,h,l,c=(_number(x,True) for x in (o,h,l,c))
    if l>min(o,c) or h<max(o,c): raise ValueError("INVALID_OHLC_GEOMETRY")
    return o,h,l,c
def _run(x):
    if type(x) is not str or not re.fullmatch(r"[1-9][0-9]{0,20}",x):
        raise ValueError("INVALID_RUN_ID")
    return x
def validate_snapshot(s, *, expected_asof, expected_scope_sha, expected_algorithm_sha, expected_symbols=None):
    """Validate a supplied envelope, NOT independently authenticate its origin.
    The real adapter must supply independently authenticated expected symbols and
    source receipts. This contract alone never authorizes a production display.
    """
    if type(s) is not dict or s.get("schema")!="XRAY_PRIVATE_SNAPSHOT_V1":
        raise ValueError("INVALID_SCHEMA")
    asof=_date(expected_asof)
    if _date(s.get("asof"))!=asof or s.get("source_accepted") is not True:
        raise ValueError("STALE_OR_UNACCEPTED_SOURCE")
    if _sha(s.get("scope_sha"))!=_sha(expected_scope_sha) or _sha(s.get("algorithm_sha"))!=_sha(expected_algorithm_sha):
        raise ValueError("SOURCE_HASH_MISMATCH")
    _run(s.get("source_run"))
    symbols=s.get("symbols")
    if type(symbols) is not list or len(symbols)!=477:
        raise ValueError("INVALID_SCOPE_COUNT")
    scope={_symbol(x) for x in symbols}
    if len(scope)!=477: raise ValueError("DUPLICATE_SCOPE")
    if expected_symbols is not None:
        if type(expected_symbols) not in (list,tuple) or len(expected_symbols)!=477 or {_symbol(x) for x in expected_symbols}!=scope:
            raise ValueError("CANONICAL_MEMBERSHIP_MISMATCH")
    scan=s.get("scan")
    if type(scan) is not list or len(scan)!=477: raise ValueError("INVALID_SCAN_COUNT")
    seen=set()
    for r in scan:
        if type(r) is not dict or r.get("status") not in ("AL","IZLE","ELE","HOLD"):
            raise ValueError("INVALID_SCAN_ROW")
        k=_symbol(r.get("symbol"))
        if k not in scope or k in seen: raise ValueError("SCAN_MEMBERSHIP_MISMATCH")
        seen.add(k)
    forecasts=s.get("kronos")
    if type(forecasts) is not list or len(forecasts)!=1431: raise ValueError("INVALID_FORECAST_COUNT")
    keys=set()
    for r in forecasts:
        if type(r) is not dict or r.get("asof")!=asof or type(r.get("horizon")) is not int or r["horizon"] not in HORIZONS:
            raise ValueError("INVALID_FORECAST_EPOCH")
        k=(_symbol(r.get("symbol")),r["horizon"])
        if k[0] not in scope or k in keys: raise ValueError("FORECAST_MEMBERSHIP_MISMATCH")
        keys.add(k)
        q=r.get("quality"); close=r.get("close"); native=r.get("native")
        if q=="NATIVE":
            if type(native) is not dict or set(native)!={"open","high","low","close"}: raise ValueError("NATIVE_BAR_REQUIRED")
            if _bar(native["open"],native["high"],native["low"],native["close"])[3]!=_number(close,True):
                raise ValueError("FORECAST_CLOSE_MISMATCH")
        elif q=="RESEARCH_CLOSE_ONLY":
            _number(close,True)
            if native is not None: raise ValueError("CLOSE_ONLY_NOT_NATIVE")
        elif q=="HOLD":
            if close is not None or native is not None: raise ValueError("HOLD_MUST_NOT_DRAW")
        else: raise ValueError("INVALID_FORECAST_QUALITY")
    return {"system":SYSTEM,"asof":asof,"scan_count":len(seen),"forecast_count":len(keys),"status":"CONTRACT_PASS","source_authentication":"CALLER_WITNESS_NOT_ATTESTED","may_publish":False,"may_modify_al":False}

def risk_bounds(ref,stop,target,o,h,l,c,cost_r):
    """Single completed post-origin daily bar, theoretical long bracket bounds.
    Entry reference is not a fill. Gap stop uses opening proxy; target capped.
    Costs are assumed R units. Never infer intraday ordering or order fills.
    """
    ref,stop,target=(_number(x,True) for x in (ref,stop,target))
    risk=ref-stop
    if risk<=0 or target<=ref or abs((target-ref)/risk-2)>1e-9:
        raise ValueError("INVALID_FIXED_BRACKET")
    o,h,l,c=_bar(o,h,l,c); cost=_number(cost_r)
    if cost<0: raise ValueError("NEGATIVE_COST")
    if o<=stop: state="STOP_GAP_PROXY"; low=high=(o-ref)/risk-cost
    elif o>=target: state="TARGET_GAP_CAPPED"; low=high=2-cost
    elif l<=stop and h>=target: state="AMBIGUOUS_DUAL_TOUCH"; low,high=-1-cost,2-cost
    elif l<=stop: state="STOP_TOUCH_PROXY"; low=high=-1-cost
    elif h>=target: state="TARGET_TOUCH_PROXY"; low=high=2-cost
    else: state="OPEN_NO_TERMINAL"; low=high=None
    return {"status":state,"net_r_min":low,"net_r_max":high,"real_fill":False,"decision_influence":"NO_GO"}

def watchdog(o, seen):
    """Classify an observation, not authenticate it or persist a reservation.
    Only an independently verified caller plus durable atomic ledger can admit
    an event. No dispatch, notifications, or trading from this function.
    """
    if type(o) is not dict or not isinstance(seen,(set,frozenset)): raise ValueError("INVALID_WATCHDOG_INPUT")
    asof=_date(o.get("expected_asof"))
    def out(state,reason,key=None):
        return {"system":SYSTEM,"status":state,"reason":reason,"event_key":key,
                "may_notify":False,"may_dispatch":False,"may_trade":False,"source_authentication":"CALLER_WITNESS_NOT_ATTESTED"}
    required=("asof","source_run","run_status","scan_count","sheet_asof","sheet_exact","guardian","score","identity_verified")
    if any(o.get(k) is None for k in required): return out("UNKNOWN","MISSING_WITNESS")
    _date(o["asof"]);_date(o["sheet_asof"]);_run(o["source_run"])
    if o["asof"]!=asof: return out("HOLD","SOURCE_ASOF_MISMATCH")
    if o["run_status"] in ("queued","in_progress","waiting","pending"): return out("WAIT","RUN_NOT_TERMINAL")
    if o["run_status"]!="success": return out("HOLD","RUN_NOT_SUCCESS")
    if type(o["scan_count"]) is not int or o["scan_count"]!=477 or o["sheet_asof"]!=asof or any(o[k] is not True for k in ("sheet_exact","guardian","score","identity_verified")):
        return out("HOLD","ACCEPTANCE_WITNESS_MISMATCH")
    key=f"{SYSTEM}|EOD_ACCEPTED|{asof}"
    return out("DUPLICATE" if key in seen else "ACCEPTED","READ_ONLY_CANDIDATE",key)
