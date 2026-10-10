#!/usr/bin/env python3
"""Fail-closed, encrypted/resumable 260-session Massive grouped-EOD transport.

One provider request PER SESSION, not per ticker. Zero trading/AL/MC/HISTORY
authority. Real vendor rows stored ONLY in authenticated ciphertext within
runner-temporary memory/artifact, contingent on operator's verified usage rights.
Historical PRICE ASOF, blob and scope are exact-pinned; older epochs never mix.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import math
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from datetime import date,datetime,timezone
from pathlib import Path
from current_history_source_request import expected_dates,sha256_lines

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
SCHEMA="XRAY_MASSIVE_GROUPED_HISTORY_RESUME_SHADOW_V1"
REPORT="XRAY_MASSIVE_GROUPED_HISTORY_HEALTH_V1"
MIN_SPACING=13.0
MAX_CALLS_PER_JOB=10
MAX_BODY_BYTES=6_000_000
MAX_CIPHER_BYTES=70_000_000

def gitblob(path):
    return subprocess.check_output(["git","hash-object",str(path)],cwd=REPO,text=True).strip()

def master_price_lineage_exact(price,master):
    """Exact canonical per-ASOF MASTER queue provenance, not mere subset."""
    return (isinstance(price,dict) and isinstance(master,dict)
            and price.get("asof_et")==master.get("asof_et")
            and master.get("unknown_never_pass") is True
            and price.get("source_master_queue_hash")==master.get("queue_hash")
            and master.get("queue_hash")==master.get("pass_hash")
            and price.get("source_master_count")==master.get("pass_count")
            and master.get("pass_count")==len(master.get("pass_symbols") or [])
            and master.get("pass_symbols")==sorted(set(master.get("pass_symbols") or []))
            and master.get("queue_total")==master.get("queue_unique")
            and master.get("queue_total")==master.get("pass_count")
            and master.get("execution")=="NONE" and master.get("real_money")=="NO-GO")

def scope():
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    symbols=price.get("pass_symbols")
    asof=price.get("asof_et")
    if (price.get("execution")!="NONE" or price.get("real_money")!="NO-GO"
        or price.get("unknown_never_pass") is not True
        or master.get("asof_et")!=asof or master.get("execution")!="NONE"
        or master.get("real_money")!="NO-GO"
        or not master_price_lineage_exact(price,master)
        or not isinstance(symbols,list) or symbols!=sorted(set(symbols))
        or len(symbols)!=price.get("pass_count")
        or sha256_lines(symbols)!=price.get("pass_hash")
        or not set(symbols).issubset(set(master.get("pass_symbols") or []))):
        raise ValueError("PRICE_MASTER_SCOPE_NOT_EXACT")
    sessions,weeks=expected_dates(asof)
    if len(sessions)!=260 or len(weeks)!=52 or sessions[-1]!=asof:
        raise ValueError("NASDAQ_OFFICIAL_CALENDAR_NOT_EXACT")
    return {"asof":asof,"symbols":symbols,"targets":sorted(set(symbols)|{"QQQ"}),
            "dates":sessions,"weeks":weeks,
            "price_sha":gitblob(ROOT/"canonical_current_price_dv30.json"),
            "master_sha":gitblob(ROOT/"canonical_current_master_manifest.json"),
            "scope_hash":sha256_lines(symbols),
            "dates_hash":sha256_lines(sessions)}

def allowed(env):
    digest=env.get("XRAY_MASSIVE_LICENSE_EVIDENCE_SHA256","")
    return bool(env.get("XRAY_MASSIVE_API_KEY","")) and (
        env.get("XRAY_MASSIVE_NONDISPLAY_LICENSE_OK","").lower()=="true"
        and env.get("XRAY_MASSIVE_PRIVATE_CACHE_RIGHTS_OK","").lower()=="true"
        and re.fullmatch("[a-f0-9]{64}",digest) is not None)

def cipher(key):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.fernet import Fernet
    if len(key)<20:raise ValueError("API_KEY_INSUFFICIENT_FOR_ENCRYPTION")
    secret=HKDF(algorithm=hashes.SHA256(),length=32,
      salt=b"xray-c417-massive-grouped-eod-private-v1",
      info=b"ENCRYPTED_RESEARCH_TRANSPORT_NOT_ALPHA").derive(key.encode())
    return Fernet(base64.urlsafe_b64encode(secret))

def fresh(s):
    return {"schema":SCHEMA,"asof":s["asof"],"price_sha":s["price_sha"],
            "master_sha":s["master_sha"],"scope_hash":s["scope_hash"],
            "dates_hash":s["dates_hash"],"scope_symbols":s["symbols"],
            "required_dates":s["dates"],"bars_adjusted":False,"dates":{},
            "request_count":0,"last_request_ts":None,
            "execution":"NONE","real_money":"NO-GO","alpha_authority":False}

def exact(cp,s):
    if not isinstance(cp,dict):return False
    for key,wanted in (("schema",SCHEMA),("asof",s["asof"]),
        ("price_sha",s["price_sha"]),("master_sha",s["master_sha"]),
        ("scope_hash",s["scope_hash"]),("dates_hash",s["dates_hash"]),
        ("execution","NONE"),("real_money","NO-GO"),("alpha_authority",False)):
        if cp.get(key)!=wanted:return False
    if (cp.get("scope_symbols")!=s["symbols"]
        or cp.get("required_dates")!=s["dates"]
        or cp.get("bars_adjusted") is not False):return False
    dates=cp.get("dates")
    if not isinstance(dates,dict) or not set(dates).issubset(s["dates"]):return False
    if type(cp.get("request_count")) is not int or cp["request_count"]<len(dates):return False
    t=cp.get("last_request_ts")
    if t is not None and (type(t) not in (int,float) or not math.isfinite(t) or t<=0):return False
    targets=set(s["targets"])
    for d,rows in dates.items():
        if not isinstance(rows,dict) or "QQQ" not in rows or not set(rows).issubset(targets):return False
        for symbol,bar in rows.items():
            if not isinstance(bar,list) or len(bar)!=5:return False
            try: o,h,l,c,v=map(float,bar)
            except (ValueError,TypeError):return False
            if not (all(math.isfinite(x) and x>0 for x in (o,h,l,c,v))
                    and h>=max(o,c,l) and l<=min(o,c)):return False
    return True

def rebound(old,s):
    """Preserve authenticated UNADJUSTED prior-session bars across ASOF roll.

    Future stock splits do not retroactively adjust as-traded bars. Any source
    corrections, ticker changes and exact class continuity remain independently
    UNVERIFIED and never authorize alpha. New target names may remain missing.
    """
    if (old.get("schema")!=SCHEMA or old.get("bars_adjusted") is not False
        or not isinstance(old.get("scope_symbols"),list)
        or old["scope_symbols"]!=sorted(set(old["scope_symbols"]))
        or old.get("scope_hash")!=sha256_lines(old["scope_symbols"])
        or not isinstance(old.get("asof"),str)
        or old["asof"]>=s["asof"]):
        raise ValueError("OLD_EPOCH_REBIND_NOT_ALLOWED")
    prevdays,prevweeks=expected_dates(old["asof"])
    prev=dict(s,asof=old["asof"],symbols=old["scope_symbols"],
        targets=sorted(set(old["scope_symbols"])|{"QQQ"}),
        dates=prevdays,weeks=prevweeks,dates_hash=sha256_lines(prevdays),
        scope_hash=old["scope_hash"],price_sha=old.get("price_sha"),
        master_sha=old.get("master_sha"))
    if not exact(old,prev):
        raise ValueError("OLD_EPOCH_AUTHENTIC_BUT_NOT_CONSISTENT")
    current=fresh(s)
    allowed_targets=set(s["targets"])
    for d,rows in old["dates"].items():
        if d not in s["dates"]:continue
        eligible={symbol:bar for symbol,bar in rows.items() if symbol in allowed_targets}
        if "QQQ" in eligible:current["dates"][d]=eligible
    current["request_count"]=max(old["request_count"],len(current["dates"]))
    current["last_request_ts"]=old["last_request_ts"]
    assert exact(current,s),"REBIND_POSTCONDITIONS_NOT_EXACT"
    return current

def load(path,crypto,s):
    if not path or not Path(path).is_file():return fresh(s),False
    token=Path(path).read_bytes()
    if not token or len(token)>MAX_CIPHER_BYTES:raise ValueError("CIPHERTEXT_MISSING_OR_OVERSIZED")
    try:cp=json.loads(crypto.decrypt(token))
    except Exception as e:raise ValueError("CIPHERTEXT_NOT_AUTHENTIC") from e
    if not isinstance(cp,dict) or cp.get("schema")!=SCHEMA:raise ValueError("CHECKPOINT_SCHEMA_INVALID")
    if any(cp.get(k)!=s[k] for k in ("asof","price_sha","master_sha","scope_hash","dates_hash")):
        # Authentic same-date PRICE revisions are STALE, not corrupt.
        # Never merge two same-ASOF identities or price-blobs.
        if cp.get("asof")==s["asof"] or cp.get("asof")>s["asof"]:
            return fresh(s),False
        return rebound(cp,s),True
    if not exact(cp,s):raise ValueError("CHECKPOINT_NOT_EXACT")
    return cp,True

def save(cp,crypto,s,path):
    if not exact(cp,s):raise ValueError("CHECKPOINT_TAMPERED")
    dest=Path(path);dest.parent.mkdir(parents=True,exist_ok=True)
    encoded=crypto.encrypt(json.dumps(cp,sort_keys=True,separators=(",",":")).encode())
    if len(encoded)>MAX_CIPHER_BYTES:raise ValueError("CHECKPOINT_CAP")
    tmp=dest.with_name(dest.name+".pending")
    tmp.write_bytes(encoded);tmp.chmod(0o600);os.replace(tmp,dest)

class VendorNotEntitled(ValueError):
    """Provider explicitly did not grant this session's data on the plan."""

