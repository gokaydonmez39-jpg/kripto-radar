#!/usr/bin/env python3
"""One authorized BusinessQuant historical MC batch, PRICE-UNKNOWN independent.

A bounded, one-request, <=5-ticker shadow-only date/metric presence probe.
No market-cap values, raw vendor bodies, tokens or URLs are persisted. Missing
account, runner key, permission, or PIT leaves canonical C4.17 PRIMARY blocked.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import urllib.error
from pathlib import Path

from bq_history_onecall_shadow import research_grant_claim
from xray_multi_provider_research import bq_historic_batch_shadow, http

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
MASTER=ROOT/"canonical_current_master_manifest.json"
PRICE=ROOT/"canonical_current_price_dv30.json"
SCHEMA="XRAY_BQ_MC_EXACT_ASOF_PRICE_INDEPENDENT_SHADOW_V1"

def source_scope(master,price,latest):
    if (master.get("asof_et")!=price.get("asof_et") or
        price.get("asof_et")!=latest or
        master.get("execution")!="NONE" or master.get("real_money")!="NO-GO" or
        price.get("execution")!="NONE" or price.get("real_money")!="NO-GO" or
        master.get("unknown_never_pass") is not True or
        price.get("unknown_never_pass") is not True):
        raise ValueError("UNTRUSTED_EPOCH_OR_SAFETY")
    ms=master.get("pass_symbols")
    ps=price.get("pass_symbols")
    us=price.get("unknown_symbols")
    if (not all(isinstance(x,list) and len(x)==len(set(x)) for x in (ms,ps,us))
        or len(ms)!=master.get("pass_count") or len(ps)!=price.get("pass_count")
        or len(us)!=price.get("unknown_count") or set(ps)&set(us)
        or not set(ps+us).issubset(set(ms))):
        raise ValueError("INVALID_CANONICAL_PARTITION")
    # PRICE UNKNOWN is allowed for provider readiness; NEVER promoted to pass.
    sample=sorted(ps)[:5] if ps else sorted(us)[:5]
    return sample,"PRICE_PASS_DIAGNOSTIC" if ps else "PRICE_UNKNOWN_DIAGNOSTIC"

def report(asof):
    return {"schema":SCHEMA,"provider":"BUSINESSQUANT",
        "asof_et":asof,"policy":"C4.17","control":"C4.27",
        "status":"BLOCKED_UNVERIFIED_INPUT","api_calls":0,
        "sample_symbols_requested":0,"dated_metric_rows_present":0,
        "price_unknown_allowed_for_observation":True,
        "source_cohort_role":None,"runner_key_configured":False,
        "operator_grant_claimed":False,"license_independently_verified":False,
        "market_cap_values_persisted":False,"vendor_raw_data_persisted":False,
        "request_url_or_key_persisted":False,"filing_acceptance_pit_attested":False,
        "current_primary_market_cap_created":False,"history_pass_created":False,
        "r92_created":False,"alpha_authority":False,"strict_g9_pass":False,
        "account_pass":False,"can_create_primary":False,"research_only":True,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def run(master,price,latest,env,http_get=http):
    out=report(price.get("asof_et"))
    try:
        sample,role=source_scope(master,price,latest)
    except Exception:
        out["status"]="BLOCKED_STALE_OR_INVALID_CANONICAL_SOURCE"
        return out
    out["source_cohort_role"]=role
    if not sample:
        out["status"]="BLOCKED_NO_RESEARCH_SAMPLE"
        return out
    key=env.get("XRAY_BQ_API_KEY","").strip()
    out["runner_key_configured"]=bool(key)
    out["operator_grant_claimed"]=research_grant_claim(env)
    if not key:
        out["status"]="BLOCKED_RUNNER_KEY_NOT_CONFIGURED"
        return out
    if not out["operator_grant_claimed"]:
        out["status"]="BLOCKED_RESEARCH_LICENSE_NOT_ATTESTED"
        return out
    out["sample_symbols_requested"]=len(sample)
    out["api_calls"]=1
    try:
        found=bq_historic_batch_shadow(sample,latest,key,http_get)
        out["dated_metric_rows_present"]=sum(found.values())
        out["status"]=("SHADOW_DATED_MC_METRIC_OBSERVED_NO_PRIMARY" if all(found.values())
                       else "SHADOW_SOME_DATED_MC_METRIC_MISSING_NO_PRIMARY")
    except urllib.error.HTTPError as exc:
        out["status"]=("BLOCKED_HTTP_401_403" if exc.code in (401,403) else
                       "BLOCKED_HTTP_429" if exc.code==429 else "BLOCKED_VENDOR_HTTP")
    except (urllib.error.URLError,OSError,TimeoutError):
        out["status"]="BLOCKED_VENDOR_TRANSPORT"
    except Exception:
        out["status"]="BLOCKED_VENDOR_SCHEMA_OR_IDENTITY"
    return out

def selftest():
    master={"asof_et":"2026-10-12","execution":"NONE","real_money":"NO-GO",
            "unknown_never_pass":True,"pass_count":5,
            "pass_symbols":["AAPL","AAON","AAL","AAOI","NVDA"]}
    price={"asof_et":"2026-10-12","execution":"NONE","real_money":"NO-GO",
           "unknown_never_pass":True,"pass_count":0,"pass_symbols":[],
           "unknown_count":5,"unknown_symbols":["AAPL","AAON","AAL","AAOI","NVDA"]}
    scope,role=source_scope(master,price,"2026-10-12")
    assert len(scope)==5 and role=="PRICE_UNKNOWN_DIAGNOSTIC"
    calls=[]
    def mocked(url):
        calls.append(url)
        from urllib.parse import urlsplit,parse_qs
        x=urlsplit(url);q=parse_qs(x.query)
        assert x.scheme=="https" and x.hostname=="data.businessquant.com" and x.path=="/historic"
        assert q["slug"]==["market-capitalization-daily"] and q["mode"]==["original"]
        assert q["from_date"]==q["till_date"]==["2026-10-12"]
        assert q["ticker"]==[",".join(scope)]
        return [{"ticker":s,"date":"2026-10-12","metric":"Market Capitalization","value":2000000000}
                for s in scope]
    no=run(master,price,"2026-10-12",{},mocked)
    assert no["api_calls"]==0 and not calls
    no=run(master,price,"2026-10-12",{"XRAY_BQ_API_KEY":"SECRET"},mocked)
    assert no["api_calls"]==0 and no["status"]=="BLOCKED_RESEARCH_LICENSE_NOT_ATTESTED"
    assert not calls
    env={"XRAY_BQ_API_KEY":"SECRET","XRAY_BQ_UNATTENDED_RESEARCH_LICENSE_OK":"true",
         "XRAY_BQ_LICENSE_EVIDENCE_SHA256":"a"*64}
    yes=run(master,price,"2026-10-12",env,mocked)
    assert yes["api_calls"]==1 and len(calls)==1
    assert yes["dated_metric_rows_present"]==5
    assert yes["status"]=="SHADOW_DATED_MC_METRIC_OBSERVED_NO_PRIMARY"
    assert "SECRET" not in json.dumps(yes)
    assert all(yes[k] is False for k in ("license_independently_verified","filing_acceptance_pit_attested",
        "market_cap_values_persisted","current_primary_market_cap_created",
        "can_create_primary","r92_created","history_pass_created","alpha_authority"))
    stale=run(master,price,"2026-10-13",env,mocked)
    assert stale["api_calls"]==0 and len(calls)==1
    bad=dict(price,unknown_symbols=["AAPL","AAPL","AAL","AAOI","NVDA"])
    assert run(master,bad,"2026-10-12",env,mocked)["api_calls"]==0
    bad=dict(price,unknown_count=4)
    assert run(master,bad,"2026-10-12",env,mocked)["api_calls"]==0
    bad=dict(price,unknown_symbols=["AAPL","AAON","AAL","AAOI","NO_SUCH"])
    assert run(master,bad,"2026-10-12",env,mocked)["api_calls"]==0
    def fractional_bad(url):
        data=mocked(url);data[0]["value"]=float("nan")
        return data
    err=run(master,price,"2026-10-12",env,fractional_bad)
    assert err["status"]=="BLOCKED_VENDOR_SCHEMA_OR_IDENTITY"
    def duplicate_bad(url):
        data=mocked(url);data.append(dict(data[0]))
        return data
    err=run(master,price,"2026-10-12",env,duplicate_bad)
    assert err["status"]=="BLOCKED_VENDOR_SCHEMA_OR_IDENTITY"
    print("XRAY_BQ_PRICE_INDEPENDENT_MC_SHADOW_SELFTEST=PASS_BOUNDED_FIVE_ONE_CALL_NO_LICENCE_NO_PRIMARY")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:selftest();return
    if a.out is None:p.error("--out required")
    if a.out.resolve().is_relative_to(REPO.resolve()):
        p.error("PUBLIC_REPO_OUTPUT_FORBIDDEN")
    from source_epoch_freshness_guard import last_complete_session
    try:
        latest=last_complete_session(dt.datetime.now(dt.timezone.utc))
        master=json.loads(MASTER.read_text())
        price=json.loads(PRICE.read_text())
        result=run(master,price,latest,os.environ)
    except Exception:
        result=report(None)
        result["status"]="BLOCKED_UNREADABLE_CANONICAL_OR_CALENDAR"
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_BQ_MC_PRICE_INDEPENDENT="+result["status"])
    print("XRAY_BQ_MC_SHADOW_CALLS="+str(result["api_calls"]))
    print("XRAY_BQ_MC_NO_PRIMARY_NO_R92=PASS")

if __name__=="__main__":main()
