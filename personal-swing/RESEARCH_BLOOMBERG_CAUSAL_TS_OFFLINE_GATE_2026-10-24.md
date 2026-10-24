# XRAY / Bloomberg causal-ts — OFFLINE FEASIBILITY ONLY

**Status: RESEARCH_SPEC_ONLY; NOT CONNECTED, NOT INSTALLED, NOT BACKTESTED, NOT INTEGRATED.**
Reviewed 2026-10-24. Upstream https://github.com/bloomberg/causal-ts
Upstream HEAD: 0d1fae061b2445a51d0c8b75fc565d897dd54fb7 (2026-10-20).
PyPI tagged release v0.27.0 (2026-09-10) predates fixes to lag-0 edge orientation and ill-conditioned partial correlation inversion, so exact code and dependency revisions must be pinned in a future *isolated* experiment.
License GPL-3.0-or-later (includes GPL Tigramite-derived code); legal review before source copying, derivative distribution or linking. No Bloomberg source code has been copied.

## Thesis and boundary
causal-ts is a **statistical discovery algorithm**, not a market data provider or a confirmed stock-return predictor. Observational edge != established causal effect != profitable AL signal.

Experimental use, if approved later:
1. Single-target `select_features(algo="cedar", markov_blanket=False)` to rank **lagged** candidate causes/features. Repository advertises target-mode O(d); full CEDAR graph O(d^2). A full 477-variable graph is out of scope.
2. Compare predeclared CEDAR with LASSO/AR baseline and independently CDNOTS+ on a small selected factor set; only if warranted test GRACE. Treat regime/hidden-confounder routines (LUCID, C-node) as hypothesis diagnostics, not proof.
3. Temporal contiguous-window bootstrap performed inside training partitions only, edge persistence is stability not causality.

## Input gate
- Private and licit read-only historical XNAS OHLCV data; provider basis IEX vs SIP tagged and not mixed, ticker/issuer PIT identity, splits, halts, official sessions validated. Nothing copied into the public repository.
- At least 500 complete comparable historical daily sessions is an **initial experiment heuristic**; 52 official XNAS sessions for the existing live screen is NOT causal model training evidence. 15 future sessions of candidate monitoring are outcomes, not an input training set.
- Train only on data available before the EOD cutoff. For t+1 forecast, only lagged/ex-ante values permissible. ALFRED revisions or regulatory releases require exact first-publication timestamp, otherwise UNKNOWN.
- Pilot pre-registers one target, 8–20 covariates, lags 1–5, transforms and hyperparameter selection on TRAIN ONLY; macro/sector inputs only if separate data rights verified.

## Evaluation gate
- Synthetic known causal graph test; placebo shuffled time and label tests; controls for hidden sector/market factors, regime instability, incorrect lag-0 orientation, ill-conditioned covariance, provider mismatch, missing sessions and corporate actions.
- Purged and embargoed rolling-origin walk-forward, accounting for 15-session overlapping labels when using such an outcome. Training-only temporal bootstrap, seed and SHA locked, multiple-testing control, negative controls.
- Baseline unchanged 477 EOD AL/IZLE/ELE and 15-session lifecycle; compare *incremental* independent OOS precision, calibration, time stability, net-of-cost return/risk, signal count, false positives, latency and compute. No efficacy claim without valid OOS results.
- Fail CLOSED for unknown rights, missing history, lookahead, unstable edges, insufficient OOS, no value-add or high runtime.

## Operational safety
- No running library or installing GitHub agent skill. No cloud submission of user data, private Sheets read/write, no external secrets, API calls, paid services or brokerage.
- No modification of `personal-swing/engine.py`, `daily_job.py`, `tracker.py`, watchlist 477, research_sources_v1.json (49 current sources), current GitHub EOD cron, 15-session records, R92/C4.17 or ChatGPT automations.
- Cannot generate AL, WATCH, critical event, R92, device notification, trade, stop/target update or an automated veto.
- CVLT/LOGI dated records and original stop/target levels remain immutable.
- This is a **review spec only**, not integration, test result or backtest. Promotion would require a separate explicit approval, independently reviewed license/rights, pinned dependency and isolated acceptance evidence.
