# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 8 OpenFactor Lineage + Risk

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
G9_AUTHORITY_CHANGE=NO
ACCOUNT_AUTHORITY_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## Official Rallies OpenFactor repository
Repo: https://github.com/ralliesai/openfactor
License: Apache-2.0
Public model: openfactor-us1000 (top 1000 active US common stocks by market cap).

## Stronger Massive lineage evidence
Files:
https://github.com/ralliesai/openfactor/blob/main/data/providers/massive/client.py
https://github.com/ralliesai/openfactor/blob/main/data/providers/massive/stocks.py
https://github.com/ralliesai/openfactor/blob/main/data/README.md

OpenFactor's official Rallies data pipeline explicitly uses Massive for:
- ticker daily bars: /v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}
- all-US grouped daily market: /v2/aggs/grouped/locale/us/market/stocks/{date}
- reference tickers: /v3/reference/tickers
- dividends and short-interest data.
OpenFactor requires OPENFACTOR_MASSIVE_API_KEY and documents Massive as a paid raw-data provider.

This strongly explains the observed exact equality between connected Rallies 2026-10-02 all-ticker daily rows and Massive grouped-daily rows for AAPL/NVDA/MSFT.
Still NOT sufficient to assert that every Rallies platform/ChatGPT market-data tool is contractually backed by Massive. Product-surface binding remains separate.

## OpenFactor public-output gem
README: https://github.com/ralliesai/openfactor/blob/main/README.md
Public model files are designed to be consumed without direct vendor-data access.
Core objects: universe, factor exposures, factor returns, residual returns, covariance, idiosyncratic risk, metadata.

Public data URLs documented by the project:
https://openfactor-data.rallies.ai/factors/openfactor-us1000/latest.json
https://openfactor-data.rallies.ai/factors/openfactor-us1000/latest/metadata.json
https://openfactor-data.rallies.ai/factors/openfactor-us1000/latest/exposures.csv
https://openfactor-data.rallies.ai/factors/openfactor-us1000/latest/factor_returns.csv
https://openfactor-data.rallies.ai/factors/openfactor-us1000/latest/residual_returns.csv
https://openfactor-data.rallies.ai/factors/openfactor-us1000/latest/factor_covariance.csv
https://openfactor-data.rallies.ai/factors/openfactor-us1000/latest/idiosyncratic_risk.csv
https://openfactor-data.rallies.ai/factors/openfactor-us1000/latest/universe.csv

## Factor families
Market/Beta; Size/Mid-Cap; Momentum/Industry Momentum/Seasonality/Long-Term Reversal/Short-Term Reversal; Residual Volatility/Downside Risk/Prospect; Liquidity/Short Interest; Value/Earnings Yield/Forward Earnings Yield/Dividend Yield; Growth/Forward Growth; Profitability/Gross Profitability/Earnings Quality/Earnings Variability/Capital Discipline; Leverage/Asset Growth; Sector/Industry; Analyst Sentiment.

## XRAY candidate use — SHADOW only
Name: OPENFACTOR_RISK_OVERLAY_V1
Purpose: risk/diagnostic overlay, NEVER a setup creator and NEVER a G9 or price authority.
Candidate diagnostics when ticker is covered:
- beta and residual-volatility extreme
- downside-risk / prospect skew
- liquidity factor context
- short-interest exposure
- momentum and reversal conflict
- sector/industry concentration
- factor covariance / idiosyncratic risk
- candidate portfolio tracking-error contribution if ACCOUNT later passes.

Hard rules:
- missing ticker or stale snapshot => overlay UNKNOWN, never candidate failure by itself.
- OpenFactor top-1000 coverage is not full XRAY eligible universe, so it cannot be a global hard gate without proven coverage.
- public model is in-sample explanatory risk infrastructure; it does not prove alpha/forward returns.
- raw pipeline uses paid provider inputs; do not claim that rebuilding the model from source is permanent-$0.
- public model outputs may be consumed as a separate free diagnostic layer subject to availability and license.

## Rallies entitlement contradiction retained
Current Rallies pricing: https://rallies.ai/pricing — full platform currently free, no subscription or usage limits.
Historical official CLI: https://github.com/ralliesai/rallies-cli — documents free-tier rate limits and optional API key for higher limits.
Conclusion: entitlement is surface/version specific. Do not generalize current platform terms to legacy CLI/public B2B API or vice versa.

## G9 status
OpenFactor does not provide live NBBO and does not solve strict G9.

END.
