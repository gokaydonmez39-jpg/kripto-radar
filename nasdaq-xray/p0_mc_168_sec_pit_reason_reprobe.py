#!/usr/bin/env python3
"""Research-only SEC PIT root-cause re-probe of the frozen 168/514 MC UNKNOWN set.

Uses original GitHub Actions union artifact + exact 2026-10-09 canonical
PRICE/MASTER blobs. A *new* SEC read is not a retroactive 2026-10-09
market-cap, share-class, listing-continuity or vendor-entitlement witness.
No shares, prices, raw filings, accession numbers or vendor payloads are
persisted. NEVER modifies C4.17 PRIMARY, HISTORY, R92, G9 or ACCOUNT.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import time
from pathlib import Path

from sec_official_free_mc_transport_probe import get_json, select_shares, valid_operator_contact
from sec_free_mc_multisymbol_pit_audit import SEC_MAP, map_ciks, root_cause_class

ASOF = "2026-10-09"
PRICE_SHA = "6f3f68fff0897d68f200ad3621c51a5071494714"
MASTER_SHA = "828c21436a836b69fe5084387e1c54446c7b5075"
SOURCE_ARTIFACT_ID = 11718354595
SOURCE_WORKFLOW_RUN = 38183357135
UNKNOWN = "UNKNOWN_SEC_DIMENSIONAL_CLASS_OR_PIT_SHARES"
SHADOW = "SHADOW_SEC_PIT_AND_SIP_CLOSE_ARITHMETIC_VERIFIED_CLASS_CA_UNPROVEN"
SCHEMA = "XRAY_P0_MC_168_SEC_PIT_ROOT_CAUSE_REPROBE_V1"
SEC_REASON_CODES = frozenset((
    "NASDAQ_ASOF_NOT_TRADING_SESSION", "NASDAQ_SESSION_CALENDAR_UNAVAILABLE",
    "NASDAQ_SESSION_CLOSE_TIMEZONE_MISSING", "NASDAQ_SESSION_CLOSE_DATE_MISMATCH",
    "SEC_COMPANYFACTS_CIK_MISMATCH", "SEC_SUBMISSIONS_CIK_MISMATCH",
    "SEC_SUBMISSIONS_LIST_LENGTH_MISMATCH", "SEC_SUBMISSIONS_CONFLICTING_ACCESSION",
    "NO_DEI_BUT_GAAP_SHARES_AVAILABLE_CLASS_UNRESOLVED",
    "NO_SEC_DEI_OR_GAAP_SHARES_FACT",
    "SEC_FACT_ACCESSION_NOT_VERIFIED_IN_RECENT_SUBMISSIONS",
    "SEC_ACCEPTANCE_CLOCK_AMBIGUOUS_PIT", "SEC_FACT_ACCEPTED_AFTER_RTH_CLOSE",
    "SEC_SHARES_STALE_OR_FUTURE_OBSERVATION", "SEC_FACT_MALFORMED_OR_INVALID",
    "NO_FRESH_ACCEPTANCE_BOUND_SINGLE_ENTITY_SHARES",
    "SEC_CONFLICTING_SAME_VINTAGE_SHARES", "SEC_HTTP_404",
    "SEC_TRANSPORT_UNAVAILABLE", "SEC_JSON_INVALID", "SEC_PAYLOAD_TOO_LARGE",
    "SEC_NOT_200", "SEC_RESPONSE_NOT_OBJECT", "SEC_HTTP_429", "SEC_HTTP_403",
    "SEC_CURRENT_CIK_ROUTE_MISSING", "SEC_FAIR_ACCESS_STOP",
    "SEC_SHARES_NOW_OBSERVABLE_PRIOR_UNKNOWN_UNCHANGED",
    "SEC_REASON_UNCLASSIFIED", "SEC_READ_ERROR_UNCLASSIFIED",
))
def require(condition, reason):
    if not condition:
        raise ValueError("XRAY_MC_168_SEC_REASON:" + reason)

def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def symbol_sha(symbols):
    return hashlib.sha256(("\n".join(symbols) + "\n").encode()).hexdigest()

def safe_reason(code):
    return code if type(code) is str and code in SEC_REASON_CODES else "SEC_REASON_UNCLASSIFIED"

def original_scope(union, price_bytes, master_bytes):
    price = json.loads(price_bytes)
    master = json.loads(master_bytes)
    symbols = price.get("pass_symbols")
    require(git_blob(price_bytes) == PRICE_SHA and
            git_blob(master_bytes) == MASTER_SHA, "FROZEN_CANONICAL_BLOB_DRIFT")
    require(price.get("asof_et") == master.get("asof_et") == ASOF
            and type(symbols) is list and symbols == sorted(set(symbols))
            and len(symbols) == price.get("pass_count") == 514
            and symbol_sha(symbols) == price.get("pass_hash")
            and set(symbols).issubset(set(master.get("pass_symbols") or [])),
            "FROZEN_CANONICAL_SET_DRIFT")
    require(all(x.get("execution") == "NONE" and
                x.get("real_money") == "NO-GO" and
                x.get("unknown_never_pass") is True for x in (price, master)),
            "CANONICAL_SAFETY_DRIFT")
    rows = union.get("symbol_classifications")
    require(union.get("schema") == "XRAY_P0_SEC_ALPACA_514_MC_FOUR_ARTIFACT_JOIN_V1"
            and union.get("asof_et") == ASOF
            and union.get("stock_scope") == union.get("measured_symbol_count") == 514
            and union.get("C417_PRIMARY_MC_created") == 0
            and union.get("AL_R92_created") is False
            and union.get("GO") is False
            and union.get("price_git_blob_sha") == PRICE_SHA
            and union.get("master_git_blob_sha") == MASTER_SHA
            and type(rows) is dict and set(rows) == set(symbols),
            "SOURCE_UNION_AUTHORITY_OR_SET_DRIFT")
    require(all(type(v) is dict and v.get("C417_PRIMARY_MC") is False
                and v.get("status") in (UNKNOWN, SHADOW) for v in rows.values()),
            "SHADOW_OR_PRIMARY_MUTATION")
    targets = sorted(k for k,v in rows.items() if v["status"] == UNKNOWN)
    require(len(targets) == 168 and
            sum(v["status"] == SHADOW for v in rows.values()) == 346,
            "SOURCE_168_346_PARTITION_DRIFT")
    return targets

def probe(targets, routes, fetch, classify, pause=lambda: None):
    """SEC-only diagnosis. Failures and later-vintage discoveries never promote MC."""
    require(targets == sorted(set(targets)) and len(targets) == 168, "TARGET_SET_DRIFT")
    rows = {}
    fair_access_stop = False
    attempted = 0
    for symbol in targets:
        cik = routes.get(symbol)
        if fair_access_stop:
            reason = "SEC_FAIR_ACCESS_STOP"
            status = "UNKNOWN_NOT_ATTEMPTED_SEC_FAIR_ACCESS"
        elif not (type(cik) is str and len(cik) == 10 and cik.isdigit()):
            reason = "SEC_CURRENT_CIK_ROUTE_MISSING"
            status = "UNKNOWN_EXACT_CURRENT_CIK_ROUTE"
        else:
            attempted += 1
            try:
                facts = fetch("https://data.sec.gov/api/xbrl/companyfacts/CIK" + cik + ".json")
                pause()
                subs = fetch("https://data.sec.gov/submissions/CIK" + cik + ".json")
                observation = classify(facts, subs, ASOF, expected_cik=cik)
                if observation.get("status") == "SHADOW_SHARES_VINTAGE_ONLY":
                    status = "REPROBE_SEC_SHARES_VINTAGE_ONLY_NOT_PRIMARY"
                    reason = "SEC_SHARES_NOW_OBSERVABLE_PRIOR_UNKNOWN_UNCHANGED"
                else:
                    status = "UNKNOWN_SEC_PIT_OR_CLASS"
                    reason = safe_reason(observation.get("reason"))
            except (ValueError, RuntimeError, TimeoutError, TypeError, KeyError) as exc:
                raw = str(exc)
                reason = safe_reason(raw)
                if reason == "SEC_REASON_UNCLASSIFIED":
                    reason = "SEC_READ_ERROR_UNCLASSIFIED"
                status = "UNKNOWN_SEC_READ_FAILURE"
                if reason in ("SEC_HTTP_403", "SEC_HTTP_429"):
                    fair_access_stop = True
            pause()
        remediation = root_cause_class(
            "SHADOW_SHARES_VINTAGE_ONLY" if status.startswith("REPROBE_") else
            "UNKNOWN_SEC_TRANSPORT" if status == "UNKNOWN_SEC_READ_FAILURE" else
            "UNKNOWN", reason, symbol)
        rows[symbol] = {
            "original_20261009_MC_status": UNKNOWN,
            "sec_reprobe_status": status,
            "sec_reprobe_reason": reason,
            "remediation_route": remediation,
            "C417_PRIMARY_MC": False,
            "historical_listing_class_PIT_confirmed": False,
            "history_CA_release_confirmed": False,
        }
    require(set(rows) == set(targets) and len(rows) == 168
            and all(x["C417_PRIMARY_MC"] is False and
                    x["original_20261009_MC_status"] == UNKNOWN for x in rows.values()),
            "INCOMPLETE_OR_PROMOTED_PARTITION")
    statuses = collections.Counter(x["sec_reprobe_status"] for x in rows.values())
    reasons = collections.Counter(x["sec_reprobe_reason"] for x in rows.values())
    return {
        "schema": SCHEMA, "asof_et": ASOF,
        "source_union_run_id": SOURCE_WORKFLOW_RUN,
        "source_union_artifact_id": SOURCE_ARTIFACT_ID,
        "price_git_blob_sha": PRICE_SHA, "master_git_blob_sha": MASTER_SHA,
        "original_full_price_count": 514, "original_shadow_count": 346,
        "original_unknown_count": 168, "unknown_exact_set_sha256": symbol_sha(targets),
        "scope_exact": True, "attempted_sec_ticker_count": attempted,
        "fair_access_stop": fair_access_stop,
        "sec_reprobe_status_counts": dict(sorted(statuses.items())),
        "sec_reprobe_reason_counts": dict(sorted(reasons.items())),
        "rows": rows,
        "sec_route_current_not_historical_PIT": True,
        "later_SEC_reprobe_never_retroactively_proves_20261009": True,
        "issuer_shares_not_traded_class_market_cap": True,
        "historical_listing_class_CA_independent_mc_unverified": True,
        "raw_shares_prices_filings_accessions_vendor_OHLCV_persisted": False,
        "C417_PRIMARY_MC_created": 0,
        "canonical_HISTORY_PASS_created": 0,
        "R92_created": False, "GO": False,
        "execution": "NONE", "real_money": "NO-GO",
        "unknown_never_pass": True,
    }

def selftest():
    # Negative fixtures deliberately synthetic and confined to selftest.
    names = [f"TEST{i:04d}" for i in range(168)]
    routes = {s: f"{i+100:010d}" for i,s in enumerate(names)}
    def f(url):
        return {"cik": 100}
    def c(facts, subs, asof, expected_cik):
        return {"status": "UNKNOWN", "reason": "NO_SEC_DEI_OR_GAAP_SHARES_FACT"}
    good = probe(names, routes, f, c)
    require(len(good["rows"]) == 168 and good["attempted_sec_ticker_count"] == 168
            and good["C417_PRIMARY_MC_created"] == 0
            and set(x["sec_reprobe_reason"] for x in good["rows"].values())
                == {"NO_SEC_DEI_OR_GAAP_SHARES_FACT"},
            "POSITIVE_UNKNOWN_REASONS")
    shifted = dict(routes)
    shifted.pop(names[0])
    alt = probe(names, shifted, f, c)
    require(alt["rows"][names[0]]["sec_reprobe_reason"] ==
            "SEC_CURRENT_CIK_ROUTE_MISSING", "MISSING_ID_NEVER_PROMOTED")
    def denied(url):
        raise ValueError("SEC_HTTP_429")
    halted = probe(names, routes, denied, c)
    require(halted["attempted_sec_ticker_count"] == 1
            and halted["sec_reprobe_reason_counts"]["SEC_FAIR_ACCESS_STOP"] == 167,
            "FAIR_ACCESS_MUST_STOP")
    def sensitive(*args, **kwargs):
        return {"status":"UNKNOWN", "reason":"token:PRIVATE_SECRET"}
    safe = probe(names, routes, f, sensitive)
    require(set(safe["sec_reprobe_reason_counts"]) ==
            {"SEC_REASON_UNCLASSIFIED"}, "PROPRIETARY_STRING_LEAK")
    def latest(*args, **kwargs):
        return {"status":"SHADOW_SHARES_VINTAGE_ONLY"}
    late = probe(names, routes, f, latest)
    require(late["C417_PRIMARY_MC_created"] == 0 and
            set(v["original_20261009_MC_status"] for v in late["rows"].values())
                == {UNKNOWN}, "RETROACTIVE_SHADOW_PROMOTION")
    for bad in (names[:-1], names + [names[0]], list(reversed(names))):
        try:
            probe(bad, routes, f, c)
        except ValueError:
            pass
        else:
            raise AssertionError("SCOPE_FALSE_ACCEPT")
    print("XRAY_MC_168_SEC_REASON_SELFTEST=PASS_REAL_CODE_2_POSITIVE_6_NEGATIVE_NO_PRIMARY")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--union", type=Path)
    p.add_argument("--price", type=Path, default=Path(__file__).resolve().parent / "canonical_current_price_dv30.json")
    p.add_argument("--master", type=Path, default=Path(__file__).resolve().parent / "canonical_current_master_manifest.json")
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if args.selftest:
        return selftest()
    require(args.union is not None and args.out is not None, "REAL_SOURCE_INPUTS_REQUIRED")
    original = json.loads(args.union.read_bytes())
    targets = original_scope(original, args.price.read_bytes(), args.master.read_bytes())
    import os
    ua = os.environ.get("XRAY_SEC_USER_AGENT", "")
    require(valid_operator_contact(ua), "SEC_OFFICIAL_OPERATOR_REQUIRED")
    route_data = get_json(SEC_MAP, ua)
    routes = map_ciks(route_data)
    last = [0.0]
    def pause():
        elapsed = time.monotonic() - last[0]
        if last[0] and elapsed < 0.65:
            time.sleep(0.65 - elapsed)
        last[0] = time.monotonic()
    # A fair SEC pacing contract, no proxy rotation or block bypass.
    out = probe(targets, routes, lambda url: get_json(url, ua),
                select_shares, pause)
    out["source_union_json_sha256"] = hashlib.sha256(args.union.read_bytes()).hexdigest()
    out["source_code_role"] = "OFFICIAL_SEC_RESEARCH_DIAGNOSIS_NOT_PRIMARY"
    args.out.write_text(json.dumps(out, sort_keys=True, indent=2) + "\n")
    print("XRAY_168_SEC_REPROBE_COUNTS=" + json.dumps(out["sec_reprobe_reason_counts"], sort_keys=True))
    print("XRAY_168_SEC_REPROBE_NO_PRIMARY=true")

if __name__ == "__main__":
    main()
