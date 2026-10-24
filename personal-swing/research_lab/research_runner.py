#!/usr/bin/env python3
"""XRAY research-only: registry QA, offline bar comparison, GH source freshness.

Never imports a third-party research package, fetches vendor price data, accesses
broker secrets, changes AL eligibility, touches private Sheets or emits alerts.
A public GitHub repo metadata check is permitted only in explicit monitor mode.
"""
import argparse
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "unified_research_88.json"
GROUP_COUNTS = {"REFERENCE_49":49, "EMERGING_13":13, "QUANT_GITHUB":12,
                "MCP_GITHUB":10, "DATA_PROVIDER":4}
DENIAL_FIELDS = ("production_enabled", "may_issue_al", "may_write_sheet",
                 "may_emit_alert", "may_place_order", "may_fetch_unapproved_api")
SCOPES = {"IEX", "US_CONSOLIDATED", "OTHER", "UNKNOWN"}
BASES = {"RAW", "SPLIT_ADJUSTED", "SPLIT_DIVIDEND_ADJUSTED", "UNKNOWN"}

def registry_check(doc):
    if not isinstance(doc, dict) or doc.get("schema") != "XRAY_RESEARCH_UNIFIED_88_V1":
        raise ValueError("INVALID_REGISTRY_SCHEMA")
    entries = doc.get("entries")
    if not isinstance(entries,list) or len(entries) != 88:
        raise ValueError("REGISTRY_EXPECTS_88")
    counts = {k:0 for k in GROUP_COUNTS}
    ids = set()
    for item in entries:
        if not isinstance(item,dict) or not isinstance(item.get("key"),str):
            raise ValueError("INVALID_SOURCE")
        if item["key"] in ids:
            raise ValueError("DUPLICATE_SOURCE_KEY")
        ids.add(item["key"])
        if item.get("group") not in counts:
            raise ValueError("UNRECOGNIZED_GROUP")
        counts[item["group"]] += 1
        if any(item.get(k) is not False for k in DENIAL_FIELDS):
            raise ValueError("UNAUTHORIZED_SOURCE_SIDE_EFFECT")
        url = item.get("url")
        if not isinstance(url,str) or not url.startswith("https://"):
            raise ValueError("NO_CANONICAL_HTTPS_SOURCE_URL")
    if counts != GROUP_COUNTS:
        raise ValueError("REGISTRY_PARTITIONS_DRIFT")
    for k,v in doc.get("global_prohibitions",{}).items():
        if v is not False:
            raise ValueError("GLOBAL_RESEARCH_AUTHORITY_VIOLATION")
    if not doc.get("global_prohibitions"):
        raise ValueError("MISSING_GLOBAL_PROHIBITIONS")
    if not any(x.get("key") == "data:massive" for x in entries):
        raise ValueError("MASSIVE_CANDIDATE_MISSING")
    for x in entries:
        if x.get("key") == "data:massive" and x.get("status") != "READ_ONLY_EXTERNAL_CONNECTOR_SAMPLED":
            raise ValueError("MASSIVE_STATUS_MISREPRESENTED")
    return {
        "registry": "VALID_RESEARCH_ONLY", "unique": len(ids), "groups":counts,
        "live_production_sources_authorized":0, "external_vendor_calls":0
    }

def read_registry(path=CATALOG):
    doc=json.loads(Path(path).read_text(encoding="utf-8"))
    registry_check(doc)
    return doc

def _utc(value):
    if not isinstance(value,str):
        raise ValueError("MISSING_UTC")
    try:
        t=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_UTC") from exc
    if t.tzinfo is None or t.utcoffset().total_seconds()!=0:
        raise ValueError("NON_UTC_TIMESTAMP")
    return t

def _number(v, allow_zero=False):
    if type(v) not in (int,float) or not math.isfinite(v):
        raise ValueError("INVALID_PRICE_OR_VOLUME")
    if v < 0 or (not allow_zero and v == 0):
        raise ValueError("INVALID_PRICE_OR_VOLUME")
    return float(v)

