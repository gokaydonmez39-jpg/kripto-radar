#!/usr/bin/env python3
"""C4.17 current MC request witness, using GitHub canonical blob and exact set.

The passive automation request is a coordinator, not a market-data authority.
This test does not read ChatGPT task state, call vendor APIs or mint any PASS.
"""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import mc_request_freshness_rebind as source

def verify():
    r=source.build()
    assert r["schema"]=="XRAY_MC_REQUEST_FRESHNESS_REBIND_V1"
    assert r["status"]=="CURRENT_REQUEST_EVIDENCE_READY_NO_MC_MEASUREMENT"
    assert r["asof_et"]=="2026-10-09"
    assert r["input_blob_sha"]=="6f3f68fff0897d68f200ad3621c51a5071494714"
    assert r["input_pass_count"]==514
    assert r["input_pass_hash"]=="cb6d740f43378cacca40351e7503384d52b5a81a8b9b6cdc444f58a3965bbaef"
    assert r["resolver_provenance_path"]=="nasdaq-xray/canonical_resolver_bridge_20261009_c417_dv30_v2.json"
    assert r["resolver_provenance_blob_sha"]=="f69dbe9db68dc52369c574c0597f118b44635874"
    assert r["input_unknown_count"]==0 and r["input_blocked_count"]==0
    assert r["input_pass_symbols"]==sorted(set(r["input_pass_symbols"]))
    assert len(r["input_pass_symbols"])==514
    assert hashlib.sha256("\n".join(r["input_pass_symbols"]).encode()).hexdigest()==r["input_pass_hash"]
    assert r["policy_version"]=="C4.17" and r["settlement_status"]=="PASS"
    assert r["resolver_role"]=="FULL_SCOPE_MC_HANDOFF_AUTHORITY"
    assert r["candidate_created"] is False and r["primary_mc_pass_created"]==0 and r["can_register_R92"] is False
    assert r["unknown_never_pass"] is True and r["execution"]=="NONE" and r["real_money"]=="NO-GO"
    # Future completions cannot re-label 7-Oct alternate marketcap as primary.
    old=json.loads((ROOT/"canonical_mc_bridge_20261007_c417_dv30_v1.json").read_text())
    assert old["asof_et"]=="2026-10-07"
    assert old["input_count"]==510
    assert old["counts"]=={"MC_FAIL_FALLBACK_TWO_SOURCE":9,"MC_FAIL_PRIMARY":0,"MC_PASS_FALLBACK_WATCH":472,"MC_PASS_PRIMARY":0,"MC_UNKNOWN":29,"TOTAL":510}
    assert old["authority"]=="CANONICAL_MC_C417_DV30_FRESH_FALLBACK_MEASUREMENT_V1"
    assert old["resolution_evidence"]["same_run_source_pair"]=="RALLIES_XNAS_PLUS_LONGBRIDGE_NASD"
    assert old["resolution_evidence"]["primary_provider_current_status"]=="BLOCKED_EXTERNAL_CREDITS_EXHAUSTED_NO_PAID_TOPUP"
    assert all(v.get("r92_eligible") is False for v in old["results"].values() if v.get("status")=="MC_PASS_FALLBACK_WATCH")
    # Source contract must enforce future ASOF equality; exact pinned Oct9
    # request can never remain READY after PRICE moves to a later epoch.
    current_price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    assert current_price["asof_et"]==r["asof_et"]
    assert source.blob(ROOT/"canonical_current_price_dv30.json")==r["input_blob_sha"]
    print("XRAY_MC_REQUEST_20261009_EXACT_SOURCE=PASS_514_MATCH_NO_PRIMARY_NO_ALPHA")
    print("XRAY_MC_20261007_SOURCE_PROVENANCE=RALLIES_PLUS_LONGBRIDGE_510_FALLBACK_WATCH_ONLY")
if __name__=="__main__":verify()
