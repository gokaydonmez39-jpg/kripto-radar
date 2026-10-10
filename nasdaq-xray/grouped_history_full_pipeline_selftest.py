#!/usr/bin/env python3
"""Offline current PRICE cohort + QQQ x 260-day HISTORY transport integration test.

Synthetic fixtures only; never market authority, confidence, AL, or a vendor
license. Tests actual encrypted checkpoint, ephemeral gzip transport, official
Nasdaq 260 daily/52 weekly gate, missing-day and malformed-volume negatives.
"""
from __future__ import annotations
import copy
import gzip
import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from massive_grouped_history_resume import (
    cipher,exact,export_completed_private_csv,fresh,gitblob,load,save,scope,telemetry
)
from qualified_history_ingress_shadow import evaluate
from history_transport_cache_guard import cache_path

def main():
    ss=scope()
    price=json.loads((Path(__file__).resolve().parent/"canonical_current_price_dv30.json").read_text())
    assert ss["symbols"] and ss["symbols"]==sorted(set(ss["symbols"]))
    assert len(ss["symbols"])==price["pass_count"]
    assert len(ss["targets"])==len(set(ss["symbols"])|{"QQQ"})
    assert len(ss["dates"])==260 and len(ss["weeks"])==52
    private_symbol=ss["symbols"][0]
    with TemporaryDirectory(prefix="xray-current-scope-260-fullmock-") as work:
        tmp=Path(work)
        crypt=cipher("synthetic-test-key-only-"+"A"*38)
        cp=fresh(ss)
        # These are deliberately constant synthetic values and NOT securities
        # market observations, split-adjusted history or tradable research.
        for d in ss["dates"]:
            cp["dates"][d]={s:[10.0,11.0,9.0,10.0,125.125]
                            for s in ss["targets"]}
        cp["request_count"]=260
        assert exact(cp,ss)
        assert telemetry(cp,ss,"TEST_ONLY",0)["full_260_symbol_date_transport"] is True
        checkpoint=tmp/"checkpoint.encrypted"
        save(cp,crypt,ss,checkpoint)
        ciphertext=checkpoint.read_bytes()
        assert ciphertext.startswith(b"gAAAA") and not ciphertext.startswith(b"{")
        # Random ciphertext can incidentally contain 3-byte tokens such as
        # QQQ. Check that a full *plaintext bar* is absent; decryption and
        # authenticated tampering are verified by the separate selftest.
        assert b'"QQQ":[10.0,11.0,9.0,10.0,125.125]' not in ciphertext
        decrypted,restored=load(checkpoint,crypt,ss)
        assert restored and exact(decrypted,ss)
        outputdir=tmp/"private-raw"
        exported=export_completed_private_csv(decrypted,ss,outputdir)
        assert exported["symbol_csv_private"]==len(ss["targets"])
        # Real PRICE UNKNOWN is a correct hard STOP, never weaken ingress.
        if price.get("unknown_count",0)!=0:
            try:evaluate(price,ss["price_sha"],outputdir)
            except ValueError as exc:
                assert str(exc)=="PRICE_SCOPE_OR_SAFETY_INVALID"
            else:raise AssertionError("REAL_UNKNOWN_WAS_ACCEPTED")
        # Pure synthetic control fixture; no real vendor proof or authority.
        fixture=copy.deepcopy(price)
        fixture["unknown_count"]=0
        fixture["unknown_symbols"]=[]
        raw_fixture=json.dumps(fixture,sort_keys=True).encode()
        fixture_sha=hashlib.sha1(b"blob "+str(len(raw_fixture)).encode()
                                 +bytes([0])+raw_fixture).hexdigest()
        complete=evaluate(fixture,fixture_sha,outputdir)
        assert complete["structural_private_transport_complete"]
        assert complete["counts"]["complete_private_transport"]==len(ss["targets"])
        assert not complete["source_vendor_rights_independently_verified"]
        assert not complete["source_exchangewide_volume_proven"]
        assert complete["canonical_history_pass_created"]==0
        assert complete["primary_mc_pass_created"]==0
        assert complete["can_register_R92"] is False
        # One missing latest session invalidates the entire ticker; no synthetic
        # fill or per-symbol false PASS.
        path=cache_path(outputdir,private_symbol)
        with gzip.open(path,"rt",encoding="utf-8") as fh:
            lines=fh.readlines()
        assert len(lines)==261
        with gzip.open(path,"wt",encoding="utf-8") as fh:
            fh.writelines(lines[:-1])
        missing=evaluate(fixture,fixture_sha,outputdir)
        assert missing["counts"]["stale_or_session_gap"]==1
        assert not missing["structural_private_transport_complete"]
        # Restore and corrupt one real numeric column: hard FAIL, not
        # incomplete fallback or an implied valid bar.
        with gzip.open(path,"wt",encoding="utf-8") as fh:
            mutated=lines.copy()
            mutated[2]=mutated[2].rsplit(",",1)[0]+",0\n"
            fh.writelines(mutated)
        corrupt=evaluate(fixture,fixture_sha,outputdir)
        assert corrupt["counts"]["invalid_or_unreadable"]==1
        assert not corrupt["can_register_R92"]
    print("XRAY_CURRENT_SCOPE_XNAS_260D_52W_ENCRYPTED_PIPELINE_SELFTEST=PASS_SYNTHETIC_ONLY_2_NEGATIVES_0_HISTORY_MC_AL_AUTHORITY")

if __name__=="__main__":
    main()
