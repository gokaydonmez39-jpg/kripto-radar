# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 6 SEC PIT + MC Migration

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
G9_AUTHORITY_CHANGE=NO
ACCOUNT_AUTHORITY_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## Gem 1 — edgartools
X profile surfaced in X search: https://x.com/dwightwgunning
Repo: https://github.com/dgunning/edgartools
Docs: https://edgartools.readthedocs.io/
License: MIT
Observed capabilities:
- current/today SEC filings monitoring;
- 8-K, 10-K, 10-Q, Forms 3/4/5, 13F, ADV and XBRL parsing;
- EntityFiling carries report_date, filing_date, acceptance_datetime and accession number;
- filing headers parse SEC ACCEPTANCE-DATETIME;
- XBRL supports DEI EntityCommonStockSharesOutstanding.
Classification: LOCAL_SEC_PARSER_CANDIDATE
Authority rule: SEC remains authority; edgartools only parses/caches.
XRAY value:
- official acceptance timestamp as available_at for PIT facts;
- accession-bound event evidence;
- Form4/8-K event parser;
- share-count vintage extraction for MC replacement;
- real-time filing ingestion without paid SEC wrapper.
Guard:
- obey SEC fair-access;
- parser failure => UNKNOWN, never silent omission;
- exact form matching; amendments/restatements append as new vintage.

## Gem 2 — sec-edgar-downloader
Repo: https://github.com/jadchaar/sec-edgar-downloader
Docs: https://sec-edgar-downloader.readthedocs.io
License: MIT
Classification: BULK_FILING_INGESTION_ENGINEERING_CANDIDATE
Value: simple local filing archive/downloader from SEC EDGAR.
Guard: ingestion helper only; not an authority or event classifier by itself.

## Proposed Bigdata-free market-cap lane
SEC_OFFICIAL_FILING
  -> exact Nasdaq ticker/listing identity
  -> filing acceptance_datetime
  -> EntityCommonStockSharesOutstanding observation
  -> immutable share-count vintage
  -> reject if stale or invalidated by known split/issuance/corporate-action evidence
  -> QUALIFIED_PRICE_ASOF
  -> DERIVED_MC = shares * price
  -> threshold buffer/crosscheck
  -> PASS/FAIL/UNKNOWN

PIT invariant:
A fact can only be used if acceptance_datetime <= decision_cutoff.
Never use a later restatement/current CompanyFacts row to rewrite an older ASOF decision.

## Rallies as price/MC replacement candidate — stronger runtime evidence
Pricing: https://rallies.ai/pricing
Connected tool evidence:
- one get_ohcv_data_for_all_tickers_for_a_date(2026-10-02) call returned 12,601 rows;
- AAPL: O=333.26 H=334.54 L=330.61 C=333.69, plus volume, VWAP (vw), trade count (n) and epoch timestamp (t);
- same call included MSFT and NVDA with exact daily OHLC values matching known completed-session reference values;
- full-universe rows do NOT contain exchange or upstream-provider fields;
- get_company_overview/screener independently expose exchange=XNAS + current_price + market_cap;
- AAPL recent daily chart exposed 1,376 observations.
Classification: HIGH_PRIORITY_BROAD_DATA_REPLACEMENT_CANDIDATE
Inference guard:
The compact row schema resembles common aggregate-market-data schemas, but upstream lineage is NOT proven. Never infer Polygon/Massive/SIP from shape or matching values.

## Potential C4 migration if provenance qualifies
1. Official NasdaqTrader stays universe/identity primary.
2. SEC/IR stays issuer/share-count/event authority.
3. Rallies broad daily path may replace rate/cost-constrained daily-price/DV20 dependencies.
4. Derived SEC-share-count × qualified price may replace paid Bigdata market-cap primary.
5. Rallies reported market_cap becomes independent crosscheck, not sole authority at first.
6. Alpaca/Bigdata are removed only after same-ASOF regression + full-universe coverage tests prove replacement.
7. New compiled-policy epoch required; never edit C4.17 semantics in place.

## Validation suite before migration
- >=260 completed sessions on representative NASDAQ sample and edge cases;
- exact official-session-set equality;
- OHLC match tolerance;
- volume discrepancy characterization;
- split/dividend/corporate-action cases;
- IPO/new listing + delisted cases;
- multiple share classes;
- share-count staleness/restatement;
- same-ASOF reproducible replay;
- provider outage/empty-response fail closed;
- cost/quota entitlement proof.

END.
