#!/usr/bin/env python3
import copy
import json
import unittest
from sec_manual_seed_contract import load_registry_document,select_registry_rows,eligible_evidence,sec_source_binds_cik

def doc():
    old={"cik":"0002083689","sic":6770,"classification":"Blank Checks","is_blank_check":True,
         "evidence_date":"2026-07-17","verified_asof_et":"2026-10-07",
         "source_url":"https://www.sec.gov/Archives/edgar/data/2083689/old-index.htm",
         "evidence_authority":"SEC_EDGAR_OFFICIAL"}
    new=dict(old,evidence_date="2026-11-12",verified_asof_et="2026-11-24",
             source_url="https://www.sec.gov/Archives/edgar/data/2083689/000121390026118205/0001213900-26-118205-index.htm")
    return {"schema":"XRAY_MASTER_SEC_IDENTITY_MANUAL_SEED_REGISTRY_V1","execution":"NONE",
            "real_money":"NO-GO","unknown_never_pass":True,"authority":"OFFICIAL_SEC_EVIDENCE_DISCOVERY_SEED_ONLY",
            "records":{"AEAQ":old},"renewals":{"AEAQ":[new]}}

class Contract(unittest.TestCase):
    def test_header(self):
        for k,v in [("execution","TRADE"),("real_money","GO"),("unknown_never_pass",False),("schema","WRONG"),("authority","AL"),("records",[]),("renewals",[])]:
            j=doc();j[k]=v
            with self.subTest(k=k),self.assertRaises(RuntimeError):
                load_registry_document(json.dumps(j))
        with self.assertRaises(RuntimeError):
            load_registry_document('{"records":{},"records":{}}')
        j=doc();j["records"][" AEAQ"]=j["records"]["AEAQ"]
        with self.assertRaises(RuntimeError):
            load_registry_document(json.dumps(j))
    def test_exact_url(self):
        a="https://www.sec.gov/Archives/edgar/data/2083689/new-index.htm"
        for url in (a,a+"?CIK=2083689","https://www.sec.gov/edgar/browse/?CIK=0002083689"):
            self.assertTrue(sec_source_binds_cik(url,"0002083689"))
        for url in (a+"?CIK=1",a+"?CIK=2083689&CIK=1",a.replace("2083689","1")+"?CIK=2083689",
                    "https://www.sec.gov/not-a-filing?CIK=2083689","https://www.sec.gov.evil.test/edgar/browse/?CIK=2083689",
                    "https://www.sec.gov/edgar/browse/?CIK=2083689&CIK=2083689"):
            self.assertFalse(sec_source_binds_cik(url,"0002083689"),url)
    def test_pit_and_age(self):
        j=doc();original=copy.deepcopy(j)
        self.assertEqual(select_registry_rows(j,"2026-11-23")["AEAQ"],j["records"]["AEAQ"])
        self.assertEqual(select_registry_rows(j,"2026-11-24")["AEAQ"],j["renewals"]["AEAQ"][0])
        self.assertEqual(j,original)
        self.assertTrue(eligible_evidence("2026-11-24","2026-07-27","2026-11-24"))
        self.assertFalse(eligible_evidence("2026-11-24","2026-07-26","2026-11-24"))
        self.assertFalse(eligible_evidence("2026-11-24","2026-11-25","2026-11-25"))
        self.assertFalse(eligible_evidence("2026-11-24","2026-11-12","2026-11-25"))
        self.assertFalse(eligible_evidence("2026-11-24","2026-02-30","2026-11-24"))
    def test_bad_renewals(self):
        for k,v in [("cik","0000000001"),("sic",7374),("sic","6770"),("is_blank_check",False),
                    ("evidence_date","2026-07-17"),("verified_asof_et","2026-10-07"),
                    ("source_url","https://www.sec.gov/edgar/browse/?CIK=2083689"),
                    ("evidence_authority","MIRROR")]:
            j=doc();j["renewals"]["AEAQ"][0][k]=v
            with self.subTest(k=k),self.assertRaises(RuntimeError):
                select_registry_rows(j,"2026-11-24")
        j=doc()
        with self.assertRaises(RuntimeError):
            select_registry_rows(j,"2026-11-24",{"AEAQ"})
        j["renewals"]["OTHER"]=j["renewals"]["AEAQ"]
        with self.assertRaises(RuntimeError):
            select_registry_rows(j,"2026-11-24")
    def test_unchanged_actual_registry(self):
        from pathlib import Path
        j=load_registry_document((Path(__file__).resolve().parent/"master_sec_identity_manual_seed_registry.json").read_text())
        old=copy.deepcopy(j["records"])
        for sym,versions in j.get("renewals",{}).items():
            for version in versions:
                asof=version["verified_asof_et"]
                selected=select_registry_rows(j,asof,{"FVN"})
                self.assertEqual(set(selected),set(old))
                self.assertEqual(selected[sym],version)
                self.assertTrue(eligible_evidence(asof,version["evidence_date"],version["verified_asof_et"]))
        self.assertEqual(j["records"],old)

    def test_producer_manual_admission_offline(self):
        # Calendar/network operations are not exercised by this test.
        import sys
        import types
        from unittest.mock import patch
        from importlib import import_module
        with patch.dict(sys.modules,{"pandas_market_calendars":types.ModuleType("pandas_market_calendars")}):
            producer=import_module("build_current_identity_proofs")
        names={"AEAQ":"Activate Energy Acquisition Corp.","AESP":"Aeon Acquisition I Corp.",
               "aeaQ":"Unrelated Acquisition Corp."}
        current,meta=producer.manual_identity_seed_registry("2026-11-24",names)
        self.assertEqual(set(current),{"AEAQ","AESP"})
        self.assertEqual(current["AEAQ"]["evidence_date"],"2026-11-12")
        self.assertEqual(current["AESP"]["evidence_date"],"2026-11-18")
        self.assertEqual(meta["record_count"],2)
        self.assertEqual(meta["blob_sha"],producer.file_blob_sha(producer.MANUAL_IDENTITY_SEED))
        before,_=producer.manual_identity_seed_registry("2026-11-23",names)
        self.assertEqual(before,{})
        wrong_case,_=producer.manual_identity_seed_registry("2026-11-24",{"aeaQ":"Other Acquisition Corp."})
        self.assertEqual(wrong_case,{})


    def test_master_live_identity_and_access_fence_offline(self):
        import sys,types,urllib.error
        from unittest.mock import patch
        from importlib import import_module
        with patch.dict(sys.modules,{"pandas_market_calendars":types.ModuleType("pandas_market_calendars")}):
            m=import_module("build_current_identity_proofs")
        for payload,expected in [
            ({"cik":2128462,"tickers":["TLAC"]},True),
            ({"cik":"0002128462","tickers":["TLAC"]},True),
            ({"cik":1,"tickers":["TLAC"]},False),
            ({"tickers":["TLAC"]},False),
            ({"cik":True,"tickers":["TLAC"]},False),
            ({"cik":2128462.0,"tickers":["TLAC"]},False),
            ({"cik":2128462,"tickers":[]},False),
            ({"cik":2128462,"tickers":"TLAC"},False),
            ({"cik":2128462,"tickers":["Tlac"]},False),
            ({"cik":2128462,"tickers":[" TLAC"]},False),
            ({"cik":2128462,"tickers":["TLAC",None]},False),
        ]:
            row=dict(payload,sic="6770",sicDescription="Blank Checks")
            with self.subTest(payload=payload),patch.object(m,"_SEC_ISSUER_ACCESS_DENIAL",None),patch.object(m,"load_json_url",return_value=row),patch.object(m,"latest_filing_date",return_value="2026-11-23"),patch.object(m,"sec_entity_landing_row") as landing:
                self.assertEqual(m.sec_current_classification("TLAC","2026-11-24",2128462) is not None,expected)
                self.assertEqual(m.sec_current_row("TLAC","2026-11-24",2128462,True) is not None,expected)
                landing.assert_not_called()
        for code in (401,403,429):
            exc=urllib.error.HTTPError("https://data.sec.gov/",code,"denied",{},None)
            with self.subTest(code=code),patch.object(m,"_SEC_ISSUER_ACCESS_DENIAL",None),patch.object(m,"load_json_url",side_effect=exc) as network,patch.object(m,"request_bytes") as landing:
                for call in (
                    lambda:m.sec_current_row("TLAC","2026-11-24",2128462,True,"2026-11-23"),
                    lambda:m.sec_current_classification("OTHER","2026-11-24",1234567),
                    lambda:m.sec_entity_landing_row("OTHER","2026-11-24",1234567,True,"2026-11-23"),
                    lambda:m.sec_current_row("OTHER","2026-11-24",1234567,True,"2026-11-23"),
                ):
                    with self.assertRaises(urllib.error.HTTPError) as err:
                        call()
                    self.assertEqual(err.exception.code,code)
                network.assert_called_once()
                landing.assert_not_called()
        transient=urllib.error.HTTPError("https://data.sec.gov/",500,"transient",{},None)
        with patch.object(m,"_SEC_ISSUER_ACCESS_DENIAL",None),patch.object(m,"load_json_url",side_effect=transient),patch.object(m,"sec_entity_landing_row",return_value=None) as landing:
            self.assertIsNone(m.sec_current_row("TLAC","2026-11-24",2128462,True,"2026-11-23"))
            landing.assert_called_once()
            self.assertIsNone(m._SEC_ISSUER_ACCESS_DENIAL)


    def test_blank_proof_source_identity_and_pit(self):
        import sys,types
        from unittest.mock import patch
        from importlib import import_module
        with patch.dict(sys.modules,{"pandas_market_calendars":types.ModuleType("pandas_market_calendars")}):
            m=import_module("build_current_identity_proofs")
        asof="2026-11-24"
        good={"cik":"0002128462","sic":6770,"classification":"Blank Checks",
              "source_url":"https://www.sec.gov/edgar/browse/?CIK=2128462",
              "evidence_date":"2026-11-23","same_asof_revalidated_without_sec_network":False}
        names={"TLAC":"Three Lions Acquisition Corp."}
        self.assertTrue(m.valid_sec_spac_proof_row(good,asof))
        self.assertIsNotNone(m.prior_blank_fallback("TLAC",good,asof,names,{}))
        for field,bad in (
            ("cik","0000000000"),("cik",2128462),("cik","0002128463"),("cik",None),
            ("sic","6770"),("sic",6770.0),("sic",True),("sic",7373),
            ("source_url","https://www.sec.gov/example"),
            ("source_url","https://www.sec.gov/Archives/edgar/data/1/other-index.htm?CIK=2128462"),
            ("source_url","https://www.sec.gov/edgar/browse/?CIK=1"),
            ("classification","Operating company"),
            ("evidence_date","2026-11-25"),("evidence_date","2026-02-30"),
        ):
            row=dict(good,**{field:bad})
            with self.subTest(field=field,bad=bad):
                self.assertFalse(m.valid_sec_spac_proof_row(row,asof))
                self.assertIsNone(m.prior_blank_fallback("TLAC",row,asof,names,{}))
        for bad in (None,0,"false","true"):
            self.assertFalse(m.valid_sec_spac_proof_row(dict(good,same_asof_revalidated_without_sec_network=bad),asof))
        missing=dict(good)
        del missing["same_asof_revalidated_without_sec_network"]
        self.assertFalse(m.valid_sec_spac_proof_row(missing,asof))
        for day,expected in (("2026-07-27",True),("2026-07-26",False)):
            row=dict(good,evidence_date=day)
            out=m.prior_blank_fallback("TLAC",row,asof,names,{})
            self.assertEqual(out is not None,expected)
            if out:
                out["same_asof_nasdaq_directory_footer"]="File Creation Time: 1124202617:01|||||||"
                self.assertTrue(m.valid_sec_spac_proof_row(out,asof))
        landing=dict(good,same_asof_sec_entity_landing_revalidated=True,
                     revalidation_transport="SEC_EDGAR_ENTITY_LANDING",revalidation_asof_et=asof)
        self.assertTrue(m.valid_sec_spac_proof_row(landing,asof))
        self.assertFalse(m.valid_sec_spac_proof_row(dict(landing,evidence_date="2026-07-26"),asof))
        self.assertFalse(m.valid_sec_spac_proof_row(dict(landing,revalidation_asof_et="2026-11-23"),asof))
        with patch.object(m,"request_bytes") as network:
            self.assertIsNone(m.sec_entity_landing_row("TLAC",asof,2128462,True,"2026-07-26"))
            self.assertIsNone(m.sec_entity_landing_row("TLAC",asof,2128462,True,"2026-02-30"))
            network.assert_not_called()

if __name__=="__main__":
    unittest.main()
