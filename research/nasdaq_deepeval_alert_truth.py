"""NASDAQ-only synthetic, no-LLM DeepEval BaseMetric: deterministic alert truth."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json

from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

REQUIRED = frozenset({
    "symbol", "asof_et", "event_key", "event_type",
    "source", "policy_sha", "iex_close", "stop", "target", "device_ack"
})


class EvaluationBlocked(ValueError):
    pass


def _unique_pairs(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise EvaluationBlocked("DUPLICATE_JSON_KEY")
        output[key] = value
    return output


def _bad_constant(_):
    raise EvaluationBlocked("NONFINITE_JSON")


def _read_document(data):
    if not isinstance(data, str) or len(data) > 8192:
        raise EvaluationBlocked("INVALID_DOCUMENT")
    try:
        d = json.loads(data, object_pairs_hook=_unique_pairs, parse_constant=_bad_constant)
    except (ValueError, TypeError) as exc:
        raise EvaluationBlocked("BAD_JSON") from exc
    if not isinstance(d, dict) or set(d) != REQUIRED:
        raise EvaluationBlocked("UNKNOWN_OR_MISSING_FIELD")
    for field in ("symbol", "asof_et", "event_key", "event_type", "source", "policy_sha"):
        if not isinstance(d[field], str) or not d[field] or len(d[field]) > 160:
            raise EvaluationBlocked("INVALID_TEXT_FIELD")
    if type(d["device_ack"]) is not bool:
        raise EvaluationBlocked("INVALID_ACK_TYPE")
    for field in ("iex_close", "stop", "target"):
        value = d[field]
        if type(value) is not str:
            raise EvaluationBlocked("PRICE_STRING_REQUIRED")
        try:
            n = Decimal(value)
        except InvalidOperation as exc:
            raise EvaluationBlocked("PRICE_PARSE_ERROR") from exc
        if not n.is_finite() or n <= 0:
            raise EvaluationBlocked("INVALID_PRICE")
        d[field] = n
    if not (d["stop"] < d["iex_close"] < d["target"]):
        raise EvaluationBlocked("INVALID_STOP_TARGET_ORDER")
    if d["event_type"] != "AL_NEW_EPISODE":
        raise EvaluationBlocked("UNSUPPORTED_FIXTURE_EVENT")
    if d["event_key"] != f'{d["asof_et"]}|{d["symbol"]}|{d["asof_et"]}|AL_NEW_EPISODE|1':
        raise EvaluationBlocked("EVENT_KEY_IDENTITY")
    return d


class NasdaqSyntheticAlertTruthMetric(BaseMetric):
    """Compare strict JSON synthetic notification facts; NEVER model-assisted."""

    def __init__(self):
        self.threshold = 1.0
        self.score = 0.0
        self.success = False
        self.error = None
        self.reason = "NOT_MEASURED"
        self.async_mode = False

    def measure(self, test_case: LLMTestCase) -> float:
        self.score = 0.0
        self.success = False
        self.error = None
        try:
            authoritative = _read_document(test_case.expected_output)
            alleged = _read_document(test_case.actual_output)
            if authoritative["device_ack"] is not False:
                raise EvaluationBlocked("FIXTURE_MUST_NOT_CLAIM_DEVICE_RECEIPT")
            if alleged != authoritative:
                raise EvaluationBlocked("SOURCE_FACT_MISMATCH")
        except (EvaluationBlocked, AttributeError, TypeError):
            self.reason = "BLOCKED_SYNTHETIC_FACT_OR_ACK_MISMATCH"
            return self.score
        self.score = 1.0
        self.success = True
        self.reason = "SYNTHETIC_STRICT_FACTS_MATCH_NOT_REAL_DELIVERY"
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.error is None and self.success and self.score >= self.threshold

    @property
    def __name__(self):
        return "NASDAQ Synthetic Alert Exactness (NO MODEL)"
