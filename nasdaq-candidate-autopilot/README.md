# XRAY NASDAQ A42 — Candidate Intake Autopilot

**Scope:** NASDAQ research only. This is autonomous **intake and evidence collection**, not autonomous trading or production integration.

- Frozen user inventory: all **284** deduplicated candidate records in `registry.json` (source-snapshot, no silent replacements).
- Priority: seven P1 engineering candidates first, then P0 existing-core verification, P1 validation, P2 shadow, P2 backlog; **HOLD/HOLD-SEPARATE are excluded**. At most seven candidates per daily eligible run, **36 weekday cohorts**.
- Preflight: schema, unique IDs 1–284, exact tier counts, HTTPS scheme, scope separation, deterministic SHA-256 receipt, missing provenance and malicious URL tests.
- On verified successful **scheduled** personal 477 EOD `workflow_run`, anonymous bounded **public github.com HEAD** link checks; **no redirects, scripts, third-party execution, private keys, account API data, or new cron**.
- On PR/manual dispatch, strictly offline metadata preflight. Both normal and optimized Python tests run via GitHub Actions; artifact `xray-a42-readonly-candidate-receipt` retained 30 days.
- No changes to `personal-swing/`, private Google Sheets, notifications, existing 477 decision algorithm, NASDAQ production workflow, or any CRYPTO path.

## Explicit limits

The receipt always labels each candidate `NOT_INTEGRATED`. An `HTTP_2XX` result proves **only** that the public URL returned a 2xx response; not license, trusted ownership, safe execution, benchmark improvement, PIT validity, alpha or runtime compatibility.

**Promotion requires a separate candidate-specific change:** verifiable upstream tag/SHA + license and dependencies, independent functional test with a frozen baseline, adversarial tests, shadow comparison, sample-out/walk-forward where applicable, CI, protected PR approval, production post-deploy readback and revert plan. No automatic approval/merge of production adapters in A42.

**Consequence:** Merging A42 alone enables the autonomous, low-risk intake loop but **does not** deliver fully autonomous package installation or end-to-end production integration. A43+ must add secure candidate-specific adapter generators and independently verifiable performance gates before that larger objective can be claimed.

### Local (offline) run

```sh
python -m unittest discover -s nasdaq-candidate-autopilot -p 'test_*.py' -q
python -O -m unittest discover -s nasdaq-candidate-autopilot -p 'test_*.py' -q
python nasdaq-candidate-autopilot/autopilot.py --date 2026-11-02 --output /tmp/a42-receipt.json
```

The initial HEAD-probe mode uses `--network` for seven allowlisted public GitHub candidate URLs; all other URLs remain `SKIPPED_EXTERNAL_OR_UNSAFE_HOST`.


## A43 additional fail-closed source EOD admission

In production `workflow_run` mode A42 must not mistake a successful but **empty/skip-only** EOD workflow for a verified 477-personal EOD scan. A43 now calls `eod_admission.py` **before** any URL probe, via GitHub CLI `gh run view RUN_ID --log` and scoped `actions:read` only.

The gate independently demands: exact repository/workflow/main/scheduled-success identity; a timestamped 477/477/0-final-ready raw EOD source witness with SHA-256 fingerprints; completed IEX-to-Sheet handoff; exact matching as-of date across private Sheet, lifecycle and PANEL readback markers; authenticated Sheet preflight; and NY-local session-date parity. A non-compliant run fails closed without ever invoking the candidate probe. A successful result writes a separate **sanitized** A43 artifact containing proof SHA, no source logs and no private candidate data.

GitHub log receipts are supporting evidence, **not cryptographic proof of the upstream external Sheet**. Full live readback still requires independent Google Sheets inspection. If the default-branch source workflow changes its log format or a GitHub runner cannot access logs, A43 deliberately blocks intake; it never resumes automatically by weakening the check. This is an availability-vs-integrity tradeoff.

All A43 changes remain inside the A42 research-only directory and its one workflow. GitHub PR CI exercises normal/optimized synthetic positive and adversarial tests. No live source verification has occurred until a future scheduled 477 EOD triggers the actual `workflow_run` path.


## A44 — Bounded source provenance and license triage

After A43 admits the parent EOD, A44 checks at most **seven** candidate sources. It resolves HTTPS `github.com/owner/repo` candidates through the official GitHub REST API, independently checks public repository identity, archived/fork/disabled flags, machine-readable license identifier, and a 40-character exact source commit SHA. No upstream code is fetched, installed or executed. Recognized permissive license **tags are not license approvals**, and provenance pass means only `PROVENANCE_RECORDED_TEST_REQUIRED`. Unknown, AGPL/GPL, archived, fork, stale identity and unsupported non-GitHub URLs are held or marked for manual provenance. External authority URLs remain in the complete 284 registry; do not substitute GitHub URLs.

