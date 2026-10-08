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
import re
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
        "records":{},"retry_counts":{},"request_count_cumulative":0,
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
        or not isinstance(cp.get("retry_counts"),dict)
        or not set(cp["retry_counts"]).issubset(cp.get("records",{}))
        or any(type(n) is not int or n<1 or n>3
               for n in cp.get("retry_counts",{}).values())
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

def persist_checkpoint_atomic(cp,fernet,scope,path):
    """Write authenticated bytes durably after EACH accepted response.

    On a later unexpected runner failure, upload-artifact if:always can still
    preserve the most recent *valid* encrypted checkpoint.
    """
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    scratch=target.with_name(target.name+".pending")
    scratch.write_bytes(seal(cp,fernet,scope))
    os.replace(scratch,target)

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

def shadow_coverage_complete(scope, cp):
    """Only classify shadow coverage complete when EVERY symbol has valid PIT data."""
    rows=(cp or {}).get("records") or {}
    return (len(rows)==len(scope["symbols"])
            and all(rec.get("state") in (
                "SHADOW_OBSERVED_ABOVE_2B","SHADOW_OBSERVED_BELOW_2B")
                for rec in rows.values()))

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
        "resume_complete_shadow_only":shadow_coverage_complete(scope,cp),
        "all_symbols_attempted_but_unverified":pending==0 and not shadow_coverage_complete(scope,cp),
        "current_mc_production_authority":False,
        "note":"Even complete shadow cannot grant C4.17 MC or AL authority."}

def nondisplay_license_attested(environ):
    """Operator-provided compliance prerequisite, NOT an independent license grant.

    A true flag or digest proves only that the operator supplied a declaration.
    No legal entitlement, redistribution right or primary MC PASS is inferred.
    """
    raw=str(environ.get("XRAY_MASSIVE_NONDISPLAY_LICENSE_OK","")).lower()
    digest=str(environ.get("XRAY_MASSIVE_LICENSE_EVIDENCE_SHA256",""))
    return raw=="true" and bool(re.fullmatch(r"[a-f0-9]{64}",digest))

def retryable_unknown(rec):
    """Retry temporary errors, never upgrade stale or unsupported evidence."""
    if not isinstance(rec,dict) or rec.get("state")!="UNKNOWN":
        return False
    reason=str(rec.get("reason") or "")
    return (reason.startswith("TRANSPORT_") or reason.startswith("HTTP_5")
            or reason=="PROVIDER_RESPONSE_NOT_OK")

