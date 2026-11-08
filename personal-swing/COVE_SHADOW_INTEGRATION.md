# XRAY NASDAQ GODZILLA Ω — independent Cove-method research shadow V1

## Scope, provenance and license

Cove Trader describes the unreleased **Cove Strategy Lab** (parameter plateau/knife-edge and bracket path re-walk), **Cove Lab** (no-order forward grading), and unreleased **Cove Edge Desk** (Wilson intervals), at https://covetrader.com/ninjatrader-tools/.

This implementation is **original Python research code based on those publicly described methodologies**. It is **NOT** Cove Trader's NinjaTrader add-on, a port of their software/source, a partnership, a proprietary model download, a reproduction of their private benchmark, or a transfer of their license. No external code was copied. Source availability of their unreleased modules is unknown.

- **Asset scope:** `personal-swing/nasdaq_watchlist_477.json`, exactly 477 PIT-aware securities (effective 2026-11-03 INDV/SUPN mapping), not `nasdaq-xray/` canonical and never Binance crypto.
- **Source:** only authenticated Alpaca `feed=iex`, `timeframe=1Day`, `adjustment=raw`, `asof=<official completed XNAS date>`, via the existing `engine.live_read`. Single-exchange IEX bars are **not consolidated SIP**.
- **Entry and exit levels:** immutable `ADAY_GECMISI` historical entry close, STOP 2ATR, and 2R target; **15 completed XNAS sessions**.
- **No capabilities:** trading, fill confirmations, order routing, position sizing, portfolio weights, private Sheet writes, user notifications, real-time market signal generation, paid-data or new cron.
- **Two planes:** original AL/IZLE/ELE engine and private ledger remain authoritative. This sidecar is diagnostic only. Failures of Cove never modify, suppress, unblock, or escalate original AL.
- **Kronos:** separate forecast research; Cove does not invoke Kronos model/predictor, modify its monthly partitions, or use its generated OHLC as market source. The `kronos_v2.private_authority` **read-only 477-source/score verification function** is reused without model inference.

## Component wiring

1. `cove_shadow.py` — pure deterministic offline validation and analysis. A supplied private JSON must attest schema `XRAY_COVE_METHOD_SHADOW_INPUT_V1`, completed XNAS ASOF, exact 477 source counts, 477 PIT scopeSHA, exact algorithmSHA, raw IEX feed, valid 52 consecutive source sessions per episode symbol, immutable episode identity/2R, positive OHLCV, and no future bars. A supplied bundle is **not independent provider/Sheet receipt**, even if hashes match.
2. `cove_private_shadow.py` — authenticated post-EOD adapter. Only on a trusted runner with stored data-service secrets: obtains *spreadsheets.readonly* OAuth, checks private Sheet metadata, same-ASOF 477 final scan + SHA via `kronos_v2.private_authority`, verifies private lifecycle/outbox/PANEL via existing A21 flight recorder, snapshots all private tabs, fetches only candidate-symbol raw Alpaca IEX bars, re-reads Sheet and refuses concurrent changes, and calls the pure analysis in memory. Public Actions log emits **only fixed PASS/HOLD labels**, no ticker, positions, prices, counts, IDs, secrets, hashes or traceback.
3. `.github/workflows/xray-personal-cove-shadow.yml` — separate `workflow_run` consumer after the existing personal NASDAQ scheduled EOD **success** on trusted protected main, plus offline PR tests. No `schedule`, `push`, workflow-dispatch, broker, secret exposure in PR, orders, Sheet append or GH repo push.
4. `xray-nasdaq-477-pr-required-readonly.yml` — existing stable `xray-477-required-ci` now must run Cove pure/adapter tests in **normal and optimized Python**, independently of the external Cove page and provider.

## Bracket path semantics

