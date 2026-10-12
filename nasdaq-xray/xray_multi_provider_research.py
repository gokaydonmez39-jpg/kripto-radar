#!/usr/bin/env python3
"""C4.17 multi-provider quota-aware failover: RESEARCH ONLY, never AL/MC/G9/ACCOUNT authority."""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parent
SCHEMA="XRAY_MULTI_PROVIDER_RESEARCH_SHADOW_V1"
ROUTES={"MASTER":("SEC_TICKER_DIRECTORY","SEC_MIRROR_PIT","BQ_STOCK_PROFILE"),
        "MC":("MASSIVE_TICKER_PIT","BQ_MC_SCREENER"),
        "EVENT":("SEC_SUBMISSIONS","BQ_SEC_FILINGS")}
MAX_PER_RUN={"SEC_TICKER_DIRECTORY":1,"SEC_MIRROR_PIT":1,"SEC_SUBMISSIONS":3,
             "MASSIVE_TICKER_PIT":3,"BQ_STOCK_PROFILE":3,
             "BQ_MC_SCREENER":3,"BQ_SEC_FILINGS":3}
GROUP_CAP={"SEC":5,"MIRROR":1,"MASSIVE":3,"BQ":7}
SEC_DIRECTORY="https://www.sec.gov/files/company_tickers_exchange.json"
UA="NASDAQ-SWING-XRAY/1.0 non-trading research github.com/gokaydonmez39-jpg/kripto-radar"
SYMBOL=re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")

def blob(path):
    b=path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def proper_date(s):
    if not isinstance(s,str) or dt.date.fromisoformat(s).isoformat()!=s:
        raise ValueError("INVALID_ASOF")
    return s

def finite(v):
    if isinstance(v,bool):return None
    try:
        x=float(v)
        return x if math.isfinite(x) and x>0 else None
    except (ValueError,TypeError,OverflowError):return None

def http(url,headers=None,body=None):
    parts=urllib.parse.urlparse(url)
    if parts.scheme!="https" or parts.hostname not in (
        "www.sec.gov","data.sec.gov","data.businessquant.com","api.massive.com"):
        raise ValueError("UNAPPROVED_URL")
    req=urllib.request.Request(url,headers={
        "User-Agent":UA,"Accept":"application/json",**(headers or {})},
        data=None if body is None else json.dumps(body).encode("utf-8"),
        method="GET" if body is None else "POST")
    with urllib.request.urlopen(req,timeout=12) as resp:
        raw=resp.read(1500001)
        if len(raw)>1500000:raise ValueError("OVERSIZED_RESPONSE")
        return json.loads(raw)

def bq_url(endpoint,key,**params):
    # Vendor contract requires API key in URL; NEVER log URL/errors or publish raw data.
    return "https://data.businessquant.com/"+endpoint+"?"+urllib.parse.urlencode({**params,"api_key":key})

def sec_directory(http_get,cache):
    if "directory" not in cache:
        obj=http_get(SEC_DIRECTORY)
        fields=obj.get("fields") if isinstance(obj,dict) else None
        rows=obj.get("data") if isinstance(obj,dict) else None
        if not isinstance(fields,list) or not isinstance(rows,list):
            raise ValueError("SEC_DIRECTORY_SCHEMA")
        pos={n:i for i,n in enumerate(fields)}
        if not {"ticker","cik","exchange","name"}.issubset(pos):
            raise ValueError("SEC_DIRECTORY_FIELDS")
        m={}
        for row in rows:
            try:
                sym=str(row[pos["ticker"]]).upper()
                if SYMBOL.fullmatch(sym) and str(row[pos["exchange"]]).upper()=="NASDAQ":
                    m[sym]=(int(row[pos["cik"]]),str(row[pos["name"]]))
            except (IndexError,ValueError,TypeError):pass
        if not m:raise ValueError("SEC_DIRECTORY_EMPTY")
        cache["directory"]=m
    return cache["directory"]

