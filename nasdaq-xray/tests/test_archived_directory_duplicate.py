#!/usr/bin/env python3
"""RED/GREEN regression for duplicate canonical queue symbols hiding false coverage."""
import gzip
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("archived_directory_audit_duplicates", ROOT / "nasdaq_20261009_immutable_archive_shadow.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

class Response:
    status=200
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n): return self.data[:n]

def main():
    footer="File Creation Time: 1009202621:31|||||||"
    rows=["Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"]
    rows += [f"T{i:04d}|Company {i}|Q|N|N|100|N|N" for i in range(510)]
    rows.append(footer)
    archived=gzip.compress(("\n".join(rows)+"\n").encode(),mtime=0)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        # Two nominal queue entries, but only ONE distinct ticker: a false raw total.
        full={"asof_et":"2026-10-09","official_footer":footer,"execution":"NONE",
              "real_money":"NO-GO","queue":["T0001","T0001"],
              "identity_unknown_symbols":[],"raw_identity_total":2,
              "identity_unknown_detail":{},"security_names":{"T0001":"Company 1"}}
        master={"asof_et":"2026-10-09","official_footer":footer,
                "execution":"NONE","real_money":"NO-GO",
                "pass_symbols":["T0001","T0001"]}
        proof={"asof_et":"2026-10-09","source_directory_footer":footer}
        for filename,data in (("canonical_current_full_state.json",full),
                              ("canonical_current_master_manifest.json",master),
                              ("master_asof_identity_proof_20261009.json",proof)):
            (root/filename).write_text(json.dumps(data),encoding="utf-8")
        output=root/"census.json"
        with patch.object(audit,"ROOT",root),patch.object(
            audit,"SOURCE_GIT_BLOB",audit.sha_git_blob(archived)
        ),patch.object(
            audit.urllib.request,"urlopen",return_value=Response(archived)
        ),patch.object(
            sys,"argv",["audit","--out",str(output)]
        ):
            try:
                audit.main()
            except (ValueError, RuntimeError) as e:
                assert "DUPLICATE" in str(e) or "UNTRUSTED" in str(e),str(e)
                print("NEGATIVE_DUPLICATE_QUEUE=REJECTED")
                return
            except SystemExit as e:
                if e.code not in (None,0):
                    print("NEGATIVE_DUPLICATE_QUEUE=REJECTED")
                    return
                raise AssertionError("Duplicate queue was accepted with exit zero")
        raise AssertionError("Duplicate queue silently greenlit (RED expected)")

if __name__=="__main__":
    main()
