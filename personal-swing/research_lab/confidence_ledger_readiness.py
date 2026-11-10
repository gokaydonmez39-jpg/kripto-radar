"""Private episode/terminal evidence readiness, NOT a performance estimator.

Pure read-only contract. The caller must independently authenticate complete
private ranges, official XNAS session sequence and original source run jobs.
No private rows, forecasts, returns, or identities may enter public logs.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
from collections import Counter
import re

CANDIDATE_HEADER=("ALARM KİMLİĞİ","ASOF ET","SEMBOL","SINIF","IEX KAPANIŞ USD","STOP 2ATR","HEDEF 2R","TAKİP DURUMU","KAPANIŞ SEANSI","SONUÇ","TEORİK %","BİLDİRİM","KAYNAK / NOT")
EVENT_HEADER=("OLAY_ANAHTARI","ADAY_ANAHTARI","AL_ASOF_ET","SEMBOL","OLAY_ASOF_ET","OLAY_KODU","ONCELIK","IEX_KAPANIS_USD","ORIJINAL_STOP_USD","ORIJINAL_HEDEF_USD","SMA20","SMA50","DESTEK_20","DIRENC_20","TEPE_52","TAKIP_SEANSI","BIRINCIL_KANIT_URL","BILDIRIM_DURUMU","BILDIRIM_ZAMANI_TR","NOT")
TERMINAL={"STOP_TOUCHED","TARGET_TOUCHED","TIME_EXIT_AT_CLOSE","BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS","CORPORATE_ACTION_REVIEW"}
RUN_PREFIX="https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/"

def require(ok, code):
    if not ok: raise ValueError(code)

def day(s):
    require(type(s) is str,"INVALID_DATE")
    try: d=date.fromisoformat(s)
    except ValueError: raise ValueError("INVALID_DATE") from None
    require(d.isoformat()==s,"INVALID_DATE")
    return s

def number(s):
    require(type(s) is str and re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?",s) is not None,"INVALID_PRICE")
    try: v=Decimal(s.replace(",","."))
    except InvalidOperation: raise ValueError("INVALID_PRICE") from None
    require(v.is_finite() and v>0,"INVALID_PRICE")
    return v

def matrix(values,header,cap):
    require(type(values) is list and 1<=len(values)<=cap and tuple(values[0])==header,"HEADER_OR_CAPACITY")
    rows=[];keys=set();blank=False
    for raw in values[1:]:
        require(type(raw) is list and len(raw)<=len(header) and all(type(x) is str for x in raw),"ROW_SCHEMA")
        if not raw or all(x=="" for x in raw):
            blank=True;continue
        require(not blank and bool(raw[0]) and raw[0] not in keys,"DUPLICATE_OR_BLANK")
        keys.add(raw[0]);rows.append(raw+[""]*(len(header)-len(raw)))
    return rows

def audit(candidate_values,event_values,*,expected_asof,xnas_sessions,verified_source_run_ids):
    """Audit linkage only. No label, payoff, probability, training or trading authority."""
    asof=day(expected_asof)
    require(type(xnas_sessions) in (tuple,list) and bool(xnas_sessions),"MISSING_SESSIONS")
    sessions=[day(x) for x in xnas_sessions]
    require(sessions==sorted(set(sessions)) and sessions[-1]==asof,"SESSION_ORDER_OR_ASOF")
    ordinal={d:i for i,d in enumerate(sessions)}
    require(isinstance(verified_source_run_ids,(set,frozenset)) and all(type(x) is str and re.fullmatch("[1-9][0-9]{0,20}",x) for x in verified_source_run_ids),"INVALID_RUN_WITNESSES")
    candidates=matrix(candidate_values,CANDIDATE_HEADER,20000)
    events=matrix(event_values,EVENT_HEADER,20000)
    indexed={}
    for e in events:
        require(day(e[4])<=asof,"FUTURE_EVENT")
        indexed.setdefault(e[1],[]).append(e)
    counts=Counter(); results=[]
    for r in candidates:
        origin=day(r[1]);symbol=r[2];key=r[0]
        require(origin in ordinal and re.fullmatch(r"[A-Z0-9.]+",symbol) is not None and key==origin+"|"+symbol,"EPISODE_ID")
        ref,stop,target=map(number,r[4:7])
        require(stop<ref<target and abs(target-(ref+2*(ref-stop)))<=Decimal("0.025"),"FIXED_BRACKET")
        open_match=re.fullmatch(r"AÇIK • ([0-9]{1,2})/15 SEANS",r[7])
        closed_match=re.fullmatch(r"KAPALI • ([A-Z0-9_]+) • ([0-9]{1,2})/15 SEANS",r[7])
        terminal=[e for e in indexed.get(key,[]) if e[5] in TERMINAL]
        if open_match:
            held=int(open_match[1])
            require(0<=held<15 and ordinal[origin]+held<=ordinal[asof] and r[8:11]==["","",""],"OPEN_STATE")
            state="HOLD_OPEN_NOT_MATURE" if not terminal else "HOLD_OPEN_TERMINAL_CONFLICT"
        else:
            require(closed_match is not None,"INVALID_EPISODE_STATE")
            outcome=closed_match[1];held=int(closed_match[2]);end=day(r[8])
            require(outcome in TERMINAL and r[9]==outcome and origin<end<=asof and 0<=held<=15,"INVALID_TERMINAL")
            if outcome!="CORPORATE_ACTION_REVIEW":
                require(end in ordinal and ordinal[end]-ordinal[origin]==held and held>0,"TERMINAL_SESSION_COUNT")
                require(outcome!="TIME_EXIT_AT_CLOSE" or held==15,"TIME_EXIT_HORIZON")
            else:
                require(r[10]=="","CORPORATE_RETURN_MUST_BE_BLANK")
            matching=[e for e in terminal if e[4]==end and e[5]==outcome]
            if not matching: state="HOLD_TERMINAL_EVENT_MISSING"
            elif len(terminal)!=1 or len(matching)!=1: state="HOLD_TERMINAL_EVENT_CONFLICT"
            else:
                e=matching[0]
                if (e[0]!=f"{key}|{end}|{outcome}|1" or e[2]!=origin or e[3]!=symbol or e[15]!=str(held) or number(e[8])!=stop or number(e[9])!=target):
                    state="HOLD_TERMINAL_EVENT_MISMATCH"
                elif not e[16].startswith(RUN_PREFIX) or re.fullmatch("[1-9][0-9]{0,20}",e[16][len(RUN_PREFIX):]) is None:
                    state="HOLD_SOURCE_RUN_URL_MISSING"
                elif e[16][len(RUN_PREFIX):] not in verified_source_run_ids:
                    state="HOLD_SOURCE_RUN_UNVERIFIED"
                elif outcome in ("CORPORATE_ACTION_REVIEW","BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS"):
                    state="CENSORED_RESEARCH_ONLY"
                else:
                    state="LINKAGE_CANDIDATE_NEEDS_RAW_PATH_AND_FORECAST"
        counts[state]+=1;results.append({"episode_id":key,"readiness":state})
    return {"schema":"XRAY_CONFIDENCE_LEDGER_READINESS_V1","asof":asof,"episodes":len(candidates),"counts":dict(sorted(counts.items())),"rows":results,"source_authentication":"CALLER_WITNESS_NOT_ATTESTED","performance_labels_admitted":0,"may_fit":False,"may_notify":False,"may_trade":False}
