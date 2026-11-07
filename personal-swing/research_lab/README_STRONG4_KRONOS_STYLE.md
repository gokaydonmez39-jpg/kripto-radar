# XRAY NASDAQ GODZILLA Ω — Strong Four / Kronos-style Research Isolation

**7 November 2026. Research only. NOT deployed/merged, not a stock forecast, not a new AL source.**

## Goal and pre-registered acceptance
- Keep personal 477-symbol NASDAQ, Alpaca IEX RAW 1Day, 52 sessions for scanner,
  2-ATR STOP and 4-ATR target (2R), 15-XNAS-session tracking, NO_ORDER.
- Four independent modules with different duties: Pydantic (schema/security),
  QuantStats (periodic return metrics), VectorBT (synthetic backtest challenger),
  DuckDB (ephemeral SQL research audit).
- Four dist versions must be installed in an isolated *no network, no secrets* Docker
  runtime and run deterministic offline smoke tests. PR CI smoke PASS is not real
  PIT, alpha, or permission for production. Only **this draft PR** triggers added
  four SDK test jobs. Existing 05:41Z public-source metadata schedule stays unchanged.
- Zero new paid service, no cron, no Sheet writes, no trading, no signal promotion.
- GitHub source HEAD SHA fields are review references ONLY; package wheels and all
  transitive dependencies are not yet pinned to hashes. Audit SBOM before broader use.

## Source & licence risk
- Pydantic 2.14.3 MIT; Pydantic *AI* is separate and already has a different pilot PR.
- QuantStats 0.0.86 Apache 2.0; daily return series are NOT trade win rates.
- VectorBT 1.2.0 Apache 2.0 WITH Commons Clause: selling the software or a service
  substantially based on it is restricted. Requires legal review for distribution.
  Version 1.2.0 ecosystem needs >=3.11 Python, >=2.4.6 NumPy, pandas >=3.
- DuckDB 2.0.0 MIT. In-memory tests do not create tamper-proof evidence archives;
  persistence, backup/restore, private data at rest and concurrency not certified.

## Exact run mode
Existing GitHub Research Source Lab on PR: tests with stdlib and XNAS dependency,
then a PR-only matrix downloads fixed direct package versions as binary wheels,
installs with Docker build network disabled, runs containers with --network none,
--read-only, --cap-drop ALL, no credentials and temporary in-memory data.
PyPI transitive wheels are not hash locked; do not treat the build as a verified SBOM.
Package installation happens in GitHub PR CI only, never in the protected EOD engine.

## Common failure modes and gates
1. A wheel is unavailable or dependencies conflict => SDK_HOLD (no sdist build).
2. Docker has network or secrets => security HOLD (do not bypass).
3. QuantStats drawdown differs from stdlib cumulative equity baseline => FAIL.
4. VectorBT package/API mismatch => FAIL; no changes to STOP or targets.
5. DuckDB requests file access, external extension or remote SQL => DENY.
6. No lawful/verified 477x500 historical PIT dataset => OOS_HOLD, including new listings.
7. Successful SDK smoke => RESEARCH_SHADOW only. No production signal authority.
8. Any CI negative or permission drift => HOLD and keep PR unmerged.

## Rollback
Close draft PR; no changes to main. If separately authorized for a future merge,
revert its isolated commit in a new reviewed PR. Do not roll back/replay AL or STOP.

## Local checks (source only, no SDK install)
```sh
python -m unittest -v test_strong4_guard test_strong4_real_sdk_smoke
python -O -m unittest -v test_strong4_guard test_strong4_real_sdk_smoke
python strong4_guard.py
python strong4_guard.py --require-production # expected exit 3
```
