"""NASDAQ-only SEC EDGAR offline filing header PIT gate. No network/data mutation."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from edgar.headers import IndexHeaders

NY=ZoneInfo("America/New_York")

class FilingBlocked(ValueError):
    pass

def validated_header_asof(html, expected_cik: str, asof_close_et: datetime):
    if asof_close_et.tzinfo is None or asof_close_et.utcoffset() is None:
        raise FilingBlocked("TZ_AWARE_CLOSE_REQUIRED")
    if asof_close_et.astimezone(NY).hour != 16:
        raise FilingBlocked("EXPLICIT_REGULAR_CLOSE_REQUIRED")
    if not isinstance(expected_cik,str) or not re.fullmatch(r"\d{10}",expected_cik):
        raise FilingBlocked("CIK_REQUIRED")
    try:
        h=IndexHeaders.load(html)
    except Exception as e:
        raise FilingBlocked("INVALID_SEC_HEADER") from e
    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}",h.accession_number):
        raise FilingBlocked("INVALID_ACCESSION")
    if h.form not in ("8-K","10-Q","10-K","4"):
        raise FilingBlocked("UNSUPPORTED_FORM")
    if not h.filer or h.filer.company_data.cik!=expected_cik:
        raise FilingBlocked("ISSUER_CIK_MISMATCH")
    accepted=h.acceptance_datetime
    if accepted is None or accepted.tzinfo is not None:
        raise FilingBlocked("AMBIGUOUS_ACCEPTANCE_TIME")
    accepted_et=accepted.replace(tzinfo=NY)
    if accepted_et>asof_close_et.astimezone(NY):
        raise FilingBlocked("AFTER_ASOF_CLOSE_LOOKAHEAD")
    return {"accession":h.accession_number,"cik":expected_cik,
            "form":h.form,"accepted_at_et":accepted_et.isoformat()}
