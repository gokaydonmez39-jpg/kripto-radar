#!/usr/bin/env python3
"""Independent, read-only dual-lane FINAL truth receipt. Never AL or device ACK.

This is a proof verifier, not a source generator. Canonical PASS requires live
same-session lineage and zero UNKNOWN. Private Google Sheets/phone acceptance
cannot be inferred from a public GitHub checkout and remains unattested here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SCHEMA = "XRAY_NASDAQ_FINAL_PROOF_ENGINE_V1"
FILES = {
    "overlay": "canonical_current_final_gate_overlay.json",
    "terminal": "canonical_current_terminal.json",
    "pointer": "chatgpt_canonical_state_v2.json",
    "g9_runtime": "strict_g9_runtime_state.json",
    "g9_authority": "g9_entitlement_authority.json",
    "account_gate": "account_gate_contract.json",
    "resolver": "canonical_current_resolver_request.json",
    "price": "canonical_current_price_dv30.json",
    "master": "canonical_current_master_manifest.json",
    "orchestrator": "orchestrator_state.json",
    "official": "canonical_official_source_guard.json",
}
SIP = "AUTHENTICATED_SIP_RESOLVER_BRIDGE_REQUIRED"
NO_TRADE = {"execution": "NONE", "real_money": "NO-GO"}


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def official_last_complete(now: dt.datetime) -> str | None:
    """XNAS official exchange-calendar close + 30 minutes, or UNKNOWN."""
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW_NOT_AUTHORIZED")
    try:
        import exchange_calendars as xcals
        import pandas as pd
        utc = pd.Timestamp(now).tz_convert("UTC")
        cal = xcals.get_calendar("XNAS")
        sessions = cal.sessions_in_range(
            (utc - pd.Timedelta(days=20)).date(), utc.date())
        complete = [str(s.date()) for s in sessions
                    if cal.session_close(s) + pd.Timedelta(minutes=30) <= utc]
        return complete[-1] if complete else None
    except (ImportError, ValueError, TypeError, OverflowError, KeyError):
        return None


def snapshot(root: Path) -> tuple[dict, dict, list[str]]:
    documents, blobs, errors = {}, {}, []
    for key, file in FILES.items():
        path = root / file
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError("SOURCE_MISSING_OR_SYMLINK")
            data = path.read_bytes()
            doc = json.loads(data)
            if type(doc) is not dict:
                raise ValueError("NOT_AN_OBJECT")
            documents[key] = doc
            blobs[key] = git_blob(data)
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            documents[key] = {}
            blobs[key] = None
            errors.append(key + ":" + type(exc).__name__)
    return documents, blobs, errors


def _int(value: Any) -> int:
    return value if type(value) is int else -1


def _reason(row: Any) -> str | None:
    if type(row) is not dict:
        return None
    v = row.get("price_result")
    info = v.get("info") if type(v) is dict else None
    return info.get("reason") if type(info) is dict else None


def audit(doc: dict, sha: dict, official_asof: str | None,
          errors: list[str] | None = None) -> dict:
    """Pure and reproducible decision; tests must exercise positive AND negative."""
    o = doc.get("overlay") or {}
    t = doc.get("terminal") or {}
    p = doc.get("pointer") or {}
    gr = doc.get("g9_runtime") or {}
    ga = doc.get("g9_authority") or {}
    account = doc.get("account_gate") or {}
    master = doc.get("master") or {}
    price = doc.get("price") or {}
    resolver = doc.get("resolver") or {}
    root = doc.get("orchestrator") or {}
    official = doc.get("official") or {}
    source_terminal = o.get("source_terminal") or {}
    source_pointer = o.get("source_pointer") or {}
    g9 = o.get("strict_g9") or {}
    acct = o.get("account") or {}
    bridge = o.get("current_research_chain") or {}
    bind = o.get("terminal_live_artifact_bindings") or {}
    flags = o.get("binding_integrity") or {}
    go = o.get("true_full_go") or {}
    unknown_rows = resolver.get("price_unknown_detail")
    unknown_symbols = resolver.get("price_unknown_symbols")
    unknown = _int(resolver.get("price_unknown_count"))
    details = list(unknown_rows.values()) if type(unknown_rows) is dict else []
    sip_count = sum(_reason(r) == SIP for r in details)
    history = _int(root.get("unknown_count"))
    names = (t.get("asof_et"), o.get("asof_et"), master.get("asof_et"),
             price.get("asof_et"), resolver.get("asof_et"),
             root.get("asof_et"))
    safe_sources = all(type(x) is dict and
        x.get("execution") == "NONE" and x.get("real_money") == "NO-GO"
        for x in (o, t, master, price, resolver, root, gr, ga))
    checks = {
        "source_files_complete": not bool(errors) and all(
            type(doc.get(k)) is dict and bool(doc[k]) and
            isinstance(sha.get(k), str) for k in FILES),
        "no_execution_or_real_money": safe_sources,
        "official_xnas_completed_session": (
            type(official_asof) is str and len(official_asof) == 10),
        "same_current_asof": (
            type(official_asof) is str and all(a == official_asof for a in names)),
        "overlay_exact_terminal_pointer_sha": (
            source_terminal.get("blob_sha") == sha.get("terminal") and
            source_pointer.get("blob_sha") == sha.get("pointer") and
            isinstance(sha.get("terminal"), str) and
            isinstance(sha.get("pointer"), str)),
        "overlay_exact_g9_account_sha": (
            g9.get("runtime_blob_sha") == sha.get("g9_runtime") and
            g9.get("authority_blob_sha") == sha.get("g9_authority") and
            acct.get("gate_blob_sha") == sha.get("account_gate") and
            all(isinstance(sha.get(k), str)
                for k in ("g9_runtime", "g9_authority", "account_gate"))),
        "no_live_terminal_blob_drift": (
            bind.get("exact") is True and bind.get("mismatch_count") == 0 and
            bind.get("mismatches") == [] and
            flags.get("fail_closed_safe") is True),
        "price_resolver_source_bound": (
            resolver.get("source_price_blob_sha") == sha.get("price") and
            isinstance(sha.get("price"), str) and
            _int(price.get("pass_count")) ==
                _int(resolver.get("source_price_pass_count")) and
            _int(price.get("pass_count")) > 0),
        "zero_price_unknown_and_exhaustive_detail": (
            unknown == 0 and type(unknown_rows) is dict and
            len(details) == 0 and type(unknown_symbols) is list and
            len(unknown_symbols) == 0 and
            _int(resolver.get("price_blocked_count")) == 0 and
            _int(price.get("unknown_count")) == 0),
        "master_identity_complete": (
            _int((master.get("counts") or {}).get("UNKNOWN_IDENTITY")) == 0 and
            _int((master.get("counts") or {}).get("PASS_IDENTITY")) > 0),
        "independent_history_complete": history == 0 and
            root.get("status") not in ("PARTIAL_HISTORY", None),
        "same_asof_settlement_proven": (
            resolver.get("settlement_required") is False or
            resolver.get("settlement_already_proven") is True),
        "measured_mc_history_chain_exact": (
            bridge.get("exact") is True and
            bridge.get("coverage_complete") is True),
        "official_safety_sources_pass": (
            official.get("status") == "PASS" and
            official.get("alpha_authority") is False and
            all((official.get("sources") or {}).get(k, {}).get("status") == "PASS"
                for k in ("security_status", "system_status_ipo",
                          "system_status_selfhelp", "trade_halts",
                          "trading_system_adds_deletes"))),
        "strict_g9_authority": (
            g9.get("g9_pass") is True and
            gr.get("g9_pass") is True and ga.get("status") == "PROVEN"),
        "account_same_run_attested": (
            acct.get("account_pass") is True and
            acct.get("same_run_live_witness_attested") is True and
            account.get("current_status") in ("PASS", "ACCOUNT_PASS")),
        "terminal_research_pass": (
            t.get("full_end_to_end_research_pass") is True and
            source_terminal.get("full_end_to_end_research_pass") is True and
            go.get("status") == "PASS" and
            set(go.get("passed") or []) == {
                "FULL_E2E_RESEARCH_PASS", "STRICT_G9_PASS", "SAME_RUN_ACCOUNT_PASS"} and
            not go.get("blocked")),
    }
    groups = []
    def add(key, ok, children=()):
        if not ok:
            groups.append({"id": key, "status": "HOLD", "downstream": list(children)})
    add("SOURCE_INTEGRITY", all(checks[k] for k in (
        "source_files_complete", "no_execution_or_real_money",
        "overlay_exact_terminal_pointer_sha", "overlay_exact_g9_account_sha",
        "no_live_terminal_blob_drift", "official_safety_sources_pass")))
    add("ASOF_FRESHNESS", checks["official_xnas_completed_session"] and
        checks["same_current_asof"])
    add("PRICE_SIP", checks["price_resolver_source_bound"] and
        checks["zero_price_unknown_and_exhaustive_detail"], ("MC", "TERMINAL"))
    add("IDENTITY", checks["master_identity_complete"])
    add("HISTORY_INDEPENDENT_PROOF", checks["independent_history_complete"],
        ("MC", "TERMINAL"))
    add("SETTLEMENT", checks["same_asof_settlement_proven"], ("MC",))
    add("MC_AUTHORITY", checks["measured_mc_history_chain_exact"],
        ("TERMINAL",))
    add("G9_ENTITLEMENT", checks["strict_g9_authority"], ("TERMINAL",))
    add("ACCOUNT_AUTHORITY", checks["account_same_run_attested"], ("TERMINAL",))
    add("TERMINAL_RELEASE", checks["terminal_research_pass"])
    canonical = "PASS" if all(checks.values()) else "HOLD"
    personal = "HOLD"  # No private Sheets or independent device receipts in this job.
    return {
        "schema": SCHEMA, "asof_official_last_complete": official_asof,
        "canonical": {"status": canonical, "checks": checks,
                      "root_groups": groups,
                      "price_unknown": unknown,
                      "price_sip_requirement_count": sip_count,
                      "price_unknown_detail_count": len(details),
                      "history_unknown": history,
                      "terminal_asof": t.get("asof_et")},
        "personal_477": {"status": personal,
                         "reason": "INDEPENDENT_PRIVATE_SHEETS_EOD_READBACK_NOT_IN_THIS_JOB",
                         "device_delivery_status": "UNKNOWN_NOT_DEVICE_ACK"},
        "full_system_final": "HOLD",
        "security": {"execution": "NONE", "real_money": "NO-GO",
                     "alpha_authority": False, "no_broker_orders": True,
                     "unknown_never_pass": True},
        "source_errors": errors or [],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--at-utc", type=str)
    args = ap.parse_args()
    now = (dt.datetime.fromisoformat(args.at_utc.replace("Z", "+00:00"))
           if args.at_utc else dt.datetime.now(dt.timezone.utc))
    if now.tzinfo is None:
        raise SystemExit("AWARE_UTC_TIMESTAMP_REQUIRED")
    docs, blobs, errors = snapshot(args.root)
    report = audit(docs, blobs, official_last_complete(now), errors)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("XRAY_INDEPENDENT_FINAL_CANONICAL=" + report["canonical"]["status"])
    print("XRAY_INDEPENDENT_FINAL_PERSONAL=" + report["personal_477"]["status"])
    print("XRAY_INDEPENDENT_FINAL_SYSTEM=" + report["full_system_final"])
    print("XRAY_INDEPENDENT_FINAL_ROOTS=" +
          ",".join(x["id"] for x in report["canonical"]["root_groups"]))
    # HOLD is a validated safe decision, not a failing Python process.


if __name__ == "__main__":
    main()
