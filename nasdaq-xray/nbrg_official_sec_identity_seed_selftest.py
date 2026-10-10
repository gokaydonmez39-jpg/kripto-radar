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
    assert 'age>120' in source
    assert 'sec_source_binds_cik(source,cik)' in source
    assert '"same_asof_nasdaq_security_name"' in source
    assert '"OFFICIAL_SEC_STATIC_EVIDENCE_PLUS_EXACT_ASOF_NASDAQ_IDENTITY;NO_ALPHA_PASS"' in source
    # No candidate can receive MC/HISTORY/AL authority from this seed.
    assert rec.get("alpha_authority") is not True
    print("XRAY_NBRG_SEC_OFFICIAL_20260803_IDENTITY_SEED=PASS_FAIL_ONLY_NO_PRIMARY")

if __name__=="__main__":
    run()