def lookup(provider,sym,asof,keys,cache,http_get):
    if not SYMBOL.fullmatch(sym):raise ValueError("INVALID_SYMBOL")
    if provider=="SEC_TICKER_DIRECTORY":
        if sym not in sec_directory(http_get,cache):raise ValueError("SEC_UNKNOWN_TICKER")
        return "IDENTITY_DISCOVERY_ONLY"
    if provider=="SEC_MIRROR_PIT":
        if "mirror" not in cache:
            from sec_mirror_cik_shadow import discover
            master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
            if master.get("asof_et")!=asof or master.get("unknown_never_pass") is not True:
                raise ValueError("MIRROR_ASOF_DRIFT")
            result=discover(asof,master["unknown_symbols"])
            if result.get("status")!="EXACT_ASOF_CIK_DISCOVERY_ONLY":
                raise ValueError("MIRROR_PIT_UNVERIFIED")
            if result.get("ciK_discovered_count")!=len(result.get("ciK_discovery_only") or {}):
                raise ValueError("MIRROR_IDENTITY_PARTITION")
            cache["mirror"]=result["ciK_discovery_only"]
        if sym not in cache["mirror"]:
            raise ValueError("MIRROR_CIK_UNRESOLVED")
        return "IDENTITY_DISCOVERY_ONLY"
    if provider=="BQ_STOCK_PROFILE":
        obj=http_get(bq_url("stocks/profile",keys["BQ"],ticker=sym))
        row=obj.get("data",obj) if isinstance(obj,dict) else None
        if not isinstance(row,dict) or str(row.get("ticker","")).upper()!=sym or not str(row.get("cik") or "").strip("0").isdigit():
            raise ValueError("BQ_IDENTITY_UNVERIFIED")
        return "IDENTITY_DISCOVERY_ONLY"
    if provider=="MASSIVE_TICKER_PIT":
        url="https://api.massive.com/v3/reference/tickers/"+urllib.parse.quote(sym)+"?date="+asof
        obj=http_get(url,headers={"Authorization":"Bearer "+keys["MASSIVE"]})
        row=obj.get("results") if isinstance(obj,dict) else None
        if not isinstance(row,dict) or row.get("ticker")!=sym or row.get("market")!="stocks" or finite(row.get("market_cap")) is None:
            raise ValueError("MASSIVE_NO_MATCHING_PIT_MC")
        return "PIT_MC_DISCOVERY_ONLY"
    if provider=="BQ_MC_SCREENER":
        url=bq_url("screener",keys["BQ"],page=1,limit=5)
        obj=http_get(url,headers={"Content-Type":"application/json"},
            body={"conditions":"\"ticker\" = '"+sym+"'","preferred_columns":["Market Capitalization"]})
        rows=obj.get("data") if isinstance(obj,dict) else None
        if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or (
            str(rows[0].get("ticker","")).upper()!=sym or finite(rows[0].get("Market Capitalization")) is None):
            raise ValueError("BQ_MC_IDENTITY_OR_CAP_UNVERIFIED")
        # BQ current screener is not verified PIT for canonical ASOF.
        return "LATEST_NON_PIT_MC_DISCOVERY_ONLY"
    if provider=="SEC_SUBMISSIONS":
        row=sec_directory(http_get,cache).get(sym)
        if not row:raise ValueError("SEC_NO_CIK")
        obj=http_get("https://data.sec.gov/submissions/CIK"+f"{row[0]:010d}"+".json")
        recent=(obj.get("filings") or {}).get("recent") if isinstance(obj,dict) else None
        if not isinstance(recent,dict) or not any(isinstance(x,str) and x<=asof for x in recent.get("filingDate",[])):
            raise ValueError("SEC_NO_PRIOR_FILINGS")
        # Past filings DO NOT establish future earnings clearance.
        return "PAST_FILINGS_DISCOVERY_ONLY"
    if provider=="BQ_SEC_FILINGS":
        till=dt.date.fromisoformat(asof).strftime("%d-%m-%Y")
        obj=http_get(bq_url("secfilings",keys["BQ"],ticker=sym,
                            formtype="8-K,10-Q,10-K",till_date=till,page_size=20))
        meta=obj.get("metadata",{}) if isinstance(obj,dict) else {}
        rows=obj.get("data") if isinstance(obj,dict) else None
        if not isinstance(rows,list) or not rows or str(meta.get("ticker","")).upper()!=sym or not any(
            isinstance(r,dict) and isinstance(r.get("filingdate"),str) and r["filingdate"][:10]<=asof for r in rows):
            raise ValueError("BQ_NO_ASOF_MATCHING_FILINGS")
        return "PAST_FILINGS_DISCOVERY_ONLY"
    raise ValueError("UNKNOWN_PROVIDER")

