#!/usr/bin/env python3
from __future__ import annotations
import io, json, threading, time, urllib.error
from pathlib import Path
import resilience_runtime as rr

orig_urlopen=rr.urllib.request.urlopen
orig_ledger=rr.LEDGER
snapshot=orig_ledger.read_text() if orig_ledger.exists() else None
calls={"n":0}

class FakeResp:
    def __init__(self,body): self.body=body
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def read(self): return self.body

def good(req,timeout=20):
    calls["n"]+=1
    time.sleep(0.08)
    return FakeResp(b'{"ok":true,"value":7}')

def bad(req,timeout=20):
    calls["n"]+=1
    raise OSError("synthetic network failure")

def forbidden(req,timeout=20):
    calls["n"]+=1
    raise urllib.error.HTTPError(req.full_url,403,"Forbidden",{},io.BytesIO(b""))

def ratelimited(req,timeout=20):
    calls["n"]+=1
    raise urllib.error.HTTPError(req.full_url,429,"Too Many Requests",{},io.BytesIO(b""))

def flaky_once(req,timeout=20):
    calls["n"]+=1
    if calls["n"]==1:
        raise OSError("synthetic transient once")
    return FakeResp(b'{"ok":true,"recovered":true}')

try:
    rr._MEM.clear(); rr._INFLIGHT.clear()
    rr.urllib.request.urlopen=good
    vals=[]; errs=[]
    def worker():
        try: vals.append(rr.fetch_json("SELFTEST_SINGLE","https://selftest.invalid/a",cache_ttl=30))
        except Exception as e: errs.append(str(e))
    threads=[threading.Thread(target=worker) for _ in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errs,errs
    assert len(vals)==5
    assert all(x=={"ok":True,"value":7} for x in vals)
    assert calls["n"]==1,calls

    rr._MEM.clear(); rr._INFLIGHT.clear(); calls["n"]=0
    rr.urllib.request.urlopen=bad
    for i in range(3):
        try: rr.fetch_json("SELFTEST_BREAKER",f"https://selftest.invalid/fail{i}",circuit_failures=3,cooldown=120,retry_delays=(0,0),retry_jitter=0)
        except Exception: pass
    assert calls["n"]==9,calls
    try:
        rr.fetch_json("SELFTEST_BREAKER","https://selftest.invalid/fourth",circuit_failures=3,cooldown=120)
        raise AssertionError("circuit did not open")
    except RuntimeError as e:
        assert str(e).startswith("CIRCUIT_OPEN:SELFTEST_BREAKER"),str(e)
    assert calls["n"]==9,calls

    # A transient owner failure should recover inside one logical fetch and
    # publish the successful result to the single-flight cache.
    rr._MEM.clear(); rr._INFLIGHT.clear(); calls["n"]=0
    rr.urllib.request.urlopen=flaky_once
    got=rr.fetch_json("SELFTEST_RETRY_RECOVERY","https://selftest.invalid/recover",retry_delays=(0,),retry_jitter=0)
    assert got=={"ok":True,"recovered":True},got
    assert calls["n"]==2,calls
    led=json.loads(rr.LEDGER.read_text())
    assert led["providers"]["SELFTEST_RETRY_RECOVERY"]["status"]=="HEALTHY"

    # Definitive 403 must not build transient failure count or open circuit.
    rr._MEM.clear(); rr._INFLIGHT.clear(); calls["n"]=0
    rr.urllib.request.urlopen=forbidden
    for i in range(4):
        try: rr.fetch_json("SELFTEST_403",f"https://selftest.invalid/forbidden{i}",circuit_failures=3,cooldown=120)
        except urllib.error.HTTPError as e: assert e.code==403
    assert calls["n"]==4,calls
    led=json.loads(rr.LEDGER.read_text())
    p=led["providers"]["SELFTEST_403"]
    assert p["status"]=="NONRETRYABLE_ERROR",p
    assert p["consecutive_failures"]==0,p
    assert p["last_error_retryable"] is False,p
    assert p["last_http_status"]==403,p
    assert float(p.get("open_until_epoch") or 0)==0,p

    # 429 is transient and must participate in the circuit breaker.
    rr._MEM.clear(); rr._INFLIGHT.clear(); calls["n"]=0
    rr.urllib.request.urlopen=ratelimited
    for i in range(2):
        try: rr.fetch_json("SELFTEST_429",f"https://selftest.invalid/rate{i}",circuit_failures=2,cooldown=120,retry_delays=(0,0),retry_jitter=0)
        except urllib.error.HTTPError as e: assert e.code==429
    assert calls["n"]==6,calls
    led=json.loads(rr.LEDGER.read_text())
    p=led["providers"]["SELFTEST_429"]
    assert p["status"]=="CIRCUIT_OPEN",p
    assert p["last_error_retryable"] is True,p
    assert p["last_http_status"]==429,p

    led=json.loads(rr.LEDGER.read_text())
    assert led["providers"]["SELFTEST_SINGLE"]["status"]=="HEALTHY"
    assert led["providers"]["SELFTEST_BREAKER"]["status"]=="CIRCUIT_OPEN"
    print("XRAY_RESILIENCE_SELFTEST=PASS")
finally:
    rr.urllib.request.urlopen=orig_urlopen
    rr._MEM.clear(); rr._INFLIGHT.clear()
    if snapshot is None:
        try: orig_ledger.unlink()
        except FileNotFoundError: pass
    else:
        orig_ledger.write_text(snapshot)
