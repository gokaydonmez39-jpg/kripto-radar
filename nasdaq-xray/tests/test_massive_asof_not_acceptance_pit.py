#!/usr/bin/env python3
"""Vendor's documented report-period 'date' is not SEC filing-acceptance PIT.

Synthetic contract regression, no provider requests, market data, or trading.
Massive ticker-overview docs explicitly permit future-accepted filing facts
to appear at an earlier report-period 'date'. Only an independently checked
filing-acceptance chain can promote a value; this test never promotes.
"""
import copy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import massive_mc_shadow_probe as probe
import massive_mc_resume_shadow as resume

SOURCE="MASSIVE_REFERENCE_REPORT_PERIOD_DATE_NOT_ACCEPTANCE_PIT"
def test():
    vendor={"ticker":"TEST","active":True,"market":"stocks",
        "primary_exchange":"XNAS","type":"CS","currency_name":"usd",
        "cik":"0000123456","market_cap":2_300_000_000}
    classified=probe.classify("TEST",vendor)
    assert classified["state"]=="SHADOW_OBSERVED_ABOVE_2B"
    assert classified["source"]==SOURCE,("MISLABELED_PERIOD_AS_PIT",classified.get("source"))
    assert classified["filing_acceptance_pit_attested"] is False
    assert classified["possible_historical_filing_lookahead"] is True
    assert classified["alpha_authority"] is False
    row=resume.clean_record("TEST","2026-10-09",classified)
    assert row["source"]==SOURCE
    assert row["filing_acceptance_pit_attested"] is False
    assert row["possible_historical_filing_lookahead"] is True
    scope={"asof_et":"2026-10-09","symbols":["TEST"],
           "scope_hash":"fake-tests-only","price_blob_sha":"fake-test-blob",
           "master_price_content_binding_exact":True}
    cp=resume.fresh_checkpoint(scope)
    cp["records"]["TEST"]=row
    cp["request_count_cumulative"]=1
    assert resume.exact_checkpoint(cp,scope)
    for k,v in (
        ("source","MASSIVE_REFERENCE_TICKER_OVERVIEW_PIT"),
        ("filing_acceptance_pit_attested",True),
        ("possible_historical_filing_lookahead",False)):
        corrupt=copy.deepcopy(cp)
        corrupt["records"]["TEST"][k]=v
        assert not resume.exact_checkpoint(corrupt,scope),("UNSAFE_ASOF_ACCEPTED",k)
    missing=copy.deepcopy(cp)
    del missing["records"]["TEST"]["filing_acceptance_pit_attested"]
    assert not resume.exact_checkpoint(missing,scope)
    result=resume.health(scope,cp)
    assert result["filing_acceptance_pit_attested"] is False
    assert result["possible_historical_filing_lookahead"] is True
    assert result["current_mc_production_authority"] is False
    print("XRAY_MASSIVE_REPORT_PERIOD_NOT_ACCEPTANCE_PIT=PASS_4_NEGATIVES_NO_PRIMARY")
if __name__=="__main__":test()
