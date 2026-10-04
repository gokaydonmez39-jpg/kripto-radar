# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 5 Free+Unlimited Dependency Audit

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
G9_AUTHORITY_CHANGE=NO
ACCOUNT_AUTHORITY_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE
USER_HARD_CONSTRAINT=PERMANENT_$0_PLUS_UNLIMITED_REQUIRED

## Why this round exists
The current C4.17 research chain contains Alpaca, Bigdata, Rallies and Longbridge roles. Under the user's strengthened hard constraint, each dependency must be re-audited separately for software cost, market-data entitlement, remote API rate/quota, account/funding conditions, and automation rights.

## Bigdata.com — FAIL hard cost constraint
Pricing: https://bigdata.com/pricing
Terms: https://bigdata.com/terms-and-conditions
Current official facts:
- Starter: $0/month but only $10 one-time credits.
- Consumption is token/usage-priced.
- Pro/Max are paid; even "unrestricted content" does not remove standard search/retrieval token charges.
- Terms restrict caching/retaining underlying Bigdata Content beyond consumption unless separately licensed.
C4.17 impact:
- current mc.primary uses Bigdata exact Nasdaq-family USD MARKET_CAP.
Decision:
BIGDATA_PERMANENT_ZERO=FAIL
BIGDATA_UNLIMITED=FAIL
MIGRATION_REQUIRED_BUT_NOT_SAFE_TO_REMOVE_UNTIL_REPLACEMENT_PROVEN.

## Longbridge OpenAPI — FREE SERVICE, NOT UNLIMITED/UNCONDITIONAL
Docs: https://open.longbridge.com/docs
Quote docs: https://open.longbridge.com/docs/quote/pull/quote
Pricing/activation summary in docs:
- OpenAPI interface activation itself has no additional fee after opening an integrated account and obtaining permission.
- US LV1 quote permission can be free with OpenAPI activation.
Limits:
- max 10 quote calls/sec;
- max 5 concurrent requests;
- max 500 subscribed symbols/account;
- requires account opening + developer verification/OpenAPI permission.
ACCOUNT runtime:
- current ChatGPT-connected account_balance + stock_positions still fail 403308 scope-not-authorized.
Decision:
LONGBRIDGE_$0_SERVICE=CONDITIONAL_PASS
LONGBRIDGE_UNLIMITED=FAIL
LONGBRIDGE_UNCONDITIONAL_ACCESS=FAIL
Useful as fallback/identity/account candidate only while policy permits; incompatible with literal no-limit dependency goal.

## Alpaca — RECONFIRMED NONCONFORMING
Official docs/prior audit:
- Basic/free live US equities = IEX only;
- delayed/historical SIP may be available outside latest 15 minutes;
- API/WebSocket limits exist.
Live connected probe in this research:
- IEX latest quote works;
- delayed_sip latest quote works;
- live sip latest quote fails;
- historical SIP daily can work.
Decision:
ALPACA_PERMANENT_CORE_UNLIMITED=FAIL
STRICT_G9=FAIL
Current settlement role must remain NON-G9 and eventually be replaced if literal no-limit constraint is enforced.

## Rallies — HIGHEST-POTENTIAL FREE+WIDE RESEARCH DATA PLANE
Pricing: https://rallies.ai/pricing
Current official pricing says:
- full access free;
- no subscription or usage limits;
- includes deep research, agents, screeners and AI funds.
Platform: https://rallies.ai/
API docs: https://rallies.ai/api-docs
Open-source CLI: https://github.com/ralliesai/rallies-cli

Connected-surface live evidence:
1) get_company_overview(AAPL)
- exchange=XNAS
- current_price and market_cap returned.
2) screener include AAPL/NVDA/MSFT
- exchange=XNAS
- market_cap, current_price, volume etc.
3) full-US daily OHLCV call for 2026-10-02
- 12,601 ticker rows in one call;
- row fields: ticker/open/high/low/close/volume/vw/n/t;
- AAPL/NVDA/MSFT OHLC matched known completed-session SIP prices;
- timestamp/trade-count/VWAP available.
4) AAPL daily chart returned 1,376 data points.
This makes Rallies a very strong candidate for broad daily-history/DV20/price-universe/MC acceleration.

Open blockers:
- rows expose no upstream provider/feed/venue provenance;
- no public proof that "no usage limits" applies specifically to every connected market-data/MCP tool rather than the registered platform UI/account experience;
- older rallies-cli README says a Rallies API key provides higher rate limits, indicating historical quota semantics that may have changed;
- current public B2B API documentation says it is a behavioral-intelligence API, not a raw price/news feed;
- old CLI source contains yfinance-assisted coding paths, so open-source CLI is NOT evidence of current connected plugin market-data provenance;
- real-time market-data marketing language does not prove CTA/UTP National NBBO.
Decision:
RALLIES_DAILY_RESEARCH_PLANE=HIGH_PRIORITY_REPLACEMENT_CANDIDATE
RALLIES_MC_PRIMARY_REPLACEMENT=INVESTIGATE
RALLIES_DV20_PRIMARY=ALREADY_C4_17_ROLE_AND_STRONGER_NOW
RALLIES_STRICT_G9=NOT_PROVEN
No production authority upgrade yet.

## Rallies X evidence
Profile: https://x.com/ralliesai
Arena: https://x.com/ralliesarena
Observed public posts support active platform/Arena usage but do not disclose upstream market-data feed provenance.
Decision: X is discovery/context only; no entitlement promotion.

## Massive — RECONFIRMED FAIL
Pricing: https://massive.com/pricing?product=stocks
Quotes docs: https://www.massive.com/docs/rest/stocks/trades-quotes/quotes
Detailed plan availability places quote/NBBO/live requirements on paid tiers; free does not satisfy.
Decision: not permanent-$0 strict G9.

## G9 near-miss X re-sweep
Paper Invest, Clear Street, Wealthnow, ForInvest were re-searched on indexed X.
No new provider/maintainer primary-source post was found proving all strict A+B+C+D.
Paper clarification issue remains:
https://github.com/paperinvest/mcp-server/issues/3
No maintainer/provider answer observed in latest direct fetch.
Decision: all remain near-miss/quarantine; registry state should not be promoted.

## Architectural consequence
Under PERMANENT_$0_PLUS_UNLIMITED:
- Bigdata MC primary must eventually be replaced.
- Alpaca settlement primary must eventually be replaced.
- Longbridge can remain a conditional fallback/account bridge only if the literal no-limit constraint is relaxed for provider safety caps; otherwise replace.
- Rallies is the strongest newly revalidated broad-data replacement candidate, but provenance must be solved first.
- Official SEC/Nasdaq feeds are authoritative and free but have fair-access/poll cadence; they should be ingested incrementally then used locally without computation limits.

## Preferred replacement research path
UNIVERSE = NasdaqTrader official files + local append-only PIT snapshots.
EVENTS = SEC/issuer IR/Nasdaq event feeds + local data lake.
PRICE/DV20 = Rallies broad daily data if provenance/terms qualify, independently cross-checked against official/other zero-dollar evidence.
MC = official SEC share-count vintage × qualified price, plus Rallies market-cap crosscheck; never current-value look-ahead.
G9 = remains separate and BLOCKED until a provider proves National NBBO + timestamps + permanent-$0 automation + scheduler callability.

END.
