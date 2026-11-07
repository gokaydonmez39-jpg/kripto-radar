# XRAY NASDAQ — Historical lifecycle-aware research gate (7 Nov 2026)

Scope: additive read-only research gate; never alters the fixed personal 477 Alpaca IEX scan, AL/STOP/2R, alerts, Sheets, broker, canonical or crypto.

## Verified sample: Alpaca IEX 1Day, 2024-09-03 through 2026-11-06
Chat-session read-only checks (NOT written as proprietary bars to GitHub):
- AAPL: 548 unique XNAS daily bars, 0 missing calendar sessions, 0 OHLC geometry violations
- MU: 548 unique XNAS daily bars, 0 missing calendar sessions, 0 OHLC geometry violations
- NBIS: 514 unique XNAS daily bars, 0 missing calendar sessions, 0 OHLC geometry violations
- CRWV: 406 unique XNAS daily bars, 0 missing calendar sessions, 0 OHLC geometry violations

The exchange calendar was also retrieved from Alpaca, so this is NOT a fully independent market-data source audit. First-known-at / revision PIT, issuer history, legal provider rights and survivorship are not proven.

## Corrective policy
Demanding exactly 500 bars for ALL 477 currently listed symbols is structurally invalid: recent listings such as CRWV cannot have 500 valid pre-listing observations. Never synthesize, forward-fill or invent bars before eligibility.

The date-shape audit retains all 477 symbols, classifying each as UNKNOWN_HISTORY, INSUFFICIENT_HISTORY, STALE_HISTORY_HOLD, GAPPED_HISTORY_HOLD, or DATE_SHAPE_500_PASS_ONLY.

DATE_SHAPE_500_PASS_ONLY is NOT actual PIT admission, model training authority, OOS alpha, source-rights proof or production PASS. Require independent history, original point-in-time membership, adjusted/raw and corporate actions, 15-XNAS-session purge/embargo, 3+ OOS folds, fees/slippage and baselines.

## How to run the synthetic checks
python -m unittest -q test_candidate_symbol_history_gate
python -O -m unittest -q test_candidate_symbol_history_gate

No new cron, model import, provider call, paid service or private Sheet change. Rollback: close draft PR #403 before merging.
