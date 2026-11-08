#!/usr/bin/env python3
"""Explicit one-ticker SEC capture; NO cron, credentials, broker, or Sheets.

The SEC source is read-only. Caller must declare a real SEC contact identity.
This command is NOT used in PR CI and does not make historical PIT claims.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener

from fundamental_shadow import (
    INPUT_SCHEMA, ShadowHold, analyze, load_watchlist,
    parsed_date, timestamp, TICKER_RE, ACCESSION_RE,
)

MAX_BODY = 16_000_000
SEC_HOSTS = frozenset(("data.sec.gov", "www.sec.gov"))
SEC_INTERVAL_SECONDS = 1.25


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ShadowHold(code)


def safe_url(url: str) -> None:
    parsed = urlparse(url)
    require(parsed.scheme == "https" and parsed.hostname in SEC_HOSTS
            and parsed.port is None and parsed.username is None
            and parsed.password is None and not parsed.fragment
            and not parsed.query, "NON_SEC_URL_FORBIDDEN")
    require(bool(re.fullmatch(r"/submissions/CIK[0-9]{10}\.json|"
                              r"/api/xbrl/companyfacts/CIK[0-9]{10}\.json",
                              parsed.path)) if parsed.hostname == "data.sec.gov" else
            bool(re.fullmatch(r"/Archives/edgar/data/[0-9]{1,10}/"
                              r"[0-9]{18}/[0-9]{10}-[0-9]{2}-[0-9]{6}-index-headers\.html",
                              parsed.path)), "SEC_PATH_NOT_APPROVED")


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ShadowHold("SEC_REDIRECT_BLOCKED")


def default_transport(request: Request, timeout: float) -> bytes:
    try:
        with build_opener(_RejectRedirect()).open(request, timeout=timeout) as response:
            require(response.status == 200, "SEC_NON_200")
            require(response.headers.get("Content-Encoding", "identity") == "identity",
                    "SEC_RESPONSE_ENCODING_UNSUPPORTED")
            blob = response.read(MAX_BODY + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ShadowHold("SEC_HTTP_UNAVAILABLE") from exc
    require(len(blob) <= MAX_BODY, "SEC_BODY_TOO_LARGE")
    return blob


class SecCapture:
    def __init__(self, *, identity: str, transport=default_transport,
                 sleeper=time.sleep, clock=time.monotonic):
        require(type(identity) is str and 8 <= len(identity) <= 200 and
                "@" in identity and " " in identity and "\n" not in identity
                and "\r" not in identity,
                "SEC_IDENTITY_REQUIRED")
        self.identity = identity
        self.transport = transport
        self.sleeper = sleeper
        self.clock = clock
        self.last_at = None

    def read(self, url: str) -> bytes:
        safe_url(url)
        if self.last_at is not None:
            elapsed = self.clock() - self.last_at
            if elapsed < SEC_INTERVAL_SECONDS:
                self.sleeper(SEC_INTERVAL_SECONDS - max(0, elapsed))
        req = Request(url, headers={"User-Agent": self.identity,
                                    "Accept": "application/json,text/plain,text/html",
                                    "Accept-Encoding": "identity"}, method="GET")
        self.last_at = self.clock()
        result = self.transport(req, 15.0)
        require(type(result) is bytes and 0 < len(result) <= MAX_BODY,
                "SEC_INVALID_RESPONSE")
        return result

    def json(self, url: str) -> dict:
        try:
            obj = json.loads(self.read(url).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ShadowHold("SEC_JSON_INVALID") from exc
        require(type(obj) is dict, "SEC_JSON_NOT_OBJECT")
        return obj


def capture_one(ticker: str, cik: str, cutoff_utc: str, *, client: SecCapture,
                clock_utc=None) -> dict:
    """Capture exactly one company. Caller must separately validate origin/PIT.

    Does not rely on submissions acceptanceDateTime for cutoff evidence.
    """
    require(type(ticker) is str and TICKER_RE.fullmatch(ticker) is not None,
            "TICKER_MALFORMED")
    require(type(cik) is str and re.fullmatch(r"[0-9]{10}", cik) is not None,
            "CIK_MALFORMED")
    cutoff = timestamp(cutoff_utc)
    subs = client.json(f"https://data.sec.gov/submissions/CIK{cik}.json")
    facts = client.json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    recent = subs.get("filings", {}).get("recent")
    require(type(recent) is dict, "SUBMISSIONS_RECENT_MISSING")
    keys = ("accessionNumber", "filingDate", "form")
    require(all(type(recent.get(k)) is list for k in keys),
            "SUBMISSIONS_COLUMNS_MISSING")
    lengths = [len(recent[k]) for k in keys]
    require(0 < lengths[0] <= 20000 and len(set(lengths)) == 1,
            "SUBMISSIONS_COLUMN_LENGTH_DRIFT")
    annual = sorted((parsed_date(day), accession)
                    for accession, day, form in zip(*(recent[k] for k in keys))
                    if form == "10-K" and parsed_date(day) <= cutoff.date()
                    and type(accession) is str and ACCESSION_RE.fullmatch(accession))
    require(bool(annual), "NO_ANNUAL_FILING_BY_CUTOFF")
    selected_acc = annual[-1][1]
    headers_url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                   f"{selected_acc.replace('-', '')}/{selected_acc}-index-headers.html")
    try:
        raw_header = client.read(headers_url).decode("utf-8")
    except UnicodeError as exc:
        raise ShadowHold("SEC_HEADER_ENCODING_INVALID") from exc
    now = clock_utc() if clock_utc is not None else datetime.now(timezone.utc)
    require(isinstance(now, datetime) and now.tzinfo is not None,
            "CAPTURE_CLOCK_INVALID")
    observed_at = now.astimezone(timezone.utc).isoformat()
    return {"schema": INPUT_SCHEMA, "ticker": ticker, "cik": cik,
            "asof_utc": cutoff.isoformat(), "observed_at_utc": observed_at,
            "submissions": subs, "companyfacts": facts,
            "filing_headers": {selected_acc: {
                "raw": raw_header, "observed_at_utc": observed_at,
            }}}


def main() -> int:
    parser = argparse.ArgumentParser(description="Explicit SEC one-ticker capture, no scheduled service")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--cik", required=True)
    parser.add_argument("--asof-utc", required=True, help="ISO8601 cutoff with timezone")
    parser.add_argument("--watchlist", required=True, type=Path)
    parser.add_argument("--private-output", required=True, type=Path,
                        help="LOCAL untracked path outside Git checkout only")
    args = parser.parse_args()
    try:
        allowed = load_watchlist(args.watchlist)
        require(args.ticker in allowed, "TICKER_NOT_IN_APPROVED_477")
        path = args.private_output.resolve(strict=False)
        repo_root = Path(__file__).resolve().parents[2]
        require(not path.is_relative_to(repo_root), "PUBLIC_REPO_OUTPUT_FORBIDDEN")
        require(not args.private_output.is_symlink() and not path.exists(),
                "PRIVATE_OUTPUT_EXISTS_OR_SYMLINK")
        identity = os.environ.get("XRAY_SEC_USER_AGENT", "")
        capture = capture_one(args.ticker, args.cik, args.asof_utc,
                              client=SecCapture(identity=identity))
        result = analyze(capture, allowed)
        require(result["status"] == "OFFLINE_STRUCTURE_PASS_NOT_LIVE",
                "STRUCTURAL_RESULT_NOT_PASS")
        # Deliberate local-only, create-exclusive, default privacy mode for Unix.
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump({"capture": capture, "research": result}, out,
                      ensure_ascii=False, indent=2)
            out.write("\n")
        print("SEC_FUNDAMENTAL_CAPTURE=OFFLINE_STRUCTURE_PASS_NOT_LIVE;NO_AL;NO_ORDER")
        return 0
    except (ShadowHold, ValueError, OSError, TypeError) as exc:
        # Intentionally no user identity, source prices, paths or stack in CI logs.
        print("SEC_FUNDAMENTAL_CAPTURE=HOLD;NO_AL;NO_ORDER")
        return 3


if __name__ == "__main__":
    sys.exit(main())
