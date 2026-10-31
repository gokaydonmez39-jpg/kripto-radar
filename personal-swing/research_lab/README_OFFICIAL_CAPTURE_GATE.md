# XRAY NASDAQ — raw official source capture evidence gate (research only)

This change extends PR #320/#321 with a **zero-network, zero-output-authority** validation layer for externally captured SEC JSON, Nasdaq halt XML, and Nasdaq Symbol Directory text. Alpaca remains under its separate grouped connector sample audit. The gate is NOT a live collector, not a provider-origin attestation and not a completeness/PIT certificate.

## Boundary and invariants

- READ ONLY. No new scheduled task, network or broker access, API key, paid feed, Sheets mutation, push, notification, order, stop/2R or AL modification.
- Never write provider payloads, company records, private sheet data or headers to public GitHub. Only synthetic test inputs belong here.
- Independent collector must retain source URL, final URL, HTTP status, media type, observed UTC timestamp, exact decoded raw bytes and SHA256, an independently fixed ticker and SEC CIK, and an explicit as-of cutoff.
- The envelope's fields are **self-reported**. Even if hash and parser checks pass, real HTTP origin and first-public-availability remain **UNPROVEN**. SHA only checks byte consistency against a supplied digest.
- The gate requires HTTP 200, exact allowed HTTPS URL with no redirect, strict base64/UTF-8, a coherent body length, a SHA256 match and accepted media type. 403/429/206, invalid or duplicate-key JSON, bad XML, DTD and mismatched CIK refuse.
- Nasdaq RSS official page advises no more than one request per minute; the gate performs **zero requests**. A separately authorized collector must obey the provider's terms and frequency limits.
- Nasdaq Directory is **current snapshot only**, not point-in-time listing history. Its footer is ET; the gate calculates source age using America/New_York. Over 72 hours is marked STALE (not clearance). 72h is a conservative laboratory threshold, **not a trading-day acceptance policy** and may overflag holidays.
- Empty SEC/RSS responses cannot establish no material risk. No automatic CLEAR, AL, order, alert, mobile delivery or sheet sync is permitted.

## Programmatic audit (externally supplied bytes only)

Call `audit_capture(capture, source="SEC_EDGAR", ticker="AAPL", cik="0000320193", asof_utc="YYYY-MM-DDTHH:MM:SSZ")` from `official_source_evidence_gate.py`. Other known source keys are `NASDAQ_HALTS` and `NASDAQ_DIRECTORY` (omit CIK for those). Required capture dictionary keys: `source`, `method=GET`, `request_url`, `final_url`, `status_code`, `content_type`, `content_encoding=identity`, `body_base64`, `body_bytes`, `body_sha256`, `observed_at_utc`.

Passing returns `FORMAT_REVIEW_ONLY_ORIGIN_NOT_ATTESTED` or, for a stale directory, `STALE_SNAPSHOT_NOT_ACCEPTED`. Neither is live acceptance. Body bytes are not returned; no payload is logged by the gate.

## Test and rollback

A11 offline CI executes normal and optimized `test_official_source_evidence_gate` suites. No production runner imports this module. Rollback is simply not merging this draft PR, or reverting its research files and the one A11 CI addition; historical Sheets and alerts remain unchanged.

### Not yet achieved

A rights-compliant live read of original SEC JSON, Nasdaq RSS XML, and current Symbol Directory bytes, independently attested origin and capture timestamp, publication-vs-acceptance PIT analysis, and complete event coverage all remain **NOT PROVEN**. Do not promote a synthetic PASS to production clearance.


## PR-only live HTTP probe (no production integration)

`official_nasdaq_live_probe.py` makes exactly **one** HTTPS GET to the current Nasdaq Halt RSS and **one** GET to the Nasdaq-listed directory per invocation, after a 65-second CI pacing delay. The separate `xray-nasdaq-official-one-shot.yml` job runs only after an explicit PR label event (`xray-official-source-once`) or an explicit manual workflow dispatch where available, not on ordinary PR updates, commits, or a schedule. It has read-only repository permissions and no secrets. The existing A11 suite remains strictly offline.

