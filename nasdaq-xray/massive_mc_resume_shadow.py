#!/usr/bin/env python3
"""Persistent, encrypted, zero-alpha Massive PIT MC collector.

C4.17 remains unchanged: this is *not* an admitted primary MC provider.
No plaintext vendor records in public GitHub logs, commits or artifacts.
Private cipher state is replay-protected by ASOF + exact PRICE Git SHA.
"""
from __future__ import annotations
import argparse
import base64
from copy import deepcopy
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

from massive_mc_shadow_probe import (
    ROOT, MC_FLOOR, classify, probe, select_current_price_scope
)

SCHEMA="XRAY_MASSIVE_MC_RESUME_SHADOW_V1"
REPORT="XRAY_MASSIVE_MC_RESUME_HEALTH_V1"
ARTIFACT_NAME="xray-massive-mc-checkpoint-encrypted-v1"
MAX_PER_RUN=25
MIN_SPACING_SECONDS=13.0
CAPACITY=5
SCOPE_STATUS="NON_ALPHA_SHADOW_ONLY"

def git_sha(data:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def bytes_sha256(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def make_fernet(api_key:str):
    """Derive a distinct authenticated-encryption key from one GitHub secret.

    Rotating the API key invalidates prior encrypted checkpoints and triggers
    a *new* diagnostic run, not a stale restore or an alpha promotion.
    """
    if not api_key or len(api_key)<20:
        raise ValueError("API_KEY_MISSING_OR_WEAK_FOR_CHECKPOINT")
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.fernet import Fernet
    salt=b"xray-massive-mc-c417-personal-usage-20261009-v1"
    key=HKDF(algorithm=hashes.SHA256(),length=32,salt=salt,
             info=b"NASDAQ-XRAY-MASSIVE-MC-ENCRYPTED-PIT-CHECKPOINT-V1").derive(
                 api_key.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))

def current_scope(root=ROOT):
    master_path=root/"canonical_current_master_manifest.json"
    price_path=root/"canonical_current_price_dv30.json"
    mb=master_path.read_bytes()
    pb=price_path.read_bytes()
    master=json.loads(mb)
    price=json.loads(pb)
    asof, symbols=select_current_price_scope(master,price)
    # A mutable same-session master footer must never be mistaken for an
    # exact-bound primary MC authority. Price+scope are diagnostic-only.
    return {"asof_et":asof,"symbols":symbols,
        "scope_hash":bytes_sha256(("\n".join(symbols)+"\n").encode()),
        "master_blob_sha":git_sha(mb),
        "price_blob_sha":git_sha(pb),
        "master_price_content_binding_exact":(
            master.get("queue_hash")==price.get("source_master_queue_hash")),
        "master_queue_count":len(master.get("pass_symbols") or []),
        "price_pass_count":len(symbols)}

def fresh_checkpoint(scope):
    return {"schema":SCHEMA,"asof_et":scope["asof_et"],
        "price_blob_sha":scope["price_blob_sha"],
        "scope_hash":scope["scope_hash"],
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
        "alpha_authority":False,"policy_unchanged":"C4.17",
        "records":{},"request_count_cumulative":0,
        "created_by":"GITHUB_ACTIONS_ENCRYPTED_CHECKPOINT"}

def exact_checkpoint(cp,scope):
    if (not isinstance(cp,dict) or cp.get("schema")!=SCHEMA
        or cp.get("asof_et")!=scope["asof_et"]
        or cp.get("price_blob_sha")!=scope["price_blob_sha"]
        or cp.get("scope_hash")!=scope["scope_hash"]
        or cp.get("execution")!="NONE" or cp.get("real_money")!="NO-GO"
        or cp.get("unknown_never_pass") is not True
        or cp.get("alpha_authority") is not False
        or cp.get("policy_unchanged")!="C4.17"
        or not isinstance(cp.get("records"),dict)
        or len(cp["records"])>len(scope["symbols"])
        or not set(cp["records"]).issubset(scope["symbols"])
        or type(cp.get("request_count_cumulative")) is not int
        or cp["request_count_cumulative"]<len(cp["records"])):
        return False
    for symbol,rec in cp["records"].items():
        if (not isinstance(rec,dict)
            or rec.get("source")!="MASSIVE_REFERENCE_TICKER_OVERVIEW_PIT"
            or rec.get("asof_et")!=scope["asof_et"]
            or rec.get("alpha_authority") is not False
            or rec.get("r92_eligible") is not False
            or rec.get("state") not in (
                "UNKNOWN","SHADOW_OBSERVED_ABOVE_2B",
                "SHADOW_OBSERVED_BELOW_2B")):
            return False
        if rec.get("state")!="UNKNOWN":
            mc=rec.get("market_cap_usd")
            if (type(mc) not in (float,int)
                or not math.isfinite(mc) or mc<=0
                or (mc>=MC_FLOOR)!=(rec["state"]=="SHADOW_OBSERVED_ABOVE_2B")
                or not isinstance(rec.get("cik"),str)
                or len(rec["cik"])!=10 or not rec["cik"].isdigit()
                or rec.get("primary_exchange") not in ("XNAS","XNGS","XNMS","XNCM")
                or rec.get("type")!="CS"
                or rec.get("ticker")!=symbol):
                return False
    return True

def restore(ciphertext:bytes,fernet,scope):
    if not ciphertext:
        return fresh_checkpoint(scope),False
    if len(ciphertext)>4_000_000:
        raise ValueError("CHECKPOINT_OVERSIZED")
    try:
        raw=fernet.decrypt(ciphertext)
        cp=json.loads(raw)
    except Exception as exc:
        raise ValueError("CHECKPOINT_DECRYPT_OR_PARSE_FAILED") from exc
    if (cp.get("asof_et")!=scope["asof_et"]
        or cp.get("price_blob_sha")!=scope["price_blob_sha"]
        or cp.get("scope_hash")!=scope["scope_hash"]):
        # Authenticated, genuine prior epoch; discard ALL old observations.
        # No stale-price or stale-MC carryover even when symbol sets coincide.
        if cp.get("schema")!=SCHEMA:
            raise ValueError("CHECKPOINT_SCHEMA_CHANGED")
        return fresh_checkpoint(scope),False
    if not exact_checkpoint(cp,scope):
        raise ValueError("CHECKPOINT_SOURCE_OR_SEMANTICS_DRIFT")
    return cp,True

def seal(cp,fernet,scope):
    if not exact_checkpoint(cp,scope):
        raise ValueError("CHECKPOINT_NOT_EXACT_PRESEAL")
    raw=json.dumps(cp,sort_keys=True,separators=(",",":")).encode("utf-8")
    return fernet.encrypt(raw)

def clean_record(symbol,asof,raw):
    state=raw.get("state")
    if state not in ("SHADOW_OBSERVED_ABOVE_2B","SHADOW_OBSERVED_BELOW_2B"):
        return {"state":"UNKNOWN",
                "reason":str(raw.get("reason") or "VENDOR_PROOF_UNVERIFIED")[:80],
                "source":"MASSIVE_REFERENCE_TICKER_OVERVIEW_PIT",
                "asof_et":asof,"alpha_authority":False,"r92_eligible":False}
    return {"state":state,
        "ticker":symbol,"cik":str(raw["cik"]),
        "market_cap_usd":raw["market_cap_usd"],
        "primary_exchange":raw["primary_exchange"],"type":raw["type"],
        "source":"MASSIVE_REFERENCE_TICKER_OVERVIEW_PIT",
        "asof_et":asof,"alpha_authority":False,"r92_eligible":False}

def health(scope, cp=None,status="UNKNOWN",requests=0,restored=False,reason=None):
    records=(cp or {}).get("records") or {}
    n=len(records)
    pending=len(scope["symbols"])-n
    if pending<0:raise ValueError("NEGATIVE_PENDING")
    return {"schema":REPORT,"asof_et":scope["asof_et"],
        "status":status,"block_reason":reason,
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"alpha_authority":False,
        "policy_unchanged":"C4.17","mc_primary_pass_created":False,
        "r92_created":False,"research_signal_created":False,
        "vendor_data_in_public_artifact":False,
        "source_price_blob_sha":scope["price_blob_sha"],
        "source_scope_sha256":scope["scope_hash"],
        "source_master_price_scope_equal":scope["master_price_content_binding_exact"],
        "total_price_pass":len(scope["symbols"]),
        "processed_count":n,"pending_count":pending,
        "last_run_requests":requests,"restored_encrypted_checkpoint":restored,
        "resume_complete_shadow_only":pending==0,
        "current_mc_production_authority":False,
        "note":"Even complete shadow cannot grant C4.17 MC or AL authority."}

def run(args):
    scope=current_scope()
    out=Path(args.telemetry)
    out.parent.mkdir(parents=True,exist_ok=True)
    if args.limit<1 or args.limit>MAX_PER_RUN:
        raise ValueError("LIMIT_EXCEEDS_FREE_TIER_RUN_CAP")
    token=os.getenv("XRAY_MASSIVE_API_KEY","").strip()
    if not token:
        result=health(scope,status="BLOCKED_NO_RUNTIME_KEY",reason="MISSING_GITHUB_ACTIONS_SECRET")
        out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        print("XRAY_MASSIVE_RESUME=BLOCKED_NO_RUNTIME_KEY")
        return 0
    fernet=make_fernet(token)
    restore_path=Path(args.restore)
    cipher=restore_path.read_bytes() if restore_path.is_file() else b""
    cp,restored=restore(cipher,fernet,scope)
    todo=[s for s in scope["symbols"] if s not in cp["records"]]
    count=0
    interrupted_reason=None
    for i,symbol in enumerate(todo[:args.limit]):
        # Prevent exceeding 5 calls/minute from this job: every 13 seconds.
        if i>0:time.sleep(MIN_SPACING_SECONDS)
        raw=probe(symbol,scope["asof_et"],token)
        reason=str(raw.get("reason") or "")
        if reason in ("HTTP_429","HTTP_401","HTTP_403","HTTP_402"):
            interrupted_reason="VENDOR_QUOTA_OR_AUTHORIZATION"
            break
        cp["records"][symbol]=clean_record(symbol,scope["asof_et"],raw)
        count+=1
    cp["request_count_cumulative"]+=count
    encrypted=seal(cp,fernet,scope)
    dest=Path(args.checkpoint)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(encrypted)
    remaining=len(scope["symbols"])-len(cp["records"])
    status=("SHADOW_COMPLETE_NO_ALPHA" if remaining==0 else
            "SHADOW_PARTIAL_NO_ALPHA")
    if interrupted_reason:status="BLOCKED_VENDOR_QUOTA_OR_AUTHORIZATION"
    result=health(scope,cp,status,count,restored,interrupted_reason)
    out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_MASSIVE_RESUME="+status)
    print("XRAY_MASSIVE_RESUME_COUNTS="+json.dumps({
        "processed_count":len(cp["records"]),"pending_count":remaining,
        "run_requests":count,"restored":restored,
        "alpha_authority":False},sort_keys=True))
    return 0

def selftest():
    from cryptography.fernet import InvalidToken
    scope={"asof_et":"2026-10-08","symbols":["AAPL","NVDA"],
        "scope_hash":"sh","price_blob_sha":"ph",
        "master_price_content_binding_exact":True}
    a=make_fernet("unit-test-fixed-fake-secret-32characters-long")
    b=make_fernet("different-fixed-fake-secret-32characters-long")
    cp=fresh_checkpoint(scope)
    assert exact_checkpoint(cp,scope)
    raw=seal(cp,a,scope)
    rr,ok=restore(raw,a,scope)
    assert ok and rr==cp
    try:restore(raw,b,scope)
    except ValueError:pass
    else:raise AssertionError("KEY_ROTATION_NOT_BLOCKED")
    badscope=dict(scope,asof_et="2026-10-09")
    restart, reused=restore(raw,a,badscope)
    assert reused is False and restart["records"]=={}
    assert restart["asof_et"]=="2026-10-09"
    for fn in (
        lambda d:d.update(alpha_authority=True),
        lambda d:d.update(price_blob_sha="rebound"),
        lambda d:d.update(scope_hash="wrong"),
        lambda d:d.update(policy_unchanged="C4.18"),
        lambda d:d.update(request_count_cumulative=-1),
        lambda d:d.update(records={"OUTSIDE":{}}),
    ):
        invalid=deepcopy(cp);fn(invalid)
        assert not exact_checkpoint(invalid,scope)
    good=clean_record("AAPL",scope["asof_et"],classify("AAPL",{
        "ticker":"AAPL","active":True,"market":"stocks","primary_exchange":"XNAS",
        "type":"CS","currency_name":"usd","cik":"0000320193",
        "market_cap":4_000_000_000}))
    assert good["state"]=="SHADOW_OBSERVED_ABOVE_2B"
    assert good["alpha_authority"] is False and good["r92_eligible"] is False
    cp["records"]["AAPL"]=good
    cp["request_count_cumulative"]=1
    assert exact_checkpoint(cp,scope)
    for mutation in (
        {"market_cap_usd":True},
        {"market_cap_usd":float("nan")},
        {"market_cap_usd":100},
        {"state":"SHADOW_OBSERVED_BELOW_2B"},
        {"primary_exchange":"XNYS"},
        {"cik":"123"},
        {"alpha_authority":True},
        {"r92_eligible":True},
    ):
        corrupted=deepcopy(cp)
        corrupted["records"]["AAPL"].update(mutation)
        assert not exact_checkpoint(corrupted,scope),mutation
    final=restore(seal(cp,a,scope),a,scope)[0]
    assert final["records"]["AAPL"]["market_cap_usd"]==4_000_000_000
    public=json.dumps(health(scope,cp,"SHADOW_PARTIAL_NO_ALPHA",1,True))
    assert "AAPL" not in public and "4000000000" not in public
    assert "SHADOW_OBSERVED_ABOVE_2B" not in public
    assert health(scope,cp)["pending_count"]==1
    print("XRAY_MASSIVE_RESUME_SELFTEST=PASS_ENCRYPT_REPLAY_C4.17_NO_ALPHA")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--limit",type=int,default=25)
    p.add_argument("--restore",default="/tmp/xray_mc_checkpoint_previous.enc")
    p.add_argument("--checkpoint",default="/tmp/xray_mc_checkpoint_current.enc")
    p.add_argument("--telemetry",default="/tmp/xray_mc_resume_health.json")
    args=p.parse_args()
    if args.selftest:selftest()
    else:sys.exit(run(args))
