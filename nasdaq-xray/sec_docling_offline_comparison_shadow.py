#!/usr/bin/env python3
"""Optional offline SEC-like HTML parsing research comparison.

Exact pin docling-slim[format-html]==2.140.0 versus markitdown==0.1.8.
This is NOT an SEC filing verification and never grants market-data rights,
PIT/asof validation, C4.17 PRICE, market cap, R92 or user notification.
No network, broker integration, LLM or live SEC calls within this adapter.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

MAX_SIZE = 524288
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def require(ok: bool, label: str):
    if not ok:
        raise ValueError("XRAY_DOCLING_COMPARE_" + label)


def compare_html(path: Path, *, source_sha256: str,
                 required_literals: list[str]) -> dict:
    path = Path(path)
    require(path.suffix.lower() in (".html",".htm"), "LOCAL_HTML_ONLY")
    require(path.is_file() and not path.is_symlink(), "REGULAR_SOURCE_ONLY")
    require(type(source_sha256) is str and SHA256.fullmatch(source_sha256)
            is not None, "SOURCE_HASH_TYPE")
    require(type(required_literals) is list and
            1 <= len(required_literals) <= 12 and
            all(type(t) is str and 3 <= len(t) <= 100 and
                "\n" not in t and "\r" not in t for t in required_literals)
            and len(set(required_literals)) == len(required_literals),
            "REQUIRED_LITERAL_SET")
    size = path.stat().st_size
    require(0 < size <= MAX_SIZE, "HTML_SIZE")
    raw = path.read_bytes()
    require(len(raw) == size, "SIZE_DRIFT")
    require(hashlib.sha256(raw).hexdigest() == source_sha256,
            "SOURCE_DIGEST_DRIFT")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("XRAY_DOCLING_COMPARE_UTF8_ONLY") from exc
    require(all(token in text for token in required_literals),
            "UNATTESTED_SOURCE_LITERAL")
    # Imports happen only after file/digest/literal verification;
    # packages are available only in an isolated secretless CI job.
    import importlib.metadata as metadata
    require(metadata.version("docling-slim") == "2.140.0",
            "DOCLING_VERSION_NOT_PINNED")
    require(metadata.version("markitdown") == "0.1.8",
            "MARKITDOWN_VERSION_NOT_PINNED")
    from docling.datamodel.base_models import ConversionStatus, InputFormat
    from docling.document_converter import DocumentConverter
    from markitdown import MarkItDown

    docling = DocumentConverter(allowed_formats=[InputFormat.HTML]).convert(str(path))
    require(docling.status == ConversionStatus.SUCCESS, "DOCLING_CONVERSION_INCOMPLETE")
    dm = docling.document.export_to_markdown()
    mt = MarkItDown(enable_plugins=False).convert(str(path))
    mm = getattr(mt, "markdown", None)
    if not isinstance(mm, str):
        mm = getattr(mt, "text_content", None)
    require(type(dm) is str and bool(dm.strip()), "DOCLING_EMPTY")
    require(type(mm) is str and bool(mm.strip()), "MARKITDOWN_EMPTY")
    require(all(t in dm for t in required_literals), "DOCLING_LOST_FACT")
    require(all(t in mm for t in required_literals), "MARKITDOWN_LOST_FACT")
    require(len(dm.encode("utf-8")) <= MAX_SIZE*4 and
            len(mm.encode("utf-8")) <= MAX_SIZE*4, "OUTPUT_TOO_LARGE")
    # Keep only hashes and counts, not unlicensed raw/vendor records.
    return {
        "schema":"XRAY_SEC_DOC_PARSER_COMPARISON_OFFLINE_V1",
        "status":"COMPARABLE_LOCAL_HTML_RESEARCH_ONLY",
        "source_sha256":source_sha256,
        "docling_version":"2.140.0", "markitdown_version":"0.1.8",
        "docling_markdown_sha256":hashlib.sha256(dm.encode("utf-8")).hexdigest(),
        "markitdown_markdown_sha256":hashlib.sha256(mm.encode("utf-8")).hexdigest(),
        "required_literal_count":len(required_literals),
        "both_preserved_required_literals":True,
        "official_sec_document_verified":False,
        "asof_acceptance_verified":False,
        "market_data_licensed":False,
        "price_pass":False, "mc_pass":False,
        "r92_authority":False, "may_notify_user":False,
        "execution":"NONE","real_money":"NO-GO"
    }
