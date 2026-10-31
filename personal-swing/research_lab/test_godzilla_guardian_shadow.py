"""GODZILLA guardian pure synthetic falsification; no real price or account data."""
import copy
import math
import unittest
from decimal import Decimal

import godzilla_guardian_shadow as g


def scenario():
    return {
        "schema": g.SCHEMA, "source": g.SOURCE,
        "symbol": "TEST", "asof_et": "2026-10-30",
        "scope_sha256": "a" * 64, "algorithm_sha256": "b" * 64,
        "consecutive_xnas_sessions": 52, "universe_477_valid": True,
        "previous_active_episode": False,
        "reference_close": "100", "original_stop": "94",
        "original_target": "112", "hypothetical_next_open": "101",
        "atr14": "3", "paper_equity_usd": "10000",
        "paper_risk_bps": "50", "paper_exposure_cap_bps": "1000",
        "spread_bps": "20", "slippage_bps": "30",
        "fees_bps": "10", "adverse_gap_atr": "2",
    }


class GuardianSyntheticFalsifiers(unittest.TestCase):
    def test_sane_case_paper_only_and_no_trading_go(self):
        out = g.guardian(scenario())
        self.assertEqual(out["decision"], "HOLD")
        self.assertEqual(out["reason"], "PAPER_ONLY_NO_TRADE_APPROVAL")
        self.assertGreater(out["hypothetical_share_cap"], 0)
        self.assertLessEqual(Decimal(out["stressed_paper_loss_usd"]),
                             Decimal(out["paper_risk_budget_usd"]))
        self.assertLessEqual(Decimal(out["stressed_paper_notional_usd"]),
                             Decimal(out["paper_exposure_cap_usd"]))
        for flag in ("automatic_trade", "broker_access", "orders", "can_emit_alert",
                     "real_fill_proven", "live_trading_authorized",
                     "device_ack_proven", "scientific_alpha_proven"):
            self.assertFalse(out[flag])

    def test_atr_gap_stress_is_more_conservative_than_normal_stop(self):
        x = g.guardian(scenario())
        self.assertGreater(Decimal(x["stressed_unit_loss_usd"]),
                           Decimal(x["normal_stop_unit_loss_usd"]))
        self.assertEqual(Decimal(x["stress_exit_price_usd"]), Decimal("88"))

    def test_wider_gap_cannot_increase_share_count(self):
        counts = []
        for gap in ("0", "1", "2", "5", "12", "20"):
            x=scenario(); x["adverse_gap_atr"]=gap
            counts.append(g.guardian(x)["hypothetical_share_cap"])
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_more_slippage_never_increases_shares(self):
        counts=[]
        for slip in ("0", "20", "80", "150", "500"):
            x=scenario(); x["slippage_bps"]=slip
            counts.append(g.guardian(x)["hypothetical_share_cap"])
        self.assertEqual(counts,sorted(counts,reverse=True))

    def test_higher_spread_never_increases_shares(self):
        counts=[]
        for spread in ("0", "20", "50", "200", "500"):
            x=scenario(); x["spread_bps"]=spread
            counts.append(g.guardian(x)["hypothetical_share_cap"])
        self.assertEqual(counts,sorted(counts,reverse=True))

    def test_budget_below_one_share_is_hold(self):
        x=scenario(); x["paper_equity_usd"]="10"
        result=g.guardian(x)
        self.assertEqual(result["hypothetical_share_cap"],0)
        self.assertEqual(result["reason"],"HOLD_PAPER_BUDGET_BELOW_ONE_SHARE")

    def test_prior_active_episode_blocks_new_al_size(self):
        x=scenario(); x["previous_active_episode"]=True
        out=g.guardian(x)
        self.assertEqual(out["reason"],"EXISTING_ACTIVE_EPISODE_NO_SECOND_NEW_AL")
        self.assertEqual(out["hypothetical_share_cap"],0)

    def test_unknown_prior_episode_fails_closed(self):
        for v in (None, "false", 0, 1):
            x=scenario(); x["previous_active_episode"]=v
            with self.subTest(v=v),self.assertRaises(g.GuardianBlocked):
                g.guardian(x)

    def test_open_gap_below_stop_is_not_entry(self):
        x=scenario();x["hypothetical_next_open"]="92"
        o=g.guardian(x)
        self.assertEqual(o["reason"],"NEXT_OPEN_OUTSIDE_ORIGINAL_LEVELS_NO_ENTRY")
        self.assertEqual(o["hypothetical_share_cap"],0)

    def test_open_above_target_is_not_entry(self):
        x=scenario();x["hypothetical_next_open"]="120"
        self.assertEqual(g.guardian(x)["hypothetical_share_cap"],0)

    def test_exact_at_stop_or_target_cannot_be_paper_entry(self):
        for p in ("94","112"):
            x=scenario();x["hypothetical_next_open"]=p
            self.assertEqual(g.guardian(x)["hypothetical_share_cap"],0)

    def test_future_target_tamper_rejected(self):
        x=scenario();x["original_target"]="113"
        with self.assertRaisesRegex(g.GuardianBlocked,"ORIGINAL_TARGET_NOT_2R"):
            g.guardian(x)

    def test_stop_above_reference_rejected(self):
        x=scenario();x["original_stop"]="100.1"
        with self.assertRaisesRegex(g.GuardianBlocked,"IMMUTABLE_LEVEL_GEOMETRY"):
            g.guardian(x)

    def test_excess_atr_to_close_blocks(self):
        x=scenario();x["atr14"]="5"
        with self.assertRaisesRegex(g.GuardianBlocked,"ORIGINAL_ATR_RISK_LIMIT_MISMATCH"):
            g.guardian(x)

    def test_non_477_or_non_52_rejected(self):
        for k,v in (("consecutive_xnas_sessions",51),("consecutive_xnas_sessions",True),
                    ("universe_477_valid",False),("universe_477_valid",1)):
            x=scenario();x[k]=v
            with self.subTest(k=k,v=v),self.assertRaises(g.GuardianBlocked):
                g.guardian(x)

    def test_missing_or_forged_source_hash_rejected(self):
        for k,v in (("scope_sha256",""),("scope_sha256","z"*64),
                    ("algorithm_sha256","A"*64)):
            x=scenario();x[k]=v
            with self.subTest(k=k),self.assertRaises(g.GuardianBlocked):
                g.guardian(x)

    def test_source_and_schema_exclusion(self):
        for k,v in (("schema","XRAY_CRYPTO"),("source","SIP"),
                    ("symbol","btc/usdt"),("asof_et","2026-10-99")):
            x=scenario();x[k]=v
            with self.subTest(k=k),self.assertRaises(g.GuardianBlocked):
                g.guardian(x)

    def test_missing_or_extra_field_blocked(self):
        x=scenario();x.pop("spread_bps")
        with self.assertRaisesRegex(g.GuardianBlocked,"MISSING_OR_EXTRA_FIELDS"):
            g.guardian(x)
        x=scenario();x["api_key"]="secret"
        with self.assertRaisesRegex(g.GuardianBlocked,"MISSING_OR_EXTRA_FIELDS"):
            g.guardian(x)

    def test_nonfinite_floats_rejected(self):
        for v in (float("nan"),float("inf"),float("-inf"),"-Infinity"):
            x=scenario();x["paper_equity_usd"]=v
            with self.subTest(v=str(v)),self.assertRaises(g.GuardianBlocked):
                g.guardian(x)

    def test_negative_and_boolean_cost_rejected(self):
        for v in (-1, True, "501", "nan"):
            x=scenario();x["slippage_bps"]=v
            with self.subTest(v=v),self.assertRaises(g.GuardianBlocked):
                g.guardian(x)

    def test_unbounded_gap_rejected(self):
        x=scenario();x["adverse_gap_atr"]="21"
        with self.assertRaisesRegex(g.GuardianBlocked,"GAP_STRESS_OUTSIDE_BOUND"):
            g.guardian(x)

    def test_total_loss_does_not_exceed_risk_under_tested_scenario(self):
        for budget in ("1","25","50","250","10000"):
            for gap in ("0","2","5","20"):
                x=scenario();x["paper_risk_bps"]=budget;x["adverse_gap_atr"]=gap
                out=g.guardian(x)
                self.assertLessEqual(Decimal(out["stressed_paper_loss_usd"]),
                                     Decimal(out["paper_risk_budget_usd"]))

    def test_repeat_deterministic_input_sha_and_no_implicit_state(self):
        x=scenario()
        a=g.guardian(x);b=g.guardian(copy.deepcopy(x))
        self.assertEqual(a,b)
        x["paper_equity_usd"]="10001"
        self.assertNotEqual(g.guardian(x)["input_sha256"],a["input_sha256"])

    def test_no_implicit_real_portfolio_permission(self):
        x=scenario();x["paper_risk_bps"]="10000";x["paper_exposure_cap_bps"]="10000"
        a=g.guardian(x)
        self.assertFalse(a["live_trading_authorized"])
        self.assertFalse(a["automatic_trade"])
        self.assertEqual(a["decision"],"HOLD")


if __name__ == "__main__":
    unittest.main()
