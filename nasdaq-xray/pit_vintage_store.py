#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

SAFE=re.compile(r"[^A-Za-z0-9_.-]+")
def canonical_bytes(obj):
    return (json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode("utf-8")
def content_hash(obj):
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()
def _safe(x):
    return SAFE.sub("_",str(x)).strip("._") or "unknown"

def append_vintage(root,dataset,entity_key,available_at,source,payload,metadata=None):
    """Append one immutable PIT vintage. Never overwrites an existing payload."""
    root=Path(root)
    rec={
        "schema":"XRAY_PIT_VINTAGE_V1",
        "dataset":str(dataset),
        "entity_key":str(entity_key),
        "available_at":str(available_at),
        "source":str(source),
        "payload":payload,
        "metadata":metadata or {},
    }
    rec["payload_sha256"]=content_hash(payload)
    rec["record_sha256"]=content_hash(rec)
    d=root/_safe(dataset)/_safe(entity_key)
    d.mkdir(parents=True,exist_ok=True)
    p=d/f"{_safe(available_at)}__{rec['record_sha256']}.json"
    if p.exists():
        old=json.loads(p.read_text(encoding="utf-8"))
        if old!=rec:
            raise RuntimeError("PIT_IMMUTABILITY_VIOLATION")
        return p
    p.write_bytes(canonical_bytes(rec))
    return p

def visible_vintages(root,dataset,entity_key,asof):
    d=Path(root)/_safe(dataset)/_safe(entity_key)
    if not d.exists(): return []
    out=[]
    for p in sorted(d.glob("*.json")):
        j=json.loads(p.read_text(encoding="utf-8"))
        if str(j.get("available_at",""))<=str(asof):
            out.append(j)
    return out

def latest_visible(root,dataset,entity_key,asof):
    xs=visible_vintages(root,dataset,entity_key,asof)
    return xs[-1] if xs else None