Only these values may appear in public CI logs: fixed source label, research-only status, HTTP status or error type, byte count, SHA256, observation timestamp, parser acceptance status and directory-staleness flag. No raw XML/text, issuer events, private Sheet records, request cookies, provider headers or secrets are printed. SEC is explicitly **SKIPPED**: official fair-access guidance requires an actual declared user agent including a contact; none is invented or requested by the public PR.

A green workflow means the diagnostic code ran, **not** that source data passed. Inspect individual source states; HTTP refusal, parse refusal and stale directory remain `UNKNOWN/NOT_CLEAR`. Even a 200/parse success is only a live snapshot format observation, with no comprehensive feed-coverage or PIT proof.

GitHub public standard hosted runner pricing is described in their official Actions billing documentation; account charges for unrelated services have not been audited. This workflow uses `ubuntu-latest` only. A draft PR avoids production changes and rollback requires no historical mutation.

### Existing 477-symbol snapshot cross-check

The one-shot directory probe now compares its validated raw directory snapshot to the existing public `personal-swing/nasdaq_watchlist_477.json` file (exactly 477 unique source symbols). Only aggregate counts of currently matching basic directory flags, missing symbols and flagged rows, plus a scope SHA256, are written in the diagnostic log. No symbol names, historical membership conclusions, user alerts, AL results or private candidate data are published. All 477 flags are historical-PIT **UNPROVEN**. A stale or refused directory cannot produce a 477 snapshot comparison. No new securities are added or removed.


## SEC and Alpaca contract repair — 2026-10-31

1. **SEC recent row bound correction:** SEC's official API guarantees at least one year *or* 1,000 filings, whichever is greater. The previous synthetic reader hard-refused valid 1,001+ row documents. The research-only parser now supports up to 20,000 rows as a conservative local memory bound (not a provider guarantee). Regression tests require 1,001 valid rows pass without granting PIT or history completeness, while 20,001 rows fail closed. Extra history indicated by `filings.files` is explicitly counted, not loaded or represented as complete.
2. **SEC acceptance timestamp:** `acceptanceDateTime`, even if a `Z` suffix is present, is not independently proven as an exact public availability timestamp. The result explicitly exposes `acceptance_utc_independently_crosschecked=false` and `filing_history_exhaustiveness_proven=false`. The SEC webmaster FAQ states the **first-public-availability timestamp is not available** in the EDGAR header. No automatic historical signal chronology or preopen inference.
3. **Alpaca grouped connected-app output:** An externally supplied nonempty `next_page_token` now refuses processing. A missing or null token **never** attests complete vendor pagination because the connector is not the raw HTTP response. Expose whether pagination and data-quality options were present, whether returned process-date order matches the requested sort, and that default complete quality may omit early incomplete actions. An unknown region/quality value fails closed.
4. **No secret, no new data collection:** The current SEC API probe stays disabled until an authentic contact-bearing declared User-Agent exists. Do not place a personal email in a public workflow, commit, PR description, log, or screenshot. SEC JSON access and company-specific historical completeness remain unproven.
5. **Invariant:** No trade signal, AL rule, universe, STOP, 2R, Sheets, iPhone notification, broker, execution, cron, secret, fee or crypto workflow change.

References: https://www.sec.gov/search-filings/edgar-application-programming-interfaces ; https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data ; https://docs.alpaca.markets/us/reference/corporateactions-1 .


## 2026-10-31 adversarial timestamp / order audit (research only)

**Finding SEC, HIGH:** `acceptanceDateTime` from submissions JSON must not silently define a point-in-time negative. An external recent issue reports some observed discrepancies against original SEC filing headers; this is a falsifying test case, not official confirmation that all records are bad: https://github.com/dgunning/edgartools/issues/1501 . Previously, if a material filing's reported acceptance timestamp exceeded the captured read or EOD cutoff, the parser silently dropped it, which could hide a filing from review. Fixed by reporting `SEC_TIMESTAMP_DISPUTE_REVIEW_REQUIRED` and quarantined event IDs + form/date/time separately, with zero AL/STOP/notification/clearance authority. Independently crosscheck against the original filing headers and index before any historic PIT decision. This does not promote future filings to known-as-of.

