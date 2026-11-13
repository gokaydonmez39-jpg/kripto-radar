# Personal 477 delivery reservation

This change only supplies the private caller with a request planner and verifier.
The default branch, existing Ana Merkez task, and production spreadsheet are
unchanged. No delivery is attempted by the module or by PR CI.

1. The authorized caller verifies the latest natural EOD, eligibility, live Sheet
   IDs and complete formatted values. A and B remain independent. It must serialize
   against any nonparticipating writer (including edits or row moves), or hold.
2. Call delivery_reservation.py on private stdin with action=plan, kind=event
   or digest, current asof, verified sheet_id, complete baseline including the
   header, and actual Istanbul stamp in YYYY-MM-DD HH:MM TRT. For events supply
   the eligible keys. For the digest supply the independently verified summary
   hash as verified_sha. Do not emit the private inputs/outputs to public logs.
3. Send the complete requests array as one Sheets spreadsheets.batchUpdate.
   Each key inserts the same reserved named-range ID regardless of writer,
   timestamp, or row position. The status and timestamp update is in the same
   batch. A duplicate ID must reject the whole batch. Never remove the marker,
   repeat the POST, or retry from ambiguous transport/readback.
4. Fetch the full same range separately. Call the same CLI with action=verify,
   the identical plan inputs, the original successful POST response, fresh
   observed values and expected spreadsheet_id. Only verified intent may proceed
   to the authorized task output. That output is not proof of device receipt.

This is a uniqueness constraint for participating writers, not cross-provider
exactly-once delivery and not a condition on arbitrary collaborator changes.
Uncertain acceptance is not permission to send or to reset the status. Before
deployment, check named-range capacity, confirm that existing clients don't
use the reserved namespace, and ensure only the migrated consumer can write
notification statuses. Old intents are not replayed. A rollback disables new
reservation attempts and leaves recorded rows and markers intact.

2026-11-13 native, synthetic-only provider test: both baseline writers were
accepted without a marker. With the planner, exactly one event writer and
exactly one digest writer were accepted in their separate races. A colliding
marker ID rolled back another cell update and did not consume a fresh marker.
The successful POST and independent GET passed the verifier in both races.


## Private execution without a terminal

The portable JavaScript module implements the same planner/verifier contract
and the same marker namespace. It performs no calls and cannot send, reserve,
or change data itself. Use a trusted private JS execution surface to run the
exact immutable reviewed source. Never interpolate private input into code;
pass it as an object to XRAY_RESERVATION.operation. If no actual private
execution surface is available, remain HOLD. Do not approximate a request.
The caller still owns source provenance, independent score digest, concurrent
writer preflight, original POST response and independent complete GET.
`scoreDigest` accepts ranked tuples of exact decimal strings for score and
close, with empty strings when applicable, and refuses unsupported encodings.
Do not log any private matrices or emit them into public CI. No new channel,
credentials, or external runtime are needed. Restore Python-only caller config
if portability acceptance fails; retain all markers and committed statuses.
