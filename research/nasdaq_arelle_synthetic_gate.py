"""NASDAQ research-only point-in-time XBRL preflight; fictional fixtures, no private inputs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
XBRLI = "http://www.xbrl.org/2003/instance"
LINK = "http://www.xbrl.org/2003/linkbase"
XLINK = "http://www.w3.org/1999/xlink"
EX = "https://example.invalid/xray-nasdaq-synthetic"


class ShadowGateBlocked(ValueError):
    """Fail closed; never issue an AL or a notification."""


def examine_fictional_xbrl(path: Path, cik: str, accepted_et: datetime, asof_et: datetime) -> dict:
    if not isinstance(cik, str) or re.fullmatch(r"[0-9]{10}", cik) is None:
        raise ShadowGateBlocked("INVALID_CIK")
    if any(d.tzinfo is None or d.utcoffset() is None for d in (accepted_et, asof_et)):
        raise ShadowGateBlocked("TZ_AWARE_REQUIRED")
    closing = asof_et.astimezone(NY)
    accepted = accepted_et.astimezone(NY)
    if (closing.hour, closing.minute, closing.second) != (16, 0, 0):
        raise ShadowGateBlocked("REGULAR_CLOSE_REQUIRED")
    if accepted > closing:
        raise ShadowGateBlocked("LOOKAHEAD_ACCEPTANCE")
    size = path.stat().st_size
    if not 0 < size <= 65536:
        raise ShadowGateBlocked("INVALID_FIXTURE_SIZE")
    raw = path.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ShadowGateBlocked("XML_ENTITY_FORBIDDEN")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ShadowGateBlocked("XML_PARSE_BLOCKED") from exc
    if root.tag != f"{{{XBRLI}}}xbrl":
        raise ShadowGateBlocked("XBRL_ROOT_REQUIRED")
    refs = root.findall(f"{{{LINK}}}schemaRef")
    if len(refs) != 1 or refs[0].get(f"{{{XLINK}}}href") != "synthetic_taxonomy.xsd":
        raise ShadowGateBlocked("LOCAL_TAXONOMY_ONLY")
    contexts = root.findall(f"{{{XBRLI}}}context")
    if len(contexts) != 1 or contexts[0].get("id") != "ctx1":
        raise ShadowGateBlocked("CONTEXT_UNIQUE_REQUIRED")
    ident = contexts[0].find(f"{{{XBRLI}}}entity/{{{XBRLI}}}identifier")
    if ident is None or ident.get("scheme") != "http://www.sec.gov/CIK" or ident.text != cik:
        raise ShadowGateBlocked("ISSUER_CIK_MISMATCH")
    instant = contexts[0].find(f"{{{XBRLI}}}period/{{{XBRLI}}}instant")
    if instant is None or instant.text != closing.date().isoformat():
        raise ShadowGateBlocked("PERIOD_ASOF_MISMATCH")
    units = root.findall(f"{{{XBRLI}}}unit")
    if len(units) != 1 or units[0].get("id") != "usd":
        raise ShadowGateBlocked("UNIT_UNIQUE_REQUIRED")
    measure = units[0].find(f"{{{XBRLI}}}measure")
    if measure is None or measure.text != "iso4217:USD":
        raise ShadowGateBlocked("USD_UNIT_REQUIRED")
    facts = root.findall(f"{{{EX}}}SyntheticCash")
    if len(facts) != 1 or facts[0].get("contextRef") != "ctx1" or facts[0].get("unitRef") != "usd":
        raise ShadowGateBlocked("FACT_REFERENCE_REQUIRED")
    try:
        amount = Decimal(facts[0].text or "")
    except InvalidOperation as exc:
        raise ShadowGateBlocked("INVALID_AMOUNT") from exc
    if not amount.is_finite() or amount < 0:
        raise ShadowGateBlocked("NONFINITE_OR_NEGATIVE_AMOUNT")
    return {"cik": cik, "asof_et": closing.isoformat(), "accepted_et": accepted.isoformat(), "amount": str(amount)}


def arelle_offline_probe(path: Path) -> int:
    """Independent Arelle model load: no network, fail closed on taxonomy/schema errors."""
    from arelle import Cntlr, ModelManager

    controller = Cntlr.Cntlr()
    controller.webCache.workOffline = True
    manager = ModelManager.initialize(controller)
    try:
        model = manager.load(str(path))
        if model is None or model.modelDocument is None:
            raise ShadowGateBlocked("ARELLE_DOCUMENT_NOT_LOADED")
        if model.errors:
            raise ShadowGateBlocked("ARELLE_SCHEMA_OR_VALIDATION_ERRORS")
        if len(model.facts) != 1:
            raise ShadowGateBlocked("ARELLE_FACT_COUNT_MISMATCH")
        return len(model.facts)
    finally:
        manager.close()
