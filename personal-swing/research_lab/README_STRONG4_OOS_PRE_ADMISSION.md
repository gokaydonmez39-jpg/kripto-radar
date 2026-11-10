# XRAY Strong4 — historical OOS admission (research only)

**Scope:** Read-only and local-only, no signal or order authority, no new source acquisition, no private Sheet access, no paid service and no new schedule.

**Protocol frozen before seeing actual strategy outcomes:** 477-symbol personal universe, IEX RAW 1Day, 2×ATR STOP / 4×ATR target, 15-session tracking. Minimum **623 consecutive XNAS sessions** = 500 usable training + 15-session purge + three disjoint 31-session OOS folds + 15-session label-maturity tail. The precommit uses the exact fixed benchmark `PIT_477_EQUAL_WEIGHT_BUY_HOLD`. Fees of **4 bps** and slippage of **5 bps** are explicitly *unverified research cost assumptions per unit of turnover*; not realistic execution quotes or a guaranteed fill model.

**Provisional statistical rubric:** At least 20 claimed ALs overall, five in each fold, positive after-cost excess return in every fold, and a positive 15-session moving-block bootstrap one-sided 95% descriptive lower bound. These values cannot prove alpha independently; folds are time-correlated and 93 OOS sessions are not large enough to claim broad regime stability. All outputs retain `real_oos_alpha_verified=false` and `production_authorized=false` even if descriptive criteria pass.

**Private intake:** An owner-supplied and lawfully obtained *aggregated daily return ledger* with `schema=XRAY_STRONG4_PRIVATE_OOS_LEDGER_V1`, contemporaneous decision-time fields, per-day decision receipts, fixed 477 cohort benchmark, and external record SHA-256 references for rights, issuer lineage and decisions. Self-asserted SHA hashes **do not attest authorship, publication time, legal entitlements, survival bias or PIT history**. The script refuses missing/duplicate/non-XNAS days, decision after following market open, future-known features, wrong universe, changed STOP, relaxed embargo and missing fees.

Real certified AL decision history is not available in this PR; the public `nasdaq-xray/personal_research_signal_digest.json` asof 2026-11-06 reports **zero certified C4.17 AL signals**. **Do not synthesize or backfill real signal claims.** The 258,795 IEX bar shape audit is not a historical decision ledger and does not establish historical corporate-action treatment or data rights. Thus `REAL_PIT=HOLD` and `REAL_OOS=HOLD` until owner-authorized independent records are supplied and reconciled.

Input file must **never** be uploaded into a public PR, workflow artifact or stdout. Only the aggregate diagnostic is printed. To run locally with private evidence:

```bash
python strong4_oos_admission.py --private-ledger /PRIVATE/research_oos_623.json
python -m unittest -q test_strong4_oos_admission
python -O -m unittest -q test_strong4_oos_admission
```

**Fail-closed acceptance:** No automatic merge, new automatic daily job, broker token, execution engine, crypto workflow, replay of historical AL, or production promotion. A real trade ledger, contemporaneous PIT/vendor receipt, corporate-action issuer map, license assessment, executed market-cost study, multiple-testing audit and owner approval are still required.