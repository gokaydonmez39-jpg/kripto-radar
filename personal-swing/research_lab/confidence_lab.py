"""XRAY Confidence Lab V1: pure, offline, descriptive research. No signal authority."""
from __future__ import annotations
from math import fsum, isfinite, sqrt
from itertools import combinations

SCHEMA = "XRAY_CONFIDENCE_LAB_V1"
RESOLVED = {"TARGET", "STOP", "TIMEOUT"}
CENSORED = {"AMBIGUOUS", "CORPORATE_ACTION", "UNAVAILABLE"}
FIELDS = {"key","start","end","available","probability","outcome","gross_r","cost_r","quality"}

def _num(x, label, lo=None, hi=None):
    if type(x) not in (int,float) or not isfinite(x):
        raise ValueError(label)
    if (lo is not None and x < lo) or (hi is not None and x > hi):
        raise ValueError(label)
    return float(x)

def _idx(x):
    if type(x) is not int or x < 0:
        raise ValueError("INVALID_SESSION_ORDINAL")
    return x

def _rows(rows):
    if not isinstance(rows,(tuple,list)) or not rows:
        raise ValueError("EMPTY_OR_INVALID_ROWS")
    seen=set()
    out=[]
    for r in rows:
        if type(r) is not dict or set(r)!=FIELDS:
            raise ValueError("INVALID_ROW_SCHEMA")
        key=r["key"]
        if type(key) is not str or not key or key in seen:
            raise ValueError("INVALID_OR_DUPLICATE_KEY")
        seen.add(key)
        start,end,available=(_idx(r[k]) for k in ("start","end","available"))
        if not start < end <= start+15 or available > start:
            raise ValueError("HORIZON_OR_FUTURE_FEATURE")
        outcome=r["outcome"]
        if type(outcome) is not str or outcome not in RESOLVED|CENSORED:
            raise ValueError("UNKNOWN_OUTCOME")
        if r["quality"]!="NATIVE":
            raise ValueError("BRACKET_RESEARCH_REQUIRES_NATIVE_WITNESS")
        p=r["probability"]
        if p is not None:
            p=_num(p,"INVALID_PROBABILITY",0,1)
        if outcome in CENSORED:
            if r["gross_r"] is not None or r["cost_r"] is not None:
                raise ValueError("CENSORED_RETURN_MUST_BE_NULL")
            gross=cost=None
        else:
            if p is None:
                raise ValueError("MISSING_FORECAST")
            gross=_num(r["gross_r"],"INVALID_GROSS_R")
            cost=_num(r["cost_r"],"INVALID_COST_R",0)
            # TARGET/STOP refer to deterministic theoretical bracket outcome,
            # not fills. A stop gap may exceed -1R; target gap is capped at 2R.
            if (outcome=="TARGET" and gross!=2) or (outcome=="STOP" and gross > -1):
                raise ValueError("OUTCOME_RETURN_MISMATCH")
            if outcome=="TIMEOUT" and (end!=start+15 or not -1 < gross < 2):
                raise ValueError("INVALID_TIMEOUT_RETURN_OR_HORIZON")
        out.append(dict(r,probability=p,gross_r=gross,cost_r=cost))
    return out

def wilson(k,n):
    """Descriptive 95% Wilson interval; iid binomial interpretation not guaranteed."""
    if type(k) is not int or type(n) is not int or not 0<=k<=n:
        raise ValueError("INVALID_BINOMIAL_COUNTS")
    if n==0:
        return None
    z=1.959963984540054
    p=k/n
    d=1+z*z/n
    c=(p+z*z/(2*n))/d
    h=z*sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return max(0.,c-h),min(1.,c+h)

def _clusters(rows):
    right=-1
    count=0
    for r in sorted(rows,key=lambda x:(x["start"],x["end"])):
        if r["start"]>right:
            count+=1
        right=max(right,r["end"])
    return count

