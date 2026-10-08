#!/usr/bin/env python3
"""Exact-ASOF, SHA256-verified public SEC ticker-CIK mirror: discovery only."""
import argparse,hashlib,json,pathlib,urllib.parse,urllib.request
ROOT=pathlib.Path(__file__).resolve().parent
UPSTREAM="TylerJForstrom/Stock-Data"
SCOPE="data/symbols/current/"
API="https://api.github.com/repos/"+UPSTREAM+"/commits"
UA="NASDAQ-SWING-XRAY research xray-dataplane-bot@users.noreply.github.com"

def sha(x):return hashlib.sha256(x).hexdigest()

def fetch(url):
    if not url.startswith(("https://api.github.com/repos/TylerJForstrom/Stock-Data/",
                           "https://raw.githubusercontent.com/TylerJForstrom/Stock-Data/")):
        raise ValueError("UNAPPROVED_MIRROR_ORIGIN")
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":UA,
        "Accept":"application/json"}),timeout=22) as r:
        out=r.read(3_000_001)
    if len(out)>3_000_000:raise ValueError("UNBOUNDED_SOURCE")
    return out

def classify(asof,unknown,manifest,body):
    if (manifest.get("snapshot_date")!=asof or
            (manifest.get("last_success") or {}).get("sec_company_tickers_exchange")!=asof):
        raise ValueError("ASOF_DRIFT")
    item=next((v for v in manifest.get("files",[]) if
               v.get("name")=="sec_company_tickers_exchange.jsonl"),{})
    if item.get("sha256")!=sha(body) or item.get("bytes")!=len(body):
        raise ValueError("SOURCE_SHA256_MISMATCH")
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
    return {"status":"EXACT_ASOF_CIK_DISCOVERY_ONLY",
            "ciK_discovered_count":len(found),
            "ciK_discovery_only":found,"unknown_total":len(set(unknown)),
            "symbol_conflict_count":len(conflicts),"source_sha256":sha(body)}

def select_exact_asof_commit(asof,request=fetch):
    """Use historical immutable snapshot, not current main, without future leakage."""
    from datetime import date
    if date.fromisoformat(asof).isoformat()!=asof:
        raise ValueError("ASOF_INVALID")
    url=API+"?"+urllib.parse.urlencode({
        "path":SCOPE+"manifest.json",
        "until":asof+"T23:59:59Z",
        "per_page":30})
    entries=json.loads(request(url))
    if not isinstance(entries,list) or not entries:raise ValueError("NO_HISTORICAL_COMMITS")
    for entry in entries:
        rev=str(entry.get("sha",""))
        if len(rev)!=40 or any(c not in "0123456789abcdef" for c in rev):
            continue
        prefix="https://raw.githubusercontent.com/"+UPSTREAM+"/"+rev+"/"+SCOPE
        try:
            manifest=json.loads(request(prefix+"manifest.json"))
            if (manifest.get("snapshot_date")==asof and
                    (manifest.get("last_success") or {}).get("sec_company_tickers_exchange")==asof):
                return rev,manifest,prefix
        except (ValueError,KeyError,TypeError):
            pass
    raise ValueError("NO_EXACT_ASOF_SEC_SNAPSHOT")

def discover(asof,unknown,request=fetch):
    rev,manifest,prefix=select_exact_asof_commit(asof,request)
    raw=request(prefix+"sec_company_tickers_exchange.jsonl")
    result=classify(asof,unknown,manifest,raw)
    result["source_repository"]=UPSTREAM
    result["source_commit"]=rev
    result["snapshot_date"]=asof
    return result

def run():
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    asof=master["asof_et"];unknown=master.get("unknown_symbols") or []
    assert len(unknown)==master["unknown_count"]
    out={"schema":"XRAY_SEC_MIRROR_CIK_SHADOW_V1","asof_et":asof,
         "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
         "alpha_authority":False,"official_sec_sic_authority":False,"go":False,
         "approved_alpha_symbols":[],"status":"UNKNOWN_SOURCE",
         "ciK_discovered_count":0,"unknown_total":len(unknown),
         "ciK_discovery_only":{}}
    try:
        out.update(discover(asof,unknown))
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
    rev="a"*40
    commit_url="https://raw.githubusercontent.com/"+UPSTREAM+"/"+rev+"/"+SCOPE
    responses={"LIST":json.dumps([{"sha":rev}]).encode(),
               commit_url+"manifest.json":json.dumps(m).encode(),
               commit_url+"sec_company_tickers_exchange.jsonl":raw}
    fake=lambda url:responses["LIST"] if "/commits?" in url else responses[url]
    status=discover("2026-10-07",["TEST"],fake)
    assert status["status"]=="EXACT_ASOF_CIK_DISCOVERY_ONLY" and status["source_commit"]==rev
    try:discover("2026-10-06",["TEST"],fake)
    except ValueError:pass
    else:raise AssertionError("FUTURE_SNAPSHOT_ACCEPTED")
    print("XRAY_SEC_MIRROR_EXACT_ASOF_HISTORICAL_SELFTEST=PASS")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out")
    a=p.parse_args()
    if a.selftest:selftest()
    else:
        if not a.out:p.error("--out required")
        result=run()
        pathlib.Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print(json.dumps({k:result.get(k) for k in ("status","asof_et","unknown_total",
            "ciK_discovered_count","source_commit","failure_reason")}))
