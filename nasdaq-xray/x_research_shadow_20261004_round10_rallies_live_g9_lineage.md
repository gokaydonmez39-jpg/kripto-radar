# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 10 Rallies Live-G9 + Lineage

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
G9_PASS_CHANGE=NO
ACCOUNT_PASS_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## Rallies live market-data tool audit
Connected Rallies tool surface was exhaustively searched for quote/bid/ask/latest-trade/snapshot/realtime/price tools.
Available relevant tools include minute/day chart bars, historical prices, price performance and dark-pool trades.
No connected Rallies tool exposes the strict G9 shape: current National-NBBO bid + ask + separate latest trade + independent upstream quote/trade event timestamps.
Decision: RALLIES_STRICT_G9=FAIL_FOR_CURRENT_TOOL_SURFACE.

## Minute-bar behavior
AAPL get_recent_chart_data(timeframe=1min) returned processed aggregate rows including fractional volume and naive local-looking datetime strings.
These are suitable for research/discovery only; do not infer exchange-event semantics or NBBO.

## Polygon -> Massive lineage chain
Historical first-person developer/community evidence (2025-07-31) states Rallies paid Polygon.io for realtime stocks/options data.
Massive official rebrand announcement states Polygon.io renamed to Massive.com on 2025-10-30 while API/data/accounts remained the same product lineage.
Rallies official 2026 OpenFactor repository directly implements Massive adapters for:
- /v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}
- /v2/aggs/grouped/locale/us/market/stocks/{date}
- /v3/reference/tickers
- dividends and short-interest.
OpenFactor repo: https://github.com/ralliesai/openfactor
Massive client: https://github.com/ralliesai/openfactor/blob/main/data/providers/massive/client.py
Massive stocks: https://github.com/ralliesai/openfactor/blob/main/data/providers/massive/stocks.py
OpenFactor data notes: https://github.com/ralliesai/openfactor/blob/main/data/README.md
Massive rebrand: https://massive.com/blog/polygon-is-now-massive

Observed runtime evidence: connected Rallies all-US daily rows for 2026-10-02 matched Massive grouped-daily rows exactly for AAPL/NVDA/MSFT across OHLC, volume, VWAP, trade count and timestamp.
Conclusion: RALLIES_MASSIVE_LINEAGE=VERY_STRONG_EVIDENCE.
Guard: do not assert every Rallies platform/ChatGPT endpoint is contractually sourced from Massive unless Rallies documents that exact binding.

## Clear Street exact G9-B semantics
MCP docs: https://docs.clearstreet.com/guides/mcp/
Changelog: https://docs.clearstreet.com/changelog/
Clear Street 2026-08-17 market-data snapshot update documents:
- bid_venue and ask_venue MICs for venues holding National Best Bid/Offer;
- separate bid_timestamp and ask_timestamp as exchange timestamps;
- last_trade venue and trade timestamp as exchange event time.
Classification: CLEAR_STREET_G9_B=STRONG/PRACTICALLY_EXACT.
Remaining blockers: Turkey/individual eligibility, account prerequisite, permanent-$0 entitlement, no-balance/no-activity conditions.

## Paper Invest safety note
Official MCP repo: https://github.com/paperinvest/mcp-server
The official MCP server exposes both read market-data tools and paper-order/account mutation tools.
Any future XRAY integration must NOT attach the full MCP toolset. Use a read-only REST adapter allowlisting only quote/trade endpoints under EXECUTION=NONE.

## UTP classification remains unresolved
UTP1APIS vendor-billable $1 supports theoretical $0 end-user API delivery, but private unattended cloud investment analysis classification vs Non-Display remains unresolved.
No provider silence may be converted to PASS.

STRICT_G9_PASS=FALSE
TRUE_FULL_GO=BLOCKED

END.