Failure or timeouts never silently promote a candidate. `assessment.py` uses capped HTTPS response size, no redirects, strict URL/hostname rules and only GitHub API GET. No paid API, new cron, account secrets or candidate-controlled shell commands.

## A45 — Read-only rolling artifact ledger (security contract preserved)

**Critical fail-first (2026-11-01):** The first A45 version requested \`issues:write\` and caused the repository's independent preopen source audit to fail with \`UNAUTHORIZED_ISSUE_WRITE_PRIVILEGE:nasdaq-a42-candidate-autopilot.yml\`. The pre-existing user policy explicitly disallows any new GitHub Issues, issue writers or issue-driven user notifications. The guard is correct and is NOT weakened. A45 is now replaced with a read-only rolling artifact ledger; no GitHub Issue is created.

After the A42/A43/A44 job confirms the genuine scheduled EOD and uploads bounded candidate receipts, a separate \`contents:read, actions:read\` job downloads the current run's **own** A42/A43/A44 artifact and the latest available previously published \`xray-a45-rolling-state\` artifact. \`ledger.py\` independently checks exact 477-EOD, Sheet, lifecycle, PANEL, ASOF, registry and source-receipt SHA evidence and either admits one new source-run epoch or idempotently ignores the same digest. A conflicting replay is blocked. One encrypted-in-transit but **public repository workflow artifact** is emitted; it contains only 284-candidate public metadata, SHA digests, status and source epoch, never private Sheets contents or signal details. No candidate source is installed or promoted.

**Retention limitation:** GitHub Actions artifact retention is set to **30 days**, and the rolling snapshot is renewed by each admitted EOD. If no successful run occurs for longer than the retention period, the previous snapshot may be lost: bootstrap explicitly declares \`history_continuity=UNATTESTED_FIRST_OR_EXPIRED_ARTIFACT\`. This is renewable operational continuity, **not immutable, indefinite archival**. The separate 284-entry Git-tracked registry remains versioned. To achieve indefinite archival later, add a separately authorized non-Issue persistence mechanism and its independent readback.

The \`all_workflow_schedule_audit.py --selftest\` is now included in candidate CI; any new \`issues:write\` scope or unreviewed cron must fail before merge. This is a security regression and automated self-diagnosis guard, not automatic loosening of a policy.

### Limits still open

**No autonomous runtime functional test of third-party code**, no automatic dependence installation, no market-source vendor onboarding, no claimed production integration or alpha/return evidence. No integration PR auto-merge, secrets, public raw bars, new NASDAQ/CRYPTO workflows or orders. The separate A41 GitHub main-branch ruleset still lacks required PR/CI controls; this must be resolved without breaking existing research witness bots before any system-wide promotion authority can be granted.


## A46 — Ledger-driven adaptive candidate progression

A42's historical weekday-index cohort rotation could silently skip a page on official XNAS holidays or a failed producer run. A46 replaces **the live workflow_run selection** with \`candidate_queue.py\` reading the most recent A45 rolling artifact and the exact 284-item registry hash. Workload is **seven candidates per successful evidenced source EOD**, not per calendar weekday; **249 eligible IDs can therefore be observed in 36 successful distinct source epochs** (the last cohort has four new IDs). The original 12 A42 date-rotation tests remain for isolated offline replay compatibility, but the real scheduled path uses the A46 ledger queue.

- First: P1 engineering (7), then P0 existing-core verification, P1 validation, P2 shadow and P2 backlog, exact registry-ID tie-break. 35 HOLD/HOLD-SEPARATE records never selected.
- Next: inspect the first unseen IDs, regardless of missing exchange sessions or GitHub scheduler delays.
- Then: bounded rechecks for \`SOURCE_PROBE_UNKNOWN\` and \`SOURCE_PROVENANCE_UNKNOWN\` with fewer than three observations, followed by oldest-record periodic provenance rechecks; no upgrade on merely repeated successful URL/provenance probes.
- Fail closed if the source-run ID is already in A45's accepted epochs, the prior ledger belongs to another registry SHA, any prior source is marked integrated, or dates are stale/unstable.
- A42 receipt validates the A46 queue SHA, selection IDs and asof; A45 independently requires exact A42/A44/A46 source ID parity and A43 matching source epoch.
- The 30-day artifact expiry caveat remains: if the prior state is lost, a first-cohort recovery restarts with an **unattested** history label; the system cannot claim proof of uninterrupted progress.

GitHub Actions has no extra cron, no Issue writer, no candidate code install/execute, no auto-merge, and no changes in \`personal-swing/\`, Google Sheets or XRAY CRYPTO. The A46 workflow_run path needs actual GitHub Actions read access to find and download the previous A45 artifact; this network dependency has **not** been verified in a live EOD until the next eligible source run.
