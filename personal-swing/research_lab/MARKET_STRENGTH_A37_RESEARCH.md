# XRAY PERSONAL NASDAQ A37 — Independent Market Breadth + Relative Return Shadow
Date: 2026-10-29. Status: **OFFLINE_ENGINEERING_PASS / REAL_477_HISTORY_NOT_VALIDATED / PRODUCTION_NO-GO**.

## Purpose and legal boundary
A37 is an independently implemented offline indicator, NOT an integration or copied proprietary 1–99 ranking from getmarketstrength.com. That site's Terms of Use effective 2026-10-20 prohibit scraping, bulk downloads and automated extraction. No site HTTP calls occur.

## Data contracts
- Ordered exactly 477 original personal-swing symbols; source SHA is calculated using sha256(('\n'.join(symbols)+'\n').encode()) and checked against the pinned independent canonical SHA. Never silently sort, deduplicate or substitute NASDAQ 478 or CRYPTO symbols.
- Exactly 64 consecutive completed official XNAS daily sessions for all 477 stocks AND QQQ benchmark, per source and raw/split adjustment profile. Explicit provider feed, adjustment basis and availability timestamps are mandatory.
- One selected feed IEX or SIP; no combining single-exchange volumes or closes with consolidated benchmark rows in one run. Raw/split adjustments never mix. Timestamp after official close and no later than provided cutoff. Reject missing/extra bars, duplicates, NaN, zero or nonfinite price, and look-ahead.
- SMA20 and SMA50 breadth are percentages of exactly the fixed 477 universe, not the whole NASDAQ. Above SMA means strictly greater, not equal.
- Relative return measured over 63 close-to-close intervals from 64 closes: 100*((stock_last/stock_first)/(QQQ_last/QQQ_first)-1). This is NOT a Market Strength 1–99 RS score, nor equivalent to exactly 3 calendar months.
- The caller must prove legal upstream data access, source version, pagination completeness, symbol identity and corporate actions. These are outside this offline calculator; a metadata label is not evidence of license rights.

## Test commands
python -m pip install -r personal-swing/requirements.txt
cd personal-swing/research_lab
python -m unittest -q test_market_strength_a37
python -O -m unittest -q test_market_strength_a37
29 positive/negative synthetic fixtures per mode. Green CI proves only offline fixture engineering, never current real 477 history or strategy alpha.

## Production isolation and later acceptance
- This change adds four isolated research-only files and one manual/PR-only CI workflow. No scheduled live fetch, no price download, no secret, no Sheet read/write, no trade, no notification and no new recurring ChatGPT automation.
- The existing 477 AL rules, 52-session IEX EOD motor, stop/target invariants, 15 official-session lifecycle, Premium V6 and CRYPTO system are UNCHANGED.
- For authorized 477+QQQ x 64 real research, a separate adapter must handle bounded pagination, rate limits, exact XNAS dates, source / adjustment attestations and corporate actions. Real 64-session collection has NOT been run for the full universe.
- Before predictive claims: minimum roughly 500 PIT XNAS sessions where available, rolling-origin walk-forward OOS, 15-session purge/embargo, realistic spread/fees/gap, regime/survivorship diagnostics and paired comparison with unchanged baseline. No alpha improvement claimed.
- No future production integration without explicit authorization and verified source/license rights.

Output permission booleans all FALSE: may_generate_al, may_change_stops, may_write_sheets, may_emit_alert, may_trade. No automatic Market Strength website calls.

## Connected-source 477+QQQ pilot — 29 October 2026 (research only)
* Official 64 XNAS sessions: 2026-07-30 through 2026-10-28, excluding the unfinished 29 October candle.
* Connected authorized Alpaca daily IEX read-only tool was queried in 48 batches (47 × 10 stocks + 1 × 7 stocks), with QQQ separately. All 477 + QQQ contained all 64 official dates; no missing official dates or nonpositive/nonfinite CLOSE observed in these queries. The source also returned historical windows beyond the required 64 sessions.
* Observed universe breadth on the fixed contemporary watchlist: close > SMA20 = **282/477 = 59.119497%**; close > SMA50 = **219/477 = 45.91195%**; 63-session stock/QQQ relative-return > 0 = **165/477 = 34.591195%**. QQQ 63-session return approximately **6.14248%**. These three categories overlap; do not add their counts.
* An aggregate-only structured evidence receipt lives at `a37_connected_iex_20261028_receipt.json`. Audited by `a37_source_receipt.py` and 20 metadata falsification tests. It does NOT contain private raw bars and cannot cryptographically attest vendor correctness, historical point-in-time availability, corporate actions, or licensing rights. See its explicit FALSE fields.
* This closes the **data-access and date-completeness** question only. Historical pricing/benchmark quality, authorized long-history collection, older universe membership and >=500-session OOS backtest are still not validated. The read-only source is single-exchange IEX and does not represent entire market volume.
* The evidence receipt is a snapshot, not a replacement for a reproducible licensed vendor collector. Keep PR a draft and do not merge it into production decision-making.

