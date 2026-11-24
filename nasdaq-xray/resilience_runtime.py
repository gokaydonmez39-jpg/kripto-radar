#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, threading, time, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
LEDGER=ROOT/"provider_health_ledger.json"
CACHE=ROOT/".resilience_cache"
_LOCK=threading.Lock()
_INFLIGHT={}
_MEM={}

def now(): return datetime.now(timezone.utc).isoformat()

def load_ledger():
    try: return json.loads(LEDGER.read_text())
    except Exception: return {"schema":"XRAY_PROVIDER_HEALTH_LEDGER_V1","providers":{}}

def save_ledger(x):
    tmp=LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")
    tmp.replace(LEDGER)

def _provider_state(provider):
    l=load_ledger(); p=l.setdefault("providers",{}).setdefault(provider,{})
    return l,p

def classify_exception(exc):
    """Return machine-readable retry semantics for provider failures.

    Retryable failures are transport/upstream conditions that may recover
    without operator/config changes. Definitive auth/permission/not-found and
    other client errors must not poison the transient circuit breaker.
    """
    if isinstance(exc, urllib.error.HTTPError):
        status=int(getattr(exc,"code",0) or 0)
        if status in {408,425,429} or 500 <= status <= 599:
            return {"retryable":True,"code":"HTTP_TRANSIENT","http_status":status}
        return {"retryable":False,"code":"HTTP_DEFINITIVE","http_status":status}
    if isinstance(exc, json.JSONDecodeError):
        return {"retryable":True,"code":"UPSTREAM_INVALID_JSON","http_status":None}
    if isinstance(exc, (TimeoutError, ConnectionError, urllib.error.URLError, OSError)):
        return {"retryable":True,"code":"TRANSPORT_TRANSIENT","http_status":None}
    return {"retryable":False,"code":"INTERNAL_OR_DEFINITIVE","http_status":None}

def _record_success(provider):
    l,p=_provider_state(provider)
    p.update({
        "status":"HEALTHY","consecutive_failures":0,"last_success_at_utc":now(),
        "last_error":None,"last_error_code":None,"last_error_retryable":None,
        "last_http_status":None,"open_until_epoch":0
    })
    l["updated_at_utc"]=now(); save_ledger(l)

def failure_message(provider,exc,cls):
    # FRED uses a query-string API key. Never persist raw exception text for it.
    if provider=="FRED":
        status=cls.get("http_status")
        return "FRED:HTTP_"+str(status) if type(status) is int and 100<=status<=599 else "FRED:PROVIDER_ERROR"
    status=cls.get("http_status")
    return "HTTP_"+str(status) if type(status) is int and 100<=status<=599 else cls["code"]

def _record_failure(provider,exc,circuit_failures,cooldown):
    cls=classify_exception(exc)
    l,p=_provider_state(provider)
    err=failure_message(provider,exc,cls)
    if cls["retryable"]:
        n=int(p.get("consecutive_failures") or 0)+1
        p.update({
            "status":"DEGRADED","consecutive_failures":n,
            "last_failure_at_utc":now(),"last_error":err,
            "last_error_code":cls["code"],"last_error_retryable":True,
            "last_http_status":cls["http_status"]
        })
        if n>=circuit_failures:
            p["open_until_epoch"]=time.time()+cooldown
            p["status"]="CIRCUIT_OPEN"
    else:
        # Definitive failures (e.g. 401/403/404) need a config/permission/source
        # change, not repeated hammering. They do not count toward the transient
        # circuit and also clear a circuit that may have been poisoned by older
        # versions that misclassified definitive 4xx responses.
        p.update({
            "status":"NONRETRYABLE_ERROR","consecutive_failures":0,
            "last_failure_at_utc":now(),"last_error":err,
            "last_error_code":cls["code"],"last_error_retryable":False,
            "last_http_status":cls["http_status"],"open_until_epoch":0
        })
    l["updated_at_utc"]=now(); save_ledger(l)
    return cls

def _check_circuit(provider,now_s):
    l,p=_provider_state(provider)
    open_until=float(p.get("open_until_epoch") or 0)
    if open_until>now_s:
        raise RuntimeError(f"CIRCUIT_OPEN:{provider}:{int(open_until-now_s)}s")