def group(provider):
    return "MIRROR" if provider=="SEC_MIRROR_PIT" else (
        "BQ" if provider.startswith("BQ_") else "MASSIVE" if provider.startswith("MASSIVE_") else "SEC")

def reason(exc):
    if isinstance(exc,urllib.error.HTTPError):
        return "QUOTA_429" if exc.code==429 else "AUTH_DENIED" if exc.code in (401,403) else (
            "UPSTREAM_5XX" if exc.code>=500 else "HTTP_REJECTED")
    if isinstance(exc,(TimeoutError,ConnectionError,urllib.error.URLError)):return "TRANSPORT"
    return "INVALID_OR_INSUFFICIENT_RESPONSE"

def route(lane,sym,asof,keys,counters,cache,http_get=http,runner=lookup):
    attempts=[]
    for provider in ROUTES[lane]:
        g=group(provider)
        if g in ("MASSIVE","BQ") and not keys.get(g):
            attempts.append((provider,"NO_KEY"));continue
        needed=0 if (provider=="SEC_TICKER_DIRECTORY" and "directory" in cache) or (
            provider=="SEC_MIRROR_PIT" and "mirror" in cache) else 1
        if provider=="SEC_SUBMISSIONS" and "directory" not in cache:needed+=1
        if (needed>0 and counters[provider]>=MAX_PER_RUN[provider]) or counters[g]+needed>GROUP_CAP[g]:
            attempts.append((provider,"QUOTA_GUARD"));continue
        if cache.get("circuit:"+provider):
            attempts.append((provider,"CIRCUIT_OPEN"));continue
        counters[provider]+=1 if needed else 0
        counters[g]+=needed
        if provider=="SEC_SUBMISSIONS" and "directory" not in cache:
            counters["SEC_TICKER_DIRECTORY"]+=1
        try:
            status=runner(provider,sym,asof,keys,cache,http_get)
            if status not in ("IDENTITY_DISCOVERY_ONLY","PIT_MC_DISCOVERY_ONLY",
                              "LATEST_NON_PIT_MC_DISCOVERY_ONLY","PAST_FILINGS_DISCOVERY_ONLY"):
                raise ValueError("UNKNOWN_RESULT_TYPE")
            attempts.append((provider,status))
            return "REFERENCE_OBSERVED_NOT_AUTHORITY",attempts
        except Exception as e:
            code=reason(e)
            attempts.append((provider,code))
            if code in ("QUOTA_429","AUTH_DENIED"):
                cache["circuit:"+provider]=True
            # Discard exception body; API URL may contain a secret.
    return "UNKNOWN",attempts

