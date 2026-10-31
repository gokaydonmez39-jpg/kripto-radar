#!/usr/bin/env python3
"""Independent, synthetic-only review of Trading Hub v1.1.0 research methods.

NO Trading Hub code imported or copied. NO market/broker APIs, account keys,
production AL, Sheets, or crypto. This is NOT C# execution/parity evidence.
"""
import argparse
from itertools import combinations
import json
import math
import random

SOURCE = {
    "repository": "ralphtradesz/trading-hub",
    "release": "v1.1.0",
    "commit": "9c17ef1957ccd20ad2b04feadf2c69241504a86b",
    "reference_paths": [
        "src/TradingHub.Strategies/SmartWalkForward.cs",
        "src/TradingHub.Strategies/BacktestEngine.cs",
        "tests/TradingHub.Tests/SmartWalkForwardTests.cs",
    ],
    "license": "MIT_WITH_COMMONS_CLAUSE_NONCOMMERCIAL_RESTRICTION",
}
NO_AUTHORITY = {
    "may_generate_al": False, "may_change_stops": False,
    "may_write_private_sheet": False, "may_send_notification": False,
    "may_place_order": False, "may_fetch_market_data": False,
    "may_use_private_credentials": False, "alpha_proven": False,
    "csharp_binary_parity_verified": False,
}


def _integer(value, minimum, name):
    if type(value) is not int or value < minimum:
        raise ValueError("INVALID_" + name)
    return value


