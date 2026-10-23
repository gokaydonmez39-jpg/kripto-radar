#!/usr/bin/env python3
"""Source-exact, read-only personal NASDAQ research diagnostics (never R92)."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent
SCHEMA = "XRAY_PERSONAL_RESEARCH_DIAGNOSTICS_V1"
DIGEST = "XRAY_PERSONAL_EOD_RESEARCH_DIGEST_V1"
BLOBS = {"root": "orchestrator_state.json",
         "master": "canonical_current_master_manifest.json",
         "price": "canonical_current_price_dv30.json"}
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
TICKER = re.compile(r"[A-Z][A-Z0-9.]{0,9}\Z")
REASON = re.compile(r"[A-Z0-9_]+\Z")


def check(ok, reason):
    if not ok:
        raise ValueError("XRAY_PERSONAL_DIAGNOSTICS_" + reason)


def observed_blobs():
    output = {}
    for k, filename in BLOBS.items():
        output[k] = subprocess.check_output(
            ["git", "hash-object", str(ROOT / filename)],
            cwd=ROOT.parent, text=True, timeout=15).strip()
        check(HEX40.fullmatch(output[k]) is not None, "HASH_" + k)
    return output


def verify(d):
    check(type(d) is dict and d.get("schema") == DIGEST, "SCHEMA")
    try:
        actual = date.fromisoformat(d["asof_et"])
    except (KeyError, ValueError, TypeError):
        raise ValueError("XRAY_PERSONAL_DIAGNOSTICS_DATE") from None
    check(actual.isoformat() == d["asof_et"], "DATE_CANONICAL")
    check(d.get("mode") == "PERSONAL_NONCOMMERCIAL_RESEARCH_ONLY"
          and d.get("execution") == "NONE" and d.get("real_money") == "NO-GO"
          and d.get("broker") is False and d.get("orders") == []
          and d.get("unknown_never_pass") is True
          and d.get("registered_r92_count") == 0
          and d.get("certified_C417_AL_signal_count") == 0
          and d.get("automated_alert_authority") is False
          and d.get("iphone_receipt_attested") is False
          and d.get("candidate_setup_is_not_R92") is True
          and d.get("no_raw_ohlcv_or_levels_exported") is True,
          "NO_TRADING_OR_R92")
    check(d.get("source_confidence", {}).get("grade") == "LOW"
          and d["source_confidence"].get("source_quality_not_probability") is True,
          "CONFIDENCE_NOT_PROBABILITY")
    b = d.get("source_epoch_blobs")
    check(type(b) is dict and set(b) == set(BLOBS)
          and all(type(v) is str and HEX40.fullmatch(v) for v in b.values()),
          "GIT_BLOBS")
    check(all(type(d.get(k)) is str and HEX64.fullmatch(d[k])
              for k in ("watchlist_digest", "source_candidates_sha256")),
          "WATCH_HASHES")
    names = d.get("liquidity_watch_symbols")
    pending = d.get("technical_pending_symbols")
    state = d.get("technical_state_counts")
    check(type(names) is list and len(names) == d.get("watchlist_count")
          and len(names) == len(set(names))
          and all(type(s) is str and TICKER.fullmatch(s) for s in names)
          and type(pending) is list and pending == sorted(set(pending))
          and set(pending).issubset(names) and type(state) is dict
          and all(type(n) is int and n >= 0 for n in state.values())
          and sum(state.values()) == len(names)
          and state.get("UNKNOWN_260_OFFICIAL_HISTORY", 0) == len(pending)
          and type(d.get("technical_evaluated_count")) is int
          and d["technical_evaluated_count"] + len(pending) == len(names),
          "WATCH_PARTITION")
    triggers = d.get("recent_technical_triggers")
    candidates = d.get("research_setup_candidate_symbols")
    check(type(triggers) is list
          and len(triggers) == d.get("recent_technical_trigger_count")
          and type(candidates) is list
          and candidates == sorted(set(candidates))
          and all(type(s) is str and TICKER.fullmatch(s) for s in candidates)
          and len(candidates) == d.get("research_setup_candidate_count"),
          "TRIGGER_PARTITION")
    seen, derived = set(), []
    for row in triggers:
        check(type(row) is dict, "ROW_TYPE")
        sym, fam, bad = (row.get("symbol"), row.get("families"),
                         row.get("unresolved_or_rejected"))
        check(type(sym) is str and TICKER.fullmatch(sym) and sym in names
              and sym not in seen and type(fam) is list and fam
              and fam == sorted(set(fam)) and set(fam).issubset(set("ABCD"))
              and row.get("math_formula_audited") is True
              and row.get("not_a_trade_or_R92") is True
              and row.get("technical_source_confidence") == "LIMITED_SECONDARY_EOD"
              and type(bad) is list and bad == sorted(set(bad))
              and all(type(s) is str and REASON.fullmatch(s) for s in bad),
              "TRIGGER_PROVENANCE")
        seen.add(sym)
        if row.get("status") == "RESEARCH_SETUP_CANDIDATE":
            check(not bad, "CANDIDATE_REJECTED")
            derived.append(sym)
        else:
            check(row.get("status") == "TRIGGER_OBSERVED_NOT_APPROVED"
                  and bad, "REJECTED_UNLABELED")
    check(sorted(derived) == candidates
          and d.get("status") == (
              "PERSONAL_RESEARCH_SETUP_CANDIDATES_AVAILABLE" if candidates
              else "PERSONAL_LIQUIDITY_WATCH_AND_REJECTED_TRIGGERS"),
          "CANDIDATE_STATE")


def build(d, actual_blobs):
    verify(d)
    check(type(actual_blobs) is dict and set(actual_blobs) == set(BLOBS)
          and all(type(v) is str and HEX40.fullmatch(v)
                  for v in actual_blobs.values()), "CURRENT_BLOBS")
    mismatch = sorted(k for k in BLOBS
                      if d["source_epoch_blobs"][k] != actual_blobs[k])
    base = {"schema": SCHEMA, "asof_et": d["asof_et"],
            "source_epoch_blobs": d["source_epoch_blobs"],
            "source_binding_mismatches": mismatch,
            "source_confidence": "LOW_SECONDARY_EOD_NOT_PROBABILITY",
            "mode": "PERSONAL_NONCOMMERCIAL_RESEARCH_ONLY",
            "execution": "NONE", "real_money": "NO-GO",
            "broker": False, "orders": [],
            "registered_r92_count": 0, "certified_C417_AL_signal_count": 0,
            "automated_alert_authority": False,
            "iphone_receipt_attested": False,
            "no_raw_ohlcv_or_levels_exported": True}
    if mismatch:
        return {**base, "status": "STALE_SOURCE_EPOCH_BLOCKED",
                "watch_count": 0, "trigger_count": 0, "candidate_count": 0,
                "rejected_triggers": [], "blocker_frequency": {},
                "candidate_symbols": []}
    reject = [x for x in d["recent_technical_triggers"]
              if x["status"] == "TRIGGER_OBSERVED_NOT_APPROVED"]
    counts = Counter(code for x in reject
                     for code in x["unresolved_or_rejected"])
    return {**base, "status": "SOURCE_BOUND_RESEARCH_ONLY_NOT_BUY",
            "watch_count": d["watchlist_count"],
            "technical_evaluated_count": d["technical_evaluated_count"],
            "technical_pending_count": len(d["technical_pending_symbols"]),
            "trigger_count": len(d["recent_technical_triggers"]),
            "rejected_count": len(reject),
            "candidate_count": d["research_setup_candidate_count"],
            "candidate_symbols": d["research_setup_candidate_symbols"],
            "blocker_frequency": dict(sorted(counts.items(),
                             key=lambda x: (-x[1], x[0]))),
            "rejected_triggers": [
                {"symbol": x["symbol"], "families": x["families"],
                 "reason_count": len(x["unresolved_or_rejected"]),
                 "reasons": x["unresolved_or_rejected"],
                 "confidence": x["technical_source_confidence"],
                 "research_only_not_buy": True} for x in reject]}


def selftest():
    d = json.loads((ROOT / "personal_research_signal_digest.json").read_text())
    original = d["source_epoch_blobs"]
    good = build(d, original)
    check(good["status"] == "SOURCE_BOUND_RESEARCH_ONLY_NOT_BUY"
          and good["registered_r92_count"] == 0
          and good["trigger_count"] ==
              good["rejected_count"] + good["candidate_count"],
          "ACTUAL_DIGEST_TEST")
    bad_binding = build(d, {**original, "root": "0" * 40})
    check(bad_binding["status"] == "STALE_SOURCE_EPOCH_BLOCKED"
          and bad_binding["rejected_triggers"] == []
          and bad_binding["candidate_symbols"] == [], "STALE_REDACTED")
    mutations = (
        ("CERTIFIED", lambda x: x.update(certified_C417_AL_signal_count=1)),
        ("AUTHORITY", lambda x: x.update(automated_alert_authority=True)),
        ("BROKER", lambda x: x.update(broker=True)),
        ("RAW", lambda x: x.update(no_raw_ohlcv_or_levels_exported=False)),
        ("CONFIDENCE", lambda x: x["source_confidence"].update(grade="HIGH")),
        ("BAD_ASOF", lambda x: x.update(asof_et="2026-13-21")),
        # A zero-WATCH real digest is valid; mutate only an isolated copy.
        # Duplicate sentinel names must fail the watch partition even if
        # the actual watchlist has no rows.
        ("DUP_WATCH", lambda x: x["liquidity_watch_symbols"].extend(
            ["SIMULATED","SIMULATED"])),
        ("BAD_EVALUATED", lambda x: x.update(technical_evaluated_count=-1)),
        ("FALSE_TRIGGER", lambda x: x.update(
            recent_technical_trigger_count=d["recent_technical_trigger_count"] + 1)),
        ("FAKE_BLOB", lambda x: x["source_epoch_blobs"].update(root="not_sha")),
    )
    for label, mutate in mutations:
        x = deepcopy(d)
        mutate(x)
        try:
            build(x, original)
        except ValueError:
            continue
        raise AssertionError("MUTATION_FALSE_PASS_" + label)
    if d["recent_technical_triggers"]:
        for label, field, value in (
            ("FAKE_MATH", "math_formula_audited", False),
            ("HIDDEN_REJECTION", "unresolved_or_rejected", []),
            ("FAKE_BUY", "not_a_trade_or_R92", False)):
            x = deepcopy(d)
            x["recent_technical_triggers"][0][field] = value
            try:
                build(x, original)
            except ValueError:
                continue
            raise AssertionError("MUTATION_FALSE_PASS_" + label)
    print("XRAY_PERSONAL_DIAGNOSTICS=PASS_10_BASE_NEGATIVES"
          "_3_TRIGGER_NEGATIVES_STALE_REDACT_NO_R92")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--digest", type=Path,
                    default=ROOT / "personal_research_signal_digest.json")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        check(a.out is None, "SELFTEST_NO_WRITE")
        selftest()
        return
    check(a.out is not None, "OUTPUT_REQUIRED")
    report = build(json.loads(a.digest.read_text()), observed_blobs())
    a.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("XRAY_PERSONAL_DIAGNOSTICS=" + report["status"])


if __name__ == "__main__":
    main()
