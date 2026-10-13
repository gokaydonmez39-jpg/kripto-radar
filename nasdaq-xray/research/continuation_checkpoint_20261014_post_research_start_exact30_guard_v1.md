# NASDAQ SWING X-RAY — research start live CI continuation, 2026-10-14

## Immutable evidence / no reset

- Project: gokaydonmez39-jpg/kripto-radar, branch main. This note records the research-only engineering continuation after nasdaq-xray/research/continuation_checkpoint_20261014_new_chat_research_start_v1.md.
- Prior source main HEAD: `2ef2ff081a9b988f63f2f4359f85ce4d2e2f6394`.
- Prior AAPL cross-timeframe pilot: GitHub Actions `38466943779` SUCCESS; 30 Nasdaq sessions / 11,700 1Min / 390 30Min, 7 API requests, SHADOW.
- Prior 4-symbol bounded SIP research: GitHub Actions `38468954318` SUCCESS; AAON/AAPL/MSFT/NVDA 4/4 SHADOW RTH lower-bound >= USD 50,000,000 (not C4.17 PRIMARY); 10 recorded API calls; no repeated historical download authorized by this note.

## Source-exact code repair and green CI

- RED predicate witness: old `measure()` precondition `len(dates)==30 and dates[-1]==ASOF` accepted a deterministic 30-element date sequence with 29 unique sessions (duplicate dates). The precondition did not independently validate the frozen Nasdaq session set. This is a validator defect, not evidence that the earlier provider artifact was bad.
- Commit: `33f50b5eed93e6581eb1c8769d03d4011c8e7979`, message `fix(xray): enforce frozen exact30 Nasdaq calendar before shadow classification`.
- Changed only `nasdaq-xray/alpaca_sip_4symbol_30min_rth_shadow.py`, preimage blob `daa6abb74e0e5b1dba58270d03949226086cb065`, readback blob `527936d2eb06c9d92c90364e9391974e0c3085eb`.
- Implementation: cached independent Nasdaq official valid_days calendar from 2026-08-31 through frozen ASOF 2026-10-12; `measure` rejects any incoming date list not byte/order/exact-set identical. Prevents duplicates, reordering, missing/supplanted sessions, shortened lists, or bad types from being classified.
- Added five negative fixtures: duplicate, reordered, earlier wrong official session instead of required one, truncated, wrong container; preserve existing positive/mixed/integrity/pagination tests. Threshold unchanged.
- GitHub Actions `38471033844`, job `115549862575`: completed SUCCESS on exact commit. CI logs show `XRAY_4SYM_OFFICIAL_EXACT30_NEGATIVE=PASS_DUPLICATE_ORDER_MISSING_TRUNCATION`, `XRAY_4SYM_30M_PAGINATION_SELFTEST=PASS_MERGE_CYCLE_LIMIT_FOREIGN_NO_HTTP`, and `XRAY_4SYM_30M_EXACT30_SELFTEST=PASS_MIXED_UNKNOWN_BOUND_NO_PRIMARY`, each in normal Python and Python -O.
- The run used a normal commit message without `[run4bound]`, `[run30mbound]`, or `[run540shadow]`; the previous 30-day four-symbol or 540-symbol provider research was not repeated. Routine runner canaries report stale/invalid current PRICE scope, API calls 0 for the RTH-minute request, no source-primary/R92 claim.
- CI is code and research-canary success, not live current-asof C4.17 PRICE/DV30 PASS, not official RTH corrections/auction proof, not PRIMARY MC, and not R92.

## Live canonical gate readback at this continuation

- MASTER `canonical_current_master_manifest.json`: blob `fb64a44b79ced9dcda390f5661b796ee13a60f63`; 2026-10-12; 3184 PASS_IDENTITY, 10 UNKNOWN_IDENTITY; PARTIAL_UNKNOWN.
- PRICE `canonical_current_price_dv30.json`: blob `787e1222fe140ae141b51e98bbbaaa9034ead377`; 2026-10-12; 540 remaining UNKNOWN according to the frozen source cohort; no current primary DV30 generated here.
- HISTORY `canonical_current_history.json`: blob `28e182225c45c3adf4243e40eb7df7ebdb783884`; 2026-10-07, stale relative to PRICE.
- TERMINAL `canonical_current_terminal.json`: blob `ea9c41cd1e5971e78d85bf3f620d7f8c4e01034f`; 2026-10-07 PARTIAL; candidate_local_research_pass=false; r92_candidates=[].
- FINAL overlay `canonical_current_final_gate_overlay.json`: blob `1f489c7a6306d0b0d8d5c75056f1606416d94e05`; ASOF 2026-10-07, stale.
- Strict G9 entitlement `g9_entitlement_authority.json`: BLOCKED_STRICT_PERMANENT_ZERO. ACCOUNT same-run PASS unproven. TRUE_FULL_GO=NO-GO.
- Research-only start config `research_only_start_20261010.json`: active=true, mode=RESEARCH_ONLY, EXECUTION=NONE, REAL_MONEY=NO-GO.
- Five XRAY recurring ChatGPT automations were privately read back enabled: Reader :43, Committer :46, Health :49, Finisher :52, Canonical :57 America/New_York. No sixth created and none modified.

## Eight acceptance stages / outstanding dependencies (do not relabel PASS)

1. Root/Resilience official calendar precedent CI PASS; current scheduling/runner freshness must be checked for each candidate.
2. Actual Health closed-session/holiday no-CAS automatic recovery run: UNVERIFIED.
3. Alpaca historic SIP personal access verified only for bounded read-only SHADOW; automated non-display data rights for PRIMARY are NOT ATTESTED. The official Alpaca Basic docs allow historical SIP older than 15 minutes; this is NOT a standalone redistribution/right-to-primary proof.
4. C4.17 exact official 30 RTH DV30 for 540 unknown: SHADOW sampled four positives; 27 previous daily anomalies; close-auction/corrections/exchange provenance and full PRIMARY rights unavailable => BLOCKED.
5. PRIMARY MC: currently no same-ASOF Bigdata exact qualifying market-cap measurement. SEC point-in-time share-count and issuer-class work and lawfully entitled alternative vendors remain RESEARCH, NOT PRIMARY.
6. MASTER 10 unknown + same-ASOF 260 daily and 52 weekly HISTORY exact source: BLOCKED / STALE.
7. Exact current LEGAL/EVENT/TECH/FINAL and durable R92 lifecycle/deduplicated ChatGPT receipt: UNVERIFIED; no candidate/no iPhone receipt attested.
8. Strict G9 + synchronized read-only ACCOUNT for TRUE_FULL_GO: BLOCKED; not mandatory to issue a truly verified research-only manual candidate.

## Safest following research phase

Retain the previous positive four-symbol historical cohort without redownloading. Before any bounded new-symbol SIP research, independently establish relevant personal/automated access conditions, official RTH correction/auction treatment and current source ASOF. Separately investigate SEC PIT issuer/market-cap and the ten master unknowns using lawful, bounded, official source methods; never silently substitute shadow for C4.17 Bigdata PRIMARY. Candidate-local release requires exact-current independent PRICE/DV30/PRIMARY MC/HISTORY/LEGAL/FINAL/safety/R92 proof. No new paid fallback, provider raw OHLCV, broker or execution. Research START is active; research R92 not yet ready; TRUE_FULL_GO NO-GO. Always refetch live HEAD because this document is historical.

EXECUTION=NONE; REAL_MONEY=NO-GO; UNKNOWN!=PASS; policy C4.17 and control C4.27 frozen.
