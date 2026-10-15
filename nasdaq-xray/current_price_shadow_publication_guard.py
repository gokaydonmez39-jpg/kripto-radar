#!/usr/bin/env python3
"""Private, current-ASOF Alpaca 30Min SIP census -> PUBLIC COUNTS ONLY.

The existing consumer measures a bounded, lower-bound *research* partition.
This gate neither fetches nor stores vendor bars. It prevents emitting ticker
classifications, prices, volumes, missing-session detail, or false AL/R92.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MASTER = ROOT / "canonical_current_master_manifest.json"
PRICE = ROOT / "canonical_current_price_dv30.json"
SCHEMA = "XRAY_CURRENT_SIP_30MIN_RESEARCH_COUNTS_ONLY_V1"
CENSUS_SCHEMA = "XRAY_PERSONAL_CURRENT_EXACT30_SIP_PRICE_RECHECK_V1"
MEASURED = {
    "LOWER_BOUND_GE_50M_SHADOW",
    "UPPER_BOUND_LT_50M_SHADOW",
    "AMBIGUOUS_BETWEEN_BOUNDS_SHADOW",
}
NONPASS = {
    "UNKNOWN_NOT_ATTEMPTED",
    "UNKNOWN_BATCH_TRANSPORT_OR_INTEGRITY",
    "UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW",
}
SAFE = {"execution": "NONE", "real_money": "NO-GO",
        "unknown_never_pass": True}
# Strict enumeration of derived incident labels; never copy exception text,
# symbol IDs, missing bar positions, per-session values or provider payloads.
GAP_REASONS = {
    "DAILY_30_SESSION_GAP","RTH_30MIN_SESSION_GAP",
    "DUPLICATE_SOURCE_BAR","OHLCV_SCHEMA_OR_TIMESTAMP_INVALID",
    "RTH_VOLUME_EXCEEDS_DAILY","OTHER_STRUCTURAL_SOURCE_REJECTION",
    "NO_VERIFIABLE_SOURCE_BARS","PROVIDER_AUTH_OR_RATE_LIMIT",
    "PROVIDER_TRANSPORT_FAILURE","UNATTEMPTED_BUDGET_OR_LIMIT",
}


def demand(value: bool, code: str) -> None:
    if not value:
        raise ValueError("XRAY_CURRENT_SIP_RESEARCH_" + code)


def gitsha(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + bytes([0]) + raw
    ).hexdigest()


def symbolsha(symbols: list[str]) -> str:
    return hashlib.sha256(("\n".join(symbols) + "\n").encode()).hexdigest()


def source(master: dict, price: dict, last_complete: str) -> tuple[str, list[str]]:
    demand(type(master) is dict and type(price) is dict, "INVALID_DOCUMENT")
    demand(all(x.get(k) == v for x in (master, price)
               for k, v in SAFE.items()), "UNSAFE_SOURCE")
    asof = price.get("asof_et")
    demand(isinstance(asof, str) and asof == master.get("asof_et")
           and asof == last_complete, "NOT_LATEST_SOURCE_ASOF")
    full = master.get("pass_symbols")
    symbols = price.get("unknown_symbols")
    demand(type(full) is list and full == sorted(set(full))
           and len(full) == master.get("pass_count")
           and type(symbols) is list and symbols == sorted(set(symbols))
           and len(symbols) == price.get("unknown_count")
           and 0 < len(symbols) <= 650
           and set(symbols).issubset(set(full)), "UNKNOWN_SCOPE_INCOMPLETE")
    demand(price.get("pass_count") == 0
           or type(price.get("pass_count")) is int,
           "PRICE_PASS_BAD_TYPE")
    demand(type(master.get("unknown_count")) is int
           and master.get("unknown_count") >= 0, "MASTER_UNKNOWN_INVALID")
    return asof, symbols


def baseline(asof: str, symbols: list[str],
             master_sha: str, price_sha: str, status: str) -> dict:
    return {
        "schema": SCHEMA, "asof_et": asof, "status": status,
        "source_master_blob_sha": master_sha,
        "source_price_blob_sha": price_sha,
        "source_unknown_symbols_sha256": symbolsha(symbols),
        "exact_source_unknown_scope_count": len(symbols),
        "classified_count": 0, "attempted_count": 0, "api_calls": 0,
        "counts": {"UNKNOWN_NOT_ATTEMPTED": len(symbols)},
        "complete_research_partition": False,
        "all_symbol_dispositions_recorded": False,
        "measured_research_bound_count": 0,
        "unresolved_shadow_source_count": len(symbols),
        "integrity_recheck_unresolved_reason_counts": {},
        "source_authority": "SHADOW_RTH_30MIN_LOWER_BOUND_NOT_CANONICAL",
        "data_rights_independently_attested": False,
        "closing_auction_and_corrections_attested": False,
        "current_price_dv30_primary_pass_created": 0,
        "mc_primary_pass_created": 0, "r92_registered": False,
        "user_device_receipt_attested": False,
        "published_vendor_raw_ohlcv": False,
        "published_symbol_classifications": False,
        "alpha_authority": False,
        **SAFE,
    }


def sanitize(j: dict, master: dict, price: dict, mb: bytes, pb: bytes,
             latest: str) -> dict:
    asof, symbols = source(master, price, latest)
    demand(type(j) is dict and j.get("schema") == CENSUS_SCHEMA,
           "WRONG_CENSUS_SCHEMA")
    demand(j.get("asof_et") == asof
           and j.get("source_master_git_blob_sha") == gitsha(mb)
           and j.get("source_price_git_blob_sha") == gitsha(pb)
           and j.get("source_sha_exact") is True, "SHA_OR_ASOF_DRIFT")
    demand(j.get("source_price_unknown_total") == len(symbols)
           and j.get("source_price_unknown_symbols_sha256") == symbolsha(symbols)
           and j.get("scope_total") == len(symbols)
           and j.get("scope_truncated") is False, "CENSUS_SCOPE_MISMATCH")
    partition = j.get("classifications")
    demand(type(partition) is dict and set(partition) == set(symbols),
           "CENSUS_EXACT_SYMBOL_SET")
    allowed = MEASURED | NONPASS
    counts = collections.Counter()
    for classification in partition.values():
        demand(type(classification) is str
               and (classification in allowed
                    or re.fullmatch(r"UNKNOWN_HTTP_(400|401|403|404|429|500|502|503)",
                                    classification) is not None),
               "INVALID_CLASSIFICATION")
        counts[classification] += 1
    demand(j.get("counts") == dict(counts)
           and sum(counts.values()) == len(symbols)
           and j.get("classified_count") == len(symbols) - counts["UNKNOWN_NOT_ATTEMPTED"]
           and j.get("all_symbols_classified")
               == (counts["UNKNOWN_NOT_ATTEMPTED"] == 0),
           "CLASSIFICATION_ACCOUNTING")
    demand(type(j.get("attempted_count")) is int
           and 0 <= j["attempted_count"] <= len(symbols)
           and type(j.get("api_calls")) is int
           and 0 <= j["api_calls"] <= j.get("call_budget", -1) <= 1200,
           "UNBOUNDED_REQUESTS")
    demand(all(j.get(k) is False for k in (
        "canonical_price_promoted", "canonical_mc_promoted",
        "canonical_files_mutated", "registered_R92_created",
        "auction_and_trade_correction_independently_verified",
        "official_rth_exact_volume_attested", "vendor_raw_OHLCV_written"))
        and j.get("price_primary_pass_count") == 0
        and j.get("research_lower_bound_ge_50m_count")
            == counts["LOWER_BOUND_GE_50M_SHADOW"]
        and all(j.get(k) == v for k, v in SAFE.items()),
        "PRIMARY_AUTHORITY_FALSE_ASSERTION")
    # "Every ticker received a classification label" is NOT synonymous with
    # intact thirty-session source evidence. On real 14-Oct input, 5/513
    # had an integrity gap; the old code falsely marked the whole research
    # partition complete. Preserve exact counts without promoting any alpha.
    measured=sum(counts[k] for k in MEASURED)
    unresolved=len(symbols)-measured
    demand(measured>=0 and unresolved>=0, "MEASURED_SCOPE_ACCOUNTING")
    status = ("PARTIAL_OR_BLOCKED_SHADOW_NO_PRIMARY"
              if counts["UNKNOWN_NOT_ATTEMPTED"]>0 else
              "SHADOW_CENSUSED_WITH_SOURCE_GAPS_NO_PRIMARY"
              if unresolved>0 else
              "SHADOW_BOUNDS_ALL_MEASURED_NOT_PRIMARY")
    result = baseline(asof, symbols, gitsha(mb), gitsha(pb), status)
    result.update({
        "counts": dict(sorted(counts.items())),
        "classified_count": j["classified_count"],
        "attempted_count": j["attempted_count"],
        "api_calls": j["api_calls"],
        "complete_research_partition": measured==len(symbols),
        "all_symbol_dispositions_recorded": bool(j["all_symbols_classified"]),
        "measured_research_bound_count": measured,
        "unresolved_shadow_source_count": unresolved,
    })
    if "integrity_recheck_unresolved_reason_counts" in j:
        categories=j["integrity_recheck_unresolved_reason_counts"]
        candidate_count=j.get("integrity_recheck_candidate_count")
        attempts=j.get("integrity_recheck_attempted")
        recovered=j.get("integrity_recheck_recovered")
        unknown=counts["UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW"]
        demand(type(categories) is dict and
               all(type(k) is str and k in GAP_REASONS and
                   type(v) is int and v>=0 for k,v in categories.items()),
               "GAP_DIAGNOSTIC_ENUM_INVALID")
        demand(type(candidate_count) is int and type(attempts) is int
               and type(recovered) is int and
               0<=recovered<=attempts<=8 and
               recovered+unknown==candidate_count and
               attempts<=candidate_count and
               sum(categories.values())==unknown and
               j.get("integrity_recheck_unresolved")==unknown,
               "GAP_DIAGNOSTIC_PARTITION_INVALID")
        result["integrity_recheck_unresolved_reason_counts"]=dict(sorted(categories.items()))
        result["integrity_recheck_attempted"]=attempts
        result["integrity_recheck_recovered"]=recovered
        result["integrity_recheck_unresolved"]=unknown
    return result


def selftest() -> None:
    master = dict(SAFE, asof_et="2026-10-14",
                  pass_symbols=["AAPL", "MSFT"], pass_count=2,
                  unknown_count=0)
    price = dict(SAFE, asof_et="2026-10-14",
                 unknown_symbols=["AAPL", "MSFT"], unknown_count=2,
                 pass_count=0)
    mb = b"MASTER_FIXTURE"
    pb = b"PRICE_FIXTURE"
    a = dict.fromkeys(price["unknown_symbols"], "UNKNOWN_NOT_ATTEMPTED")
    j = {
        "schema": CENSUS_SCHEMA, "asof_et": "2026-10-14",
        "source_master_git_blob_sha": gitsha(mb),
        "source_price_git_blob_sha": gitsha(pb),
        "source_sha_exact": True,
        "source_price_unknown_total": 2,
        "source_price_unknown_symbols_sha256": symbolsha(["AAPL", "MSFT"]),
        "scope_total": 2, "scope_truncated": False,
        "classifications": a,
        "counts": {"UNKNOWN_NOT_ATTEMPTED": 2},
        "classified_count": 0, "all_symbols_classified": False,
        "attempted_count": 0, "api_calls": 0, "call_budget": 1200,
        "canonical_price_promoted": False, "canonical_mc_promoted": False,
        "canonical_files_mutated": False, "registered_R92_created": False,
        "auction_and_trade_correction_independently_verified": False,
        "official_rth_exact_volume_attested": False,
        "vendor_raw_OHLCV_written": False,
        "price_primary_pass_count": 0,
        "research_lower_bound_ge_50m_count": 0,
        **SAFE,
    }
    demand(sanitize(j, master, price, mb, pb, "2026-10-14")[
        "status"] == "PARTIAL_OR_BLOCKED_SHADOW_NO_PRIMARY",
        "VALID_UNKNOWN_REJECTED")
    live = json.loads(json.dumps(j))
    live["classifications"]["AAPL"] = "LOWER_BOUND_GE_50M_SHADOW"
    live["classifications"]["MSFT"] = "UPPER_BOUND_LT_50M_SHADOW"
    live["counts"] = {"LOWER_BOUND_GE_50M_SHADOW": 1,
                      "UPPER_BOUND_LT_50M_SHADOW": 1}
    live["classified_count"] = 2
    live["attempted_count"] = 2
    live["all_symbols_classified"] = True
    live["research_lower_bound_ge_50m_count"] = 1
    output = sanitize(live, master, price, mb, pb, "2026-10-14")
    demand(output["complete_research_partition"] is True
            and output["unresolved_shadow_source_count"] == 0
            and output["measured_research_bound_count"] == 2
            and output["status"] == "SHADOW_BOUNDS_ALL_MEASURED_NOT_PRIMARY"
            and output["current_price_dv30_primary_pass_created"] == 0
            and output["published_symbol_classifications"] is False,
            "FALSE_RELEASE")
    # Real 14-Oct shape: all 513 symbols assigned a status, but five
    # underlying source datasets are incomplete. Never call that COMPLETE.
    mixed=json.loads(json.dumps(live))
    mixed["classifications"]["MSFT"]="UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW"
    mixed["counts"]={"LOWER_BOUND_GE_50M_SHADOW":1,
                     "UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW":1}
    diagnostic=json.loads(json.dumps(mixed))
    diagnostic.update(integrity_recheck_candidate_count=1,
                      integrity_recheck_attempted=1,
                      integrity_recheck_recovered=0,
                      integrity_recheck_unresolved=1,
                      integrity_recheck_unresolved_reason_counts={
                         "RTH_30MIN_SESSION_GAP":1})
    safe_diag=sanitize(diagnostic,master,price,mb,pb,"2026-10-14")
    demand(safe_diag["integrity_recheck_unresolved_reason_counts"]==
           {"RTH_30MIN_SESSION_GAP":1}
           and safe_diag["unresolved_shadow_source_count"]==1
           and safe_diag["published_symbol_classifications"] is False,
           "SOURCE_DIAGNOSTIC_LEAK_OR_MISMATCH")
    for tamper in (
        dict(diagnostic,integrity_recheck_unresolved_reason_counts={
             "RAW_VENDOR_ERROR_123":1}),
        dict(diagnostic,integrity_recheck_unresolved_reason_counts={
             "RTH_30MIN_SESSION_GAP":2}),
        dict(diagnostic,integrity_recheck_recovered=1),
    ):
        try:sanitize(tamper,master,price,mb,pb,"2026-10-14")
        except ValueError:pass
        else:raise AssertionError("INVALID_GAP_DIAGNOSTIC_ACCEPTED")
    partial=sanitize(mixed,master,price,mb,pb,"2026-10-14")
    demand(partial["status"]=="SHADOW_CENSUSED_WITH_SOURCE_GAPS_NO_PRIMARY"
           and partial["all_symbol_dispositions_recorded"] is True
           and partial["complete_research_partition"] is False
           and partial["unresolved_shadow_source_count"]==1
           and partial["measured_research_bound_count"]==1
           and partial["r92_registered"] is False,
           "FALSE_COMPLETION_ON_SOURCE_INTEGRITY_GAP")
    bad = [
        (dict(j, asof_et="2026-10-13"), price, mb, pb, "2026-10-14"),
        (dict(j, source_price_git_blob_sha="0"*40), price, mb, pb, "2026-10-14"),
        (dict(j, counts={}), price, mb, pb, "2026-10-14"),
        (dict(j, canonical_price_promoted=True), price, mb, pb, "2026-10-14"),
        (dict(j, registered_R92_created=True), price, mb, pb, "2026-10-14"),
        (dict(j, classifications={"AAPL": "PASS_PRICE_DV30"}),
         price, mb, pb, "2026-10-14"),
        (dict(j, classifications={"AAPL": "UNKNOWN_NOT_ATTEMPTED"}),
         price, mb, pb, "2026-10-14"),
        (dict(j, api_calls=1201), price, mb, pb, "2026-10-14"),
        (j, dict(price, unknown_symbols=["MSFT"]), mb, pb, "2026-10-14"),
        (j, price, mb, pb, "2026-10-15"),
    ]
    for idx, (candidate, p, mbytes, pbytes, epoch) in enumerate(bad):
        try:
            sanitize(candidate, master, p, mbytes, pbytes, epoch)
        except (ValueError, TypeError):
            continue
        raise AssertionError("FALSE_SHADOW_EVIDENCE_ACCEPTED_" + str(idx))
    print("XRAY_CURRENT_SIP_PUBLICATION_SELFTEST=PASS_4_POSITIVE_13_NEGATIVE_ENUMERATED_FIVE_GAP_REASONS_NO_RAW_NO_R92")


def live(mode: str, path: Path, output: Path) -> int:
    demand(not output.resolve().is_relative_to(ROOT.parent.resolve()),
           "PUBLIC_REPO_OUTPUT_FORBIDDEN")
    from source_epoch_freshness_guard import last_complete_session
    now = dt.datetime.now(dt.timezone.utc)
    latest = last_complete_session(now)
    mb, pb = MASTER.read_bytes(), PRICE.read_bytes()
    master, price = json.loads(mb), json.loads(pb)
    try:
        asof, symbols = source(master, price, latest)
    except ValueError as exc:
        blocked = {
            "schema": SCHEMA, "status": "BLOCKED_SOURCE_ASOF_OR_SCOPE",
            "asof_et": price.get("asof_et"), "latest_completed_asof_et": latest,
            "execution": "NONE", "real_money": "NO-GO",
            "alpha_authority": False, "r92_registered": False,
            "published_vendor_raw_ohlcv": False,
            "published_symbol_classifications": False,
            "reason_code": str(exc),
        }
        output.write_text(json.dumps(blocked, sort_keys=True, indent=2)+"\n")
        print("XRAY_CURRENT_SIP_PREFLIGHT=BLOCKED_SOURCE_NOT_CURRENT")
        return 2
    if mode == "preflight":
        result = baseline(asof, symbols, gitsha(mb), gitsha(pb),
                          "PREFLIGHT_READY_SHADOW_ONLY")
    elif mode in ("no-keys", "runtime-error"):
        result = baseline(asof, symbols, gitsha(mb), gitsha(pb),
                          ("BLOCKED_PROVIDER_CREDENTIALS_NOT_CONFIGURED"
                           if mode == "no-keys" else
                           "BLOCKED_PRIVATE_VENDOR_CENSUS_ERROR"))
    else:
        demand(path is not None and path.is_file(), "PRIVATE_SOURCE_MISSING")
        result = sanitize(json.loads(path.read_text()), master, price, mb, pb, latest)
    output.write_text(json.dumps(result, sort_keys=True, indent=2)+"\n")
    print("XRAY_CURRENT_SIP_PUBLIC_STATUS="+result["status"])
    print("XRAY_CURRENT_SIP_PUBLIC_SCOPE="+str(result["exact_source_unknown_scope_count"]))
    print("XRAY_CURRENT_SIP_NO_ALPHA_NO_DEVICE_RECEIPT=TRUE")
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--selftest", action="store_true")
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--no-keys", action="store_true")
    modes.add_argument("--runtime-error", action="store_true")
    modes.add_argument("--sanitize", type=Path)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if args.out is None:
        p.error("--out is required")
    raise SystemExit(live(
        "preflight" if args.preflight else
        "no-keys" if args.no_keys else
        "runtime-error" if args.runtime_error else "sanitize",
        args.sanitize, args.out))


if __name__ == "__main__":
    main()
