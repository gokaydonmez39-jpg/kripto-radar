#!/usr/bin/env python3
"""Fail-closed verification of immutable SIP/Rallies/Longbridge settlement evidence.
No network requests, no broker/account access, no price/MC reclassification.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
ET = ZoneInfo("America/New_York")
POLICY = "68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def blob(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\\0" + raw).hexdigest()


def amount(x) -> float:
    if isinstance(x, bool):
        raise ValueError("BOOLEAN_MARKET_NUMBER")
    y = float(x)
    if not math.isfinite(y):
        raise ValueError("NONFINITE_MARKET_NUMBER")
    return y


def verify_proof(w: dict) -> None:
    if not (
        w.get("schema") == "XRAY_RESOLVER_EPOCH_RESULT_V1"
        and w.get("status") == "COMMITTED"
        and w.get("bridge_role") == "CURRENT_RESIDUAL_REQUEST_AUTHORITY"
        and w.get("execution") == "NONE"
        and w.get("real_money") == "NO-GO"
        and w.get("unknown_never_pass") is True
        and w.get("compiled_policy_version") == "C4.17"
        and w.get("compiled_policy_hash") == POLICY
        and w.get("settlement_status") == "PASS"
        and w.get("settlement_required") is True
        and str(w.get("settlement_method") or "").startswith("ALPACA_HISTORICAL_SIP_")
    ):
        raise ValueError("SIP_WITNESS_POLICY_CONTRACT_FAILURE")
    names = w.get("settlement_symbols")
    if not (isinstance(names, list) and len(names) == 3
            and len(set(names)) == 3 and {"AAPL", "NVDA"}.issubset(names)):
        raise ValueError("SIP_SETTLEMENT_SYMBOL_SCOPE")
    evidence = w.get("settlement_evidence") or {}
    if set(evidence) != set(names):
        raise ValueError("SIP_SETTLEMENT_EVIDENCE_SET")
    asof = w.get("asof_et")
    if not isinstance(asof, str):
        raise ValueError("SIP_ASOF_MISSING")
    for sym in names:
        record = evidence[sym]
        a = record.get("alpaca_sip") or {}
        r = record.get("rallies") or {}
        l = record.get("longbridge") or {}
        if (a.get("feed") != "SIP" or a.get("timeframe") != "1Day"
                or r.get("date") != asof or l.get("trade_status") != "Normal"
                or record.get("ohlc_match_0_01") is not True
                or record.get("sip_volume_authority") is not True):
            raise ValueError("SIP_SOURCE_SEMANTIC_FAILURE:" + sym)
        session = datetime.fromisoformat(str(a.get("timestamp")))
        quote = datetime.fromisoformat(str(l.get("timestamp")).replace("Z", "+00:00"))
        if not (session.tzinfo and quote.tzinfo
                and session.astimezone(ET).date().isoformat() == asof
                and session.astimezone(ET).time() == time(0, 0)
                and quote.astimezone(ET).date().isoformat() == asof
                and time(16, 0) <= quote.astimezone(ET).time() <= time(16, 2)):
            raise ValueError("SIP_SESSION_TIMESTAMP_MISMATCH:" + sym)
        for field in ("open", "high", "low", "close"):
            sip, rallies, longbridge = (amount(o[field]) for o in (a, r, l))
            if max(abs(sip - rallies), abs(sip - longbridge)) > 0.010000001:
                raise ValueError("SIP_OHLC_CROSSCHECK_FAIL:" + sym + ":" + field)
        if (amount(a.get("volume")) <= 0 or amount(a.get("trade_count")) <= 0
                or amount(r.get("volume")) <= 0 or amount(l.get("volume")) <= 0):
            raise ValueError("SIP_VOLUMES_NOT_POSITIVE:" + sym)
    provenance = w.get("settlement_evidence_provenance") or {}
    audit = w.get("audit") or {}
    if not (provenance.get("observation_asof_et") == asof
            and provenance.get("alpaca_feed") == "sip"
            and provenance.get("sip_volume_is_authoritative") is True
            and audit.get("no_new_price_pass") is True
            and audit.get("no_MC_primary_pass_created") is True):
        raise ValueError("SIP_PROVENANCE_SAFETY_FAIL")


def check_current() -> str:
    request = read(ROOT / "canonical_current_resolver_request.json")
    if request.get("settlement_already_proven") is not True:
        return "PENDING_NOT_A_PASS"
    rel = request.get("settlement_bridge_path") or ""
    sha = request.get("settlement_bridge_blob_sha")
    target = (REPO / rel).resolve()
    if not (rel.startswith("nasdaq-xray/canonical_resolver_bridge_")
            and target.parent == ROOT.resolve()
            and target.is_file() and blob(target) == sha):
        raise ValueError("SIP_SETTLEMENT_REQUEST_WITNESS_SHA_INVALID")
    w = read(target)
    if not str(w.get("settlement_method") or "").startswith("ALPACA_HISTORICAL_SIP_"):
        return "OTHER_SETTLEMENT_METHOD_NOT_ATTESTED_BY_THIS_GUARD"
    verify_proof(w)
    master = read(ROOT / "canonical_current_master_manifest.json")
    price = read(ROOT / "canonical_current_price_dv30.json")
    if not (
        w["asof_et"] == request["asof_et"] == master["asof_et"] == price["asof_et"]
        and w["queue_hash"] == master["queue_hash"] == request["queue_hash"]
        and w["queue_total"] == master["queue_total"] == request["queue_total"]
        and w["source_price_blob_sha"] == request["source_price_blob_sha"] == blob(ROOT / "canonical_current_price_dv30.json")
        and request["source_price_pass_hash"] == price["pass_hash"]
        and request["source_price_pass_count"] == price["pass_count"]
        and w["price_unknown_symbols"] == price["unknown_symbols"] == []
        and w["price_unknown_count"] == price["unknown_count"] == 0
        and w["price_blocked_symbols"] == price["blocked_symbols"]
        and w["price_blocked_count"] == price["blocked_count"]
        and w["symbol_hash"] == request["symbol_hash"]
        and w["symbols"] == request["symbols"]
        and w["symbol_count"] == request["symbol_count"]
        and all(s in master["pass_symbols"] and s in price["pass_symbols"]
                for s in w["settlement_symbols"])
    ):
        raise ValueError("SIP_CURRENT_LINEAGE_OR_PRICE_PARTITION_MISMATCH")
    return "PASS_WITNESS_VERIFIED_NO_ALPHA_AUTHORITY"


def selftest() -> None:
    p = ROOT / "canonical_resolver_bridge_20261008_c417_dv30_v1.json"
    witness = read(p)
    verify_proof(witness)
    def must_fail(change):
        x = copy.deepcopy(witness)
        change(x)
        try:
            verify_proof(x)
        except (ValueError, KeyError, TypeError):
            return
        raise AssertionError("NEGATIVE_PROOF_UNEXPECTEDLY_PASSED")
    must_fail(lambda x: x["settlement_evidence"]["AAPL"]["alpaca_sip"].__setitem__(
        "high", x["settlement_evidence"]["AAPL"]["alpaca_sip"]["high"] + 0.02))
    must_fail(lambda x: x["settlement_evidence"]["AAPL"]["alpaca_sip"].__setitem__("volume", 0))
    must_fail(lambda x: x["settlement_evidence"]["NVDA"]["longbridge"].__setitem__(
        "timestamp", "2026-10-07T20:00:00Z"))
    must_fail(lambda x: x["settlement_evidence"].pop("MSFT"))
    must_fail(lambda x: x.__setitem__("settlement_status", "UNKNOWN"))
    print("XRAY_SIP_SETTLEMENT_WITNESS_SELFTEST=PASS_POSITIVE_AND_5_NEGATIVE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--check-current", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
    if args.check_current:
        print("XRAY_SIP_SETTLEMENT_CURRENT=" + check_current())
    if not (args.selftest or args.check_current):
        parser.error("Select --selftest or --check-current")
