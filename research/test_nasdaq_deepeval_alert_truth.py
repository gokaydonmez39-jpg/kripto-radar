"""Synthetic NASDAQ notification truth tests. No model, market, or private Sheet."""
import asyncio
import json
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deepeval.test_case import LLMTestCase
from nasdaq_deepeval_alert_truth import NasdaqSyntheticAlertTruthMetric


def fixture():
    return {
        "symbol": "FAKE", "asof_et": "2026-10-27",
        "event_key": "2026-10-27|FAKE|2026-10-27|AL_NEW_EPISODE|1",
        "event_type": "AL_NEW_EPISODE",
        "source": "SYNTHETIC_IEX_ONLY",
        "policy_sha": "SYNTHETIC_NOT_PRODUCTION_SHA",
        "iex_close": "100.00", "stop": "95.00", "target": "110.00",
        "device_ack": False,
    }


def assess(actual, expected=None):
    d = fixture() if expected is None else expected
    case = LLMTestCase(
        input="Fictional, do not deliver",
        actual_output=actual if isinstance(actual, str) else json.dumps(actual),
        expected_output=json.dumps(d),
    )
    metric = NasdaqSyntheticAlertTruthMetric()
    score = metric.measure(case)
    return metric, score


class TestSyntheticAlertMetric(unittest.TestCase):
    def test_genuine_deepeval_base_metric_and_truth_positive(self):
        metric, score = assess(fixture())
        self.assertEqual(score, 1.0)
        self.assertTrue(metric.is_successful())

    def test_stop_hallucination_rejected(self):
        d = fixture()
        d["stop"] = "90.00"
        self.assertFalse(assess(d)[0].is_successful())

    def test_target_hallucination_rejected(self):
        d = fixture()
        d["target"] = "120.00"
        self.assertFalse(assess(d)[0].is_successful())

    def test_false_iphone_delivery_claim_rejected(self):
        d = fixture()
        d["device_ack"] = True
        self.assertFalse(assess(d)[0].is_successful())

    def test_wrong_ticker_rejected(self):
        d = fixture()
        d["symbol"] = "WRONG"
        self.assertFalse(assess(d)[0].is_successful())

    def test_source_forgery_rejected(self):
        d = fixture()
        d["source"] = "FULL_SIP"
        self.assertFalse(assess(d)[0].is_successful())

    def test_malformed_duplicate_keys_rejected(self):
        text = json.dumps(fixture())
        text = text[:-1] + ', "target": "110.00"}'
        self.assertFalse(assess(text)[0].is_successful())

    def test_untrusted_text_instead_of_json_rejected(self):
        self.assertFalse(assess("Buy now. Delivered to your iPhone.")[0].is_successful())

    def test_nan_and_nonfinite_price_rejected(self):
        d = fixture()
        d["stop"] = "NaN"
        self.assertFalse(assess(d)[0].is_successful())

    def test_event_identity_mismatch_rejected(self):
        d = fixture()
        d["event_key"] = "wrong-key"
        self.assertFalse(assess(d)[0].is_successful())

    def test_async_metric_parity(self):
        d = fixture()
        case = LLMTestCase(input="Fictional", actual_output=json.dumps(d),
                           expected_output=json.dumps(d))
        metric = NasdaqSyntheticAlertTruthMetric()
        result = asyncio.run(metric.a_measure(case))
        self.assertEqual(result, 1.0)
        self.assertTrue(metric.is_successful())


if __name__ == "__main__":
    unittest.main()