## 2026-10-29 critical correction — raw split contamination
**Proven root cause:** Alpaca corporate-action announcements include MNST ex-date 2026-08-11 and IESC ex-date 2026-08-24, both 2:1. The connected IEX daily bar tool shows large corresponding unadjusted price discontinuities, e.g. MNST 91.41 -> 45.54 on 2026-08-10/11 and IESC 685.44 -> 324.02 on 2026-08-21/24. A raw 63-interval return on either affected stock is not a reliable economic return, even though the 64 session count passed. The tool does not expose an explicit adjustment parameter. A37 now **fails closed** on raw 64-session calculations spanning these known ex-dates, rather than emitting falsely clean rankings.
**Research receipt:** The earlier three aggregate counts remain a diagnostic result from unadjusted observations, NOT a corporate-action-cleared market indicator. No guarantee is claimed that only these two corporate actions exist, because mergers, name changes, dividends and API coverage require separate verified PIT datasets. An illustrative pre-ex-date /2 correction is NOT a licensed/provider-attested split-adjusted feed.
**Source-of-truth constraint:** To certify full 477 universe or long-window returns, ingest explicitly adjusted historical OHLCV with source adjustment parameter and provenance, and independent CA/issuer identity/cusip cross-checks for each date. Real historical watchlist membership and PIT-known time must be proven, not inferred from the current 477 list. No production release is permitted.

## A37 final scientific four-gate acceptance attempt — 29 Oct 2026
- TWO-VENDOR SPLIT SAMPLE: Alpaca corporate actions (MNST 2026-08-11 2:1; IESC 2026-08-24 2:1) were independently compared with Massive explicitly split-adjusted historic closes. Before ex date: MNST Alpaca IEX 91.41 vs Massive adjusted 45.715; IESC IEX 685.44 vs Massive adjusted 342.52. Source-dependent post-ex small price differences remain; this does not certify all 477 CAs or all available-at-asof timestamps. Alpaca data API itself does not guarantee CA creation timestamps; pagination remains mandatory.
- HISTORICAL TICKER REFERENCE SAMPLE: Massive reference with date=2024-10-29 returns MNST/IESC NASDAQ identity at that date. A dated query is not proof of the original disclosure/record availability timestamp and cannot reconstruct dynamic original 477-watchlist selection or delisted historical non-survivors.
- 500+ SAMPLE ACCESS: Massive adjusted=true returned 501 daily bars for sample securities QQQ, ADI, MNST (2024-10-29 to 2026-10-28). Requesting earlier start did not yield pre-2024-10-29 rows; later provider calls hit plan RATE_LIMIT. This is sample access, not complete, bounded, persistent 477+QQQ licensed full-history PIT data. Cannot derive 500+ independent OOS episodes from 501 daily bars; 52-session warmup, 15-session future exits and preregistration further reduce usable holdouts.
- COST AND GAP: Existing private performance lab handles 15 bps each leg as explicitly hypothetical, conservative stop-first same-bar ambiguity and right censoring. No actual exchange execution/fills/NBBO from these pilot calls. Avoid public GitHub storing private candidate episodes/prices.
- New external contract `a37_external_release_gate.py` + 21 deterministic negative fixtures. Four independent evidence gates remain BLOCKED in research, with explicit non-promotion. Every "pass" supplied as a naked boolean is rejected. A green GitHub workflow means ENGINEERING regression only, never empirical trading advantage or production authority.
- Source doctrine: Historical bar adjustments are source-specific. Alpaca stockbars API explicitly supports adjustment=raw|split|dividend|all, but the connected Alpaca tool does NOT expose that argument; Massive aggregates adjusted=true is provider's split adjustment, not dividend-total-return. These must NOT be silently mixed into one feed or declared PIT.
- User-approved production personal 477, 52-session IEX AL rules, original stop/2R, 15-session lifecycle, Premium V6 :57 notification task, private Sheets and CRYPTO remain unchanged. A37 draft PR intentionally unmerged.
