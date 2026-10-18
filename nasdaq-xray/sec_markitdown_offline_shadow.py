#!/usr/bin/env python3
"""SEC-document HTML research shadow using Microsoft MarkItDown.

No SEC fetch, API, LLM, quote, order, C4.17/R92 release or notification.
Converts *local, user-supplied* HTML only, requiring source SHA256 and
independent expected literal survival. Not official SEC provenance proof.
Requires optional markitdown==0.1.8, only in isolated CI/test workflows.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import re

HASH = re.compile(r"[0-9a-f]{64}\Z")
MAX_SIZE = 524288


def guard(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError("XRAY_SEC_DOC_SHADOW_" + code)


def convert_local_html(path: Path, *, source_sha256: str,
                       required_literals: list[str]) -> dict:
    path = Path(path)
    guard(path.suffix.lower() in (".html", ".htm"), "HTML_ONLY")
    guard(not path.is_symlink() and path.is_file(), "LOCAL_REGULAR_FILE_ONLY")
    guard(type(source_sha256) is str and HASH.fullmatch(source_sha256) is not None,
          "BAD_SOURCE_DIGEST")
    guard(type(required_literals) is list and
          1 <= len(required_literals) <= 12 and
          all(type(x) is str and 3 <= len(x) <= 100
              and "\n" not in x and "\r" not in x for x in required_literals) and
          len(required_literals) == len(set(required_literals)),
          "REQUIRED_LITERAL_CONTRACT")
    size = path.stat().st_size
    guard(0 < size <= MAX_SIZE, "SIZE_LIMIT")
    raw = path.read_bytes()
    guard(len(raw) == size, "SOURCE_SIZE_DRIFT")
    guard(hashlib.sha256(raw).hexdigest() == source_sha256, "SOURCE_SHA_MISMATCH")
    # No subprocess/browser, no network permission, no prompt/agent tools.
    # HTML content is UNTRUSTED and never promoted to trusted filing evidence.
    decoded = raw.decode("utf-8")
    for token in required_literals:
        guard(token in decoded, "LITERAL_NOT_IN_SOURCE")
    from markitdown import MarkItDown  # optional dependency, not production
    result = MarkItDown(enable_plugins=False).convert(str(path))
    md = getattr(result, "markdown", None)
    if not isinstance(md, str):
        md = getattr(result, "text_content", None)
    guard(isinstance(md, str) and md.strip(), "EMPTY_MARKDOWN")
    for token in required_literals:
        guard(token in md, "LITERAL_LOST_IN_CONVERSION")
    guard(len(md.encode("utf-8")) <= MAX_SIZE * 4, "OUTPUT_TOO_LARGE")
    return {
        "schema":"XRAY_SEC_MARKITDOWN_RESEARCH_SHADOW_V1",
        "status":"CONVERTED_LOCAL_HTML_RESEARCH_ONLY",
        "package":"microsoft/markitdown",
        "package_version_tested":"0.1.8",
        "source_sha256":source_sha256,
        "markdown_sha256":hashlib.sha256(md.encode("utf-8")).hexdigest(),
        "required_literal_count":len(required_literals),
        "required_literals_preserved":True,
        "markdown_text":md,
        "official_sec_document_verified":False,
        "sec_acceptance_time_verified":False,
        "lookahead_safe":False,
        "primary_market_data":False,
        "source_rights_attested":False,
        "can_create_price_pass":False,
        "can_register_r92":False,
        "can_notify_user":False,
        "execution":"NONE",
        "real_money":"NO-GO"
    }
