# XRAY NASDAQ A36 — WHALE FLOW research-only protocol

## Scope
Independent scientific analysis under personal-swing/research_lab only. Not a live flow engine, not an AL gate, not a notification source. No crypto, main EOD, strategy, lifecycle, Sheets, Premium V5, :57 automation, broker or orders are changed. No network activity or vendor credentials are used by A36 code. Do not commit private price or trade data to public GitHub.

## Exact mechanisms
1. EOD daily price-volume proxy: independently validate Alpaca RAW 52 contiguous official XNAS sessions and cutoff at least 45 minutes after last close. Calculate RVOL20, prior 20-volume percentile, price return, close location in daily candle, approximate share turnover. Candidate research tags: EOD_UP_VOLUME_PROXY, EOD_DOWN_VOLUME_PROXY, EOD_MIXED_OR_UNINFORMATIVE, ZERO_RANGE_UNKNOWN. These do NOT reveal real buyers, sellers or large-party identity. 1.30 RVOL and absolute 0.50 close-location bands are unvalidated pilot hypotheses, not production parameters.
2. Tick-level research: up to five minutes of externally provided trades and quotes; match latest quote with timestamp no later than trade. Quotes older than one second, invalid/crossed/wide bid/ask greater than 1 percent, odd-lot or unrecognized trade conditions, midpoint ties and missing quotes give UNKNOWN. Quote-mid trade aggressor is merely inferred. Completeness/page-token evidence is explicitly NOT_ATTESTED, even when caller says it is. It never claims true whale identity.
3. Offline cohort: exact 477 distinct source symbols with ordered scope SHA256, one full valid 52-session IEX EOD sample each, common ASOF. Source rights and live collection remain NOT_ATTESTED even on offline PASS.

## Controlled data collection pilot (not scheduled)
A bounded historical Alpaca REST data-only collector is available as flow_capture_a36.py. It GETs only 1–5 exact symbols from https://data.alpaca.markets/v2/stocks/{symbol}/trades or /quotes for a maximum of 60 seconds per sample, at least 20 minutes after the sample ends. It verifies every response page token, rejects duplicates/missing fields and imposes a 10-page/10,000-record cap per endpoint (at most 100 GETs in the full five-symbol pilot). It never persists raw ticks; it prints only aggregated quality numbers, never symbols, quotes, credentials, private journal or whale claims. No GitHub runner credentials, cron, automatic full 477 capture or phone message are added. Source response pagination completion does not prove consolidated trade/quote tape completeness.

Local authorized data-only credentials: XRAY_ALPACA_DATA_KEY_ID and XRAY_ALPACA_DATA_SECRET_KEY. DO NOT put their values on the command line or in repository files.

Manual historical IEX example:
python personal-swing/research_lab/flow_capture_a36.py --symbols ADI --feed IEX --start-utc 2026-10-28T14:00:00Z --end-utc 2026-10-28T14:01:00Z

All source rights, time-in-force conditions, corrections, quota, billing, long-term private storage and 477-symbol feasibility still require separate verification. Success is a BOUNDED_SAMPLE_ONLY status, not full automated flow data collection.

## Input / run commands
Run only against private local JSON files, never public CI log data.

python personal-swing/research_lab/flow_shadow_a36.py --mode eod --input /PRIVATE/eod.json
python personal-swing/research_lab/flow_shadow_a36.py --mode ticks --input /PRIVATE/ticks.json
python personal-swing/research_lab/flow_shadow_a36.py --mode cohort --input /PRIVATE/cohort.json

EOD input: schema XRAY_NASDAQ_A36_EOD_RESEARCH_INPUT_V1; symbol, provider ALPACA, feed IEX or SIP, basis RAW, asof_et YYYY-MM-DD, cutoff_utc UTC timestamp, bars array with exactly 52 entries of session YYYY-MM-DD and open/high/low/close/volume finite positive numbers.

Tick input: schema XRAY_NASDAQ_A36_TICK_RESEARCH_INPUT_V1; symbol, provider ALPACA, feed IEX or SIP, basis RAW, window_start_utc, window_end_utc, cutoff_utc, trades and quotes arrays. Trade keys timestamp, exchange, id, price, size, conditions. Quote keys timestamp, bid_price, ask_price.

Cohort input: schema XRAY_NASDAQ_A36_COHORT_RESEARCH_INPUT_V1, watchlist array exactly 477, expected_scope_sha256 64-character lower-hex, snapshots array of exactly 477 EOD input objects.

All inputs must be held privately with source/data license and PIT documentation separate from this code. No GitHub Actions runner is presently authorized or proven to collect 477-symbol tick data unattended.

## Evidence and confounders
A connected Alpaca data-only sample of ADI on 28 October 2026, 09:30–09:31 ET returned 19 IEX trades and 26 IEX quotes. A manual pilot heuristic (one-second quote age, max 1% spread, only standard condition) yielded one inferred seller trade, zero inferred buyer trades and 18 UNKNOWN. This is NOT proof of trade direction, full page capture, operational ability at 477 symbols, or positive alpha. A sampled SIP trade response was available for the same historical open, but direct exchange and consolidated tapes differ.

## Failure and promotion gates
1. Independently establish trade/quote pagination completeness, late trades/corrections, exchange codes, trade conditions, coherent NBBO (IEX quote is not national BBO), identity/corporate-actions, timestamp and RTH status.
2. Verify data-entitlement, licensing, retention, source scope, quota, storage/transfer costs. Run bounded read-only pilots of 5–10 symbols before scaling. UNKNOWN is not SELL or NO SIGNAL.
3. Preregister endpoints, labels and baselines; freeze source and policy SHA. Run gap/slippage-aware walk-forward OOS with purged/embargoed 15-session overlapping observations, missing-data accounting, sensitivity tests and multiple-testing correction. Compare against existing IEX AL without modifying it.
4. Only after separate owner approval and passing independent out-of-sample quality and risk acceptance can any new production module or explanatory Premium V5 field be considered. Never auto-promote or rewrite historical AL/stop/target.

## Offline verification
python -m unittest discover -q -s personal-swing/research_lab -p 'test_*.py'
python -O -m unittest discover -q -s personal-swing/research_lab -p 'test_*.py'

Documentation: https://docs.alpaca.markets/us/reference/stocktrades-1 ; https://docs.alpaca.markets/us/reference/stockquotes-1 ; https://docs.alpaca.markets/us/docs/market-data-faq
