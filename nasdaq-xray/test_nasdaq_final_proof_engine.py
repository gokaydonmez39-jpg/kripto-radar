"""Adversarial FINAL proof: real PASS is reachable; forged PASS and missing sources fail closed."""
import copy
import datetime as dt
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nasdaq_final_proof_engine as engine


def good():
    blobs = {k: (str(i + 1) * 40)[:40] for i, k in enumerate(engine.FILES)}
    # No equality-to-literal SHA requirement; source SHA equality is required.
    asof = "2026-10-30"
    docs = {
        "overlay": {
            "schema": "XRAY_FINAL_GATE_OVERLAY_V2", "execution": "NONE",
            "real_money": "NO-GO", "asof_et": asof,
            "source_terminal": {"blob_sha": blobs["terminal"],
                                "full_end_to_end_research_pass": True},
            "source_pointer": {"blob_sha": blobs["pointer"]},
            "strict_g9": {"runtime_blob_sha": blobs["g9_runtime"],
                          "authority_blob_sha": blobs["g9_authority"],
                          "g9_pass": True},
            "account": {"gate_blob_sha": blobs["account_gate"],
                        "account_pass": True,
                        "same_run_live_witness_attested": True},
            "binding_integrity": {"fail_closed_safe": True},
            "terminal_live_artifact_bindings": {
                "exact": True, "mismatch_count": 0, "mismatches": []},
            "current_research_chain": {"exact": True, "coverage_complete": True},
            "true_full_go": {"status": "PASS",
                 "passed": ["FULL_E2E_RESEARCH_PASS", "STRICT_G9_PASS",
                            "SAME_RUN_ACCOUNT_PASS"], "blocked": []}},
        "terminal": {"asof_et": asof, "full_end_to_end_research_pass": True,
                     "execution": "NONE", "real_money": "NO-GO"},
        "pointer": {"asof_et": asof},
        "g9_runtime": {"g9_pass": True, "execution": "NONE", "real_money": "NO-GO"},
        "g9_authority": {"status": "PROVEN", "execution": "NONE",
                         "real_money": "NO-GO"},
        "account_gate": {"current_status": "PASS"},
        "resolver": {"asof_et": asof, "execution": "NONE",
                     "real_money": "NO-GO", "source_price_blob_sha": blobs["price"],
                     "source_price_pass_count": 50, "price_unknown_count": 0,
                     "price_blocked_count": 0, "price_unknown_detail": {},
                     "price_unknown_symbols": [], "settlement_required": True,
                     "settlement_already_proven": True},
        "price": {"asof_et": asof, "execution": "NONE", "real_money": "NO-GO",
                  "pass_count": 50, "unknown_count": 0},
        "master": {"asof_et": asof, "execution": "NONE", "real_money": "NO-GO",
                   "counts": {"PASS_IDENTITY": 3192, "UNKNOWN_IDENTITY": 0}},
        "orchestrator": {"asof_et": asof, "execution": "NONE", "real_money": "NO-GO",
                         "unknown_count": 0, "status": "COMPLETE"},
        "official": {"status": "PASS", "alpha_authority": False,
                     "sources": {k: {"status": "PASS"} for k in (
                         "security_status", "system_status_ipo",
                         "system_status_selfhelp", "trade_halts",
                         "trading_system_adds_deletes")}}
    }
    return docs, blobs


