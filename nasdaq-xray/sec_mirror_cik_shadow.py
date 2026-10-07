#!/usr/bin/env python3
"""Public SHA-verified SEC CIK mirror — discovery only, never AL/GO."""
import argparse,hashlib,json,pathlib,urllib.request
ROOT=pathlib.Path(__file__).resolve().parent
UPSTREAM="TylerJForstrom/Stock-Data"
SCOPE="data/symbols/current/"
HEAD="https://api.github.com/repos/"+UPSTREAM+"/git/ref/heads/main"
UA="NASDAQ-SWING-XRAY research xray-dataplane-bot@users.noreply.github.com"
def sha(x):return hashlib.sha256(x).hexdigest()
def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":UA}),timeout=22) as r:
        out=r.read(3_000_001)
    if len(out)>3_000_000:raise ValueError("UNBOUNDED_SOURCE")
    return out
def classify(asof,unknown,manifest,body):
    if manifest.get("snapshot_date")!=asof or (manifest.get("last_success") or {}).get("sec_company_tickers_exchange")!=asof:raise ValueError("ASOF_DRIFT")
    item=next((v for v in manifest.get("files",[]) if v.get("name")=="sec_company_tickers_exchange.jsonl"),{})
    if item.get("sha256")!=sha(body) or item.get("bytes")!=len(body):raise ValueError("SOURCE_SHA256_MISMATCH")
    maps={};conflicts=set()
    for line in body.splitlines():
        d=json.loads(line)
        if str(d.get("exchange","")).upper()!="NASDAQ":continue
        sym=str(d.get("ticker","")).strip().upper()
        try:cik=int(d.get("cik"))
        except (ValueError,TypeError):continue
        if not sym or cik<=0:continue
        if sym in maps and maps[sym]!=cik:conflicts.add(sym)
        else:maps[sym]=cik
    for sym in conflicts:maps.pop(sym,None)
    found={s:f"{maps[s]:010d}" for s in sorted(set(unknown)) if s in maps}
    return {"status":"EXACT_ASOF_CIK_DISCOVERY_ONLY","ciK_discovered_count":len(found),
            "ciK_discovery_only":found,"unknown_total":len(set(unknown)),
            "symbol_conflict_count":len(conflicts),"source_sha256":sha(body)}
def run():
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    asof=master["asof_et"];unknown=master.get("unknown_symbols") or []
    assert len(unknown)==master["unknown_count"]
    out={"schema":"XRAY_SEC_MIRROR_CIK_SHADOW_V1","asof_et":asof,
         "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
         "alpha_authority":False,"official_sec_sic_authority":False,"go":False,
         "approved_alpha_symbols":[],"status":"UNKNOWN_SOURCE","ciK_discovered_count":0,
         "unknown_total":len(unknown),"ciK_discovery_only":{}}
    try:
        obj=json.loads(fetch(HEAD))
        rev=obj["object"]["sha"]
        if len(rev)!=40 or any(c not in "0123456789abcdef" for c in rev):raise ValueError("HEAD_UNPINNED")
        prefix="https://raw.githubusercontent.com/"+UPSTREAM+"/"+rev+"/"+SCOPE
        manifest=json.loads(fetch(prefix+"manifest.json"))
        raw=fetch(prefix+"sec_company_tickers_exchange.jsonl")
        out.update(classify(asof,unknown,manifest,raw))
        out["source_repository"]=UPSTREAM
        out["source_commit"]=rev
    except Exception as exc:
        out["failure_reason"]=type(exc).__name__+":"+str(exc)[:170]
    return out
def selftest():
    raw=b'{"ticker":"TEST","cik":123,"exchange":"Nasdaq"}\n{"ticker":"ALT","cik":456,"exchange":"NYSE"}\n'
    m={"snapshot_date":"2026-10-07","last_success":{"sec_company_tickers_exchange":"2026-10-07"},
       "files":[{"name":"sec_company_tickers_exchange.jsonl","bytes":len(raw),"sha256":sha(raw)}]}
    o=classify("2026-10-07",["TEST","ALT"],m,raw)
    assert o["ciK_discovered_count"]==1 and o["ciK_discovery_only"]=={"TEST":"0000000123"}
    for badm,badr in [(dict(m,snapshot_date="2026-10-06"),raw),(m,raw+b"garbage")]:
        try:classify("2026-10-07",["TEST"],badm,badr)
        except ValueError:pass
        else:raise AssertionError("INVALID_SHADOW_ACCEPTED")
    print("XRAY_SEC_MIRROR_NO_ALPHA_SELFTEST=PASS")
if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--out")
    v=a.parse_args()
    if v.selftest:selftest()
    else:
        if not v.out:a.error("--out required")
        result=run()
        pathlib.Path(v.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print(json.dumps({k:result.get(k) for k in ("status","asof_et","unknown_total","ciK_discovered_count","failure_reason")}))