def _validate_series(obj, ticker, cutoff, asof):
    if not isinstance(obj,dict) or obj.get("ticker")!=ticker:
        raise ValueError("TICKER_OR_CLASS_MISMATCH")
    if not isinstance(obj.get("provider"),str) or not obj["provider"]:
        raise ValueError("MISSING_PROVIDER")
    if obj.get("scope") not in SCOPES or obj.get("basis") not in BASES:
        raise ValueError("VENUE_OR_ADJUSTMENT_BASIS_UNVERIFIED")
    if obj.get("attested_data_rights") is not True:
        raise ValueError("DATA_RIGHTS_ATTESTATION_MISSING")
    if not isinstance(obj.get("bars"),list) or not obj["bars"]:
        raise ValueError("EMPTY_BARS")
    seen=set()
    observed=[]
    for b in obj["bars"]:
        if not isinstance(b,dict) or not isinstance(b.get("session"),str):
            raise ValueError("INVALID_BAR")
        try:
            day=date.fromisoformat(b["session"])
        except ValueError as exc:
            raise ValueError("INVALID_BAR_SESSION") from exc
        if day.isoformat()!=b["session"] or day > asof:
            raise ValueError("FUTURE_OR_NONCANONICAL_SESSION")
        if b["session"] in seen:
            raise ValueError("DUPLICATED_SESSION")
        seen.add(b["session"])
        if _utc(b.get("known_at_utc"))>cutoff:
            raise ValueError("LOOKAHEAD_BAR_UNAVAILABLE")
        o,h,l,c=[_number(b.get(k)) for k in ("open","high","low","close")]
        v=_number(b.get("volume"),allow_zero=True)
        if h < max(o,c,l) or l > min(o,c,h):
            raise ValueError("INVALID_OHLC_GEOMETRY")
        observed.append({**b,"open":o,"high":h,"low":l,"close":c,"volume":v})
    if [x["session"] for x in observed]!=sorted(seen):
        raise ValueError("NONMONOTONIC_SESSION_ORDER")
    return {x["session"]:x for x in observed}

def compare_pair(payload):
    """Compare two local, externally authorized bar payloads; NEVER choose AL."""
    if not isinstance(payload,dict) or payload.get("schema")!="XRAY_RESEARCH_BAR_PAIR_V1":
        raise ValueError("INVALID_COMPARISON_SCHEMA")
    ticker=payload.get("ticker")
    if not isinstance(ticker,str) or not re.fullmatch(r"[A-Z][A-Z0-9.]{0,14}",ticker):
        raise ValueError("INVALID_TICKER")
    try:
        asof=date.fromisoformat(payload["asof_et"])
    except (ValueError,KeyError,TypeError) as exc:
        raise ValueError("INVALID_ASOF") from exc
    if asof.isoformat()!=payload["asof_et"]:
        raise ValueError("INVALID_ASOF")
    cutoff=_utc(payload.get("cutoff_utc"))
    if cutoff.date() < asof:
        raise ValueError("CUTOFF_PRECEDES_ASOF")
    left,right=(payload.get("left"),payload.get("right"))
    L=_validate_series(left,ticker,cutoff,asof)
    R=_validate_series(right,ticker,cutoff,asof)
    if left["provider"] == right["provider"]:
        raise ValueError("REQUIRES_TWO_DIFFERENT_SOURCES")
    overlap=sorted(set(L)&set(R))
    if not overlap or overlap[-1] != asof.isoformat():
        raise ValueError("MISSING_MATCHED_FINAL_SESSION")
    if set(L)!=set(R):
        raise ValueError("UNMATCHED_SESSIONS_FAIL_CLOSED")
    same_basis=(left["scope"]==right["scope"] and left["basis"]==right["basis"]
                and left["scope"] not in ("OTHER","UNKNOWN")
                and left["basis"]!="UNKNOWN")
    samples=[]
    for day in overlap:
        a,b=L[day],R[day]
        diff=round(b["close"]-a["close"],6)
        samples.append({"session":day,"delta_close_usd":diff,
                        "absolute_pct":round(100*abs(diff)/a["close"],5),
                        "volume_ratio_diagnostic_only":round(b["volume"]/a["volume"],4)
                        if a["volume"]>0 else None})
    return {
        "schema":"XRAY_RESEARCH_COMPARE_ONLY_V1", "ticker":ticker,
        "n_common_sessions":len(overlap),
        "comparison":("SAME_CONTRACT_CHECK_ONLY" if same_basis
                     else "DIFFERENT_VENUE_OR_ADJUSTMENT_NOT_INTERCHANGEABLE"),
        "closing_differences":samples,
        "source_rights_externally_attested_not_verified_by_tool":True,
        "market_truth_authority":False, "may_generate_al":False,
        "may_change_stops":False,"may_emit_alert":False,
        "may_write_private_sheet":False,"alpha_improvement_proven":False
    }

