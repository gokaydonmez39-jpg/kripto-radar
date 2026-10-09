#!/usr/bin/env python3
"""Fail-closed Twelve Data $0 individual EOD HISTORY private transport.

This is a SOURCE TRANSPORT SHADOW, never permission, MC, HISTORY authority,
a real R92, execution, or a notification. US venue-complete volume, all PIT
corporate actions, identity continuity and tier-specific private caching
rights require separate independent evidence. Do not set rights flags merely
to make CI pass. No vendor response or credential enters public GitHub.
"""
from __future__ import annotations
import argparse
import base64
import csv
import gzip
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import date,datetime,time as dtime,timedelta,timezone
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal
from source_epoch_freshness_guard import last_complete_session
from pathlib import Path
from tempfile import TemporaryDirectory

from current_history_source_request import sha256_lines
from history_transport_cache_guard import cache_path
from massive_grouped_history_resume import scope as _raw_scope
from twelve_data_history_probe import eod_query

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
SCHEMA="XRAY_TWELVE_260_HISTORY_ENCRYPTED_SHADOW_V1"
REPORT="XRAY_TWELVE_260_HISTORY_HEALTH_V1"
MAX_CALLS=32
MAX_RETRIES_PER_SYMBOL=3
MIN_SPACING_SECONDS=9.0
DAY_BUDGET=800
WINDOW_SECONDS=86400.0
MAX_RESPONSE_BYTES=350000
MAX_CIPHERTEXT_BYTES=90000000

class ProviderDenied(Exception):
    pass

def scope():
    """A zero-PASS PRICE cohort is empty, NEVER phantom QQQ-only history."""
    s=_raw_scope()
    if not s["symbols"]:
        assert s["targets"]==["QQQ"],"UNEXPECTED_EMPTY_PRICE_SCOPE_SHAPE"
        s=dict(s,targets=[])
    return s

def authorized(env):
    d=env.get("XRAY_TWELVE_LICENSE_EVIDENCE_SHA256","")
    import re
    return (len(env.get("XRAY_TWELVE_DATA_API_KEY",""))>=20
        and env.get("XRAY_TWELVE_NONDISPLAY_LICENSE_OK","").lower()=="true"
        and env.get("XRAY_TWELVE_PRIVATE_CACHE_RIGHTS_OK","").lower()=="true"
        and re.fullmatch("[a-f0-9]{64}",d) is not None)

def crypt(key):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.fernet import Fernet
    if len(key)<20:raise ValueError("KEY_NOT_SUITABLE_FOR_PRIVATE_CIPHER")
    raw=HKDF(algorithm=hashes.SHA256(),length=32,
             salt=b"xray-twelve-eod-private-v1",
             info=b"SHADOW_HISTORY_TRANSPORT_NOT_ALPHA").derive(key.encode())
    return Fernet(base64.urlsafe_b64encode(raw))

def fresh(s,rate_times=None,last_call=None):
    return {"schema":SCHEMA,"asof":s["asof"],"master_sha":s["master_sha"],
            "price_sha":s["price_sha"],"scope_hash":s["scope_hash"],
            "dates_hash":s["dates_hash"],"targets":s["targets"],
            "dates":s["dates"],"adjust_mode":"none","bars":{},"errors":{},
            "rate_times":list(rate_times or []),"last_call_ts":last_call,
            "requests_total":0,"source_authority":False,
            "execution":"NONE","real_money":"NO-GO"}

def _valid_rate_times(cp):
    times=cp.get("rate_times")
    if not isinstance(times,list) or len(times)>DAY_BUDGET:return False
    if any(type(x) not in (int,float) or not math.isfinite(x) or x<=0 for x in times):
        return False
    return times==sorted(times)

