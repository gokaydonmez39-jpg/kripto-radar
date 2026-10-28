# A12 — Independent Private NASDAQ Performance Research Gate

Status: **draft, shadow, not deployed**. This stacked research PR depends on A11 PR #286.

## Operating contract

The existing personal NASDAQ 477-stock Alpaca IEX EOD scan, official XNAS calendar, private Google Sheets and original fifteen-session candidate tracker are immutable. This bridge uses the existing data-only market reader and requests a Google Sheets **read-only** OAuth scope. It never writes any spreadsheet rows, creates broker orders, modifies signal thresholds, sends notifications or changes other radar systems.

The bridge checks exact 477 FINAL scan coverage and source/policy fingerprints, historical signal issuance provenance, immutable original price/stop/target levels, consecutive official XNAS sessions and signal-day provider close. It independently recalculates every verified candidate with the original tracker, compares status and signed theoretical outcome with the private sheet, then invokes A11's separately costed *hypothetical* next-open performance observer. Full-cohort research stays HOLD if manual historical signals lack provenance. Anomalies fail closed, not silently repaired.

On PR, synthetic CI tests run without secrets. A separate future workflow_run path can observe completed successful original EOD runs **only after explicit reviewed deployment**. Its special private environment is intentional; missing environment or secrets must not be bypassed just to get a green check. Public logs include only aggregate counters and hold/block states, no symbols, prices, private sheet identifiers or tokens.

## Independent release gates

1. All ordinary and optimized synthetic CI tests pass with no regressions.
2. The existing main branch receives branch/ruleset protections and a reviewed private environment before any trusted workflow with credentials becomes active.
3. Independent private end-to-end trial proves authentic Sheets + IEX readback and private telemetry without candidate leakage.
4. Historical issuance attribution, corporate actions, IEX venue limitations, delayed/missing sessions and dual-touch ambiguity are independently audited.
5. Prospectively registered holdout, matched market/regime baseline, robust trade cost assumptions, multiple-comparison control and meaningful sample size are established.
6. Any challenger recommendation requires separate review; production AL changes and real orders are not authorized.
7. Existing single ChatGPT iPhone alert task remains unchanged; delivery is not asserted by GitHub.

CI success means **synthetic implementation tests PASS**, not trading performance PASS. Full live learning and any deployment require additional evidence; until then **HOLD**.
