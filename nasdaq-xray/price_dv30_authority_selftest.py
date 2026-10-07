#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

from price_dv30_recover_from_fullstate import (
    apply_c417_rallies_primary_pass_veto,
    c417_rallies_primary_pass_conflicts,
    load_c417_rallies_primary,
)

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-06"


def main():
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    queue=list(master.get("pass_symbols") or [])
    assert queue and len(queue)==int(master.get("pass_count",-1))

    primary,meta=load_c417_rallies_primary(ASOF,queue)
    assert primary is not None,meta
    assert meta.get("status")=="PASS",meta
    assert "AAPL" in (primary.get("pass_price_dv30") or {})
    assert "GRAL" in (primary.get("block_current_run") or {})
    gral_block=(primary.get("block_current_run") or {})["GRAL"]
    assert gral_block.get("observed_usable_sessions")==29,gral_block
    assert gral_block.get("missing_sessions")==["2026-09-23"],gral_block

    synthetic_price={"asof_et":ASOF,"pass_symbols":["AAPL","GRAL"]}
    conflicts,conflict_meta=c417_rallies_primary_pass_conflicts(synthetic_price,queue)
    assert conflict_meta.get("status")=="PASS",conflict_meta
    assert conflicts==["GRAL"],conflicts

    results={
      "AAPL":{"status":"PASS_PRICE_DV30","info":{"source":"RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9"}},
      "GRAL":{"status":"PASS_PRICE_DV30","info":{"source":"ALPACA_HISTORICAL_SIP_DAILY_BATCH_NON_G9"}},
    }
    changed=apply_c417_rallies_primary_pass_veto(results,primary)
    assert changed==["GRAL"],changed
    assert results["AAPL"]["status"]=="PASS_PRICE_DV30",results["AAPL"]
    assert results["GRAL"]["status"]=="BLOCK_CURRENT_RUN",results["GRAL"]
    assert results["GRAL"]["info"]["proof"]=="FAIL_CLOSED_CURRENT_RUN_NONPASS",results["GRAL"]
    assert results["GRAL"]["info"]["missing_sessions"]==["2026-09-23"],results["GRAL"]

    print("C417_DV30_PASS_AUTHORITY_SELFTEST=PASS")


if __name__=="__main__":
    main()