def decode_provider_body(raw):
    """Recognize account-level denial without persisting or logging vendor text."""
    if isinstance(raw,bytes) and b"NOT_ENTITLED" in raw[:1024].upper():
        raise VendorNotEntitled("PROVIDER_PLAN_NOT_ENTITLED")
    parsed=json.loads(raw)
    if isinstance(parsed,dict):
        status=str(parsed.get("status") or "")
        error_text=str(parsed.get("error") or "")[:300]
        if "NOT_ENTITLED" in (status+" "+error_text).upper():
            raise VendorNotEntitled("PROVIDER_PLAN_NOT_ENTITLED")
    return parsed

def read_day(payload,day,targets):
    if isinstance(payload,dict) and "NOT_ENTITLED" in (
        str(payload.get("status") or "")+" "+str(payload.get("error") or "")[:300]).upper():
        raise VendorNotEntitled("PROVIDER_PLAN_NOT_ENTITLED")
    if not isinstance(payload,dict) or payload.get("status")!="OK" or payload.get("adjusted") is not False:
        raise ValueError("VENDOR_RESPONSE_NOT_UNADJUSTED")
    rows=payload.get("results")
    if not isinstance(rows,list) or not rows or len(rows)>30000:raise ValueError("UNBOUNDED_VENDOR_ROWS")
    if type(payload.get("resultsCount")) is not int or payload["resultsCount"]!=len(rows):
        raise ValueError("GROUPED_RESULTS_COUNT_MISMATCH")
    wanted=set(targets);got={}
    for r in rows:
        if not isinstance(r,dict):raise ValueError("VENDOR_ROW_NOT_OBJECT")
        symbol=r.get("T")
        if symbol not in wanted:continue
        if symbol in got:raise ValueError("DUPLICATED_SCOPE_TICKER")
        ts=r.get("t")
        if type(ts) is not int or datetime.fromtimestamp(ts/1000,timezone.utc).date().isoformat()!=day:
            raise ValueError("WRONG_EPOCH_TIMESTAMP")
        values=[]
        for k in ("o","h","l","c","v"):
            raw=r.get(k)
            if isinstance(raw,bool):raise ValueError("BAD_BAR_BOOLEAN")
            x=float(raw)
            if not math.isfinite(x) or x<=0:raise ValueError("BAD_BAR_VALUE")
            values.append(x)
        o,h,l,c,v=values
        if h<max(o,l,c) or l>min(o,c):raise ValueError("BAD_BAR_RANGE")
        got[symbol]=values
    if "QQQ" not in got:raise ValueError("BENCHMARK_MISSING")
    return got

