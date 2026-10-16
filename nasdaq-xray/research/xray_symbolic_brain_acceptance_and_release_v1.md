# XRAY symbolic cognitive control plane — staged acceptance (2026-10-16)

Status: **DRAFT / NOT MERGED / NO PRODUCTION ALPHA**.
This is a nontrading research-memory add-on, not a replacement for C4.17.

## Confirmed starting conditions

- GitHub main baseline: `3e8b4dac25b636e74e4bdea1896a3ed108a9ac6e`.
- Canonical durable state pointer revision 78, with separate operational checkpoint memory.
- Official PIT evidence ledger has 133 snapshots at baseline (2026-10-16T15:02:10Z).
- Canonical candidate lifecycle registry contains zero rows and was ASOF 2026-10-07.
- Existing alpha calibration: zero comparable full C4.17 sessions, minimum examination target 60.
- Canonical terminal ASOF 2026-10-07, PARTIAL_UNKNOWN; non-final.
- Confirmed acceptance artifact: GitHub Actions run `38903464178`, ASOF 2026-10-15, research A/B/D watch 14 from 416 partial-research cohort, not full 3189-symbol technical proof.
- Existing two ChatGPT tasks continue; no new scheduled task. No broker use, order, paid fallback, source-rights bypass or fake device ACK.

## Dependency chain and release authority

1. **Receipt truth**: `personal_research_operations_acceptance.py` binds exact three source artifacts and symbol/source digests, status research only.
2. **Admission**: `research_candidate_memory_admission.py` requires completed SUCCESS of the exact main-branch acceptance workflow and exact named, unexpired GitHub Actions artifact from the same run. Caller must fetch both using authenticated GitHub API and artifact download; synthetic JSON passed by an untrusted caller is NOT authentication.
3. **Memory**: `research_candidate_memory.py` accepts a validated symbolic receipt, exact WATCH membership SHA, A/B/D family lists and per-ASOF run IDs. Produces append-only hash-linked replayable ledger proposals with semantic transitions, monotonic ASOF, idempotence and same-ASOF revision quarantine. A missing later WATCH is **not** an invalidated trade.
4. **Durable storage**: isolate state in branch `xray-research-memory-state`, file `nasdaq-xray/research/symbolic_candidate_memory_ledger_v1.json`. The branch contains an empty, noncanonical seed. `research_candidate_memory_cas.py` double-reads this file, validates its actual Git blob SHA, requires source re-authentication, uses one GitHub Contents API SHA-CAS write and exact readback; no force-push and never writes to main.
5. **Activation**: default OFF. Opt-in CAS job runs only on completed successful main acceptance `workflow_run` AND repository Actions variable `XRAY_MEMORY_PERSIST_APPROVED` exactly equals `true`, **AND** repository Actions variable `XRAY_MEMORY_RELEASE_COMMIT_SHA` matches the exact `github.sha` of the verified main workflow code, following explicit owner release approval. Any different new main revision automatically disables the writer. A separate source event run ID must also match. Otherwise job is skipped. It is **not** activated by opening a draft PR.
6. **Outcome diagnostics**: `research_candidate_outcome_audit.py` uses authorized private point-in-time adjusted closes, **same-ASOF stock and benchmark reference sessions**, independent NASDAQ calendar, split/corporate action status, issuer-class identity and authorized benchmark. Its 1/3/5/10/20 session horizon values are post-observation **close moves**, NOT executable P&L, nor backtest proof; insufficient source = UNKNOWN. Raw price bars never written to output.

## Production-stopper checklist

- Until owner explicitly approves merging PR #72 and enabling the opt-in variable, **NO deployment / no persist job**.
- Do not mark `AL` or `R92` from this shadow data, never update C4.17 policy or its PRICE/DV30/MC/G9 hard gates.
- No historical replay from mere commit date: episode decisions need independently authenticated `decision_available_at_utc`, original immutable decision SHA, issuer share-class, lawful derived metrics rights, actual completed future bars and a full delisted universe. Current outcome audit explicitly does **not** authenticate these external attestations and reports `backtest_proven=false`.
- A new outcome score or model cannot be released with zero comparable C4.17 samples. At least 60 valid C4.17 sessions is only the *first review trigger*, not statistical sufficiency.
- GitHub 14-day Actions artifacts are **not permanent storage**; the distinct research state branch carries the append-only retained symbolic ledger after an authorized activation.
- Code today safeguards a whole-file ledger up to 512 KiB. A future sharded ledger migration must be reviewed before this limit, not silently truncate.
- A same-ASOF reissued receipt with a new digest stops with manual reconciliation. An upload failure or branch CAS collision keeps the previous immutable state. Never overwrite or retry blindly.
- `run` SUCCESS proves job execution, never full NASDAQ scan, G9 entitlement, issuer-class MC, or device delivery.

## Recovery / rollback

- On any source SHA drift, CAS collision, illegal provider input, bad adjustment, missing future bar or invalid run, **fail closed**. Do not generate a synthetic replacement and do not modify canonical files.
- Disable either repository opt-in variable to suspend persistence; the two existing ChatGPT tasks need no changes.
- Keep `xray-research-memory-state` immutable Git history as rollback evidence. If a bad ledger revision is detected, freeze writes, save the last known-good Git commit and conduct a branch-copy forensic reconciliation with a separate PR. Do not force-push over evidence.
- Rolling back PR code is separately reviewable and does not imply removing historical evidence. No trade/account rollback is necessary because none can be made by this layer.

## Independent acceptance metrics (prospective, not achieved results)

| Criterion | Required verification |
| --- | --- |
| Unauthorized accepted source | 0 successful adversarial forgeries |
| Duplicate event / identical receipt | 0 new entries |
| Same-ASOF source revision | always quarantine / no write |
| Broken ledger source / hash chain | always block |
| Unknown / incomplete horizon | never finite return or win-rate |
| Correct reported current source session | exact Nasdaq completed EOD ASOF |
| Notification or Alpha promotion | strictly false in this component |
| Cost per accepted EOD receipt | zero extra paid market-data calls |
| Research predictive advantage | UNPROVEN until rights-safe prospective walk-forward cohort, matched NASDAQ/QQQ benchmark and beta, costs, confidence intervals, delistings, negative signals and sample-size examination |
| iPhone ACK | no assertion without independent platform/device receipt |

## Future milestones not quietly marked done

- Formal immutable capture of the *original observation time* and exact issuer/share-class identity in the trusted producer (not an operator-filled label).
- Authorized corporate-action adjusted forward-data ingress, historical universe/delisting proof, the 1–20-session label registry and purged/embargoed walk-forward comparison.
- Explicit definition of positive/negative outcomes before evaluation; only then precision, recall, Brier score, calibration and false-positive/false-negative testing.
- Causal incident/provider budget ledger with independently measured redundant-call savings, source-error cooldown and no auth/credit-cliff retry.
- Production-readback tests only **after** owner-controlled opt-in activation. Shadow CI PASS alone does not satisfy this last milestone.

## Final merge-vs-release control

Merging the research-only code/CI into `main` is **not** an approval to write candidate memory: the SHA-pinned two-variable CAS writer remains disabled. Merge tests and read-only preflight can run as independent Actions without new paid providers. No one can treat a passing synthetic fixture as authenticated forward performance. 