def _retry_sleep(provider,url,attempt_index,base_delay,jitter):
    """Deterministic bounded jitter so retries do not synchronize in herds."""
    d=max(0.0,float(base_delay))
    j=max(0.0,min(float(jitter),0.5))
    if d<=0 or j<=0:
        if d>0: time.sleep(d)
        return
    h=hashlib.sha256(f"{provider}|{url}|{attempt_index}".encode()).digest()
    u=int.from_bytes(h[:8],"big")/(2**64-1)
    factor=1.0 + j*(2*u-1)
    time.sleep(max(0.0,d*factor))

def _attempt_budget(timeout,retry_delays):
    ds=[max(0.0,float(x)) for x in (retry_delays or ())]
    return (len(ds)+1)*float(timeout)+sum(ds)+5.0

def fetch_json(provider,url,headers=None,timeout=20,cache_ttl=0,circuit_failures=3,cooldown=120,retry_delays=(1.0,4.0),retry_jitter=0.20):
    key=provider+"|"+url
    now_s=time.time()
    with _LOCK:
        hit=_MEM.get(key)
        if hit and hit[0]>now_s: return hit[1]
    _check_circuit(provider,now_s)
    evt=None
    with _LOCK:
        evt=_INFLIGHT.get(key)
        if evt is None:
            evt=threading.Event(); _INFLIGHT[key]=evt; owner=True
        else: owner=False
    if not owner:
        evt.wait(_attempt_budget(timeout,retry_delays))
        with _LOCK:
            hit=_MEM.get(key)
        if hit and hit[0]>time.time(): return hit[1]
        raise RuntimeError(f"SINGLE_FLIGHT_OWNER_FAILED:{provider}")
    try:
        delays=tuple(retry_delays or ())
        last=None
        for attempt in range(len(delays)+1):
            try:
                req=urllib.request.Request(url,headers=headers or {"Accept":"application/json"})
                with urllib.request.urlopen(req,timeout=timeout) as r:
                    data=json.loads(r.read().decode("utf-8"))
                _record_success(provider)
                with _LOCK: _MEM[key]=(time.time()+max(1,cache_ttl),data)
                return data
            except Exception as e:
                last=e
                cls=classify_exception(e)
                if (not cls["retryable"]) or attempt>=len(delays):
                    _record_failure(provider,e,circuit_failures,cooldown)
                    raise
                _retry_sleep(provider,url,attempt+1,delays[attempt],retry_jitter)
        raise last if last is not None else RuntimeError(f"RETRY_EXHAUSTED:{provider}")
    finally:
        with _LOCK:
            _INFLIGHT.pop(key,None); evt.set()

def fetch_text(provider,url,headers=None,timeout=20,cache_ttl=0,circuit_failures=3,cooldown=120,retry_delays=(1.0,4.0),retry_jitter=0.20):
    key=provider+"|TEXT|"+url
    now_s=time.time()
    with _LOCK:
        hit=_MEM.get(key)
        if hit and hit[0]>now_s: return hit[1]
    _check_circuit(provider,now_s)
    evt=None
    with _LOCK:
        evt=_INFLIGHT.get(key)
        if evt is None:
            evt=threading.Event(); _INFLIGHT[key]=evt; owner=True
        else: owner=False
    if not owner:
        evt.wait(_attempt_budget(timeout,retry_delays))
        with _LOCK:
            hit=_MEM.get(key)
        if hit and hit[0]>time.time(): return hit[1]
        raise RuntimeError(f"SINGLE_FLIGHT_OWNER_FAILED:{provider}")
    try:
        delays=tuple(retry_delays or ())
        last=None
        for attempt in range(len(delays)+1):
            try:
                req=urllib.request.Request(url,headers=headers or {})
                with urllib.request.urlopen(req,timeout=timeout) as r:
                    data=r.read().decode("utf-8")
                _record_success(provider)
                with _LOCK: _MEM[key]=(time.time()+max(1,cache_ttl),data)
                return data
            except Exception as e:
                last=e
                cls=classify_exception(e)
                if (not cls["retryable"]) or attempt>=len(delays):
                    _record_failure(provider,e,circuit_failures,cooldown)
                    raise
                _retry_sleep(provider,url,attempt+1,delays[attempt],retry_jitter)
        raise last if last is not None else RuntimeError(f"RETRY_EXHAUSTED:{provider}")
    finally:
        with _LOCK:
            _INFLIGHT.pop(key,None); evt.set()