def run(args):
    scope=current_scope()
    out=Path(args.telemetry)
    out.parent.mkdir(parents=True,exist_ok=True)
    if args.limit<1 or args.limit>MAX_PER_RUN:
        raise ValueError("LIMIT_EXCEEDS_FREE_TIER_RUN_CAP")
    # A free API key alone is NOT permission to use market data as a
    # non-display investment-strategy input or to archive derived works.
    # A user-held written entitlement must exist BEFORE live collection.
    if not nondisplay_license_attested(os.environ):
        result=health(scope,status="BLOCKED_NONDISPLAY_LICENSE_UNVERIFIED",
            reason="WRITTEN_NONDISPLAY_AUTOMATED_COLLECTION_RIGHT_NOT_ATTESTED")
        out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        print("XRAY_MASSIVE_RESUME=BLOCKED_NONDISPLAY_LICENSE_UNVERIFIED")
        return 0
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
    todo=[s for s in scope["symbols"] if (s not in cp["records"]
          or (retryable_unknown(cp["records"].get(s))
              and cp["retry_counts"].get(s,0)<3))]
    count=0
    dest=Path(args.checkpoint)
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
        if retryable_unknown(cp["records"][symbol]):
            cp["retry_counts"][symbol]=cp["retry_counts"].get(symbol,0)+1
        cp["request_count_cumulative"]+=1
        count+=1
        persist_checkpoint_atomic(cp,fernet,scope,dest)
    persist_checkpoint_atomic(cp,fernet,scope,dest)
    remaining=len(scope["symbols"])-len(cp["records"])
    status=("SHADOW_COMPLETE_NO_ALPHA" if shadow_coverage_complete(scope,cp) else
            "SHADOW_ALL_ATTEMPTED_UNRESOLVED_NO_ALPHA" if remaining==0 else
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
    assert nondisplay_license_attested({}) is False
    assert nondisplay_license_attested({"XRAY_MASSIVE_NONDISPLAY_LICENSE_OK":"true"}) is False
    assert nondisplay_license_attested({
        "XRAY_MASSIVE_NONDISPLAY_LICENSE_OK":"true",
        "XRAY_MASSIVE_LICENSE_EVIDENCE_SHA256":"a"*64}) is True
    assert nondisplay_license_attested({
        "XRAY_MASSIVE_NONDISPLAY_LICENSE_OK":"false",
        "XRAY_MASSIVE_LICENSE_EVIDENCE_SHA256":"a"*64}) is False
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
    bad_rows=deepcopy(cp)
    bad_rows["records"]["NVDA"]=clean_record("NVDA",scope["asof_et"],{"state":"UNKNOWN","reason":"MARKET_CAP_UNAVAILABLE"})
    assert not shadow_coverage_complete(scope,bad_rows)
    assert health(scope,bad_rows)["all_symbols_attempted_but_unverified"] is True
    assert health(scope,bad_rows)["resume_complete_shadow_only"] is False
    assert retryable_unknown({"state":"UNKNOWN","reason":"HTTP_500"})
    assert retryable_unknown({"state":"UNKNOWN","reason":"TRANSPORT_URLError"})
    assert not retryable_unknown({"state":"UNKNOWN","reason":"SPAC_SUSPECT_OFFICIAL_SEC_PROOF_REQUIRED"})
    assert not retryable_unknown(good)
    # True two-invocation persistence test with NO live Massive requests.
    # A green test without this could mask a broken restore/resume workflow.
    import tempfile
    from types import SimpleNamespace
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)
        args=SimpleNamespace(
            limit=1,restore=str(path/"previous.enc"),
            checkpoint=str(path/"checkpoint.enc"),
            telemetry=str(path/"health.json"))
        env={"XRAY_MASSIVE_NONDISPLAY_LICENSE_OK":"true",
             "XRAY_MASSIVE_LICENSE_EVIDENCE_SHA256":"a"*64,
             "XRAY_MASSIVE_API_KEY":"unit-test-fixed-fake-secret-32characters-long"}
        fixture=lambda symbol: {
            "state":"SHADOW_OBSERVED_ABOVE_2B","ticker":symbol,
            "cik":"0000320193","primary_exchange":"XNAS","type":"CS",
            "market_cap_usd":4_000_000_000}
        with patch.dict(os.environ,env),patch(__name__+".current_scope",return_value=scope),\
             patch(__name__+".probe",side_effect=lambda sym,day,key:fixture(sym)) as fetch, \
             patch(__name__+".time.sleep") as sleep:
            run(args)
            assert fetch.call_count==1
            stage1=restore(Path(args.checkpoint).read_bytes(),a,scope)[0]
            assert set(stage1["records"])=={"AAPL"}
            assert stage1["request_count_cumulative"]==1
            # Simulate new runner by feeding downloaded ciphertext.
            Path(args.restore).write_bytes(Path(args.checkpoint).read_bytes())
            fetch.reset_mock()
            run(args)
            stage2=restore(Path(args.checkpoint).read_bytes(),a,scope)[0]
            assert fetch.call_count==1 and len(stage2["records"])==2
            assert stage2["request_count_cumulative"]==2
            assert json.loads(Path(args.telemetry).read_text())["pending_count"]==0
            Path(args.restore).write_bytes(Path(args.checkpoint).read_bytes())
            fetch.reset_mock()
            run(args)
            assert fetch.call_count==0
            assert json.loads(Path(args.telemetry).read_text())["last_run_requests"]==0
            assert sleep.call_count==0
        # Forced failure after the first observation must retain recoverable
        # ciphertext before the entire 25-request batch finishes.
        with patch.dict(os.environ,env),patch(__name__+".current_scope",return_value=scope),\
             patch(__name__+".probe",side_effect=[
                 fixture("AAPL"),RuntimeError("SIMULATED_PROVIDER_PROCESS_CRASH")]),\
             patch(__name__+".time.sleep"):
            args.limit=2
            Path(args.restore).unlink(missing_ok=True)
            Path(args.checkpoint).unlink(missing_ok=True)
            try:run(args)
            except RuntimeError as exc:
                assert "SIMULATED_PROVIDER_PROCESS_CRASH" in str(exc)
            else:raise AssertionError("EXPECTED_INTENTIONAL_FAULT")
            salvaged=restore(Path(args.checkpoint).read_bytes(),a,scope)[0]
            assert set(salvaged["records"])=={"AAPL"}
            assert salvaged["request_count_cumulative"]==1
            args.limit=1
        # The licence and key gates stop before touching the remote provider.
        Path(args.restore).unlink(missing_ok=True)
        with patch.dict(os.environ,{"XRAY_MASSIVE_NONDISPLAY_LICENSE_OK":"false",
                                    "XRAY_MASSIVE_LICENSE_EVIDENCE_SHA256":""}), \
             patch(__name__+".current_scope",return_value=scope), \
             patch(__name__+".probe") as blocked_probe:
            run(args)
            blocked_probe.assert_not_called()
            assert json.loads(Path(args.telemetry).read_text())["status"]=="BLOCKED_NONDISPLAY_LICENSE_UNVERIFIED"
    print("XRAY_MASSIVE_RESUME_SELFTEST=PASS_ENCRYPT_REPLAY_C4.17_NO_ALPHA")
    print("XRAY_MASSIVE_RESUME_INTEGRATION=PASS_TWO_RUN_RESUME_NO_DUPLICATES_NO_LIVE_REQUESTS")

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
