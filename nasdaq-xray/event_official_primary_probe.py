#!/usr/bin/env python3
"""Zero-dollar issuer-primary Event discovery probe.

This probe is intentionally NON-AUTHORITATIVE for canonical Event state.
It may emit candidate evidence only after live issuer-controlled IR validation.
It never infers CLEAR from missing/empty calendars, HTTP failures, or provider absence.

EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN != PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUEST = ROOT / "canonical_current_event_request.json"
EVENT_STATE = ROOT / "canonical_current_event_state.json"
SEEDS = ROOT / "event_ir_seed_registry.json"
OUT = ROOT / "event_official_primary_probe_state.json"
TASK_ID = "6a825366222081918997094d76e6ae46"
UA = "NASDAQ-SWING-XRAY/1.0 research contact=https://github.com/gokaydonmez39-jpg/kripto-radar"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
MONTH_RE = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATE_PATTERNS = [
    re.compile(MONTH_RE + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})", re.I),
    re.compile(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})"),
    re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](20\d{2})(?!\d)"),
]
MONTH_DAY_NO_YEAR_RE = re.compile(
    MONTH_RE + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?!\d)(?!\s*[,]?\s*20\d{2})",
    re.I,
)
EARNINGS_RE = re.compile(
    r"earnings|financial\s+results|quarterly\s+results|results\s+conference\s+call|"
    r"report(?:ing)?\s+(?:date|.*?results)|announce.*?results",
    re.I,
)
SCHEDULE_RE = re.compile(
    r"will\s+(?:release|report|announce|host)|to\s+(?:release|report|announce|host)|"
    r"reporting\s+date|results\s+on|earnings\s+call\s+on",
    re.I,
)
RSS_HINT_RE = re.compile(r"rss|atom|feed", re.I)
IR_SECTION_RE = re.compile(
    r"news(?:-|\s)?releases?|press(?:-|\s)?releases?|events?(?:-|\s)?presentations?|"
    r"quarterly(?:-|\s)?results?|financial(?:-|\s)?results?",
    re.I,
)
DISCRETE_PATH_RE = re.compile(
    r"news-release-details|news-details|press-releases?/detail|press-release-details|"
    r"events?/event-details|event-details|/detail/",
    re.I,
)

def blob_sha(path: Path) -> str:
    b = path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode() + b).hexdigest()

def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def fetch(url: str, *, accept: str = "*/*", timeout: int = 16) -> tuple[bytes, dict]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": accept,
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(3_000_000)
        return body, {
            "status": int(getattr(r, "status", 200)),
            "content_type": str(r.headers.get("Content-Type") or ""),
            "final_url": str(r.geturl()),
        }

def fetch_json(url: str) -> tuple[dict, dict]:
    body, meta = fetch(url, accept="application/json")
    return json.loads(body.decode("utf-8")), meta

def host(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").lower().strip(".")

def same_host(a: str, b: str) -> bool:
    return bool(host(a)) and host(a) == host(b)

def valid_http_url(url: str) -> bool:
    try:
        p = urllib.parse.urlparse(url)
        return p.scheme in {"http", "https"} and bool(p.hostname)
    except Exception:
        return False

def date_spans_in_text(text: str) -> list[tuple[int, str]]:
    out = {}
    for pat_i, pat in enumerate(DATE_PATTERNS):
        for m in pat.finditer(text or ""):
            try:
                if pat_i == 0:
                    mon = MONTHS[m.group(1).lower().rstrip(".")[:3]]
                    d = date(int(m.group(3)), mon, int(m.group(2)))
                elif pat_i == 1:
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                else:
                    d = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
                out[(m.start(), d.isoformat())] = None
            except Exception:
                continue
    return sorted(out)


def dates_in_text(text: str) -> list[str]:
    return sorted({d for _, d in date_spans_in_text(text)})

def split_sentences_preserving_month_abbrev(text: str) -> list[str]:
    """Split prose without treating Jan./Feb./.../Dec. as sentence boundaries."""
    pat = re.compile(r"\b(Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.", re.I)
    marker = "__XRAY_MONTH_DOT__"
    masked = pat.sub(lambda m: m.group(1) + marker, text or "")
    return [
        s.replace(marker, ".")
        for s in re.split(r"(?<=[.!?])\s+|[\r\n]+", masked)
        if s
    ]

def announced_event_date(title: str, body: str, asof: str) -> tuple[str | None, str | None]:
    """Extract an explicit future event date, avoiding article publication dates.

    Preference:
      1) a future date explicitly present in an earnings/results title;
      2) a future date in a sentence containing both earnings context and scheduling language.
    """
    if EARNINGS_RE.search(title or ""):
        future = [d for d in dates_in_text(title) if d > asof]
        if future:
            return min(future), "TITLE_EXPLICIT_FUTURE_DATE"
    clean = normalize_text(body)
    sentences = split_sentences_preserving_month_abbrev(clean)
    hits = []
    for s in sentences:
        if not EARNINGS_RE.search(s):
            continue
        schedule_matches = list(SCHEDULE_RE.finditer(s))
        if not schedule_matches:
            continue
        # A press-release publication dateline can precede the actual scheduling
        # clause in the same flattened HTML sentence, e.g.
        # "NEW YORK, Oct. 07, 2026 ... will release ... October 27, 2026".
        # Only dates at/after scheduling language are eligible event dates.
        for sm in schedule_matches:
            tail = s[sm.end():]
            # Preserve textual order: take the first future date after the
            # scheduling clause, not the numerically earliest date anywhere
            # later in flattened HTML. Historical fiscal-period dates are
            # skipped; publication datelines before the verb are unreachable.
            for _, d in date_spans_in_text(tail):
                if d > asof:
                    hits.append((d, s[:500]))
                    break
    if hits:
        hits.sort(key=lambda x: x[0])
        return hits[0][0], "SCHEDULE_SENTENCE_EXPLICIT_FUTURE_DATE"

    # HTML templates can flatten a discrete issuer release so aggressively that
    # the visible scheduling clause is split away from sentence punctuation.
    # As a bounded fallback, accept only the first future FULL date after a
    # scheduling verb when (a) earnings/results context remains in the same
    # short clause and (b) no sentence boundary occurs before that date.
    # This never uses URL dates, calendar ordering, or unrelated future dates.
    for sm in SCHEDULE_RE.finditer(clean):
        tail = clean[sm.end(): sm.end() + 260]
        for pos, d in date_spans_in_text(tail):
            if d <= asof:
                continue
            before_date = tail[:pos]
            if len(before_date) > 180:
                break
            # Do not cross into a later sentence/event.
            if re.search(r"[!?]|\.(?:\s|$)", before_date):
                break
            context = clean[max(0, sm.start() - 120): sm.end()] + before_date
            if not EARNINGS_RE.search(context):
                break
            return d, "SCHEDULE_CLAUSE_EXPLICIT_FUTURE_DATE"

    # Some issuer-primary releases state an explicit month/day in scheduling
    # language while omitting the year (for example "earnings call on Nov. 3").
    # Resolve the year only when the SAME issuer document contains a recent
    # full calendar date at/before ASOF. This completes an explicit date from
    # document context; it does not estimate an earnings date. Old archive pages,
    # missing schedule language, or ambiguous/missing recent context stay UNKNOWN.
    asof_date = date.fromisoformat(asof)
    recent_context_dates = []
    for _, d in date_spans_in_text(clean):
        try:
            ctx = date.fromisoformat(d)
        except Exception:
            continue
        age_days = (asof_date - ctx).days
        if 0 <= age_days <= 14:
            recent_context_dates.append(ctx)
    if recent_context_dates:
        context_date = max(recent_context_dates)
        for s in sentences:
            if not EARNINGS_RE.search(s):
                continue
            schedule_matches = list(SCHEDULE_RE.finditer(s))
            if not schedule_matches:
                continue
            for sm in schedule_matches:
                tail = s[sm.end():]
                for m in MONTH_DAY_NO_YEAR_RE.finditer(tail):
                    try:
                        mon = MONTHS[m.group(1).lower().rstrip(".")[:3]]
                        day = int(m.group(2))
                        candidate = date(context_date.year, mon, day)
                        if candidate < context_date:
                            candidate = date(context_date.year + 1, mon, day)
                    except Exception:
                        continue
                    distance = (candidate - context_date).days
                    if candidate > asof_date and 0 < distance <= 180:
                        return candidate.isoformat(), "SCHEDULE_SENTENCE_EXPLICIT_MONTH_DAY_CONTEXT_YEAR"
    return None, None

def discover_feed_links(base_url: str, page: str) -> list[str]:
    links = set()
    for m in re.finditer(r"<(?:link|a)\b[^>]*(?:href|src)=[\"']([^\"']+)[\"'][^>]*>", page or "", re.I):
        raw = html.unescape(m.group(1).strip())
        tag = m.group(0)
        if not (RSS_HINT_RE.search(raw) or RSS_HINT_RE.search(tag)):
            continue
        u = urllib.parse.urljoin(base_url, raw)
        if valid_http_url(u) and same_host(base_url, u):
            links.add(u)
    root = f"{urllib.parse.urlparse(base_url).scheme}://{host(base_url)}"
    for p in [
        "/rss/news-releases.xml",
        "/rss/pressrelease.aspx",
        "/rss/event.aspx",
        "/rss/events.xml",
        "/rss/news.xml",
    ]:
        links.add(root + p)
    return sorted(links)

def discover_ir_document_links(base_url: str, page: str) -> dict[str, list[str]]:
    """Discover issuer-controlled section and discrete document URLs.

    Landing/section pages are discovery-only.  Only discrete documents may later
    emit Event evidence after an independent live fetch and issuer-identity check.
    """
    sections = set()
    discrete = set()
    for m in re.finditer(
        r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        page or "",
        re.I | re.S,
    ):
        raw = html.unescape(m.group(1).strip())
        label = normalize_text(m.group(2))
        u = urllib.parse.urljoin(base_url, raw)
        if not (valid_http_url(u) and same_host(base_url, u)):
            continue
        surface = f"{label} {urllib.parse.urlparse(u).path}".strip()
        if DISCRETE_PATH_RE.search(surface) or EARNINGS_RE.search(surface):
            discrete.add(u)
        elif IR_SECTION_RE.search(surface):
            sections.add(u)
    return {"sections": sorted(sections), "discrete": sorted(discrete)}

def _page_title(page: str) -> str:
    for pat in (
        r"<h1\b[^>]*>(.*?)</h1>",
        r"<title\b[^>]*>(.*?)</title>",
    ):
        m = re.search(pat, page or "", re.I | re.S)
        if m:
            return normalize_text(m.group(1))
    return ""

def _discrete_event_match(
    authority_url: str,
    document_url: str,
    tokens: list[str],
    asof: str,
    horizon: set[str],
) -> tuple[dict | None, dict]:
    attempt = {"url": document_url}
    try:
        raw, meta = fetch(
            document_url,
            accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
        )
        attempt.update(meta)
        page = raw.decode("utf-8", "ignore")
        if not same_host(authority_url, meta["final_url"]):
            # document_url reached this function only through an issuer-controlled
            # discovery surface (same-host IR link or prior canonical issuer-primary
            # evidence). A cross-host final may therefore be accepted only after the
            # redirected content independently proves issuer identity.
            redirected_authority = validated_authority_url(meta["final_url"], page, tokens)
            if redirected_authority is None:
                attempt["result"] = "CROSS_HOST_REDIRECT_REJECTED"
                return None, attempt
            attempt["cross_host_redirect_identity_validated"] = True
            attempt["validated_authority_url"] = redirected_authority
        if not issuer_identity_ok(page, tokens):
            attempt["result"] = "ISSUER_IDENTITY_TOKEN_NOT_FOUND"
            return None, attempt
        title = _page_title(page)
        flat = normalize_text(page)
        if not EARNINGS_RE.search(f"{title} {flat}"):
            attempt["result"] = "NO_EARNINGS_CONTEXT"
            return None, attempt
        future_dates_seen = [d for d in dates_in_text(f"{title} {flat}") if d > asof]
        if future_dates_seen:
            attempt["future_dates_seen"] = future_dates_seen[:12]
        event_date, basis = announced_event_date(title, page, asof)
        if not event_date:
            attempt["result"] = "NO_EXPLICIT_FUTURE_EVENT_DATE"
            return None, attempt
        result = (
            "INSIDE_EXACT_8_SESSION_HORIZON"
            if event_date in horizon
            else (
                "OUTSIDE_EXACT_8_SESSION_HORIZON"
                if event_date > max(horizon)
                else "NON_DECISION_DATE"
            )
        )
        attempt["result"] = "MATCH"
        return {
            "event_date": event_date,
            "horizon_result": result,
            "authority": "ISSUER_IR_PRIMARY",
            "source_url": meta["final_url"],
            "document_kind": "DISCRETE_ISSUER_IR_DOCUMENT",
            "title": title[:500],
            "extraction_basis": basis,
        }, attempt
    except Exception as e:
        attempt["result"] = f"{type(e).__name__}:{str(e)[:140]}"
        return None, attempt

def feed_items(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    items = []
    nodes = list(root.findall(".//item"))
    if not nodes:
        nodes = [n for n in root.iter() if str(n.tag).lower().endswith("entry")]
    for node in nodes[:100]:
        vals = {}
        for child in list(node):
            tag = str(child.tag).split("}")[-1].lower()
            txt = "".join(child.itertext()).strip()
            if tag == "link" and not txt:
                txt = str(child.attrib.get("href") or "")
            vals.setdefault(tag, txt)
        title = vals.get("title", "")
        body = vals.get("description") or vals.get("summary") or vals.get("content") or ""
        link = vals.get("link", "")
        items.append({"title": normalize_text(title), "body": body, "link": link})
    return items

def issuer_identity_ok(page_text: str, tokens: list[str]) -> bool:
    clean = normalize_text(page_text).lower()
    return any(str(t).lower() in clean for t in tokens if t)

def validated_authority_url(final_url: str, page_text: str, tokens: list[str]) -> str | None:
    """Trust a redirected issuer host only after issuer identity is present there.

    This permits an issuer-controlled IR migration (for example, an IR vanity
    domain redirecting to its hosted GCS-Web property) without permitting later
    feed/item redirects to arbitrary hosts.
    """
    if not valid_http_url(final_url):
        return None
    return final_url if issuer_identity_ok(page_text, tokens) else None

def sec_symbol_map() -> dict[str, dict]:
    obj, _ = fetch_json(SEC_TICKERS)
    fields = obj.get("fields") or []
    idx = {k: i for i, k in enumerate(fields)}
    out = {}
    for row in obj.get("data") or []:
        try:
            sym = str(row[idx["ticker"]]).upper().strip()
            if not sym:
                continue
            out[sym] = {
                "cik": int(row[idx["cik"]]),
                "name": str(row[idx["name"]]),
                "exchange": str(row[idx["exchange"]]),
            }
        except Exception:
            continue
    return out

def seed_candidates(sym: str, seed_obj: dict, event_state: dict, submissions: dict | None) -> list[dict]:
    out = []
    rec = ((seed_obj.get("symbols") or {}).get(sym) or {})
    if valid_http_url(str(rec.get("base_url") or "")):
        out.append({
            "url": rec["base_url"],
            "issuer_tokens": list(rec.get("issuer_tokens") or [sym]),
            "source": "DISCOVERY_SEED_REGISTRY",
        })
    clearance = ((event_state.get("official_horizon_clearance") or {}).get(sym) or {})
    u = str(clearance.get("official_source_url") or "")
    if valid_http_url(u):
        p = urllib.parse.urlparse(u)
        out.append({
            "url": f"{p.scheme}://{p.netloc}",
            "issuer_tokens": list(rec.get("issuer_tokens") or [sym]),
            "source": "PRIOR_CANONICAL_ISSUER_PRIMARY_HOST",
            # Re-fetch the exact prior primary evidence document.  This is only
            # a discovery candidate: _discrete_event_match independently
            # validates issuer identity and extracts an explicit future date.
            "known_document_urls": [u],
        })
    if submissions:
        for k in ("investorWebsite", "website"):
            u = str(submissions.get(k) or "").strip()
            if valid_http_url(u):
                tokens = list(rec.get("issuer_tokens") or [])
                name = str(submissions.get("name") or "").strip()
                if name:
                    tokens.append(name.split(",")[0])
                out.append({
                    "url": u,
                    "issuer_tokens": tokens or [sym],
                    "source": f"SEC_SUBMISSIONS_{k.upper()}_DISCOVERY",
                })
    uniq = {}
    for row in out:
        uniq[(host(row["url"]), row["source"])] = row
    return list(uniq.values())

def _document_priority(url: str, known_urls: set[str]) -> tuple:
    """Rank bounded issuer documents for coverage only; never classify from URL metadata."""
    s = urllib.parse.unquote(str(url)).lower()
    financial = 1 if re.search(r"(earnings|financial[-_/ ]results|quarter|fiscal)", s) else 0
    date_values = []
    for m in re.finditer(r"(?<!\\d)(20\\d{2})[-_/]?(0[1-9]|1[0-2])[-_/]?([0-3]\\d)(?!\\d)", s):
        try:
            date_values.append(int("".join(m.groups())))
        except Exception:
            pass
    detail_values = []
    for m in re.finditer(r"/(?:detail|news-release-details?)/(\\d{3,})(?:/|$)", s):
        try:
            detail_values.append(int(m.group(1)))
        except Exception:
            pass
    return (
        1 if url in known_urls else 0,
        financial,
        max(date_values, default=0),
        max(detail_values, default=0),
        s,
    )

def ranked_discrete_document_urls(urls, known_urls=None) -> list[str]:
    """Deterministically prioritize recent/relevant documents inside the fixed fetch budget.

    URL metadata affects discovery order only.  A URL can never create Event evidence:
    every selected document still requires live fetch, same-host/identity validation,
    and an explicit future earnings/results date in issuer-controlled document text.
    """
    known = set(known_urls or [])
    return sorted(
        set(str(u) for u in urls if str(u)),
        key=lambda u: _document_priority(u, known),
        reverse=True,
    )

def probe_issuer(sym: str, base: dict, asof: str, horizon: set[str]) -> dict:
    url = base["url"]
    rec = {
        "base_url": url,
        "discovery_source": base["source"],
        "identity_validated": False,
        "feed_attempts": [],
        "section_attempts": [],
        "document_attempts": [],
        "matches": [],
    }
    try:
        body, meta = fetch(url, accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        text = body.decode("utf-8", "ignore")
        rec["base_fetch"] = meta
        authority_url = validated_authority_url(
            meta["final_url"], text, base.get("issuer_tokens") or [sym]
        )
        rec["identity_validated"] = authority_url is not None
        if not rec["identity_validated"]:
            rec["failure"] = "ISSUER_IDENTITY_TOKEN_NOT_FOUND"
            return rec
        rec["validated_authority_url"] = authority_url
        # Issuer landing pages are discovery/identity surfaces only. Flattened
        # HTML can concatenate card publication dates with unrelated earnings
        # text and create false event dates. Decision evidence must come from a
        # discrete issuer-controlled feed item or specific event/news document.
        rec["base_page_event_policy"] = "DISCOVERY_ONLY_NO_EVENT_DATE_DECISION"
        feeds = discover_feed_links(authority_url, text)
        ir_links = discover_ir_document_links(authority_url, text)
    except Exception as e:
        rec["failure"] = f"BASE_FETCH_{type(e).__name__}:{str(e)[:160]}"
        return rec

    for feed_url in feeds[:12]:
        attempt = {"url": feed_url}
        try:
            raw, meta = fetch(feed_url, accept="application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.3")
            attempt.update(meta)
            feed_text = raw.decode("utf-8", "ignore")
            feed_authority_url = meta["final_url"]
            if not same_host(authority_url, feed_authority_url):
                # Feed URL itself was discovered on the validated issuer IR host.
                # Accept its hosted-provider redirect only when the returned feed
                # independently contains the issuer identity; otherwise fail closed.
                redirected_authority = validated_authority_url(
                    feed_authority_url,
                    feed_text,
                    base.get("issuer_tokens") or [sym],
                )
                if redirected_authority is None:
                    attempt["result"] = "CROSS_HOST_REDIRECT_REJECTED"
                    rec["feed_attempts"].append(attempt)
                    continue
                feed_authority_url = redirected_authority
                attempt["cross_host_redirect_identity_validated"] = True
                attempt["validated_authority_url"] = feed_authority_url
            items = feed_items(raw)
            attempt["parsed_items"] = len(items)
            for item in items:
                if not EARNINGS_RE.search(item.get("title", "") + " " + normalize_text(item.get("body", ""))):
                    continue
                event_date, basis = announced_event_date(item.get("title", ""), item.get("body", ""), asof)
                if not event_date:
                    continue
                link = urllib.parse.urljoin(feed_authority_url, item.get("link") or feed_authority_url)
                if not (same_host(authority_url, link) or same_host(feed_authority_url, link)):
                    continue
                rec["matches"].append({
                    "event_date": event_date,
                    "horizon_result": "INSIDE_EXACT_8_SESSION_HORIZON" if event_date in horizon else
                                      ("OUTSIDE_EXACT_8_SESSION_HORIZON" if event_date > max(horizon) else "NON_DECISION_DATE"),
                    "authority": "ISSUER_IR_PRIMARY",
                    "source_url": link,
                    "feed_url": feed_authority_url,
                    "title": item.get("title", "")[:500],
                    "extraction_basis": basis,
                })
            attempt["result"] = "PARSED"
        except Exception as e:
            attempt["result"] = f"{type(e).__name__}:{str(e)[:140]}"
        rec["feed_attempts"].append(attempt)
        time.sleep(0.05)

    # Two-hop issuer-IR fan-out: landing -> section (discovery only) -> discrete
    # issuer document.  Neither landing nor section HTML can directly classify
    # an Event.  Every discrete page is fetched independently and identity-
    # validated before an explicit future date can become candidate evidence.
    discrete = set(base.get("known_document_urls") or [])
    discrete.update(ir_links.get("discrete") or [])
    for section_url in (ir_links.get("sections") or [])[:8]:
        section_attempt = {"url": section_url}
        try:
            raw, meta = fetch(
                section_url,
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
            )
            section_attempt.update(meta)
            page = raw.decode("utf-8", "ignore")
            section_authority_url = meta["final_url"]
            if not same_host(authority_url, section_authority_url):
                redirected_authority = validated_authority_url(
                    section_authority_url,
                    page,
                    base.get("issuer_tokens") or [sym],
                )
                if redirected_authority is None:
                    section_attempt["result"] = "CROSS_HOST_REDIRECT_REJECTED"
                    section_authority_url = None
                else:
                    section_authority_url = redirected_authority
                    section_attempt["cross_host_redirect_identity_validated"] = True
                    section_attempt["validated_authority_url"] = section_authority_url
            if section_authority_url is not None:
                if not issuer_identity_ok(page, base.get("issuer_tokens") or [sym]):
                    section_attempt["result"] = "ISSUER_IDENTITY_TOKEN_NOT_FOUND"
                else:
                    discovered = discover_ir_document_links(section_authority_url, page)
                    discrete.update(discovered.get("discrete") or [])
                    section_attempt["discrete_discovered"] = len(discovered.get("discrete") or [])
                    section_attempt["result"] = "DISCOVERY_ONLY_PARSED"
        except Exception as e:
            section_attempt["result"] = f"{type(e).__name__}:{str(e)[:140]}"
        rec["section_attempts"].append(section_attempt)
        time.sleep(0.05)

    ranked_discrete = ranked_discrete_document_urls(
        discrete,
        base.get("known_document_urls") or [],
    )
    rec["document_candidate_count"] = len(ranked_discrete)
    rec["document_attempt_limit"] = 24
    rec["document_truncated"] = len(ranked_discrete) > 24
    for document_url in ranked_discrete[:24]:
        match, attempt = _discrete_event_match(
            authority_url,
            document_url,
            base.get("issuer_tokens") or [sym],
            asof,
            horizon,
        )
        rec["document_attempts"].append(attempt)
        if match is not None:
            rec["matches"].append(match)
        time.sleep(0.05)
    return rec

UNRESOLVED_REASON_ENUM = {
    "NO_BASE",
    "BASE_FETCH_FAIL",
    "ISSUER_IDENTITY_TOKEN_FAIL",
    "NO_RSS_FEED",
    "FEED_FETCH_FAIL",
    "CROSS_HOST_REDIRECT_REJECTED",
    "RSS_PARSED_NO_EXPLICIT_EVENT_DATE",
    "IR_PAGE_HAS_DATE_BUT_CURRENT_PROBE_DOES_NOT_PARSE_HTML",
    "SEC_TRANSPORT_403",
    "OTHER",
}

def classify_unresolved_reason(
    issuer_probes: list[dict],
    sec_submissions_error: str | None = None,
    sec_ticker_map_error: str | None = None,
) -> str:
    """Normalize non-authoritative probe failures without changing Event decisions."""
    sec_errors = " ".join(
        str(x or "") for x in (sec_submissions_error, sec_ticker_map_error)
    ).upper()
    if not issuer_probes:
        return "SEC_TRANSPORT_403" if "403" in sec_errors else "NO_BASE"

    valid = [p for p in issuer_probes if p.get("identity_validated") is True]
    if not valid:
        failures = " ".join(str(p.get("failure") or "") for p in issuer_probes).upper()
        if "BASE_FETCH_" in failures:
            return "BASE_FETCH_FAIL"
        if "ISSUER_IDENTITY_TOKEN_NOT_FOUND" in failures:
            return "ISSUER_IDENTITY_TOKEN_FAIL"
        return "OTHER"

    feed_attempts = [a for p in valid for a in (p.get("feed_attempts") or [])]
    section_attempts = [a for p in valid for a in (p.get("section_attempts") or [])]
    document_attempts = [a for p in valid for a in (p.get("document_attempts") or [])]
    all_attempts = feed_attempts + section_attempts + document_attempts

    if any(
        a.get("result") == "NO_EXPLICIT_FUTURE_EVENT_DATE"
        and bool(a.get("future_dates_seen"))
        for a in document_attempts
    ):
        return "IR_PAGE_HAS_DATE_BUT_CURRENT_PROBE_DOES_NOT_PARSE_HTML"

    if feed_attempts and any(a.get("result") == "PARSED" for a in feed_attempts):
        return "RSS_PARSED_NO_EXPLICIT_EVENT_DATE"

    if any(a.get("result") == "CROSS_HOST_REDIRECT_REJECTED" for a in all_attempts):
        return "CROSS_HOST_REDIRECT_REJECTED"

    if not feed_attempts:
        return "NO_RSS_FEED"

    if all(a.get("result") != "PARSED" for a in feed_attempts):
        return "FEED_FETCH_FAIL"

    return "OTHER"

def selftest() -> None:
    asof = "2026-10-06"
    d, basis = announced_event_date(
        "Lumentum Announces Reporting Date for Fiscal First Quarter 2027 Financial Results on November 5, 2026",
        "",
        asof,
    )
    assert d == "2026-11-05" and basis == "TITLE_EXPLICIT_FUTURE_DATE", (d, basis)
    d2, _ = announced_event_date(
        "Investor Events",
        "The company will release its third quarter 2026 financial results on October 14, 2026.",
        asof,
    )
    assert d2 == "2026-10-14", d2
    d3, _ = announced_event_date(
        "Upcoming Events",
        "Stay tuned for upcoming events. No date has been announced.",
        asof,
    )
    assert d3 is None, d3
    d4, basis4 = announced_event_date(
        "Release Details",
        "EXL schedules third quarter 2026 financial results conference call October 07, 2026 "
        "NEW YORK, Oct. 07, 2026 (GLOBE NEWSWIRE) -- ExlService Holdings, Inc. "
        "will release financial results for the third quarter ended September 30, 2026, "
        "on Tuesday, October 27, 2026, after the market closes. "
        "The company will host a conference call at 10:00 a.m. EDT the following day, "
        "Wednesday, October 28, 2026.",
        asof,
    )
    assert d4 == "2026-10-27" and basis4 == "SCHEDULE_SENTENCE_EXPLICIT_FUTURE_DATE", (d4, basis4)
    d5, basis5 = announced_event_date(
        "Release Details",
        "IRVINE, Calif., Oct. 05, 2026 (GLOBE NEWSWIRE) -- Skyworks announced the transaction. "
        "Skyworks will provide financial guidance on its fiscal fourth-quarter earnings call on Nov. 3.",
        asof,
    )
    assert d5 == "2026-11-03" and basis5 == "SCHEDULE_SENTENCE_EXPLICIT_MONTH_DAY_CONTEXT_YEAR", (d5, basis5)
    d6, basis6 = announced_event_date(
        "Archived Release",
        "IRVINE, Calif., Oct. 05, 2022 -- Company will provide financial guidance on its earnings call on Nov. 3.",
        asof,
    )
    assert d6 is None and basis6 is None, (d6, basis6)
    d7, basis7 = announced_event_date(
        "Release Details",
        "Company will report financial results on Nov. 3, 2026.",
        asof,
    )
    assert d7 == "2026-11-03" and basis7 == "SCHEDULE_SENTENCE_EXPLICIT_FUTURE_DATE", (d7, basis7)
    # Regression: discrete issuer HTML may flatten the release into one stream
    # where normal sentence splitting misses the visible AMD-style clause.
    d8, basis8 = announced_event_date(
        "Release Details",
        "AMD announced today that it will report fiscal third quarter 2026 financial results "
        "on Tuesday, Nov. 3, 2026 after the market close Investor Relations Navigation",
        asof,
    )
    assert d8 == "2026-11-03" and basis8 in {
        "SCHEDULE_SENTENCE_EXPLICIT_FUTURE_DATE",
        "SCHEDULE_CLAUSE_EXPLICIT_FUTURE_DATE",
    }, (d8, basis8)
    # A later unrelated event date must not leak backward across a sentence.
    d9, basis9 = announced_event_date(
        "Release Details",
        "Company will report financial results when available. "
        "The company will participate in a technology conference on Dec. 1, 2026.",
        asof,
    )
    assert d9 is None and basis9 is None, (d9, basis9)
    # Hosting a non-earnings event with a future date is not Event-clearance evidence.
    d10, basis10 = announced_event_date(
        "Release Details",
        "Company will host a technology conference on Dec. 1, 2026. "
        "Prior financial results remain available in the archive.",
        asof,
    )
    assert d10 is None and basis10 is None, (d10, basis10)
    prior_seed = seed_candidates(
        "TEST",
        {"symbols": {"TEST": {"base_url": "https://ir.example.com", "issuer_tokens": ["Example"]}}},
        {"official_horizon_clearance": {"TEST": {"official_source_url": "https://ir.example.com/news/earnings.html"}}},
        None,
    )
    prior_rows = [r for r in prior_seed if r.get("source") == "PRIOR_CANONICAL_ISSUER_PRIMARY_HOST"]
    assert len(prior_rows) == 1
    assert prior_rows[0].get("known_document_urls") == ["https://ir.example.com/news/earnings.html"]
    # Regression: full issuer landing pages are never classified directly.
    # The extractor remains valid for discrete feed/news text, but probe_issuer
    # must mark the base page as discovery-only.
    rss = b"""<?xml version="1.0"?><rss><channel><item><title>Company to report financial results on November 5, 2026</title><link>https://ir.example.com/release</link><description>Company will release financial results on November 5, 2026.</description></item></channel></rss>"""
    items = feed_items(rss)
    assert len(items) == 1 and "November 5, 2026" in items[0]["title"]
    redirected = validated_authority_url(
        "https://issuer-host.gcs-web.com/overview/default.aspx",
        "<html><title>Silicon Motion Technology Investor Relations</title></html>",
        ["Silicon Motion"],
    )
    assert redirected and host(redirected) == "issuer-host.gcs-web.com"
    assert validated_authority_url(
        "https://unrelated.example/landing",
        "<html><title>Generic landing page</title></html>",
        ["Silicon Motion"],
    ) is None
    assert not same_host("https://ir.siliconmotion.com", redirected)
    redirected_feed = validated_authority_url(
        "https://feeds.gcs-web.com/palantir/rss.xml",
        "<rss><channel><title>Palantir Investor Relations</title></channel></rss>",
        ["Palantir"],
    )
    assert redirected_feed and host(redirected_feed) == "feeds.gcs-web.com"
    assert validated_authority_url(
        "https://feeds.unrelated.example/rss.xml",
        "<rss><channel><title>Generic market news</title></channel></rss>",
        ["Palantir"],
    ) is None
    links = discover_ir_document_links(
        "https://ir.example.com/",
        """
        <a href="/news-releases/">All News Releases</a>
        <a href="/news-releases/news-release-details/company-to-report-financial-results-on-november-5-2026">Company to report financial results on November 5, 2026</a>
        <a href="https://other.example.com/news-release-details/fake">Company to report financial results</a>
        """,
    )
    assert links["sections"] == ["https://ir.example.com/news-releases/"], links
    assert links["discrete"] == [
        "https://ir.example.com/news-releases/news-release-details/company-to-report-financial-results-on-november-5-2026"
    ], links
    # Regression: a bounded document budget must not deterministically starve
    # newer issuer earnings documents behind lexicographically older detail IDs.
    old_docs = [
        f"https://ir.example.com/news-events/press-releases/detail/{1270+i}/generic-release"
        for i in range(30)
    ]
    latest_earnings = (
        "https://ir.example.com/news-events/press-releases/detail/1300/"
        "company-to-report-fiscal-third-quarter-2026-financial-results"
    )
    dated_event = (
        "https://ir.example.com/news-events/ir-calendar/detail/"
        "20261103-company-third-quarter-financial-results"
    )
    ranked = ranked_discrete_document_urls(old_docs + [latest_earnings, dated_event])
    assert latest_earnings in ranked[:24], ranked[:24]
    assert dated_event in ranked[:24], ranked[:24]
    ranked_known = ranked_discrete_document_urls(
        old_docs + [latest_earnings, dated_event],
        [old_docs[0]],
    )
    assert ranked_known[0] == old_docs[0], ranked_known[:3]
    assert classify_unresolved_reason([], None, "HTTPError:HTTP Error 403: Forbidden") == "SEC_TRANSPORT_403"
    assert classify_unresolved_reason([], None, None) == "NO_BASE"
    assert classify_unresolved_reason([{"identity_validated": False, "failure": "BASE_FETCH_HTTPError:x"}]) == "BASE_FETCH_FAIL"
    assert classify_unresolved_reason([{"identity_validated": False, "failure": "ISSUER_IDENTITY_TOKEN_NOT_FOUND"}]) == "ISSUER_IDENTITY_TOKEN_FAIL"
    assert classify_unresolved_reason([{"identity_validated": True, "feed_attempts": []}]) == "NO_RSS_FEED"
    assert classify_unresolved_reason([{"identity_validated": True, "feed_attempts": [{"result": "HTTPError:x"}]}]) == "FEED_FETCH_FAIL"
    assert classify_unresolved_reason([{"identity_validated": True, "feed_attempts": [{"result": "CROSS_HOST_REDIRECT_REJECTED"}]}]) == "CROSS_HOST_REDIRECT_REJECTED"
    assert classify_unresolved_reason([{"identity_validated": True, "feed_attempts": [{"result": "PARSED", "parsed_items": 3}]}]) == "RSS_PARSED_NO_EXPLICIT_EVENT_DATE"
    assert classify_unresolved_reason([{"identity_validated": True, "feed_attempts": [], "document_attempts": [{"result": "NO_EXPLICIT_FUTURE_EVENT_DATE", "future_dates_seen": ["2026-10-20"]}]}]) == "IR_PAGE_HAS_DATE_BUT_CURRENT_PROBE_DOES_NOT_PARSE_HTML"
    print("EVENT_OFFICIAL_PRIMARY_PROBE_SELFTEST=PASS")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--symbols", default="")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    req = json.loads(REQUEST.read_text(encoding="utf-8"))
    ev = json.loads(EVENT_STATE.read_text(encoding="utf-8"))
    seeds = json.loads(SEEDS.read_text(encoding="utf-8"))
    assert req.get("schema") == "XRAY_EVENT_EPOCH_REQUEST_V1"
    assert ev.get("schema") == "XRAY_CANONICAL_EVENT_STATE_V1"
    assert req.get("task_id") == ev.get("task_id") == TASK_ID
    assert req.get("execution") == ev.get("execution") == "NONE"
    assert req.get("real_money") == ev.get("real_money") == "NO-GO"
    assert req.get("unknown_never_pass") is True and ev.get("unknown_never_pass") is True
    asof = str(req["asof_et"])
    horizon = set(req.get("future_horizon_sessions") or [])
    if len(horizon) != 8:
        raise RuntimeError("EXACT_8_SESSION_HORIZON_REQUIRED")

    scope = sorted(set(req.get("geometry_scope") or []))
    if args.symbols:
        requested = {x.strip().upper() for x in args.symbols.split(",") if x.strip()}
        scope = [s for s in scope if s in requested]

    secmap_error = None
    try:
        secmap = sec_symbol_map()
    except Exception as e:
        secmap = {}
        secmap_error = f"{type(e).__name__}:{str(e)[:180]}"

    results = {}
    for sym in scope:
        srec = secmap.get(sym) or {}
        submissions = None
        sec_error = None
        if srec.get("cik"):
            try:
                submissions, _ = fetch_json(SEC_SUBMISSIONS.format(cik=int(srec["cik"])))
                time.sleep(0.13)  # remain below SEC's published aggregate 10 req/s guidance
            except Exception as e:
                sec_error = f"{type(e).__name__}:{str(e)[:160]}"

        bases = seed_candidates(sym, seeds, ev, submissions)
        issuer_probes = []
        matches = []
        for base in bases[:5]:
            p = probe_issuer(sym, base, asof, horizon)
            issuer_probes.append(p)
            matches.extend(p.get("matches") or [])
            time.sleep(0.05)

        inside = sorted({m["event_date"] for m in matches if m.get("horizon_result") == "INSIDE_EXACT_8_SESSION_HORIZON"})
        outside = sorted({m["event_date"] for m in matches if m.get("horizon_result") == "OUTSIDE_EXACT_8_SESSION_HORIZON"})
        if inside:
            candidate = "BLOCK_CONFIRMED_8SESSION_CANDIDATE"
            selected = inside[0]
        elif outside:
            candidate = "CLEAN_OUTSIDE_HORIZON_CANDIDATE"
            selected = outside[0]
        else:
            candidate = "UNKNOWN_OFFICIAL_PRIMARY_UNRESOLVED"
            selected = None

        unresolved_reason = (
            classify_unresolved_reason(issuer_probes, sec_error, secmap_error)
            if candidate == "UNKNOWN_OFFICIAL_PRIMARY_UNRESOLVED"
            else None
        )
        results[sym] = {
            "status": candidate,
            "selected_event_date": selected,
            "classification_applied": False,
            "unresolved_reason": unresolved_reason,
            "sec_mapping": srec or None,
            "sec_submissions_error": sec_error,
            "issuer_probe_count": len(issuer_probes),
            "issuer_probes": issuer_probes,
        }

    counts = {}
    unresolved_reason_counts = {}
    for r in results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        reason = r.get("unresolved_reason")
        if reason:
            assert reason in UNRESOLVED_REASON_ENUM, reason
            unresolved_reason_counts[reason] = unresolved_reason_counts.get(reason, 0) + 1
    obj = {
        "schema": "XRAY_EVENT_OFFICIAL_PRIMARY_PROBE_V1",
        "authority": "NON_CANONICAL_DISCOVERY_AND_PRIMARY_EVIDENCE_CANDIDATE_ONLY",
        "task_id": TASK_ID,
        "asof_et": asof,
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "classification_applied": False,
        "source_event_request_path": "nasdaq-xray/canonical_current_event_request.json",
        "source_event_request_blob_sha": blob_sha(REQUEST),
        "source_event_state_path": "nasdaq-xray/canonical_current_event_state.json",
        "source_event_state_blob_sha": blob_sha(EVENT_STATE),
        "source_seed_registry_path": "nasdaq-xray/event_ir_seed_registry.json",
        "source_seed_registry_blob_sha": blob_sha(SEEDS),
        "future_horizon_sessions": sorted(horizon),
        "scope": scope,
        "scope_count": len(scope),
        "sec_ticker_map_error": secmap_error,
        "counts": counts,
        "unresolved_reason_counts": dict(sorted(unresolved_reason_counts.items())),
        "results": results,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision_rule": "ONLY_EXPLICIT_ISSUER_PRIMARY_FUTURE_DATE_MAY_BECOME_SUCCESSOR_EVIDENCE;ABSENCE_OR_FETCH_FAILURE_REMAINS_UNKNOWN",
    }
    out = Path(args.out)
    out.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scope": len(scope), "counts": counts, "unresolved_reason_counts": dict(sorted(unresolved_reason_counts.items())), "out": str(out)}, sort_keys=True))

if __name__ == "__main__":
    main()
