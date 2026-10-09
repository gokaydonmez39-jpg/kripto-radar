# NASDAQ SWING X-RAY — 09 October 2026 / zero-dollar provider deep sweep

Status: RESEARCH ONLY / no source migration / no change to canonical C4.17, C4.27 or AL/R92 thresholds.
Repo scope: `gokaydonmez39-jpg/kripto-radar`, `main`; reference PRICE blob `42ed4a1c1a104aff94f73793194b25746d3bea59`, 2026-10-08 ASOF, PRICE/DV30 PASS=514, hash `6e6f8bbabb4c1aaba4db18671a470151843afdc88f7d843190acaf444d7ffb17`.
Do not confuse a free app, open-source client, public website, or connected ChatGPT app with a licensed public-GitHub-Action OHLCV feed.

## Live observed connected-provider verification on 2026-10-09

- Rallies `get_ohcv_data_for_all_tickers_for_a_date(date="2026-10-08")`: **12,592** US ticker rows; 12,592 distinct ticker IDs.
- Join against **all 514** exactly PRICE pass symbols at the pinned blob: **514/514** matched, 0 missing; 514/514 passed basic finite positive OHLCV/range arithmetic; **514/514 volume fields fractional** (i.e. not unadjusted exchange-share trade-count integers). This may reflect adjustment/scaling; no such explanation verified. Do not relabel fractional volume as raw consolidated volume or official DV30.
- `get_price_from_date_range(ticker="AAPL", start_date="2025-09-01", end_date="2026-10-08",interval="day")`: **278** historical daily records, latest 2026-10-08, oldest observed 2025-09-02. A 260-session-plus-weekly backfill looks TECHNICALLY PLAUSIBLE for some symbols; no complete 514x260 check.
- Rallies `get_company_overview` AAPL, MSFT, NVDA exposed XNAS, market_cap, current_price but **no instrument-class share provenance or exact market-data observation time**. Do not call this primary same-ASOF C4.17 MC.
- Provider's consumer page says full platform free/no usage limits; its published external B2B API documentation calls it a *behavioral intelligence API*, **not a raw OHLCV API**. ChatGPT connector access does not establish GitHub Actions runner API route, allowed redistribution, non-display rights, retention, or unlimited automated calls. Production remains NO-GO.
Sources: https://rallies.ai/pricing ; https://rallies.ai/api-docs ; https://github.com/ralliesai/rallies-cli

## Newly prioritized potentially useful source: Twelve Data Basic

Official pricing https://twelvedata.com/pricing :
- Basic US equities with internal non-display usage; 8 API credits/min, **800 API credits/day**, batch requests. /time_series documented at **1 credit per requested symbol**.
- **514** symbols -> 514 credits, minimum **65 rate-limited minute buckets** at 8/min, excluding overhead, errors, or other requests. **3401** -> 3401 credits and minimum **5 daily budget allocations**; an entire 3401-symbol refresh every trading day does **not** fit one free key. Rate limits are not to be bypassed.
- Proposed /time_series?symbol=<SYMBOL>&interval=1day&outputsize=320&adjust=splits; outputsize documented 1–5000 as API parameter, but real Basic-tier 320-bar access to these symbols is **NOT tested**. 320 rather than 260 gives completed-week aggregation space; must validate official 260 daily and 52 completed weekly against canonical calendar and issuer/split history.
- Terms https://twelvedata.com/terms : 2.2 data processing/internal use and irreconstructible derived data; non-display **only as tier permits**; 2.3 caching restricted to specified periods, free commercial use forbidden; 16.1 retention conditional on subscription and third-party providers. Hence non-display pricing description is useful but **does not independently verify unattended public GitHub runner credentials, backfill/retention or publishability**.
- No Twelve API key held/used. No raw bars downloaded/stored. `nasdaq-xray/free_history_source_preflight.py` and existing GitHub workflow provide fail-closed quota/PRICE SHA regression, **not** vendor authority.

