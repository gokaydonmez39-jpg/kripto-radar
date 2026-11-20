# Personal 477 source health — private, read-only V1

Use the existing research bridge's `compose_source_health` entry point to
evaluate the four independently retrieved observations for one completed EOD.
It does not call, configure or affect the `compose` decision function, the
canonical EOD, the notification runtime, the Sheet, or any vendor API.

```python
from unified_evidence_bridge import compose_source_health

# The private caller establishes the official completed XNAS epoch and
# independently retrieves and validates direct receipts for that epoch.
view = compose_source_health(
    asof=verified_epoch.asof,
    eod_run_id=verified_epoch.run_id,
    eod_head_sha=verified_epoch.head_sha,
    receipts=independently_observed_receipts,
)
```

Do not copy private receipt payloads, raw records, symbols, or data to public
GitHub. The entry point accepts normalized aggregate records only and emits
no side effects. A `MATCHED_*` state describes structural corroboration of
the supplied witness, not an authenticated source, a delivery ACK, alpha,
market clearance, or protection against a dishonest caller. This code does
not wire an unattended authenticated reader or publish a new view externally.

## Input and matching contract

Each normalized receipt contains exactly `source`, `asof`, `eod_run_id`,
`eod_head_sha`, `run`, `result`, and `metrics`. `run` contains exactly `id`,
`path`, `repository`, `branch`, `head_sha`, `attempt`, `event`, `status`,
and `conclusion`. EOD and official evidence use the same natural `schedule`
run. Kronos and Cove use distinct successful `workflow_run` children. All are
exact `main`, same repository, attempt 1, and bound to the expected head.

| Lane | Direct result used by caller | Aggregate metrics required |
|---|---|---|
| `CORE` | `CORE_EOD_READBACK_VERIFIED` is a normalized conclusion from the original scan, Guardian and score readbacks, not the green job badge | `requested`, `processed`, `valid` = 477, `missing` = 0, `history_sessions` = 52, `feed=ALPACA_IEX_RAW_1DAY`, `calendar=XNAS`, and true `final_ready`, `guardian_verified`, `score_verified` |
| `KRONOS_V2` | `KRONOS2_PRIVATE_READBACK_FULL_GEOMETRY` or `KRONOS2_PRIVATE_READBACK_CLOSE_ONLY` | `symbols` = 477, `rows` = 1431, `horizons` = [1, 5, 12], `full_geometry` + `close_only` + `qc_hold` = 477; `qc_hold` = 0 for match |
| `COVE` | `READONLY_RESEARCH_PASS_NO_PUBLIC_METRICS` | Empty metrics. Do not infer realized performance from the result. |
| `OFFICIAL_477` | `RESEARCH_LEDGER_READBACK_PASS_NO_MARKET_CLEARANCE` | `rows` = 477, false `pit_verified` and `market_clearance` |

**A sibling job's matching SHA and a green step alone do not prove exact
source-parent identity.** The caller must independently obtain the child's
parent binding and source ASOF, not fill those fields from the expected
epoch. When a producer only exposes a status and does not provide an
independent binding, leave that lane `UNKNOWN`. A mismatched, duplicate or
invalid supplied receipt puts only that lane on `HOLD`. Omission does not
alter any other lane or the original private decision output.

The companion producer change binds the two existing shadow jobs to their
natural source parent using the Actions event, then matches the already-read
private scan and score receipt URLs to that parent before a forecast or
provider read. Their successful aggregate receipt may include only the public
EOD run ID, public source commit and session date. No private row, ticker,
prices, sheet identifier or provider credential is exposed. Historic receipts
without this binding are not upgraded or replayed.

## Verification and release

Run `python -m unittest -q test_source_health test_unified_evidence_bridge
test_private_research_readback` from this directory in both standard and
optimized mode (`python -O`). Existing Research Source Lab CI discovers the
new test with no workflow or schedule change. Cover exact matches, missing
and mismatched epochs, misleading successes, incomplete cohort, duplicate
witnesses, rejected private extras and byte-identical base outputs while
individual research inputs are omitted. All unit tests use synthetic inputs.

Natural acceptance still requires one independent same-epoch real receipt
for all four lanes without changing A/B inputs. No production authority,
automatic trading, additional writer/scheduler, or data-provider grant. No
historical replay. Roll back only the companion module, import, tests and
documentation if necessary. Do not change the original research bridge's
decision result, core feed, or active deliveries.


## Bounded automatic read recovery (Personal 477 only)

The natural Research Source Lab's independent source_health_live.py performs
**GET-only** source recovery. On GitHub HTTP 429, 500, 502, 503, 504,
URLError or TimeoutError it performs at most **three total reads** of the
same API path, with 1- then 2-second backoff. On recovery, it reports
aggregate transient_failures, recovered_reads, max_attempts and mutations: 0.
Recovery of transport alone is never a provenance PASS; the complete
exact EOD/Sheet/child-run receipt must still validate.

HTTP 400/401/403/404/409/422, invalid path, oversized body, malformed
content, mismatched EOD or incomplete private receipt **never trigger**
automatic alteration or a fake ACK. Exhaustion returns a fixed HOLD and
requires a separate observed correction. No job rerun, workflow dispatch,
GitHub POST, auto-merge, credential rotation, price-bar repair, Sheet write,
ChatGPT card, iOS notification or order is permitted.

**Acceptance before merge:** both ordinary and optimized Research Source
Lab CI pass for the existing full suite plus test_source_health_repair.py;
required Personal 477 read-only PR CI also passes.
**Live acceptance:** a natural scheduled Source Lab run logs either
the exact four-lane results or explicit HOLD; a synthetic recovered GET
does not count as a live provider outage. This is a bounded
self-healing *transport subcomponent*, not an unattended self-modifying
AI or guaranteed device delivery.
