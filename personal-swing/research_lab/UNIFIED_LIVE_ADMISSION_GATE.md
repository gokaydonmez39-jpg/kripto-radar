# XRAY NASDAQ GODZILLA Ω — Unified research evidence gate
**2026-11-11 • DRAFT • RESEARCH_ONLY • FULL_FINAL=HOLD**

## Proven software work
PR #435 combines exact code from existing Confidence Lab #429, Three-Layer #430 and Decision Intelligence #431 over the already merged P0 recovery (PR #434). The `unified_evidence_bridge` is a pure function. It does not read Google Sheets, GitHub or IEX itself; it cannot send ChatGPT messages, schedule a task, publish a dashboard, fit a model, modify AL or place an order.

Input must be the **complete authenticated private source** held by the calling service: original 477 ordered watchlist and its SHA, completed XNAS ASOF, exact EOD run and algorithm SHA, full private `TARAMA_KAYITLARI`, `SWING_SKOR_GUNLUK` and month-specific `KRONOS2_YYYY_MM` matrices. The parser validates the content contract but reports `CALLER_WITNESS_NOT_ATTESTED`; it cannot itself attest user identity, first-public-time, or upstream GitHub Action result.

Mandatory binding: unique 477-symbol H1/H5/H12 = 1431 rows; each scored episode must match its own symbol's KRONOS forecast-origin IEX close to within 0.0005005 USD rounding allowance. Every score must preserve actual 0.1-point precision, original STOP / 2R, component bounds, ranked count and independently recomputed producer SHA-256. Changes in a signed forecast row must affect evidence SHA. HOLD_QC records carry no forecast, CLOSE_ONLY is not native OHLC, ambiguous paths are not fills.

## P0/P1 source separation
- Core EOD on ASOF 2026-11-10: 477/477, Guardian/A34/score PASS. Production P0 Cove original scope SHA fix and Kronos stage diagnostics merged in #434 on main.
- KRONOS2_2026_11 private tab **ABSENT** at this review. 10-Nov real V2 run FAIL; next *natural eligible* EOD needed to prove 1431 genuine records.
- Cove 10-Nov live run FAIL; code fixed but new real success required. Cove presently evaluates cohorts, not legitimate per-symbol risk certainty.
- Official Shadow 477 remains SOURCE_REFUSED / authorization and PIT review HOLD. SEC #419 is draft; no first-public-time guarantee. Neither may clear risk.
- Kronos V1 H1 latest evaluation had 14 matured examples and did NOT beat persistence MAE; H5/H12 maturity and proper forward OOS absent. Confidence Lab must remain NO_GO, probability and expected R NULL.
- Private terminal and n8n: synthetic browser/motor tests alone do not enable authenticated hosting or iPhone delivery. Actual system notifications use the existing Ana Merkez only; user-visible ChatGPT result is not OS-level device ACK.
- GitHub required CI ruleset 26024575 still lacks `required_status_checks`. Branch protection must be independently enforced and tested before FULL_FINAL.
- Backup and release of further modules require exact-main comparison, reviewed source changes, approved release scope, all exact-HEAD checks, rollback revision and independent natural EOD readback. Never force-push/replay/backfill.

## Precommitted acceptance (none may be inferred from CI)
1. **CORE** original 477 exactly once; FINAL_READY true; 1 SUMMARY + unique N EPISODE; Guardian and A34 exact ASOF.
2. **KRONOS V2** 1431 distinct valid same-ASOF H1/H5/H12 rows with pinned model revisions and independent original private Sheet GET readback. Distinguish RESEARCH_ONLY, RESEARCH_CLOSE_ONLY and HOLD_QC.
3. **COVE** independent original-order PIT SHA and Flight Recorder readback. No inferred fills, model gains or per-symbol certainty.
4. **DISPLAY/DECISION** private caller authentication and data access control; no private rows/logs in public CI; forecasts never authority over original AL/STOP/2R; no copied SHA without recomputation.
5. **NOTIFICATIONS** unique-event atomic reservation and GET readback; device ACK separately UNKNOWN until actually proven. No repeat for 11-Nov 08:59 delivered intents.
6. **SCHEDULE** verify real primary and fallback timing across 20 consecutive natural XNAS sessions; a synthetic second cron slot (#433) is NOT proof GitHub will fire it, and increases quota/duplicate risk.
7. **PERFORMANCE** prospective OOS and walk-forward; baseline persistence and buy-and-hold where applicable, cost/slippage and censoring, min 60 forward sessions before any claim of alpha; no automatic strategy self-modification.
8. **GOVERNANCE** GitHub ruleset, service licensing, data rights and API budget verified; manual rollback route tested without destructive force updates.

HOLD any failure; preserve immutable source data and the working core; no real orders, no fees, no crypto coupling.

## Test and rollback contract
Run Research Lab normal + `-O`, browser/n8n synthetic smoke, mandatory NASDAQ Required CI, private EOD PR guards and SEC no-data privacy tests. If any FAIL: do not merge this DRAFT; correct in branch with RED/GREEN. If a future reviewed release fails in production, revert only its reviewed source commit through a new checked PR, keeping prior Sheet rows intact. Never modify historical ASOF to manufacture continuity.