def evaluate(rows, *, baseline_probability):
    """Target-before-stop within 15 sessions: timeout is binary 0, not -1R.
    Caller must supply point-in-time verified labels and an independently fitted
    baseline probability. This function does not establish source provenance,
    model calibration, true fills, or statistical significance.
    """
    baseline=_num(baseline_probability,"INVALID_BASELINE",0,1)
    a=_rows(rows)
    resolved=[r for r in a if r["outcome"] in RESOLVED]
    n=len(resolved)
    successes=sum(r["outcome"]=="TARGET" for r in resolved)
    clusters=_clusters(resolved)
    if n:
        brier=fsum((r["probability"]-int(r["outcome"]=="TARGET"))**2 for r in resolved)/n
        base=fsum((baseline-int(r["outcome"]=="TARGET"))**2 for r in resolved)/n
        net=fsum(r["gross_r"]-r["cost_r"] for r in resolved)/n
    else:
        brier=base=net=None
    bins=[]
    for i in range(5):
        group=[r for r in resolved if min(4,int(r["probability"]*5))==i]
        m=len(group)
        bins.append({"lower":i/5,"upper":(i+1)/5,"n":m,
                     "mean_probability":fsum(r["probability"] for r in group)/m if m else None,
                     "observed_target_rate":sum(r["outcome"]=="TARGET" for r in group)/m if m else None})
    return {"schema":SCHEMA,"decision_influence":"NO_GO","research_only":True,
            "input_n":len(a),"resolved_n":n,"binary_n":n,"censored":len(a)-n,
            "outcome_counts":{k:sum(r["outcome"]==k for r in a) for k in sorted(RESOLVED|CENSORED)},
            "overlap_clusters":clusters,"target_rate":successes/n if n else None,
            "wilson_iid_descriptive":wilson(successes,n),"brier":brier,
            "baseline_brier":base,"brier_skill":1-brier/base if base else None,
            "net_mean_r":net,"calibration_bins":bins,
            "statistical_status":"HOLD_SMALL_OR_DEPENDENT_SAMPLE" if clusters<30 else "DESCRIPTIVE_ONLY_DEPENDENCE_UNPROVEN",
            "provenance_status":"CALLER_WITNESS_NOT_ATTESTED",
            "may_modify_al":False,"may_place_order":False}

def purged_split(rows, *, test_start, test_end, embargo=15):
    """Forward-only split by verified XNAS ordinal; no post-test training.
    Test window is inclusive by origin; labels may mature later.
    """
    start,end,gap=map(_idx,(test_start,test_end,embargo))
    if end<start or gap<15:
        raise ValueError("INVALID_TEST_WINDOW_OR_EMBARGO")
    a=_rows(rows)
    train=[r for r in a if r["end"]<=start-gap and r["start"]<start]
    test=[r for r in a if start<=r["start"]<=end]
    return train,test

def concentration(series):
    """Pearson diagnostics for PREALIGNED same-session research return arrays.
    No alignment or source validation here; constant/missing/misaligned fail.
    """
    if type(series) is not dict or len(series)<2:
        raise ValueError("INSUFFICIENT_SERIES")
    vals={}
    length=None
    for k,v in series.items():
        if type(k) is not str or not k or not isinstance(v,(list,tuple)) or len(v)<3:
            raise ValueError("INVALID_SERIES")
        if length is None: length=len(v)
        if len(v)!=length: raise ValueError("MISALIGNED_SERIES")
        a=[_num(x,"INVALID_RETURN") for x in v]
        avg=fsum(a)/length
        centered=[x-avg for x in a]
        norm=sqrt(fsum(x*x for x in centered))
        if not isfinite(norm) or norm==0: raise ValueError("CONSTANT_OR_OVERFLOW_SERIES")
        vals[k]=[x/norm for x in centered]
    correlations=[abs(fsum(x*y for x,y in zip(a,b))) for a,b in combinations(vals.values(),2)]
    return {"pairs":len(correlations),"observations":length,
            "max_abs_correlation":min(1.,max(correlations)),
            "mean_abs_correlation":min(1.,fsum(correlations)/len(correlations)),
            "alignment_attested":False,"decision_influence":"NO_GO"}
