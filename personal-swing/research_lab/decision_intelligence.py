"""XRAY Decision Intelligence V1: research-only evidence composition.

Inputs are normalized, caller-supplied witnesses, not independently authenticated
source receipts. No I/O, fitting, AL changes, notifications, orders, or publishing.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

SYSTEM="XRAY_NASDAQ_PERSONAL"
SOURCES=("KRONOS","COVE","SEC","CONFIDENCE")
CORE_FIELDS={"system","asof","episode_id","symbol","source_run","scope_sha","algorithm_sha","reference","stop","target","current_close","technical_score"}
SOURCE_FIELDS={"source","asof","episode_id","scope_sha","algorithm_sha","source_run","status","payload","sha256"}
def require(ok,code):
    if not ok: raise ValueError(code)
def digest(value):
    try:
        raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    except (TypeError,ValueError,OverflowError):
        raise ValueError("INVALID_CANONICAL_VALUE") from None
    return hashlib.sha256(raw.encode()).hexdigest()
def day(v):
    require(type(v) is str,"INVALID_ASOF")
    try: d=date.fromisoformat(v)
    except ValueError: raise ValueError("INVALID_ASOF") from None
    require(d.isoformat()==v,"INVALID_ASOF")
    return v
def sha(v):
    require(type(v) is str and re.fullmatch("[0-9a-f]{64}",v) is not None,"INVALID_SHA")
    return v
def price(v):
    require(type(v) is str and len(v)<=40 and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?",v) is not None,"INVALID_PRICE")
    try: n=Decimal(v)
    except InvalidOperation: raise ValueError("INVALID_PRICE") from None
    require(n.is_finite() and n>0,"INVALID_PRICE")
    return n
def assess(core,evidence):
    """Compose context on one existing AL episode; never make an AL decision."""
    require(type(core) is dict and set(core)==CORE_FIELDS and core["system"]==SYSTEM,"CORE_SCHEMA")
    asof=day(core["asof"]); symbol=core["symbol"]
    require(type(symbol) is str and re.fullmatch(r"[A-Z0-9.]+",symbol) is not None,"CORE_SYMBOL")
    require(type(core["episode_id"]) is str,"CORE_EPISODE")
    origin,sep,sym=core["episode_id"].partition("|")
    require(sep=="|" and sym==symbol and day(origin)<=asof,"CORE_EPISODE")
    require(type(core["source_run"]) is str and re.fullmatch("[1-9][0-9]{0,20}",core["source_run"]) is not None,"CORE_RUN")
    sha(core["scope_sha"]);sha(core["algorithm_sha"])
    ref,stop,target,current=map(price,(core["reference"],core["stop"],core["target"],core["current_close"]))
    require(stop<ref<target and abs(target-(ref+2*(ref-stop)))<=Decimal("0.025"),"CORE_BRACKET")
    raw_score=core["technical_score"]
    require(type(raw_score) in (int,float),"CORE_SCORE")
    score=Decimal(str(raw_score))
    require(score.is_finite() and Decimal("0")<=score<=Decimal("100")
            and score*10==(score*10).to_integral_value(),"CORE_SCORE")
    require(type(evidence) in (list,tuple) and len(evidence)<=len(SOURCES),"EVIDENCE_COUNT")
    records={};status={k:"MISSING" for k in SOURCES};context="UNAVAILABLE";quality=None
    for e in evidence:
        require(type(e) is dict and set(e)==SOURCE_FIELDS,"EVIDENCE_SCHEMA")
        name=e["source"]
        require(type(name) is str and name in SOURCES and name not in records,"EVIDENCE_SOURCE")
        require(e["asof"]==asof and all(e[k]==core[k] for k in ("scope_sha","algorithm_sha","source_run")),"EVIDENCE_EPOCH")
        require(e["episode_id"]==(core["episode_id"] if name=="KRONOS" else None),"EVIDENCE_SCOPE")
        require(sha(e["sha256"])==digest({k:v for k,v in e.items() if k!="sha256"}),"EVIDENCE_HASH")
        state=e["status"]; p=e["payload"]
        require(type(state) is str and state in ("READY","HOLD","UNKNOWN") and type(p) is dict,"EVIDENCE_STATE")
        if state!="READY":
            require(p=={},"UNAVAILABLE_PAYLOAD")
        elif name=="KRONOS":
            require(set(p)=={"model_quality","reference","closes"} and p["model_quality"] in ("RESEARCH_ONLY","RESEARCH_CLOSE_ONLY"),"KRONOS_SCHEMA")
            # Allow the actual score's 3-decimal price vs Kronos's 6-decimal
            # price only when the two rounded values are compatible.
            anchor=price(p["reference"])
            require(abs(anchor-current)<=Decimal("0.0005005"),"KRONOS_REFERENCE")
            closes=p["closes"]
            require(type(closes) is dict and set(closes)=={"1","5","12"},"KRONOS_HORIZONS")
            signs=[(price(closes[h])>anchor)-(price(closes[h])<anchor) for h in ("1","5","12")]
            context="UPWARD_FORECAST" if all(x>0 for x in signs) else "DOWNWARD_FORECAST" if all(x<0 for x in signs) else "FLAT_FORECAST" if not any(signs) else "MIXED_FORECAST"
            quality=p["model_quality"]
        elif name=="COVE":
            require(p=={"scope":"COHORT","oos":"HOLD_UNVERIFIED_PIT_OOS"},"COVE_COHORT_ONLY")
        elif name=="SEC":
            # No authorized PIT financial source admission in this version.
            raise ValueError("SEC_READY_NOT_ADMITTED")
        else:
            require(set(p)=={"statistical_status","decision_influence"} and p["decision_influence"]=="NO_GO" and p["statistical_status"] in ("HOLD_SMALL_OR_DEPENDENT_SAMPLE","DESCRIPTIVE_ONLY_DEPENDENCE_UNPROVEN"),"CONFIDENCE_DESCRIPTIVE_ONLY")
        records[name]=e;status[name]=state
    n=sum(v=="READY" for v in status.values())
    flags=[]
    if context=="DOWNWARD_FORECAST": flags.append("TECHNICAL_AL_VS_DOWNWARD_FORECAST")
    if context=="MIXED_FORECAST": flags.append("FORECAST_HORIZONS_DISAGREE_OR_FLAT")
    if quality=="RESEARCH_CLOSE_ONLY": flags.append("NATIVE_OHLC_QUALITY_HOLD")
    if status["COVE"]=="READY": flags.append("COVE_COHORT_ONLY_OOS_HOLD")
    if status["CONFIDENCE"]=="READY": flags.append("CONFIDENCE_DESCRIPTIVE_NOT_CALIBRATED")
    result={"schema":"XRAY_DECISION_INTELLIGENCE_V1","system":SYSTEM,"asof":asof,"episode_id":core["episode_id"],
            "technical_score":core["technical_score"],"source_status":status,
            "research_state":"PARTIAL_RESEARCH" if n else "NO_RESEARCH","kronos_context":context,"kronos_quality":quality,
            "flags":flags,"success_probability":None,"net_expected_r":None,
            "source_authentication":"CALLER_WITNESS_NOT_ATTESTED","decision_influence":"NO_GO",
            "may_modify_al":False,"may_notify":False,"may_publish":False,"may_trade":False}
    result["research_sha256"]=digest({"core":core,"evidence":[records[k] for k in sorted(records)],"result":result})
    return result
