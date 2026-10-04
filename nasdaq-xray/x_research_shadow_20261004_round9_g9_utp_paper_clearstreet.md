# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 9 G9 UTP + Paper + Clear Street

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
G9_PASS_CHANGE=NO
ACCOUNT_PASS_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## UTP structural licensing gem
Official policies:
https://www.utpplan.com/DOC/datapolicies.pdf
https://www.utpplan.com/DOC/UTP_POLICY_SUPPLEMENTAL_DOCUMENT_-_VRXML_Codes.pdf
https://www.utpplan.com/DOC/NonDisplayDeclaration.pdf
https://www.utpplan.com/DOC/UTP%20DATA%20POLICIES-1%20Fees.pdf

Key facts:
- API is explicitly an Uncontrolled Product class under UTP policy.
- UTP1APIS = Real-Time Nonprofessional Uncontrolled Recipient; detailed reporting; billable to vendor; $1/month as of the current reporting-code table.
- Therefore a permanent $0 END-USER real-time Tape-C/NBBO API is theoretically possible when the vendor lawfully absorbs/reports the subscriber fee.
- Non-Display is a separate policy category. Current declaration/policy includes investment analysis, risk management and portfolio valuation as examples of Non-Display use by an organization/Data Feed Recipient.
- Current fee schedule shows $3,500/month per firm for Real-Time Non-Display Internal Use and $3,500/month per firm for use on behalf of customers.
- Policy text does not safely answer whether a natural-person nonprofessional receiving a vendor-supplied uncontrolled API and running private unattended cloud research remains UTP1APIS, or becomes separately non-display fee-liable.
Decision: G9 C remains UNKNOWN until UTP/vendor gives written classification. Do not infer.

## Paper Invest — strongest permanent-$0 strict-G9 candidate
Pricing: https://paperinvest.io/pricing
API landing: https://paperinvest.io/paper-trading-api
Market data docs: https://docs.paperinvest.io/market-data
MCP landing: https://paperinvest.io/mcp
Official MCP repo: https://github.com/paperinvest/mcp-server
Clarification issue: https://github.com/paperinvest/mcp-server/issues/3

Validated facts:
- Basic = $0/month, free forever, API & MCP access.
- REST quote endpoint is marketed as real-time NBBO with bid/ask sizes.
- Separate REST last-trade endpoint exists.
- Single quote/trade endpoints have high rate limits (1000 requests per unspecified window).
- Batch quote and batch trade endpoints accept 1..50 symbols and docs explicitly say no rate limiting applied to batch requests.
- Quote response has bid/ask/last and a timestamp; trade response has independent endpoint timestamp.
- WebSocket market data is Pro-only and therefore NOT usable under permanent-$0 requirement.
- Official MCP server is stdio/local and exposes both reads and paper-order mutations. XRAY must never bind the full MCP toolset because EXECUTION=NONE; a future adapter must allowlist read-only REST quote/trade only.

Unresolved blockers:
A: Docs say NBBO but do not identify UTP Tape C/UQDF/UTDF or licensed redistributor lineage.
B: Quote/trade timestamps are documented only as Unix-ms; exact upstream event-time vs Paper receive/server-time semantics are not stated. Separate endpoints alone are not enough.
C: Basic $0 is strong; batch no-rate-limit is strong; but provider-specific UTP1APIS/non-display classification remains unanswered.
D: REST is cloud-callable with API key and Paper documents agent/API runtimes, but XRAY canonical scheduler binding with secret-safe adapter has not been implemented/tested.
Current status: HIGHEST_POTENTIAL_G9_CANDIDATE / NEVER PASS BY INFERENCE.
Provider issue remains open with no maintainer response as of 2026-10-04.

## Clear Street — strongest technical B-gate candidate
MCP docs: https://docs.clearstreet.com/guides/mcp/
Changelog: https://docs.clearstreet.com/changelog/
API docs: https://docs.clearstreet.com/api/

Validated facts:
- Read-only MCP endpoint: https://api.clearstreet.com/v1/mcp ; cannot place/cancel orders under any circumstances.
- get_market_data_snapshot exposes current L1 quote + last trade.
- August 17 2026 changelog explicitly says last_quote reports bid_venue/ask_venue MICs for venues holding NBBO, bid_timestamp/ask_timestamp as exchange times, and last_trade venue/timestamp as exchange trade time.
- This is an unusually exact match for G9 B semantics.
- MCP requires Clear Street login with access to at least one OEMS trading account.
- Clear Street trading platform is fee-bearing for actual trading, and no primary-source proof currently establishes a Turkey-resident retail account path with permanent-$0/no-balance market-data entitlement.
Current status: TECHNICAL_A_B_D_STRONG; C + TURKEY ELIGIBILITY UNPROVEN.

## ForInvest — Turkey-fit near miss
MCP: https://mcp.forinvest.com/
Docs: https://mcp.forinvest.com/docs
Free/live data: https://www.forinvest.com/canli-veri
Plans: https://www.forinvest.com/standard-plan
FXPlus free/delayed: https://www.forinvest.com/fx-plus

Validated facts:
- Hosted StreamableHTTP MCP, OAuth2+PKCE, read-only tools.
- Docs claim real-time and historical data for BIST and global markets.
- Free ForInvest account exists.
- Consumer free-live page specifically establishes free live BIST data; FXPlus free plan explicitly says data are 15-min delayed and live BIST requires paid Basic.
- No primary-source documentation found proving free-account US equity National NBBO/CTA/UTP lineage or independent quote/trade timestamps.
Current status: TURKEY_AND_D_STRONG; G9 A/B/C UNPROVEN.

## Wealthnow — removed from strict unlimited shortlist
Pricing: https://app.wealthnow.io/docs/pricing-and-credits
Quickstart: https://app.wealthnow.io/docs/quickstart

Validated facts:
- Free market_data and fundamentals routes exist.
- Free tier has a fixed monthly 1,000-credit grant, hard cap, and plan rate limits.
- Therefore it fails the user's strict NO_USAGE_LIMITS requirement regardless of quote quality.
Decision: NOT a permanent strict-G9 core provider. May remain diagnostic only.

## No provider-response change
2026-10-04 checks:
- Clear Street email thread: no provider/human reply.
- Wealthnow email thread: no provider/human reply.
- Alpaca email thread: no provider/human reply.
- UTP admin email thread: no provider/human reply.
- ForInvest email thread: no provider/human reply.
- Paper Invest GitHub issue #3: open; no maintainer reply.
No gate may be upgraded from silence.

## Strict G9 ranking after Round 9
1. Paper Invest — highest potential permanent-$0 path; A/B timestamp semantics/C classification/D binding unresolved.
2. Clear Street — strongest exact NBBO/timestamp technical path; permanent-$0 and Turkey/account eligibility unresolved.
3. ForInvest — strongest Turkey-native hosted MCP path; free US-NBBO entitlement/lineage unresolved.
4. Rallies — strong zero-cost connected daily/intraday research data but no bid/ask NBBO tool; not G9.
Wealthnow removed from strict unlimited shortlist.

STRICT_G9_PASS=FALSE
TRUE_FULL_GO=BLOCKED

END.
