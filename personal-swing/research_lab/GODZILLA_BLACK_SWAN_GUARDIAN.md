# XRAY NASDAQ GODZILLA Ω — BLACK-SWAN GUARDIAN (read-only shadow)

**Purpose:** a self-contained, deterministic *hypothetical* risk laboratory.
This is NOT the existing 477-symbol AL algorithm, not a strategy modification,
not a backtest, not a production alert, not a trade recommendation, and not a
broker/order/account integration. Its release decision **always remains HOLD**.

## Why it exists

A headline reward-to-risk ratio of 2R does not bound realized loss.
Gaps through the original stop, spread, execution slippage, fees, and concentrated
notional exposure can make a planned paper position more fragile than
"reference close minus stop" suggests. A stop is not a guaranteed fill price.

The existing A21/A22 private alarm audit and the existing performance_lab
scientific outcome witness solve *different* problems; they are not replaced.

## Data flow and scientific invariants

1. Accept one explicitly furnished paper-only fixture; never query Alpaca,
   Google Sheets, ChatGPT, exchanges or a broker. No fixture is committed with
   real candidate or account data. A valid hash string is **not** proof that
   a real dataset was fetched, checked or legally licensed.
2. Require the original source **ALPACA_IEX_RAW_1D**, a declared 477/477 full
   technical scope, exactly 52 consecutive XNAS sessions, canonical date,
   source/policy fingerprints, an actual XNAS session date (no weekends/holidays),
   and exact original reference/stop/2R geometry.
   These are **synthetic contract assertions**, not externally authenticated
   source attestations. Any missing, different or malformed field blocks.
3. Refuse a second new-AL paper episode if the same symbol has an earlier open
   episode. This is an additional research gate, not a replacement for the
   authoritative private Sheets outbox's reservation/readback.
4. Do not construct an entry when the hypothetical next open is at/below the
   original stop or at/above the target. No assumption of close-time execution.
5. Calculate an adverse gap-stress exit as max(0, original stop minus a
   supplied ATR multiple), plus explicit entry spread, slippage and fees, and
   exit slippage and fees. Compute each **whole-share hypothetical cap** as
   the minimum of (risk budget / stressed per-share loss) and
   (notional exposure ceiling / assumed entry price), rounded downward.
6. Even for a valid fixture, return decision HOLD, no device ACK, no
   broker, no orders, no production AL modification, and no authority to trade.
   The stress exit is one chosen adverse scenario **not an upper loss bound**.
   If the paper scenario returns zero whole shares, HOLD. If the paper scenario
   returns nonzero, still HOLD for trading.
7. No portfolio-level correlation, borrow restrictions, real market impact,
   volatility-regime modeling, executable quote, options, events, gap upper
   bound, fills, tax, or verified device delivery is supplied. These remain
   unmeasured risks, not silently passed controls.

## Technical scope

Pure module: `godzilla_guardian_shadow.py`.

Tests: `test_godzilla_guardian_shadow.py` (deterministic ordinary and Python
`-O`; includes duplicate-alarm prevention, source and fingerprint drift,
unbounded gap/friction, nonfinite numbers, impossible original stop/target,
no-entry next opening, monotonic stress checks, budget and exposure bounds,
full 477/52 fail-closed contract, and zero trading permissions).

Run locally from the research_lab directory:

```bash
python -m unittest -q test_godzilla_guardian_shadow
python -O -m unittest -q test_godzilla_guardian_shadow
```

The existing `.github/workflows/xray-research-source-lab.yml` picks up these
two files on PR/push and runs the full research regression suite in both modes.
No GitHub schedule, private EOD job, strategy code, notification task or Sheets
configuration is modified by this research-only PR.

## Acceptance and adversarial criteria

- No accidental live GO, even if apparent nominal reward/risk is 2R.
- Increasing slippage, spread or assumed adverse gap cannot increase the
  hypothetical share cap while all other inputs remain equal.
- The scenario loss at the computed whole-share cap must not exceed the
  explicitly supplied paper risk budget; notional must not exceed the paper
  exposure ceiling. This is a calculation guarantee **under the scenario's
  assumptions**, not a promise about market losses.
- Repeated inputs must return exactly the same result and digest.
- Partial 477/52 history, invalid costs, unsupported venue, unknown prior
  episode, malformed datetime/identity, or altered 2R geometry must block.

**Current maturity:** synthetic risk QA only. No true positive predictive edge,
no risk-free trade, no verified tail bounds and no authority to act on its
hypothetical share counts. Production remains unchanged until separately
justified and approved.
