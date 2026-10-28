# XRAY PERSONAL NASDAQ 477 — A20 FINAL START CONTRACT (2026-10-28)

**Scope:** the 477-stock personal NASDAQ IEX single-exchange daily technical radar only. Cryptocurrency signals and all other NASDAQ research/risk workflows are independent. No broker endpoints, execution, orders, account changes or purchases. Existing EOD scheduler, lifecycle reader, iPhone notification task, threshold/stop/target rules, 477 watchlist and current Sheets rows are unchanged. This is a one-time GitHub *metadata-only* START attestation, not a newly scheduled monitor.

## Two release decisions — never conflate them

1. **Operational START:** ARMED only if the protected main branch, force-push/deletion prevention, real successfully completed EOD -> event-driven A14 chain sharing the originating SHA, authenticated private-source readback, verified separate Resilience recovery, and EOD/A14 required GitHub jobs all have independent evidence. The A20 CLI re-reads those specific actual public GitHub run IDs and job status from the repository. A successful normal EOD no-op *before* the current US market close verifies event wiring, **not** a fresh 477-market-data scan. All results are dated **one-time historical checks**, not future-session attestations.
2. **Statistical alpha / strategy improvement:** **HOLD / NO-GO**, independent of operational START, until sufficient **mature** and genuine 15-session outcomes, original issuance hashes, gap/missing-data checks, controlled benchmark, genuine unobserved preregistered holdout, negative controls, corporate-action consistency, actual transaction-cost and tradability evidence, and explicit human approval. Current private cohort's last confirmed observed state: **6 open, 0 complete, 3 source/policy SHA-matched, 3 historical SHA-incomplete** (as of completed XNAS 2026-10-27); no real fills or device receipts proved. Model parameter / AL-rule auto-promotion is **disabled**. A green synthetic test or GitHub SUCCESS is not alpha proof.

## 16-scientist *methodology* review (not endorsement or claims of complete implementation)

| Lens | Falsifiable controls or required evidence | Present verdict |
| --- | --- | --- |
| Einstein | Distinguish data-origin failures from strategy failure before hypothesis | Designed; causal attribution not independently verified |
| Euler | Exact 477 symbols, bounded 10-symbol EOD batches and original 15-day window | Implemented; current EOD full scan 2026-10-27 independently verified |
| Gauss | Missing days, confidence, day-cluster bootstrap, uncertainty, power | A11 theoretical calculation; real cohort underpowered |
| Newton | Dated EOD and A14 job results, not narrative assertions | Confirmed 2026-10-28 real GH event chain |
| Leibniz | Original policy and scope SHA, immutable stop/target, no duplicate episodes | Code/negative tests and private readback; some early issuance SHA unverified |
| Turing | Normal and Python -O fail-closed deterministic tests | A11-A13 and A20 CI; not a formal proof |
| Shannon | Unconsolidated IEX signal/noise and no SIP claim | Source identified; predictive edge NOT proved |
| Bayes | Beta posterior only after mature real outcomes | Mechanism in A11; no meaningful posterior alpha evidence yet |
| Popper | Negative fixtures, falsifiers and null effect challengers | A11/A12/A13 negative tests; genuine forward rejection pending |
| Feynman | Explicit EOD -> private A14 -> scientific scorecard trace | Functional source path; no executed broker path |
| Lamport | Same source SHA and ordered GitHub workflow_run; private idempotency | GitHub source chain observed; phone delivery acknowledgement not proved |
| Deming | Repeated readback, regression/metadata/CI monitoring | Current pipeline tested; future EOD observation still pending |
| Kahneman | No profitability, true device receipt, or completion claim from green CI | Hard-coded independent HOLD and NO-GO |
| Thorp | Fixed close-referenced stop/2R target; separate theoretical vs fill and assumed costs | A11 theory only, not executed fills |
| Simons | Frozen preregistration, cohort matching, OOS benchmark | A13 proposed; real temporal holdout evidence absent |
| Taleb | Opening gaps, intraday stop-first ambiguity, left-tail diagnostics | A11 safeguards; real stress/fill adequacy NOT proved |

## Verified history pinned by A20 (immutable initial START snapshot)

- 477 EOD controlled event: GitHub run **40668287074**, event push, success, *pre-market no-op*, main SHA `d502830533a25a72e45d2476531668623685fa37`.
- Real triggered A14: run **40668438065**, event workflow_run, success, same SHA. Private reader returned `SKIPPED_NO_COMPLETED_CURRENT_XNAS_SESSION_NO_DATA_USED`, correctly not promoting an unfinished trading day.
- Real IEX + Google Sheets private historical readback: run **40667234654**, success, 3 verified SHA-linked historical candidate episodes, 3 SHA-unproven, none matured.
- Resilience failed GH013 before protection adjustment; successful retry attempt 2: run **40660732531**.
- Current main protection ruleset **26024575**: active deletion + force-push protection. PR-required main protection was removed to let existing scheduled operational safety witness commits persist; that removal is a **known reduced change-control guarantee**, not equivalent to mandatory human reviewed PRs. Future migration to PR-based automation needs a separate tested architecture.
- The existing personal user notification task is enabled on the existing hourly `:57` check; A20 does **not** claim phone push or delivered alert.

## Acceptance, next session, and prohibitions

- A20's `START_ARMED` means **personal research radar already active and its plumbing validated**. It does **not** launch a new broker process, add another schedule, force a duplicate scan, re-write private Sheets, or create another ChatGPT notification task.
- At the next *actual* Nasdaq EOD (close +45min), only the existing `xray-personal-477-eod.yml` schedule may execute the 477 scan, and its successful `workflow_run` should invoke A14. The 28 Oct 2026 post-close data evidence **cannot** be observed before the market completes. Missing/partial price or private readback => status HOLD; never make up signals.
- A20 uses public GitHub Actions metadata only, with `contents:read` and `actions:read` scope, no secrets except ephemeral built-in GitHub action token, and no vendor/Sheet API. It exits nonzero if metadata is unavailable or mismatched.
- No unconditional historical success claims or autonomous scientific challenger promotion. This is a snapshot with explicit as-of, not a monitor that remains accurate forever.