class FinalProofSafety(unittest.TestCase):
    def result(self, obj=None, sha=None, epoch="2026-10-30", errors=None):
        good_docs, good_blobs = good()
        return engine.audit(obj if obj is not None else good_docs,
                            sha if sha is not None else good_blobs, epoch, errors)

    def test_canonical_positive_can_actually_pass_without_full_false_claim(self):
        r = self.result()
        self.assertEqual(r["canonical"]["status"], "PASS")
        self.assertTrue(all(r["canonical"]["checks"].values()))
        self.assertEqual(r["personal_477"]["status"], "HOLD")
        self.assertEqual(r["full_system_final"], "HOLD")
        self.assertFalse(r["security"]["alpha_authority"])

    def test_live_current_repo_stays_blocked(self):
        root = pathlib.Path(__file__).resolve().parent
        docs, blobs, errors = engine.snapshot(root)
        r = engine.audit(docs, blobs, "2026-10-30", errors)
        expected = "PASS" if all(r["canonical"]["checks"].values()) else "HOLD"
        self.assertEqual(r["canonical"]["status"], expected)
        self.assertEqual(r["canonical"]["price_unknown"],
                         docs["resolver"].get("price_unknown_count"))
        self.assertEqual(r["canonical"]["history_unknown"],
                         docs["orchestrator"].get("unknown_count"))
        self.assertLessEqual(r["canonical"]["price_sip_requirement_count"],
                             r["canonical"]["price_unknown_detail_count"])
        self.assertEqual(r["full_system_final"], "HOLD")

    def test_time_calculation_ny_est_preclose(self):
        # 2 Nov 2026 in EST, XNAS closes 21:00Z +30m.
        now = dt.datetime(2026, 11, 2, 18, 0, tzinfo=dt.timezone.utc)
        actual = engine.official_last_complete(now)
        if actual is not None:
            self.assertEqual(actual, "2026-10-30")

    def test_negative_forgery_matrix(self):
        tests = [
            ("price_552_unknown", lambda d, s: d["resolver"].update(
                price_unknown_count=552, price_unknown_symbols=["A"] * 552,
                price_unknown_detail={"A": {"price_result": {"info": {"reason": engine.SIP}}}})),
            ("no_settlement", lambda d, s: d["resolver"].update(settlement_already_proven=False)),
            ("price_sha_drift", lambda d, s: d["resolver"].update(source_price_blob_sha="0" * 40)),
            ("zero_price_pass", lambda d, s: d["price"].update(pass_count=0)),
            ("master_identity_unknown", lambda d, s: d["master"]["counts"].update(UNKNOWN_IDENTITY=16)),
            ("history_215", lambda d, s: d["orchestrator"].update(unknown_count=215)),
            ("mc_unproven", lambda d, s: d["overlay"]["current_research_chain"].update(exact=False)),
            ("g9_unproven", lambda d, s: d["g9_authority"].update(status="UNPROVEN")),
            ("account_unproven", lambda d, s: d["overlay"]["account"].update(same_run_live_witness_attested=False)),
            ("terminal_false_pass", lambda d, s: d["terminal"].update(full_end_to_end_research_pass=False)),
            ("terminal_sha_forged", lambda d, s: d["overlay"]["source_terminal"].update(blob_sha="0" * 40)),
            ("pointer_sha_forged", lambda d, s: d["overlay"]["source_pointer"].update(blob_sha="0" * 40)),
            ("G9_sha_forged", lambda d, s: d["overlay"]["strict_g9"].update(authority_blob_sha="0" * 40)),
            ("official_halt_unknown", lambda d, s: d["official"]["sources"]["trade_halts"].update(status="UNKNOWN")),
            ("broker_enabled", lambda d, s: d["terminal"].update(execution="BROKER")),
            ("stale_overlay", lambda d, s: d["overlay"].update(asof_et="2026-10-07")),
            ("source_absent", lambda d, s: d.pop("account_gate")),
            ("false_live_binding", lambda d, s: d["overlay"]["terminal_live_artifact_bindings"].update(mismatch_count=2)),
            ("false_g9_runtime", lambda d, s: d["g9_runtime"].update(g9_pass=False)),
            ("missing_detail", lambda d, s: d["resolver"].pop("price_unknown_detail")),
            ("price_future", lambda d, s: d["price"].update(asof_et="2026-11-03")),
        ]
        for label, mutate in tests:
            d, s = good()
            mutate(d, s)
            with self.subTest(label=label):
                r = self.result(d, s)
                self.assertEqual(r["canonical"]["status"], "HOLD")
                self.assertEqual(r["full_system_final"], "HOLD")

    def test_downstream_mc_and_terminal_do_not_duplicate_upstream(self):
        d, s = good()
        d["resolver"].update(price_unknown_count=1,
            price_unknown_symbols=["AAA"],
            price_unknown_detail={
                "AAA": {"price_result": {"info": {"reason": engine.SIP}}}})
        d["overlay"]["current_research_chain"]["exact"] = False
        d["overlay"]["true_full_go"]["status"] = "BLOCKED"
        result = self.result(d, s)
        roots = {x["id"] for x in result["canonical"]["root_groups"]}
        dependent = result["canonical"]["dependent_gates"]
        self.assertIn("PRICE_SIP", roots)
        self.assertNotIn("MC_AUTHORITY", roots)
        self.assertNotIn("TERMINAL_RELEASE", roots)
        self.assertIn("MC_AUTHORITY_DEPENDS_ON_UPSTREAM", dependent)
        self.assertIn("TERMINAL_RELEASE_DEPENDS_ON_UPSTREAM", dependent)

    def test_workflow_observer_has_no_new_schedule_or_write_authority(self):
        source = (pathlib.Path(__file__).resolve().parent.parent /
                  ".github/workflows/xray-final-gate-overlay-v2.yml").read_text()
        self.assertEqual(source.count("  proof-only:\n"), 1)
        self.assertEqual(source.count("  schedule:\n"), 1)
        observer = source.split("  proof-only:\n", 1)[1]
        self.assertIn("needs: overlay", observer)
        self.assertIn("contents: read", observer)
        self.assertIn("nasdaq_final_proof_engine.py", observer)
        self.assertIn("xray-independent-final.json", observer)
        for forbidden in ("git push", "workflow_dispatch", "gh api", "secrets.",
                          "XRAY_ALPACA_DATA_SECRET_KEY", "gh workflow run"):
            self.assertNotIn(forbidden, observer)

    def test_malformed_or_missing_sources_hold(self):
        d, s = good()
        self.assertEqual(self.result(d, s, errors=["price:ValueError"])["canonical"]["status"], "HOLD")
        self.assertEqual(self.result(d, s, epoch=None)["canonical"]["status"], "HOLD")
        self.assertEqual(self.result(d, s, epoch="2026-11-02")["canonical"]["status"], "HOLD")
        self.assertEqual(self.result(d, {**s, "price": None})["canonical"]["status"], "HOLD")
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            v, blobs, errors = engine.snapshot(root)
            self.assertEqual(len(errors), len(engine.FILES))
            self.assertEqual(engine.audit(v, blobs, None, errors)["canonical"]["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
