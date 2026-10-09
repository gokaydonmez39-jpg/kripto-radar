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
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from current_history_source_request import sha256_lines
from history_transport_cache_guard import cache_path
from massive_grouped_history_resume import scope
from twelve_data_history_probe import eod_query

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
SCHEMA="XRAY_TWELVE_260_HISTORY_ENCRYPTED_SHADOW_V1"
REPORT="XRAY_TWELVE_260_HISTORY_HEALTH_V1"
MAX_CALLS=32
MIN_SPACING_SECONDS=9.0
DAY_BUDGET=800
WINDOW_SECONDS=86400.0
MAX_RESPONSE_BYTES=350000
MAX_CIPHERTEXT_BYTES=90000000

class ProviderDenied(Exception):
    pass

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
            "dates":s["dates"],"adjust_mode":"none","bars":{},
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
    return cp,True

def parse_response(data,symbol,s):
    if not isinstance(data,dict) or data.get("status")!="ok":
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
    return [ret[k] for k in sorted(ret)]

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
    if isinstance(e,ProviderDenied):return "BLOCKED_PROVIDER_RESPONSE_NOT_ENTITLED_OR_INVALID"
    return "BLOCKED_VENDOR_OHLCV_VALIDATION"

def health(cp,s,status,requests):
    n=len(cp["bars"])
    complete=sum(len(v)==260 for v in cp["bars"].values())
    return {"schema":REPORT,"status":status,"asof_et":s["asof"],
            "source_price_blob_sha":s["price_sha"],"source_master_blob_sha":s["master_sha"],
            "source_scope_hash":s["scope_hash"],"target_count":len(s["targets"]),
            "queried_symbols":n,"complete_260_symbols":complete,
            "remaining_symbols_to_query":len(s["targets"])-n,
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
    if not authorized(env):
        out=health(fresh(s),s,"BLOCKED_KEY_OR_UNVERIFIED_NONDISPLAY_CACHE_RIGHTS",0)
        report_path.write_text(json.dumps(out,sort_keys=True)+"\n")
        return out
    key=env["XRAY_TWELVE_DATA_API_KEY"]
    c=crypt(key)
    cp,_=load(args.restore,s,c)
    calls=0;status="PARTIAL_PRIVATE_TRANSPORT_ONLY"
    for sym in [z for z in s["targets"] if z not in cp["bars"]][:args.limit]:
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
            status=safe_error(e)
            break
        cp["bars"][sym]=rows
        save(args.checkpoint,cp,s,c)
    if not Path(args.checkpoint).exists():save(args.checkpoint,cp,s,c)
    if len(cp["bars"])==len(s["targets"]):
        status=("COMPLETE_260_PRIVATE_TRANSPORT_ONLY" if
                all(len(v)==260 for v in cp["bars"].values()) else
                "ALL_SYMBOLS_FETCHED_WITH_UNVERIFIED_IPO_OR_HISTORY_GAPS")
    out=health(cp,s,status,calls)
    report_path.write_text(json.dumps(out,sort_keys=True)+"\n")
    print("XRAY_TWELVE_HISTORY="+status)
    print("XRAY_TWELVE_HISTORY_QUERIED="+str(out["queried_symbols"])+"/"+str(len(s["targets"])))
    return out

def export_private(cp,s,directory):
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
        assert s["symbols"] and len(s["dates"])==260 and len(s["weeks"])==52
        symbol=s["symbols"][0]
        smaller=dict(s,symbols=[symbol],targets=sorted({symbol,"QQQ"}),
                     scope_hash=sha256_lines([symbol]))
        dt=smaller["dates"][-1]
        fixture={"status":"ok","meta":{"symbol":symbol,"interval":"1day",
                 "currency":"USD","mic_code":"XNAS"},
                 "values":[{"datetime":d,"open":"10","high":"11","low":"9",
                            "close":"10","volume":"100.25"} for d in smaller["dates"]]}
        good=parse_response(fixture,symbol,smaller)
        assert len(good)==260 and good[-1][0]==dt
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
    print("XRAY_TWELVE_260_RESUME_SELFTEST=PASS_OFFLINE_VENDOR_NEGATIVES_ENCRYPTION_TAMPER_QUOTA_SCOPE_NO_ALPHA")

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