# Public diagnostics only; preserve the original circuit-state schema and each
# observation timestamp. A successful HTTP request is not data/license authority.
HEALTH_PROVIDERS=frozenset({
    "CLOUDFLARE_STATUS","CLOUDFLARE_RADAR","GITHUB_REPO_VERIFY","GITHUB_STATUS",
    "NASDAQ_ADDS_DELETES","NASDAQ_SECURITY_STATUS","NASDAQ_SYSTEM_STATUS_IPO",
    "NASDAQ_SYSTEM_STATUS_SELFHELP","NASDAQ_TRADE_HALTS","SEC_EFTS",
    "SEC_TICKER_MAP","SEC_SUBMISSIONS","US_TREASURY_YIELD_CURVE","FRED",
})
HEALTH_CODES=frozenset({"HTTP_TRANSIENT","HTTP_DEFINITIVE","UPSTREAM_INVALID_JSON",
                        "TRANSPORT_TRANSIENT","INTERNAL_OR_DEFINITIVE"})
HEALTH_FIELDS=frozenset({"status","consecutive_failures","last_error","last_error_code",
    "last_error_retryable","last_http_status","open_until_epoch",
    "last_success_at_utc","last_failure_at_utc"})

def prepare_health_publication(previous,current,at):
    import math
    def require(ok,label):
        if not ok: raise ValueError(label)
    def stamp(v):
        require(type(v) is str,"HEALTH_TIMESTAMP_TYPE")
        d=datetime.fromisoformat(v)
        require(d.tzinfo is not None and d<=at,"HEALTH_TIMESTAMP_FUTURE_OR_NAIVE")
        return d
    require(at.tzinfo is not None,"HEALTH_CLOCK")
    for obj in (previous,current):
        require(type(obj) is dict and set(obj)=={"schema","providers","updated_at_utc"}
                and obj["schema"]=="XRAY_PROVIDER_HEALTH_LEDGER_V1"
                and type(obj["providers"]) is dict
                and set(obj["providers"])<=HEALTH_PROVIDERS,"HEALTH_SCHEMA_OR_PROVIDER")
    old,new=previous["providers"],current["providers"]
    before,after=stamp(previous["updated_at_utc"]),stamp(current["updated_at_utc"])
    require(0<=(at-after).total_seconds()<=900 and after>before,"HEALTH_GENERATION_AGE")
    require(set(old)<=set(new),"HEALTH_PROVIDER_REMOVED")
    output={}
    observed=0
    for name,row in new.items():
        require(type(row) is dict and set(row)<=HEALTH_FIELDS,"HEALTH_ROW_SCHEMA")
        state=row.get("status")
        n=row.get("consecutive_failures")
        retry=row.get("last_error_retryable")
        code=row.get("last_error_code")
        http=row.get("last_http_status")
        until=row.get("open_until_epoch",0)
        require(type(n) is int and n>=0 and type(until) in (float,int)
                and math.isfinite(until) and until>=0,"HEALTH_COUNTER")
        require(http is None or (type(http) is int and 100<=http<=599),"HEALTH_HTTP")
        times={}
        for key in ("last_success_at_utc","last_failure_at_utc"):
            if key in row:
                times[key]=stamp(row[key])
                require(times[key]<=after,"HEALTH_OBSERVATION_AFTER_UPDATE")
            if key in old.get(name,{}):
                require(key in times and times[key]>=stamp(old[name][key]),"HEALTH_OBSERVATION_REGRESSION")
            if key in times and (key not in old.get(name,{}) or times[key]>stamp(old[name][key])):
                observed+=1
        success=times.get("last_success_at_utc")
        failure=times.get("last_failure_at_utc")
        if state=="HEALTHY":
            require(success is not None and (failure is None or success>=failure)
                    and n==0 and until==0 and retry is None and code is None and http is None,
                    "HEALTH_SUCCESS_CONTRADICTION")
            error=None
        elif state in ("DEGRADED","CIRCUIT_OPEN","NONRETRYABLE_ERROR"):
            require(failure is not None and (success is None or failure>=success)
                    and code in HEALTH_CODES,"HEALTH_FAILURE_CONTRADICTION")
            if state=="NONRETRYABLE_ERROR":
                require(retry is False and n==0 and until==0
                        and code in {"HTTP_DEFINITIVE","INTERNAL_OR_DEFINITIVE"},"HEALTH_DEFINITIVE_CONTRADICTION")
            else:
                require(retry is True and n>0 and code not in {"HTTP_DEFINITIVE","INTERNAL_OR_DEFINITIVE"}
                        and (state!="CIRCUIT_OPEN" or until>0),"HEALTH_RETRY_CONTRADICTION")
            error=("FRED:HTTP_"+str(http) if http is not None else "FRED:PROVIDER_ERROR") if name=="FRED" else ("HTTP_"+str(http) if http is not None else code)
        else:
            raise ValueError("HEALTH_UNKNOWN_STATE")
        # A changed state requires a changed observation, not just a new file timestamp.
        if name in old and state!=old[name].get("status"):
            require(any(key not in old[name] or value>stamp(old[name][key]) for key,value in times.items()),
                    "HEALTH_STATE_WITHOUT_OBSERVATION")
        clean={"status":state,"consecutive_failures":n,"last_error":error,
               "last_error_code":code,"last_error_retryable":retry,"last_http_status":http,
               "open_until_epoch":until}
        clean.update({key:row[key] for key in times})
        output[name]=clean
    require(observed>0,"HEALTH_NO_NEW_OBSERVATIONS")
    return {"schema":current["schema"],"updated_at_utc":current["updated_at_utc"],"providers":output}

