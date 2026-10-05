#!/usr/bin/env python3
"""Restore the last validated immutable Pre-MC snapshot for one completed ASOF.

Zero-alpha recovery only. It restores an already-committed PRICE/DV20 snapshot
and its exact resolver request/manifest/chunks; it never manufactures market
data or changes C4.17 thresholds.
"""
from __future__ import annotations
import glob, hashlib, json, os, pathlib, re, subprocess, time

ROOT=pathlib.Path(__file__).resolve().parent
REPO=ROOT.parent
PRICE="nasdaq-xray/canonical_current_price_dv20.json"
STATIC=[
 "nasdaq-xray/canonical_current_full_state.json",
 "nasdaq-xray/canonical_current_full_candidates.json",
 "nasdaq-xray/canonical_current_unknowns.json",
 "nasdaq-xray/canonical_current_resolution_overlay.json",
 "nasdaq-xray/canonical_current_master_manifest.json",
 PRICE,
 "nasdaq-xray/canonical_current_resolver_request.json",
 "nasdaq-xray/canonical_current_resolver_chunk_manifest.json",
]
CHUNK_RE=re.compile(r"^nasdaq-xray/canonical_current_resolver_chunk_[0-9]{4}\.json$")

def run(*args,check=True,text=True):
    return subprocess.run(args,cwd=REPO,check=check,text=text,capture_output=True)

def blob(path:pathlib.Path)->str:
    b=path.read_bytes()
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()

def show_json(sha:str,path:str):
    cp=run("git","show",f"{sha}:{path}",check=False)
    if cp.returncode!=0:
        return None
    try:
        return json.loads(cp.stdout)
    except Exception:
        return None

def find_good(asof:str)->str:
    run("git","fetch","--depth=150","origin","main")
    cp=run("git","log","--format=%H","--",PRICE)
    for sha in cp.stdout.splitlines():
        p=show_json(sha,PRICE)
        if not p:
            continue
        if (
            p.get("asof_et")==asof
            and p.get("execution")=="NONE" and p.get("real_money")=="NO-GO"
            and int(p.get("unknown_count",-1))==0
            and int(p.get("pass_count",0))>0
        ):
            return sha
    raise RuntimeError("NO_VALID_SAME_ASOF_PRICE_SNAPSHOT")

def files_at(sha:str):
    cp=run("git","ls-tree","-r","--name-only",sha,"--","nasdaq-xray")
    chunks=[x for x in cp.stdout.splitlines() if CHUNK_RE.match(x)]
    if not chunks:
        raise RuntimeError("NO_RESOLVER_CHUNKS_IN_SNAPSHOT")
    for p in STATIC:
        probe=run("git","cat-file","-e",f"{sha}:{p}",check=False)
        if probe.returncode!=0:
            raise RuntimeError("SNAPSHOT_FILE_MISSING:"+p)
    return STATIC+chunks

def validate(asof:str):
    price=json.load(open(REPO/PRICE))
    master=json.load(open(ROOT/"canonical_current_master_manifest.json"))
    req=json.load(open(ROOT/"canonical_current_resolver_request.json"))
    manifest=json.load(open(ROOT/"canonical_current_resolver_chunk_manifest.json"))
    assert price["asof_et"]==master["asof_et"]==req["asof_et"]==asof
    assert price["execution"]=="NONE" and price["real_money"]=="NO-GO"
    assert int(price["unknown_count"])==0 and int(price["pass_count"])>0
    assert price["source_master_queue_hash"]==master["queue_hash"]
    assert req["queue_hash"]==master["queue_hash"]
    assert manifest["request_blob_sha"]==blob(ROOT/"canonical_current_resolver_request.json")
    assert manifest["queue_hash"]==req["queue_hash"]
    assert manifest["symbol_hash"]==req["symbol_hash"]
    assert int(manifest["symbol_count"])==int(req["symbol_count"])
    chunks=sorted(ROOT.glob("canonical_current_resolver_chunk_[0-9][0-9][0-9][0-9].json"))
    assert len(chunks)==int(manifest["chunk_count"])
    rebuilt=[]
    for cp in chunks:
        cj=json.load(open(cp))
        assert cj["request_blob_sha"]==manifest["request_blob_sha"]
        assert cj["symbol_hash"]==manifest["symbol_hash"]
        rebuilt.extend(cj["symbols"])
    assert rebuilt==req["symbols"]
    return {
      "asof":asof,"price_pass":price["pass_count"],"price_unknown":price["unknown_count"],
      "price_blocked":price.get("blocked_count",(price.get("counts") or {}).get("BLOCK_CURRENT_RUN",0)),
      "resolver_symbols":req["symbol_count"],"resolver_chunks":len(chunks),
    }

def restore_once(good:str,files:list[str],asof:str):
    run("git","fetch","origin","main")
    run("git","reset","--hard","origin/main")
    for p in glob.glob(str(ROOT/"canonical_current_resolver_chunk_[0-9][0-9][0-9][0-9].json")):
        pathlib.Path(p).unlink(missing_ok=True)
    for p in files:
        run("git","checkout",good,"--",p)
    summary=validate(asof)
    run("git","add","-A","--","nasdaq-xray")
    diff=run("git","diff","--cached","--quiet",check=False)
    if diff.returncode==0:
        print(json.dumps({"status":"NO_CHANGE","source_commit":good,**summary},sort_keys=True))
        return True
    run("git","commit","-m","fix(xray): restore validated frozen pre-MC epoch [skip ci]")
    push=run("git","push","origin","HEAD:main",check=False)
    if push.returncode==0:
        print(json.dumps({"status":"RESTORED","source_commit":good,**summary},sort_keys=True))
        return True
    return False

def main():
    asof=str(os.getenv("XRAY_RECOVERY_ASOF") or "").strip()
    if not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}",asof):
        raise RuntimeError("RECOVERY_ASOF_INVALID")
    good=find_good(asof)
    files=files_at(good)
    for attempt in range(1,6):
        if restore_once(good,files,asof):
            return
        time.sleep(attempt*2)
    raise RuntimeError("RECOVERY_PUSH_RACE_EXHAUSTED")

if __name__=="__main__":
    main()
