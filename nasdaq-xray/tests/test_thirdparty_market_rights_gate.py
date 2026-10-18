"""Adversarial license-gate regression: open-source adapter != market-data rights."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "provider_automation_governance.json"
NEW = ("TRADINGVIEW_MCP","OPENBB_PUBLIC_NASDAQ_CBOE","GLOBAL_STOCK_DATA")

def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError("XRAY_UNLICENSED_PROVIDER_"+reason)

def validate(doc):
    require(type(doc) is dict and doc.get("schema")=="XRAY_PROVIDER_AUTOMATION_GOVERNANCE_V1","SCHEMA")
    require(doc.get("execution")=="NONE" and doc.get("real_money")=="NO-GO" and doc.get("unknown_never_pass") is True,"NO_TRADE")
    providers=doc.get("providers")
    require(type(providers) is dict and all(x in providers for x in NEW),"SOURCE_MISSING")
    for key in NEW:
        x=providers[key]
        require(type(x) is dict,"SOURCE_OBJECT_"+key)
        require(x.get("code_availability_does_not_grant_market_data_rights") is True,"CODE_RIGHTS_"+key)
        require(x.get("automated_unattended_data_access_attested") is False,"DATA_RIGHTS_"+key)
        require(x.get("license_evidence_status")=="NOT_ATTESTED","LICENSE_"+key)
        for flag in ("positive_price_dv30_promotion_allowed","primary_mc_promotion_allowed",
                     "history_pass_promotion_allowed","r92_promotion_allowed",
                     "strict_g9_promotion_allowed","paid_top_up_allowed"):
            require(x.get(flag) is False,"FALSE_PROMOTION_"+key+"_"+flag)
        require(x.get("execution")=="NONE" and x.get("real_money")=="NO-GO","SOURCE_NO_TRADE_"+key)
        require(type(x.get("official_or_upstream_references")) is list
                and len(x["official_or_upstream_references"])>=2
                and all(type(s) is str and s.startswith("https://") for s in x["official_or_upstream_references"]),
                "SOURCE_REFS_"+key)
    require(providers["TRADINGVIEW_MCP"].get("standard_plan_non_display_algo_use")=="PROHIBITED_UNLESS_EXPLICIT_SEPARATE_RIGHTS","TV_NONDISPLAY_PROHIBITION")
    require(providers["OPENBB_PUBLIC_NASDAQ_CBOE"].get("provider_sdk_data_license_transfer") is False,"OPENBB_FEED_LICENSE_TRANSFER")
    require(providers["GLOBAL_STOCK_DATA"].get("unlicensed_yahoo_sina_cboe_nasdaq_market_data_promoted") is False,"GLOBAL_TOOL_3RD_PARTY_QUOTE_PROMOTION")
    require(providers["GLOBAL_STOCK_DATA"].get("sec_public_filing_facts_not_a_quote_license") is True,"SEC_FACTS_QUOTE_CONFUSION")
    return True

class ThirdPartyDataLicenseGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=json.loads(GOV.read_text())

    def test_real_governance_contains_all_three_fail_closed(self):
        self.assertTrue(validate(copy.deepcopy(self.original)))

    def test_remove_any_provider_is_rejected(self):
        for name in NEW:
            fake=copy.deepcopy(self.original)
            fake["providers"].pop(name,None)
            with self.subTest(name=name),self.assertRaises(ValueError):
                validate(fake)

    def test_false_claimed_permissions_are_rejected(self):
        for name in NEW:
            for flag,value in (
                ("automated_unattended_data_access_attested",True),
                ("license_evidence_status","ATTESTED"),
                ("positive_price_dv30_promotion_allowed",True),
                ("primary_mc_promotion_allowed",True),
                ("history_pass_promotion_allowed",True),
                ("r92_promotion_allowed",True),
                ("strict_g9_promotion_allowed",True),
                ("paid_top_up_allowed",True),
                ("code_availability_does_not_grant_market_data_rights",False),
            ):
                fake=copy.deepcopy(self.original)
                fake["providers"][name][flag]=value
                with self.subTest(source=name,flag=flag),self.assertRaises(ValueError):
                    validate(fake)

    def test_confusing_filing_facts_with_quotes_is_rejected(self):
        fake=copy.deepcopy(self.original)
        fake["providers"]["GLOBAL_STOCK_DATA"]["sec_public_filing_facts_not_a_quote_license"]=False
        with self.assertRaises(ValueError): validate(fake)

    def test_tv_display_only_rights_cannot_turn_into_algo_grant(self):
        fake=copy.deepcopy(self.original)
        fake["providers"]["TRADINGVIEW_MCP"]["standard_plan_non_display_algo_use"]="ALLOWED"
        with self.assertRaises(ValueError): validate(fake)

    def test_openbb_sdk_cannot_transfer_nasdaq_and_cboe_rights(self):
        fake=copy.deepcopy(self.original)
        fake["providers"]["OPENBB_PUBLIC_NASDAQ_CBOE"]["provider_sdk_data_license_transfer"]=True
        with self.assertRaises(ValueError): validate(fake)

if __name__=="__main__":
    unittest.main()
