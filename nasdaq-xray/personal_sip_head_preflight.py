#!/usr/bin/env python3
"""Zero-vendor-HTTP main/ASOF/SHA preflight for personal SIP research.

Never authorizes C4.17 PRICE/HISTORY/MC, G9, R92, or market orders.
Requires exact source identity plus latest HEAD at every vendor stage.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
from source_epoch_freshness_guard import last_complete_session

ROOT=Path(__file__).resolve().parent
HEX40=re.compile(r"^[0-9a-f]{40}$")

def decide(local_sha,remote_sha,last,source):
    if not (isinstance(local_sha,str) and HEX40.fullmatch(local_sha)
            and isinstance(remote_sha,str) and HEX40.fullmatch(remote_sha)):
        return False,"HEAD_SHA_UNVERIFIED"
    if local_sha != remote_sha:
        return False,"MAIN_SUPERSEDED"
    if not isinstance(source,dict) or set(source)!={"sina","master","price"}:
        return False,"SOURCE_SET_MISSING"
    try:
        s,m,p=(source[k] for k in ("sina","master","price"))
        if any(x.get("asof_et")!=last for x in (s,m,p)):
            return False,"SOURCE_ASOF_NOT_LAST_COMPLETED"
        if any(x.get("execution")!="NONE" or x.get("real_money")!="NO-GO"
               or x.get("unknown_never_pass") is not True for x in (s,m,p)):
            return False,"SOURCE_SAFETY_DRIFT"
        n=s.get("queue_total")
        q=s.get("queue_hash")
        if (type(n) is not int or n<=0 or not isinstance(q,str)
                or not re.fullmatch(r"[0-9a-f]{64}",q)):
            return False,"SINA_QUEUE_INVALID"
        if not (m.get("queue_total")==n==p.get("source_master_count")
                and m.get("queue_hash")==q==p.get("source_master_queue_hash")):
            return False,"SOURCE_QUEUE_SHA_OR_COUNT_DRIFT"
    except (AttributeError,TypeError,ValueError):
        return False,"SOURCE_ARTIFACT_INVALID"
    return True,"EXACT_MAIN_ASOF_QUEUE_RESEARCH_ONLY"

def examine():
    try:
        current=os.environ.get("GITHUB_SHA","")
        last=last_complete_session(dt.datetime.now(dt.timezone.utc))
        remote=subprocess.run(["git","ls-remote","origin","refs/heads/main"],
                              text=True,capture_output=True,timeout=15,check=False)
        sha=(remote.stdout.split()[0] if remote.returncode==0 and
             remote.stdout.split() else "")
        source={k:json.loads((ROOT/v).read_text(encoding="utf-8"))
                for k,v in (("sina","sina_state.json"),
                             ("master","canonical_current_master_manifest.json"),
                             ("price","canonical_current_price_dv30.json"))}
        return decide(current,sha,last,source)
    except (KeyError,OSError,TypeError,ValueError,RuntimeError,
            subprocess.SubprocessError):
        return False,"PREFLIGHT_IO_OR_CALENDAR_UNVERIFIED"

def selftest():
    sha="a"*40
    q="b"*64
    last="2026-10-19"
    base={"asof_et":last,"execution":"NONE","real_money":"NO-GO",
          "unknown_never_pass":True}
    src={"sina":dict(base,queue_total=3189,queue_hash=q),
         "master":dict(base,queue_total=3189,queue_hash=q),
         "price":dict(base,source_master_count=3189,source_master_queue_hash=q)}
    assert decide(sha,sha,last,src)==(True,"EXACT_MAIN_ASOF_QUEUE_RESEARCH_ONLY")
    import copy
    cases=[
        ("" ,"HEAD_SHA_UNVERIFIED"),
        ("c"*40,"MAIN_SUPERSEDED"),
    ]
    for changed,reason in cases:
        assert decide(sha,changed,last,src)==(False,reason)
    tests=[
        (lambda x:x["sina"].update(asof_et="2026-10-16"),"SOURCE_ASOF_NOT_LAST_COMPLETED"),
        (lambda x:x["master"].update(queue_hash="f"*64),"SOURCE_QUEUE_SHA_OR_COUNT_DRIFT"),
        (lambda x:x["price"].update(source_master_count=0),"SOURCE_QUEUE_SHA_OR_COUNT_DRIFT"),
        (lambda x:x["price"].update(unknown_never_pass=False),"SOURCE_SAFETY_DRIFT"),
        (lambda x:x.pop("sina"),"SOURCE_SET_MISSING"),
        (lambda x:x["sina"].update(queue_hash="wrong"),"SINA_QUEUE_INVALID"),
    ]
    for modify,reason in tests:
        sample=copy.deepcopy(src);modify(sample)
        assert decide(sha,sha,last,sample)==(False,reason),reason
    print("XRAY_PERSONAL_SIP_HEAD_PREFLIGHT_SELFTEST=PASS_8_NEGATIVES_ZERO_VENDOR_HTTP")

def main():
    parser=argparse.ArgumentParser()
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--selftest",action="store_true")
    modes.add_argument("--emit",action="store_true")
    modes.add_argument("--check",action="store_true")
    opts=parser.parse_args()
    if opts.selftest:
        selftest();return
    ready,reason=examine()
    print("XRAY_PERSONAL_SIP_SOURCE_PREFLIGHT="+reason+
          "_"+("PASS" if ready else "NO_VENDOR_HTTP"))
    if opts.emit:
        out=os.environ.get("GITHUB_OUTPUT")
        if not out:raise RuntimeError("GITHUB_OUTPUT_REQUIRED")
        with open(out,"a",encoding="utf-8") as fp:
            fp.write("ready="+str(ready).lower()+"\\n")
    if opts.check and not ready:
        raise SystemExit(2)

if __name__=="__main__":main()