def inputs():
    names={"MASTER":"canonical_current_master_manifest.json",
           "HISTORY":"canonical_current_history.json",
           "EVENT":"canonical_current_event_state.json",
           "TERMINAL":"canonical_current_terminal.json"}
    docs={k:json.loads((ROOT/v).read_text()) for k,v in names.items()}
    asof=proper_date(docs["TERMINAL"].get("asof_et"))
    for k,v in docs.items():
        if (v.get("asof_et")!=asof or v.get("execution")!="NONE" or v.get("real_money")!="NO-GO"
                or v.get("unknown_never_pass") is not True):
            raise ValueError("SOURCE_DRIFT:"+k)
    mcpath=docs["HISTORY"].get("source_mc_artifact","")
    if not re.fullmatch(r"nasdaq-xray/canonical_mc_bridge_[0-9]{8}_c417(?:_dv30_v[0-9]+)?\.json",mcpath):
        raise ValueError("INVALID_MC_PATH")
    full=ROOT.parent/mcpath
    if blob(full)!=docs["HISTORY"].get("source_mc_blob_sha"):
        raise ValueError("HISTORY_MC_BLOB_DRIFT")
    mc=json.loads(full.read_text())
    if mc.get("asof_et")!=asof or mc.get("unknown_never_pass") is not True:
        raise ValueError("MC_ASOF_DRIFT")
    scopes={"MASTER":docs["MASTER"]["unknown_symbols"],"MC":mc["unknown_symbols"],
            "EVENT":docs["EVENT"].get("affected_geometry_event_unknown") or []}
    for k,items in scopes.items():
        if not isinstance(items,list) or len(items)!=len(set(items)) or any(
            not isinstance(s,str) or not SYMBOL.fullmatch(s) for s in items):
            raise ValueError("INVALID_SCOPE:"+k)
    sha={k:blob(ROOT/v) for k,v in names.items()}
    sha["MC"]=blob(full)
    return asof,scopes,sha

def pre_mc_recovery_inputs(now_utc=None):
    """Exact current MASTER+PRICE bootstrap when 9-Oct MC/HISTORY/TERMINAL lag.

    The MC lane is the price-pass cohort, *not* a fabricated canonical MC
    unknown list. EVENT cannot run without exact terminal proof.
    Every reported SHA comes from the actual tracked local Git bytes.
    """
    from hashlib import sha256
    names={"MASTER":"canonical_current_master_manifest.json",
           "PRICE":"canonical_current_price_dv30.json",
           "HISTORY":"canonical_current_history.json",
           "EVENT":"canonical_current_event_state.json",
           "TERMINAL":"canonical_current_terminal.json"}
    master=json.loads((ROOT/names["MASTER"]).read_text())
    price=json.loads((ROOT/names["PRICE"]).read_text())
    asof=proper_date(price.get("asof_et"))
    from source_epoch_freshness_guard import last_complete_session
    instant=now_utc if now_utc is not None else dt.datetime.now(dt.timezone.utc)
    if asof!=last_complete_session(instant):
        raise ValueError("PRE_MC_PRICE_NOT_LATEST_OFFICIAL_COMPLETED_SESSION")
    if master.get("asof_et")!=asof:
        raise ValueError("PRE_MC_MASTER_PRICE_ASOF_MISMATCH")
    for row in (master,price):
        if row.get("execution")!="NONE" or row.get("real_money")!="NO-GO" or row.get("unknown_never_pass") is not True:
            raise ValueError("PRE_MC_SAFETY_NOT_FROZEN")
    ms,us,ps=master.get("pass_symbols"),master.get("unknown_symbols"),price.get("pass_symbols")
    for name,seq in (("MASTER_PASS",ms),("MASTER_UNKNOWN",us),("PRICE_PASS",ps)):
        if (not isinstance(seq,list) or seq!=sorted(set(seq))
            or any(not isinstance(x,str) or not SYMBOL.fullmatch(x) for x in seq)):
            raise ValueError("PRE_MC_SCOPE_INVALID:"+name)
    if (len(ms)!=master.get("pass_count") or len(us)!=master.get("unknown_count")
        or len(ps)!=price.get("pass_count") or set(ms)&set(us)
        or not set(ps).issubset(ms)):
        raise ValueError("PRE_MC_IDENTITY_COUNT_OR_MEMBERSHIP_MISMATCH")
    hashset=lambda rows:sha256("\n".join(rows).encode()).hexdigest()
    if (master.get("queue_hash")!=hashset(ms)
        or price.get("pass_hash")!=hashset(ps)
        or price.get("source_master_queue_hash")!=master.get("queue_hash")
        or price.get("source_master_count")!=len(ms)
        or price.get("unknown_count")!=0 or price.get("blocked_count")!=0):
        raise ValueError("PRE_MC_GIT_SCOPE_HASH_OR_PRICE_BLOCKED")
    sha={k:blob(ROOT/v) for k,v in names.items()}
    sha["MC"]=None  # no current PRIMARY MC authority: intentionally absent
    return asof,{"MASTER":us,"MC":ps,"EVENT":[]},sha


