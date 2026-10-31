# Qlib candidate — XRAY NASDAQ offline admission contract (2026-10-31)

**Only Qlib-inspired ideas; Qlib package not imported or run.**
Reference: https://github.com/microsoft/qlib ; official Qlib data docs
https://qlib.readthedocs.io/en/latest/component/data.html .
Do NOT use Qlib/Yahoo examples as automatically acceptable PIT-aligned evidence.

## Acceptance, fixed before observing output
- Fail 52-session historical samples; minimum policy heuristic 500 XNAS-verified
  sessions (statistical sufficiency also depends on independent labels/trades).
- Fail first-seen after decision cutoff, missing first-seen, missing issuer identity,
  incomplete rows, wrong IEX/RAW basis, missing rights attestation.
- Purge a 15-session label horizon across train/test boundary; fit preprocessing
  ONLY on train; test-period outliers must not change train statistics.
- Reject NaN/Inf/bool numeric, duplicate or reordered sessions, zero-variance
  scaler. Tests run both Python normal and -O in existing research CI.
- **Never** promote AL, stops, targets, Sheets, orders, notifications, crypto.

## Status / structural limitation
The added synthetic fixture contains 520 **calendar days**, NOT proven XNAS
sessions. Synthetic source fields are inventions and cannot prove a real
provider's first-seen timestamp, exchange/issuer lineage, or redistribution
rights. Self-attested rights flags are inputs, NOT legal permission. The
scanner's 52-session live window is NOT 500-session research validation.

The 500-history threshold is a research gate, not a requirement for the
existing 52-session production scanner; no production rules change.
Source rights, chronological first-seen, historical 477 constituents,
corporate actions, event maturity, benchmark, slippage/fees and independent
OOS result all remain **NO-GO for real model admission**. Any claim of
"Qlib outperformance" requires an independent rights-cleared historical
dataset and preregistered OOS tests.

## Rollback
Close draft PR / delete research branch. No workflow or production dependency
has been introduced. This script does not run from daily EOD, cron or broker.