**Finding Alpaca connector, HIGH:** Official Alpaca corporate-actions documentation says `start/end` results are sorted by `process_date`, with `sort=asc` or `desc`: https://docs.alpaca.markets/us/reference/corporateactions-1 . A real connected-app sample queried 2026-10-31 with `sort=asc` for GILD/LNT/BTSG, 2026-08-01..2026-10-31, returned **two** `cash_dividends` items in descending process-date order (2026-09-29 then 2026-08-17). Root location **UNKNOWN**: upstream API vs connector postprocessing. This is a connector contract dispute, not evidence of provider fraud. The adapter now reports `CONNECTOR_ORDER_DISPUTE_REVIEW_REQUIRED` instead of `SAMPLE_FOR_REVIEW`, never deletes an event, claims all pagination/pages covered, modifies signals, clears issuer risks or emits alerts. Synthetic sorted and reversed negative tests required.

**Invariant / rollback:** all changes isolated to the research shadow and offline tests within draft PR #322. Production rule set, 477 watchlist, 52-session EOD, stop/2R, active episode ledger, Sheets, V6 notifications, crypto and broker remain untouched. External SEC live download and direct authenticated Alpaca pagination / `data_quality=all` remain unverified; no source receives production authority.


## Resource / request budget gate — 2026-10-31

Prior PR workflow used `pull_request: synchronize`, which can trigger one supposedly one-shot live HTTP probe for EACH commit. This is an uncontrolled CI/request multiplier even on GitHub Free public runner. The workflow now requires `pull_request: labeled` with EXACT label `xray-official-source-once` and matching same-repo head, or permitted explicit `workflow_dispatch`; normal commits only execute OFFLINE CI. Label-triggering is optional and not required for strategy operation. If the label is unavailable, do not invent a run: declare LIVE_DIAGNOSTIC_NOT_RUN. No new schedule, data entitlement or secret was enabled.


## Final raw-provider access path (manual only, not activated in draft PR)

A new **protected-default-branch, workflow_dispatch ONLY** job is staged at `.github/workflows/xray-nasdaq-manual-official-raw.yml`. It cannot be run until this research PR is expressly authorized for merge and the workflow exists on `main`. It does **not** run on PRs, source commits, scheduler, market close or any V6 automation. It never writes Google Sheets, changes AL, sends mobile alerts or places broker orders.

* SEC publicly documents `data.sec.gov/submissions/CIK##########.json` with zero API-key requirement and requests a **genuinely declared organization/name and contact email** in the HTTP User-Agent. The manual job reads this only from `XRAY_SEC_DECLARED_USER_AGENT` in GitHub Actions Secrets. No secret means a **SKIP with zero SEC requests**; a dummy identity is not a workaround. Example syntax (not a value): `Your Organization authentic-contact@your-domain.tld`. Never paste the actual email or credentials into a public PR/chat/log.
* Alpaca uses the existing protected market-data credentials `XRAY_ALPACA_DATA_KEY_ID` / `XRAY_ALPACA_DATA_SECRET_KEY` (with existing compatible fallback names). The manual audit calls **only** `https://data.alpaca.markets/v1/corporate-actions` (not the trading API), supports explicit workflow input `scope=pilot3` (GILD/LNT/BTSG) OR `scope=all477` (unchanged existing 477 symbols in 20 batches of 25, final batch 2), a rolling 30-day window, requests `region=us&sort=asc&data_quality=all`, follows every `next_page_token` up to 8 pages/100 rows each, and fails closed on missing page metadata, repeated event IDs, invalid date/UUID, redirect, HTTP errors, MIME mismatch, truncated/oversize responses or exhausted page budget. The default is the safer **three-symbol pilot**. When the owner manually chooses `all477`, each batch must independently exhaust its page chain with strict 8-page/100-rows cap and ≥1.05-second request pacing; at most 160 Alpaca HTTP pages are permitted in one run. The aggregate event count is per-query occurrences, **not** verified global unique events or absence of risk. Neither scope changes the 477 production watchlist. No raw events, symbols inside provider responses, tokens or credentials are printed.
* SEC's `ROAD` CIK `0001718227` is the fixed public pilot. Receipt includes only parser status, number of bytes and raw SHA256; no raw filings, contact string or company events are logged. SEC timestamps are not independently proven as first public availability.
* Even a complete raw `next_page_token` chain cannot establish future provider-update completeness or historical PIT. Provider eventual consistency and outage risks remain: no `CLEAR` status has any execution, risk-release or AL authority.
* Evidence: the connected-app sample GILD/LNT/BTSG, Aug-Oct 2026, returned 1 record at `limit=1`, 2 at `limit=200` and **no `next_page_token` field in either formatted reply**. This directly falsifies the sufficiency of the connector for completeness and motivates raw REST. The new 26 normal + 26 optimized manual-audit negative tests are executed in existing read-only A11 CI (not with actual secrets).
* Two external prerequisites are unavoidable: authorization to merge the isolated research PR to protected `main` (publication/release), and a genuine SEC declared contact supplied securely. The current feature code can be reviewed and tested without either. No GitHub Actions payment or provider-data entitlement is asserted without account-specific confirmation.

