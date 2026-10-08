# NASDAQ SWING X-RAY — Deep X-Ray end-to-end production audit

**Audit timestamp (TRT date):** 2026-10-09. **Live-main reference HEAD at source readback:** `06e2d72f8049ec27ce224a9101d6cdeef03cfaaa`. **Research ASOF:** 2026-10-08 ET, where available. **Purpose:** rigorous production-readiness assessment; this document is DIAGNOSTIC ONLY, not a candidate signal or an alpha authority.

**Mandatory controls:** C4.17, execution NONE, real money NO-GO, UNKNOWN != PASS, no paid entitlement/upgrade, no account read or brokerage operation for RESEARCH_ONLY_MANUAL_DECISION; do not relax MC, PRICE, DV30, HISTORY, weekly, risk, R/R or official event vetoes. C4.27 is a user-stated control, not independently attested as satisfied by this report.

## Verdict

**MANUAL_SIGNAL_PRODUCTION_BLOCKED** and **FULL_E2E_RESEARCH_PASS=NOT_ATTESTED for 2026-10-08**. Valid completed settlement and Preis/DV30 provenance are not proof of a current MC/HISTORY/SETUP/FINAL/R92 chain. Historical 2026-10-07 findings must never be represented as 2026-10-08 NO_QUALIFIED.

## Source identity, coverage and cardinality

| Layer | Evidence | Audit assessment |
|---|---|---|
| Full NASDAQ identity | 2026-10-08 MASTER 3,183 eligible identity PASS; 72 SPAC-name-suspect identity UNKNOWN; 2,375 instruments excluded by earlier type partition | PARTIAL_UNKNOWN, not FULL_COMPLETE |
| PRICE/DV30 | 3,183 exact current results; 514 PASS_PRICE_DV30; 45 BLOCK_CURRENT_RUN; 1,306 FAIL_PRICE; 10 FAIL_PRICE_NO_ASOF_BAR; 1,299 FAIL_DV30; 9 FAIL_DV30_INSUFFICIENT_SESSIONS; 0 UNKNOWN | PRICE PARTITION CONSISTENT; 45 BLOCK cannot become PASS |
| Exact completed 30 sessions | C4.17 Rallies-primary exact30 authority with immutable 2026-10-08 evidence; $5 minimum and median Close * RTH volume >= $50m | PASS for 514 current-price members ONLY |
| 2026-10-08 settlement | SIP completed daily bars for AAPL/NVDA/MSFT with Rallies and Longbridge OHLC <= $0.01 each, positive SIP volume; `v1` settlement PASS, `v2` full-scope provenance witness; five negative mutations in CI PASS | SETTLEMENT PASS, explicitly NON-G9; not MC/PRE-G9 PASS |
| 2026-10-08 MC | NO canonical committed primary MC authority bound to 2026-10-08 PRICE 514 PASS; Post-MC log: `MC_AUTHORITY_MEASUREMENT_REQUIRED` | CRITICAL BLOCK |
| 2026-10-08 HISTORY/weekly | Current HISTORY/weekly not committed with current MC; 2026-10-07 history had 460/472 pass, 12 history fail, 100 weekly PASS | CURRENT UNKNOWN; historical is DIAGNOSTIC ONLY |
| Regime | 2026-10-07 snapshot QQQ 757.73, breadth 37.6087%, regime MIXED; no current 2026-10-08 regime authority | NOT CURRENT |
| Technical candidate generation | 2026-10-07 17 confirmed-family finalists; 17/17 FAIL_RISK_GEOMETRY, 17/17 risk > 8%; 16/17 RR basic and 16/17 severe low; 17/17 MC WATCH and R92-ineligible; pre-G9 tech PASS 0 | HISTORICAL VALID RET, NOT CURRENT NO_CANDIDATE |
| Official events | 2026-10-07 event state coverage_complete=false, 87 unresolved, 17 affected geometry unknown; temporal mismatch to 2026-10-08 | PARTIAL, NOT CURRENT |
| Terminal and pointer | Terminal, event, HISTORY, weekly and deep-final ASOF = 2026-10-07; master and PRICE ASOF = 2026-10-08; current overlay shows `current_research_chain.exact=false` | EPOCH/BLOB MISMATCH BLOCK |
| Manual research channel | Manual workflow 37851107495 failed `UNBOUND_SOURCE:events` due historical terminal evidence reference vs changed live same-ASOF event artifact; refusal is fail-closed, public source-integrity telemetry emitted | REAL SIGNAL PRODUCTION BLOCKED |
| Delivery | Latest delivery run 37851636944 SUCCESS but `NO_REGISTERED_RESEARCH_CANDIDATE` explicitly; delivery ledger `deliveries={}`; no issue/push/device receipt verified | ZERO ACTUAL DELIVERY; synthetic test not receipt |
| GitHub root factory | Root run 37850931563 SUCCESS but logged `XRAY_ORCHESTRATOR=PARTIAL_HISTORY`: 3,183/3,183 cursor, 3,155 UNKNOWN_STATIC + 28 exhausted, zero Sina candidates. Canonical independent PRICE can still pass 514. | GREEN RUN != FULL E2E |
| Strict G9 | Historical `strict_g9_runtime_state`: G9 blocked due consolidated live NBBO rights/source and $0 automation not proven | BLOCKED; not mandatory for manual research |
| Account | Account gate `ACCOUNT_BOOTSTRAP_READY_CREDENTIALS_REQUIRED`, same-run ACCOUNT PASS false | BLOCKED; not mandatory for manual research |
| Automations | 5 existing Radar/Reader/Committer/Health/Finisher tasks enabled. Last-run timestamps are invocations, not production delivery receipts. | ENABLED, no end-to-end proof |
| Policy conformance tests | Dynamic Policy Invariants run 37850977121 SUCCESS; Dynamic Phase Regression run 37850977079 SUCCESS; SIP witness guard Pre-MC run 37851636951 SUCCESS | POSITIVE STATIC/SEMANTIC TESTS, NOT PRODUCTION SIGNAL |
| Root and downstream workflow semantics | Post-MC run 37851693525 SUCCESS but `MC_AUTHORITY_MEASUREMENT_REQUIRED`; Final run 37851714888 SUCCESS but `CURRENT_DV30_MC_CHAIN_NOT_EXACT`; Delivery run 37851636944 SUCCESS but no candidate | GREEN NOOP AND GREEN BLOCKED states correctly distinguished |

