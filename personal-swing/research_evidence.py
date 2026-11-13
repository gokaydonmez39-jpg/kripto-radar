#!/usr/bin/env python3
"""XRAY offline, fail-closed evidence adapter: no networking, trading, alerts or writes to live state.

Input JSON/XML must be independently acquired from allowed official sources.
Parsed records are RESEARCH_ONLY; an external provenance check and human/legal
review are required before any runtime signal or alert integration.
"""
import argparse
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from research_source_events import event_evidence

SCHEMA = "XRAY_RESEARCH_EVIDENCE_V1"
ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
DOCUMENT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,190}$")
FORM_HINTS = {
    "8-K": "ISSUER_EVENT_REVIEW", "8-K/A": "AMENDED_EVENT_REVIEW",
    "10-K": "FINANCIAL_REPORT_REVIEW", "10-K/A": "AMENDED_REPORT_REVIEW",
    "10-Q": "FINANCIAL_REPORT_REVIEW", "10-Q/A": "AMENDED_REPORT_REVIEW",
    "4": "INSIDER_REVIEW", "4/A": "AMENDED_INSIDER_REVIEW",
    "13F-HR": "DELAYED_HOLDINGS_CONTEXT", "13F-HR/A": "AMENDED_HOLDINGS_CONTEXT",
}

def utc_time(value):
    if not isinstance(value, str):
        raise ValueError("TIMESTAMP_REQUIRED")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP_FORBIDDEN")
    return parsed.astimezone(timezone.utc)

def strict_day(value):
    if not isinstance(value, str):
        raise ValueError("DATE_REQUIRED")
    try:
        d = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_DATE") from exc
    if d.isoformat() != value:
        raise ValueError("NONCANONICAL_DATE")
    return d

def cik10(value):
    if isinstance(value, bool) or not str(value).isdigit():
        raise ValueError("INVALID_CIK")
    n = int(value)
    if n <= 0 or n >= 10**10:
        raise ValueError("INVALID_CIK")
    return f"{n:010d}"

def _row(columns, i, names):
    row = {}
    for name in names:
        values = columns.get(name)
        if not isinstance(values, list) or i >= len(values):
            raise ValueError("MALFORMED_SEC_COLUMNS")
        row[name] = values[i]
    return row

def sec_submission_evidence(payload, *, symbol, expected_cik, cutoff_utc):
    """Inspect SEC submissions JSON with exact CIK/ticker/acceptance binding.

    No assumption that local JSON was fetched from SEC; provenance is UNATTESTED.
    """
    cutoff = utc_time(cutoff_utc)
    cik = cik10(expected_cik)
    if cik10(payload.get("cik")) != cik:
        raise ValueError("SEC_CIK_MISMATCH")
    tickers = payload.get("tickers")
    exchanges = payload.get("exchanges")
    if not isinstance(tickers, list) or not isinstance(exchanges, list) or len(tickers) != len(exchanges):
        raise ValueError("SEC_IDENTITY_AMBIGUOUS")
    if symbol not in tickers or not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", symbol):
        raise ValueError("SEC_TICKER_MISMATCH")
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form")
    if not isinstance(forms, list):
        raise ValueError("SEC_RECENT_FORMS_MISSING")
    out, unseen = [], 0
    for i, form in enumerate(forms):
        if form not in FORM_HINTS:
            continue
        try:
            row = _row(recent, i, ("accessionNumber", "acceptanceDateTime", "filingDate", "primaryDocument"))
            accepted = utc_time(row["acceptanceDateTime"])
            strict_day(row["filingDate"])
            accession = row["accessionNumber"]
            document = row["primaryDocument"]
            if not ACCESSION_RE.fullmatch(accession) or not DOCUMENT_RE.fullmatch(document):
                raise ValueError("UNSAFE_SEC_DOCUMENT_IDENTIFIER")
        except (TypeError, KeyError, ValueError):
            unseen += 1
            continue
        if accepted > cutoff:
            continue  # NEVER leak a future filing into a historical snapshot
        archive_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{document}"
        )
        out.append({
            "symbol": symbol, "cik": cik, "form": form,
            "accession": accession, "accepted_utc": accepted.isoformat(),
            "filing_date": row["filingDate"], "official_url": archive_url,
            "risk_hint": FORM_HINTS[form], "source": "SEC_EDGAR",
            "authority": "UNATTESTED_OFFLINE_INPUT", "action": "MANUAL_REVIEW_ONLY",
        })
    out.sort(key=lambda x: (x["accepted_utc"], x["accession"], x["form"]))
    return {"filings": out, "unverifiable_rows": unseen,
            "coverage": "PARTIAL_UNKNOWN" if unseen else "LOCAL_PAYLOAD_ONLY",
            "live_source_attested": False}

