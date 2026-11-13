# Private research readback bridge V1

This is a pure, in-memory contract for the actual private Sheet scan, daily
score, and Kronos V2 20-column monthly ledger. It does not read credentials,
perform HTTP, write a Sheet, create a notification or authorize publication.
No private data or identifiers are stored in this public repository.

Important correction: the V2 ledger stores only 1/5/12-session closing
predictions, even when the original model path passed native OHLC QC.
Both RESEARCH_ONLY and RESEARCH_CLOSE_ONLY are therefore close-point
visualizations; their quality labels remain distinct. HOLD_QC_* has no
forecast drawing. No synthetic OHLC may be substituted. The private scan
ledger is aggregate; it is not 477 per-symbol AL/IZLE/ELE classifications.
Scores are episode-specific and preserve original bracket levels.

Inputs: independently verified completed XNAS ASOF; original ordered PIT
477 symbols; exact current algorithm fingerprint; genuine main scheduled
or dispatch EOD run ID; complete authenticated, formatted-value matrices
from TARAMA_KAYITLARI A:J, SWING_SKOR_GUNLUK A:AI and KRONOS2_YYYY_MM A:T.
Use source job receipts and Guardian/lifecycle/readback independently;
the bridge never attests a caller-supplied source or claims production PASS.
Missing, stale, partial, duplicated, mismatched or tampered rows reject.
The score digest is compared across rows, not recomputed from rounded cells.
Kronos row hash validates stored bytes; original raw inference path hash is
not independently reproducible from three closing points.

Next private acceptance: only after genuine 10-Nov or later EOD and first
V2 1431-record readback, compare complete matrices with the original source
jobs, validate exact cohort and source hashes, then build an authenticated
private display adapter. Do not publish rows to Actions logs/artifacts or
GitHub Pages; no API tokens in browser. Existing single Ana Merkez remains
the sole reporting path. This module has no live routing or deployment.