def exact(cp,s):
    if not isinstance(cp,dict) or not _valid_rate_times(cp):return False
    for k,v in (("schema",SCHEMA),("asof",s["asof"]),("master_sha",s["master_sha"]),
                ("price_sha",s["price_sha"]),("scope_hash",s["scope_hash"]),
                ("dates_hash",s["dates_hash"]),("targets",s["targets"]),
                ("dates",s["dates"]),("adjust_mode","none"),
                ("source_authority",False),("execution","NONE"),("real_money","NO-GO")):
        if cp.get(k)!=v:return False
    last=cp.get("last_call_ts")
    if last is not None and (type(last) not in (int,float) or not math.isfinite(last) or last<=0):
        return False
    if type(cp.get("requests_total")) is not int or cp["requests_total"]<0:return False
    bars=cp.get("bars")
    if not isinstance(bars,dict) or not set(bars).issubset(s["targets"]):return False
    failures=cp.get("errors",{})
    if not isinstance(failures,dict) or not set(failures).issubset(s["targets"]):return False
    if any(not isinstance(e,dict) or set(e)!={"count","reason"}
           or type(e["count"]) is not int
           or not 1<=e["count"]<=MAX_RETRIES_PER_SYMBOL
           or not isinstance(e["reason"],str)
           or not e["reason"].startswith("BLOCKED_")
           or len(e["reason"])>90 for e in failures.values()):return False
    if set(bars)&set(failures):return False
    if cp["requests_total"]<len(bars):return False
    required=set(s["dates"])
    for sym,rows in bars.items():
        if not isinstance(rows,list) or len(rows)>260:return False
        seen=set()
        for bar in rows:
            if not isinstance(bar,list) or len(bar)!=6:return False
            d=bar[0]
            if type(d) is not str or d not in required or d in seen:return False
            seen.add(d)
            if any(type(v) not in (float,int) or not math.isfinite(v) or v<=0 for v in bar[1:]):
                return False
            o,h,l,c,v=bar[1:]
            if h<max(o,c,l) or l>min(o,c):return False
        if [row[0] for row in rows]!=sorted(seen):return False
        # Old checkpoints or partially published EOD cannot claim one ticker
        # has already been fetched for the current market-data epoch.
        if s["asof"] not in seen:return False
    return True

def save(path,cp,s,c):
    if not exact(cp,s):raise ValueError("CHECKPOINT_INVALID_BEFORE_SEAL")
    p=Path(path)
    if p.resolve().is_relative_to(REPO.resolve()):raise ValueError("PUBLIC_CHECKPOINT_FORBIDDEN")
    data=json.dumps(cp,separators=(",",":"),sort_keys=True).encode()
    token=c.encrypt(data)
    if len(token)>MAX_CIPHERTEXT_BYTES:raise ValueError("PRIVATE_CIPHER_LIMIT")
    p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_name(p.name+".pending")
    t.write_bytes(token);t.chmod(0o600);os.replace(t,p)

def load(path,s,c):
    if not path or not Path(path).is_file():return fresh(s),False
    blob=Path(path).read_bytes()
    if not blob or len(blob)>MAX_CIPHERTEXT_BYTES:raise ValueError("CIPHER_MISSING_OR_OVERSIZED")
    try:cp=json.loads(c.decrypt(blob))
    except Exception as e:raise ValueError("CIPHER_NOT_AUTHENTIC") from e
    if not isinstance(cp,dict) or cp.get("schema")!=SCHEMA or not _valid_rate_times(cp):
        raise ValueError("CIPHER_STATE_SCHEMA_OR_RATE_INVALID")
    if (cp.get("asof"),cp.get("master_sha"),cp.get("price_sha"),
        cp.get("scope_hash"),cp.get("dates_hash")) != (
        s["asof"],s["master_sha"],s["price_sha"],s["scope_hash"],s["dates_hash"]):
        # NEVER reuse stale vendor prices or issuer identity. Preserve only an
        # authenticated rolling quota ledger, preventing epoch-change bursts.
        return fresh(s,cp["rate_times"],cp.get("last_call_ts")),False
    if not exact(cp,s):raise ValueError("CHECKPOINT_CONTENT_INVALID")
    cp.setdefault("errors",{})
    return cp,True

def parse_response(data,symbol,s):
    if not isinstance(data,dict) or data.get("status")!="ok":
        # Provider JSON HTTP-200 error code 404 denotes a missing ticker;
        # all other codes are a global issue until individually diagnosed.
        if isinstance(data,dict) and data.get("code")==404:
            raise ProviderDenied("VENDOR_SYMBOL_UNAVAILABLE")
        raise ProviderDenied("NO_VALID_VENDOR_EOD_RESPONSE")
    meta=data.get("meta") or {}
    if (not isinstance(meta,dict) or meta.get("symbol")!=symbol
        or meta.get("interval")!="1day" or meta.get("currency")!="USD"
        or meta.get("mic_code")!="XNAS"):
        raise ValueError("SYMBOL_CURRENCY_EXCHANGE_IDENTITY_UNPROVEN")
    series=data.get("values")
    if not isinstance(series,list) or not 1<=len(series)<=320:
        raise ValueError("SERIES_MISSING_OR_SIZE_INVALID")
    seen=set();ret={}
    valid=set(s["dates"])
    for row in series:
        if not isinstance(row,dict):raise ValueError("BAR_NOT_OBJECT")
        raw=row.get("datetime")
        if type(raw) is not str or len(raw)!=10:raise ValueError("INVALID_BAR_DATE")
        try: d=date.fromisoformat(raw)
        except ValueError as e:raise ValueError("INVALID_BAR_DATE") from e
        if d.isoformat()!=raw or raw>s["asof"] or raw in seen:
            raise ValueError("FUTURE_OR_DUPLICATE_OR_MALFORMED_DAY")
        seen.add(raw)
        vals=[]
        for k in ("open","high","low","close","volume"):
            z=row.get(k)
            if isinstance(z,bool):raise ValueError("BOOLEAN_VENDOR_FIELD")
            try:v=float(z)
            except (TypeError,ValueError) as e:raise ValueError("INVALID_VENDOR_NUMBER") from e
            if not math.isfinite(v) or v<=0:raise ValueError("NONPOSITIVE_OR_NONFINITE_BAR")
            vals.append(v)
        o,h,l,c,v=vals
        if h<max(o,l,c) or l>min(o,c):raise ValueError("INVALID_OHLC_RANGE")
        if raw in valid:ret[raw]=[raw,*vals]
    # A vendor returning 259 old bars on a fresh but not-yet-published ASOF
    # MUST NOT silently complete this symbol in the checkpoint. Retry safely.
    if s["asof"] not in ret:
        raise ProviderDenied("LATEST_COMPLETED_SESSION_NOT_YET_PUBLISHED")
    return [ret[k] for k in sorted(ret)]