def rotate_sample(symbols,limit,day_ordinal=None):
    """Deterministic daily coverage; never continuously repeat the first 3 symbols."""
    ordered=sorted(symbols)
    if not ordered:return []
    n=dt.datetime.now(dt.timezone.utc).date().toordinal() if day_ordinal is None else day_ordinal
    start=(n*limit)%len(ordered)
    return [ordered[(start+i)%len(ordered)] for i in range(min(limit,len(ordered)))]

def source_epoch_blocked(reason: str)->dict:
    """Do not fetch stale mixed-ASOF sources. Explicit zero-call telemetry.

    A normal asynchronous MASTER/MC/HISTORY/TERMINAL revision is PENDING,
    not a programming crash, not success and emphatically not an AL.
    """
    if reason not in ("SOURCE_DRIFT:MASTER","SOURCE_DRIFT:HISTORY",
                      "SOURCE_DRIFT:EVENT","SOURCE_DRIFT:TERMINAL"):
        raise ValueError("UNKNOWN_SOURCE_EPOCH_DRIFT")
    source_names={"MASTER":"canonical_current_master_manifest.json",
                  "HISTORY":"canonical_current_history.json",
                  "EVENT":"canonical_current_event_state.json",
                  "TERMINAL":"canonical_current_terminal.json"}
    sha={k:blob(ROOT/filename) if (ROOT/filename).is_file() else None
         for k,filename in source_names.items()}
    sha["MC"]=None
    lanes={k:{"scope_count":0,"scope_unverified":True,
              "sample_attempted":0,"status_counts":{},"provider_attempts":{},
              "reason":"SOURCE_EPOCH_DRIFT_BLOCKED"} for k in ROUTES}
    return {"schema":SCHEMA,"asof_et":None,"policy":"C4.17","control":"C4.27",
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
            "research_only":True,"alpha_authority":False,
            "mc_pass_created":False,"g9_pass":False,"account_pass":False,
            "canonical_status_changed":False,"raw_market_data_persisted":False,
            "provider_keys_present":{"MASSIVE":bool(os.getenv("XRAY_MASSIVE_API_KEY","")),
                                     "BQ":bool(os.getenv("XRAY_BQ_API_KEY",""))},
            "source_epoch_exact":False,"source_epoch_block_reason":reason,
            "source_blobs":sha,"lanes":lanes,"invocation_counts":{},
            "result":"BLOCKED_SOURCE_EPOCH_NO_CALLS_NO_ALPHA"}


