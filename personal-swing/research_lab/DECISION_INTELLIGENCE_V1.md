# Decision Intelligence V1 — research-only evidence composition

## What this draft implements
One existing personal NASDAQ AL episode, same completed EOD and source
fingerprints, immutable original bracket, current technical score, and
optional normalized KRONOS/COVE/SEC/CONFIDENCE witnesses. A canonical
envelope digest binds the content and an output research SHA binds every
input and the result. Missing/HOLD/UNKNOWN remain distinct. No source can
change AL, STOP/2R, notify, publish, trade, or imply a probability.

Kronos is a close-point research forecast at H1/H5/H12, not a probability
or actual OHLC candle. Relative signs at the forecast origin describe
up/down/flat/mixed; no investment superiority claim. The score price is
rounded to 3 decimals, Kronos to 6; compatible rounding is required.
Cove's actual current private output is cohort-level sensitivity research,
with PIT/OOS HOLD. No per-symbol risk label is inferred. SEC READY is not
admitted until separately authorized, point-in-time evidence exists.
Confidence Lab can carry only descriptive readiness, never calibrated
success probability or expected net R. No numeric weighted ensemble.

## Source and deployment gates
The existing #429/#430 private bridge work remains separate, neither
merged nor required to run these synthetic tests. A caller-provided hash
cannot authenticate real data. A future private adapter must verify the
original private Sheet/source jobs, exact completed XNAS ASOF, PIT 477
scope/order, immutable episode identity, exact source/run and model
revision hashes, independent readback and appropriate data permissions.
It must also bind original raw evidence receipts, not just normalized
payloads. Score, Kronos, Cove and confidence schemas must be independently
accepted before composition. No public logs/artifacts containing private
records; no public hosting or new scheduler. The existing Ana Merkez is
the only possible future reporting path, with its existing unique-event
and silence policies.

No historical replay or backfill. No real orders, capital, fees, autonomous
strategy updates or production merge before core live acceptance and
approval. Actual learning/OOS and paper-forward acceptance remain separate.
Current system remains RESEARCH_START ACTIVE / FULL_FINAL HOLD.
