#!/usr/bin/env python3
"""Pin the first *actually fetched* NasdaqTrader directory within one ROOT run.

Only the orchestrator creates the private temp directory. A new ROOT run
fetches a fresh directory. Exact-ASOF footer validation and every canonical
source/identity/PRICE gate remain in sina_stage.py. This is not market data,
MC, RTH volume or R92 authority.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import tempfile

ENV_NAME="XRAY_NASDAQ_SAME_RUN_DIRECTORY_CACHE"
CACHE_FILENAME="official-nasdaq-listed.txt"

def read_once(fetch, cache_path=None):
    if cache_path is None or cache_path=="":
        return fetch()
    path=Path(cache_path)
    if (not path.is_absolute() or path.name!=CACHE_FILENAME
        or not path.parent.name.startswith("xray-nasdaq-run-")):
        raise ValueError("XRAY_NASDAQ_RUN_CACHE_PATH_NOT_PRIVATE")
    if path.is_symlink():
        raise ValueError("XRAY_NASDAQ_RUN_CACHE_SYMLINK_FORBIDDEN")
    if path.exists():
        if not path.is_file():
            raise ValueError("XRAY_NASDAQ_RUN_CACHE_NOT_FILE")
        return path.read_text(encoding="utf-8")
    body=fetch()
    if type(body) is not str or not body.strip():
        raise ValueError("XRAY_NASDAQ_DIRECTORY_EMPTY_FETCH")
    # Atomic exclusive create: no silent overwrite or cross-writer race.
    fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as out:
        out.write(body)
    return body

def selftest():
    calls=[]
    with tempfile.TemporaryDirectory(prefix="xray-nasdaq-run-") as folder:
        p=str(Path(folder)/CACHE_FILENAME)
        def fetch():
            calls.append(len(calls))
            return "Symbol|Security Name\\nAAPL|Apple Inc\\nFile Creation Time: 10212026\\n" if len(calls)==1 else "changed"
        first=read_once(fetch,p)
        for _ in range(16):
            assert read_once(fetch,p)==first
        assert len(calls)==1,"INTRA_RUN_NET_CALL_MULTIPLIED"
        assert "File Creation Time: 10212026" in first
        assert read_once(lambda:"fresh",None)=="fresh"
        assert (os.stat(p).st_mode & 0o777)==0o600
        bad=p+".wrong"
        try:read_once(fetch,bad)
        except ValueError:pass
        else:raise AssertionError("UNSAFE_CACHE_NAME_ACCEPTED")
        Path(p).write_text("",encoding="utf-8")
        # A corrupt cached directory remains rejectable by sina_stage's
        # exact source/footer/body validator; it may never silently refetch
        # and join two official directory snapshots in one ROOT run.
        assert read_once(fetch,p)==""
    with tempfile.TemporaryDirectory(prefix="xray-nasdaq-run-") as folder:
        p=str(Path(folder)/CACHE_FILENAME)
        assert read_once(lambda:"NEW_OFFICIAL_ASOF",p)=="NEW_OFFICIAL_ASOF"
    print("XRAY_NASDAQ_RUN_FENCE_SELFTEST=PASS_16_SUBPROCESSES_ONE_SOURCE_NEW_RUN_REFRESH_NO_OVERWRITE")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest()
    else:p.error("Offline --selftest only")
