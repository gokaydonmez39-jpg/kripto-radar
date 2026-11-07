#!/usr/bin/env python3
"""Verify downloaded binary-wheel SHA256 against review-committed audit lock.

No network, package installation, archive unpacking, secret reads or file writes.
Not a complete vulnerability scan, provider data-rights or production attestation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

RECEIPT="XRAY_STRONG4_WHEELHOUSE_SHA256_RECEIPT_V1"
TARGETS={"pydantic":"2.14.3","quantstats":"0.0.86","vectorbt":"1.2.0","duckdb":"2.0.0"}

def witness(directory: Path, sdk: str, lock: dict | None = None) -> dict:
    if type(sdk) is not str or sdk not in TARGETS:
        raise ValueError("UNKNOWN_SDK_TARGET")
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("INVALID_WHEELHOUSE_DIRECTORY")
    files=sorted(directory.iterdir(),key=lambda p:p.name)
    if not files or len(files)>250:
        raise ValueError("WHEELHOUSE_EMPTY_OR_TOO_LARGE")
    items=[]
    for f in files:
        if not f.is_file() or f.is_symlink() or not f.name.endswith(".whl"):
            raise ValueError("NON_BINARY_OR_SYMLINK_ARTIFACT")
        size=f.stat().st_size
        if not (0<size<=250_000_000):
            raise ValueError("INVALID_WHEEL_BYTES")
        parts=f.name.split("-")
        if len(parts)<5 or not re.fullmatch(r"[A-Za-z0-9_\.]+",parts[0]) or not re.fullmatch(r"[A-Za-z0-9_.+]+",parts[1]):
            raise ValueError("INVALID_WHEEL_FILENAME")
        normalized_name=parts[0].lower().replace("_","-").replace(".","-")
        key=(normalized_name,parts[1])
        if any((i["name"],i["version"])==key for i in items):
            raise ValueError("DUPLICATE_DISTRIBUTION_VERSION")
        h=hashlib.sha256()
        with f.open("rb") as fh:
            for block in iter(lambda:fh.read(1024*1024),b""):
                h.update(block)
        items.append({"filename":f.name,"name":key[0],"version":key[1],"size_bytes":size,"sha256":h.hexdigest()})
    direct=(sdk,TARGETS[sdk])
    if not any((x["name"],x["version"])==direct for x in items):
        raise ValueError("DIRECT_VERSION_MISSING")
    canonical=json.dumps(items,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    if lock is not None:
        if type(lock) is not dict or lock.get("schema") != "XRAY_STRONG4_WHEELHOUSE_IMMUTABLE_LOCK_V1":
            raise ValueError("LOCK_SCHEMA_INVALID")
        targets=lock.get("targets")
        if type(targets) is not dict or set(targets) != set(TARGETS):
            raise ValueError("LOCK_TARGETS_INVALID")
        saved=targets.get(sdk)
        if type(saved) is not dict or set(saved) != {"version","inventory_digest","wheels"}:
            raise ValueError("LOCK_ENTRY_INVALID")
        if saved["version"] != TARGETS[sdk] or saved["inventory_digest"] != hashlib.sha256(canonical).hexdigest() or saved["wheels"] != items:
            raise ValueError("WHEELHOUSE_HASH_LOCK_MISMATCH")
    return {"schema":RECEIPT,"sdk":sdk,"direct_version":TARGETS[sdk],
            "observed_binary_wheels":len(items),
            "full_wheel_inventory_sha256":hashlib.sha256(canonical).hexdigest(),
            "observed_packages":items,
            "transitive_wheels_installable_not_verified":True,
            "hash_lock_committed":lock is not None,
            "hash_lock_verified":lock is not None,
            "trusted_provenance_verified":False,
            "vulnerability_audit_verified":False,
            "license_audit_all_transitives_verified":False,
            "production_authorized":False}

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--wheel-dir",type=Path,required=True)
    parser.add_argument("--sdk",required=True)
    parser.add_argument("--lock-file",type=Path,required=True)
    a=parser.parse_args()
    try:
        lock=json.loads(a.lock_file.read_text(encoding="utf-8"))
        print("XRAY_STRONG4_WHEELHOUSE_RECEIPT="+json.dumps(witness(a.wheel_dir,a.sdk,lock),sort_keys=True))
        return 0
    except (ValueError,OSError,TypeError,json.JSONDecodeError) as exc:
        print(json.dumps({"status":"HOLD","reason":str(exc)[:150],"production_authorized":False},sort_keys=True))
        return 3
if __name__=="__main__": raise SystemExit(main())
