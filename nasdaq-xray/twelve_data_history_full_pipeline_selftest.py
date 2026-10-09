#!/usr/bin/env python3
"""Offline entire current PRICE+QQQ 260-day Twelve EOD encrypted transport integration.

Synthetic data only, no license, source certification, market probabilities,
real HISTORY/MC, R92 signal or trading execution.
"""
from __future__ import annotations
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from twelve_data_history_resume import (crypt,exact,export_private,fresh,load,save,scope,health)
from qualified_history_ingress_shadow import evaluate
from history_transport_cache_guard import cache_path

def main():
    s=scope()
    price=json.loads((Path(__file__).resolve().parent/"canonical_current_price_dv30.json").read_text())
    assert len(s["symbols"])==price["pass_count"]
    assert len(s["dates"])==260 and len(s["weeks"])==52
    if not s["symbols"]:
        assert s["targets"]==[] and price["pass_count"]==0
        assert health(fresh(s),s,"BLOCKED_NO_CURRENT_PRICE_PASS_SCOPE",0)["target_count"]==0
        assert health(fresh(s),s,"BLOCKED_NO_CURRENT_PRICE_PASS_SCOPE",0)["R92_AL"] is False
        print("XRAY_TWELVE_CURRENT_SCOPE_260_52_ENCRYPTED_FULL_SELFTEST=PASS_ZERO_PRICE_PASS_SCOPE_BLOCKED_NO_PHANTOM_QQQ_NO_ALPHA")
        return
    assert len(s["targets"])==len(set(s["symbols"])|{"QQQ"})
    with TemporaryDirectory(prefix="xray-twelve-current-scope-") as name:
        temp=Path(name)
        cp=fresh(s)
        # Deterministic invented geometry: integrity test ONLY, not vendor bars.
        template=[[d,10.0,11.0,9.0,10.0,100.25] for d in s["dates"]]
        for sym in s["targets"]:
            cp["bars"][sym]=[row.copy() for row in template]
        cp["requests_total"]=len(s["targets"])
        cp["rate_times"]=[100000.0+i*9 for i in range(len(s["targets"]))]
        assert len(cp["rate_times"])<=800, "OUTSIDE_FREE_DAILY_BUDGET"
        assert exact(cp,s)
        c=crypt("OFFLINE-SYNTHETIC-ONLY-"+"A"*32)
        enc=temp/"all_260.entitlement_unproven.enc"
        save(enc,cp,s,c)
        assert b'"date"' not in enc.read_bytes()
        restored,match=load(enc,s,c)
        assert match and exact(restored,s)
        assert health(restored,s,"SYNTHETIC_ONLY",0)["complete_260_symbols"]==len(s["targets"])
        raw=temp/"private_csv"
        assert export_private(restored,s,raw)==len(s["targets"])
        structural=evaluate(price,s["price_sha"],raw)
        assert structural["structural_private_transport_complete"] is True
        assert structural["counts"]["complete_private_transport"]==len(s["targets"])
        assert structural["source_vendor_rights_independently_verified"] is False
        assert structural["source_exchangewide_volume_proven"] is False
        assert structural["canonical_history_pass_created"]==0
        assert structural["primary_mc_pass_created"]==0
        assert structural["can_register_R92"] is False
        # Missing one completed session fails that ticker; never synthesize fill.
        symbol=s["targets"][0]
        path=cache_path(raw,symbol)
        with gzip.open(path,"rt",encoding="utf-8") as f:lines=f.readlines()
        assert len(lines)==261
        with gzip.open(path,"wt",encoding="utf-8") as f:f.writelines(lines[:-1])
        bad=evaluate(price,s["price_sha"],raw)
        assert bad["counts"]["stale_or_session_gap"]==1
        assert not bad["structural_private_transport_complete"]
        # Invalid numeric source record is a distinct hard invalidity.
        with gzip.open(path,"wt",encoding="utf-8") as f:
            mutated=lines.copy()
            mutated[3]=mutated[3].rsplit(",",1)[0]+",0\n"
            f.writelines(mutated)
        corrupted=evaluate(price,s["price_sha"],raw)
        assert corrupted["counts"]["invalid_or_unreadable"]==1
        assert not corrupted["can_register_R92"]
        tampered=enc.read_bytes()
        enc.write_bytes(tampered[:-1]+b"Z")
        try:load(enc,s,c)
        except ValueError:pass
        else:raise AssertionError("CIPHER_TAMPER_ACCEPTED")
    print("XRAY_TWELVE_CURRENT_SCOPE_260_52_ENCRYPTED_FULL_SELFTEST=PASS_SYNTHETIC_ONLY_2_NEGATIVES_0_HISTORY_MC_R92_AUTHORITY")

if __name__=="__main__":
    main()
