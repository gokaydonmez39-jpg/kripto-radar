# XRAY NASDAQ A9 — Arelle synthetic XBRL research (NOT production)

**Scope:** Only the XRAY Personal NASDAQ Swing Radar research directory and a new PR-only CI workflow. No production import, scheduler, broker, AL/stop/target, 477-scope, Sheet or push permission is introduced.

**Provider:** [Arelle](https://github.com/Arelle/Arelle), PyPI package `arelle-release==2.47.3`. Apache-2.0. PyPI release dated 2026-10-26, Python >=3.11; CI pins Python 3.12. Published wheel SHA256: `e3a4837ab0b8af0525ec7d1f01e5262f4e378cd8f196e2d3319ed725cae2e3bf`. Pinning a version alone does not pin the full transitive dependency graph.

**Goal:** Test that a fully fictional one-fact XBRL instance can pass separate deterministically audited CIK / context / acceptance timestamp / XNAS close / local schema / finite numerical checks *and* be independently parsed by genuine Arelle offline with exactly one fact and no reported errors. Negative tests reject lookahead, wrong issuer, remote taxonomy reference, XML entities, non-finite numbers, duplicate contexts, naïve datetime.

**Source contracts:** The current production market data remains Alpaca IEX EOD; the original deterministic 477-stock logic is never called here. SEC/EDGAR corporate XBRL data must NOT enter production from this lab. XBRL financial periods are distinct from the SEC publication timestamp: we inject an independent synthetic acceptance-time witness, not inferred from the financial instance. The limited 16:00 New York clock preflight intentionally excludes half-days; it does NOT replace `exchange_calendars` or production XNAS scheduling.

**Falsifiers / acceptance gates:**
1. Actual isolated CI execution imports Arelle and parses one fictitious local XBRL fact without unresolved schema errors, **PASS** required.
2. Both normal and `python -O` Python runs pass all negative cases; no `assert`-only protection.
3. Arelle network cache is disabled for the parse. PyPI package download during setup does not constitute an SEC or market data request.
4. Dependency and vulnerability review, licensing distribution review, and threat-model / network restrictions must be completed before any live SEC adapter. Current tests do not attest zero egress at the firewall level.
5. No external data or model API, no private sheet, no notification, no trading rights.
6. Failures are **HOLD**; don't merge until green CI and privacy checks and production diff review.

**Alternative:** Existing EdgarTools A8 already tests synthetic SEC header acceptance-time metadata. Arelle tests XBRL structural facts. Neither alone proves incremental forecasting alpha or current filing availability. Production adoption requires live publisher provenance, issuer mapping, licensable PIT history, costed independent holdout, and separate explicit approval.

**Known limitation:** XBRL base taxonomy may be unavailable offline for the synthetic local schema; if Arelle records an error, the negative outcome correctly blocks acceptance. Do not turn off Arelle errors or use a network resolver simply to make CI green.
