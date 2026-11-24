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
        selected=select_registry_rows(j,"2026-11-24",{"FVN"})
        self.assertEqual(j["records"],old)
        self.assertEqual(set(selected),set(old))
        for sym,versions in j.get("renewals",{}).items():
            self.assertEqual(selected[sym],versions[-1])
            self.assertTrue(eligible_evidence("2026-11-24",selected[sym]["evidence_date"],selected[sym]["verified_asof_et"]))

if __name__=="__main__":
    unittest.main()