def produce(limit=3,http_get=http,runner=lookup,inputs_fn=inputs,
            allow_pre_mc_recovery=False,recovery_inputs_fn=pre_mc_recovery_inputs):
    if not isinstance(limit,int) or not 1<=limit<=3:raise ValueError("MAX_3_PER_LANE")
    recovery=False
    try:
        asof,scopes,sha=inputs_fn()
    except ValueError as e:
        msg=str(e)
        if msg.startswith("SOURCE_DRIFT:"):
            if not allow_pre_mc_recovery:
                return source_epoch_blocked(msg)
            # Deliberate independent exact source boundary: no MC or
            # terminal is read as current authority during recovery.
            try:
                asof,scopes,sha=recovery_inputs_fn()
            except (ValueError,KeyError,TypeError,OSError) as err:
                blocked=source_epoch_blocked(msg)
                blocked["pre_mc_recovery_failed_reason"]=type(err).__name__
                return blocked
            recovery=True
        else:
            raise
    # A GitHub Actions secret being present is NOT evidence of an unattended
    # derived-use licence. Explicit grant fence avoids an accidental API call.
    # Operator declarations are not a substitute for independent legal proof.
    def research_key(envkey,prefix):
        key=os.getenv(envkey,"").strip()
        approved=os.getenv(prefix+"_UNATTENDED_RESEARCH_LICENSE_OK","").lower()=="true"
        digest=os.getenv(prefix+"_LICENSE_EVIDENCE_SHA256","")
        if not (approved and re.fullmatch(r"[a-f0-9]{64}",digest)):
            return ""
        return key
    keys={"MASSIVE":research_key("XRAY_MASSIVE_API_KEY","XRAY_MASSIVE"),
          "BQ":research_key("XRAY_BQ_API_KEY","XRAY_BQ")}
    counters=collections.Counter()
    cache={}
    lanes={}
    for lane,symbols in scopes.items():
        statuses=collections.Counter()
        attempts=collections.Counter()
        for sym in rotate_sample(symbols,limit):
            status,logs=route(lane,sym,asof,keys,counters,cache,http_get,runner)
            statuses[status]+=1
            for provider,code in logs:attempts[provider+":"+code]+=1
        lanes[lane]={"scope_count":len(symbols),"sample_attempted":min(limit,len(symbols)),
                     "scope_unverified":bool(recovery and lane=="EVENT"),
                     "status_counts":dict(statuses),"provider_attempts":dict(attempts)}
    return {"schema":SCHEMA,"asof_et":asof,"policy":"C4.17","control":"C4.27",
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
            "research_only":True,"alpha_authority":False,
            "mc_pass_created":False,"g9_pass":False,"account_pass":False,
            "canonical_status_changed":False,"raw_market_data_persisted":False,
            "provider_keys_present":{k:bool(v) for k,v in keys.items()},
            "source_epoch_exact":not recovery,
            "pre_mc_recovery_source_exact":recovery,
            "post_mc_event_lane_ready":not recovery,
            "source_blobs":sha,"lanes":lanes,"invocation_counts":dict(counters),
            "result":"PRE_MC_SOURCE_EXACT_SHADOW_ONLY_NO_PRIMARY_NO_AL" if recovery else
                     "MULTI_PROVIDER_FAIL_CLOSED_SHADOW_ONLY_NO_C4_17_PROMOTION"}