def publication_state(s,ts):
    """Source-specific next-Nasdaq-trading-day EOD publication embargo.

    Twelve Data documents U.S. consolidated EOD availability only AFTER
    midnight ET on the next trading day. +15m is merely scheduling safety,
    NOT proof data exists. Never call a vendor against a stale PRICE ASOF.
    """
    if type(ts) not in (int,float) or not math.isfinite(ts) or ts<=0:
        raise ValueError("PROVIDER_CLOCK_INVALID")
    now_utc=datetime.fromtimestamp(ts,tz=timezone.utc)
    current=last_complete_session(now_utc)
    if current!=s["asof"]:
        return "BLOCKED_STALE_SCOPE_REQUIRES_CURRENT_ASOF"
    session=date.fromisoformat(s["asof"])
    next_days=mcal.get_calendar("NASDAQ").valid_days(
        start_date=(session+timedelta(days=1)).isoformat(),
        end_date=(session+timedelta(days=15)).isoformat())
    if len(next_days)<1:
        raise ValueError("NEXT_OFFICIAL_SESSION_NOT_FOUND")
    next_day=next_days[0].date()
    earliest=datetime.combine(next_day,dtime(0,15),
                              tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    if now_utc<earliest:
        return "BLOCKED_PROVIDER_EOD_PUBLICATION_WINDOW"
    return "PROVIDER_PUBLICATION_WINDOW_ELAPSED_NOT_DATA_PROOF"

def fetch(symbol,s,key):
    # Twelve /time_series explicitly supports adjust=none. The credential is
    # never a query parameter and never persisted in logs or artifacts.
    import urllib.parse
    params=urllib.parse.parse_qs(eod_query(s["asof"]))
    params["symbol"]=[symbol]
    query=urllib.parse.urlencode(params,doseq=True)
    request=urllib.request.Request("https://api.twelvedata.com/time_series?"+query,
                 headers={"Authorization":"apikey "+key,"Accept":"application/json"})
    with urllib.request.urlopen(request,timeout=25) as f:raw=f.read(MAX_RESPONSE_BYTES+1)
    if len(raw)>MAX_RESPONSE_BYTES:raise ValueError("VENDOR_RESPONSE_TOO_LARGE")
    return json.loads(raw)

def safe_error(e):
    if isinstance(e,urllib.error.HTTPError):
        if e.code==429:return "BLOCKED_RATE_LIMIT"
        if e.code in (401,402,403):return "BLOCKED_PROVIDER_AUTH_OR_ENTITLEMENT"
        return "BLOCKED_VENDOR_HTTP"
    if isinstance(e,(urllib.error.URLError,TimeoutError)):return "BLOCKED_VENDOR_TRANSPORT"
    if isinstance(e,ProviderDenied):
        if str(e)=="VENDOR_SYMBOL_UNAVAILABLE":
            return "BLOCKED_VENDOR_SYMBOL_UNAVAILABLE"
        if str(e)=="LATEST_COMPLETED_SESSION_NOT_YET_PUBLISHED":
            return "BLOCKED_VENDOR_EOD_LATEST_SESSION_ABSENT_RETRY_REQUIRED"
        return "BLOCKED_PROVIDER_RESPONSE_NOT_ENTITLED_OR_INVALID"
    return "BLOCKED_VENDOR_OHLCV_VALIDATION"

def health(cp,s,status,requests):
    n=len(cp["bars"])
    complete=sum(len(v)==260 for v in cp["bars"].values())
    return {"schema":REPORT,"status":status,"asof_et":s["asof"],
            "source_price_blob_sha":s["price_sha"],"source_master_blob_sha":s["master_sha"],
            "source_scope_hash":s["scope_hash"],"target_count":len(s["targets"]),
            "queried_symbols":n,"complete_260_symbols":complete,
            "remaining_symbols_to_query":len(s["targets"])-n,
            "individual_symbol_retry_or_quarantine_count":len(cp.get("errors") or {}),
            "individual_symbol_quarantined_after_3_count":sum(
                x["count"]>=MAX_RETRIES_PER_SYMBOL for x in (cp.get("errors") or {}).values()),
            "required_daily_sessions":260,"required_completed_weeks":52,
            "vendor_requests_this_run":requests,
            "rolling_24h_local_checkpoint_requests":len(cp["rate_times"]),
            "max_per_minute_spacing_seconds":MIN_SPACING_SECONDS,
            "plan_daily_credit_ceiling":DAY_BUDGET,
            "source_license_independently_verified":False,
            "consolidated_volume_independently_verified":False,
            "issuer_split_PIT_verified":False,
            "canonical_HISTORY_pass":False,"PRIMARY_MC_pass":False,"R92_AL":False,
            "raw_bars_public":False,"execution":"NONE","real_money":"NO-GO"}

def run(args,env=None,transport=fetch,now=time.time,sleep=time.sleep):
    s=scope()
    env=os.environ if env is None else env
    if not 1<=args.limit<=MAX_CALLS:raise ValueError("OUT_OF_FREE_RATE_SCOPE")
    if any(p and Path(p).resolve().is_relative_to(REPO.resolve())
           for p in (args.report,args.checkpoint,args.restore)):
        raise ValueError("PUBLIC_DATA_PATH_FORBIDDEN")
    report_path=Path(args.report)
    if not s["symbols"]:
        if s["targets"]:raise ValueError("ZERO_PRICE_PASS_BENCHMARK_ONLY_SCOPE")
        out=health(fresh(s),s,"BLOCKED_NO_CURRENT_PRICE_PASS_SCOPE",0)
        report_path.write_text(json.dumps(out,sort_keys=True)+"\n")
        print("XRAY_TWELVE_HISTORY=BLOCKED_NO_CURRENT_PRICE_PASS_SCOPE")
        print("XRAY_TWELVE_VENDOR_CALLS=0")
        return out
    if not authorized(env):
        out=health(fresh(s),s,"BLOCKED_KEY_OR_UNVERIFIED_NONDISPLAY_CACHE_RIGHTS",0)
        report_path.write_text(json.dumps(out,sort_keys=True)+"\n")
        return out
    timing=publication_state(s,now())
    if timing!="PROVIDER_PUBLICATION_WINDOW_ELAPSED_NOT_DATA_PROOF":
        out=health(fresh(s),s,timing,0)
        report_path.write_text(json.dumps(out,sort_keys=True)+"\n")
        print("XRAY_TWELVE_HISTORY="+timing)
        print("XRAY_TWELVE_VENDOR_CALLS=0")
        return out
    key=env["XRAY_TWELVE_DATA_API_KEY"]
    c=crypt(key)
    cp,_=load(args.restore,s,c)
    calls=0;status="PARTIAL_PRIVATE_TRANSPORT_ONLY"
    errors=cp.setdefault("errors",{})
    # New symbols have priority over retries: one broken ticker cannot starve
    # the other 514. Quarantine at three attempts without claiming PASS.
    new=[z for z in s["targets"] if z not in cp["bars"] and z not in errors]
    retries=[z for z in s["targets"] if z in errors
             and z not in cp["bars"]
             and errors[z]["count"]<MAX_RETRIES_PER_SYMBOL]
    for sym in (new+retries)[:args.limit]:
        current=now()
        if cp["last_call_ts"] is not None:
            elapsed=current-cp["last_call_ts"]
            if elapsed< -60:raise ValueError("SOURCE_REQUEST_CLOCK_REWIND")
            sleep(max(0.0,MIN_SPACING_SECONDS-elapsed))
        current=now()
        cp["rate_times"]=[x for x in cp["rate_times"] if current-x<WINDOW_SECONDS]
        if any(x>current+60 for x in cp["rate_times"]):
            raise ValueError("QUOTA_LEDGER_CLOCK_AHEAD")
        if len(cp["rate_times"])>=DAY_BUDGET:
            status="BLOCKED_ROLLING_24H_LOCAL_CREDIT_BUDGET"
            break
        cp["last_call_ts"]=current
        cp["rate_times"].append(current)
        cp["requests_total"]+=1
        save(args.checkpoint,cp,s,c)  # Reserve quota before ANY real request.
        calls+=1
        try:
            rows=parse_response(transport(sym,s,key),sym,s)
        except Exception as e:
            error_status=safe_error(e)
            # Authentication, plan limits, 429, network failure and unknown
            # provider JSON errors may affect EVERY symbol: stop immediately.
            if error_status in (
                "BLOCKED_RATE_LIMIT",
                "BLOCKED_PROVIDER_AUTH_OR_ENTITLEMENT",
                "BLOCKED_VENDOR_HTTP",
                "BLOCKED_VENDOR_TRANSPORT",
                "BLOCKED_PROVIDER_RESPONSE_NOT_ENTITLED_OR_INVALID"):
                status=error_status
                break
            old_count=(errors.get(sym) or {}).get("count",0)
            errors[sym]={"count":min(MAX_RETRIES_PER_SYMBOL,old_count+1),
                         "reason":error_status}
            save(args.checkpoint,cp,s,c)
            status="PARTIAL_PER_SYMBOL_RETRY_QUARANTINE_NO_ALPHA"
            continue
        errors.pop(sym,None)
        cp["bars"][sym]=rows
        save(args.checkpoint,cp,s,c)
    if not Path(args.checkpoint).exists():save(args.checkpoint,cp,s,c)
    if len(cp["bars"])==len(s["targets"]):
        status=("COMPLETE_260_PRIVATE_TRANSPORT_ONLY" if
                all(len(v)==260 for v in cp["bars"].values()) else
                "ALL_SYMBOLS_FETCHED_WITH_UNVERIFIED_IPO_OR_HISTORY_GAPS")
    elif errors and status=="PARTIAL_PRIVATE_TRANSPORT_ONLY":
        status="PARTIAL_PER_SYMBOL_RETRY_QUARANTINE_NO_ALPHA"
    out=health(cp,s,status,calls)
    report_path.write_text(json.dumps(out,sort_keys=True)+"\n")
    print("XRAY_TWELVE_HISTORY="+status)
    print("XRAY_TWELVE_HISTORY_QUERIED="+str(out["queried_symbols"])+"/"+str(len(s["targets"])))
    return out

def export_private(cp,s,directory):
    if not s["symbols"] or not s["targets"]:
        raise ValueError("EMPTY_PRICE_PASS_SCOPE_NOT_EXPORTABLE")
    if not exact(cp,s) or len(cp["bars"])!=len(s["targets"]):
        raise ValueError("NOT_ALL_SYMBOLS_FETCHED")
    dest=Path(directory).resolve()
    if dest.is_relative_to(REPO.resolve()):raise ValueError("PUBLIC_VENDOR_CSV_FORBIDDEN")
    dest.mkdir(parents=True,exist_ok=True,mode=0o700)
    for sym in s["targets"]:
        rows=cp["bars"].get(sym) or []
        if not rows:continue
        target=cache_path(dest,sym)
        with gzip.open(target,"wt",newline="",encoding="utf-8") as f:
            writer=csv.writer(f)
            writer.writerow(("date","open","high","low","close","volume"))
            writer.writerows(rows)
        target.chmod(0o600)
    return len(cp["bars"])

def selftest():
    from copy import deepcopy
    with TemporaryDirectory() as tmp:
        s=scope()
        # Zero current PRICE PASS is legitimate production NO-GO. Synthetic
        # nonempty test fixture is created ONLY in memory and never authority.
        assert len(s["dates"])==260 and len(s["weeks"])==52
        assert s["symbols"] or not s["targets"],"BUG_ZERO_PRICE_PASS_QQQ_ONLY_PHANTOM_SCOPE"
        if s["symbols"]:
            symbol=s["symbols"][0]
        else:
            assert s["targets"]==[]
            master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
            assert master["pass_symbols"]
            symbol=master["pass_symbols"][0]
        smaller=dict(s,symbols=[symbol],targets=sorted({symbol,"QQQ"}),
                     scope_hash=sha256_lines([symbol]))
        dt=smaller["dates"][-1]
        fixture={"status":"ok","meta":{"symbol":symbol,"interval":"1day",
                 "currency":"USD","mic_code":"XNAS"},
                 "values":[{"datetime":d,"open":"10","high":"11","low":"9",
                            "close":"10","volume":"100.25"} for d in smaller["dates"]]}
        good=parse_response(fixture,symbol,smaller)
        assert len(good)==260 and good[-1][0]==dt
        # A missing CURRENT ASOF close is not a legitimate completed request:
        # never record this symbol as fetched while vendor EOD is still late.
        missing_close=deepcopy(fixture)
        missing_close["values"]=[
            bar for bar in missing_close["values"] if bar["datetime"]!=dt]
        try:parse_response(missing_close,symbol,smaller)
        except ProviderDenied:pass
        else:raise AssertionError("MISSING_LATEST_EOD_SILENTLY_STORED")
        for kind in ("future","duplicate","bad_vol","wrong_mic","bad_high","nan","split_adjusted_not_claimed"):
            bad=deepcopy(fixture)
            if kind=="future":bad["values"][0]["datetime"]="2026-10-12"
            if kind=="duplicate":bad["values"].append(deepcopy(bad["values"][0]))
            if kind=="bad_vol":bad["values"][0]["volume"]="0"
            if kind=="wrong_mic":bad["meta"]["mic_code"]="XNYS"
            if kind=="bad_high":bad["values"][0]["high"]="5"
            if kind=="nan":bad["values"][0]["close"]="nan"
            if kind=="split_adjusted_not_claimed":bad["status"]="error"
            try:parse_response(bad,symbol,smaller)
            except (ValueError,ProviderDenied):continue
            raise AssertionError("INVALID_VENDOR_BAR_ACCEPTED_"+kind)
        assert not authorized({})
        # Provider's published timestamp: a Friday session is not necessarily
        # available on Saturday or Sunday; next trading day is Monday.
        friday=dict(smaller,asof="2026-10-09")
        def ts(year,month,day,hour,minute):
            return datetime(year,month,day,hour,minute,tzinfo=timezone.utc).timestamp()
        assert publication_state(friday,ts(2026,10,10,12,0))=="BLOCKED_PROVIDER_EOD_PUBLICATION_WINDOW"
        assert publication_state(friday,ts(2026,10,12,4,10))=="BLOCKED_PROVIDER_EOD_PUBLICATION_WINDOW"
        assert publication_state(friday,ts(2026,10,12,4,16))=="PROVIDER_PUBLICATION_WINDOW_ELAPSED_NOT_DATA_PROOF"
        assert publication_state(friday,ts(2026,10,12,21,0))=="BLOCKED_STALE_SCOPE_REQUIRES_CURRENT_ASOF"
        assert publication_state(smaller,ts(2026,10,9,5,15))=="PROVIDER_PUBLICATION_WINDOW_ELAPSED_NOT_DATA_PROOF"
        cp=fresh(smaller)
        cp["bars"][symbol]=good
        cp["requests_total"]=1
        assert exact(cp,smaller)
        c=crypt("OFFLINE-TEST-ONLY-"+"A"*32)
        secret=Path(tmp)/"private.enc"
        save(secret,cp,smaller,c)
        restored,reused=load(secret,smaller,c)
        assert reused and restored["bars"][symbol]==good
        drift=dict(smaller,price_sha="0"*40)
        new,exact_epoch=load(secret,drift,c)
        assert not exact_epoch and new["bars"]=={}
        assert not health(cp,smaller,"TEST_ONLY",0)["canonical_HISTORY_pass"]
        tamper=secret.read_bytes()
        secret.write_bytes(tamper[:-1]+b"Z")
        try:load(secret,smaller,c)
        except ValueError:pass
        else:raise AssertionError("CIPHERTEXT_TAMPER_ACCEPTED")
        cp["bars"][symbol][0][4]=-1
        assert not exact(cp,smaller)
        for bad_env in ({"XRAY_TWELVE_DATA_API_KEY":"a"*32},
          {"XRAY_TWELVE_DATA_API_KEY":"a"*32,
           "XRAY_TWELVE_NONDISPLAY_LICENSE_OK":"true",
           "XRAY_TWELVE_PRIVATE_CACHE_RIGHTS_OK":"true",
           "XRAY_TWELVE_LICENSE_EVIDENCE_SHA256":"INVALID"}):
            assert not authorized(bad_env)
        assert not health(fresh(smaller),smaller,"BLOCKED",0)["R92_AL"]
        # Exercise the ACTUAL run orchestration with only synthetic in-memory
        # EOD bars. It must resume its ciphertext, respect rolling quota and
        # never try a provider call when license/key authorization is absent.
        from types import SimpleNamespace
        from unittest.mock import patch
        stub_calls=[]
        fake_env={"XRAY_TWELVE_DATA_API_KEY":"OFFLINE-TEST-ONLY-"+"A"*32,
                  "XRAY_TWELVE_NONDISPLAY_LICENSE_OK":"true",
                  "XRAY_TWELVE_PRIVATE_CACHE_RIGHTS_OK":"true",
                  "XRAY_TWELVE_LICENSE_EVIDENCE_SHA256":"a"*64}
        def vendor_fake(sym,scope_arg,key):
            assert scope_arg["asof"]==smaller["asof"]
            assert key==fake_env["XRAY_TWELVE_DATA_API_KEY"]
            stub_calls.append(sym)
            response=deepcopy(fixture)
            response["meta"]["symbol"]=sym
            return response
        with patch(__name__+".scope",lambda:smaller):
            a1=SimpleNamespace(report=Path(tmp)/"first.json",
                               checkpoint=Path(tmp)/"first.enc",
                               restore=Path(tmp)/"no-prior.enc",limit=1)
            deny=run(a1,env={},transport=lambda *a: (_ for _ in ()).throw(
                AssertionError("UNLICENSED_NETWORK_CALLED")))
            assert deny["status"]=="BLOCKED_KEY_OR_UNVERIFIED_NONDISPLAY_CACHE_RIGHTS"
            assert deny["vendor_requests_this_run"]==0 and not stub_calls
            # Test rights-granted Friday ASOF against Saturday timestamp:
            # latest session drift AND next-trading-day publication embargo.
            stale_clock=ts(2026,10,10,12,0)
            stale=run(a1,env=fake_env,transport=vendor_fake,
                      now=lambda:stale_clock,sleep=lambda _:None)
            assert stale["vendor_requests_this_run"]==0, "STALE_ASOF_VENDOR_CALL_ACCEPTED"
            assert stale["status"]=="BLOCKED_STALE_SCOPE_REQUIRES_CURRENT_ASOF"
            # This fixture is after 2026-10-08 EOD publication (Friday
            # 2026-10-09 00:15 ET) but BEFORE 2026-10-09 market close.
            valid_epoch=datetime(2026,10,9,5,15,tzinfo=timezone.utc).timestamp()
            one=run(a1,env=fake_env,transport=vendor_fake,
                    now=lambda:valid_epoch,sleep=lambda _:None)
            assert one["vendor_requests_this_run"]==1 and one["queried_symbols"]==1
            a2=SimpleNamespace(report=Path(tmp)/"second.json",
                               checkpoint=Path(tmp)/"second.enc",
                               restore=a1.checkpoint,limit=1)
            two=run(a2,env=fake_env,transport=vendor_fake,
                    now=lambda:valid_epoch+9.0,sleep=lambda _:None)
            assert two["queried_symbols"]==len(smaller["targets"])
            assert two["complete_260_symbols"]==len(smaller["targets"])
            assert two["status"]=="COMPLETE_260_PRIVATE_TRANSPORT_ONLY"
            assert len(stub_calls)==2
            cp2,reused=load(a2.checkpoint,smaller,crypt(fake_env["XRAY_TWELVE_DATA_API_KEY"]))
            assert reused and export_private(cp2,smaller,Path(tmp)/"private")==2
            assert len(list((Path(tmp)/"private").glob("*.csv.gz")))==2
            # An authenticated ASOF/PRICE revision discards all bars BUT MUST
            # carry signed 24h request accounting into the next cohort.
            changed=dict(smaller,price_sha="2"*40)
            carried,matched=load(a2.checkpoint,changed,crypt(fake_env["XRAY_TWELVE_DATA_API_KEY"]))
            assert not matched and not carried["bars"]
            assert len(carried["rate_times"])==2
            limited=fresh(smaller,rate_times=[
                valid_epoch-10.0+i*0.01 for i in range(DAY_BUDGET)],last_call=valid_epoch-2.01)
            assert exact(limited,smaller)
            capped=Path(tmp)/"capped.enc"
            save(capped,limited,smaller,crypt(fake_env["XRAY_TWELVE_DATA_API_KEY"]))
            a3=SimpleNamespace(report=Path(tmp)/"capped.json",
                               checkpoint=Path(tmp)/"after_cap.enc",
                               restore=capped,limit=1)
            n_calls=len(stub_calls)
            blocked=run(a3,env=fake_env,transport=vendor_fake,
                        now=lambda:valid_epoch,sleep=lambda _:None)
            assert blocked["status"]=="BLOCKED_ROLLING_24H_LOCAL_CREDIT_BUDGET"
            assert blocked["vendor_requests_this_run"]==0
            assert len(stub_calls)==n_calls
            # Provider may have ONE invalid ticker. All other licensed
            # symbols must be probed within rate budget; never let the first
            # bad ticker permanently starve the entire Nasdaq cohort.
            blocked_symbol=smaller["targets"][0]
            success_symbol=smaller["targets"][1]
            visited=[]
            def one_bad_one_good(sym,sp,key):
                visited.append(sym)
                if sym==blocked_symbol:
                    raise ValueError("TEST_SINGLE_ISSUER_VENDOR_BAR_INVALID")
                response=deepcopy(fixture)
                response["meta"]["symbol"]=sym
                return response
            a4=SimpleNamespace(report=Path(tmp)/"one_bad.json",
                               checkpoint=Path(tmp)/"one_bad.enc",
                               restore=Path(tmp)/"no-fault-prior.enc",limit=2)
            mixed=run(a4,env=fake_env,transport=one_bad_one_good,
                      now=lambda:valid_epoch,sleep=lambda _:None)
            assert mixed["vendor_requests_this_run"]==2,"ONE_BAD_SYMBOL_STARVED_ALL_OTHER_NAMES"
            assert mixed["queried_symbols"]==1,"OTHER_SYMBOL_NOT_PERSISTED"
            assert visited==smaller["targets"]
            assert mixed["canonical_HISTORY_pass"] is False
            assert mixed["individual_symbol_retry_or_quarantine_count"]==1
            # Retry the bad symbol only AFTER all new names were inspected,
            # without refetching or overwriting the other completed symbol.
            a5=SimpleNamespace(report=Path(tmp)/"fixed.json",
                               checkpoint=Path(tmp)/"fixed.enc",
                               restore=a4.checkpoint,limit=2)
            recovery=run(a5,env=fake_env,transport=vendor_fake,
                         now=lambda:valid_epoch+9,sleep=lambda _:None)
            assert recovery["vendor_requests_this_run"]==1
            assert recovery["queried_symbols"]==len(smaller["targets"])
            assert recovery["individual_symbol_retry_or_quarantine_count"]==0
            assert recovery["complete_260_symbols"]==len(smaller["targets"])
            # Independent quarantine path: after exactly three invalid bars,
            # retain the failed ticker as UNKNOWN and stop spending free
            # credits on it; never silently turn failure into HISTORY PASS.
            prior=a4.checkpoint
            for attempt in (2,3):
                next_path=Path(tmp)/("quarantine_"+str(attempt)+".enc")
                next_report=Path(tmp)/("quarantine_"+str(attempt)+".json")
                args_q=SimpleNamespace(report=next_report,checkpoint=next_path,
                                       restore=prior,limit=2)
                bad_response=run(args_q,env=fake_env,transport=one_bad_one_good,
                                 now=lambda attempt=attempt:valid_epoch+9*attempt,
                                 sleep=lambda _:None)
                assert bad_response["vendor_requests_this_run"]==1
                assert bad_response["individual_symbol_retry_or_quarantine_count"]==1
                assert bad_response["canonical_HISTORY_pass"] is False
                if attempt==3:
                    assert bad_response["individual_symbol_quarantined_after_3_count"]==1
                prior=next_path
            args_last=SimpleNamespace(report=Path(tmp)/"q_final.json",
                                      checkpoint=Path(tmp)/"q_final.enc",
                                      restore=prior,limit=2)
            no_more=run(args_last,env=fake_env,transport=one_bad_one_good,
                        now=lambda:valid_epoch+40,sleep=lambda _:None)
            assert no_more["vendor_requests_this_run"]==0
            assert no_more["individual_symbol_quarantined_after_3_count"]==1
            assert no_more["complete_260_symbols"]==1
            assert no_more["R92_AL"] is False
    print("XRAY_TWELVE_260_RESUME_SELFTEST=PASS_ET_PUBLICATION_NONSTARVATION_RECOVERY_THREE_STRIKE_QUARANTINE_QUOTA_ENCRYPTION_NO_ALPHA")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--report",type=Path)
    p.add_argument("--checkpoint",type=Path)
    p.add_argument("--restore",type=Path)
    p.add_argument("--limit",type=int,default=32)
    p.add_argument("--check-restore",type=Path)
    p.add_argument("--export-checkpoint",type=Path)
    p.add_argument("--export-dir",type=Path)
    args=p.parse_args()
    if args.selftest:selftest();return
    if args.check_restore:
        if not authorized(os.environ):raise SystemExit(3)
        s=scope()
        try:load(args.check_restore,s,crypt(os.environ["XRAY_TWELVE_DATA_API_KEY"]))
        except Exception:raise SystemExit(3)
        raise SystemExit(0)
    if args.export_checkpoint:
        if not authorized(os.environ) or not args.export_dir:
            raise ValueError("EXPORT_RIGHTS_OR_DIRECTORY_MISSING")
        s=scope()
        cp,same=load(args.export_checkpoint,s,crypt(os.environ["XRAY_TWELVE_DATA_API_KEY"]))
        if not same:raise ValueError("NO_EXACT_ASOF_EXPORT")
        n=export_private(cp,s,args.export_dir)
        print("XRAY_TWELVE_EPHEMERAL_PRIVATE_CSV="+str(n))
        return
    if not args.report or not args.checkpoint:
        p.error("--report and --checkpoint runner-private paths required")
    run(args)

if __name__=="__main__":
    main()