## Source inventory beyond the original small shortlist

All entries are candidates or component references, NOT certified compliant production feeders. Priority reflects next investigation, not alpha PASS.

| # | Source / project | What it can contribute | Real free / licensing / scope caveat | Priority |
| --- | --- | --- | --- | --- |
| 1 | Twelve Data | US daily OHLCV, split handling, batch | Basic 800 credits/day; internal non-display advertised; actual 320 bars/retention/runner authorization unverified | P0 test |
| 2 | Rallies connected research | Verified 12,592 rows per date and 514/514 join; historical single symbol and MC metadata | All 514 volumes fractional; public third-party OHLCV endpoint / GitHub runner grant / source provenance unknown | P0 investigate |
| 3 | FMP / Financial Modeling Prep | EOD, full and light historical price, market-cap/reference | Free 250 calls/day; full OHLCV endpoint may be limited; individual plan not redistribution; 514 one-day requests exceed 250 | P1 |
| 4 | Massive / Polygon | EOD aggregate OHLCV and reference | Free 5 req/min; explicit non-display and derived-use licensing constraints; Bigdata MC $0 replacement not established | P1 conditional |
| 5 | Alpha Vantage | Daily raw OHLCV + finance indicators | 25 free requests/day; full history and adjusted endpoint entitlements must be distinguished | P1 spot crosscheck |
| 6 | Market Data (marketdata.app) | Standard historical candles | Free 100 API credits/day; >=24h delay; one-year depth below robust 260 completed-session target | Secondary only |
| 7 | EODHD | EOD daily raw data and demo historical | Free 20 calls/day, 1-year depth; demo only handful of symbols; personal use | Secondary only |
| 8 | StockData.org | EOD, multiple tickers per request | Free 100/day, at most 3 symbols/stock request, only one month of EOD history | Not 260 |
| 9 | marketstack | EOD API | Free 100 **per month**, up to 12 months history | Not primary |
| 10 | Tiingo | Historical equities OHLCV | Starter/trial derived-data persistent storage issue in published ToS; check account's exact privileges | Legal gate |
| 11 | Alpaca historical SIP | Delayed SIP historical bars on appropriate feed | Runner keys not proven; IEX live is not consolidated SIP; terms, scope and retention unverified | Key/rights gate |
| 12 | Finnhub | Quote, reference, fundamentals | Free quote != proven licensed 260-day daily bars; historical candle endpoint tier uncertain | MC crosscheck only |
| 13 | Stooq | Historical US stocks in public interface | No independently verified automated GitHub runner/retention rights and no PIT guarantee | Research crosscheck |
| 14 | Yahoo Finance / yfinance | Batch price histories, actions and fundamentals | Unofficial API, explicitly personal-use-only; code OSS license != raw market-data license | Sandbox only |
| 15 | yahoo-finance2 | Additional historical/chart interface | Unofficial Yahoo wrapper with delisting/renaming gaps; same upstream data entitlement issue | Sandbox only |
| 16 | AKShare stock_us_daily / Eastmoney / Sina | US OHLCV alternative exposed by OSS | Scraped third-party sources; provider permission, stability and exchange provenance unproven | Sandbox only |
| 17 | FinanceDataReader / pandas-datareader | Providers including Stooq/Yahoo | Aggregator, no independent source grant | Adapter reference |
| 18 | OpenBB Platform | Provider routing / validation patterns | Open-source software aggregation does not license underlying OHLCV | Architecture only |
| 19 | Nasdaq Data Link | Certain open Nasdaq/Quandl datasets | Free datasets exist but not proven to cover current 3401 names with valid recent daily bars | Dataset check |
| 20 | NasdaqTrader Symbol Directory | Official current NASDAQ universe and ticker status | Instrument/identity, not OHLCV | Official support |
| 21 | SEC EDGAR | CIK, entity filings, float/share-vintage context, earnings/events | No daily traded price bars; shares not automatically current class-specific MC | Official support |
| 22 | OpenFIGI | FIGI and share-class/composite symbol mapping | Free public API, rate caps; identity, not OHLCV | Official support |
| 23 | FRED / ALFRED | Historical macro / point-in-time vintage regime | No equity OHLCV or class MC | Official support |
| 24 | SimFin | Historical normalized company fundamentals | Fundamental statements, not market OHLCV; free retention terms apply | Event research |
| 25 | TradingView community scripts / MCPs | Technical scanning implementation ideas | TradingView feed rights not inherited from GitHub client | Reference only |
| 26 | Databento | Institutional historical tick/aggregates | Promotional credits expire; not permanent zero-cost entitlement | Excluded |
| 27 | Cboe / Barchart OnDemand | Exchange/quote comparison and optional paid feeds | Not a proven zero-dollar consolidated Nasdaq 260-bar / G9 source | Excluded for primary |