For each confirmed historical AL episode (not a new AL), scan only official **post-entry** sessions, no lookahead, max 15. A daily bar with open at/below stop yields `GAP_BELOW_STOP_OPEN_PROXY`; open at/above target yields `GAP_ABOVE_TARGET_OPEN_PROXY` (the opening price boundary is observed before the remainder of that bar); otherwise if low<=stop and high>=target it is **ambiguous**: lower-bound stop-first, upper-bound target-first. A single touch yields stop or target. Untouched after 15 sessions yields theoretical time exit at close. Earlier/unfinished cohort stays OPEN; no imaginary mark-to-market or backfilled trade.

All values are **theoretical daily IEX reference proxies**, never actual fills or an executable bar path. Gap-open proxies can be worse than original stop. Report two-sided per-share slippage bps plus commission for sensitivity, not actual paid commissions. Never silently replace source STOP/2R: hypothetical stop-risk multipliers 0.8, 1.0, 1.2 and fixed 2R target relationship are *counterfactual only*, with no "best multiplier" recommendation. Wilson 95% interval is calculated for definitive resolved target-first events only; ambiguous events cannot be counted as a certain win. All descriptive results are **not** OOS or causal evidence.

## Security, quality and provenance gates

- **Reversible adoption:** pre-change main `0fbfa55fc3d3b25271d3863ef08efa447620a61d` backed up under `xray/backup-main-before-cove-shadow-20261108`. One new isolated workflow may be disabled or reverted without touching original EOD or Kronos.
- **Tests:** see `test_cove_shadow.py` (17 tests) and `test_cove_private_shadow.py` (11 tests). Must pass Python normal + `-O` and required CI on exact HEAD. Confirm green PR positive and RED negative run.
- **No code execution on PR with secrets:** PR job offline only. Production `workflow_run` checks successful scheduled personal EOD, main branch, head repo identity. Checkout protected main. No external PR code with credentials.
- **Source rights:** IEX quote history's licensing and 623-session PIT history rights unresolved. This pipeline must not publish raw provider data or private personal positions.
- **Quality:** `FULL_FINAL=HOLD` until independent 623-session PIT/issuer lineage, 3×31 OOS, walk-forward, market regime, baseline comparisons, cost sensitivity, real paper-trade criteria. The fixed STOP/2R and IEX-specific volume caveat remain.
- **Delivery:** the research shadow never generates or replays AL/STOP notifications, never claims an OS push ACK and never creates a ChatGPT task.
- **Production proof:** until the **first newly completed post-merge XNAS EOD** triggers actual scheduled source/score/private readback and the new private-eod-research job is independently observed with status PASS, mark `COVE_LIVE_ACCEPTANCE=HOLD`. Offline 28/28 successful unit tests do not establish 477 real-price outcomes.

## Offline API (only in a private working copy)

```sh
cd personal-swing
python -m unittest -q test_cove_shadow test_cove_private_shadow
python -O -m unittest -q test_cove_shadow test_cove_private_shadow
python -m py_compile cove_shadow.py cove_private_shadow.py
python cove_shadow.py --input /secure/private/research-bundle.json --slippage-bps 5 --commission-per-share 0.005
```

No sample source IEX prices, user ledger, access tokens or private input file are committed. Never upload the private bundle to public GitHub. The source adapter prints redacted status only by design. For full private numerical inspection, run the pure adapter in a trusted private environment with controlled output, not public GitHub Actions logs.

## Limits and rollback

1. If `xray-477-required-ci` fails, do not merge. Fix the exact failing test. If scheduled `COVE_SHADOW_POST_EOD=HOLD`, keep original radar unaffected; the first live debug must use private secure context, not raw public logs.
2. On unexpected side effects disable **only** `xray-personal-cove-shadow.yml`; revert Cove commits and retain backup original main. Do not weaken branch protection, scope, algorithm or original source authority.
3. Claim `COVE_SHADOW_CODE_PASS` only after red/green tests and main readback. Claim `COVE_SHADOW_LIVE_PASS` only after new source-consistent EOD GitHub scheduled production receipt. Neither claim represents profitable strategy validation.

**Decision:** an independent research *method* integration, not an external NinjaTrader plugin installation. No automatic trading.
