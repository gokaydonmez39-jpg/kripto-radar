# XRAY NASDAQ — Official Event Risk Shadow, offline contract v1

Scope: **SEC EDGAR → Nasdaq Trade Halts → Alpaca Corporate Actions → Nasdaq Symbol Directory**, in that precedence. FINRA ATS/OTC and FRED/ALFRED are **P2 not installed**.

This module is an **isolated, zero-vendor-calls, offline-only research adapter**, not a live feed. It accepts externally collected responses as untrusted data and reports **REVIEW ONLY**, never an `AL`, sell action, target/stop edit, cleared risk, mobile notification, trade, or Google Sheets write. Test fixtures are synthetic and are **not** evidence of current company events. The existing 477-holding research universe, thresholds, and Premium V6 remain untouched.

Source documentation checked 2026-10-31:

1. SEC `https://www.sec.gov/search-filings/edgar-application-programming-interfaces`; no API key. SEC `data.sec.gov/submissions/CIK##########.json`, columnar `filings.recent`. SEC acceptance timestamp **is not proof of the first public-availability timestamp**; present SEC ticker identity is **not point-in-time listing identity**. Future/non-UTC, malformed, duplicated filings fail/are excluded.
2. Nasdaq `https://www.nasdaqtrader.com/Trader.aspx?id=TradeHaltRSS` + `https://www.nasdaqtrader.com/Trader.aspx?id=TradeHaltCodes`. Free RSS with once-per-minute maximum polling guidance. Requires explicit symbol/date/time/reason per item. Empty feed **never** proves no halt; missing metadata fails. Do **not** automatically claim trading resumed or is safe.
3. Alpaca `https://docs.alpaca.markets/us/reference/corporateactions-1`. Endpoint `https://data.alpaca.markets/v1/corporate-actions`, `corporate_actions` list, pagination `next_page_token`; incomplete pagination fails closed. Provider explicitly warns about unpredictable creation delay. Tests **do not prove account entitlement** or full action coverage; never infer split-adjusted volume/prices.
4. Nasdaq `https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs`; `nasdaqlisted.txt` is a **current snapshot**, not a historical universe. Reject malformed header, duplicated symbols, missing creation time, and test/ETF/abnormal status as clean securities. No automatic universe modifications.

## Run the deterministic offline test suite

```sh
cd personal-swing/research_lab
python -m unittest -q test_official_event_risk_shadow
python -O -m unittest -q test_official_event_risk_shadow
python -m py_compile official_event_risk_shadow.py
python official_event_risk_shadow.py
```

**Live acceptance is separate**, and this PR does not grant it. External automated collection is intentionally absent pending read-only authorization, provider entitlement, per-provider request budgets, non-display rights, and provenance/PIT tests. For actual live integration, obtain a known source timestamp and immutable SHA for each externally collected payload, evaluate stale/unavailable/vendor 403/429 cases, then compare against unchanged 477 EOD and active GILD/LNT ledger identities. No source may override signal decision-making without separate pre-registered OOS evidence and explicit approval.

Cost model: no additional credentials, no scheduled workflow, no source API calls, no broker access; one test run piggybacks on the existing public A11 offline CI workflow. No code path permits writes or user notifications.