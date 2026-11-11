# XRAY NASDAQ GODZILLA Ω — P0 recovery admission gate (2026-11-11)
**Status: HOLD. Draft PR #432, main unchanged by this PR. Research-only.**

## Current independently checked baseline
- Personal-477 official 2026-11-10 EOD: 477/477, zero missing, FINAL_READY TRUE; source run 42948281135; full scan, follow-up, Guardian, daily score and A34 completed successfully
- 25 scored active episodes; 10-Nov score content SHA independently recomputed from ranks, score floats, risk tags and last closes and matched the immutable SUMMARY value
- ChatGPT Ana Merkez reserved the two new events and the daily score at 2026-11-11 08:59 TRT. Private event/digest readback matches screenshot; pending=0. This means REQUESTED intent and user-visible ChatGPT content; not OS-level push telemetry or actual broker fills
- 10-Nov real Kronos V2 run 42948529845 failed; no V2 month partition yet. Cove 42948529890 failed; both remain LIVE HOLD. Offline green is NOT a live acceptance
- Source root cause found in Cove: EOD scope SHA uses original ordered 477 personal PIT symbols, whereas its consumer sorted the same symbols before hashing; #432 separates original-order SHA from compute order. Independent regression RED -> GREEN
- Kronos V2 had opaque public error `KRONOS2_UNCLASSIFIED`; #432 adds static diagnostic stages and a strict code allowlist, with seeded exception leak RED -> GREEN. Exact real failure stage remains UNKNOWN until the NEXT NATURAL eligible EOD

## No permission implied for production release
**Do not mark PR ready / merge, dispatch, rerun, backfill, rewrite ledgers, add paid resources, alter schedules, change AL/STOP/2R, send events or enable orders on the basis of offline CI alone.** The user's explicit approval is required before production merge or any irreversible access/control change. The separate crypto radar is out of scope.

## Mandatory source and acceptance order
1. Re-read latest main SHA, approved branch tip, full patch, GitHub ruleset, source SHA and 477 PIT order; preserve pre-merge main SHA for a reversible revert PR (never force-push)
2. All exact-HEAD CI workflows for #432 must complete SUCCESS; a skipped LIVE job is not proof of live acceptance. Check conflicts from independent research PRs #419, #429, #430, #431 and fallback #433
3. At the NEXT genuine complete XNAS session after an explicitly approved merge, use ONLY the original natural schedule run. Do not dispatch to make tests green and do not replay 9/10 Nov
4. Core admission: 477 unique / 477 valid / zero missing / FINAL_READY TRUE, genuine source run and immutable scope+algorithm SHA; Guardian, corporate terminal custody, episode lifecycle, A34, 1 SUMMARY and N EPISODE unique rank/score rows with a recomputed content SHA. No change to technical AL, bracket or 15-XNAS lifecycle rules
5. Kronos V2: verify full 477×(H1,H5,H12)=1431 same-ASOF unique original forecast records in the private KRONOS2_YYYY_MM tab, pinned model/tokenizer/code, full SHA and readback. HOLD_QC and CLOSE_ONLY remain separate; do not manufacture native OHLC. If failed, use the new allowlisted stage code (and no private exception text) to isolate source, model or Sheet stage; keep FULL_FINAL HOLD
6. Cove: verify same original PIT scope SHA as official EOD, independent readback/Flight Recorder, correct theoretical gap/dual-touch/cost bounds, no real fill or per-symbol confidence inference. A failed read must not block successful core EOD
7. Notifications: never resend already REQUESTED events or the 10-Nov score. For future unique events require original source, independent acceptance, single atomic reservation and GET readback. ChatGPT user-visible message != device OS delivery
8. Fallback: #433 is separate and remains draft. A second safe cron window has offline test evidence but cannot guarantee GitHub scheduler delivery. Account for added Actions usage and require explicit deployment approval. Keep NO_REPLAY/NO_BACKFILL and the original 10h boundary
9. Source/rights/governance: SEC #419 contact/authorized PIT remains HOLD, ruleset 26024575 lacks actual required-status-check enforcement, model calibration/OOS and 20-session forward continuity remain future gates. No automatic model self-modification
10. For ANY new mismatch: mark corresponding research source HOLD, keep independent core intact, preserve original logs and ledger, file a corrective draft PR and require RED/GREEN plus next natural source readback before reconsidering

## Predeclared terminal gate
FULL_FINAL may be considered only when all source, identity, workflow, independent readback, scheduling, notification and scientific acceptance gates have empirical evidence. This document is an operational review checklist, not authorization, release, monitoring automation or live result.
