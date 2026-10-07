#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
from pathlib import Path

from price_dv30_recover_from_fullstate import (
    apply_c417_rallies_primary_pass_veto,
    c417_rallies_primary_pass_conflicts,
    load_c417_rallies_primary,
    valid_bridge_price_resolution,
)

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-06"


def main():
    outer=json.loads((ROOT/"chatgpt_compiled_policy_v3.json").read_text())
    policy=json.loads(outer["payload_json"])
    assert policy.get("version")=="C4.17",policy.get("version")
    hard=policy.get("hard_gates") or {}
    assert hard.get("price")==">=5",hard
    assert hard.get("dv30")=="median exactly30 completed official-RTH Close*regular-session Volume >=50000000",hard
    # C4.17 specifies the measurement, not a Rallies-exclusive PASS provider.
    assert "dv30_primary_source" not in hard,hard
    assert "price_primary_source" not in hard,hard

    ev=json.loads((ROOT/"evidence"/"alpaca_sip_dv30_gral_20261006_v1.json").read_text())
    assert ev.get("schema")=="XRAY_ALPACA_SIP_DV30_EVIDENCE_V1",ev.get("schema")
    assert ev.get("asof_et")==ASOF and ev.get("symbol")=="GRAL"
    assert ev.get("execution")=="NONE" and ev.get("real_money")=="NO-GO"
    assert ev.get("unknown_never_pass") is True
    assert ev.get("session_calendar_match") is True
    assert ev.get("exact_session_count")==30
    expected=list(ev.get("expected30") or [])
    bars=list(ev.get("bars") or [])
    assert len(expected)==30 and len(bars)==30
    assert [x.get("date") for x in bars]==expected
    assert ev.get("zero_trade_sessions")==["2026-09-23"]
    z=[x for x in bars if x.get("date")=="2026-09-23"]
    assert len(z)==1 and z[0].get("volume")==0 and z[0].get("trade_count")==0,z

    dv=[float(x["close"])*float(x["volume"]) for x in bars]
    median=statistics.median(dv)
    assert abs(median-float(ev.get("dv30_median_usd")))<0.005,(median,ev.get("dv30_median_usd"))
    assert float(ev.get("price_asof_usd"))>=5
    assert median>=50_000_000

    gral={
      "decision":"PASS_PRICE_DV30",
      "price":float(ev["price_asof_usd"]),
      "dv30":median,
      "known_session_count":30,
      "missing_sessions":[],
      "no_synthetic_bar":True,
      "source":"ALPACA_HISTORICAL_SIP_DAILY_BATCH_NON_G9",
      "proof":"EXACT30_MEDIAN_GE_GATE",
    }
    assert valid_bridge_price_resolution(gral,ASOF),gral

    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    queue=list(master.get("pass_symbols") or [])
    assert queue and len(queue)==int(master.get("pass_count",-1))

    rallies,meta=load_c417_rallies_primary(ASOF,queue)
    assert rallies is not None,meta
    assert meta.get("status")=="PASS",meta
    assert "GRAL" in (rallies.get("block_current_run") or {})
    block=(rallies.get("block_current_run") or {})["GRAL"]
    assert block.get("observed_usable_sessions")==29,block
    assert block.get("missing_sessions")==["2026-09-23"],block

    synthetic={"asof_et":ASOF,"pass_symbols":["AAPL","GRAL"]}
    conflicts,conflict_meta=c417_rallies_primary_pass_conflicts(synthetic,queue)
    assert conflicts==["GRAL"],conflicts
    assert conflict_meta.get("authority_role")=="DIAGNOSTIC_CROSS_SOURCE_CLASSIFICATION_NOT_PASS_VETO",conflict_meta

    results={
      "AAPL":{"status":"PASS_PRICE_DV30","info":{"source":"RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9"}},
      "GRAL":{"status":"PASS_PRICE_DV30","info":dict(gral)},
    }
    changed=apply_c417_rallies_primary_pass_veto(results,rallies)
    assert changed==[],changed
    assert results["AAPL"]["status"]=="PASS_PRICE_DV30"
    assert results["GRAL"]["status"]=="PASS_PRICE_DV30",results["GRAL"]

    print("C417_DV30_PROVIDER_NEUTRAL_EXACT30_SELFTEST=PASS")


if __name__=="__main__":
    main()
