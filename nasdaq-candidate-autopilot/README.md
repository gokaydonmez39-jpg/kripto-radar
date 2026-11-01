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
