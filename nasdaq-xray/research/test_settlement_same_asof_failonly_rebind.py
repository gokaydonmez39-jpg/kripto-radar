#!/usr/bin/env python3
"""Adversarial test of SAME-ASOF frozen settlement reuse with real canonical PRICE.

No market data calls. Reads main via supplied local git show snapshots. The
only positive is reuse of source witness: no PRICE, MC, HISTORY, R92 promotion.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from settlement_same_asof_failonly_rebind import safe_same_asof_failonly_settlement as eligible

def blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+bytes([0])+data).hexdigest()

def main():
    x=argparse.ArgumentParser()
    x.add_argument("--master",type=Path,required=True)
    x.add_argument("--price",type=Path,required=True)
    x.add_argument("--bridge",type=Path,required=True)
    a=x.parse_args()
    data=[p.read_bytes() for p in (a.master,a.price,a.bridge)]
    master,price,bridge=map(json.loads,data)
    master_sha,price_sha=map(blob,data[:2])
    check=lambda bb,pp,mm,ms,ps:eligible(bb,pp,mm,ms,ps)
    assert check(bridge,price,master,master_sha,price_sha), "REAL_OCT9_SAME_ASOF_SETTLEMENT_REUSE_REJECTED"
    tests=(
      ("epoch",lambda b,p,m:p.update(asof_et="2026-10-08")),
      ("master_epoch",lambda b,p,m:m.update(asof_et="2026-10-08")),
      ("queue",lambda b,p,m:m.update(queue_hash="f"*64)),
      ("master_sha",lambda b,p,m:b.update(source_master_blob_sha="f"*40)),
      ("policy",lambda b,p,m:b.update(compiled_policy_hash="f"*64)),
      ("execution",lambda b,p,m:b.update(execution="ORDER")),
      ("no_rights",lambda b,p,m:p.update(real_money="GO")),
      ("not_settled",lambda b,p,m:b.update(settlement_status="UNKNOWN")),
      ("status_not_committed",lambda b,p,m:b.update(status="DRAFT")),
      ("partial",lambda b,p,m:b.update(partial_data=True)),
      ("counterfeit_close",lambda b,p,m:b["settlement_evidence"]["AAPL"].update(longbridge_rth_close_timestamp="2026-10-08T20:00:00Z")),
      ("fake_volume",lambda b,p,m:b["settlement_evidence"]["MSFT"].update(alpaca_volume=-1)),
      ("fake_price",lambda b,p,m:b["settlement_evidence"]["NVDA"].update(ohlc=[0,200,100,150])),
      ("change_settlement_core",lambda b,p,m:b.update(settlement_symbols=["AAPL","NVDA","MSTR"])),
      ("new_pass",lambda b,p,m:p["pass_symbols"].append("ZZZ")),
      ("pass_hash_wrong",lambda b,p,m:p.update(pass_hash="0"*64)),
      ("old_pass_downgrade",lambda b,p,m:p["results"][b["pass_price_dv30_symbols"][0]].update(status="FAIL_PRICE")),
      ("old_block_promote",lambda b,p,m:p["results"][b["block_current_run"][0]].update(status="PASS_PRICE_DV30")),
      ("old_block_unknown",lambda b,p,m:p["results"][b["block_current_run"][0]].update(status="UNKNOWN")),
      ("erase_official_fail",lambda b,p,m:p["results"]["GRAL"]["info"].update(no_synthetic_bar=False)),
      ("alter_pass_scope",lambda b,p,m:b["pass_price_dv30_symbols"].pop()),
      ("alter_block_scope",lambda b,p,m:b["block_current_run"].pop()),
      ("alter_settlement_method",lambda b,p,m:b.update(settlement_method="UNKNOWN")),
      ("alter_issuer",lambda b,p,m:m["pass_symbols"].pop()),
    )
    for name,mutate in tests:
        bb,pp,mm=(copy.deepcopy(j) for j in (bridge,price,master))
        mutate(bb,pp,mm)
        if check(bb,pp,mm,master_sha,price_sha):
            raise AssertionError("UNSAFE_SETTLEMENT_REBIND_ACCEPTED:"+name)
    print("XRAY_SAME_ASOF_20261009_SETTLEMENT_REBIND=PASS_REAL_514_EXACT_39_FAILONLY_24_NEGATIVE_NO_PRIMARY")
    print("XRAY_SETTLEMENT_RESOLVER_WITNESS_BLOB="+blob(data[2]))
    print("XRAY_SETTLEMENT_CURRENT_PRICE_BLOB="+price_sha)
    print("XRAY_SETTLEMENT_AUTHORITY=OLD_SAME_ASOF_ONLY_NO_NEW_BARS_NO_MC_NO_R92")

if __name__=="__main__":
    main()
