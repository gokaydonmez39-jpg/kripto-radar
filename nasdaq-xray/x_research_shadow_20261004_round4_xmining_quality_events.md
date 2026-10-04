# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 4 X-Mining + Quality + Official Events

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
G9_AUTHORITY_CHANGE=NO
ACCOUNT_AUTHORITY_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## Gem 1 — last30days multi-source research engine
Repo: https://github.com/mvanhorn/last30days-skill
Skill spec: https://github.com/mvanhorn/last30days-skill/blob/main/skills/last30days/SKILL.md
X discovery example: https://x.com/Mnilax/status/2042647728660881677
Classification: RESEARCH_CRAWLER_ENGINEERING_CANDIDATE
Validated X behavior:
- Default X chain on ordinary hosts: Bird/browser cookies -> xAI -> xurl -> Xquik.
- Browser-cookie/Bird is the only potentially zero-incremental-cost X path but is session-dependent, scraping-based and carries account/platform risk.
- Official X API backend is opt-in and spends developer credits.
- Grok backend consumes a Grok plan; not free.
- Supports FROM/ABOUT lanes, source health diagnosis, backend failover, historical --as-of, and watchlist deltas.
Decision:
- useful for interactive/shadow X mining and source-discovery architecture;
- NEVER mandatory production dependency;
- NEVER describe as unlimited X API/firehose;
- use no secret/session automation without explicit user consent.

## Gem 2 — Official X hosted MCP / xurl
Docs: https://docs.x.com/tools/mcp
Hosted MCP: https://api.x.com/mcp
Open-source xurl: https://github.com/xdevplatform/xurl
Legacy/local xmcp reference: https://github.com/xdevplatform/xmcp
Classification: OFFICIAL_RESEARCH_INTERFACE
Value:
- official MCP tools for full-archive search, user/timeline/news/trends etc. when entitled;
- OAuth refresh and read-only app-bearer route.
Blocker:
- X Developer Platform is pay-per-use; post reads consume credits.
Decision:
- optional research accelerant only;
- violates permanent-$0 mandatory production condition.

## Gem 3 — X Community Notes open data + scoring code
Data guide: https://communitynotes.x.com/guide/en/under-the-hood/download-data
Scoring code guide: https://communitynotes.x.com/guide/en/under-the-hood/note-ranking-code
Classification: SOCIAL_SOURCE_DILIGENCE_OVERLAY
Facts:
- public data snapshots are free;
- notes/ratings/status/request data are downloadable;
- snapshots are best-effort daily and contain notes/ratings only through roughly 48h before release;
- scoring algorithm is open source/reproducible.
XRAY use:
- POSTMORTEM credibility/diligence overlay for X-discovered claims;
- flag posts that acquired helpful/inaccuracy/source-diligence notes;
- train/evaluate a social-source reliability feature.
Guard:
- 48h lag => never realtime candidate trigger or event-clear authority;
- absence of a Community Note never means claim is true.

## Gem 4 — Nasdaq Trade Halt RSS
Official page: https://www.nasdaqtrader.com/Trader.aspx?id=TradeHaltRSS
Direct current feed documented by Nasdaq: http://www.nasdaqtrader.com/rss.aspx?feed=tradehalts
Classification: OFFICIAL_EVENT_SAFETY_CANDIDATE
Facts:
- free;
- covers Nasdaq-listed and other exchange-listed halt/pause information;
- Nasdaq guideline: updated once a minute; do not query more than once per minute.
XRAY use:
- candidate-level HALT_VETO / RESUMPTION state;
- local cache; poll <= official cadence;
- independent social halt accounts become discovery-only.
Guard:
- free but not mathematically unlimited request cadence.

## Gem 5 — Nasdaq System Status RSS
Official page: https://www.nasdaqtrader.com/Trader.aspx?cid=21&id=SystemStatusRSS
Classification: OFFICIAL_MARKET_INFRA_HEALTH_CANDIDATE
XRAY use:
- exchange/system incident flag;
- Guardian market-infrastructure health;
- suppress false data-feed conclusions during known exchange incident.
Guard:
- system-status context, not stock alpha.

## Gem 6 — Nasdaq public Events Data
Symbol Directory: https://www.nasdaqtrader.com/Trader.aspx?id=symbollookup
Security Status: https://www.nasdaqtrader.com/Trader.aspx?id=nasdaq-security-status-updates
Ex-Date: https://www.nasdaqtrader.com/Trader.aspx?id=nasdaq-ex-date
Symbol definitions: https://www.nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs
Classification: OFFICIAL_CORPORATE_ACTION_RISK_CANDIDATE
Facts:
- Nasdaq states selected Events Data are publicly available without further licensing requirement;
- 2024 fee-change notice says public subset includes Financial Status, Market Categories, Issue Events (Additions/Delistings etc.), Ex-Dates and other information;
- full historical Daily List remains paid.
XRAY use:
- current listing/security-status/ex-date/event cross-check;
- nightly append-only local snapshot to build our own forward PIT history from now onward.
Guard:
- do NOT imply this reconstructs complete pre-existing historical Daily List;
- paid full Daily List remains unavailable under $0 rule.

## Gem 7 — SEC Latest Filings/RSS + JSON APIs
Developer resources: https://www.sec.gov/about/developer-resources
EDGAR APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
Latest filings: https://www.sec.gov/search-filings
RSS: https://www.sec.gov/about/rss-feeds
Structured disclosure RSS: https://www.sec.gov/data-research/structured-data/structured-disclosure-rss-feeds
Classification: T0_EVENT_AUTHORITY
Facts:
- submissions/XBRL JSON APIs require no authentication or API key;
- latest filings support RSS filters by company/CIK/form;
- SEC fair-access guideline <=10 requests/sec;
- structured-disclosure RSS updates every ten minutes on stated weekday window.
XRAY use:
- official 8-K/10-Q/10-K/Form4/13D/G/144 discovery;
- exact accession binding;
- event timestamps into PIT store;
- local append-only cache/bulk archives to minimize requests.
Guard:
- external service has fair-access cap, so $0 yes, unlimited requests no;
- local computation/caching can be unlimited after ingestion.

## Gem 8 — Nasdaq current public symbol/event delta path
Definitions: https://www.nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs
Public Add/Delete file documented: ftp://ftp.nasdaqtrader.com/dynamic/SymDir/TradingSystemAddsDeletes.txt
Nasdaq-listed file: ftp://ftp.nasdaqtrader.com/symboldirectory/nasdaqlisted.txt
Classification: OFFICIAL_UNIVERSE_DELTA_CANDIDATE
XRAY use:
- current canonical universe;
- snapshot each file version locally with creation/effective time;
- diff Add/Delete forward to create a PIT universe history from integration date onward.
Guard:
- does not supply full historical delisted universe before our own capture start;
- full Daily List history is paid.

## Integration decisions
SAFE_TO_DESIGN_FOR_PRODUCTION (after implementation tests, no alpha change):
- Nasdaq halt RSS
- Nasdaq system-status RSS
- Nasdaq public events/security-status/ex-date pages
- SEC RSS/JSON APIs
- append-only local PIT snapshots of official universe/event sources

SHADOW/RESEARCH ONLY:
- last30days
- official X MCP/xurl
- Community Notes reliability overlay

ABSOLUTE RULE:
FREE_SOFTWARE != UNLIMITED_UPSTREAM.
PERMANENT_ZERO must be evaluated separately for software license, market-data license, external API quota, authentication/account conditions, and compute/storage.

END.
