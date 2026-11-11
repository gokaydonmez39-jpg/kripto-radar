"""Offline RED/GREEN: real ledger readback -> Decision Intelligence, no authority."""
import unittest

from private_research_readback import canonical_sha
from test_private_research_readback import (
    ALG, DAY, RUN, SCOPE, SYMS, fixture, rehash, reseal_score,
)
from unified_evidence_bridge import compose


def run(f, **kw):
    args=dict(expected_asof=DAY,expected_symbols=SYMS,
              expected_algorithm_sha=ALG,expected_run_id=RUN)
    args.update(kw)
    return compose(*f, **args)


def symbol_episode(f, sym):
    e=f[1][2]
    e[0]=DAY+"|2026-11-06|"+sym
    e[2]="2026-11-06|"+sym
    e[3]=sym
    reseal_score(f)


class UnifiedEvidenceBridgeTests(unittest.TestCase):
    def test_complete_477_1431_readonly_upward(self):
        out=run(fixture())
        self.assertEqual((out["scope_count"],out["forecast_count"],out["episode_count"]), (477,1431,1))
        self.assertEqual(out["asof"],DAY)
        self.assertEqual(out["source_run_id"],RUN)
        self.assertEqual(out["source_authentication"],"CALLER_WITNESS_NOT_ATTESTED")
        self.assertEqual(len(out["verdicts"]),1)
        r=out["verdicts"][0]
        self.assertEqual(r["kronos_context"],"UPWARD_FORECAST")
        self.assertEqual(r["source_status"]["KRONOS"],"READY")
        self.assertEqual(r["source_status"]["COVE"],"MISSING")
        self.assertEqual(r["source_status"]["SEC"],"MISSING")
        self.assertEqual(r["source_status"]["CONFIDENCE"],"MISSING")
        self.assertIsNone(r["success_probability"])
        self.assertIsNone(r["net_expected_r"])
        self.assertTrue(all(out[k] is False for k in ("may_notify","may_publish","may_trade","may_modify_al")))
        self.assertTrue(all(r[k] is False for k in ("may_notify","may_publish","may_trade","may_modify_al")))
        self.assertEqual(len(out["source_evidence_sha256"]),64)

    def test_fractional_original_score_preserved(self):
        f=fixture()
        f[1][2][6]="71.8"
        f[1][2][7:14]=["16.0","14.0","11.0","12.0","8.0","7.0","3.8"]
        reseal_score(f)
        self.assertEqual(run(f)["verdicts"][0]["technical_score"],71.8)

    def test_close_only_is_not_native_candle(self):
        f=fixture();symbol_episode(f,"DEMO001")
        r=run(f)["verdicts"][0]
        self.assertEqual(r["kronos_quality"],"RESEARCH_CLOSE_ONLY")
        self.assertIn("NATIVE_OHLC_QUALITY_HOLD",r["flags"])
        self.assertEqual(r["decision_influence"],"NO_GO")

    def test_qc_hold_is_not_a_forecast(self):
        f=fixture();symbol_episode(f,"DEMO002")
        r=run(f)["verdicts"][0]
        self.assertEqual(r["source_status"]["KRONOS"],"HOLD")
        self.assertEqual(r["kronos_context"],"UNAVAILABLE")
        self.assertEqual(r["research_state"],"NO_RESEARCH")
        self.assertIsNone(r["success_probability"])

    def test_conflicting_downward_forecast(self):
        f=fixture()
        for row in f[2][1:4]:
            row[5]="99.000000"
            row[6]="-1.000000"
            rehash(row)
        r=run(f)["verdicts"][0]
        self.assertEqual(r["kronos_context"],"DOWNWARD_FORECAST")
        self.assertIn("TECHNICAL_AL_VS_DOWNWARD_FORECAST",r["flags"])

    def test_resigned_source_close_drift_still_rejected(self):
        f=fixture()
        for row in f[2][1:4]:
            row[4]="99.000000"
            row[6]="2.020202"
            rehash(row)
        with self.assertRaisesRegex(ValueError,"KRONOS_EPISODE_CLOSE_MISMATCH"):
            run(f)

    def test_kronos_missing_entire_month_denied(self):
        f=fixture()
        f[2]=f[2][:1]
        with self.assertRaisesRegex(ValueError,"KRONOS_COHORT"):
            run(f)

    def test_stale_or_wrong_authority_denied(self):
        f=fixture()
        for kw in (dict(expected_run_id="999"),dict(expected_symbols=list(reversed(SYMS))),
                   dict(expected_algorithm_sha="b"*64)):
            with self.subTest(kw=list(kw)),self.assertRaises(ValueError):
                run(f,**kw)

    def test_mutated_score_component_denied(self):
        f=fixture();f[1][2][7]="999.0"
        with self.assertRaisesRegex(ValueError,"SCORE_COMPONENT_MISMATCH"):
            run(f)

    def test_no_open_episodes_no_fabricated_al(self):
        f=fixture();f[1].pop()
        f[1][1][5:9]=["0","0","0","0"]
        reseal_score(f)
        out=run(f)
        self.assertEqual(out["verdicts"],[])
        self.assertEqual(out["episode_count"],0)
        self.assertFalse(out["may_notify"])

    def test_no_real_actions_or_distribution(self):
        f=fixture()
        a=run(f)
        b=run(f)
        self.assertEqual(a,b)
        self.assertEqual(a["source_evidence_sha256"],b["source_evidence_sha256"])
        self.assertNotIn("orders",a)
        self.assertEqual(a["research_only"],True)


if __name__=="__main__":
    unittest.main()
