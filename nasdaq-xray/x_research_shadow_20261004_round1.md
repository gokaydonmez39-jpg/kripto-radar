# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 1

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
G9_AUTHORITY_CHANGE=NO
ACCOUNT_AUTHORITY_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## Purpose
Persist X-discovered engineering/data leads without contaminating C4.17 production authority. Every lead must pass independent primary-source validation before any production binding.

## Existing conclusions revalidated
- Alpaca Basic is NOT unlimited and NOT strict-G9: free live US-equity path is IEX; delayed/historical SIP is NON-G9; current connected live `feed=sip` probe fails while `iex` and `delayed_sip` succeed.
- Strict G9 remains BLOCKED. Do not infer National NBBO from realtime, Tape C, IEX, Cboe, Nasdaq Basic/QBBO, delayed SIP, or marketing language.
- ACCOUNT remains BLOCKED until same-run read-only balance + positions witness from an eligible sanctioned adapter.

## X-discovered lead A — Will Hu / big_movers
X: https://x.com/traderwillhu/status/2038432164782452744
Repo: https://github.com/willhjw/big_movers
Observed claim: self-hosted research tool processing daily OHLCV for 12,000+ US tickers including delisted names and surfacing historical top performers.
Classification: RESEARCH_METHODOLOGY_CANDIDATE
Production use: NO
Potential system value:
- survivorship-bias audit for historical setup research;
- delisted-name cohort for stress-testing A/B/C/D pattern definitions;
- historical exemplar library for visual/feature research.
Guard:
- repo accepts local CSV and does not establish authoritative raw-data provenance;
- never use its data directly for production PASS;
- use only after independent provenance/adjustment/corporate-action validation.

## X-discovered lead B — free multi-source MCP pattern
Repo: https://github.com/CohenD/fin-data-mcp
Observed: read-only MCP aggregating no-key Yahoo + Cboe and other public sources; explicit retries/cache/error mapping and provider fallback.
Classification: ENGINEERING_REFERENCE_ONLY
Potential system value:
- typed provider catalog;
- failover pattern;
- structured 403/429/451/5xx/timeout handling;
- TTL cache;
- never expose unavailable keyed tools.
Guard:
- Yahoo unofficial/bot-sensitive;
- Cboe path delayed/partial and not National NBBO;
- not a G9 authority.

## X/web-discovered lead C — Equibles self-hosted core
Repo: https://github.com/daniel3303/Equibles
Observed: AGPL self-hosted financial-data MCP with SEC/XBRL, 13F, insider/congressional trades, FINRA/SEC short data, FRED, CFTC/CBOE, FDA catalysts and daily prices. Self-hosted core advertised as free forever; live quotes are cloud/licensed, not self-hosted.
Classification: EVENT_RISK_DATA_LAKE_CANDIDATE
Potential system value:
- redundant SEC/event ingestion;
- FDA catalyst calendar for biotech event veto;
- FINRA short-interest/short-volume enrichment;
- FRED macro-event context;
- CFTC/CBOE market-context enrichment;
- local durable store and MCP query surface.
Guard:
- daily prices rely on Yahoo and cannot become price authority;
- FINRA/FRED may require free keys and source-specific limits;
- cloud live quotes are licensed and do not solve strict G9;
- no alpha promotion without source-by-source contract.

## X architecture lead — financially relevant social-event pipeline
X/Bloomberg partnership evidence shows a useful architecture pattern: curate financially relevant X posts, entity-map them, score/filter noise, and validate material posts against authoritative news/issuer sources.
Classification: ARCHITECTURE_PATTERN
Free-system adaptation:
X_DISCOVERY -> ENTITY_RESOLUTION -> MATERIALITY_SCORE -> OFFICIAL_SOURCE_RESOLUTION -> EVENT_CLASSIFICATION -> CANDIDATE_IMPACT -> QUARANTINE/PASS
Raw X content can never clear event risk by itself.

## Self-healing pattern
Use consistency checks + automatic repair/failover as a control-plane pattern:
- source freshness;
- schema/version drift;
- set/count drift;
- duplicate/missing events;
- failed provider batches;
- stale cache;
- delivery acknowledgement.
Automatic repair may restore control-plane configuration or fail over to a prequalified source; it may NEVER weaken alpha thresholds or convert UNKNOWN to PASS.

## Integration decision
ACCEPT_SHADOW:
- survivorship-bias research lane;
- local event/risk data-lake lane;
- provider-catalog/error-taxonomy/failover engineering pattern;
- X social-event discovery/official-source-validation pipeline.
REJECT_AS_AUTHORITY:
- big_movers raw CSV as production data;
- Yahoo/Cboe MCP as G9;
- Equibles Yahoo prices as production price authority;
- raw X post as event-clear evidence.

## Next X mining targets
1. Permanent-$0 National-NBBO/API claims with exact SIP/UTP/CTA lineage.
2. Hosted read-only MCP/API with unattended scheduler use and no funding/activity condition.
3. Open-source point-in-time/delisted US-equity datasets with explicit provenance.
4. Free issuer/earnings/IR event APIs and calendars with machine-readable timestamps.
5. Market-data quality/lineage tools: gap detection, corporate-action reconciliation, timestamp skew and cross-source consensus.
6. Agent observability: deterministic replay, event sourcing, health checks, canary/failover and notification acknowledgement.

END.
