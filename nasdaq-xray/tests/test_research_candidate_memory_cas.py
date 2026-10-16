#!/usr/bin/env python3
"""Opt-in isolated state branch CAS preimage, authorization and replay tests."""
import base64
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import research_candidate_memory as m
import research_candidate_memory_cas as s
from test_research_candidate_memory_admission import run,artifact,receipt


def github_obj(ledger):
    raw=m.canonical(ledger)+b"\n"
    return {"type":"file","path":s.PATH,"encoding":"base64",
            "content":base64.b64encode(raw).decode("ascii"),
            "sha":s.git_blob_sha(raw)}


class CASBranchTests(unittest.TestCase):
    def setUp(self):
        self.r=run()
        self.a=artifact()
        self.v=receipt()
        self.file=github_obj(m.empty_ledger())

    def plan(self,**kw):
        return s.authorized_proposal(
            kw.get("run",self.r),kw.get("artifact",self.a),
            kw.get("receipt",self.v),kw.get("file",self.file),
            current_asof=kw.get("asof","2026-10-15"),
            expected_run_id=kw.get("run_id",567))

    def test_propose_and_exact_git_blob_round_trip(self):
        p=self.plan()
        self.assertEqual(p["status"],"NEW_ACCEPTED_SESSION")
        self.assertEqual(p["entries"],1)
        self.assertFalse(p["alpha_authority"])
        self.assertEqual(s.git_blob_sha(p["content"]),p["new_blob_sha"])
        result=json.loads(p["content"])
        self.assertEqual(m.validate_ledger(result),
                         result["entries"][-1]["entry_sha256"])
        again=self.plan(file=github_obj(result))
        self.assertEqual(again["status"],"IDEMPOTENT_NO_CHANGE")
        self.assertEqual(again["entries"],1)

    def test_optin_environment_fail_closed(self):
        good={"XRAY_MEMORY_PERSIST_APPROVED":"true",
              "GITHUB_EVENT_NAME":"workflow_run",
              "GITHUB_REF":"refs/heads/main",
              "GITHUB_REPOSITORY":s.REPO,"GH_TOKEN":"fixture"}
        s.check_authorization(good)
        for key,val in (
            ("XRAY_MEMORY_PERSIST_APPROVED","false"),
            ("GITHUB_EVENT_NAME","pull_request"),
            ("GITHUB_REF","refs/heads/xray-research-memory-state"),
            ("GITHUB_REPOSITORY","fake/repo"),
            ("GH_TOKEN",""),
        ):
            with self.subTest(key=key):
                changed={**good,key:val}
                with self.assertRaises(ValueError):
                    s.check_authorization(changed)

    def test_malformed_blob_and_wrong_source(self):
        for key,val in (
            ("sha","a"*40),
            ("path","nasdaq-xray/canonical_current_terminal.json"),
            ("type","dir"),
            ("encoding","utf-8"),
            ("content","!!!not-base64!!!"),
        ):
            with self.subTest(key=key):
                obj=copy.deepcopy(self.file)
                obj[key]=val
                with self.assertRaises((ValueError,Exception)):
                    s.verified_file_response(obj)

    def test_stale_session_revision_and_run_forgery(self):
        p=self.plan()
        ledger=json.loads(p["content"])
        newer=receipt("2026-10-16",{"MSFT":["D"]})
        newer["source_workflow_run_id"]=2020
        newer["watch_membership_digest_sha256"]=m.sha({
            "asof_et":"2026-10-16",
            "technical_setup_family_verified":{"MSFT":["D"]}})
        with self.assertRaisesRegex(ValueError,"WRONG_OFFICIAL_COMPLETED_SESSION"):
            self.plan(file=github_obj(ledger),receipt=newer)
        tampered=copy.deepcopy(self.r)
        tampered["head_branch"]="fork"
        with self.assertRaises(ValueError):
            self.plan(run=tampered)
        revision=copy.deepcopy(self.v)
        revision["source_workflow_run_id"]=44
        with self.assertRaisesRegex(ValueError,"SAME_ASOF_REVISED_RECEIPT"):
            self.plan(file=github_obj(ledger),receipt=revision)

    def test_shares_scope_and_no_market_data(self):
        p=self.plan()
        e=json.loads(p["content"])["entries"][0]
        self.assertEqual(set(e["watch_families"]),{"MANH","WDAY"})
        self.assertNotIn("market_cap",str(e))
        self.assertNotIn("close_price",str(e))
        self.assertFalse(e["alpha_authority"])
        self.assertFalse(e["device_receipt_attested"])

    def test_size_guard(self):
        oversized=copy.deepcopy(self.file)
        oversized["content"]=base64.b64encode(b" " * s.MAX_LEDGER_BYTES).decode("ascii")
        oversized["sha"]=s.git_blob_sha(b" " * s.MAX_LEDGER_BYTES)
        with self.assertRaisesRegex(ValueError,"LEDGER_SIZE_LIMIT"):
            s.verified_file_response(oversized)


if __name__=="__main__":
    unittest.main()