def fetch(day,key):
    endpoint="https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/"+day
    request=urllib.request.Request(endpoint+"?adjusted=false&include_otc=false",
               headers={"Authorization":"Bearer "+key,"Accept":"application/json"})
    with urllib.request.urlopen(request,timeout=24) as f:
        raw=f.read(MAX_BODY_BYTES+1)
    if len(raw)>MAX_BODY_BYTES:raise ValueError("VENDOR_RESPONSE_TOO_LARGE")
    return decode_provider_body(raw)

def telemetry(cp,s,status,request_count):
    n=len(cp["dates"])
    complete=n==len(s["dates"])
    targets=s["targets"]
    good={symbol:sum(symbol in day for day in cp["dates"].values()) for symbol in targets} if complete else {}
    full=complete and all(v==260 for v in good.values())
    return {"schema":REPORT,"status":status,"asof_et":s["asof"],
            "source_price_blob_sha":s["price_sha"],"source_scope_hash":s["scope_hash"],
            "required_days":260,"collected_days":n,"remaining_days":260-n,
            "max_sample_symbols":len(targets),"full_260_symbol_date_transport":full,
            "missing_symbol_day_count":sum(260-v for v in good.values()) if complete else None,
            "requests_this_run":request_count,"source_license_independently_verified":False,
            "split_chain_independently_verified":False,
            "primary_MC_pass":False,"canonical_HISTORY_pass":False,"R92_AL":False,
            "raw_bars_public":False,"execution":"NONE","real_money":"NO-GO"}

