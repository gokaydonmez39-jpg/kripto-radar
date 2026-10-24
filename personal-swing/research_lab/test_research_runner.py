"""Synthetic security and source research checks. No real stock data or network."""
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import json
import unittest
from urllib.error import HTTPError

from research_runner import (
    compare_pair, github_monitor, read_registry, registry_check
)

def synthetic_pair():
    def sample(provider,scope,basis,c):
        return {"ticker":"CVLT","provider":provider,"scope":scope,"basis":basis,
                "attested_data_rights":True,
                "bars":[{"session":"2026-10-23","known_at_utc":"2026-10-23T21:15:00Z",
                         "open":100.0,"high":102.0,"low":98.0,"close":c,"volume":500.0}]}
    return {"schema":"XRAY_RESEARCH_BAR_PAIR_V1","ticker":"CVLT",
            "asof_et":"2026-10-23","cutoff_utc":"2026-10-23T22:00:00Z",
            "left":sample("FAKE_A","IEX","RAW",100.0),
            "right":sample("FAKE_B","US_CONSOLIDATED","RAW",100.5)}

class FakeHTTPResponse(BytesIO):
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

class ResearchRunnerTest(unittest.TestCase):
    def setUp(self):
        self.registry=read_registry()
    def rejected(self,mutator,code):
        p=synthetic_pair()
        mutator(p)
        with self.assertRaisesRegex(ValueError,code):
            compare_pair(p)

    def test_registry_is_88_unique_and_disabled(self):
        report=registry_check(self.registry)
        self.assertEqual(report["unique"],88)
        self.assertFalse(report["live_production_sources_authorized"])
        self.assertEqual(report["groups"]["REFERENCE_49"],49)
        self.assertEqual(report["groups"]["EMERGING_13"],13)

    def test_registry_source_never_promotion(self):
        doc=deepcopy(self.registry)
        doc["entries"][0]["may_issue_al"]=True
        with self.assertRaisesRegex(ValueError,"UNAUTHORIZED_SOURCE_SIDE_EFFECT"):
            registry_check(doc)

    def test_registry_duplicate(self):
        doc=deepcopy(self.registry)
        doc["entries"][2]["key"]=doc["entries"][1]["key"]
        with self.assertRaisesRegex(ValueError,"DUPLICATE_SOURCE_KEY"):
            registry_check(doc)

    def test_synthetic_different_tape_context_only(self):
        x=compare_pair(synthetic_pair())
        self.assertEqual(x["comparison"],"DIFFERENT_VENUE_OR_ADJUSTMENT_NOT_INTERCHANGEABLE")
        self.assertEqual(x["closing_differences"][0]["delta_close_usd"],0.5)
        self.assertFalse(x["may_generate_al"])
        self.assertFalse(x["may_write_private_sheet"])

    def test_wrong_source_rights(self):
        self.rejected(lambda p:p["right"].__setitem__("attested_data_rights",False),
                      "DATA_RIGHTS_ATTESTATION_MISSING")

    def test_future_leak(self):
        self.rejected(lambda p:p["right"]["bars"][0].__setitem__(
            "known_at_utc","2026-10-24T00:00:00Z"),"LOOKAHEAD_BAR_UNAVAILABLE")

    def test_unverified_source_basis(self):
        self.rejected(lambda p:p["right"].__setitem__("basis","WILD"),
                      "VENUE_OR_ADJUSTMENT_BASIS_UNVERIFIED")

    def test_cross_symbol_mix(self):
        self.rejected(lambda p:p["right"].__setitem__("ticker","LOGI"),
                      "TICKER_OR_CLASS_MISMATCH")

    def test_bad_ohlc_geometry(self):
        self.rejected(lambda p:p["right"]["bars"][0].__setitem__("high",99),
                      "INVALID_OHLC_GEOMETRY")

    def test_missing_asof(self):
        self.rejected(lambda p:p["right"]["bars"][0].__setitem__("session","2026-10-22"),
                      "MISSING_MATCHED_FINAL_SESSION")

    def test_future_bar(self):
        self.rejected(lambda p:p["right"]["bars"][0].__setitem__("session","2026-10-24"),
                      "FUTURE_OR_NONCANONICAL_SESSION")

    def test_duplicate_provider(self):
        self.rejected(lambda p:p["right"].__setitem__("provider","FAKE_A"),
                      "REQUIRES_TWO_DIFFERENT_SOURCES")

    def test_github_monitor_fixture_only(self):
        seen=[]
        def fetch(req, timeout=None):
            seen.append(req.full_url)
            repo=req.full_url.removeprefix("https://api.github.com/repos/")
            b=json.dumps({"full_name":repo,"archived":False,
                         "pushed_at":"2026-10-23T00:00:00Z",
                         "default_branch":"main"}).encode("utf-8")
            return FakeHTTPResponse(b)
        out=github_monitor(self.registry,opener=fetch)
        self.assertEqual(out["sources_checked"],22)
        self.assertTrue(all(x["status"]=="AVAILABLE" for x in out["result"]))
        self.assertTrue(all(x.startswith("https://api.github.com/repos/") for x in seen))
        self.assertFalse(out["market_data_fetched"])

    def test_github_network_errors_report_unknown(self):
        def error(req,timeout=None):
            raise HTTPError(req.full_url,403,"test failure",{},None)
        result=github_monitor(self.registry,opener=error)
        self.assertEqual(result["sources_checked"],22)
        self.assertTrue(all(r["status"]=="UNKNOWN_UNREACHABLE" for r in result["result"]))

if __name__=="__main__":unittest.main()
