"""A37 read-only aggregate receipt audit. No broker, network, Sheets or alerts.

An aggregate checksum verifies arithmetic and gating, not the truth of raw vendor data.
"""
import json
from pathlib import Path
import exchange_calendars as ec

SCHEMA = "XRAY_PERSONAL_A37_CONNECTED_IEX_SNAPSHOT_AUDIT_V1"
SCOPE_SHA = "420025dd5b83b59fedd3d9af4332471fee731aedfaacb616ce80ca473bef6745"
METRICS = ("above_sma20", "above_sma50", "positive_relative_to_qqq_63")
DENIALS = ("historical_point_in_time_provenance_verified",
           "corporate_actions_coverage_verified",
           "historical_universe_membership_verified",
           "cross_provider_reconciled", "license_redistribution_verified",
           "backtest_oos_completed", "performance_lift_verified",
           "production_al_enabled", "new_alerts_emitted")


class ReceiptRejected(ValueError):
    pass


def _need(value, code):
    if not value:
        raise ReceiptRejected(code)


def _int_exact(x, expected=None):
    _need(type(x) is int and x >= 0, "NON_INTEGER_COUNT")
    if expected is not None:
        _need(x == expected, "COUNT_MISMATCH")
    return x


def validate(receipt):
    _need(isinstance(receipt, dict) and receipt.get("schema") == SCHEMA, "BAD_SCHEMA")
    _need(receipt.get("asof_et") == "2026-10-28", "UNEXPECTED_ASOF")
    _need(receipt.get("observed_date_utc") == "2026-10-29", "BAD_READ_DATE")
    _need(receipt.get("feed") == "iex" and receipt.get("basis") == "raw", "BAD_FEED")
    _need(receipt.get("source") == "Alpaca connected-app daily IEX", "BAD_SOURCE")
    _need(receipt.get("scope_sha256") == SCOPE_SHA, "SCOPE_MISMATCH")
    _need(receipt.get("benchmark") == "QQQ", "BENCHMARK_MISMATCH")
    _int_exact(receipt.get("universe"), 477)
    _int_exact(receipt.get("series_count"), 478)
    _int_exact(receipt.get("expected_bars_per_series"), 64)
    _int_exact(receipt.get("observed_required_bar_cells"), 30592)
    _int_exact(receipt.get("official_xnas_sessions"), 64)
    _need(receipt.get("include_partial_2026_10_29") is False, "PARTIAL_SESSION_LEAK")
    cal = ec.get_calendar("XNAS")
    sessions = cal.sessions_in_range("2026-07-01", receipt["asof_et"])
    days = [x.date().isoformat() for x in sessions][-64:]
    _need(len(days) == 64 and days[0] == receipt.get("first_required_xnas_session")
          and days[-1] == receipt.get("last_required_xnas_session"), "SESSION_MISMATCH")
    _need(receipt.get("research_only") is True
          and receipt.get("raw_market_bars_persisted") is False,
          "UNSUPPORTED_RAW_EVIDENCE_CLAIM")
    for key in DENIALS:
        _need(receipt.get(key) is False, "ILLEGAL_PROMOTION_" + key)
    _need(receipt.get("adjustment_parameter_explicitly_set") is False,
          "UNVERIFIED_ADJUSTMENT_PARAMETER_MUST_NOT_CLAIM_PASS")
    _need(receipt.get("known_unadjusted_split_conflicts") == ["IESC", "MNST"],
          "CA_SPLIT_CONFLICT_UNDISCLOSED")
    observed = receipt.get("known_split_events")
    _need(isinstance(observed, list) and len(observed) == 2,
          "CA_EVENT_WITNESS_MISSING")
    for event, symbol, date, witness_id in zip(observed,
                ("IESC", "MNST"), ("2026-08-24", "2026-08-11"),
                ("6be13843-233a-469f-91be-b139fe4738f7",
                 "e639b77a-af3f-411a-878b-fe2b40cff68a")):
        _need(isinstance(event, dict)
              and event.get("symbol") == symbol
              and event.get("ex_date") == date
              and event.get("type") == "forward_split"
              and event.get("old_rate") == 1
              and event.get("new_rate") == 2
              and event.get("alpaca_action_id") == witness_id,
              "CA_EVENT_WITNESS_CHANGED")
    _need(receipt.get("ca_cleared_aggregate_metrics") is False
          and receipt.get("cross_date_raw_relative_returns_safe") is False
          and receipt.get("research_release_status")
              == "BLOCKED_UNVERIFIED_CA_ADJUSTMENT_AND_PIT",
          "UNVERIFIED_CA_AGGREGATES_MUST_BE_BLOCKED")
    groups = receipt.get("groups")
    _need(isinstance(groups, list) and len(groups) == 4, "INVALID_GROUP_COUNT")
    next_index = 0
    sums = dict(scanned_symbols=0, **{key: 0 for key in METRICS})
    for group in groups:
        _need(isinstance(group, dict), "BAD_GROUP")
        _int_exact(group.get("first_index"), next_index)
        n = _int_exact(group.get("series"))
        _need(n > 0 and _int_exact(group.get("last_index")) == next_index+n-1,
              "BATCH_GAP_OVERLAP")
        _int_exact(group.get("missing_official_sessions"), 0)
        sums["scanned_symbols"] += n
        for k in METRICS:
            count = _int_exact(group.get(k))
            _need(count <= n, "GROUP_METRIC_OUT_OF_RANGE")
            sums[k] += count
        next_index += n
    _int_exact(next_index, 477)
    total = receipt.get("totals")
    _need(isinstance(total, dict), "MISSING_TOTALS")
    _int_exact(total.get("scanned_symbols"), 477)
    for k in METRICS:
        _int_exact(total.get(k), sums[k])
    _need(abs(float(receipt.get("benchmark_return_63_pct_approx"))-6.14248) < .000001,
          "BENCHMARK_MISMATCH")
    return {"status":"AGGREGATE_RECONCILED_BLOCKED_CA_PIT",
            "covered":477, "series":478, "required_bars":30592,
            "sma20_pct":round(100*sums["above_sma20"]/477, 6),
            "sma50_pct":round(100*sums["above_sma50"]/477, 6),
            "rs63_positive_pct":round(100*sums["positive_relative_to_qqq_63"]/477, 6),
            "may_issue_al":False, "may_write_sheet":False, "may_trade":False}


def main():
    path = Path(__file__).with_name("a37_connected_iex_20261028_receipt.json")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps(validate(receipt), sort_keys=True))


if __name__ == "__main__":
    main()
