#!/usr/bin/env python3
"""Semantic stale-source check for gzip benchmark-cache blobs.

Byte-level gzip drift caused only by headers (for example mtime) is ignored.
Any decompressed payload change, missing path, malformed gzip, or git read error
is reported fail-closed as semantic drift.
"""
from __future__ import annotations

import gzip
import subprocess
import sys
from typing import Iterable


def gzip_payload_equal(a: bytes, b: bytes) -> bool:
    try:
        return gzip.decompress(a) == gzip.decompress(b)
    except Exception:
        return False


def git_blob(ref: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"])


def semantic_changed_paths(base: str, latest: str, paths: Iterable[str]) -> list[str]:
    bad: list[str] = []
    for path in paths:
        path = str(path).strip()
        if not path:
            continue
        try:
            if not gzip_payload_equal(git_blob(base, path), git_blob(latest, path)):
                bad.append(path)
        except Exception:
            bad.append(path)
    return sorted(set(bad))


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        raise SystemExit("usage: semantic_cache_diff.py BASE_REF LATEST_REF [PATH ...]")
    for path in semantic_changed_paths(argv[1], argv[2], argv[3:]):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
