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
