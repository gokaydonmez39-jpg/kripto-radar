# XRAY Research Source Lab - Operational Runbook (2026-10-25)

**STRICTLY RESEARCH-ONLY; this is NOT the 477-share live AL/FINAL engine.**

## Implemented and executable

- unified_research_88.json: 88 source records with explicit denial flags. Sources are NOT automatically integrated.
- research_runner.py --mode catalogue: 88-source registry schema, deduplication and permission audit.
- research_runner.py --mode pair --input /PRIVATE/bar-comparison.json: local, authorized two-provider PIT OHLCV QA, diagnostic only. Never commit real/private bars.
- research_runner.py --mode github-watch: GET-only public GitHub metadata for 22 research code repositories (existence, archive, push timestamp, default branch). No external package execution or vendor market API calls.
- The dedicated research-only Actions workflow runs normal and optimized Python offline tests on PRs. Weekly Sunday 05:41 UTC on main plus manual dispatch performs bounded GitHub metadata polling only. Cron execution may be delayed.
- Chat-session read-only Massive and Alpaca IEX API calls already returned real dated daily bars for two historical equities. No raw data were copied to public GitHub; connected-chat access does NOT authorize the GitHub runner to fetch these providers unattended.

## Data providers and verified gating facts

1. Massive / Polygon.io: https://massive.com -- former Polygon.io renamed 2025-10-30. Free Basic has 2 years of history and 5 requests per minute; connected chat read-only sample VERIFIED. GitHub not authenticated for vendor access. Aggregates are a distinct tape from Alpaca IEX.
2. Alpha Vantage: https://www.alphavantage.co -- long history, daily, fundamentals, insider/news; standard free tier 25 requests/day, adjusted daily historical endpoint documented as premium. No authenticated data call.
3. StockData.org: https://www.stockdata.org -- IEX-derived US quotes, split-adjusted EOD, news. Free plan: 100 requests/day and just ONE MONTH EOD history, not sufficient for 500-session causal modeling. No authenticated data call.
4. Finage: https://finage.co.uk -- its public site says US stock prices are NOT directly exchange-sourced and can differ materially. Advertises US realtime starting at USD 999/month. No purchase or authenticated data call.

Official publisher sources: https://massive.com/pricing?product=stocks ; https://massive.com/blog/polygon-is-now-massive ; https://www.alphavantage.co/documentation/ ; https://www.alphavantage.co/support/ ; https://www.stockdata.org/pricing ; https://www.stockdata.org/documentation ; https://finage.co.uk/pricing ; https://finage.co.uk/product/stocks

## Candidate progression (never automatic production promotion)

CATALOGUED -> DOCS_VERIFIED -> READ_ONLY_CONNECTED_IN_ONE_ENV -> SOURCE_PIT_QA -> EMBARGOED_OOS_BACKTEST -> RESEARCH_REPORT_ONLY.
PRODUCTION is a separate owner decision: no candidate in this lab may write an AL, change stop/target, send ChatGPT messages, write private Sheets, call brokers or change R92/C4.17.
All external data keys, source licenses, distribution rights, timestamp proof, exchange identity, raw vs adjusted basis and corporate actions must be independently attested. The booleans in pair-input JSON do not legally verify terms.

## Work cadence

1. Every research PR: source catalogue + local synthetic regression tests in both normal and optimized Python; fail closed.
2. Weekly on main after merge: public GitHub source health of 22 code repositories, only repo metadata. Missing or rate limited source becomes UNKNOWN. No model or market data inference.
3. When lawful private data and proper license exist: isolated vendor adapter sample, point-in-time and venue comparison to read-only Alpaca IEX; log provenance privately.
4. Statistical experiments: pre-register targets/factors, minimum historical span as a heuristic 500+ verified XNAS sessions, 15-session purge/embargo for overlapping labels, rolling-origin out-of-sample, transaction costs, splits, false positives, multiple tests, regime sensitivity, alternate source cross-check. No such full OOS experiment is reported as completed.
5. Promotion remains approval-gated even after a positive result. Neither GitHub metadata freshness nor model popularity demonstrates alpha.

## Local commands

python personal-swing/research_lab/research_runner.py --mode catalogue
python -m unittest discover -v -s personal-swing/research_lab -p 'test_*.py'
python -O -m unittest discover -v -s personal-swing/research_lab -p 'test_*.py'
python personal-swing/research_lab/research_runner.py --mode pair --input /PRIVATE/bar-comparison.json

Research-only pair-input schema: XRAY_RESEARCH_BAR_PAIR_V1, ticker, asof_et, cutoff_utc, left/right each with provider, ticker, scope, basis, attested_data_rights, bars[]. Each bar requires session, open, high, low, close, volume, known_at_utc. A matched final session is required; no future bars or future-known values. IEX vs consolidated and adjusted vs raw results are labeled NOT INTERCHANGEABLE. Every report returns may_generate_al=false, may_change_stops=false, may_emit_alert=false.

Safety: no third-party auto-install, portfolio accounts, wallet/payment, order endpoints, public private-Sheets access, price ingestion without authorization, or unattended scraping. GitHub scheduled monitor is public GitHub metadata only, not full candidate or provider production validation.
