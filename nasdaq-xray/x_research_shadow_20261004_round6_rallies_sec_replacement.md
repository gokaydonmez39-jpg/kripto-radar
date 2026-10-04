# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 6 Rallies+SEC Replacement

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
G9_AUTHORITY_CHANGE=NO
ACCOUNT_AUTHORITY_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## Correction — non-API X automation
Official X automation policy: https://help.x.com/en/rules-and-policies/x-automation
Finding: X explicitly warns against non-API automation such as scripting the X website and says it can lead to account suspension.
Decision: last30days/Bird/browser-cookie X path is NOT an acceptable canonical unattended X ingestion dependency. Official X API/MCP remains the compliant programmatic route but is metered/credit-bearing. Production XRAY must not depend on X; X remains research/discovery only.

## Rallies platform vs public B2B API vs connected ChatGPT surface
Pricing: https://rallies.ai/pricing
Platform: https://rallies.ai/
Agents: https://rallies.ai/features/agents
Features: https://rallies.ai/features
B2B docs: https://rallies.ai/api-docs
B2B reference: https://rallies.ai/api-docs/reference
Screener: https://rallies.ai/api-docs/miscellaneous/screener
Facts: platform currently advertises full access free with no subscription or usage limits; public B2B API is a distinct 19-endpoint behavioral/filings API requiring an API key and does not document the rich raw OHLCV connector functions exposed in ChatGPT. Never transfer terms/capability between surfaces by inference.

## Scheduled connector callability proof
Current XRAY automation topology was re-read on 2026-10-04. XRAY Epoch Multi-Reader is hourly and explicitly permitted to perform provider reads while remaining zero-alpha/read-only. Historical passive resolver evidence shows scheduled Rallies scanner use over thousands of symbols.
RALLIES_CHATGPT_SCHEDULER_CALLABILITY=PROVEN_AT_ARCHITECTURAL_RUNTIME_LEVEL
This does NOT prove strict-G9 A/B/C or upstream entitlement.

## Full-universe daily evidence
Connected Rallies get_ohcv_data_for_all_tickers_for_a_date(date=2026-10-02) returned 12,601 U.S. symbols in one call with ticker/OHLC/volume/VWAP/transaction-count/timestamp fields.

## Massive-lineage numerical identity
Massive docs: https://massive.com/docs/rest/stocks/aggregates/daily-market-summary
For AAPL/NVDA/MSFT on 2026-10-02, Rallies and Massive matched exactly across open/high/low/close/volume/VWAP/transaction-count/timestamp. Alpaca historical SIP matched OHLC and transaction count but differed slightly on volume/VWAP.
RALLIES_MASSIVE_COMMON_DATASET_OR_UPSTREAM=STRONG_NUMERICAL_EVIDENCE
RALLIES_USES_MASSIVE=NOT_PROVEN

## Rallies market-cap quality test against SEC
Rallies samples:
AAPL price=333.519 MC=4869931924200
MSFT price=517.188 MC=3842942557957
NVDA price=234.229 MC=5649190650000
AMZN price=251.37 MC=2712973589629
META price=727.648 MC=1854788332298
AVGO price=355.085 MC=1695306910256

Official SEC outstanding-share sources:
AAPL 14,594,180,000 as of 2026-07-17 — https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm
MSFT 7,425,545,491 as of 2026-07-23 — https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm
NVDA 24.1B as of 2026-08-21 — https://www.sec.gov/Archives/edgar/data/1045810/000104581026000075/nvda-20260726.htm
AMZN 10,786,313,572 as of 2026-07-22 — https://www.sec.gov/Archives/edgar/data/1018724/000101872426000026/amzn-20260630.htm
META A 2,205,128,509 + B 342,377,716 = 2,547,506,225 as of 2026-07-24 — https://www.sec.gov/Archives/edgar/data/1326801/000162828026050705/meta-20260630.htm
AVGO 4,773,629,865 as of 2026-08-28 — https://www.sec.gov/Archives/edgar/data/1730168/000173016826000080/avgo-20260802.htm

Rallies MC / price implied share-count relative difference versus SEC:
AAPL +0.0513%; MSFT +0.0661%; NVDA +0.0757%; AMZN +0.0597%; META +0.0594%; AVGO +0.0155%.
All six are within 0.08%. RALLIES_MC_FIELD_QUALITY=STRONG_SAMPLE_EVIDENCE. FULL_UNIVERSE_CORPORATE_ACTION_SAFETY=UNPROVEN.

## Official SEC scalable path
Docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
Companyfacts bulk: https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip
Submissions bulk: https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip
Public APIs require no API key; bulk archives are republished nightly. One bulk download plus local storage can support unlimited local calculations without per-symbol API fanout.

## Candidate Bigdata replacement — SHADOW ONLY
Name: RALLIES_SEC_MC_V1
1. Identity from official Nasdaq master.
2. Rallies same ticker exchange=XNAS and finite positive market_cap.
3. Latest SEC shares-outstanding vintage must be available by ASOF.
4. Reject stale shares or split/merger/share-class/corporate-action conflict.
5. Compute SEC_MC = SEC_SHARES * verified_price.
6. Compare Rallies MC and SEC_MC using a threshold learned from shadow measurements, not guessed.
7. Near-$2B decisions require stronger corroboration/fail closed.
8. Persist source timestamps, SEC accession, price source, share-class aggregation and corporate-action evidence.
9. UNKNOWN remains UNKNOWN.
Potential: replace paid Bigdata primary MC only after full shadow equivalence and failure-injection testing. No production cutover now.

## Candidate price/DV20 architecture — SHADOW ONLY
Official Nasdaq master -> Rallies broad daily aggregates -> local rolling 20-session cache -> DV20/indicators/screens; SEC/Nasdaq official event/corporate-action sources protect identity/adjustments. Provider-lineage/terms remain unresolved, so Rallies cannot yet be sole production authority.

## G9 status
Nothing above solves strict real-time National NBBO G9. G9 remains BLOCKED.

END.