Selected primary evidence:
- FMP https://site.financialmodelingprep.com/pricing-plans ; https://site.financialmodelingprep.com/developer/docs
- Massive https://www.massive.com/legal/market-data-terms-of-service
- AV https://www.alphavantage.co/documentation/ ; https://www.alphavantage.co/premium/
- Market Data https://www.marketdata.app/docs/account/free-accounts/
- EODHD https://eodhd.com/financial-apis/api-for-historical-data-and-volumes
- StockData.org https://www.stockdata.org/pricing
- marketstack https://marketstack.com/contact
- Tiingo https://app.tiingo.com/tos/
- Yahoo https://github.com/ranaroussi/yfinance/blob/main/README.md ; https://github.com/gadicc/yahoo-finance2
- AKShare https://github.com/akfamily/akshare/blob/main/docs/data/stock/stock.md
- NasdaqTrader https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs
- SEC https://www.sec.gov/about/developer-resources
- OpenFIGI https://www.openfigi.com/api/documentation
- FRED https://fred.stlouisfed.org/docs/api/fred/
- Rallies official Github https://github.com/ralliesai/rallies-cli

## X and Github research discipline

Indexed X profile/marketing posts establish existence and leads, **not** original data rights or full market venue coverage. The already-present repo survey `nasdaq-xray/x_research_shadow_20261004_round5_free_unlimited_audit.md` is incorporated, including its reported prior Rallies tool output and quota caveats. Do not reset that work; current direct readback supersedes dated counts.

## Next production-critical experiments (none is complete at this checkpoint)

1. Verify Twelve Basic key obtained legitimately, 320 real daily bars (AAPL, thin NASDAQ/IPO, renamed issuer), US XNAS identity, full 260/52 dates, split/volume semantics, **explicitly permitted automation and retention**, no secrets/raw data on public GitHub. Respect 8/min and 800/day. Running a quota selftest is not running this probe.
2. Determine Rallies fractional volumes' origin, exchange vs adjusted volume semantics and exact data lineage. Verify direct GitHub Actions automated API and derivative alert rights; absent such a grant Rallies remains interactive shadow.
3. FMP Basic full endpoint with a real authorized free key and independent US availability/MC; test 250/day not duplicate bills.
4. Separate same-ASOF PRIMARY MC source entitlement and class share identity from history and G9. Do not equate opaque Rallies overview market cap (untimestamped) with primary.
5. When authorized sources exist, put raw vendor data in rights-compliant private ephemeral cache, enforce immutable date/issuer/volume/corporate-action audits; only then consider canonical HISTORY/MC guard activation. Repeat canonical terminal and R92 only on independently PASS inputs.

EXECUTION=NONE; REAL_MONEY=NO-GO; UNKNOWN!=PASS; NO_G9_REQUIRED; no signal, order, balance, portfolio or user credential retrieved; no newly scheduled automations; C4.17 thresholds unchanged.