## 477 option verification / release distinction

The production watchlist file is read-only and must contain 477 unique symbols, otherwise the probe refuses **before any provider request**. A synthetic full-scope test independently asserts 20 batches, 25 symbols in the first query, 2 symbols in the final query, exactly 20 paced calls in the one-page-per-batch case, no order/alert/Sheets rights, and fail-fast when a later batch is malformed. Actual live raw all-477 coverage is **NOT YET RUN**; GitHub's current source PR has no default-branch workflow_dispatch and no secure SEC identity.


## 2026-10-31: real raw `all477` result and unresolved 51-versus-50

On 31 Oct 2026 `workflow_dispatch` run [41202555257](https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/41202555257) on `main` reported `requested_symbols=477`, `batches=20`, `http_pages=20`, `observed_query_event_occurrences=51` and `SEC_EDGAR=SKIPPED_NO_AUTHORIZED_INPUT`. The 51 value was **batch-row occurrences**, not unique IDs across the entire watchlist. Independently queried connected Alpaca app returned 50 distinct records (48 cash dividends, 2 stock+cash mergers), but hides both `data_quality` and `next_page_token`. **No conclusion that the 51st was an extra unpublished event is justified**.

Official Alpaca data REST documentation (https://docs.alpaca.markets/us/reference/corporateactions-1) explicitly says `complete` is the default, that `all` includes early/incomplete records, that total pagination uses `next_page_token`, and that creation/publication latency is **not guaranteed**. Three competing hypotheses must be distinguished:

1. The same event ID appeared in two symbol batches (cross-batch duplicate): `unique_event_ids_observed` less than `observed_query_event_occurrences`.
2. An early/incomplete event exists under `all` but not `complete` (true provider quality difference): `all_only_event_ids_count=1`, with strict observed subset and identical row checks; the connector may still differ for other reasons.
3. A non-atomic provider update or connector transformation changed the captured data: `complete` not subset of `all` or same-ID content drift. This results in a hard refusal, not market clearance.

New manual-only workflow input `reconcile477`, when **separately approved for merge** and run by the owner, executes 20 batches under `all` and 20 under `complete` using the same 477 unchanged watchlist and observed rolling 30-day window. Each batch retains the 8-page/100-item cap and 1.05-second pace; total maximum 320 HTTP pages across both passes (40 pages for the 1-page-per-batch case), bounded within the existing six-minute manual job. It computes an **ephemeral per-ID index in memory only** and outputs aggregated counts, quality differences by type and SHA256 of sorted ID sets, never secrets, raw event rows or event IDs in Actions logs. Cross-batch same-ID rows with inconsistent fields fail closed, and `complete` must be a subset of `all`. These are **observed provider sets, not an atomic snapshot** and do not independently attest first-public-availability, provider coverage, PIT, rights, or trading outcomes.

There is no new cron, broker, Sheets or AL/stop/target/notification production integration. The absence of a real declared SEC User-Agent continues to produce `SKIPPED` and cannot be represented as SEC acceptance. Until a real independently captured EDGAR response is available, `SEC_LIVE_ACCEPTANCE=NO_GO`.
