# XRAY Personal NASDAQ Swing Radar — A11 Evidence Intelligence Lab

**Scope: isolated, read-only, no production import.** This is a source-backed analysis *foundation*, **not an autonomous production learning engine**. No new ChatGPT automation, GitHub schedule, Sheet writes, alerts, broker connections, stock ingestion or model calls. Files live only under `personal-swing/performance_lab/` and one PR-triggered CI workflow.

## Engineering objective and explicit success contract

1. Do not modify the 477 stock universe, deterministic `AL/IZLE/ELE`, historical stops/targets, XNAS calendar, 15-session follow-ups, one alert ledger or user-facing notifications.
2. A signal is a **research episode**, not an executed trade. A completed signal's old reference-close path and theoretical next-eligible-XNAS-open path must remain separate, accounting for *declared* round-trip entry/exit friction. The initial cost scenario is **15 bps entry + 15 bps exit**, an **ASSUMPTION**, not measured live spreads/slippage. First open at/beyond stop or target invalidates hypothetical entry rather than claiming a fill. Gap past a stop exits at IEX next open rather than stop price. Same-day stop+target within OHLC remains conservatively stop-first; no intraday route is asserted. All exit results are **hypothetical IEX EOD**, not actual realized execution.
3. Strictly validate episode identity, original stop/2R target, source and policy SHA, official XNAS session sequence, input bar correctness, and missing completed-day coverage. Fail closed if chronology/coverage cannot be proven; ongoing episodes are **right-censored**, never assigned a final win or loss.
4. Statistical monitor calculates **Bayes Beta(1,1) posterior mean for the sign of net return**, Wilson 95% win interval, **signal-day-block** bootstrap 95% mean-net-return interval, observed worst 5%-episode tail mean, gaps and OHLC path ambiguity. Observations sharing a signal day are not independent draws. This is not a Sharpe ratio or investable portfolio equity curve because real fills, overlap position sizing and cash constraints are unknown.
5. **EX-ANTE trial safeguards (provisional design limits):** 60 completed episodes and at least 20 distinct signal days just to leave *underpowered* state; >10% censored or ambiguous requires source/path review; pairwise benchmark, actual preregistered temporal holdout and source provenance required before **human** assessment. These thresholds do **not** certify statistical power, alpha, production PASS or the validity of any strategy change. Additional robust prospective power analysis is needed before a hypothesis trial.
6. Drift detector splits by signal dates with at least 40 complete episodes and 20 separate dates. Net-return deterioration >=0.50 percentage points is only **suspected drift**, not multiple-testing-adjusted significance. It raises a silent diagnostic, not a push or an AL rule change.
7. Deterministic proposal card allowlist: RVOL, RSI, ATR risk, liquidity and entry-time research. Must record original SHA and an explicit falsifier; it always returns `NO_GO`, never edits strategy code. A human must preregister and run unseen XNAS sessions, purged/walk-forward checks, licensed matched baseline, costs, survivorship, stress and multiple-comparison corrections before any PR promotion.
8. Secure storage/privacy is a separate gate: caller must export needed *private* Sheet rows and licensed Alpaca IEX OHLCV via a separately reviewed, authenticated, non-public adapter; **no candidate data or real 477-stock results may be committed, logged, uploaded to public CI, or included in prompts**. This lab currently has no such adapter. Raw `proof_hash` from local episode JSON only identifies a record; it is not cryptographically attested vendor provenance. Provenance and IP rights remain unverified.

## The five mechanisms

| Module | What is automated **after authentic input exists** | Guard |
| --- | --- | --- |
| Episode evidence witness | Input contract, SHA identity, session + pricing chronology, audit fingerprint | `EvidenceBlocked` if source or a completed day is unknown |
| Realistic cost/gap evaluator | Next-open theoretical execution sensitivity, gap and 15-XNAS-session stop-first | Never calls an executed trade or real fill |
| Bayesian and robust statistics | Win-probability estimate, uncertainty, date-block bootstrap and tail summary | Small sample and missing benchmark are HOLD |
| Silent drift / integrity watchdog | Wrong chronological coverage, entry-gap, simultaneous levels, gap loss, possible deterioration | Stable dedup keys, **no delivery** |
| Falsification challenger laboratory | Generates proposal-only hypothesis with frozen SHA and test-to-refute | All changes `NO_GO` until independently reviewed |

## Baselines and alternatives

- **Baseline A — Existing radar untouched:** costs nothing and carries no new dependency but has no independent cohort-level performance accounting.
- **Baseline B — Pure Python isolated lab (selected):** transparent deterministic calculations, one already-required `exchange_calendars` dependency, no AI model/API fees; still only a historical *hypothetical* proxy pending authentic source data.
- **Alternative C — Autonomous optimizer:** not selected. Self-adjusting thresholds on a small, overlapping sample risk leakage, multiple testing, false discovery, distribution shift and loss of reproducibility. Even a good backtest would not prove future live performance.

## Test and deployment conditions

Run offline: `python -m unittest -v test_nasdaq_performance_guard` and `python -O -m unittest -v test_nasdaq_performance_guard`, from this directory with `exchange_calendars>=4.7,<5` installed. The CI workflow runs **only when lab files/CI change**; it is **not a daily performance job**. There are no new automations or push permissions.

**Unfinished:** authenticated private data adapter, independent official XNAS close / venue cross-check, full spread/NBBO and executable fill data, licensed PIT history, adjusted corporate actions, matched buy-and-hold and regime controls, vendor security/key rotation, sample collection through 15 sessions, and prospective research/real-device audit. **Status: HOLD**, even if all synthetic tests pass. Existing daily EOD and private lifecycle remain fully owned by the original production workflow and ChatGPT notification coordinator.