def selftest():
    good=lambda *args:"PIT_MC_DISCOVERY_ONLY"
    q=collections.Counter()
    status,att=route("MC","ASTS","2026-10-07",{"BQ":"k","MASSIVE":""},q,{},runner=good)
    assert status=="REFERENCE_OBSERVED_NOT_AUTHORITY"
    assert att[0]==("MASSIVE_TICKER_PIT","NO_KEY") and att[1][0]=="BQ_MC_SCREENER"
    def quota(p,*args):
        if p=="MASSIVE_TICKER_PIT":
            raise urllib.error.HTTPError("https://api.massive.com/",429,"quota",{},None)
        return "LATEST_NON_PIT_MC_DISCOVERY_ONLY"
    c={}
    status,att=route("MC","ASTS","2026-10-07",{"BQ":"k","MASSIVE":"k"},
                     collections.Counter(),c,runner=quota)
    assert status=="REFERENCE_OBSERVED_NOT_AUTHORITY"
    assert att[0][1]=="QUOTA_429" and att[1][0]=="BQ_MC_SCREENER"
    assert c["circuit:MASSIVE_TICKER_PIT"] is True
    q=collections.Counter({"MASSIVE":GROUP_CAP["MASSIVE"],"BQ":GROUP_CAP["BQ"]})
    status,att=route("MC","ASTS","2026-10-07",{"BQ":"k","MASSIVE":"k"},q,{},runner=good)
    assert status=="UNKNOWN" and all(x[1]=="QUOTA_GUARD" for x in att)
    m={"fields":["ticker","name","cik","exchange"],
       "data":[["ALIS","Calisa Acquisition",1920406,"Nasdaq"]]}
    assert sec_directory(lambda url:m,{})["ALIS"][0]==1920406
    c=collections.Counter()
    mem={"mirror":{"ALIS":"0001920406"}}
    status,att=route("MASTER","ALIS","2026-10-07",{"BQ":"","MASSIVE":""},
                     c,mem,runner=lambda p,*args: (
                         "IDENTITY_DISCOVERY_ONLY" if p=="SEC_MIRROR_PIT" else
                         (_ for _ in ()).throw(ValueError("sec unavailable"))))
    assert status=="REFERENCE_OBSERVED_NOT_AUTHORITY"
    assert att[1]==("SEC_MIRROR_PIT","IDENTITY_DISCOVERY_ONLY")
    assert c["MIRROR"]==0
    assert finite(None) is None and finite(float("nan")) is None
    assert finite(2000000000)==2000000000
    assert rotate_sample(["A","B","C","D","E","F"],2,0)==["A","B"]
    assert rotate_sample(["A","B","C","D","E","F"],2,1)==["C","D"]
    assert rotate_sample(["A","B","C","D","E","F"],2,2)==["E","F"]
    assert rotate_sample([],2,0)==[]
    # Real repo pre-MC recovery: current MASTER/PRICE may advance while
    # HISTORY and TERMINAL remain stale. This MUST NOT freeze shadow discovery.
    fixture_asof=proper_date(json.loads((ROOT/"canonical_current_price_dv30.json").read_text())["asof_et"])
    fixture_now=dt.datetime.combine(dt.date.fromisoformat(fixture_asof),dt.time(23,30),
                                    tzinfo=dt.timezone.utc)
    recovered_asof,recovered_scopes,recovered_sha=pre_mc_recovery_inputs(now_utc=fixture_now)
    assert recovered_scopes["EVENT"]==[]
    assert recovered_scopes["MC"]==sorted(set(recovered_scopes["MC"]))
    assert len(recovered_scopes["MC"])>0
    assert recovered_sha["MC"] is None
    assert recovered_sha["PRICE"]==blob(ROOT/"canonical_current_price_dv30.json")
    assert recovered_sha["MASTER"]==blob(ROOT/"canonical_current_master_manifest.json")
    assert recovered_asof==json.loads((ROOT/"canonical_current_price_dv30.json").read_text())["asof_et"]
    # 9-Oct is latest through Mon-12 Oct 20:29 UTC. The same immutable
    # 9-Oct PRICE must not be replayed as "current" after Mon close+buffer.
    if recovered_asof=="2026-10-09":
        for instant in (dt.datetime(2026,10,10,12,tzinfo=dt.timezone.utc),
                        dt.datetime(2026,10,12,13,tzinfo=dt.timezone.utc),
                        dt.datetime(2026,10,12,20,29,tzinfo=dt.timezone.utc)):
            assert pre_mc_recovery_inputs(now_utc=instant)[0]=="2026-10-09"
        try:
            pre_mc_recovery_inputs(now_utc=dt.datetime(2026,10,12,20,30,tzinfo=dt.timezone.utc))
        except ValueError as e:
            assert str(e)=="PRE_MC_PRICE_NOT_LATEST_OFFICIAL_COMPLETED_SESSION"
        else:
            raise AssertionError("STALE_9OCT_REPLAY_AS_12OCT_CURRENT")
        try:
            pre_mc_recovery_inputs(now_utc=dt.datetime(2026,10,9,19,tzinfo=dt.timezone.utc))
        except ValueError as e:
            assert str(e)=="PRE_MC_PRICE_NOT_LATEST_OFFICIAL_COMPLETED_SESSION"
        else:
            raise AssertionError("FUTURE_9OCT_PRE_MARKET_CLOSE")
    print("XRAY_PRE_MC_OFFICIAL_SESSION_FRESHNESS=PASS_9OCT_THROUGH_12OCT_PRESETTLEMENT")

    # Deliberately simulate the production circular deadlock. Recovery must
    # inspect just MASTER/PRICE and never infer MC PRIMARY, EVENTS or R92.
    def synthetic_recovery():
        return "2026-10-09",{"MASTER":["ALIS"],"MC":["AAPL"],"EVENT":[]},{
            "MASTER":"a"*40,"PRICE":"b"*40,"MC":None,
            "HISTORY":"c"*40,"EVENT":"d"*40,"TERMINAL":"e"*40}
    def lagging_terminal():
        raise ValueError("SOURCE_DRIFT:TERMINAL")
    from unittest.mock import patch
    with patch.dict(os.environ,{"XRAY_MASSIVE_API_KEY":"SECRET_FAKE",
                                 "XRAY_BQ_API_KEY":"SECRET_FAKE",
                                 "XRAY_MASSIVE_UNATTENDED_RESEARCH_LICENSE_OK":"",
                                 "XRAY_BQ_UNATTENDED_RESEARCH_LICENSE_OK":""}):
        recovery=produce(1,inputs_fn=lagging_terminal,
                         recovery_inputs_fn=synthetic_recovery,
                         allow_pre_mc_recovery=True,
                         runner=lambda p,*a:"IDENTITY_DISCOVERY_ONLY")
    assert recovery["result"]=="PRE_MC_SOURCE_EXACT_SHADOW_ONLY_NO_PRIMARY_NO_AL"
    assert recovery["source_epoch_exact"] is False
    assert recovery["pre_mc_recovery_source_exact"] is True
    assert recovery["lanes"]["MC"]["scope_count"]==1
    assert recovery["lanes"]["EVENT"]["scope_unverified"] is True
    assert recovery["provider_keys_present"]=={"MASSIVE":False,"BQ":False}
    assert recovery["mc_pass_created"] is False and recovery["alpha_authority"] is False
    assert recovery["g9_pass"] is False and recovery["raw_market_data_persisted"] is False
    no_recovery=produce(1,inputs_fn=lagging_terminal,
                        recovery_inputs_fn=lambda: (_ for _ in ()).throw(ValueError("BAD_MASTER")),
                        allow_pre_mc_recovery=True,
                        runner=lambda *a: (_ for _ in ()).throw(AssertionError("NETWORK_WITH_BAD_MASTER")))
    assert no_recovery["result"]=="BLOCKED_SOURCE_EPOCH_NO_CALLS_NO_ALPHA"
    assert no_recovery["invocation_counts"]=={}
    print("XRAY_PRE_MC_514_SHADOW_RECOVERY=PASS_LAG_TERMINAL_INDEPENDENT_ZERO_PRIMARY")
    def stale_inputs():
        raise ValueError("SOURCE_DRIFT:MASTER")
    blocked=produce(1,inputs_fn=stale_inputs,
                    runner=lambda *a: (_ for _ in ()).throw(AssertionError("NETWORK_ON_DRIFT")))
    assert blocked["result"]=="BLOCKED_SOURCE_EPOCH_NO_CALLS_NO_ALPHA"
    assert blocked["source_epoch_exact"] is False
    assert set(blocked["source_blobs"])=={"MASTER","MC","HISTORY","EVENT","TERMINAL"}
    assert set(blocked["lanes"])=={"MASTER","MC","EVENT"}
    assert all(v["sample_attempted"]==0 and v["scope_unverified"] is True
               for v in blocked["lanes"].values())
    assert blocked["invocation_counts"]=={} and blocked["alpha_authority"] is False
    for unsafe in ("HISTORY_MC_BLOB_DRIFT","FAKE_DRIFT"):
        def bogus(c=unsafe):
            raise ValueError(c)
        try:
            produce(1,inputs_fn=bogus)
        except ValueError:
            continue
        raise AssertionError("CORRUPTION_OR_UNKNOWN_ERROR_WAS_SILENCED")
    assert _guard_invalid_url()
    print("XRAY_MULTI_PROVIDER_FAIL_CLOSED_SELFTEST=PASS")

def _guard_invalid_url():
    try:http("http://localhost:8080/secret")
    except ValueError:return True
    return False

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--limit",type=int,default=3)
    ap.add_argument("--pre-mc-recovery",action="store_true")
    ap.add_argument("--out",default="/tmp/xray_multi_provider_research.json")
    args=ap.parse_args()
    if args.selftest:
        selftest();return
    out=pathlib.Path(args.out)
    out.unlink(missing_ok=True)
    result=produce(args.limit,allow_pre_mc_recovery=args.pre_mc_recovery)
    out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_MULTI_PROVIDER_RESEARCH="+result["result"])
    for lane,v in result["lanes"].items():
        print("XRAY_"+lane+"_OBSERVATIONS="+str(v["status_counts"].get("REFERENCE_OBSERVED_NOT_AUTHORITY",0)))

if __name__=="__main__":
    main()
