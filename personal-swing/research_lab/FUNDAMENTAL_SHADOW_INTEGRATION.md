# XRAY NASDAQ GODZILLA Ω — Fundamental SEC Shadow V1 (research-only)

## Contract and scope

This is **a draft, independent, fail-closed, non-authoritative financial research module**, patterned after the existing separate Kronos/Cove shadow integration. It **does not** change the 477-symbol personal-swing AL/IZLE/ELE system, the Alpaca IEX `1Day/raw` price feed, 52 official sessions, immutable 2-ATR stop / 4-ATR 2R target, 15-session lifecycle, Google Sheets, alerts, GitHub schedules, execution, money, or orders. It **does not** touch the crypto radar, the canonical `nasdaq-xray/` decision pipeline, or the three production-like flows in the shared repository.

Only an explicitly invoked, one-ticker **read-only SEC endpoint capture** exists; GitHub PR CI executes **offline synthetic tests only**, and no new cron or automation is created. No LLM or third-party research package is installed or executed in CI. Data quality HOLD is **not** a technical `ELE` result or a zero-signal claim.

## Architecture

- `fundamental_sec_capture.py`: optional/manual SEC **GET** for exactly one approved ticker/declared CIK and three endpoints: `data.sec.gov/submissions`, `data.sec.gov/api/xbrl/companyfacts`, and that accession's SEC `-index-headers.html`. Identity must be supplied by a real, authorized operator via `XRAY_SEC_USER_AGENT`; absent identity -> HOLD. A request interval of 1.25 seconds, 16-MB response cap, HTTPS domain/path allowlist, blocked redirects, no retries, 15-second request timeout. No implicit Yahoo/FMP fallback. No brokerage key, expense, or paid endpoint.
- `fundamental_shadow.py`: deterministic zero-network model; verify fixed 477 watchlist membership, exact CIK/ticker current mapping, accession/header identity, SEC SGML `<ACCEPTANCE-DATETIME>` interpreted as `America/New_York`, original filing date, per-fact accession and XBRL reporting periods, units, duplicates, all four required line items, and two comparable annual periods. Compute YoY revenue, operating cash flow, capex, net income; derive annual FCF proxy = operating cash flow - capex. This is only a **proxy**, not complete contractual funding obligations.
- `test_fundamental_shadow.py`, `test_fundamental_sec_capture.py`: positive and negative synthetic fixtures. Must pass under normal Python AND `python -O`; reject missing or disputed source evidence, unexpected networks, non-477 symbols, backdated observations, future filings, conflicts, missing ratios, unresolvable amendments and unsafe writes.
- Existing required **all-PR** `xray-477-required-ci` must include these tests. No source/live access in its job.

## Critical issuer and temporal caveats

SEC `submissions/CIK...json` `acceptanceDateTime` is not considered proof of publication time. **Documented historical clock discrepancies** exist, sometimes carrying a misleading `Z` suffix. The code ignores that value for PIT admission and requires the accession-matched SEC SGML `<ACCEPTANCE-DATETIME>` header. Even this is an **acceptance**, not independently attested first **public** availability. Offline-supplied header text, CIK mapping, observed-at timestamps and SHA values are **NOT independent SEC-origin proof**. Direct SEC source and publisher rights still require a real authorized live capture with provider receipt and separately assessed clock lineage.

**14-day disclosure visibility (v1.1):** `recent_disclosures_index_only` lists only `10-Q`, `10-Q/A`, `8-K`, `8-K/A` and `10-K/A` accession/form/filing dates already present in the same SEC submissions input. It never makes additional HTTP requests, never identifies an 8-K as an earnings report without checking Item 2.02, never asserts SEC acceptance or historical first-public availability, never filters AL, and never sends alerts. Duplicate event accession or >100 recent entries is fail-closed. This is a provisional analyst-review index, not full quarterly/8-K financial analysis. A new source observation cannot be backdated to a past market ASOF.

