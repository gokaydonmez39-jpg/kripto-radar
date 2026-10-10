#!/usr/bin/env python3
"""Independent C4.17 two-lane observability; NEVER an authority for PRIMARY, R92 or GO.

Lane A observes the immutable existing canonical production gate. Lane B allows
exact-SHA independent source-preparation research while those external rights
remain unavailable. This file contains NO vendor requests and NEVER promotes
SHADOW evidence, inferred licenses or offline tests to a production PASS.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from current_history_source_request import build as history_request_build
from e2e_production_readiness import snapshot as existing_readiness_snapshot

SCHEMA = "XRAY_C417_DUAL_LANE_GO_OBSERVABILITY_SHADOW_V1"
POLICY = "C4.17"
CONTROL = "C4.27"


def blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def symbol_hash(symbols: list[str]) -> str:
    return hashlib.sha256("\n".join(symbols).encode("utf-8")).hexdigest()


def evaluate(master: dict, price: dict, resolver: dict, history_request: dict,
             existing: dict, blobs: dict[str, str]) -> dict:
    reasons: list[str] = []
    def demand(ok: bool, code: str) -> None:
        if not ok:
            reasons.append(code)

    for name, document in (("master", master), ("price", price),
                           ("resolver", resolver), ("history", history_request),
                           ("existing", existing)):
        demand(isinstance(document, dict), "INVALID_OBJECT_" + name.upper())
    if reasons:
        return blocked_report(None, 0, "", None, existing, blobs, reasons)

    asof = price.get("asof_et")
    symbols = price.get("pass_symbols")
    symbols = symbols if isinstance(symbols, list) else []
    master_symbols = master.get("pass_symbols")
    master_symbols = master_symbols if isinstance(master_symbols, list) else []
    demand(isinstance(asof, str) and asof != "", "MISSING_ASOF")
    demand(master.get("asof_et") == asof == resolver.get("asof_et")
           == history_request.get("asof_et") == existing.get("asof_et"),
           "ASOF_SOURCE_DRIFT")
    demand(all(d.get("execution") == "NONE" and d.get("real_money") == "NO-GO"
               and d.get("unknown_never_pass") is True
               for d in (master, price, resolver, history_request)),
           "SAFETY_STATE_CHANGED")
    demand(existing.get("execution") == "NONE"
           and existing.get("real_money") == "NO-GO", "AUDIT_SAFETY_DRIFT")
    demand(master_symbols == sorted(set(master_symbols))
           and len(master_symbols) == master.get("pass_count")
           and symbol_hash(master_symbols) == master.get("pass_hash"),
           "MASTER_SYMBOL_SCOPE_INVALID")
    demand(symbols != [] and symbols == sorted(set(symbols))
           and len(symbols) == price.get("pass_count")
           and symbol_hash(symbols) == price.get("pass_hash")
           and set(symbols).issubset(master_symbols), "PRICE_PASS_SET_INVALID")
    demand(master.get("queue_total") == len(master_symbols)
           and price.get("source_master_count") == len(master_symbols)
           and price.get("source_master_queue_hash") == master.get("queue_hash"),
           "MASTER_QUEUE_BINDING_INVALID")
    demand(set(price.get("results") or {}) == set(master_symbols)
           and len(price.get("results") or {}) == len(master_symbols),
           "PRICE_FULL_PARTITION_NOT_REPLAYABLE")
    demand(price.get("unknown_count") == len(price.get("unknown_symbols") or [])
           and price.get("blocked_count") == len(price.get("blocked_symbols") or [])
           and not (set(symbols) & set(price.get("unknown_symbols") or []))
           and not (set(symbols) & set(price.get("blocked_symbols") or [])),
           "PRICE_UNKNOWN_BLOCKED_INVALID")
    demand(all(isinstance(blobs.get(n), str) and len(blobs[n]) == 40
               and all(c in "0123456789abcdef" for c in blobs[n])
               for n in ("master", "price", "resolver", "terminal")),
           "SOURCE_GIT_SHA_INVALID")
    demand(resolver.get("source_master_blob_sha") == blobs.get("master")
           and resolver.get("source_price_blob_sha") == blobs.get("price")
           and resolver.get("source_price_pass_count") == len(symbols)
           and resolver.get("source_price_pass_hash") == price.get("pass_hash"),
           "RESOLVER_GIT_BLOB_MISMATCH")
    demand(history_request.get("source_price_blob_sha") == blobs.get("price")
           and history_request.get("source_price_pass_hash") == price.get("pass_hash")
           and history_request.get("source_price_pass_count") == len(symbols)
           and history_request.get("symbol_scope") == symbols,
           "SHADOW_HISTORY_SCOPE_OR_SHA_MISMATCH")
    daily = history_request.get("required_daily_official_sessions")
    weekly = history_request.get("required_completed_week_closes")
    demand(isinstance(daily, list) and len(daily) == 260
           and len(set(daily)) == 260 and daily == sorted(daily)
           and daily[-1] == asof
           and isinstance(weekly, list) and len(weekly) == 52
           and len(set(weekly)) == 52 and weekly == sorted(weekly)
           and weekly[-1] <= asof,
           "OFFICIAL_260_52_DATE_SCOPE_INVALID")
    demand(history_request.get("source_entitlement_proven") is False
           and history_request.get("current_history_authority_proven") is False
           and history_request.get("canonical_history_pass_created") == 0
           and history_request.get("can_register_R92") is False,
           "SHADOW_SOURCE_FORGED_AUTHORITY")
    demand(existing.get("source_blob_shas", {}).get("master") == blobs.get("master")
           and existing.get("source_blob_shas", {}).get("price") == blobs.get("price")
           and existing.get("source_blob_shas", {}).get("resolver_request") == blobs.get("resolver")
           and existing.get("source_blob_shas", {}).get("terminal") == blobs.get("terminal"),
           "CANONICAL_READINESS_SOURCE_SHA_MISMATCH")
    demand(existing.get("price_pass_count") == len(symbols)
           and existing.get("master_unknown_count") == master.get("unknown_count"),
           "AUDIT_SOURCE_SCOPE_MISMATCH")
    return blocked_report(asof, len(symbols), price.get("pass_hash"),
                          master.get("unknown_count"), existing, blobs, reasons)


def blocked_report(asof, count, p_hash, identity_unknown, existing, blobs, reasons):
    valid = len(reasons) == 0
    canonical_attested = (valid and existing.get("full_e2e_research_attested") is True)
    return {
        "schema": SCHEMA, "asof_et": asof, "policy": POLICY, "control": CONTROL,
        "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True,
        "source_integrity_pass": valid,
        "source_integrity_failures": sorted(set(reasons)),
        "dual_lane_architecture": "CONCURRENT_SEPARATE_AUTHORITIES_NO_SHADOW_PROMOTION",
        "canonical_lane": {
            "status": ("EXISTING_CANONICAL_RESEARCH_CHAIN_ATTESTED_DIAGNOSTIC_ONLY"
                       if canonical_attested else "CANONICAL_CURRENT_RESEARCH_BLOCKED"),
            "existing_full_e2e_attested": canonical_attested,
            "existing_current_primary_mc_count":
                existing.get("current_mc_authority_count") if valid else None,
            "existing_blockers": existing.get("blockers") if valid else [],
            "canonical_history_created_by_dual_lane": 0,
            "primary_mc_created_by_dual_lane": 0,
        },
        "shadow_lane": {
            "status": ("EXACT_PRICE_PASS_HISTORY_REQUEST_READY_NO_VENDOR_DATA"
                       if valid else "INTEGRITY_BLOCKED_NO_SOURCE_PREP"),
            "price_pass_scope_count": count if valid else 0,
            "price_pass_scope_hash": p_hash if valid else None,
            "master_identity_unknown_count": identity_unknown if valid else None,
            "required_official_daily_sessions": 260 if valid else 0,
            "required_completed_week_closes": 52 if valid else 0,
            "vendor_calls_made_by_dual_lane": 0,
            "provider_rights_attested_by_dual_lane": False,
            "measured_vendor_ohlcv_by_dual_lane": False,
            "shadow_is_canonical_source": False,
        },
        "source_blob_shas": blobs,
        "go_authority": False,
        "can_register_R92": False,
        "can_notify_device": False,
        "actual_device_delivery_receipt_attested": False,
        "no_order_placement": True,
        "note": "This report is observability only. Source licenses, original real OHLCV, MC, G9, ACCOUNT and canonical release remain independent gates.",
    }


def selftest():
    syms = ["AAA", "BBB"]
    master = {"asof_et": "2026-10-09", "pass_symbols": syms, "pass_count": 2,
              "pass_hash": symbol_hash(syms), "queue_total": 2,
              "queue_hash": "q" * 64, "unknown_count": 1,
              "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True}
    price = {"asof_et": "2026-10-09", "pass_symbols": syms, "pass_count": 2,
             "pass_hash": symbol_hash(syms), "source_master_count": 2,
             "source_master_queue_hash": "q" * 64,
             "results": {"AAA": {}, "BBB": {}},
             "unknown_count": 0, "unknown_symbols": [],
             "blocked_count": 0, "blocked_symbols": [],
             "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True}
    sha = {"master": "a"*40, "price": "b"*40, "resolver": "c"*40, "terminal": "d"*40}
    resolver = {"asof_et": "2026-10-09", "source_master_blob_sha": sha["master"],
                "source_price_blob_sha": sha["price"], "source_price_pass_count": 2,
                "source_price_pass_hash": price["pass_hash"],
                "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True}
    history = {"asof_et": "2026-10-09", "source_price_blob_sha": sha["price"],
               "source_price_pass_hash": price["pass_hash"],
               "source_price_pass_count": 2, "symbol_scope": syms,
               "required_daily_official_sessions": ["S%03d" % n for n in range(259)] + ["2026-10-09"],
               "required_completed_week_closes": ["W%03d" % n for n in range(52)],
               "source_entitlement_proven": False, "current_history_authority_proven": False,
               "canonical_history_pass_created": 0, "can_register_R92": False,
               "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True}
    # Synthetic dates in test only; never used as market history.
    history["required_daily_official_sessions"] = ["2026-10-09"] + ["S%03d" % n for n in range(259)]
    # Exercise the date shape via minimal fixture with lexicographic ordering.
    history["required_daily_official_sessions"] = ["2025-%03d" % n for n in range(259)] + ["2026-10-09"]
    history["required_completed_week_closes"] = ["2025-W%02d" % n for n in range(52)]
    existing = {"asof_et": "2026-10-09", "execution": "NONE", "real_money": "NO-GO",
                "full_e2e_research_attested": False,
                "current_mc_authority_count": 0, "master_unknown_count": 1,
                "price_pass_count": 2,
                "blockers": ["CURRENT_MC_AUTHORITY_MISSING"],
                "source_blob_shas": {**{k: sha[k] for k in ("master", "price", "terminal")},
                                     "resolver_request": sha["resolver"]}}
    good = evaluate(master, price, resolver, history, existing, sha)
    assert good["source_integrity_pass"] is True
    assert good["shadow_lane"]["price_pass_scope_count"] == 2
    assert good["canonical_lane"]["status"] == "CANONICAL_CURRENT_RESEARCH_BLOCKED"
    assert good["can_register_R92"] is False and good["go_authority"] is False
    corrupt = [
        ("PRICE_PASS_HASH", lambda m,p,r,h,e,s: p.update(pass_hash="f"*64)),
        ("PRICE_SYMBOL_SUBSTITUTION", lambda m,p,r,h,e,s: p.update(pass_symbols=["AAA", "ZZZ"])),
        ("MASTER_SHA", lambda m,p,r,h,e,s: s.update(master="f"*40)),
        ("SHADOW_PRICE_SHA", lambda m,p,r,h,e,s: h.update(source_price_blob_sha="f"*40)),
        ("ASOF_LOOKAHEAD", lambda m,p,r,h,e,s: h.update(asof_et="2026-10-12")),
        ("PARTITION", lambda m,p,r,h,e,s: p["results"].pop("BBB")),
        ("SHADOW_FORGED_HISTORY_PASS", lambda m,p,r,h,e,s: h.update(canonical_history_pass_created=2)),
        ("SHADOW_FORGED_ENTITLEMENT", lambda m,p,r,h,e,s: h.update(source_entitlement_proven=True)),
        ("SHADOW_FORGED_R92", lambda m,p,r,h,e,s: h.update(can_register_R92=True)),
        ("SAFETY", lambda m,p,r,h,e,s: r.update(real_money="GO")),
        ("DATE_SCOPE", lambda m,p,r,h,e,s: h["required_daily_official_sessions"].pop()),
        ("AUDIT_SOURCE_SHA", lambda m,p,r,h,e,s: e["source_blob_shas"].update(price="f"*40)),
    ]
    for name, mutate in corrupt:
        values = deepcopy((master, price, resolver, history, existing, sha))
        mutate(*values)
        x = evaluate(*values)
        assert x["source_integrity_pass"] is False, name
        assert x["shadow_lane"]["price_pass_scope_count"] == 0, name
        assert x["go_authority"] is False and x["can_register_R92"] is False, name
    fake_ready = deepcopy(existing)
    fake_ready.update(full_e2e_research_attested=True, current_mc_authority_count=1, blockers=[])
    x = evaluate(master, price, resolver, history, fake_ready, sha)
    assert x["source_integrity_pass"] is True
    assert x["go_authority"] is False and x["can_register_R92"] is False
    assert x["canonical_lane"]["existing_full_e2e_attested"] is True
    print("XRAY_C417_DUAL_LANE=PASS_1_POSITIVE_12_NEGATIVES_1_FAKE_READY_NO_SHADOW_PROMOTION")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--out", type=Path)
    opts = parser.parse_args()
    if opts.selftest:
        selftest()
        return
    def load(name: str) -> tuple[dict, bytes]:
        raw = (ROOT/name).read_bytes()
        return json.loads(raw), raw
    master, raw_m = load("canonical_current_master_manifest.json")
    price, raw_p = load("canonical_current_price_dv30.json")
    resolver, raw_r = load("canonical_current_resolver_request.json")
    _terminal, raw_t = load("canonical_current_terminal.json")
    blobs = {n: blob_sha(b) for n,b in (
        ("master", raw_m), ("price", raw_p), ("resolver", raw_r), ("terminal", raw_t))}
    current = existing_readiness_snapshot()
    history = history_request_build(price, master, blobs["price"])
    result = evaluate(master, price, resolver, history, current, blobs)
    if opts.out:
        if opts.out.resolve().is_relative_to(ROOT.parent.resolve()):
            raise ValueError("PUBLIC_REPOSITORY_OUTPUT_FORBIDDEN")
        opts.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("XRAY_C417_DUAL_LANE_SOURCE_INTEGRITY=" + ("PASS" if result["source_integrity_pass"] else "BLOCKED"))
    print("XRAY_C417_DUAL_LANE_SHADOW_SCOPE=" + str(result["shadow_lane"]["price_pass_scope_count"]))
    print("XRAY_C417_DUAL_LANE_PRIMARY_MC=" + str(result["canonical_lane"]["existing_current_primary_mc_count"]))
    print("XRAY_C417_DUAL_LANE_BLOCKERS=" + json.dumps(result["canonical_lane"]["existing_blockers"]))
    print("XRAY_C417_DUAL_LANE_NO_SOURCE_NO_GO_NO_R92=PASS")
    if not result["source_integrity_pass"]:
        raise SystemExit("FAIL_CLOSED_DUAL_LANE_INPUT_DRIFT:" + ",".join(result["source_integrity_failures"]))


if __name__ == "__main__":
    main()
