"""Binding for historical terminal halt evidence, distinct from live veto data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

LIVE_NAME = "canonical_official_source_guard.json"
TERMINAL_NAME = "canonical_current_terminal_official_guard.json"
PREFIX = "nasdaq-xray/"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def terminal_guard_name(bound: dict, *, legacy: bool) -> str:
    names = (TERMINAL_NAME, LIVE_NAME) if legacy else (TERMINAL_NAME,)
    if (not isinstance(bound, dict)
        or bound.get("path") not in tuple(PREFIX + n for n in names)
        or not isinstance(bound.get("blob_sha"), str)
        or not re.fullmatch(r"[0-9a-f]{40}", bound["blob_sha"])):
        raise ValueError("TERMINAL_OFFICIAL_GUARD_BINDING_INVALID")
    return bound["path"][len(PREFIX):]


def verify_terminal_guard(root: Path, bound: dict, *, legacy: bool = False) -> dict:
    filename = terminal_guard_name(bound, legacy=legacy)
    path = root / filename
    if path.is_symlink() or not path.is_file():
        raise ValueError("TERMINAL_OFFICIAL_GUARD_NOT_REGULAR")
    data = path.read_bytes()
    if git_blob(data) != bound["blob_sha"]:
        raise ValueError("TERMINAL_OFFICIAL_GUARD_BLOB_MISMATCH")
    doc = json.loads(data)
    if (not isinstance(doc, dict)
        or doc.get("schema") != "XRAY_OFFICIAL_SOURCE_GUARD_V1"
        or doc.get("execution") != "NONE"
        or doc.get("real_money") != "NO-GO"
        or doc.get("alpha_authority") is not False):
        raise ValueError("TERMINAL_OFFICIAL_GUARD_SAFETY_INVALID")
    return doc
