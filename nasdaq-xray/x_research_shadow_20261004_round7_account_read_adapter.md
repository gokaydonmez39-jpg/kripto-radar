# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 7 ACCOUNT Read Adapter

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
ACCOUNT_PASS_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## Rallies authenticated portfolio surface
Public platform: https://rallies.ai/
Pricing: https://rallies.ai/pricing
Agents: https://rallies.ai/features/agents

Connected Rallies ChatGPT tools expose read functions including:
- get_users_portfolio_data: current positions, trades, portfolio account objects, total balances, broker/institution info, sync status.
- get_users_financial_snapshot: portfolios/banks/crypto/net-worth/connections/manual assets.
- get_users_portfolio_exposure_analysis: exposure by symbol/account/sector/asset class/open P&L.
- get_users_financial_activity: recent brokerage activity.

Public Rallies documentation says brokerage connections are separated through SnapTrade and are read-only so Rallies cannot place trades or move funds.
Current ChatGPT Rallies tool catalog inspection found portfolio/account access under get_* read surfaces and no obvious order-placement/trade-execution mutation function in the exposed Rallies tool set.
Guard: tool-name inspection is not a formal permission proof; adapter must allowlist exact read calls and reject every other Rallies tool.

## Candidate ACCOUNT adapter — SHADOW ONLY
Name: RALLIES_ACCOUNT_READ_V1
Pass contract proposal:
1. Same scheduled run calls ONLY get_users_portfolio_data (optionally exposure snapshot for consistency).
2. At least one current connected brokerage account must have explicit broker/institution identity and successful sync state.
3. total balance must be finite and nonnegative.
4. positions list must be explicit; empty list is valid only if the provider explicitly reports a current synchronized zero-position account, never inferred from missing data.
5. Each position must have ticker, finite shares, finite market value/current price or an explicit unsupported asset classification.
6. Capture provider timestamp/sync timestamp when exposed; stale or unknown freshness => ACCOUNT UNKNOWN.
7. Execution/write capability remains disabled by policy; do not call AI-fund creation/trading or any future mutation tool.
8. Compare account total versus sum of position/cash components within a measured tolerance when fields permit.
9. Persist only derived gate witness/minimal metadata needed by XRAY; do not persist unnecessary personal transaction details.

## Why this matters
Current Longbridge account adapter is blocked by OAuth scope 403308 and Longbridge OpenAPI has account/entitlement conditions. Rallies is currently advertised full-access free with no subscription or usage limits and already runs in the ChatGPT connected-provider environment.
Potential: provider-neutral replacement for Longbridge ACCOUNT gate IF the authenticated Rallies user has a supported, successfully synchronized brokerage.

## Current status
RALLIES_ACCOUNT_TOOL_CAPABILITY=PROVEN
RALLIES_PUBLIC_READ_ONLY_BROKER_MODEL=PROVEN
RALLIES_CURRENT_USER_SUPPORTED_BROKER_CONNECTION=UNPROVEN
SAME_RUN_ACCOUNT_WITNESS=NOT_RUN_IN_THIS_RESEARCH_TURN
ACCOUNT_PASS=FALSE

No personal portfolio data was read during this research audit.

END.
