# XRAY NASDAQ A40 — Official P0 source / receipt admission

This is a **read-only, no-network, no-secrets** GitHub Actions acceptance contract for
the existing NASDAQ PERSONAL research code. Not a provider permission grant,
broker, order engine, new signal, vendor integration, or claim of realized alpha.

## Scope and priority

| Risk order | Existing source contract | Offline regression |
| --- | --- | --- |
| P0 Alpaca corporate-action source / declared RAW basis | `official_provider_raw_once.py`, `official_477_shadow.py` | `test_official_provider_raw_once`, `test_official_477_shadow` |
| P0 Nasdaq Trader directory and halt snapshots | `official_event_risk_shadow.py`, `official_source_evidence_gate.py` | `test_official_event_risk_shadow`, `test_official_source_evidence_gate` |
| P0 SEC EDGAR CIK/filing reported timestamps | Same official source reader and capture gate | Same two source-regression modules |
| P0 477-row completed EOD and private readback integrity | `official_eod_shadow_receipt.py` | `test_official_eod_shadow_receipt`, `test_a40_official_receipt_contract` |
| P1 point-in-time / walk-forward controls | `qlib_pit_readiness_shadow.py`, `a37_anchored_walkforward_shadow.py` | `test_qlib_pit_readiness_shadow`, `test_a37_anchored_walkforward_shadow` |
| P1 commit / Actions proof | Exact commit HEAD and SHA-pinned workflow actions | GitHub branch protection / CI + diff review |

## Reproducible red/green: A40

- Legacy EOD receipt check **accepted** matched but malformed `asof_et` values,
  despite matching hashes. It also accepted symbols containing punctuation like
  `SYM000!` when both 477-row arrays agreed.
- GitHub Actions baseline RED recorded **11 failing negative subtests** in
  the six-case A40 test module; unchanged baseline passed existing EOD tests.
- Repair: enforce **canonical real calendar YYYY-MM-DD date** and the same
  **A-Z then A-Z/0-9/period, max 15** research ticker grammar used by other
  official source modules. A correctly represented dotted symbol remains valid.
- Negative test suite rejects unapproved source promotion and keeps private
  rows, credentials, Sheets, notifications and broker operations out of logs.
- Passing only means internal shape and time-claim consistency; hashes are not
  independent upstream-origin proof and cannot prove true historical PIT.

## Security and acceptance

- Workflow is triggered **only** by changes to listed source/test/docs paths,
  on PRs or protected-main pushes; no cron or workflow_dispatch.
- GitHub job permission `contents: read`; pinned checkout/setup-python;
  credential persistence disabled; Python standard-library tests only.
- Run both ordinary Python and Python `-O` to prevent `assert` shortcuts.
- Any failing test blocks this isolated P0 research acceptance.
- The existing protected main 477 EOD algorithm, 15-XNAS-session episode
  tracking, live provider connector, watchlist, Google Sheets, AL/IZLE/ELE,
  stop/target, vendor rights and CRYPTO remain unchanged.

## Separate, unproven gates

Actual Alpaca feed rights and coverage, historical XNAS membership and halts,
SEC public first-known timestamps, `>=500` real sessions, out-of-sample
performance and executable fills are **NOT VERIFIED** by this workflow.
A separate source owner/rights decision and real-data PIT audit are mandatory
before live-source promotion. HOLD if unavailable.

## Revert

If this gate causes regressions after merge, open a revert PR targeting only
the A40 merge and re-run both existing and new tests; never reset protected
main or silently weaken 477/PIT checks.