Current SEC ticker-CIK mapping **is not** historical point-in-time identity. Corporate-action/symbol migrations, cross-issuer mapping, subsequent revisions, amendments and late publication may invalidate historical use. Any `observed_at_utc > asof_utc` is HOLD. Amended 10-Ks after the selected filing are HOLD, never silently ignored. Annual comparable XBRL facts missing from the **same accession** are HOLD. Company-specific/non-standard XBRL concepts cannot be inferred.

This module deliberately covers **one SEC 10-K annual comparison**. 10-Q/YTD reconstruction, segment disclosure, industry-specific statements, full research thesis, bull/bear LLM, EdgarTools typed-section extraction, FinanceToolkit ratios, VectorBT, QuantStats, TradingAgents, backtests, live SEC CI capture, and persistent private memo storage are **NOT part of V1**. They are gated future adapters. Do not claim they are integrated or validated because this draft passes offline CI.

### Status semantics

| Result | Meaning |
| --- | --- |
| `OFFLINE_STRUCTURE_PASS_NOT_LIVE` | Synthetic/offline provenance and arithmetic checks passed, NO production admission |
| `HOLD` | Missing, disputed, untimely, unsupported, or unsafe data; no AL/STOP/2R changes |
| `RESEARCH_ONLY` | One-way informational sidecar with no decision authority |
| `FULL_FINAL=HOLD` | Remains unchanged for the personal 477 system |

## Manual private test (only when explicitly authorized)

Run from `personal-swing/research_lab`, after setting a real SEC-compliant contact identity **in your own environment** (never in Git):

```bash
python -m unittest -q test_fundamental_shadow test_fundamental_sec_capture
python -O -m unittest -q test_fundamental_shadow test_fundamental_sec_capture
python -m py_compile fundamental_shadow.py fundamental_sec_capture.py test_fundamental_shadow.py test_fundamental_sec_capture.py
```

Manual SEC capture uses `python fundamental_sec_capture.py --ticker ABNB --cik <verified 10-digit CIK> --current-research --watchlist ../nasdaq_watchlist_477.json --private-output <outside-git-private-file>`. The placeholders are operator inputs; **do not** make these instructions into an automatic scheduled GitHub run. A current SEC capture has `asof_utc == observed_at_utc` by construction, reflecting observation time (NOT an XNAS EOD decision time). A new download CANNOT be backdated to an old EOD. Explicit dated cutoffs are rejected before any network request with `HISTORICAL_SEC_RETRIEVAL_NOT_PIT`; a truly historical PIT claim requires separately archived, independently timestamped source evidence. Live capture with arbitrary or unverified CIK is not admission. The program refuses missing `XRAY_SEC_USER_AGENT`, out-of-scope symbols, outputs inside the repo, unverified headers and retroactive market-decision cutoffs. Private results belong outside the repository; no publication is authorized.

## Pre-registered acceptance and rollback

1. Negative tests demonstrably fail before fix and pass after, with normal/optimized Python and existing PR required CI. No changes outside `personal-swing/research_lab/` and required PR CI workflow.
2. No new permissions, secrets, schedules, workflows, outbound requests, ChatGPT tasks, messages, trading or private Sheet writes. GitHub diff must show this.
3. Before real SEC use, prove vendor response provenance, SGML accession/time cross-check, authorized identity, per-company concept coverage and exact read-only endpoint contract. Test 403/429, changed XBRL taxonomy, missing 10-K/A and inconsistent records.
4. ABNB pilot: verify company identity using SEC and original issuer lineage, obtain at least two comparable annual periods; only verified fact claims may be interpreted, all historical outcomes remain PIT HOLD absent first-public evidence. Manual network operation is not part of this PR acceptance.
5. No production merge while shared-`main` required-CI protection P1 remains open without separate manual review of independent CI evidence and source correctness. Rollback: close draft PR without merging, or revert only its isolated commit after authorized merge. Never force-push `main`.

## Primary sources

- SEC API: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC fair-access guidance: https://www.sec.gov/about/webmaster-frequently-asked-questions
- EdgarTools (future optional typed-section reader; **not installed**): https://github.com/dgunning/edgartools
- Timestamp ambiguity investigation: https://github.com/dgunning/edgartools/issues/1501

All rights and historical PIT claims require separate admission. No profit forecast, buy recommendation, real fill, or observed investment return is asserted.