def health_publication_selftest():
    from copy import deepcopy
    def require(ok,label):
        if not ok: raise AssertionError(label)
    oldstamp="2026-11-24T20:00:00+00:00"
    stamp="2026-11-24T21:00:00+00:00"
    at=datetime.fromisoformat(stamp)
    old={"schema":"XRAY_PROVIDER_HEALTH_LEDGER_V1","updated_at_utc":oldstamp,
         "providers":{"GITHUB_STATUS":{"status":"HEALTHY","consecutive_failures":0,
            "last_error":None,"last_error_code":None,"last_error_retryable":None,
            "last_http_status":None,"open_until_epoch":0,"last_success_at_utc":oldstamp}}}
    curr=deepcopy(old);curr["updated_at_utc"]=stamp
    curr["providers"]["SEC_TICKER_MAP"]={"status":"NONRETRYABLE_ERROR","consecutive_failures":0,
       "last_error":"https://example.invalid/?secret=TEST_SECRET","last_error_code":"HTTP_DEFINITIVE",
       "last_error_retryable":False,"last_http_status":403,"open_until_epoch":0,
       "last_failure_at_utc":stamp}
    got=prepare_health_publication(old,curr,at)
    require(got["providers"]["GITHUB_STATUS"]["last_success_at_utc"]==oldstamp,"PRESERVE_OLD_OBSERVATION")
    require(got["providers"]["SEC_TICKER_MAP"]["last_error"]=="HTTP_403"
            and "TEST_SECRET" not in json.dumps(got),"REDACT_SECRET")
    cases=[]
    def negative(label,change):
        x=deepcopy(curr);change(x);cases.append((label,x))
    negative("DROPPED",lambda x:x["providers"].pop("GITHUB_STATUS"))
    negative("UNKNOWN_PROVIDER",lambda x:x["providers"].update({"BAD":{}}))
    negative("NO_OBSERVATION",lambda x:x["providers"].pop("SEC_TICKER_MAP"))
    negative("FALSE_HEALTHY",lambda x:x["providers"]["SEC_TICKER_MAP"].update(status="HEALTHY"))
    negative("FUTURE",lambda x:x["providers"]["SEC_TICKER_MAP"].update(last_failure_at_utc="2026-11-25T00:00:00+00:00"))
    negative("REGRESSION",lambda x:x["providers"]["GITHUB_STATUS"].update(last_success_at_utc="2026-11-23T00:00:00+00:00"))
    negative("STALE_GENERATION",lambda x:x.update(updated_at_utc=oldstamp))
    negative("UNEXPECTED_FIELD",lambda x:x["providers"]["GITHUB_STATUS"].update(secret="TEST_SECRET"))
    for label,x in cases:
        try:prepare_health_publication(old,x,at)
        except ValueError:continue
        raise AssertionError("HEALTH_NEGATIVE_ACCEPTED:"+label)
    print("XRAY_PROVIDER_HEALTH_PUBLICATION_SELFTEST=PASS_PRESERVE_REDACT_8_NEGATIVE")

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--selftest-health-publication",action="store_true")
    group.add_argument("--prepare-health-publication",nargs=3,type=Path)
    args=ap.parse_args()
    if args.selftest_health_publication:
        health_publication_selftest()
    else:
        prior,current,out=args.prepare_health_publication
        result=prepare_health_publication(json.loads(prior.read_text()),json.loads(current.read_text()),datetime.now(timezone.utc))
        out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        print("XRAY_PROVIDER_HEALTH_PUBLICATION_VALIDATED=OBSERVATIONS_ONLY")
