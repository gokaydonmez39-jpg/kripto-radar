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
