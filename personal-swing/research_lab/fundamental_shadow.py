#!/usr/bin/env python3
"""Fail-closed, deterministic SEC annual-fundamental research shadow.

NO source HTTP, no model inference, vendor installs, broker, orders, Sheets,
notifications or production AL/STOP/2R authority. Input data are UNTRUSTED.
A passing structure test never proves the captured input came from SEC nor
that a historical market participant could access it at the asserted time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path
from zoneinfo import ZoneInfo

INPUT_SCHEMA = "XRAY_FUNDAMENTAL_SEC_INPUT_V1"
OUTPUT_SCHEMA = "XRAY_FUNDAMENTAL_SEC_SHADOW_V1"
TICKER_RE = re.compile(r"[A-Z][A-Z0-9.]{0,14}\Z")
CIK_RE = re.compile(r"[0-9]{10}\Z")
ACCESSION_RE = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
HEADER_ACCESSION = re.compile(r"ACCESSION NUMBER:\s*([0-9]{10}-[0-9]{2}-[0-9]{6})")
HEADER_CIK = re.compile(r"CENTRAL INDEX KEY:\s*([0-9]{1,10})")
HEADER_ACCEPTED = re.compile(r"<ACCEPTANCE-DATETIME>\s*([0-9]{14})")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
FIELDS = ("accessionNumber", "form", "filingDate", "acceptanceDateTime")
REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues", "SalesRevenueNet",
)
TAGS = {
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "net_income": ("NetIncomeLoss",),
}
MAX_RECENT = 20000
MAX_RAW_SIZE = 8_000_000  # Offline memory safety; not an SEC completeness claim.


class ShadowHold(ValueError):
    """An explicit safety hold; never treat as absence of a signal."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ShadowHold(code)


def timestamp(value: object) -> datetime:
    require(type(value) is str and len(value) <= 40 and
            re.search(r"(?:Z|[+-]\d{2}:\d{2})\Z", value) is not None,
            "TIMESTAMP_MISSING_OFFSET")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShadowHold("TIMESTAMP_MALFORMED") from exc
    require(dt.tzinfo is not None, "TIMESTAMP_MISSING_OFFSET")
    return dt.astimezone(timezone.utc)


def parsed_date(value: object) -> date:
    require(type(value) is str and DATE_RE.fullmatch(value) is not None,
            "DATE_MALFORMED")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ShadowHold("DATE_MALFORMED") from exc
    require(parsed.isoformat() == value, "DATE_MALFORMED")
    return parsed


def normalize_cik(value: object) -> str:
    if type(value) is int and 0 < value < 10**10:
        return f"{value:010d}"
    if type(value) is str and re.fullmatch(r"[0-9]{1,10}", value) and int(value) > 0:
        return value.zfill(10)
    raise ShadowHold("CIK_MALFORMED")


def load_watchlist(path: str | Path) -> frozenset[str]:
    """Read the project's exact 477-symbol user-approved research universe."""
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ShadowHold("WATCHLIST_NOT_READABLE") from exc
    symbols = obj.get("liquidity_watch_symbols") if type(obj) is dict else None
    require(type(symbols) is list and len(symbols) == 477,
            "WATCHLIST_NOT_477")
    require(all(type(s) is str and TICKER_RE.fullmatch(s) for s in symbols),
            "WATCHLIST_SYMBOL_MALFORMED")
    require(len(set(symbols)) == 477, "WATCHLIST_DUPLICATE")
    return frozenset(symbols)