def github_monitor(registry, *, opener=None, token=None, max_items=22):
    """GET public GitHub repo metadata only; NEVER execute/import fetched source.
    
    Performs no price API requests, GitHub writes or user-alert side effects.
    """
    watch=[s for s in registry["entries"] if s["group"] in ("QUANT_GITHUB","MCP_GITHUB")]
    if max_items != 22 or len(watch) != 22:
        raise ValueError("WATCH_SCOPE_UNEXPECTED")
    if opener is None:
        opener=urlopen
    results=[]
    for source in watch:
        name=source["display"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",name):
            raise ValueError("BAD_GITHUB_REPO_LOCATOR")
        url="https://api.github.com/repos/"+name
        hdr={"Accept":"application/vnd.github+json","User-Agent":"XRAY-public-source-audit/1"}
        if token:
            hdr["Authorization"]="Bearer "+token
        req=Request(url,headers=hdr,method="GET")
        try:
            with opener(req,timeout=12) as res:
                obj=json.load(res)
            status=("AVAILABLE" if obj.get("full_name","").lower()==name.lower()
                    and obj.get("archived") is False
                    else "UNKNOWN_OR_ARCHIVED")
            results.append({"repo":name,"status":status,
                            "pushed_at":obj.get("pushed_at"),
                            "default_branch":obj.get("default_branch")})
        except (HTTPError,URLError,TimeoutError,ValueError,KeyError,OSError) as e:
            results.append({"repo":name,"status":"UNKNOWN_UNREACHABLE",
                            "error_type":type(e).__name__})
    available=sum(x["status"]=="AVAILABLE" for x in results)
    return {"schema":"XRAY_GITHUB_METADATA_WATCH_V1",
            "sources_checked":len(results),
            "available_count":available,
            "unknown_or_archived_count":len(results)-available,
            "market_vendor_api_integrated_count":0,
            "research_models_executed_count":0,
            "github_public_only":True,"market_data_fetched":False,
            "source_code_executed":False,"production_changed":False,
            "result":results}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=["catalogue","pair","github-watch"],default="catalogue")
    p.add_argument("--input",help="PRIVATE local file; never commit real OHLCV")
    p.add_argument("--catalogue",default=str(CATALOG))
    p.add_argument("--require-all-available",action="store_true",
                   help="For GitHub metadata mode, fail when one or more of the 22 repos is unavailable")
    args=p.parse_args(argv)
    registry=read_registry(args.catalogue)
    if args.mode=="catalogue":
        outcome=registry_check(registry)
    elif args.mode=="pair":
        if not args.input:
            raise SystemExit("--input required for private comparison")
        outcome=compare_pair(json.loads(Path(args.input).read_text(encoding="utf-8")))
    else:
        outcome=github_monitor(registry,token=os.environ.get("GITHUB_TOKEN"))
    print(json.dumps(outcome,ensure_ascii=False,sort_keys=True))
    if args.require_all_available:
        if args.mode != "github-watch":
            raise SystemExit("REQUIRE_ALL_ONLY_GITHUB_WATCH")
        if outcome["available_count"] != 22:
            print("XRAY_RESEARCH_SOURCE_HEALTH=DEGRADED_GITHUB_METADATA_ONLY")
            raise SystemExit(3)
        print("XRAY_RESEARCH_SOURCE_HEALTH=PASS_22_PUBLIC_GITHUB_METADATA_ONLY")

if __name__=="__main__":
    main()
