"""Offline source-clock evidence for the Personal 477 research lane only.

Input rows are externally obtained observations, not authenticated by this module.
No networking, portfolio state, alerts, price changes or orders.
"""
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit


SCHEMA = "XRAY_OFFLINE_SOURCE_EVENTS_V1"
SEC_FORMS = frozenset({"8-K", "8-K/A", "10-K", "10-K/A", "10-Q", "10-Q/A",
                       "4", "4/A", "13D", "13D/A", "13G", "13G/A"})
SEC_8K_ITEMS = frozenset({"1.01", "1.02", "2.02", "2.03", "2.04", "2.05", "2.06",
                         "3.01", "3.02", "4.01", "4.02", "5.02", "7.01", "8.01", "9.01"})
FED_KINDS = frozenset({"FOMC_STATEMENT", "FOMC_PRESS_CONFERENCE", "FOMC_MINUTES"})
BLS_KINDS = frozenset({"CPI", "PPI", "EMPLOYMENT_SITUATION"})
SEC_ACC = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", re.ASCII)
SEC_CIK = re.compile(r"[0-9]{10}", re.ASCII)
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", re.ASCII)


def instant(text):
    if not isinstance(text, str) or not 20 <= len(text) <= 40:
        raise ValueError("EVENT_TIMESTAMP_INVALID")
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("EVENT_TIMESTAMP_NAIVE")
    return dt.astimezone(timezone.utc)


def official_url(url, source):
    if (not isinstance(url, str) or len(url) > 2048 or not url.isascii()
            or any(ord(c) < 33 or ord(c) == 127 for c in url)):
        raise ValueError("EVENT_SOURCE_URL")
    p = urlsplit(url)
    if (p.scheme != "https" or p.query or p.fragment
            or p.netloc not in {
                "SEC": {"www.sec.gov", "sec.gov"},
                "FED": {"www.federalreserve.gov", "federalreserve.gov"},
                "BLS": {"www.bls.gov", "bls.gov"},
            }[source]
            or not re.fullmatch(r"/[A-Za-z0-9/._-]+", p.path)
            or any(part in {".", ".."} for part in p.path.split("/"))):
        raise ValueError("EVENT_SOURCE_URL")
    return p.path


def normalize(row, observed):
    source, kind = row["source"], row["kind"]
    url = row["url"]
    if source not in {"SEC", "FED", "BLS"}:
        raise ValueError("EVENT_SOURCE_UNSUPPORTED")
    path = official_url(url, source)
    status = row["status"]
    scheduled = published = accepted = None
    if source == "SEC":
        accession, cik = row["accession"], row["issuer_cik"]
        if (not SEC_ACC.fullmatch(accession) or not SEC_CIK.fullmatch(cik)
                or not int(cik) or kind not in SEC_FORMS or status != "OBSERVED"):
            raise ValueError("EVENT_SEC_IDENTITY")
        if not path.startswith(f"/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"):
            raise ValueError("EVENT_SEC_DOCUMENT_PATH")
        accepted = instant(row["accepted_at"])
        if accepted > observed:
            raise ValueError("EVENT_SEC_ACCEPTED_AFTER_OBSERVATION")
        item = row.get("item")
        if item is not None and (kind not in {"8-K", "8-K/A"} or item not in SEC_8K_ITEMS):
            raise ValueError("EVENT_SEC_ITEM")
        # One accession can legitimately contain multiple separate items.
        key = f"SEC|{cik}|{accession}|{item or 'FORM'}"
        extra = {"issuer_cik": cik, "accession": accession, "item": item,
                 "label": "SEC_EARNINGS_DISCLOSURE" if item == "2.02" else "SEC_FILING_REVIEW",
                 "first_publication_proven": False}
    else:
        native = row["event_id"]
        allowed = FED_KINDS if source == "FED" else BLS_KINDS
        prefix = ("/monetarypolicy/", "/newsevents/") if source == "FED" else ("/schedule/", "/news.release/")
        if (not KEY.fullmatch(native) or kind not in allowed or not path.startswith(prefix)):
            raise ValueError("EVENT_MACRO_IDENTITY")
        key = f"{source}|{kind}|{native}"
        if status == "SCHEDULED":
            scheduled = instant(row["scheduled_at"])
            if row.get("published_at") is not None:
                raise ValueError("EVENT_SCHEDULE_IS_NOT_PUBLICATION")
        elif status == "PUBLISHED":
            # Calendar pages describe future plans, not an actual release.
            if path.startswith("/schedule/") or path.endswith("/fomccalendars.htm"):
                raise ValueError("EVENT_CALENDAR_IS_NOT_PUBLICATION")
            published = instant(row["published_at"])
            if published > observed:
                raise ValueError("EVENT_PUBLICATION_AFTER_OBSERVATION")
            if row.get("scheduled_at") is not None:
                scheduled = instant(row["scheduled_at"])
        else:
            raise ValueError("EVENT_MACRO_STATUS")
        extra = {"label": "MACRO_CALENDAR_CONTEXT" if scheduled and not published else "MACRO_PUBLICATION_REVIEW"}
    iso = lambda t: t.isoformat() if t else None
    return {"key": key, "source": source, "kind": kind, "status": status, "url": url,
            "observed_at_utc": iso(observed), "scheduled_at_utc": iso(scheduled),
            "accepted_at_utc": iso(accepted), "published_at_utc": iso(published), **extra}


def event_evidence(rows, *, cutoff_utc):
    """Return as-of observations, never implied completeness or trading authority.

    The latest supplied observation of an identity and status wins. An
    equally timed conflicting observation is quarantined. Earlier observations
    are retained in inputs for the historical audit and never see later rows.
    """
    cutoff = instant(cutoff_utc)
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError("EVENT_ROWS_REQUIRED")
    seen, rejected = {}, 0
    for row in rows:
        try:
            observed = instant(row["observed_at"])
            if observed > cutoff:
                continue
            record = normalize(row, observed)
        except (TypeError, KeyError, ValueError, OverflowError):
            rejected += 1
            continue
        seen.setdefault(record["key"], []).append((observed, record))
    selected, disputed = [], 0
    for candidates in seen.values():
        # A late scrape of an old calendar cannot demote a witnessed release.
        publications = [(t, r) for t, r in candidates if r["status"] == "PUBLISHED"]
        pool = publications or candidates
        if (publications and len({r["published_at_utc"] for _, r in pool}) != 1
                or pool[0][1]["source"] == "SEC" and
                len({(r["kind"], r["accepted_at_utc"]) for _, r in pool}) != 1):
            disputed += 1
            continue
        latest = max(t for t, _ in pool)
        versions = [r for t, r in pool if t == latest]
        if any(r != versions[0] for r in versions):
            disputed += 1
            continue
        selected.append(versions[0])
    return {"schema": SCHEMA, "cutoff_utc": cutoff.isoformat(),
            "events": sorted(selected, key=lambda row: (row["observed_at_utc"], row["key"])),
            "coverage": "PARTIAL_UNKNOWN" if rejected or disputed else "LOCAL_PAYLOAD_ONLY",
            "unverifiable_rows": rejected, "quarantined_events": disputed,
            "live_source_attested": False, "history_complete_proven": False,
            "production_eligible": False, "signal": None, "alerts_sent": 0,
            "stop_target_modified": False, "no_network_requests": True}
