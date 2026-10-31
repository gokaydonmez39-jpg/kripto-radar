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

`official_nasdaq_live_probe.py` makes exactly **one** HTTPS GET to the current Nasdaq Halt RSS and **one** GET to the Nasdaq-listed directory per invocation, after a 65-second CI pacing delay. The separate `xray-nasdaq-official-one-shot.yml` job runs only on selected PR updates or explicit manual dispatch, not on a schedule. It has read-only repository permissions and no secrets. The existing A11 suite remains strictly offline.

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
