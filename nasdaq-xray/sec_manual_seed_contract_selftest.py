#!/usr/bin/env python3
import copy
import json
import unittest
from sec_manual_seed_contract import load_registry_document,select_registry_rows,eligible_evidence,sec_source_binds_cik,exact_manual_seed_identity

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
    def test_exact_archive_path_and_seed_identity_fence(self):
        row=doc()["renewals"]["AEAQ"][0]
        self.assertTrue(exact_manual_seed_identity(row))
        base="https://www.sec.gov/Archives/edgar/data/2083689/"
        for url in (base+"../1/other-index.htm",base+"%2e%2e/1/other-index.htm",
                    base+"000121390026118205/",base+"foo/bar-index.htm",
                    base+"document.htm\n",base+"file.exe"):
            with self.subTest(url=url):
                self.assertFalse(sec_source_binds_cik(url,row["cik"]))
        for key,value in (("sic","6770"),("sic",6770.0),("sic",True),
                          ("cik",2083689),("cik","0000000000"),
                          ("cik"," 0002083689"),("evidence_authority","MIRROR"),
                          ("classification","Operating"),("is_blank_check",1)):
            with self.subTest(key=key,value=value):
                self.assertFalse(exact_manual_seed_identity(dict(row,**{key:value})))
        nonblank=dict(row,sic=7374,classification="Data processing",is_blank_check=False)
        self.assertTrue(exact_manual_seed_identity(nonblank))
        self.assertFalse(exact_manual_seed_identity(dict(nonblank,classification="Blank Checks")))

    def test_real_registry_and_historical_135_proofs_preserved(self):
        from pathlib import Path
        import sec_spac_manual_seed_appendonly_guard as legacy
        root=Path(__file__).resolve().parent
        raw=(root/"master_sec_identity_manual_seed_registry.json").read_bytes()
        registry=load_registry_document(raw)
        for sym,row in registry["records"].items():
            with self.subTest(symbol=sym):
                self.assertTrue(exact_manual_seed_identity(row))
        # The genuine 135-row frozen proof and its original 20 negative
        # mutations must still pass in mandatory normal/optimized PR CI.
        legacy.test()
        historic=json.loads((root/"master_sec_spac_proof_20261009.json").read_text())
        original=historic["discovery_coverage"]["manual_seed_registry_blob_sha"]
        current=legacy.git_blob_bytes(raw)
        for key,value in (
            ("source_url","https://www.sec.gov/Archives/edgar/data/1/other-index.htm"),
            ("source_url","https://www.sec.gov/Archives/edgar/data/2092897/../1/other-index.htm"),
            ("sic",6770.0),
        ):
            with self.subTest(key=key,value=value):
                p=copy.deepcopy(historic);s=copy.deepcopy(registry)
                p["proofs"]["AACI"][key]=value
                s["records"]["AACI"][key]=value
                with self.assertRaisesRegex(ValueError,"MANUAL_SEC_ORIGINAL_IDENTITY_INVALID"):
                    legacy.prove(p,s,historic["asof_et"],"AACI",original,current)

    def test_producer_rejects_unofficial_or_coerced_seed_even_with_current_name(self):
        import sys,types,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from importlib import import_module
        with patch.dict(sys.modules,{"pandas_market_calendars":types.ModuleType("pandas_market_calendars")}):
            producer=import_module("build_current_identity_proofs")
        root=producer.ROOT
        actual=load_registry_document((root/"master_sec_identity_manual_seed_registry.json").read_text())
        good=copy.deepcopy(actual["records"]["AACI"])
        names={"AACI":"Armada Acquisition Corp. III - Class A Ordinary Share"}
        # Use a historical date before the discrepancy-witness switch and a
        # temporary registry; never touch the real historical files.
        asof="2026-10-07"
        with tempfile.TemporaryDirectory() as d:
            temp_root=Path(d)/"nasdaq-xray"
            temp_root.mkdir()
            path=temp_root/"master_sec_identity_manual_seed_registry.json"
            fixture=copy.deepcopy(actual)
            fixture["records"]={"AACI":good}
            fixture["renewals"]={}
            with patch.object(producer,"ROOT",temp_root),patch.object(producer,"MANUAL_IDENTITY_SEED",path):
                path.write_text(json.dumps(fixture))
                self.assertEqual(set(producer.manual_identity_seed_registry(asof,names)[0]),{"AACI"})
                for key,value in (("sic","6770"),("sic",6770.0),("evidence_authority","MIRROR"),
                                  ("classification","Other"),("cik",2092897)):
                    with self.subTest(key=key,value=value):
                        fixture["records"]["AACI"]=dict(good,**{key:value})
                        path.write_text(json.dumps(fixture))
                        self.assertEqual(producer.manual_identity_seed_registry(asof,names)[0],{})

    def test_existing_standalone_fvn_and_nbrg_entrypoints(self):
        import subprocess,sys
        from pathlib import Path
        root=Path(__file__).resolve().parent
        for script,marker in (
            ("tests/test_fvn_sec_sic_discrepancy.py",
             "XRAY_FVN_CONTRADICTED_SIC6770=VETOED_KEEP_UNKNOWN_IBAC_NBRG_PRESERVED_NO_ALPHA"),
            ("nbrg_official_sec_identity_seed_selftest.py",
             "XRAY_NBRG_SEC_OFFICIAL_20260803_IDENTITY_SEED=PASS_FAIL_ONLY_NO_PRIMARY"),
        ):
            with self.subTest(script=script):
                # Deliberately use a normal subprocess even under python -O;
                # the historical scripts use asserts, which must remain active.
                completed=subprocess.run([sys.executable,str(root/script)],
                                         cwd=root,capture_output=True,text=True,
                                         timeout=30,check=False)
                self.assertEqual(completed.returncode,0,completed.stderr)
                self.assertIn(marker,completed.stdout)

    def test_real_joint_filer_fvn_veto_and_unrelated_archive_rejected(self):
        import sys,types,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from importlib import import_module
        with patch.dict(sys.modules,{"pandas_market_calendars":types.ModuleType("pandas_market_calendars")}):
            producer=import_module("build_current_identity_proofs")
        root=Path(__file__).resolve().parent
        registry=(root/"master_sec_identity_manual_seed_registry.json").read_bytes()
        witness_name="master_sec_sic_discrepancies_20261009.json"
        witness=json.loads((root/witness_name).read_text())
        names={"FVN":"Future Vision II Acquisition Corporation - Ordinary Shares",
               "IBAC":"IB Acquisition Corp. - Common Stock",
               "NBRG":"Newbridge Acquisition Limited - Class A Ordinary Share"}
        for day,expected in (("2026-10-07",set()),("2026-10-09",{"IBAC","NBRG"})):
            self.assertEqual(set(producer.manual_identity_seed_registry(day,names)[0]),expected)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"nasdaq-xray";p.mkdir()
            seed=p/"master_sec_identity_manual_seed_registry.json";seed.write_bytes(registry)
            with patch.object(producer,"ROOT",p),patch.object(producer,"MANUAL_IDENTITY_SEED",seed):
                for key,value in (
                    ("official_index_url","https://www.sec.gov/Archives/edgar/data/999/000182912626006424/0001829126-26-006424-index.htm"),
                    ("official_index_url","https://www.sec.gov/Archives/edgar/data/2110070/000182912626006424/0001829126-26-006424-index.htm?CIK=1"),
                    ("official_sec_filer_name","Other issuer"),
                    ("official_sec_filer_sic",6770),
                    ("official_accession","0001829126-26-006425"),
                ):
                    with self.subTest(key=key,value=value):
                        changed=copy.deepcopy(witness)
                        changed["discrepancies"]["FVN"][key]=value
                        (p/witness_name).write_text(json.dumps(changed))
                        with self.assertRaisesRegex(RuntimeError,"OFFICIAL_SEC_SIC_DISCREPANCY_BAD_BINDING:FVN"):
                            producer.manual_identity_seed_registry("2026-10-09",names)
                (p/witness_name).write_text(json.dumps(witness))
                self.assertEqual(set(producer.manual_identity_seed_registry("2026-10-09",names)[0]),{"IBAC","NBRG"})

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


    def test_nov25_official_seed_batch_is_forward_only_and_symbol_exact(self):
        import sys, types
        from unittest.mock import patch
        from importlib import import_module
        with patch.dict(sys.modules, {"pandas_market_calendars":
                                      types.ModuleType("pandas_market_calendars")}):
            producer=import_module("build_current_identity_proofs")
        names={"RFAM":"RF Acquisition Corp III - Class A Ordinary Shares",
               "PAXG":"Pine Tree Acquisition Corp. - Class A Ordinary Shares",
               "PAXGR":"Pine Tree Acquisition Corp. - Rights",
               "PAXGU":"Pine Tree Acquisition Corp. - Units",
               "paxg":"Pine Tree Acquisition Corp. - Class A Ordinary Shares"}
        before,_=producer.manual_identity_seed_registry("2026-11-24",names)
        self.assertEqual(before,{})
        now,meta=producer.manual_identity_seed_registry("2026-11-25",names)
        self.assertEqual(set(now),{"RFAM","PAXG","PAXGR"})
        self.assertEqual(meta["record_count"],3)
        for sym,cik,day in (("RFAM","0002091712","2026-11-12"),
                            ("PAXG","0002076561","2026-10-06"),
                            ("PAXGR","0002076561","2026-10-06")):
            row=now[sym]
            self.assertEqual((row["cik"],row["sic"],row["evidence_date"]),
                             (cik,6770,day))
            self.assertEqual(row["verified_asof_et"],"2026-11-25")
            self.assertTrue(row["is_blank_check"])
            self.assertTrue(sec_source_binds_cik(row["source_url"],cik))
            self.assertTrue(sec_source_binds_cik(row["official_ticker_identity_url"],cik))
            self.assertEqual(row["official_ticker_identity_url"],
                             "https://www.sec.gov/Archives/edgar/data/2091712/000182912626007711/rfacquisitioncorp3_10q.htm" if sym=="RFAM" else
                             "https://www.sec.gov/Archives/edgar/data/2076561/000147793226006931/ptree_10q.htm")
            from datetime import date,timedelta
            deadline=(date.fromisoformat(day)+timedelta(days=120)).isoformat()
            expired=(date.fromisoformat(day)+timedelta(days=121)).isoformat()
            self.assertTrue(eligible_evidence(deadline,day,"2026-11-25"))
            self.assertFalse(eligible_evidence(expired,day,"2026-11-25"))
            self.assertIn("NO_ALPHA_PASS",row["seed_semantics"])
        unrelated,_=producer.manual_identity_seed_registry(
            "2026-11-25",{"RFAM":"Unrelated Operating Company",
                          "PAXG":"Unrelated Operating Company"})
        self.assertEqual(unrelated,{})

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


    def test_prior_blank_revalidation_conflicts_are_fail_only_no_io(self):
        import sys,types
        from unittest.mock import patch
        from importlib import import_module
        with patch.dict(sys.modules,{"pandas_market_calendars":types.ModuleType("pandas_market_calendars")}):
            m=import_module("build_current_identity_proofs")
        good={"cik":"0002128462","sic":6770,"classification":"Blank Checks",
              "source_url":"https://www.sec.gov/edgar/browse/?CIK=2128462",
              "evidence_date":"2026-11-23"}
        names={"TLAC":"Three Lions Acquisition Corp."}
        def run(*,pending=(),routes=None,vetoes=(),fresh=None):
            return m.revalidate_prior_blank_proofs(
                {"TLAC":good},fresh or {},{},names,{},"2026-11-25",
                "File Creation Time: 1125202618:01|||||||",["TLAC"],None,
                nonblank_pending_completion=pending,current_cik_map=routes or {},
                prior_blank_vetoes=vetoes)
        # The original fallback alone would accept this prior row even when
        # a newer conflicting classification or issuer route has been found.
        self.assertIsNotNone(m.prior_blank_fallback("TLAC",good,"2026-11-25",names,{}))
        for kw in ({"pending":{"TLAC"}},{"vetoes":{"TLAC"}},
                   {"routes":{"TLAC":2128463}},{"routes":{"TLAC":None}}):
            with self.subTest(kw=kw),patch.object(m,"sec_current_row") as net,patch.object(m,"prior_blank_fallback") as offline:
                proof,unresolved,error=run(**kw)
                self.assertEqual((proof,unresolved,error),({},["TLAC"],None))
                net.assert_not_called()
                offline.assert_not_called()
        # Exact current route and missing discovery route keep the existing
        # bounded fallback behavior, not a new authority path.
        for routes in ({"TLAC":2128462},{}):
            with self.subTest(routes=routes),patch.object(m,"sec_current_row",return_value=None) as net:
                proof,unresolved,error=run(routes=routes)
                self.assertEqual((set(proof),unresolved,error),({"TLAC"},[],None))
                self.assertTrue(m.valid_sec_spac_proof_row(proof["TLAC"],"2026-11-25"))
                net.assert_called_once()
        # Independently acquired current evidence is not a prior fallback.
        with patch.object(m,"sec_current_row") as net,patch.object(m,"prior_blank_fallback") as offline:
            fresh=dict(good,same_asof_revalidated_without_sec_network=False)
            proof,unresolved,error=run(vetoes={"TLAC"},fresh={"TLAC":fresh})
            self.assertEqual((proof,unresolved,error),({"TLAC":fresh},[],None))
            net.assert_not_called()
            offline.assert_not_called()

    def test_real_fvn_witness_cannot_be_resurrected_by_prior_proof(self):
        import sys,types,json
        from unittest.mock import patch
        from importlib import import_module
        with patch.dict(sys.modules,{"pandas_market_calendars":types.ModuleType("pandas_market_calendars")}):
            m=import_module("build_current_identity_proofs")
        old=json.loads(m.MANUAL_IDENTITY_SEED.read_text())["records"]["FVN"]
        names={"FVN":"Future Vision II Acquisition Corporation - Ordinary Shares"}
        # Exact frozen historical source remains unchanged. It would still
        # meet the age and CIK predicates on 9 Oct absent the conflict fence.
        self.assertIsNotNone(m.prior_blank_fallback("FVN",old,"2026-10-09",names,{}))
        vetoes=set()
        manual,_=m.manual_identity_seed_registry("2026-10-09",names,prior_blank_vetoes=vetoes)
        self.assertEqual((manual,vetoes),({},{"FVN"}))
        earlier=set()
        m.manual_identity_seed_registry("2026-10-07",names,prior_blank_vetoes=earlier)
        self.assertEqual(earlier,set())
        with patch.object(m,"sec_current_row") as net,patch.object(m,"prior_blank_fallback") as offline:
            proof,unresolved,error=m.revalidate_prior_blank_proofs(
                {"FVN":old},{},{},names,{},"2026-10-09",
                "File Creation Time: 1009202618:01|||||||",["FVN"],None,
                nonblank_pending_completion=set(),current_cik_map={"FVN":2010653},
                prior_blank_vetoes=vetoes)
            self.assertEqual((proof,unresolved,error),({},["FVN"],None))
            net.assert_not_called()
            offline.assert_not_called()

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


    def test_received_unverified_sec_response_cannot_resurrect_prior_blank(self):
        import sys,types,urllib.error
        from unittest.mock import patch
        from importlib import import_module
        with patch.dict(sys.modules,{"pandas_market_calendars":types.ModuleType("pandas_market_calendars")}):
            m=import_module("build_current_identity_proofs")
        old={"cik":"0002128462","sic":6770,"classification":"Blank Checks",
             "source_url":"https://www.sec.gov/edgar/browse/?CIK=2128462",
             "evidence_date":"2026-11-23"}
        names={"TLAC":"Three Lions Acquisition Corp."}
        asof="2026-11-25"
        good={"cik":2128462,"tickers":["TLAC"],"sic":"6770","sicDescription":"Blank Checks"}
        def run(vetoes=()):
            return m.revalidate_prior_blank_proofs(
                {"TLAC":old},{},{},names,{},asof,
                "File Creation Time: 1125202618:01|||||||",["TLAC"],None,
                nonblank_pending_completion=set(),current_cik_map={"TLAC":2128462},
                prior_blank_vetoes=vetoes)
        # Establish the previously admitted fallback independently, then
        # exercise the actual revalidation loop with provider responses.
        self.assertIsNotNone(m.prior_blank_fallback("TLAC",old,asof,names,{}))
        for payload,filing in (
            (dict(good,cik=2128463),"2026-11-24"),
            (dict(good,tickers=["Tlac"]),"2026-11-24"),
            (dict(good,sic="7373",sicDescription="Services"),"2026-11-24"),
            (dict(good,sic="6770",sicDescription="Services"),"2026-11-24"),
            (dict(good,sic=None),"2026-11-24"),
            (good,None),
            ([],None),
        ):
            with self.subTest(payload=payload,filing=filing),patch.object(m,"_SEC_ISSUER_ACCESS_DENIAL",None),patch.object(m,"load_json_url",return_value=payload),patch.object(m,"latest_filing_date",return_value=filing),patch.object(m,"prior_blank_fallback") as fallback,patch.object(m,"sec_entity_landing_row") as landing:
                self.assertEqual(run(),({},["TLAC"],None))
                fallback.assert_not_called()
                landing.assert_not_called()
        # A verified same-class response and a real access denial preserve
        # their original distinct paths. No new positive authority.
        with patch.object(m,"_SEC_ISSUER_ACCESS_DENIAL",None),patch.object(m,"load_json_url",return_value=good),patch.object(m,"latest_filing_date",return_value="2026-11-24"):
            proof,unresolved,error=run()
            self.assertEqual((set(proof),unresolved,error),({"TLAC"},[],None))
            self.assertFalse(proof["TLAC"]["same_asof_revalidated_without_sec_network"])
        denial=urllib.error.HTTPError("https://data.sec.gov/",403,"denied",{},None)
        with patch.object(m,"_SEC_ISSUER_ACCESS_DENIAL",None),patch.object(m,"load_json_url",side_effect=denial),patch.object(m,"request_bytes") as landing:
            proof,unresolved,error=run()
            self.assertEqual((set(proof),unresolved),({"TLAC"},[]))
            self.assertTrue(proof["TLAC"]["same_asof_revalidated_without_sec_network"])
            self.assertIsNotNone(error)
            landing.assert_not_called()
        # Discovery must carry the negative observation to the prior loop
        # without a second live request, even when a route agrees.
        with patch.object(m,"_SEC_ISSUER_ACCESS_DENIAL",None),patch.object(m,"load_json_url",return_value=dict(good,cik=2128463)) as network:
            vetoes=set()
            self.assertIsNone(m.sec_current_classification("TLAC",asof,2128462,reuse_vetoes=vetoes))
            self.assertEqual(vetoes,{"TLAC"})
            self.assertEqual(run(vetoes),({},["TLAC"],None))
            network.assert_called_once()
        # A bound landing's contrary SIC is also a veto. A generic landing
        # without readable SIC has no contrary observation.
        for body,want in ((b"CIK 0002128462 TLAC SIC: 7373 - Services",True),
                          (b"CIK 0002128462 TLAC SIC: 6770 - Blank Checks",False),
                          (b"CIK 0002128462 TLAC",None)):
            with self.subTest(body=body),patch.object(m,"_SEC_ISSUER_ACCESS_DENIAL",None),patch.object(m,"request_bytes",return_value=body):
                vetoes=set()
                self.assertIsNone(m.sec_entity_landing_row("TLAC",asof,2128462,True if want is None else want,"2026-11-23",reuse_vetoes=vetoes))
                self.assertEqual(vetoes,{"TLAC"} if want is not None else set())
        with patch.object(m,"_SEC_ISSUER_ACCESS_DENIAL",None),patch.object(m,"load_json_url",return_value=good):
            vetoes=set()
            self.assertIsNone(m.sec_current_row("TLAC",asof,2128462,False,reuse_vetoes=vetoes))
            self.assertEqual(vetoes,{"TLAC"})

if __name__=="__main__":
    unittest.main()
