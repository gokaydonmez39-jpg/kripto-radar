# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 3 PIT + Replay

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
G9_AUTHORITY_CHANGE=NO
ACCOUNT_AUTHORITY_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## Gem 1 — XFINLAB point-in-time / vintage store
Repo: https://github.com/lnanology/Xfinlab
Relevant file: https://github.com/lnanology/Xfinlab/blob/main/services/point_in_time_store.py
Observed pattern:
- store actual filing availability date separately from period_end;
- immutable vintages, restatements create new rows rather than overwrite;
- anti-look-ahead queries return only values available by ASOF;
- missing PIT history returns unknown, never a future/current fallback.
Classification: HIGH_VALUE_RESEARCH_INTEGRITY_PATTERN
XRAY adaptation:
- every SEC/XBRL fact gets period_end + filed_timestamp + available_at + source filing accession;
- use actual EDGAR accepted/filing time where available instead of an arbitrary fixed delay;
- bind to real U.S. trading calendar, not weekend-only business-day approximation;
- restatements immutable append-only;
- historical scans query ASOF-visible vintage only.
Production integration: NOT YET. Requires regression tests and source-timestamp contract.

## Gem 2 — frozen-state reproducible experimentation
Source: X/Twitter engineering Search Relevance Infrastructure.
Reference: https://blog.x.com/engineering/en_us/topics/infrastructure/2016/search-relevance-infrastructure-at-twitter
Observed pattern: freeze the state of the world for stable, reproducible offline experiments and diff outputs before deployment.
Classification: HIGH_VALUE_VALIDATION_PATTERN
XRAY adaptation:
- immutable ASOF snapshot for universe, price bars, event set, policy version and source bindings;
- replay old candidate decision from only frozen ASOF evidence;
- compare OLD_POLICY vs SHADOW_POLICY without rewriting historical outcome;
- semantic diff: candidate set added/removed/changed and exact reason.
This strengthens existing no-backfill/history integrity.

## Gem 3 — XFINLAB source/license registry
Reference: https://github.com/lnanology/Xfinlab/blob/main/DATA-LICENSE-MATRIX.md
Observed pattern:
- map endpoint -> service chain -> upstream source -> license status -> risk;
- disclose fallback source and scope gaps;
- do not treat configured provider as proof that provider actually served the request.
Classification: HIGH_VALUE_LINEAGE_COMPLIANCE_PATTERN
XRAY adaptation:
PROVIDER_INVOCATION_RECEIPT per field:
provider_requested
provider_actual
endpoint/feed
entitlement_class
source_timestamp
received_at
delay
fallback_used
fallback_reason
license_class
authority_class
No field may inherit authority from configured-but-unused provider.

## Gem 4 — X engineering anomaly detection
Reference: https://blog.x.com/engineering/en_us/a/2015/introducing-practical-and-robust-anomaly-detection-in-a-time-series
Observed pattern: seasonal/trend-aware anomaly detection; positive and negative anomalies; negative anomalies can detect data-collection/hardware faults.
Classification: GUARDIAN_ENGINE_PATTERN
XRAY adaptation:
- detect abnormal symbol-count collapse;
- zero/near-zero volume cohort anomaly;
- timestamp-lag spike;
- provider response-count cliff;
- breadth/price distribution discontinuity;
- alert-delivery failure-rate anomaly.
Guard: anomaly is a health flag, never market alpha by itself.

## Gem 5 — Ask Edgar X discovery bot
X: https://x.com/AskEdgar_App
Example: https://x.com/AskEdgar_App/status/1943764072073191741
Classification: SEC_EVENT_DISCOVERY_ONLY
Potential: PRE14A / dilution / reverse split / issuance / governance discovery.
Guard: resolve exact SEC filing and accession before event fact enters canonical evidence.

## Gem 6 — Massive docs-plan contradiction resolved
Endpoint docs can visually surface Stocks Basic next to NBBO endpoints, but detailed plan table states Quotes are NOT included in Basic/Starter/Developer and are real-time only on Advanced ($199/mo).
Authority references:
https://massive.com/pricing?product=stocks
https://www.massive.com/docs/rest/stocks/trades-quotes/quotes
Decision: existing registry classification remains correct. Massive does NOT solve permanent-$0 strict G9.

## Gem 7 — MertMetinDev curated research seed list
Profile mirror/search discovery: https://x.com/mertmetindev
Relevant finance-list post surfaced via indexed mirrors: includes Dataroma, WhaleWisdom, CapitolTrades, OpenInsider, 13f.info, SEC EDGAR, FRED, CompaniesMarketCap, Finviz, etc.
Classification: CURATED_DISCOVERY_SEED
High-value candidates for independent audit:
- https://www.sec.gov/edgar
- https://fred.stlouisfed.org
- https://openinsider.com
- https://13f.info
- https://www.dataroma.com
- https://whalewisdom.com
- https://www.capitoltrades.com
- https://companiesmarketcap.com
- https://finviz.com
Guard: only SEC/FRED can be treated as first-party authority for their domains; the rest are secondary discovery/cross-check until exact API/license/freshness contracts are proven.

END.
