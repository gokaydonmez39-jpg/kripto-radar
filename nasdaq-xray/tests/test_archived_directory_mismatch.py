#!/usr/bin/env python3
"""Negative regression: symbol-presence alone must not greenlight a mismatched issuer name."""
import gzip
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "nasdaq_20261009_immutable_archive_shadow.py"
spec = importlib.util.spec_from_file_location("archived_directory_audit", MODULE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class FakeHTTP:
    status = 200

    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.data[:limit]


def main():
    footer = "File Creation Time: 1009202621:31|||||||"
    headers = "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
    lines = [headers]
    for i in range(510):
        issuer = "IMPOSTOR INC - Common Stock" if i == 1 else f"Test Company {i}"
        lines.append(f"T{i:04d}|{issuer}|Q|N|N|100|N|N")
    lines.append(footer)
    compressed = gzip.compress(("\n".join(lines) + "\n").encode(), mtime=0)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = {
            "canonical_current_full_state.json": {
                "asof_et": "2026-10-09",
                "official_footer": footer,
                "execution": "NONE",
                "real_money": "NO-GO",
                "queue": ["T0001"],
                "identity_unknown_symbols": [],
                "raw_identity_total": 1,
                "identity_unknown_detail": {},
                "security_names": {"T0001": "LEGITIMATE CORPORATION - Common Stock"},
            },
            "canonical_current_master_manifest.json": {
                "asof_et": "2026-10-09",
                "official_footer": footer,
                "execution": "NONE",
                "real_money": "NO-GO",
                "pass_symbols": ["T0001"],
            },
            "master_asof_identity_proof_20261009.json": {
                "asof_et": "2026-10-09",
                "source_directory_footer": footer,
            },
        }
        for name, payload in data.items():
            (root / name).write_text(json.dumps(payload), encoding="utf-8")
        outfile = root / "result.json"
        with patch.object(audit, "ROOT", root), patch.object(
            audit, "SOURCE_GIT_BLOB", audit.sha_git_blob(compressed)
        ), patch.object(
            audit.urllib.request, "urlopen", return_value=FakeHTTP(compressed)
        ), patch.object(
            sys, "argv", ["audit", "--out", str(outfile)]
        ):
            try:
                audit.main()
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    result = json.loads(outfile.read_text())
                    assert result["canonical_projected_name_mismatch_symbols"] == ["T0001"]
                    print("NEGATIVE_NAME_IDENTITY_MISMATCH=REJECTED")
                    return
                raise AssertionError("Name mismatch returned success exit status")
        raise AssertionError("Name mismatch silently returned exit 0 (RED expected)")


if __name__ == "__main__":
    main()
