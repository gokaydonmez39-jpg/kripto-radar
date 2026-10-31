# XRAY NASDAQ A37 — Anchored Walk-Forward / PIT Structural Admission

## Frozen scope and decision

**Research-only, isolated, synthetic structural guard.** A37 adds no signal,
new technical indicator, model prediction, position sizing, order, broker,
private Google Sheets read/write, market feed, scheduled workflow, email or
notification. The unchanged 477 XNAS Alpaca IEX EOD policy, AL/IZLE/ELE,
2-ATR stop / 4-ATR target, and 15-XNAS-session tracking remain authoritative.
XRAY CRYPTO GODZILLA Ω is a separate repository and is not touched.

Methodological inputs:
- https://github.com/microsoft/qlib (MIT): point-in-time research discipline.
- https://github.com/agiprolabs/claude-trading-skills/tree/main/skills/walk-forward-validation (MIT): rolling/expanding walk-forward, label purging, OOS validation.
- Existing `personal-swing/research_lab/qlib_pit_readiness_shadow.py` is imported unchanged; no Qlib or third-party skill package is installed or executed.

This guard **does not** demonstrate profitable alpha, real point-in-time market
provenance, independent issuer lineage, legal data rights, XNAS calendar
correctness, real spreads/fills or live investment suitability. Source claims
in inputs are checked for consistency, never independently vouched for.

## Pre-registered synthetic acceptance thresholds

1. Strictly >=500 anchored training observations, >=3 complete consecutive
   non-overlapping holdout folds, each >=31 observations; default 620 synthetic
   rows = 500 initial + 3x40 held-out synthetic records.
2. `label_end_index < train_cutoff_index` for every admitted training row;
   15-session nominal label purge (the synthetic fixture uses calendar days,
   so it is **not** proof of actual XNAS sessions).
3. Per-fold scaler fits solely on *purged training rows*. A future holdout
   outlier must not change the prior fold fit; after its 15-row label matures
   it may change the next fold fit.
4. Identical single-issuer metadata, RAW IEX source declarations and temporal
   decision-cutoff alignment. No missing/extra tail rows silently dropped.
5. Reject corrupted rights, duplicate/nonchronological inputs, wrong horizon,
   future feature timestamps, multi-issuer contamination, nonfinite data,
   shortened folds, and caller attempts to relax frozen constraints.
6. Identical deterministic result under standard and `python -O` execution;
   no signal, order, account action, vendor access or private artifacts.

**Validation input is completely synthetic.** All counts are structural, not
observed NASDAQ trading sessions or a backtest. Scaler SHA witnesses are for
internal change detection, not an evidence of market outcomes.

## Command (no dependency install)

```sh
cd personal-swing/research_lab
python -m unittest -v test_qlib_pit_readiness_shadow test_a37_anchored_walkforward_shadow
python -O -m unittest -v test_qlib_pit_readiness_shadow test_a37_anchored_walkforward_shadow
python a37_anchored_walkforward_shadow.py
```

PR+push path-filtered Actions use `contents: read`, pinned first-party
checkout/setup-python, no secret environment, no new cron/dispatch and no
persisted credentials. GitHub runner usage is subject to account quotas;
no separate paid API/service is introduced.

## Initial adversarial test correction

A first locally executed draft failed 2/13 tests because *the test fixture*
wrongly treated row 535 as matured by train index 540 (label ends at 550),
and used 619 rows, violating the three-fold minimum before the expected tail
gate. Corrected test inputs to row 520 (label ends at 535) and 659 rows
(incomplete last window), respectively. Subsequently all 13/13 standard and
13/13 optimized tests passed. The imported baseline file was independently
byte-matched to the source Git blob SHA `68712265737e1a322fc1a7253fc20e55afc29e46`.

## Release status and rollback

Only four new research files may be added in this PR. A failed CI job or changed
source scope is **HOLD**. Rollback = close the draft PR before merge, or revert
its single merge commit only with separate user authorization. Main is not
automatically changed. No further external app connections are authorized.