def _local(tag):
    return tag.rsplit("}", 1)[-1]

def _first_text(parent, wanted):
    for element in parent.iter():
        if _local(element.tag) == wanted and element.text:
            return element.text.strip()
    return None

def form4_transaction_evidence(xml_text, *, expected_cik, accepted_utc, cutoff_utc, amended=False):
    """Form 4 P/S/M classification: neither P nor Form 4 is automatic AL."""
    accepted = utc_time(accepted_utc)
    cutoff = utc_time(cutoff_utc)
    if accepted > cutoff:
        return []
    if "<!DOCTYPE" in xml_text.upper() or "<!ENTITY" in xml_text.upper():
        raise ValueError("XML_ENTITY_DECLARATION_FORBIDDEN")
    if len(xml_text) > 2_000_000:
        raise ValueError("FORM4_XML_TOO_LARGE")
    root = ET.fromstring(xml_text)
    issuer = next((e for e in root.iter() if _local(e.tag) == "issuer"), None)
    if issuer is None or cik10(_first_text(issuer, "issuerCik")) != cik10(expected_cik):
        raise ValueError("FORM4_ISSUER_MISMATCH")
    result = []
    for item in root.iter():
        if _local(item.tag) != "nonDerivativeTransaction":
            continue
        code = _first_text(item, "transactionCode")
        if code not in ("P", "S", "M"):
            classification = "UNCLASSIFIED"
        else:
            classification = {"P": "PURCHASE_MARKET_OR_PRIVATE_REVIEW", "S": "SALE_REVIEW",
                              "M": "OPTION_EXERCISE_NOT_OPEN_MARKET_PURCHASE"}[code]
        value_element = next((x for x in item.iter()
                              if _local(x.tag) == "transactionDate"), None)
        trans_date = _first_text(value_element, "value") if value_element is not None else None
        if trans_date:
            strict_day(trans_date)
        if amended:
            classification = "AMENDED_" + classification
        result.append({
            "code": code, "classification": classification,
            "transaction_date": trans_date, "accepted_utc": accepted.isoformat(),
            "planned_10b5_1": "UNKNOWN_REQUIRES_FULL_FILING_REVIEW",
            "authority": "UNATTESTED_OFFLINE_INPUT", "action": "MANUAL_REVIEW_ONLY",
        })
    return result

