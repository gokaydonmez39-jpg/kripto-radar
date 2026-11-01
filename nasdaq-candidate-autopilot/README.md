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

## A45 — Persistent independent issue-only evidence ledger

One `[XRAY NASDAQ] A45 evidence-only source ledger YYYY-MM` GitHub Issue per active month is created when and only when a completed genuine scheduled EOD successfully passes A43 + A44. A separate job uses `issues:write` only for this ledger. The PR/testing job never has issue-write permission. One bounded comment per accepted upstream EOD identifies up to seven sources, their source version where verified, registry hash, receipt SHA256, EOD run SHA and source log digest; no private Google Sheet values, trading signals, credentials, or broker information.

Replaying the same source run with the same digest is idempotent. A replay with inconsistent evidence fails. A closed ledger issue, duplicate ledger issues, mismatched/absent session evidence, missing source registry SHA, unapproved candidate status, external probe failure, or unavailable GitHub API block the write. GitHub Issue comments are durable platform records but are **not** cryptographically immutable or an independent market-data witness.

Two-job execution:
1. A42/A43/A44 candidate admission (`contents:read, actions:read`), on PR/dispatch run synthetic/offline and no ledger writes. On admitted scheduled EOD, real bounded metadata preflight and artifact.
2. A45 issue-only writer (`issues:write`) runs on verified successful scheduled main EOD only, with a dependency on stage 1 and a second exact receipt integrity gate. It reads only the artifact of the same workflow run.

### Limits still open

**No autonomous runtime functional test of third-party code**, no automatic dependence installation, no market-source vendor onboarding, no claimed production integration or alpha/return evidence. No integration PR auto-merge, secrets, public raw bars, new NASDAQ/CRYPTO workflows or orders. The separate A41 GitHub main-branch ruleset still lacks required PR/CI controls; this must be resolved without breaking existing research witness bots before any system-wide promotion authority can be granted.