def safe_vendor_block_reason(error):
    # Return ONLY stable codes; vendor exception text may contain credentials.
    if isinstance(error,VendorNotEntitled):
        return "BLOCKED_PROVIDER_PLAN_NOT_ENTITLED"
    if isinstance(error,urllib.error.HTTPError):
        if error.code==429:return "BLOCKED_HTTP_429_FREE_TIER_RATE_LIMIT"
        if error.code in (401,402,403):return "BLOCKED_HTTP_VENDOR_AUTH_OR_PLAN"
        return "BLOCKED_HTTP_OTHER"
    if isinstance(error,(urllib.error.URLError,TimeoutError)):
        return "BLOCKED_VENDOR_TRANSPORT"
    return "BLOCKED_GROUPED_RESPONSE_OR_SCOPE_DATE_PROOF"

def run(args,request=fetch,sleeper=time.sleep,now=time.time):
    s=scope()
    out=Path(args.report)
    if out.resolve().is_relative_to(REPO.resolve()):raise ValueError("REPORT_INSIDE_PUBLIC_REPO")
    if not 1<=args.limit<=MAX_CALLS_PER_JOB:raise ValueError("LIMIT_OUTSIDE_FREE_QUOTA")
    if not allowed(os.environ):
        report=telemetry(fresh(s),s,"BLOCKED_AUTH_OR_NONDISPLAY_AND_PRIVATE_CACHE_RIGHTS",0)
        out.write_text(json.dumps(report,sort_keys=True)+"\n");return report
    crypto=cipher(os.environ["XRAY_MASSIVE_API_KEY"])
    cp,restored=load(args.restore,crypto,s)
    requests=0;status="PARTIAL_SHADOW_ONLY"
    for day in [d for d in s["dates"] if d not in cp["dates"]][:args.limit]:
        last=cp["last_request_ts"]
        if last is not None:
            elapsed=now()-last
            if elapsed< -1:raise ValueError("REQUEST_CLOCK_REWIND")
            sleeper(max(0,MIN_SPACING-elapsed))
        cp["last_request_ts"]=now()
        cp["request_count"]+=1
        save(cp,crypto,s,args.checkpoint)
        requests+=1  # Include failed HTTP requests in the free-tier attempt budget.
        try:
            payload=request(day,os.environ["XRAY_MASSIVE_API_KEY"])
            scoped=read_day(payload,day,s["targets"])
        except Exception as error:
            status=safe_vendor_block_reason(error)
            break
        cp["dates"][day]=scoped
        save(cp,crypto,s,args.checkpoint)
    if not Path(args.checkpoint).is_file():save(cp,crypto,s,args.checkpoint)
    if len(cp["dates"])==260:
        status=("COMPLETE_PRIVATE_TRANSPORT_ONLY" if
                telemetry(cp,s,status,requests)["full_260_symbol_date_transport"]
                else "ALL_SESSIONS_FETCHED_BUT_SYMBOL_HISTORY_GAPS")
    result=telemetry(cp,s,status,requests)
    out.write_text(json.dumps(result,sort_keys=True)+"\n")
    print("XRAY_GROUPED_HISTORY="+status)
    print("XRAY_GROUPED_HISTORY_PROGRESS="+str(result["collected_days"])+"/260")
    return result

