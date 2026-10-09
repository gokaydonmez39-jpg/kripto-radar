#!/usr/bin/env python3
"""Production MC selector SHA contract test; metadata only, no price observations."""
import json
import tempfile
from pathlib import Path
import build_current_terminal as terminal

def main():
    price={"asof_et":"2026-10-08","pass_symbols":["TST"],
           "pass_count":1,"pass_hash":"scope-hash"}
    mc={"schema":"XRAY_MC_EPOCH_RESULT_V1","status":"COMMITTED",
        "task_id":terminal.TASK,"execution":"NONE","real_money":"NO-GO",
        "asof_et":"2026-10-08",
        "input_path":"nasdaq-xray/canonical_current_price_dv30.json",
        "input_blob_sha":"a"*40,"input_pass_hash":"scope-hash",
        "input_count":1,"results":{"TST":{"status":"MC_UNKNOWN"}},
        "policy_hash":terminal.POLICY_HASH,
        "policy_version":"C4.17"}
    with tempfile.TemporaryDirectory() as directory:
        old_root=terminal.ROOT
        try:
            terminal.ROOT=Path(directory)
            (terminal.ROOT/"canonical_mc_bridge_test.json").write_text(json.dumps(mc))
            exact=terminal.find_mc(price,"a"*40)
            assert exact[2]["blob_exact"] is True
            for wrong in ["b"*40,""]:
                try:
                    terminal.find_mc(price,wrong)
                except RuntimeError as error:
                    assert str(error).startswith("MC_BRIDGE_EXACT_PRICE_BLOB_REQUIRED"),error
                else:
                    raise AssertionError("STALE_PRICE_SHA_ACCEPTED")
        finally:
            terminal.ROOT=old_root
    print("XRAY_MC_SELECTOR_RUNTIME=PASS_ONE_EXACT_TWO_STALE_NEGATIVES")

if __name__=="__main__":
    main()
