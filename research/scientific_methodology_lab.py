"""XRAY independent, research-only evidence methods (ML4T methodology pilot).
No broker, no signals, no network, no production dependencies.
Methods are independently written, not copied from third-party notebooks.
"""
from __future__ import annotations
import hashlib
import json
import math
from statistics import mean, stdev

class EvidenceReject(ValueError):
    pass

def _finite_positive(v):
    return type(v) in (int, float) and math.isfinite(v) and v > 0

def canonical_digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

def point_in_time_bars(bars, asof):
    """Validate all provided records before any metric; never silently discard future/duplicate bars."""
    if not isinstance(asof, str) or len(asof) != 10:
        raise EvidenceReject("BAD_ASOF")
    if not isinstance(bars, (list, tuple)) or not bars:
        raise EvidenceReject("NO_BARS")
    result = []
    seen = set()
    for row in bars:
        if not isinstance(row, dict):
            raise EvidenceReject("INVALID_ROW")
        day = row.get("date")
        if not isinstance(day, str) or len(day) != 10 or day > asof:
            raise EvidenceReject("FUTURE_OR_BAD_ASOF_BAR")
        if day in seen:
            raise EvidenceReject("DUPLICATE_BAR")
        seen.add(day)
        for field in ("open", "high", "low", "close"):
            if not _finite_positive(row.get(field)):
                raise EvidenceReject("INVALID_PRICE")
        if not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]:
            raise EvidenceReject("INVALID_OHLC")
        result.append(row)
    if [x["date"] for x in result] != sorted(seen):
        raise EvidenceReject("NONCHRONOLOGICAL_BARS")
    if result[-1]["date"] != asof:
        raise EvidenceReject("NO_EXACT_ASOF")
    return tuple(result)

def purged_train_indices(intervals, test_indices, embargo_sessions=0):
    """Each interval is [label start, label end], in session-index units (not calendar days).
    Remove any train label overlapping a test label; embargo AFTER each test label.
    """
    if type(embargo_sessions) is not int or embargo_sessions < 0:
        raise EvidenceReject("BAD_EMBARGO")
    if not isinstance(intervals, (list, tuple)) or not intervals:
        raise EvidenceReject("BAD_INTERVALS")
    for a,b in intervals:
        if type(a) is not int or type(b) is not int or a<0 or b<a:
            raise EvidenceReject("INVALID_LABEL_SPAN")
    holdout=set(test_indices)
    if not holdout or any(type(i) is not int or i < 0 or i >= len(intervals) for i in holdout):
        raise EvidenceReject("BAD_HOLDOUT")
    unsafe = [(intervals[i][0], intervals[i][1]+embargo_sessions) for i in sorted(holdout)]
    return tuple(i for i,(a,b) in enumerate(intervals) if i not in holdout
                 and not any(a <= test_end and b >= test_start for test_start,test_end in unsafe))

def next_open_net_return(*, signal_index, entry_index, exit_index, entry_open, exit_open, entry_bps, exit_bps):
    """No same-close fills; both costs apply. No order placement."""
    if not (type(signal_index) is int and type(entry_index) is int and type(exit_index) is int
            and 0 <= signal_index < entry_index < exit_index):
        raise EvidenceReject("LOOKAHEAD_OR_NONSEQUENTIAL_FILL")
    if not (_finite_positive(entry_open) and _finite_positive(exit_open)):
        raise EvidenceReject("INVALID_FILL_PRICE")
    if any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<10000 for x in (entry_bps, exit_bps)):
        raise EvidenceReject("INVALID_COST")
    paid=entry_open*(1+entry_bps/10000)
    received=exit_open*(1-exit_bps/10000)
    return received/paid-1

def conservative_barrier_hit(*, entry, stop, target, open_, high, low, close):
    """Stop-first on same-bar ambiguous touches; adverse gap fills at actual open."""
    if not all(_finite_positive(v) for v in (entry,stop,target,open_,high,low,close)):
        raise EvidenceReject("INVALID_LEVEL")
    if not (stop<entry<target and low<=min(open_,close)<=max(open_,close)<=high):
        raise EvidenceReject("INVALID_GEOMETRY")
    if open_<=stop:
        return ("GAP_STOP",open_)
    hit_stop=low<=stop
    hit_target=high>=target
    if hit_stop:
        return ("AMBIGUOUS_STOP_FIRST" if hit_target else "STOP",stop)
    if hit_target:
        return ("TARGET",target)
    return ("OPEN",None)

def max_drawdown(equity):
    if not isinstance(equity,(list,tuple)) or not equity or not all(_finite_positive(x) for x in equity):
        raise EvidenceReject("INVALID_EQUITY")
    peak=equity[0]
    worst=0.
    for v in equity:
        peak=max(peak,v)
        worst=min(worst,v/peak-1)
    return worst

def historical_expected_shortfall(returns, tail_fraction=0.05):
    if not isinstance(returns,(list,tuple)) or len(returns)<2 or not all(type(x) in (int,float) and math.isfinite(x) for x in returns):
        raise EvidenceReject("INSUFFICIENT_RETURNS")
    if type(tail_fraction) not in (int,float) or not 0<tail_fraction<=0.5:
        raise EvidenceReject("BAD_TAIL")
    k=max(1,math.ceil(len(returns)*tail_fraction))
    return mean(sorted(returns)[:k])

def uncertainty_witness(returns):
    """Purely descriptive; not a confidence-guaranteed future-profit probability."""
    if len(returns)<3 or not all(type(x) in (int,float) and math.isfinite(x) for x in returns):
        raise EvidenceReject("INSUFFICIENT_RETURNS")
    n=len(returns)
    return {"n":n, "mean":mean(returns), "sample_std":stdev(returns),
            "std_error":stdev(returns)/math.sqrt(n)}
