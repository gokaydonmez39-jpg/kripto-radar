# XRAY PERSONAL NASDAQ A21 — BLACK BOX / PRIVATE FLIGHT RECORDER

**Purpose:** A user-requested end-to-end notification safety surprise for the existing 477-stock Nasdaq research radar. Unlike an extra alarm or duplicated scheduler, A21 adds one narrowly gated **read-only verification job** to the already installed A14 workflow. There is no new cron, ChatGPT automation, device message, scan, AL-rule change or order.

## What A21 actually checks at every eligible successful EOD

1. Authenticate the existing private Google Sheets service account with the actual `spreadsheets.readonly` OAuth scope. Never request write scope. Read only `ADAY_GECMISI!A:M`, `TARAMA_KAYITLARI!A:J`, `UYARI_OLAYLARI!A:T`, and the `PANEL!A:B` display summary.
2. Exact header, row bound, increasing unique scan dates, latest `477/477/477/0 TRUE` witness, valid unique candidate IDs, frozen original positive stop < close < 2R target.
3. For every existing outbox event: unique canonical `episode|event_asof|event_code|1` key, matching candidate owner/symbol/issuance date, event date not later than final scan, and original stop/target unchanged.
4. **Device ACK honesty:** `EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST` and `ALERT_REQUESTED_NOT_DEVICE_ACK` are *not delivered*. A timestamp, successful GitHub run or an AL message is not a verified phone receipt. An unexpected delivery status blocks certification rather than inventing delivery.
5. Detect stale non-authoritative PANEL as a separate flag without confusing the dated `TARAMA_KAYITLARI` source of truth. A21 does not silently edit the panel.
6. Double-read the three source tables and panel; if any Sheet contents changed between snapshots, fail closed rather than risk a torn read while the existing writer/ChatGPT task operates.
7. Only print public-safe numeric counts, dates and machine statuses; never log identities, prices, private rows, auth headers or personally identifiable event keys.
8. **No device messages are sent.** Existing sole NASDAQ `:57` task remains the owner of new-AL/follow-up delivery, de-dup and receipt reservations. Unknown or missing ACK stays unknown. No new schedule is added.

## Two independent outcomes

- `PASS_PENDING_DEVICE_ACK` means the existing source table, candidate and outbox records are internally consistent but one or more events lack independently confirmed phone delivery. It is deliberately not equivalent to `DELIVERED`.
- `BLOCKED_NO_DATA_PUBLISHED_NO_WRITES` means a genuine incomplete, duplicate, malformed or conflicting private record. The job fails without public disclosure or any attempt to repair by guessing.

## Expected initial real-data witness on 2026-10-28 before Nasdaq open

The private Sheet currently contains 6 open and 0 closed episodes; 3 outbox AL events with `ALERT_REQUESTED_NOT_DEVICE_ACK`; last 477 final scan 2026-10-27; `PANEL` displays 2026-10-26 and is stale (display only). These are **observed inputs**, not manually embedded outputs. A21 must re-read and independently evaluate the live private contents after merging. Do not claim live PASS until GitHub prints it.

## Scientific interpretations

Einstein/Feynman (separate producer vs source vs phone delivery), Euler/Turing (bounded deterministic checks), Gauss/Shannon (noisy or incomplete receipt is UNKNOWN), Leibniz/Lamport (canonical idempotency and event ordering), Newton/Popper (negative fixtures), Bayes/Kahneman (a request is not an actual receipt), Deming (twice-read repeatability), Taleb/Thorp (never certify a synthetic theoretical PnL or stop as a broker fill), Simons (preserve untouched research methodology). The 16 names are methodological prompts, not attributed endorsements.

## Future verification

When a real Nasdaq EOD completes after the official close+45m and GitHub finishes existing `xray-personal-477-eod.yml`, the already installed A14 event will also execute A21's independent job. A green one-time smoke before the current session is not a claim that today's EOD and iPhone receipt both happened. User/device delivery requires separate actual confirmation.