def fred_vintage_evidence(payload, *, series_id, cutoff_utc, release_times):
    """Select only locally supplied, time-evidenced ALFRED vintages.

    Date intervals are inclusive and retain the V1 UTC-day convention. The
    immediately prior vintage can bridge into the revision day only when
    adjacent and the successor's release clock is known and still ahead.
    Caller-supplied clocks and intervals do not attest provider availability.
    """
    cutoff = utc_time(cutoff_utc)
    cut_day = cutoff.date()
    if type(release_times) is not dict or not isinstance(series_id, str) or not series_id.strip():
        raise ValueError("MACRO_SOURCE_METADATA_REQUIRED")
    rows = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("FRED_OBSERVATIONS_MISSING")

    by_day, invalid_days, expired_days, omitted = {}, set(), set(), 0
    for row in rows:
        observation = None
        try:
            observation = strict_day(row["date"])
            if observation > cut_day:
                continue
            start = strict_day(row["realtime_start"])
            if start > cut_day:
                continue
            end = strict_day(row["realtime_end"])
            if end < start:
                raise ValueError("FRED_INTERVAL_REVERSED")
            if (cut_day - end).days > 1:
                expired_days.add(observation)
                continue
            # Keep exact source values for conflict detection, including when
            # distinct decimals round to the same binary float.
            clock_key = f"{observation}|{start}"
            released = utc_time(release_times[clock_key])
            if released.date() < start:
                raise ValueError("INVALID_RELEASE_BEFORE_VINTAGE")
            # Unreleased values must never affect the as-of value, including
            # disagreements between not-yet-available values of one revision.
            raw = row.get("value")
            if released > cutoff:
                value = None
            elif raw == ".":
                value = None
            else:
                if type(raw) is not str or len(raw) > 100 or not re.fullmatch(
                    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?", raw
                ):
                    raise ValueError("FRED_VALUE_INVALID")
                value = Decimal(raw)
                numeric = float(value)
                if not math.isfinite(numeric) or (value != 0 and numeric == 0):
                    raise ValueError("FRED_VALUE_NOT_REPRESENTABLE")
                if value == 0:
                    value = Decimal(0)
            by_day.setdefault(observation, set()).add((start, end, released, value))
        except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
            omitted += 1
            if observation is not None:
                invalid_days.add(observation)

    chosen, quarantined = [], invalid_days | (expired_days - by_day.keys())
    for observation, versions in sorted(by_day.items()):
        if observation in invalid_days:
            continue
        active = [v for v in versions if v[1] >= cut_day]
        prior = [v for v in versions if v[1] < cut_day]
        # Distinct date intervals or payload values on one applicable vintage
        # cannot be resolved by input order or silently replaced by older data.
        if len(active) != 1:
            quarantined.add(observation)
            continue
        start, end, released, value = active[0]
        if released > cutoff:
            adjacent = (start == cut_day and released.date() == cut_day and
                        len(prior) == 1 and prior[0][2] <= cutoff and
                        prior[0][0] < start and prior[0][3] is not None)
            if not adjacent:
                if prior or observation in expired_days:
                    quarantined.add(observation)
                continue
            start, end, released, value = prior[0]
        if value is None:
            quarantined.add(observation)
            omitted += 1
            continue
        chosen.append({
            "series_id": series_id, "observation_date": observation.isoformat(),
            "vintage_start": start.isoformat(), "release_utc": released.isoformat(),
            "value": float(value), "source": "FRED_ALFRED",
            "authority": "UNATTESTED_OFFLINE_INPUT", "action": "MACRO_RESEARCH_ONLY",
        })
    return {"observations": chosen, "unverifiable_rows": omitted,
            "quarantined_observations": len(quarantined),
            "coverage": "PARTIAL_UNKNOWN" if omitted or quarantined else "LOCAL_PAYLOAD_ONLY",
            "live_source_attested": False}


def holdings_13f_evidence(*, accession, report_period, accepted_utc, cutoff_utc):
    """Never treat the quarter-end holding snapshot as the public availability time."""
    if not ACCESSION_RE.fullmatch(accession):
        raise ValueError("INVALID_13F_ACCESSION")
    period = strict_day(report_period)
    accepted = utc_time(accepted_utc)
    cutoff = utc_time(cutoff_utc)
    if period > accepted.date():
        raise ValueError("13F_FUTURE_REPORT_PERIOD")
    return {
        "accession": accession, "report_period": period.isoformat(),
        "available_asof_cutoff": accepted <= cutoff,
        "accepted_utc": accepted.isoformat(),
        "action": "DELAYED_CONTEXT_ONLY", "live_source_attested": False,
    }

