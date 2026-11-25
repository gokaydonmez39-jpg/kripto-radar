#!/usr/bin/env python3
"""NBRG dated SEC 8-K identity evidence; never alpha/MC/history authority.

The linked SEC 2026-08-03 8-K index explicitly lists CIK 1918414,
SIC 6770 Blank Checks, and the 8-K specifies NBRG Class A ordinary shares.
This is a fail-only/manual discovery seed, not a completed issuer gate.
"""
from pathlib import Path
import json
import re

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-09"
CIK="0001918414"
SOURCE="https://www.sec.gov/Archives/edgar/data/1918414/000121390026084680/0001213900-26-084680-index.htm"

def run():
    j=json.loads((ROOT/"master_sec_identity_manual_seed_registry.json").read_text())
    assert j["schema"]=="XRAY_MASTER_SEC_IDENTITY_MANUAL_SEED_REGISTRY_V1"
    assert j["execution"]=="NONE" and j["real_money"]=="NO-GO"
    assert j["unknown_never_pass"] is True
    assert j["authority"]=="OFFICIAL_SEC_EVIDENCE_DISCOVERY_SEED_ONLY"
    rec=j["records"].get("NBRG")
    assert isinstance(rec,dict), "NBRG_EXACT_CIK_SEC_SEED_MISSING"
    assert rec.get("cik")==CIK,rec
    assert rec.get("sic")==6770 and rec.get("is_blank_check") is True,rec
    assert rec.get("classification")=="Blank Checks"
    assert rec.get("source_url")==SOURCE
    assert rec.get("evidence_date")=="2026-08-03"
    assert rec.get("verified_asof_et")==ASOF
    assert rec.get("evidence_authority")=="SEC_EDGAR_OFFICIAL"
    source=(ROOT/"build_current_identity_proofs.py").read_text()
    assert re.search(r'def manual_identity_seed_registry\(',source)
    assert 'sec_source_binds_cik(source,cik)' in source
    assert '"same_asof_nasdaq_security_name"' in source
    assert '"OFFICIAL_SEC_STATIC_EVIDENCE_PLUS_EXACT_ASOF_NASDAQ_IDENTITY;NO_ALPHA_PASS"' in source
    # PIT regression: proof verified on Oct 9 must NEVER be backported
    # to an earlier Oct 7 canonical epoch just because the filing is older.
    # Exercise the actual producer and SEC helper imports, offline.
    import sys,types
    from unittest.mock import patch
    from importlib import import_module
    with patch.dict(sys.modules,{"pandas_market_calendars":types.ModuleType("pandas_market_calendars")}):
        producer=import_module("build_current_identity_proofs")
    consumer=producer.manual_identity_seed_registry
    from sec_manual_seed_contract import eligible_evidence
    assert eligible_evidence("2026-11-24","2026-07-27","2026-10-09")
    assert not eligible_evidence("2026-11-24","2026-07-26","2026-10-09")
    # Exact SEC filings available before the Oct-09 epoch, fail-only.
    for sym,cik,evidence,document in (
        ("IBAC","0001998781","2026-07-24",
         "https://www.sec.gov/Archives/edgar/data/1998781/000149315226034626/0001493152-26-034626-index.htm"),
    ):
        row=j["records"].get(sym)
        assert isinstance(row,dict),("OFFICIAL_6770_SEED_MISSING",sym)
        assert row["cik"]==cik and row["sic"]==6770 and row["is_blank_check"] is True,row
        assert row["evidence_date"]==evidence and row["source_url"]==document,row
        assert row["verified_asof_et"]==ASOF,row
        assert row["evidence_authority"]=="SEC_EDGAR_OFFICIAL"
        assert row.get("alpha_authority") is not True
    names={"NBRG":"Newbridge Acquisition Limited - Class A Ordinary Share",
           "FVN":"Future Vision II Acquisition Corporation - Ordinary Shares",
           "IBAC":"IB Acquisition Corp. - Common Stock"}
    current,meta=consumer("2026-10-09",names)
    assert "NBRG" in current,(current,meta)
    assert "IBAC" in current,("IBAC_VALID_SEC_SEED_MISSING",current)
    assert "FVN" not in current,("FVN_SIC_CONTRADICTION_WAS_IGNORED",current)
    for symbol in ("IBAC",):
        assert current[symbol]["seed_semantics"].endswith("NO_ALPHA_PASS")
    prior,meta=consumer("2026-10-07",names)
    assert "NBRG" not in prior,("FUTURE_MANUAL_VERIFICATION_LEAKED_BACK_TO_PRIOR_EPOCH",prior)
    # No candidate can receive MC/HISTORY/AL authority from this seed.
    assert rec.get("alpha_authority") is not True
    print("XRAY_NBRG_SEC_OFFICIAL_20260803_IDENTITY_SEED=PASS_FAIL_ONLY_NO_PRIMARY")

if __name__=="__main__":
    run()