def _finite(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("INVALID_" + name)
    return float(value)


def costed_long_trade(entry, exit_, quantity, fee_bps, slippage_bps):
    """Independent dollar-PnL arithmetic; NOT Trading Hub's tick-fill engine."""
    entry = _finite(entry, "ENTRY")
    exit_ = _finite(exit_, "EXIT")
    quantity = _finite(quantity, "QUANTITY")
    fee_bps = _finite(fee_bps, "FEE")
    slippage_bps = _finite(slippage_bps, "SLIPPAGE")
    if min(entry, exit_, quantity) <= 0 or min(fee_bps, slippage_bps) < 0:
        raise ValueError("INVALID_TRADE_ECONOMICS")
    buy = entry * (1 + slippage_bps / 10000)
    sell = exit_ * (1 - slippage_bps / 10000)
    if sell <= 0:
        raise ValueError("NONPOSITIVE_EXIT_FILL")
    fees = (buy + sell) * quantity * fee_bps / 10000
    gross = (exit_ - entry) * quantity
    net = (sell - buy) * quantity - fees
    if net > gross + 1e-9:
        raise ValueError("COST_INCREASED_GROSS_PNL")
    return {"gross_usd": round(gross, 8), "net_usd": round(net, 8),
            "cost_usd": round(gross - net, 8)}


def _matrix(rows, *, min_candidates=4, min_days=20):
    if not isinstance(rows, (list, tuple)) or len(rows) < min_candidates:
        raise ValueError("INSUFFICIENT_CANDIDATES")
    if not isinstance(rows[0], (list, tuple)) or len(rows[0]) < min_days:
        raise ValueError("INSUFFICIENT_DAYS")
    days = len(rows[0])
    result = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != days:
            raise ValueError("RAGGED_PNL_MATRIX")
        result.append(tuple(_finite(x, "PNL") for x in row))
    return result


def _sharpe(values):
    n = len(values)
    if n < 2:
        raise ValueError("INSUFFICIENT_SHARPE_SAMPLE")
    mu = sum(values) / n
    variance = sum((x - mu) ** 2 for x in values) / (n - 1)
    if variance <= 1e-24:
        return 1e6 if mu > 0 else -1e6 if mu < 0 else 0.0
    return mu / math.sqrt(variance)


def _bounds(size, groups):
    return [(size * i // groups, size * (i + 1) // groups)
            for i in range(groups)]


def pbo_cscv(rows, blocks=10):
    """CSCV PBO diagnostic on daily PnL. No optimization on genuine market data."""
    data = _matrix(rows)
    blocks = _integer(blocks, 4, "BLOCKS")
    days = len(data[0])
    if blocks % 2 or days < blocks * 5:
        raise ValueError("PBO_BLOCKS_REQUIRE_EVEN_AND_FIVE_DAYS_EACH")
    bounds = _bounds(days, blocks)
    if any((b - a) < 5 for a, b in bounds):
        raise ValueError("PBO_BLOCK_TOO_SHORT")
    below = losses = splits = 0
    for selected_blocks in combinations(range(blocks), blocks // 2):
        chosen = set(selected_blocks)
        is_days = tuple(i for b, (a, z) in enumerate(bounds) if b in chosen
                        for i in range(a, z))
        os_days = tuple(i for b, (a, z) in enumerate(bounds) if b not in chosen
                        for i in range(a, z))
        is_scores = [_sharpe([row[i] for i in is_days]) for row in data]
        os_scores = [_sharpe([row[i] for i in os_days]) for row in data]
        winner = max(range(len(data)), key=lambda c: (is_scores[c], -c))
        # CSCV rank among OOS configs; tie handling is explicit and deterministic.
        rank = 1 + sum(os_scores[c] < os_scores[winner]
                       for c in range(len(data)) if c != winner)
        if 2 * rank <= len(data) + 1:
            below += 1
        if sum(data[winner][i] for i in os_days) <= 0:
            losses += 1
        splits += 1
    return {"splits": splits, "pbo": below / splits, "oos_loss_fraction": losses / splits,
            "oos_rank_definition": "ascending_rank_1_worst_ties_equal"}


def walk_forward_folds(days, train_span=80, test_span=20, purge=15):
    """Strict past-only rolling-origin windows; 15-session label leakage guard."""
    days = _integer(days, 1, "DAYS")
    train_span = _integer(train_span, 1, "TRAIN_SPAN")
    test_span = _integer(test_span, 1, "TEST_SPAN")
    purge = _integer(purge, 1, "PURGE")
    if train_span - purge < 10 or days < train_span + test_span:
        raise ValueError("INSUFFICIENT_WALK_FORWARD_HISTORY")
    result = []
    for test_start in range(train_span, days - test_span + 1, test_span):
        train = tuple(range(test_start - train_span, test_start - purge))
        test = tuple(range(test_start, test_start + test_span))
        if max(train) + purge >= min(test) or set(train) & set(test):
            raise ValueError("WALK_FORWARD_LEAK")
        result.append((train, test))
    return result


def cpcv_folds(days, groups=8, label_horizon=15, embargo=15):
    """All group pairs; remove label overlap and after-test embargo.

    Synthetic index horizon is a stated assumption, NOT actual event availability.
    """
    days = _integer(days, 1, "DAYS")
    groups = _integer(groups, 4, "GROUPS")
    label_horizon = _integer(label_horizon, 1, "LABEL_HORIZON")
    embargo = _integer(embargo, 1, "EMBARGO")
    if days < groups * (label_horizon + 5):
        raise ValueError("INSUFFICIENT_CPCV_HISTORY")
    bounds = _bounds(days, groups)
    output = []
    for a, b in combinations(range(groups), 2):
        test = tuple(i for k in (a, b) for i in range(*bounds[k]))
        train = tuple(i for i in range(days) if all(
            not (i + label_horizon >= bounds[k][0]
                 and i < bounds[k][1] + embargo) for k in (a, b)))
        if len(train) < 10:
            raise ValueError("CPCV_TRAIN_EMPTY")
        if set(train) & set(test):
            raise ValueError("CPCV_LEAK")
        for i in train:
            for k in (a, b):
                start, end = bounds[k]
                if (i + label_horizon >= start and i < end + embargo):
                    raise ValueError("CPCV_LABEL_OR_EMBARGO_LEAK")
        output.append({"groups": (a, b), "train": train, "test": test})
    return output


def _winner(data, train):
    return max(range(len(data)), key=lambda c: (
        _sharpe([data[c][i] for i in train]), -c))


def walk_forward_audit(rows, train_span=80, test_span=20, purge=15):
    data = _matrix(rows)
    folds = walk_forward_folds(len(data[0]), train_span, test_span, purge)
    selected = []
    baseline = []
    choices = []
    for train, test in folds:
        winner = _winner(data, train)
        choices.append(winner)
        selected.extend(data[winner][i] for i in test)
        baseline.extend(data[0][i] for i in test)
    return {"folds": len(folds), "test_days": len(selected),
            "selected_net_synthetic_units": round(sum(selected), 6),
            "fixed_baseline_net_synthetic_units": round(sum(baseline), 6),
            "selected_candidates": choices,
            "is_live_return_evidence": False}


def cpcv_audit(rows, groups=8, label_horizon=15, embargo=15):
    data = _matrix(rows)
    folds = cpcv_folds(len(data[0]), groups, label_horizon, embargo)
    group_hits = [0] * groups
    fold_differences = []
    for fold in folds:
        winner = _winner(data, fold["train"])
        for g in fold["groups"]:
            group_hits[g] += 1
        test = fold["test"]
        fold_differences.append(sum(data[winner][i] - data[0][i] for i in test) / len(test))
    return {"folds": len(folds), "test_appearances_per_group": group_hits,
            "mean_fold_excess_synthetic_units": round(
                sum(fold_differences) / len(fold_differences), 6),
            "fold_results_are_correlated": True,
            "is_genuine_oos_performance": False}


def synthetic_fixture(seed=101, days=320, candidates=8):
    """Deterministic invented daily PnL; planted edge is NOT evidence of alpha."""
    seed = _integer(seed, 0, "SEED")
    days = _integer(days, 200, "DAYS")
    candidates = _integer(candidates, 4, "CANDIDATES")
    rng = random.Random(seed)
    rows = [[rng.gauss(0, 1) for _ in range(days)]
            for _ in range(candidates)]
    rows[-1] = [rng.gauss(0.7, 0.9) for _ in range(days)]
    return rows


def synthetic_report():
    data = synthetic_fixture()
    pbo = pbo_cscv(data)
    wf = walk_forward_audit(data)
    cv = cpcv_audit(data)
    sample_cost = costed_long_trade(100, 101, 10, 4, 5)
    return {"schema": "XRAY_TRADINGHUB_METHOD_COMPARISON_SHADOW_V1",
            "data": "SYNTHETIC_ONLY", "trading_hub_reference": SOURCE,
            "comparison": {
                "shared_concepts": ["PBO_CSCV", "CPCV", "WALK_FORWARD", "COST_MODEL"],
                "differences": [
                    "INDEPENDENT_PYTHON_NOT_TRADING_HUB_CSHARP_BINARY",
                    "SYNTHETIC_DAILY_PNL_NOT_TICK_LEVEL_ORDER_FILLS",
                    "SINGLE_RANK_WINNER_NOT_TRADING_HUB_PLATEAU_SELECTOR",
                    "NO_REAL_XRAY_STRATEGY_OR_MARKET_INPUT",
                    "CPCV_PAIR_FOLDS_CORRELATED_NOT_INDEPENDENT_TRIALS"
                ], "source_methods_verified": "STATIC_SOURCE_INSPECTION_ONLY",
                "numeric_cross_language_parity": "NOT_TESTED"},
            "pbo_cscv": pbo, "walk_forward": wf, "cpcv": cv,
            "illustrative_long_trade_cost": sample_cost,
            "purge_sessions": 15, "label_horizon_sessions": 15,
            "embargo_sessions": 15, "production_scope_symbols_evaluated": 0,
            "network_requests": 0, "no_authority": NO_AUTHORITY,
            "conclusion": "RESEARCH_ONLY_NO_SIGNAL_OR_PRODUCTION_CHANGE"}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic", action="store_true",
                        help="Only permitted mode, no market inputs")
    args = parser.parse_args(argv)
    if not args.synthetic:
        parser.error("--synthetic required; market-data and broker inputs forbidden")
    print(json.dumps(synthetic_report(), sort_keys=True))


if __name__ == "__main__":
    main()
