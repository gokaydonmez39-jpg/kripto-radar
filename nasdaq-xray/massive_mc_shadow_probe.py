#!/usr/bin/env python3
"""Zero-alpha Massive MC reference shadow. Never promotes MC, R92, or a signal.

Only selected MC-UNKNOWN symbols are fetched. A known capped free plan exists
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
    print("XRAY_MASSIVE_MC_SHADOW_SELFTEST=PASS (ZERO_ALPHA)")

def run(args):
    history = json.loads((ROOT / "canonical_current_history.json").read_text())
    source = str(history.get("source_mc_artifact") or "")
    if not source.startswith("nasdaq-xray/canonical_mc_bridge_") or not source.endswith(".json"):
        raise RuntimeError("CURRENT_MC_AUTHORITY_PATH_UNSAFE")
    mc = json.loads((ROOT.parent / source).read_text())
    asof = str(mc.get("asof_et") or "")
    if asof != str(history.get("asof_et")) or not dt.date.fromisoformat(asof):
        raise RuntimeError("MC_HISTORY_ASOF_MISMATCH")
    unknown = sorted(set(mc.get("unknown_symbols") or []))
    if len(unknown) != int((mc.get("counts") or {}).get("MC_UNKNOWN", -1)):
        raise RuntimeError("MC_UNKNOWN_PARTITION_MISMATCH")
    if any(not x.isalpha() or x != x.upper() or len(x) > 7 for x in unknown):
        raise RuntimeError("INVALID_SYMBOL_IN_MC_UNKNOWN")
    limit = args.limit
    if limit < 1 or limit > MAX_REQUESTS_PER_INVOCATION:
        raise RuntimeError("HARD_FREE_PLAN_LIMIT_EXCEEDED")
    buckets = max(1, (len(unknown) + limit - 1) // limit)
    offset = int(args.offset) if args.offset != "auto" else (
        dt.datetime.now(dt.timezone.utc).hour % buckets) * limit
    if offset < 0 or offset >= max(1, len(unknown)):
        raise RuntimeError("INVALID_SHADOW_OFFSET")
    chosen = unknown[offset:offset + limit]
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
        "source_mc_artifact": source, "source_mc_unknown_count": len(unknown),
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
