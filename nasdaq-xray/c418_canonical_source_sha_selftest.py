#!/usr/bin/env python3
"""Adversarial regression: matching provider claims do not bind a Git PRICE blob.

Synthetic metadata is confined to temporary unit tests, never market bars or AL.
"""
import json
import tempfile
from pathlib import Path
import c418_multi_source_guard as guard

def run():
    policy=json.loads(guard.POLICY.read_text())
    profile=json.loads(guard.PROFILE.read_text())
    original=guard.ROOT
    with tempfile.TemporaryDirectory(prefix="xray-c418-source-bind-") as td:
        try:
            guard.ROOT=Path(td)
            (guard.ROOT/"canonical_current_price_dv30.json").write_text(
                json.dumps({"asof_et":"2026-10-08","pass_symbols":["TEST"],"pass_count":1}))
            e={"schema":guard.SCHEMA,"asof_et":"2026-10-08",
               "price_blob_sha":"b"*40,"symbol":"TEST",
               "issuer_cik":"0000123456","share_class":"CLASS_A",
               "identity":{"source":"SEC_EDGAR","exchange_source":"NASDAQ",
                 "ticker":"TEST","issuer_cik":"0000123456","share_class":"CLASS_A",
                 "exchange":"NASDAQ","filed_on":"2026-10-06",
                 "pit_class_continuity_verified":True,
                 "corporate_actions_class_exact":True},
               "observations":[]}
            def row(provider,kind,root,field,value=None):
                obj={"provider":provider,"kind":kind,"upstream_root":root,
                     "asof_et":"2026-10-08","price_blob_sha":e["price_blob_sha"],
                     "ticker":"TEST","issuer_cik":"0000123456",
                     "share_class":"CLASS_A","currency":"USD"}
                if field:obj[field]=value
                if kind=="HISTORY":
                    obj.update(last_260_official_sessions_exact=True,
                               completed_52_weeks_exact=True,
                               adjustment_basis_verified=True)
                return obj
            e["observations"]=[
                row("Bigdata","MC","SRC_A","market_cap_usd",2100000000),
                row("Massive","MC","SRC_B","market_cap_usd",2050000000),
                row("Massive","PRICE","SRC_B","close_usd",20),
                row("Alpaca","HISTORY","SRC_C",None)]
            rights={provider:{"rights_document_sha256":"a"*64,
                    "effective_from":"2026-01-01","effective_to":"2026-12-31",
                    "unattended_runner":True,"non_display":True,
                    "derived_signals":True,"internal_retention":True,
                    "output_delivery":True}
                for provider in ("Bigdata","Massive","Alpaca")}
            result=guard.validate(e,rights,policy,profile)
            assert result["status"]=="DATA_BLOCKED",result
            assert "CANONICAL_PRICE_BLOB_ASOF_MISMATCH" in result["reason_codes"],result
            assert result["can_register_R92"] is False and result["can_create_PRIMARY"] is False
        finally:
            guard.ROOT=original
    print("XRAY_C418_CANONICAL_PRICE_SHA_NEGATIVE=PASS_STALE_SHA_DENIED")

if __name__=="__main__":
    run()
