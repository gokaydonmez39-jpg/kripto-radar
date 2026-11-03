# XRAY NASDAQ GODZILLA Ω — Guardian V1 production contract

**Scope:** Personal 477-symbol Alpaca IEX 1Day research only. It does not
authorize live orders, broker connectivity, SIP data, canonical R92, or the
independent CRYPTO automation.

## Existing single-writer pipeline

1. GitHub `xray-personal-477-eod.yml` scans one completed XNAS session.
2. `private_sheet_writer.py` persists candidate identities/immutable levels
   and 477/477 scan receipt with post-write readback.
3. `alert_outbox_producer.py` reserves new `AL_NEW_EPISODE` rows as PENDING;
   already-open symbols are SUPPRESSED. No push is sent.
4. `private_lifecycle.py` advances independently tracked 15-XNAS-session
   episodes, never changing original reference/STOP/2R.
5. `panel_reconciler.py` updates only derived PANEL values.
6. **Guardian V1** re-reads these private authorities in a *separate job*
   and checks latest ASOF, exactly 477 valid, zero missing, scan scope
   SHA256 / algorithm SHA256 against current repo, 2R consistency, unique
   event keys, original AL levels, suppression and 15-session bounds.
7. The **sole** ChatGPT NASDAQ Ana Merkez task reads *new verified PENDING*
   and is the **only** user-facing alert author. It must never replay old
   REQUESTED/SUPPRESSED/QUARANTINED events.

## Autonomous repair policy

| Condition | Machine action | Maximum attempts |
|---|---|---:|
| Transient Google Sheets **READ** error | Retry read only; fail closed if still unavailable | 2 reads total |
| Candidate/scan/AL clean, PANEL derived fields stale | Re-run existing tested PANEL reconciler and check all sources unchanged | 1 write |
| Missing AL key or wrong STOP/2R | HALT and emit redacted incident; **no** historical AL reconstruction, write, or message | 0 |
| Duplicate key / stale ASOF / wrong source or algorithm SHA | HALT; no promotion or auto rerun | 0 |
| REQUESTED without chat message or push ACK | HOLD; no resend or fake ACK | 0 |
| Canonical history/PRICE/SIP/G9 authority missing | Maintain independent canonical NO-GO | 0 |

**Safety boundary:** Google Sheets is not an atomic distributed CAS store.
At-most-once event *intent* is enforced by the ledger/key policy where
possible; exactly-once user message/device delivery is **not** guaranteed.
A successful Guardian action is not a ChatGPT run receipt or an iOS ACK.

## Operational gates and failover

- Existing XNAS daily workflow and schedule fallback remain the *only*
  session producer scheduling mechanism; Guardian adds no cron.
- Existing GitHub root watchdog and canonical E2E auditor are unchanged.
- Offline tests run in Python 3.12 normal and `-O` before any real vendor
  calls. Production Guardian is after the private EOD + lifecycle + PANEL
  jobs, and its only artifact is a redacted aggregate JSON receipt.
- A completed GitHub job with an internal `HOLD`, `DEFERRED`, or
  `UNKNOWN` cannot be advertised as a full-system PASS.
- The Guardian explicitly reports `personal_research_start=PASS` only
  after source/ledger readback; `full_autonomous_start=HOLD`,
  `iphone_device_ack=UNKNOWN` and `canonical_full_final=NO-GO`
  until those independently verifiable gates actually pass.
- If the EOD/private lifecycle fails, the whole workflow remains red.
  Guardian is not allowed to re-run such producers because a partial
  provider write may already have occurred.

## Proof required before calling automated START accepted

1. For **two distinct consecutive completed XNAS sessions**: original EOD,
   A34 independently verified candidate identity/levels, private Sheet
   477/477 evidence, lifecycle, and Guardian job pass.
2. A **genuinely new** AL or STOP (not an old REQUESTED event) is reserved
   exactly once and appears in one Premium V8.1 scheduled ChatGPT message.
3. iOS device push delivery is reported as *unknown* unless a separate
   platform/phone receipt exists; tests of chat rendering are not phone ACK.
4. Replay, missing event, 1-cent legacy rounding, stop/target collision,
   duplicates, source SHA drift, transient read error and panel partial
   repair are regression-tested without any real orders or real alert sends.
5. The canonical system is assessed independently of the personal IEX radar;
   inaccessible licensed/primary sources cannot be replaced with guesses.

## Triage and rollback

- Read the most recent GitHub EOD job and sanitized
  `xray-personal-guardian-redacted` artifact by exact run ID and main SHA.
- `AL_OUTBOX_EVENT_MISSING`, `IMMUTABLE_PRICE_ORDER`,
  `AL_OUTBOX_IMMUTABLE_LEVEL_DRIFT`, `SOURCE_SCOPE_OR_POLICY_SHA_DRIFT`
  are fail-closed P0 incidents. Never overwrite prior levels to quiet them.
- `PANEL_ONLY_ONCE` is the only automatically repairable P1 incident.
- If a Guardian deployment causes unexpected failures, revert its GitHub
  pull request; the private original candidate/alert rows remain unchanged.
  The preexisting one-task Premium V8.1 contract remains the source of
  user-facing presentation policy.
- Any branch ruleset requiring administration permission needs an
  authorized repository administrator. Do not silently weaken CI gates.

**Historical acceptance is not a live-market guarantee.** The Guardian is
designed to prevent false PASS, reduce repetitive manual debugging, and
perform only bounded, auditable, reversible repairs.
