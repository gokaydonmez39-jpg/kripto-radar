"""Offline, no-network hostile fixtures for social ticker identity quarantine."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from social_tip_identity_shadow import assess, validate_tip, validate_master

HEX64 = "a" * 64
TIP = {
    "schema":"XRAY_UNTRUSTED_SOCIAL_TIP_TEN_V1",
    "source_url":"https://x.com/aura_lixx/status/2111615210503168164",
    "observed_at":"2026-10-18",
    "tickers":["MP","CRWV","SMR","UUUU","OUST","RKLB","NBIS","TMDX","VRT","ASTS"],
    "source_kind":"USER_SCREENSHOT_UNVERIFIED_INVESTMENT_CLAIMS",
    "execution":"NONE","real_money":"NO-GO",
    "production_authority":False,"r92_authority":False,"can_notify_user":False
}
MASTER = {
    "asof_et":"2026-10-16",
    "identity_authority":"NASDAQTRADER_EXPLICIT_TYPE_FILTER_V6_ASOF_IDENTITY_AND_SPAC_PROOF_AT_MASTER",
    "pass_symbols":["ASTS","CRWV","NBIS","OUST","RKLB","TMDX"],
    "unknown_symbols":["QQQQ"], "pass_count":6, "unknown_count":1,
    "counts":{"PASS_IDENTITY":6,"UNKNOWN_IDENTITY":1},
    "unknown_never_pass":True,"execution":"NONE","real_money":"NO-GO"
}

def copy(x):
    return json.loads(json.dumps(x))

def raw(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":")).encode()

class TestSocialTipIdentityQuarantine(unittest.TestCase):
    def test_positive_six_identity_only_four_not_proven(self):
        result=assess(copy(TIP),copy(MASTER),raw(MASTER))
        self.assertEqual(result["status"],"RESEARCH_ONLY_IDENTITY_SCREEN_NO_AL")
        self.assertEqual(result["identity_only_symbols"],["ASTS","CRWV","NBIS","OUST","RKLB","TMDX"])
        self.assertEqual(result["not_in_master_symbols"],["MP","SMR","UUUU","VRT"])
        self.assertEqual(result["unknown_identity_symbols"],[])
        self.assertEqual(result["asof_et"],"2026-10-16")
        self.assertEqual(result["master_blob_sha256"],hashlib.sha256(raw(MASTER)).hexdigest())
        self.assertFalse(result["price_verified"])
        self.assertFalse(result["production_authority"])
        self.assertFalse(result["r92_authority"])
        self.assertEqual(result["buy_signals"],0)
        self.assertEqual(result["notifications"],0)

    def test_unknown_identity_never_becomes_identity_pass(self):
        master=copy(MASTER); master["unknown_symbols"]=["MP"]
        result=assess(copy(TIP),master,raw(master))
        self.assertEqual(result["unknown_identity_symbols"],["MP"])
        self.assertNotIn("MP",result["identity_only_symbols"])

    def test_master_asof_before_social_post_and_distinct(self):
        tip=copy(TIP); tip["observed_at"]="2026-10-16"
        with self.assertRaises(ValueError): assess(tip,copy(MASTER),raw(MASTER))

    def test_duplicate_tip_rejected(self):
        tip=copy(TIP); tip["tickers"][1]="MP"
        with self.assertRaises(ValueError): validate_tip(tip)

    def test_lowercase_or_unsafe_symbol_rejected(self):
        for symbol in ["mp","../secret","A B","", "A"*12]:
            tip=copy(TIP);tip["tickers"][0]=symbol
            with self.subTest(symbol=symbol),self.assertRaises(ValueError):
                validate_tip(tip)

    def test_unexpected_social_authority_rejected(self):
        for name, value in [("production_authority",True),("r92_authority",True),("can_notify_user",True),("execution","TRADE"),("real_money","GO")]:
            tip=copy(TIP);tip[name]=value
            with self.subTest(name=name),self.assertRaises(ValueError):
                validate_tip(tip)

    def test_tip_exact_source_and_bounded_tickers(self):
        for name,value in [("source_url","https://evil.example"),("schema","other"),("source_kind","MARKET_DATA"),("tickers",["MP"])]:
            tip=copy(TIP);tip[name]=value
            with self.subTest(name=name),self.assertRaises(ValueError):
                validate_tip(tip)

    def test_master_cannot_claim_mismatched_counts(self):
        master=copy(MASTER); master["pass_count"]=7
        with self.assertRaises(ValueError): validate_master(master)

    def test_master_unknown_identity_not_in_pass(self):
        master=copy(MASTER);master["unknown_symbols"]=["ASTS"]
        with self.assertRaises(ValueError): validate_master(master)

    def test_master_cannot_claim_unsafe_authority(self):
        for name,value in [("unknown_never_pass",False),("identity_authority","TWITTER"),("execution","TRADE"),("real_money","GO")]:
            master=copy(MASTER);master[name]=value
            with self.subTest(name=name),self.assertRaises(ValueError):
                validate_master(master)


    def test_source_bytes_must_match_claimed_master_structure(self):
        forged = copy(MASTER)
        forged["unknown_symbols"] = ["VRT"]
        with self.assertRaises(ValueError):
            assess(copy(TIP), forged, raw(MASTER))

    def test_invalid_source_bytes_are_never_accepted(self):
        with self.assertRaises(ValueError):
            assess(copy(TIP), copy(MASTER), b"not json")

    def test_missing_master_identity_is_not_a_nyse_proof(self):
        x=assess(copy(TIP),copy(MASTER),raw(MASTER))
        self.assertEqual(x["not_in_master_classification"],"NOT_IN_NASDAQ_MASTER_ASOF_NOT_EXCHANGE_PROOF")

if __name__=="__main__":
    unittest.main()
