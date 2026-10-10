#!/usr/bin/env python3
"""Adversarial SEC same-filing contradictory shares; synthetic values, no market data."""
import copy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sec_official_free_mc_transport_probe import select_shares

ACCESSION="0000320193-26-000010"
ASOF="2026-10-09"
BASE_ROW={"val":100,"end":"2026-09-30","filed":"2026-10-06","form":"10-Q","accn":ACCESSION}
FACTS={"cik":320193,"facts":{"dei":{"EntityCommonStockSharesOutstanding":{
    "units":{"shares":[BASE_ROW,dict(BASE_ROW,val=200)]}}}}}
SUB={"cik":320193,"filings":{"recent":{
    "accessionNumber":[ACCESSION],"form":["10-Q"],"filingDate":["2026-10-06"],
    "acceptanceDateTime":["2026-10-06T12:00:00-04:00"]}}}
def main():
    result=select_shares(FACTS,SUB,ASOF)
    assert result["status"]=="UNKNOWN",("CONFLICTING_SAME_VINTAGE_SHARES_SILENTLY_ACCEPTED",result)
    assert result["reason"]=="SEC_CONFLICTING_SAME_VINTAGE_SHARES",result
    duplicate=copy.deepcopy(FACTS)
    duplicate["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"][1]["val"]=100
    assert select_shares(duplicate,SUB,ASOF)["status"]=="SHADOW_SHARES_VINTAGE_ONLY"
    # Contradictory older vintage cannot override a unique later accepted filing.
    old=copy.deepcopy(FACTS)
    old["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"].append(
      {"val":300,"end":"2026-10-07","filed":"2026-10-08","form":"10-Q","accn":"0000320193-26-000011"})
    recent=copy.deepcopy(SUB)
    recent["filings"]["recent"]["accessionNumber"].append("0000320193-26-000011")
    recent["filings"]["recent"]["form"].append("10-Q")
    recent["filings"]["recent"]["filingDate"].append("2026-10-08")
    recent["filings"]["recent"]["acceptanceDateTime"].append("2026-10-08T11:00:00-04:00")
    assert select_shares(old,recent,ASOF)["status"]=="SHADOW_SHARES_VINTAGE_ONLY"
    print("XRAY_SEC_SAME_VINTAGE_CONFLICT=REJECTED_NO_PRIMARY_NO_VENDOR_NO_ALPHA")
if __name__=="__main__":main()
