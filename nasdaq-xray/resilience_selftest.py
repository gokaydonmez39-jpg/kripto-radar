#!/usr/bin/env python3
from __future__ import annotations
import json, threading, time
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
        try: rr.fetch_json("SELFTEST_BREAKER",f"https://selftest.invalid/fail{i}",circuit_failures=3,cooldown=120)
        except Exception: pass
    assert calls["n"]==3,calls
    try:
        rr.fetch_json("SELFTEST_BREAKER","https://selftest.invalid/fourth",circuit_failures=3,cooldown=120)
        raise AssertionError("circuit did not open")
    except RuntimeError as e:
        assert str(e).startswith("CIRCUIT_OPEN:SELFTEST_BREAKER"),str(e)
    assert calls["n"]==3,calls

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