def accepted_header(raw: object, accession: str, cik: str) -> datetime:
    """Accept a matching SEC SGML header, not submissions acceptanceDateTime.

    Header origin remains UNVERIFIED by this pure offline parser.
    """
    require(type(raw) is str and len(raw) <= 400000, "HEADER_MISSING_OR_LARGE")
    accession_match = HEADER_ACCESSION.search(raw)
    require(accession_match is not None and accession_match.group(1) == accession,
            "HEADER_ACCESSION_MISMATCH")
    cik_match = HEADER_CIK.search(raw)
    require(cik_match is not None and normalize_cik(cik_match.group(1)) == cik,
            "HEADER_CIK_MISMATCH")
    matches = HEADER_ACCEPTED.findall(raw)
    require(len(matches) == 1, "HEADER_ACCEPTANCE_AMBIGUOUS")
    try:
        eastern = datetime.strptime(matches[0], "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise ShadowHold("HEADER_ACCEPTANCE_MALFORMED") from exc
    local = eastern.replace(tzinfo=ZoneInfo("America/New_York"))
    # Historical fall-back DST overlap cannot be resolved by bare wall clock.
    require(local.utcoffset() == local.replace(fold=1).utcoffset(),
            "HEADER_DST_FOLD_AMBIGUOUS")
    # Reject nonexistent local times (spring DST gap) rather than normalize.
    back = local.astimezone(timezone.utc).astimezone(ZoneInfo("America/New_York"))
    require(back.replace(tzinfo=None) == eastern, "HEADER_DST_GAP_INVALID")
    return local.astimezone(timezone.utc)


def _filing_record(submissions: dict, cik: str, ticker: str, cutoff: datetime) -> dict:
    require(type(submissions) is dict, "SUBMISSIONS_MISSING")
    require(normalize_cik(submissions.get("cik")) == cik, "SUBMISSIONS_CIK_MISMATCH")
    tickers = submissions.get("tickers")
    require(type(tickers) is list and ticker in tickers and
            all(type(x) is str for x in tickers), "CURRENT_TICKER_CIK_MISMATCH")
    recent = submissions.get("filings", {}).get("recent")
    require(type(recent) is dict, "SUBMISSIONS_RECENT_MISSING")
    cols = [recent.get(key) for key in FIELDS]
    require(all(type(x) is list for x in cols), "SUBMISSIONS_COLUMNS_MISSING")
    n = len(cols[0])
    require(0 < n <= MAX_RECENT and all(len(x) == n for x in cols),
            "SUBMISSIONS_COLUMN_LENGTH_DRIFT")
    filings = []
    for accn, form, filed, _reported_clock in zip(*cols):
        require(type(accn) is str and ACCESSION_RE.fullmatch(accn) is not None,
                "ACCESSION_MALFORMED")
        require(type(form) is str and type(filed) is str, "FILING_FIELD_MALFORMED")
        filed_day = parsed_date(filed)
        if form in ("10-K", "10-K/A"):
            filings.append((filed_day, accn, form))
    require(bool(filings), "NO_ANNUAL_FILING_IN_RECENT")
    eligible = sorted((day, accn) for day, accn, form in filings
                      if form == "10-K" and day <= cutoff.date())
    require(bool(eligible), "NO_ANNUAL_FILING_BY_CUTOFF")
    latest_day, latest_accn = eligible[-1]
    if any(form == "10-K/A" and latest_day <= day <= cutoff.date()
           for day, accn, form in filings):
        raise ShadowHold("UNRESOLVED_10K_AMENDMENT")
    return {"filed": latest_day.isoformat(), "accn": latest_accn}


def _fact_periods(us_gaap: dict, tags: tuple[str, ...], accn: str,
                  filing_date: str, cutoff: datetime, positive: bool) -> tuple[str, dict]:
    for tag in tags:
        obj = us_gaap.get(tag)
        if type(obj) is not dict:
            continue
        units = obj.get("units")
        usd = units.get("USD") if type(units) is dict else None
        if type(usd) is not list:
            continue
        require(len(usd) <= 20000, "XBRL_FACT_ARRAY_TOO_LARGE")
        periods = {}
        for row in usd:
            if type(row) is not dict or row.get("accn") != accn or row.get("form") != "10-K":
                continue
            if row.get("filed") != filing_date:
                raise ShadowHold("XBRL_FILING_DATE_MISMATCH")
            start, end = parsed_date(row.get("start")), parsed_date(row.get("end"))
            duration = (end - start).days + 1
            if duration < 330 or duration > 400 or end > cutoff.date():
                continue
            val = row.get("val")
            require(type(val) is int, "NON_INTEGER_SEC_FACT")
            if positive:
                require(val >= 0, "NEGATIVE_REVENUE_OR_CAPEX")
            key = (start.isoformat(), end.isoformat())
            if key in periods and periods[key] != val:
                raise ShadowHold("CONFLICTING_XBRL_FACT")
            periods[key] = val
        if len(periods) >= 2:
            return tag, periods
    raise ShadowHold("REQUIRED_ANNUAL_FACT_MISSING")


def _annual_metrics(companyfacts: dict, cik: str, filing: dict,
                    cutoff: datetime) -> tuple[list[str], dict, dict]:
    require(type(companyfacts) is dict, "COMPANYFACTS_MISSING")
    require(normalize_cik(companyfacts.get("cik")) == cik,
            "COMPANYFACTS_CIK_MISMATCH")
    facts = companyfacts.get("facts")
    gaap = facts.get("us-gaap") if type(facts) is dict else None
    require(type(gaap) is dict, "GAAP_FACTS_MISSING")
    mapping = {"revenue": REVENUE_TAGS, **TAGS}
    all_periods = {}
    chosen_tags = {}
    for metric, tags in mapping.items():
        chosen_tags[metric], all_periods[metric] = _fact_periods(
            gaap, tags, filing["accn"], filing["filed"], cutoff,
            positive=metric in ("revenue", "capex"))
    common = set.intersection(*(set(periods) for periods in all_periods.values()))
    require(len(common) >= 2, "CROSS_STATEMENT_PERIOD_MISMATCH")
    pairs = sorted(common, key=lambda p: p[1])
    curr = pairs[-1]
    prev_candidates = [p for p in pairs[:-1] if 300 <=
                       (parsed_date(curr[1]) - parsed_date(p[1])).days <= 400]
    require(bool(prev_candidates), "PRIOR_COMPARABLE_FISCAL_YEAR_MISSING")
    prev = prev_candidates[-1]
    result = {}
    for period in (prev, curr):
        line = {metric: periods[period] for metric, periods in all_periods.items()}
        line["fcf_proxy"] = line["operating_cash_flow"] - line["capex"]
        result[period[1]] = line
    return [prev[1], curr[1]], result, chosen_tags


def analyze(source: dict, approved_symbols: set[str] | frozenset[str]) -> dict:
    """Pure offline analysis. Never upgrades externally supplied data to live PASS."""
    require(type(source) is dict and source.get("schema") == INPUT_SCHEMA,
            "INPUT_SCHEMA_INVALID")
    ticker, cik = source.get("ticker"), source.get("cik")
    require(type(ticker) is str and TICKER_RE.fullmatch(ticker) is not None,
            "TICKER_MALFORMED")
    require(ticker in approved_symbols, "TICKER_NOT_IN_APPROVED_477")
    require(type(cik) is str and CIK_RE.fullmatch(cik) is not None and int(cik) > 0,
            "CIK_MALFORMED")
    cutoff, observed = timestamp(source.get("asof_utc")), timestamp(source.get("observed_at_utc"))
    require(observed <= cutoff, "SOURCE_OBSERVED_AFTER_CUTOFF")
    filing = _filing_record(source.get("submissions"), cik, ticker, cutoff)
    if parsed_date(filing["filed"]) > cutoff.date():
        raise ShadowHold("FILING_DATE_AFTER_CUTOFF")
    headers = source.get("filing_headers")
    header = headers.get(filing["accn"]) if type(headers) is dict else None
    require(type(header) is dict, "ACCEPTANCE_HEADER_MISSING")
    header_seen = timestamp(header.get("observed_at_utc"))
    require(header_seen <= cutoff, "HEADER_OBSERVED_AFTER_CUTOFF")
    accepted = accepted_header(header.get("raw"), filing["accn"], cik)
    require(accepted <= cutoff, "FILING_NOT_ACCEPTED_BY_CUTOFF")
    periods, metrics, tags = _annual_metrics(source.get("companyfacts"), cik, filing, cutoff)
    previous, current = periods
    growth = {}
    for key in ("revenue", "operating_cash_flow", "capex", "net_income"):
        before, after = metrics[previous][key], metrics[current][key]
        require(before > 0, "BASE_PERIOD_NONPOSITIVE_GROWTH")
        growth[key] = float((Decimal(after - before) * Decimal(100) / Decimal(before))
                            .quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN))
    # Exclude all mutable computed fields from signing; canonical input only.
    payload = json.dumps(source, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
    require(len(payload.encode("utf-8")) <= MAX_RAW_SIZE, "INPUT_TOO_LARGE")
    source_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    claims = []
    for key in ("revenue", "operating_cash_flow", "capex", "net_income"):
        claims.append({"claim_id": f"{ticker}|{filing['accn']}|{key}|YOY",
                       "classification": "CALCULATED_FACT_FROM_UNTRUSTED_CAPTURE",
                       "periods": periods, "unit": "percent", "value": growth[key],
                       "taxonomy": "us-gaap", "concept": tags[key],
                       "filing_accession": filing["accn"]})
    claims.append({"claim_id": f"{ticker}|{filing['accn']}|FCF_PROXY",
                   "classification": "CALCULATED_FACT_FROM_UNTRUSTED_CAPTURE",
                   "unit": "USD", "period": current,
                   "value": metrics[current]["fcf_proxy"],
                   "formula": "operating_cash_flow - capex",
                   "filing_accession": filing["accn"]})
    return {"schema": OUTPUT_SCHEMA, "status": "OFFLINE_STRUCTURE_PASS_NOT_LIVE",
            "authority": "RESEARCH_ONLY", "ticker": ticker, "cik": cik,
            "asof_utc": cutoff.isoformat(), "observed_at_utc": observed.isoformat(),
            "filing_accession": filing["accn"], "filing_date": filing["filed"],
            "accepted_header_utc": accepted.isoformat(),
            "annual_periods": periods, "metrics_usd": metrics,
            "growth_pct": growth, "source_tags": tags,
            "claims": claims, "input_sha256": source_hash,
            "independent_sec_origin_proven": False,
            "historical_pit_proven": False,
            "current_ticker_identity_not_historical": True,
            "sec_submissions_clock_not_used_for_pit": True,
            "may_change_al": False, "may_change_stop_or_target": False,
            "may_write_sheet": False, "may_send_alert": False,
            "may_trade": False,
            "limitations": [
                "Offline payload origin is untrusted until independent SEC fetch evidence.",
                "SEC header acceptance is not independent first-public-availability proof.",
                "Present-day ticker to CIK mapping does not prove historical issuer identity.",
                "No quarterly normalization, restatement/revision or backtest admission.",
                "FCF proxy excludes leasing and broader commitments.",
            ]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict offline SEC fundamental research HOLD gate")
    parser.add_argument("--input", required=True, type=Path,
                        help="Local private JSON; never commit raw SEC payloads")
    parser.add_argument("--watchlist", required=True, type=Path)
    parser.add_argument("--out", type=Path,
                        help="Optional LOCAL private research JSON, never public CI artifact")
    args = parser.parse_args()
    try:
        source = json.loads(args.input.read_text(encoding="utf-8"))
        result = analyze(source, load_watchlist(args.watchlist))
        if args.out:
            require(not args.out.is_symlink(), "OUTPUT_SYMLINK_FORBIDDEN")
            require(not args.out.exists(), "OUTPUT_ALREADY_EXISTS")
            with args.out.open("x", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
                f.write("\n")
        print("FUNDAMENTAL_SHADOW=OFFLINE_STRUCTURE_PASS_NOT_LIVE;NO_AL;NO_ORDER")
        return 0
    except (ShadowHold, ValueError, OSError, json.JSONDecodeError) as exc:
        # Redact all input details; only fixed HOLD status in shared logs.
        print("FUNDAMENTAL_SHADOW=HOLD;NO_AL;NO_ORDER")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
