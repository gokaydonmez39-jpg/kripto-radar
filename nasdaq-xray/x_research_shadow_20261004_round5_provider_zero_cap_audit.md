# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 5 Provider Zero-Cap Audit

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
G9_AUTHORITY_CHANGE=NO
ACCOUNT_AUTHORITY_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## New hard user requirement audited
PERMANENT_ZERO_COST = required
NO_USAGE_LIMITS = required where claimed as a core provider
NO_HIDDEN_FUNDING_OR_SUBSCRIPTION_CONDITION = required
UNATTENDED_AUTOMATION = required for canonical scheduler binding
CONFIGURED_PROVIDER != ACTUAL_PROVIDER
CHATGPT_CONNECTOR_ACCESS != SCHEDULER_API_ACCESS

## Provider: Bigdata.com
Official pricing: https://bigdata.com/pricing
Official terms: https://bigdata.com/terms-and-conditions
Finding:
- Starter is $0/month but only includes one-time $10 credits.
- Consumption is token-metered; Pro/Max are paid; API/MCP are listed with paid Pro and above on current pricing.
- Terms explicitly describe token consumption, paid credits/subscriptions, and restrictions on caching underlying Bigdata content.
Decision:
CORE_ZERO_CAP = FAIL
Existing C4.17 market-cap primary role is incompatible with the new permanent-$0/no-usage-limits requirement and needs a future replacement path. Do not remove until replacement is proven.

## Provider: Alpaca Basic
Official docs: https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api
Finding:
- Free live equities = IEX path.
- delayed/historical SIP usable but NON-G9.
- API/request/WebSocket symbol limits exist.
Decision:
CORE_UNLIMITED = FAIL
Keep only as temporary NON-G9 historical/settlement dependency until a proven zero-cap replacement exists.

## Provider: Longbridge OpenAPI
Overview: https://open.longbridge.com/docs
Quote overview: https://open.longbridge.com/docs/quote/overview
Quotes: https://open.longbridge.com/docs/quote/pull/quote
Historical candles: https://open.longbridge.com/docs/quote/pull/history-candlestick
K-line quota: https://open.longbridge.com/docs/cli/market-data/kline
Finding:
- OpenAPI activation has no additional interface fee after opening a Longbridge account.
- Basic US LV1 quotes are included.
- Quote API rate limit: <=10 calls/sec, <=5 concurrent.
- historical candlesticks <=60 requests/30 sec.
- historical K-line unique-symbol monthly quota 100–3000 depending on account tier.
- account opening/OpenAPI permission is required.
Decision:
PERMANENT_ZERO_EXTRA_INTERFACE_FEE = PARTIAL/PASS
NO_USAGE_LIMITS = FAIL
NO_ACCOUNT_CONDITION = FAIL
Cannot be the project's strict unlimited core market-data provider.
May remain narrow cross-check/account adapter if explicitly allowed and live authorization works.

## Provider: AlphaStocks
Pricing: https://alphastocks.app/pricing
Terms: https://alphastocks.app/terms
Disclaimer: https://alphastocks.app/disclaimer
Finding:
- Free plan exists and is advertised $0/forever for its consumer analysis surface.
- Terms prohibit scrape/crawl/automated-collect via bots/scripts.
- Market price data is sourced from Alpaca and may be delayed >=15m.
- Coverage is a constrained stock set, not full Nasdaq operating-common universe.
Decision:
UNATTENDED_AUTOMATION = FAIL
G9 = FAIL
CORE_DATA = FAIL
Use only interactive secondary research if needed.

## Provider: Rallies
Pricing: https://rallies.ai/pricing
Public B2B API docs: https://rallies.ai/api-docs
API reference: https://rallies.ai/api-docs/reference
Features: https://rallies.ai/features
Finding:
- consumer/platform pricing explicitly says full access free and "No subscription or usage limits."
- connected ChatGPT/MCP surface currently exposes rich market-data tools including all-US daily OHLCV and scanners.
- live probe for 2026-10-02 returned 12,601 symbols in a single all-ticker daily call.
- public B2B API docs expose 19 endpoints focused on retail behavior, AI funds, filings, financial metrics and screener; raw all-ticker OHLCV is not documented in that public B2B API surface.
- public B2B API requires X-Rallies-API-Key.
- no official evidence yet proves that consumer "no usage limits" applies identically to unattended B2B/API/MCP market-data extraction or a GitHub canonical scheduler.
Decision:
ZERO_COST_PLATFORM = STRONG
NO_USAGE_LIMITS_PLATFORM = STRONG
CANONICAL_SCHEDULER_MARKET_DATA_ACCESS = UNKNOWN
UPSTREAM_MARKET_DATA_LINEAGE/LICENSE = UNKNOWN
Therefore Rallies is a HIGH-PRIORITY candidate, not production authority.

## Rallies / Massive / Alpaca lineage experiment
Date: 2026-10-02
Symbols: AAPL, NVDA, MSFT

Rallies all-ticker tool produced:
- exact OHLC
- decimal volume
- VWAP
- transaction count n
- timestamp t

Massive grouped daily endpoint:
https://massive.com/docs/rest/stocks/aggregates/daily-market-summary
API path: /v2/aggs/grouped/locale/us/market/stocks/2026-10-02

Observed:
Rallies values match Massive grouped-daily values exactly for AAPL/NVDA/MSFT across O/H/L/C/volume/VWAP/trade-count/timestamp.

Alpaca delayed/historical SIP daily:
- O/H/L/C and transaction count matched.
- volume/VWAP differed slightly from the Rallies/Massive pair.

Interpretation:
COMMON_DATASET_OR_UPSTREAM_LINEAGE = STRONG_EVIDENCE
DIRECT_RALLIES_USES_MASSIVE = UNPROVEN
Do not infer contractual/provider lineage solely from numerical identity.

## Required replacement audit in C4.17
Current compiled policy contains dependencies on:
- Bigdata for MC primary;
- Rallies for DV20 and market-cap cross-check;
- Longbridge for DV20/identity/account/cross-check;
- AlphaStocks for some identity/MC fallback;
- Alpaca historical SIP for settlement.

Under strict permanent-$0/no-usage-limits objective:
- Bigdata: incompatible;
- Alpaca: incompatible with "no usage limits";
- Longbridge: incompatible with "no usage limits" and no-account-condition;
- AlphaStocks: incompatible with unattended automated collection;
- Rallies: only current high-potential candidate, but D/scheduler + upstream terms remain unproven.

Do NOT mutate production yet. Replacement must be additive shadow -> same-ASOF comparison -> failure injection -> explicit cutover only after exact equivalence/safety proof.

END.
