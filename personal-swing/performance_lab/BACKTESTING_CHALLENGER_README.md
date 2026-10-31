# XRAY NASDAQ A35 - Backtesting.py isolated execution-model challenger

**Decision:** research-only, optional dependency, no integration into AL/IZLE/ELE,
production EOD, lifecycle, Sheets, outbox, broker or the separate XRAY CRYPTO system.
A35 only receives caller-provided validated evidence. No private input goes to
GitHub Actions or public artifacts. The CI tests use exclusively FAKE synthetic OHLCV.

## Scope / version / licensing

- Backtesting.py `0.6.6`, `AGPL-3.0`. Review AGPL obligations before external
  software distribution/network deployment. No upstream source vendored.
- No additional dependency in the production `personal-swing/requirements.txt`.
- CI: PR path-filtered, manual trigger possible; **no schedule, secrets, write scope,
  internet access from executable comparison code, notifications or orders**.
  CI's `pip install` fetches public Python dependencies only.
- Library model: individual long research episode, one hypothetical share.
  **Not a 477-symbol cash-constrained portfolio**, real fill, Sharpe, alpha,
  live performance or investment advice.

## Evidence contract

`compare_episode(witness)` accepts exactly `episode`, `previous_bar`, `signal_bar`.
The episode conforms to unchanged `nasdaq_performance_guard.evaluate_episode`:
immutable `ASOF|SYMBOL`, stop, target, policy/source SHA, completed XNAS days,
15-session cap, next-open gap rule and OHLC integrity. Prior and signal bars must
be authentic licensed input supplied privately by a separately reviewed caller;
their XNAS dates and exact signal close are validated. Both are needed because
Backtesting.py runs strategy logic after the preceding bar and places a market
order for the NEXT bar open. Synthetic fixtures in CI are never real price data.

At zero cost, stable closed stop/target episodes are cross-checked against the
existing authoritative A11 next-open witness. Comparison checks **entry date,
exit date, entry/exit prices and net percentage return**. No minimum tolerance
is loosened post hoc. A mismatch is a HOLD, not an auto-fix. Source results are
never overridden. Input mutation and unauthorized sources are rejected.

**Always HOLD**: invalidated next-open gap (no fill), still-open right-censored
episode, 15th-session close exit (the two engines have different close timing),
and same-day stop+target ambiguity. Post-entry gaps can be compared; divergence
remains HOLD rather than assuming either model represents an executable trade.

`cost_stress(witness)` separately runs Backtesting.py with nominal 0, 15 and
40 bps per side, no extra spread. This is a *hypothetical sensitivity test*;
Backtesting.py's commission accounting is **not** identical to A11's
entry/exit-price friction formula. Neither is a measured NBBO spread or fill.

## Offline tests

```sh
python -m pip install 'backtesting==0.6.6' 'exchange_calendars>=4.7,<5'
cd personal-swing/performance_lab
python -m unittest -v test_backtesting_challenger
python -O -m unittest -v test_backtesting_challenger
```

The test suite covers exact parity, falsification, immutable price policy,
source SHA, future/missing bars, chronological validation, same-bar ambiguity,
expired vs censored episodes, entry invalidation, cost sensitivity and
no-private-data/side-effect contract. Do not promote from synthetic tests to
any claim of historical or prospective alpha. A separate, licensed PIT and
survivorship-complete dataset, control, pre-registered OOS, gap/slippage and
capacity tests are required before human scientific assessment.

**Status until these gates:** `HOLD_HUMAN_SCIENTIFIC_REVIEW`.
