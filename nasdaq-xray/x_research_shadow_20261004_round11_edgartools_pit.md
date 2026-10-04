# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 11 EdgarTools + PIT Event Layer

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## X discovery lead
X profile: https://x.com/dwightwgunning
Project: https://github.com/dgunning/edgartools
Docs: https://edgartools.readthedocs.io/

## Validated properties
- MIT-licensed open-source Python library.
- Talks directly to SEC EDGAR; no vendor API key/subscription required.
- Parses 20+ filing types including 10-K, 10-Q, 8-K, Form 4, 13F, N-PORT, 13D/G, S-1, Form 144.
- Structured XBRL/financial statements, filing text, insider transactions and exchange/ticker lookup.
- Built-in configurable rate limiting, smart caching and batch handling.
- Built-in MCP/AI integration available as local/self-run tooling.
- README explicitly distinguishes its free local library from paid hosted API products.

## XRAY candidate use
Name: EDGARTOOLS_OFFICIAL_SEC_PARSER_V1
Role: local parser/cache/index layer on top of T0 SEC authority.
Potential replacements/enhancements:
- eliminate dependence on paid SEC parsing APIs;
- typed 8-K event extraction;
- Form 4 insider event parsing;
- 10-Q/10-K shares/fundamentals extraction;
- S-1/424B/ATM/secondary/dilution research;
- local caching to reduce SEC request fanout;
- MCP-compatible query layer for event engine.

## PIT guard
EdgarTools returns latest/current and historical filings, but XRAY must still impose its own point-in-time contract:
- use actual SEC filing/accepted/accession timestamps;
- never substitute current restated values into an earlier ASOF;
- persist immutable vintages;
- attach every parsed fact to exact accession/form/filing timestamp;
- event discovery time must be <= decision ASOF.
Use XFINLAB point_in_time_store architecture as design reference, but prefer SEC actual accepted timestamp over arbitrary fixed delay.

## Cost/limit classification
SOFTWARE_COST=PERMANENT_ZERO
LOCAL_COMPUTE_AFTER_CACHE=UNLIMITED
UPSTREAM_SEC_REQUESTS=FAIR_ACCESS_LIMITED
Thus do not describe SEC network access itself as unlimited. Bulk/RSS/cache should minimize external calls.

## Authority
EdgarTools is parser/transport, NOT authority. SEC EDGAR remains T0 authority.

END.