def build_record(*, symbol, expected_cik, cutoff_utc,
                 sec_payload=None, form4_xml=None, form4_accepted=None,
                 fred_payload=None, fred_series=None, release_times=None,
                 source_event_rows=None):
    utc_time(cutoff_utc)
    cik10(expected_cik)
    if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", symbol):
        raise ValueError("INVALID_SYMBOL")
    result = {
        "schema": SCHEMA, "symbol": symbol, "expected_cik": cik10(expected_cik),
        "cutoff_utc": utc_time(cutoff_utc).isoformat(),
        "production_eligible": False, "live_source_attested": False,
        "signal": None, "stop_target_modified": False, "alerts_sent": 0,
        "evidence_only": True, "no_network_requests": True,
        "sec": {"filings": [], "coverage": "NOT_SUPPLIED"},
        "form4": [], "macro": {"observations": [], "coverage": "NOT_SUPPLIED"},
    }
    if sec_payload is not None:
        result["sec"] = sec_submission_evidence(
            sec_payload, symbol=symbol, expected_cik=expected_cik, cutoff_utc=cutoff_utc)
    if form4_xml is not None:
        if form4_accepted is None:
            raise ValueError("FORM4_ACCEPTANCE_REQUIRED")
        result["form4"] = form4_transaction_evidence(
            form4_xml, expected_cik=expected_cik, accepted_utc=form4_accepted,
            cutoff_utc=cutoff_utc)
    if fred_payload is not None:
        if not fred_series or release_times is None:
            raise ValueError("FRED_RELEASE_PROVENANCE_REQUIRED")
        result["macro"] = fred_vintage_evidence(
            fred_payload, series_id=fred_series, cutoff_utc=cutoff_utc,
            release_times=release_times)
    if source_event_rows is not None:
        result["official_source_events"] = event_evidence(
            source_event_rows, cutoff_utc=cutoff_utc)
        if any(row["source"] == "SEC" and row["issuer_cik"] != cik10(expected_cik)
               for row in result["official_source_events"]["events"]):
            raise ValueError("SOURCE_EVENT_ISSUER_MISMATCH")
    return result

def main(argv=None):
    p = argparse.ArgumentParser(description="Offline SEC/ALFRED research evidence; not a signal")
    p.add_argument("--symbol", required=True)
    p.add_argument("--cik", required=True)
    p.add_argument("--cutoff-utc", required=True, help="Verified UTC close/knowledge cutoff")
    p.add_argument("--sec-json", type=Path)
    p.add_argument("--form4-xml", type=Path)
    p.add_argument("--form4-accepted-utc")
    p.add_argument("--fred-json", type=Path)
    p.add_argument("--fred-series")
    p.add_argument("--fred-release-times-json", type=Path)
    p.add_argument("--official-events-json", type=Path,
                   help="Locally supplied SEC/Fed/BLS event observations, not live evidence")
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args(argv)
    load = lambda path: json.loads(path.read_text(encoding="utf-8")) if path else None
    result = build_record(
        symbol=a.symbol, expected_cik=a.cik, cutoff_utc=a.cutoff_utc,
        sec_payload=load(a.sec_json),
        form4_xml=a.form4_xml.read_text(encoding="utf-8") if a.form4_xml else None,
        form4_accepted=a.form4_accepted_utc,
        fred_payload=load(a.fred_json), fred_series=a.fred_series,
        release_times=load(a.fred_release_times_json),
        source_event_rows=load(a.official_events_json))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    if a.output.exists():
        raise RuntimeError("OUTPUT_ALREADY_EXISTS_NO_OVERWRITE")
    # Never export raw SEC/FRED payloads; no personal candidate/private prices.
    serialized = json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    a.output.write_text(serialized, encoding="utf-8")
    print(json.dumps({"status": "OFFLINE_RESEARCH_ONLY", "symbol": a.symbol,
                      "sha256": hashlib.sha256(serialized.encode()).hexdigest(),
                      "production_eligible": False, "alerts_sent": 0}))

if __name__ == "__main__":
    main()