def export_completed_private_csv(cp,s,directory):
    """One-run-only unadjusted transport; NEVER upload or promote bars.

    Existing qualified_history_ingress_shadow independently checks the exact
    completed session and 52 week dates in these private files. Missing a
    ticker-day produces a short cache, never a synthetic filled session.
    """
    import csv
    import gzip
    from history_transport_cache_guard import cache_path
    dest=Path(directory).resolve()
    if dest.is_relative_to(REPO.resolve()):raise ValueError("PRIVATE_VENDOR_EXPORT_INSIDE_PUBLIC_REPO")
    if not exact(cp,s) or len(cp["dates"])!=260:
        raise ValueError("PRIVATE_VENDOR_HISTORY_NOT_ALL_DAYS_FETCHED")
    dest.mkdir(parents=True,exist_ok=True,mode=0o700)
    outcount=0
    for symbol in s["targets"]:
        lines=[(d,cp["dates"][d][symbol]) for d in s["dates"] if symbol in cp["dates"][d]]
        if not lines:continue
        target=cache_path(dest,symbol)
        with gzip.open(target,"wt",encoding="utf-8",newline="") as fh:
            writer=csv.writer(fh)
            writer.writerow(("date","open","high","low","close","volume"))
            for d,bar in lines:writer.writerow([d,*bar])
        target.chmod(0o600)
        outcount+=1
    return {"symbol_csv_private":outcount,
            "expected_symbols_plus_benchmark":len(s["targets"]),
            "all_session_dates_retained":len(cp["dates"]),
            "raw_unadjusted_needs_corporate_action_validation":True,
            "source_authority":False}