## Scope conflict — separate policy decision

Compiled C4.17 universe explicitly includes `eligible ADR` whereas the user's earlier reference scope specified NASDAQ operating common equity excluding ADR. As a *name-only diagnostic* (NOT an official instrument-type reclassification), 187 explicit ADR/ADS/New York Registry names exist within the 3,183 master PASS and 23 within the 514 PRICE PASS. For instance ARM, BIDU and PDD. No master/alpha policy change is authorized by this audit. A formally versioned user-approved universe decision must resolve the spec conflict without silently changing canonical history.

## Market-cap authority deadlock

C4.17 primary MC requires exact Nasdaq-family public-company Bigdata identity and finite USD market cap >= $2 billion. Provider call returned `credits used up` during live audit. Policy fallback A or B/C can yield WATCH only and `R92=false`, even with two-source numeric evidence; WATCH != primary PASS. The 2026-10-07 bridge had 0 primary PASS; 472 fallback WATCH; 9 fallback FAIL; 29 MC UNKNOWN out of 510 PRICE PASS. 2026-10-08 canonical MC is **absent**, not equivalent to the old 7 October counts. Massive `/v3/reference/tickers/AAPL?date=2026-10-08` returned one dated MC observation, but that is a shadow feasibility observation: a single ticker does NOT authorize a 514-ticker same-ASOF primary-provider migration. Longbridge historical candles returned quota 0/0 in the prior connected probe; broad collection is governed as forbidden. Never fabricate same-run entitlement, market cap, or a provisional AL from these references.

## Prohibitions and fault isolation

- NEVER treat `workflow SUCCESS` as proof of MC, technical AL or delivery receipt.
- NEVER treat a zero-candidate result from static `sina_stage.py` as proof that 514 current PRICE/DV30 PASS members have no setups.
- NEVER mark WATCH, BLOCK, stale 2026-10-07 data or UNKNOWN as 2026-10-08 PASS.
- NEVER silently weaken the frozen C4.17 universe, PRICE, DV30, MC, HISTORY, weekly, risk/R/R or event rules.
- No orders, positions/balance query, live brokerage integration, account access, paid upgrade or synthetic bar/fill.

## Remediation order and required end-to-end release proof

**P0 — MC:** Test a legitimate permanent-$0 point-in-time market-cap provider within allowed terms and schedule environment, with dated identity+MIC, currency, corporate-action and listing checks on the **exact 514 2026-10-08 PRICE PASS symbols**. Formally version the MC primary source if migrated; frozen C4.17 cannot be reinterpreted implicitly. Full partition must be explicit for each input; no primary access => UNKNOWN, never fake PASS.

**P0 — Recompute 8 October:** After exact-current MC authority and any additional required upstream coverage are available, complete HISTORY >=260 daily / 52 weekly, legal/SEC shell, 4-week weekly rising checks, QQQ/breadth regime, A/B/C/D geometry, cost-adjusted risk & R1/RR, SEC/IR 8-session event gates, exact-source same-ASOF final and terminal. Certify exact symbol-set equality and SHA bindings at every handoff. A genuine `NO_QUALIFIED_SETUP` result is valid only after complete tested coverage.

**P1 — Manual report:** Re-establish event SHA and epoch binding for the new current terminal. The existing `UNBOUND_SOURCE:events` failure is correct for a stale terminal; do NOT bypass verification.

**P1 — Delivery:** Only after a bona fide eligible registered research candidate exists, demonstrate persistent registration/lifecycle, GitHub Issue creation (if selected as delivery sink), dedupe+receipt readback, and separately verify actual user-device notification. Historical or synthetic delivery selftests do not satisfy the receipt criterion.

**P1 — Universe:** Resolve ADR inclusion/exclusion policy conflict with a deliberate versioned change and independent official symbol-type proof, not regex decisions.

**P2 — Root:** Reduce O(N) no-value deferred market-gate retries where possible; preserve source transparency. `HISTORY_PARTIAL` must remain distinct from FULL_COMPLETE and must never trigger green candidate success.

## Immutable snapshot source SHA bindings

- MASTER: `0508f9ae561c471e49ad57f8166852915f948968`.
- PRICE/DV30: `42ed4a1c1a104aff94f73793194b25746d3bea59`.
- Resolver request: `5a4507c0bf0dd9339803c01f4366cdbe89eac015`.
- Resolver chunk manifest: `775dd1aa01f5012cadd5979977ca9547f51ebffa`.
- Same-ASOF settlement witness v1: `521f5e261d51f0193a027e805a2c4f9e9551656b`.
- Full-scope resolver provenance v2: `34a6fbc96acfb7a20651da561ec9f65baeacc665`.
- Historical terminal: `ea9c41cd1e5971e78d85bf3f620d7f8c4e01034f`.
- Historical final-technical: `4d220717a8e8a8f266ef5224ed31e8eb5090e34a`.

**Audit result:** The settlement repair is real; the current production gate is NOT released. No candidate or device notification claimed. This document must be revalidated against later live main; it is not an executable decision artifact.
