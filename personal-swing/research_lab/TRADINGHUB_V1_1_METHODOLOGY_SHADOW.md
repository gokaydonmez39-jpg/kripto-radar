# XRAY NASDAQ — Trading Hub v1.1.0 independent methodology shadow

Status: **RESEARCH ONLY — NOT MERGED / NOT LIVE AL / NOT VERIFIED AS C# PARITY**.

## Problem / hypothesis, preregistered acceptance

Compare the *methodology* of the public Trading Hub v1.1.0 research engines
without importing or running its GPL-like/noncommercial-restricted source,
shipping any binary, reading real private bars, or changing XRAY production.

Target source: https://github.com/ralphtradesz/trading-hub/releases/tag/v1.1.0
Pinned public source commit:
`9c17ef1957ccd20ad2b04feadf2c69241504a86b`
Reviewed paths:
- `src/TradingHub.Strategies/SmartWalkForward.cs`: PBO/CSCV, CPCV and overfit controls.
- `src/TradingHub.Strategies/BacktestEngine.cs`: commissions, slippage and event-driven order fills.
- `tests/TradingHub.Tests/SmartWalkForwardTests.cs`: published synthetic expectations.

License: **MIT with Commons Clause** (not OSI-approved open-source). No source
code was copied or imported; comparisons are independently authored Python.

Success contract, fixed *before* interpreting results:

1. Python normal and `-O` GitHub PR CI must both pass.
2. Synthetic PBO using 10 groups must yield **252** combinatorial splits.
2a. Exploratory null sanity gate, **declared before executing the seeds**:\n    10 independent PRNG seeds 2000..2009, eight noise-only candidates,\n    320 synthetic days each; average PBO must be in [0.30, 0.70].\n    Perfectly tied zero-PnL strategies must conservatively report PBO=1\n    and OOS loss fraction=1. This is deliberately coarse; even a PASS\n    does not independently validate real-market probability calibration.\n3. CPCV using 8 groups must yield **28** test-group pairs and **7** test
   appearances per group; **15-session label horizon** and **15-session
   embargo** must exclude overlapping training labels and after-test samples.
4. Rolling-origin split must keep training strictly before every test block,
   remove a **15-session purge**, and not use each fold's test PnL for selection.
5. Higher fees or slippage must never improve identical long-trade net PnL;
   small positive gross outcomes must be capable of turning negative after costs.
6. NaN, Inf, short/ragged data and malformed parameters must fail closed.
7. No broker calls, private data, actual ticker names, provider URLs, production
   scan, AL/stop change, Sheet write or notification is permitted.

Execute from the repo root:

```sh
python -m unittest discover -v -s personal-swing/research_lab -p 'test_*.py'
python -O -m unittest discover -v -s personal-swing/research_lab -p 'test_*.py'
python personal-swing/research_lab/tradinghub_methodology_shadow.py --synthetic
```

## Method comparison and falsifiability

| Dimension | Trading Hub v1.1.0 (static code inspection) | XRAY independent shadow | Unresolved parity |
|---|---|---|---|
| CSCV/PBO | 10-block OOS ranks, IS Sharpe selection | 10-block OOS ranks, 252 splits | Same conceptual family; actual C# output **not executed** |
| CPCV | 8-group pair folds, neighboring embargo, plateau winner | 8 groups, 28 pairs, explicit 15-session label overlap and embargo, Sharpe winner | Different selection and paths; numerical parity **not claimed** |
| Walk-forward | Rolling OOS and parameter optimization/TPE | Past-only synthetic PnL fold selection with fixed baseline candidate 0 | No TPE or tick execution; cannot compare strategy profitability |
| Costs | Tick-level order-fill engine, slippage ticks and commission | Long-only entry/exit bps independent arithmetic | Different units and fill semantics; not interchangeable |
| Historical PIT | Does not by itself prove SEC/Alpaca first-seen/issuer lineage | Artificial index labels only | Both remain **UNPROVEN** |
| Rights | Provider connections and paid third-party data may be involved | No network, no real prices, no provider keys | No rights to ingest vendor data implied |

The synthetic generator plants a deliberately stable positive-mean candidate
among noise candidates. It is a **positive-control test**, not return research.
PBO with only noise / unstable regimes can vary dramatically. Passing synthetic
controls does **not** establish that either implementation is statistically
calibrated to real NASDAQ events.

### Anti-bias controls

- **Lookahead:** each rolling train index + purge is strictly below its test
  start. CPCV disallows label overlaps and explicit post-test embargo. These
  controls are based on *synthetic indices*; real event first-seen timestamps
  are NOT validated.
- **Selection:** fixed synthetic candidate 0 is baseline, with only train
  values used to select a fold's candidate. No benchmark beating claimed.
- **Survivorship, corporate actions, source rights:** NOT TESTED (no real
  market inputs). Cannot address 477 historical-issuer evidence deficiency.
- **Fees/slippage:** positive-side charge model intentionally penalizes
  returns; requires a separate realistic price-unit/tick/queue model for
  real deployment.
- **CPCV independence:** group-pair observations overlap and are correlated;
  28 pairs must NOT be reported as 28 independent experiments or as actual
  28 fully independent OOS paths.
- **External method:** source implementation has its own specific winner
  selection/tick dynamics; this audit is **not a port, a library dependency,
  a financial backtest, or cross-language numeric parity validation**.

## Decision and rollback

Until independent C# reference-output fixtures and genuine rights-cleared,
PIT-safe 500+ XNAS sessions with an embargoed OOS design exist, status remains
**METHODOLOGY_PROBE_PASS_ONLY**, not a promotion candidate. The standalone
shadow is deliberately outside EOD jobs, NASDAQ pipeline, risk model,
Google Sheets, crypto, notification channels and 88-source registry.

Rollback: close this draft PR and delete the isolated branch; production main
has no dependencies on these new files. No migration/rollback of production
state is necessary.