def export_from_checkpoint(path,directory):
    if not allowed(os.environ):raise ValueError("SOURCE_OR_PRIVATE_CACHE_RIGHTS_NOT_CONFIRMED")
    s=scope()
    cp,restored=load(path,cipher(os.environ["XRAY_MASSIVE_API_KEY"]),s)
    if not restored:raise ValueError("WRONG_EPOCH_EXPORT")
    r=export_completed_private_csv(cp,s,directory)
    print("XRAY_GROUPED_PRIVATE_TRANSPORT_EXPORT=STRUCTURE_ONLY")
    print("XRAY_GROUPED_PRIVATE_SYMBOL_FILES="+str(r["symbol_csv_private"]))

def check_restore(path):
    if not allowed(os.environ):return 3
    s=scope()
    try: _,reused=load(path,cipher(os.environ["XRAY_MASSIVE_API_KEY"]),s)
    except Exception:return 3
    return 0 if reused else 2


def selftest():
    """No network; prove positive path, tampering, EOD lookahead and caps."""
    from tempfile import TemporaryDirectory
    from copy import deepcopy
    from cryptography.fernet import InvalidToken
    ss=scope()  # Source is actual current PRICE+MASTER SHA-bound state.
    # The C4.17 PRICE cohort changes with ASOF; never freeze selftest to 514.
    assert ss["symbols"] and ss["symbols"]==sorted(set(ss["symbols"]))
    assert len(ss["targets"])==len(set(ss["symbols"])|{"QQQ"})
    assert len(ss["dates"])==260 and len(ss["weeks"])==52
    # Change just the in-memory test scope in both directions. These fixtures
    # never reach a vendor, private checkpoint artifact, or production alpha.
    for variant in ("smaller","larger"):
        alternative=deepcopy(ss)
        if variant=="smaller":
            alternative["symbols"]=ss["symbols"][1:]
        else:
            marker="__XRAY_OFFLINE_SCOPE_ONLY__"
            assert marker not in ss["symbols"]
            alternative["symbols"]=sorted(ss["symbols"]+[marker])
        assert alternative["symbols"]
        alternative["targets"]=sorted(set(alternative["symbols"])|{"QQQ"})
        alternative["scope_hash"]=sha256_lines(alternative["symbols"])
        shadow_cp=fresh(alternative)
        assert exact(shadow_cp,alternative), "CHANGING_COHORT_FALSE_REJECTED"
        assert not exact(shadow_cp,ss), "STALE_COHORT_FALSE_ACCEPTED"
        assert (telemetry(shadow_cp,alternative,"SYNTHETIC_ONLY",0)
                ["max_sample_symbols"]==len(alternative["targets"]))
    liveprice=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    livemaster=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    assert master_price_lineage_exact(liveprice,livemaster)
    for kind in ("queue_hash","source_count","asof","unknown","unexpected_symbol"):
        pm=deepcopy(liveprice)
        mm=deepcopy(livemaster)
        if kind=="queue_hash":pm["source_master_queue_hash"]="0"*64
        if kind=="source_count":pm["source_master_count"]+=1
        if kind=="asof":mm["asof_et"]="2026-10-07"
        if kind=="unknown":mm["unknown_never_pass"]=False
        if kind=="unexpected_symbol":mm["pass_symbols"]=mm["pass_symbols"]+["ZZZZ"]
        assert master_price_lineage_exact(pm,mm) is False,"MASTER_PRICE_DRIFT_ACCEPTED_"+kind
    assert not allowed({})
    assert not allowed({"XRAY_MASSIVE_API_KEY":"a"*32,
                        "XRAY_MASSIVE_NONDISPLAY_LICENSE_OK":"true",
                        "XRAY_MASSIVE_LICENSE_EVIDENCE_SHA256":"f"*64})
    env={"XRAY_MASSIVE_API_KEY":"a"*32,
         "XRAY_MASSIVE_NONDISPLAY_LICENSE_OK":"true",
         "XRAY_MASSIVE_PRIVATE_CACHE_RIGHTS_OK":"true",
         "XRAY_MASSIVE_LICENSE_EVIDENCE_SHA256":"f"*64}
    assert allowed(env)
    assert not allowed({**env,"XRAY_MASSIVE_LICENSE_EVIDENCE_SHA256":"NOT_A_DIGEST"})
    for denial in (
        b"Warning [NOT_ENTITLED]: Data not included",
        b'{"status":"NOT_ENTITLED","results":[]}',
        b'{"status":"ERROR","error":"NOT_ENTITLED"}'):
        try:decode_provider_body(denial)
        except VendorNotEntitled as e:
            assert safe_vendor_block_reason(e)=="BLOCKED_PROVIDER_PLAN_NOT_ENTITLED"
        else:raise AssertionError("ACCOUNT_DENIAL_WAS_ACCEPTED")
    assert safe_vendor_block_reason(VendorNotEntitled("safe"))=="BLOCKED_PROVIDER_PLAN_NOT_ENTITLED"
    assert safe_vendor_block_reason(urllib.error.HTTPError(
        "https://example.invalid/?token=NEVER_PRINT",429,"secret",None,None)
        )=="BLOCKED_HTTP_429_FREE_TIER_RATE_LIMIT"
    assert safe_vendor_block_reason(urllib.error.HTTPError(
        "https://example.invalid/?token=NEVER_PRINT",403,"secret",None,None)
        )=="BLOCKED_HTTP_VENDOR_AUTH_OR_PLAN"
    cp=fresh(ss);assert exact(cp,ss)
    d=ss["dates"][-1]
    t=int(datetime.fromisoformat(d+"T20:00:00+00:00").timestamp()*1000)
    symbols=["QQQ",ss["symbols"][0],ss["symbols"][1]]
    bars={"status":"OK","adjusted":False,"resultsCount":3,
          "results":[{"T":z,"o":10,"h":11,"l":9,"c":10,"v":123.125,"t":t}
                     for z in symbols]}
    scoped=read_day(bars,d,ss["targets"])
    assert len(scoped)==3 and "QQQ" in scoped
    for tag in ("not_adjusted","missing_qqq","bad_price",
                "bad_asof","duplicate","bad_count"):
        bad=deepcopy(bars)
        if tag=="not_adjusted":bad["adjusted"]=True
        if tag=="missing_qqq":
            bad["results"]=[r for r in bad["results"] if r["T"]!="QQQ"]
            bad["resultsCount"]=len(bad["results"])
        if tag=="bad_price":bad["results"][0]["h"]=1
        if tag=="bad_asof":bad["results"][0]["t"]+=86400000
        if tag=="duplicate":
            bad["results"].append(deepcopy(bad["results"][0]))
            bad["resultsCount"]+=1
        if tag=="bad_count":bad["resultsCount"]=999
        try:read_day(bad,d,ss["targets"])
        except (ValueError,TypeError):continue
        raise AssertionError("BAD_GROUPED_VENDOR_ACCEPTED_"+tag)
    # A malformed irrelevant out-of-scope US ticker cannot poison an otherwise
    # valid 514-symbol batch, but a malformed in-scope bar MUST fail.
    ignore=deepcopy(bars)
    ignore["results"].append({"T":"NOT-IN-PASS-SCOPE","o":0})
    ignore["resultsCount"]+=1
    assert len(read_day(ignore,d,ss["targets"]))==3
    with TemporaryDirectory(prefix="xray-encrypted-history-") as tmp:
        root=Path(tmp)
        crypto=cipher("A"*32)
        path=root/"priv.enc"
        cp["request_count"]=1
        cp["dates"][d]=scoped
        save(cp,crypto,ss,path)
        # Fernet ciphertext is randomized base64: a three-byte ASCII sequence
        # such as QQQ may occur by chance. Reject *plaintext JSON structure*,
        # which base64 ciphertext cannot encode literally, then authenticate
        # and inspect the decrypted value. Never assert absence of arbitrary
        # substrings from encryption output.
        encoded=path.read_bytes()
        assert encoded and b'"QQQ"' not in encoded
        assert b'"QQQ"' in crypto.decrypt(encoded)
        other,restored=load(path,crypto,ss)
        assert restored and other["dates"][d]==scoped
        wrong=deepcopy(ss);wrong["price_sha"]="0"*40
        stale,reused=load(path,crypto,wrong)
        assert not reused and stale["dates"]=={}, "SAME_ASOF_SHA_DRIFT_WAS_MERGED"
        newer=deepcopy(ss)
        # Regression: this was hard-coded to 09-Oct, which ceases to be a
        # LATER session once live PRICE itself advances to 09-Oct.
        # Select the *next official Nasdaq session* only for this synthetic
        # rollover test. It creates no bars or time-travel production claim.
        from datetime import date,timedelta
        import pandas_market_calendars as mcal
        oldday=date.fromisoformat(ss["asof"])
        following=mcal.get_calendar("NASDAQ").valid_days(
            start_date=(oldday+timedelta(days=1)).isoformat(),
            end_date=(oldday+timedelta(days=14)).isoformat())
        assert len(following)>0
        newer["asof"]=following[0].date().isoformat()
        newer["dates"],newer["weeks"]=expected_dates(newer["asof"])
        assert newer["dates"][-1]==newer["asof"]
        assert len(newer["dates"])==260 and len(newer["weeks"])==52
        newer["dates_hash"]=sha256_lines(newer["dates"])
        newer["price_sha"]="0"*40
        newer["master_sha"]="1"*40
        rolled,match=load(path,crypto,newer)
        assert match and d in rolled["dates"] and rolled["dates"][d]==scoped
        assert exact(rolled,newer)
        assert rolled["alpha_authority"] is False
        # A partial checkpoint must never be materialized as full history.
        try:export_completed_private_csv(rolled,newer,root/"private")
        except ValueError:pass
        else:raise AssertionError("PARTIAL_HISTORY_EXPORT_ACCEPTED")
        tampered=path.read_bytes()[:-1]+b"Z"
        path.write_bytes(tampered)
        try:load(path,crypto,ss)
        except ValueError:pass
        else:raise AssertionError("TAMPERED_CIPHERTEXT_RESTORED")
        cp["dates"][d]["QQQ"][0]=-1
        assert not exact(cp,ss)
        try:save(cp,crypto,ss,path)
        except ValueError:pass
        else:raise AssertionError("INVALID_PRIVATE_BAR_SEALED")
    no=telemetry(fresh(ss),ss,"BLOCKED",0)
    assert no["remaining_days"]==260 and no["canonical_HISTORY_pass"] is False
    assert no["primary_MC_pass"] is False and no["R92_AL"] is False
    print("XRAY_MASSIVE_GROUPED_260_RESUME_SELFTEST=PASS_DYNAMIC_SCOPE_260_DAYS_52_WEEKS_6_VENDOR_NEGATIVES_ENCRYPTION_TAMPER_STALE_AND_NO_ALPHA")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report",type=Path)
    p.add_argument("--checkpoint",type=Path)
    p.add_argument("--restore",type=Path)
    p.add_argument("--limit",type=int,default=10)
    p.add_argument("--check-restore",type=Path)
    p.add_argument("--export-checkpoint",type=Path)
    p.add_argument("--export-dir",type=Path)
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest();return
    if args.check_restore:raise SystemExit(check_restore(args.check_restore))
    if args.export_checkpoint:
        if not args.export_dir:p.error("--export-dir required")
        export_from_checkpoint(args.export_checkpoint,args.export_dir)
        return
    if not args.report or not args.checkpoint:p.error("private paths required")
    for path in (args.report,args.checkpoint,args.restore):
        if path and path.resolve().is_relative_to(REPO.resolve()):p.error("public repo storage forbidden")
    run(args)

if __name__=="__main__":main()
