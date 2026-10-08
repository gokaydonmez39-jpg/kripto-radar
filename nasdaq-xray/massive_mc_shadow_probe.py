#!/usr/bin/env python3
"""Zero-alpha Massive MC reference shadow. Never promotes MC, R92, or a signal.

Only selected exact-current PRICE/DV30 PASS symbols are sampled without requiring MC/HISTORY.
A known capped free plan exists
(5 calls/minute); this program never exceeds five requests in one invocation.
No key, scope, rate, identity or data failure is ever converted into PASS.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
SCHEMA = "XRAY_MASSIVE_MC_SHADOW_V1"
MC_FLOOR = 2_000_000_000
MAX_REQUESTS_PER_INVOCATION = 5
ALLOWED_EXCHANGE = {"XNAS", "XNGS", "XNMS", "XNCM"}

def as_number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return n if math.isfinite(n) and n > 0 else None

def provider_spac_suspect(row):
    """Conservative vendor-side veto; SEC-origin primary classification stays mandatory.

    Provider SIC alone cannot prove operating-company status. In particular,
    non-6770 SIC is not evidence of a completed SPAC business combination.
    """
    if not isinstance(row, dict):
        return None
    sic=str(row.get("sic_code") or "").strip()
    if sic=="6770":
        return "PROVIDER_SIC_6770_BLANK_CHECK"
    description=" ".join(str(row.get(k) or "") for k in
                         ("name","description","sic_description")).casefold()
    if re.search(r"\bblank[-\s]+check\b|\bspecial[-\s]+purpose[-\s]+acquisition\b", description):
        return "PROVIDER_TEXT_BLANK_CHECK"
    name=str(row.get("name") or "").casefold()
    if re.search(r"\bacquisition\s+(?:corp(?:oration)?\.?|co\.?|company|ltd\.?|limited)\b", name):
        return "PROVIDER_NAME_ACQUISITION_SUSPECT"
    return None

def classify(symbol, row):
    """Diagnostic classification only. No MC primary PASS is possible."""
    if not isinstance(row, dict) or row.get("ticker") != symbol:
        return {"state": "UNKNOWN", "reason": "TICKER_IDENTITY_UNPROVEN"}
    if row.get("active") is not True or row.get("market") != "stocks":
        return {"state": "UNKNOWN", "reason": "ACTIVE_US_STOCK_UNPROVEN"}
    if row.get("primary_exchange") not in ALLOWED_EXCHANGE:
        return {"state": "UNKNOWN", "reason": "NASDAQ_EXCHANGE_UNPROVEN"}
    if row.get("type") != "CS" or str(row.get("currency_name") or "").lower() != "usd":
        return {"state": "UNKNOWN", "reason": "COMMON_STOCK_USD_UNPROVEN"}
    cik = str(row.get("cik", "")).strip()
    if not cik.isdigit() or int(cik) <= 0:
        return {"state": "UNKNOWN", "reason": "CIK_UNPROVEN"}
    spac_reason = provider_spac_suspect(row)
    if spac_reason:
        return {"state": "UNKNOWN", "reason": "SPAC_SUSPECT_OFFICIAL_SEC_PROOF_REQUIRED",
                "shadow_subreason": spac_reason, "alpha_authority": False,
                "r92_eligible": False}
    mc = as_number(row.get("market_cap"))
    if mc is None:
        return {"state": "UNKNOWN", "reason": "MARKET_CAP_UNAVAILABLE"}
    return {
        "state": "SHADOW_OBSERVED_ABOVE_2B" if mc >= MC_FLOOR else "SHADOW_OBSERVED_BELOW_2B",
        "ticker": symbol, "cik": cik.zfill(10),
        "type": row["type"], "primary_exchange": row["primary_exchange"],
        "market_cap_usd": mc,
        "threshold_usd": MC_FLOOR,
        "source": "MASSIVE_REFERENCE_TICKER_OVERVIEW_PIT",
        "alpha_authority": False, "r92_eligible": False,
    }

def probe(symbol, asof, api_key):
    url = "https://api.massive.com/v3/reference/tickers/" + urllib.parse.quote(symbol, safe="")
    url += "?date=" + urllib.parse.quote(asof, safe="")
    request = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "NASDAQ-SWING-XRAY-MC-SHADOW/1.0",
        "Authorization": "Bearer " + api_key,
    })
    try:
        with urllib.request.urlopen(request, timeout=18) as r:
            doc = json.load(r)
    except urllib.error.HTTPError as e:
        return {"state": "UNKNOWN", "reason": "HTTP_" + str(e.code)}
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return {"state": "UNKNOWN", "reason": "TRANSPORT_" + type(e).__name__}
    if not isinstance(doc, dict) or doc.get("status") not in ("OK", "DELAYED", None):
        return {"state": "UNKNOWN", "reason": "PROVIDER_RESPONSE_NOT_OK"}
    return classify(symbol, doc.get("results"))

def selftest():
    fixture = {"ticker": "TEST", "market": "stocks", "active": True,
               "type": "CS", "primary_exchange": "XNAS",
               "currency_name": "usd", "cik": "0000123456", "market_cap": 2_300_000_000}
    assert classify("TEST", fixture)["state"] == "SHADOW_OBSERVED_ABOVE_2B"
    assert classify("WRONG", fixture)["state"] == "UNKNOWN"
    for key, value in [("primary_exchange", "XNYS"), ("type", "ETF"),
                       ("market_cap", 0), ("market_cap", float("nan")),
                       ("active", False), ("currency_name", None), ("cik", None)]:
        bad = dict(fixture, **{key: value})
        assert classify("TEST", bad)["state"] == "UNKNOWN"
    assert classify("TEST", dict(fixture, market_cap=1_900_000_000))["state"] == "SHADOW_OBSERVED_BELOW_2B"
    # ALIS-style provider conflict: company is described as a blank check
    # despite a non-6770 provider SIC. This MUST NEVER become an MC pass.
    alis=dict(fixture, name="Calisa Acquisition Corp",
              description="A blank check company", sic_code=7374,
              market_cap=2_500_000_000)
    assert provider_spac_suspect(alis) == "PROVIDER_TEXT_BLANK_CHECK"
    assert classify("TEST", alis)["state"] == "UNKNOWN"
    bccq=dict(fixture, name="Bleichroeder Acquisition Corp III",
              description="Blank check company", sic_code=6770)
    assert provider_spac_suspect(bccq) == "PROVIDER_SIC_6770_BLANK_CHECK"
    assert classify("TEST", bccq)["state"] == "UNKNOWN"
    nonblank=dict(fixture, name="Operating Analytics Inc",
                  description="Commercial software business", sic_code=7372)
    assert classify("TEST", nonblank)["state"] == "SHADOW_OBSERVED_ABOVE_2B"
    suspicious_name=dict(fixture, name="Example Acquisition Corp")
    assert classify("TEST", suspicious_name)["state"] == "UNKNOWN"
    assert MAX_REQUESTS_PER_INVOCATION == 5
    from copy import deepcopy
    master={"asof_et":"2026-10-08","execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"queue_hash":"Q","queue_total":2,
        "pass_symbols":["TEST","TWO"]}
    price={"asof_et":"2026-10-08","execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"source_master_queue_hash":"Q",
        "source_master_count":2,"pass_symbols":["TEST"],"pass_count":1,
        "blocked_symbols":["TWO"],"results":{"TEST":{"status":"PASS_PRICE_DV30"},
        "TWO":{"status":"BLOCK_CURRENT_RUN"}}}
    assert select_current_price_scope(master,price)==("2026-10-08",["TEST"])
    for fn in (
        lambda m,p:p.update(asof_et="2026-10-07"),
        lambda m,p:p.update(pass_symbols=["TWO"]),
        lambda m,p:p.update(pass_count=2),
        lambda m,p:p.update(source_master_queue_hash="WRONG"),
        lambda m,p:p["results"]["TEST"].update(status="MC_UNKNOWN"),
        lambda m,p:m.update(queue_total=3)):
        mm,pp=deepcopy(master),deepcopy(price)
        fn(mm,pp)
        try:select_current_price_scope(mm,pp)
        except RuntimeError:pass
        else:raise AssertionError("INVALID_SOURCE_ACCEPTED")
    clock=dt.datetime(2026,10,8,22,tzinfo=dt.timezone.utc)
    assert choose_offset(514,5,"auto",clock)==(
        (clock.date().toordinal()*24+clock.hour)%103)*5
    assert choose_offset(514,5,"5")==5
    for invalid in ("-1","514","bad"):
        try:choose_offset(514,5,invalid)
        except RuntimeError:pass
        else:raise AssertionError("INVALID_OFFSET_ACCEPTED")
    print("XRAY_MASSIVE_MC_SHADOW_SELFTEST=PASS_PRICE_SCOPE_6_NEGATIVES_NO_ALPHA")

def select_current_price_scope(master: dict, price: dict) -> tuple[str, list[str]]:
    """Exact PRICE PASS sample; no MC/HISTORY dependency and no alpha effect."""
    asof = str(price.get("asof_et") or "")
    try:
        if dt.date.fromisoformat(asof).isoformat()!=asof:
            raise ValueError("date mismatch")
    except ValueError as exc:
        raise RuntimeError("PRICE_ASOF_INVALID") from exc
    master_symbols=set(master.get("pass_symbols") or [])
    scope=list(price.get("pass_symbols") or [])
    if not (
        master.get("asof_et")==asof
        and master.get("execution")=="NONE" and master.get("real_money")=="NO-GO"
        and price.get("execution")=="NONE" and price.get("real_money")=="NO-GO"
        and master.get("unknown_never_pass") is True
        and price.get("unknown_never_pass") is True
        and master.get("queue_hash")==price.get("source_master_queue_hash")
        and master.get("queue_total")==price.get("source_master_count")
        and master_symbols==set(price.get("results") or {})
        and len(master_symbols)==int(master.get("queue_total") or -1)
        and len(scope)>0 and len(scope)==len(set(scope))
        and len(scope)==int(price.get("pass_count") or -1)
        and set(scope).issubset(master_symbols)
        and set(scope).isdisjoint(price.get("blocked_symbols") or [])
        and all((price.get("results") or {}).get(x,{}).get("status")=="PASS_PRICE_DV30"
                for x in scope)
    ):
        raise RuntimeError("CURRENT_PRICE_PASS_AUTHORITY_INVALID_FAIL_CLOSED")
    if any(not re.fullmatch(r"[A-Z]{1,7}",x) for x in scope):
        raise RuntimeError("INVALID_SYMBOL_IN_PRICE_PASS")
    return asof,sorted(scope)

def choose_offset(n:int,limit:int,offset:str,now=None) -> int:
    if limit<1 or limit>MAX_REQUESTS_PER_INVOCATION:
        raise RuntimeError("HARD_FREE_PLAN_LIMIT_EXCEEDED")
    if n<=0:raise RuntimeError("EMPTY_RESEARCH_SCOPE")
    buckets=(n+limit-1)//limit
    if offset=="auto":
        now=now or dt.datetime.now(dt.timezone.utc)
        pos=((now.date().toordinal()*24+now.hour)%buckets)*limit
    else:
        try:pos=int(offset)
        except (ValueError,TypeError) as exc:
            raise RuntimeError("INVALID_SHADOW_OFFSET") from exc
    if pos<0 or pos>=n:raise RuntimeError("INVALID_SHADOW_OFFSET")
    return pos

def run(args):
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    asof,scope=select_current_price_scope(master,price)
    limit=args.limit
    offset=choose_offset(len(scope),limit,args.offset)
    chosen=scope[offset:offset+limit]
    key = os.getenv("XRAY_MASSIVE_API_KEY", "").strip()
    records = {}
    if not key:
        status = "BLOCKED_NO_RUNTIME_KEY"
        records = {sym: {"state": "UNKNOWN", "reason": "NO_RUNTIME_KEY"} for sym in chosen}
    else:
        status = "SHADOW_PROBED_NON_ALPHA"
        for sym in chosen:
            records[sym] = probe(sym, asof, key)
    output = {
        "schema": SCHEMA, "asof_et": asof,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "execution": "NONE", "real_money": "NO-GO",
        "authority": "NON_ALPHA_SHADOW_ONLY", "unknown_never_pass": True,
        "policy_unchanged": "C4.17", "mc_primary_pass_created": False,
        "candidate_created": False, "r92_created": False,
        "source_price_artifact": "nasdaq-xray/canonical_current_price_dv30.json",
        "source_price_pass_count": len(scope),
        "source_epoch_exact": True,
        "mc_history_not_required_for_price_sample": True,
        "free_plan_5_calls_per_minute": True, "requested_count": len(chosen),
        "status": status, "offset": offset, "records": records
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, sort_keys=True, indent=2) + "\n")
    print("XRAY_MASSIVE_MC_SHADOW=" + status +
          " observed=" + str(sum(str(v.get("state")).startswith("SHADOW_") for v in records.values())) +
          " requested=" + str(len(chosen)))
    return 0

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--offset", default="auto")
    p.add_argument("--out", default="/tmp/xray_massive_mc_shadow.json")
    args = p.parse_args()
    if args.selftest:
        selftest()
        return 0
    return run(args)

if __name__ == "__main__":
    sys.exit(main())
