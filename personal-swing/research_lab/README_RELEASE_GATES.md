# XRAY NASDAQ 8 source candidates — Release gate V1

**Scope:** only `personal-swing/research_lab/`; **no production integration**.
No new cron, ChatGPT task, broker, order, paid service, vendor API key, external model inference or Sheets access. Pure Python standard-library gate.

## Why
The 8-candidate prototype has offline mock PASS but not actual SDK/vendor/PIT/OOS admission. It would be unsafe to infer production from PR CI. This independent gate exposes each unsupported assertion as an explicit blocker. `--require-production` always fails closed until a separately approved, independently verified acceptance path exists.

## Current groups
- Strong: Pydantic AI, MCP Use, Qlib, OpenBB V5.
- Helpers: TimesFM, OpenBB MCP, Alpaca MCP, TradingView Lightweight Charts.
- 88-source registry is not modified. Qlib's existing PIT synthetic guard is not a real Qlib SDK install. OpenBB and Alpaca MCP aliases reuse registry keys.

## Immediate reproducible test (no package installations)

```
cd personal-swing/research_lab
python candidate_release_gate.py
python candidate_release_gate.py --require-production  # expected exit 3
python -m unittest -v test_candidate_guard test_candidate_shadow test_candidate_release_gate
python -O -m unittest -v test_candidate_guard test_candidate_shadow test_candidate_release_gate
```

The existing XRAY Research Source Lab workflow autodiscovers `test_*.py` on this path. No new workflow schedule and no secrets are required.

## Gate hierarchy (NOT automatic promotion)

1. Offline manifest and mock contracts (PASS from deterministic CI) — this is not an SDK validation.
2. Pin reviewed upstream code versions, complete package dependency/SBOM and model weight licence audit — UNKNOWN until actually verified.
3. Isolated real framework execution **without network or secrets**; compare CPU, memory and runner time with stdlib baseline. If dependency installation needs external access, that installation must be isolated, separately approved and audited.
4. Pydantic AI: compare real SDK's deterministic model or offline mocks against current stdlib shape checks; never call an LLM API by default.
5. MCP Use: enumerate real tools, resources, prompts, transport and hidden permissions; mock server must be provably read-only; block paper/live order calls, credentials and unknown external hosts.
6. Qlib: >=500 legally accessed real XNAS PIT sessions, issuer mapping, survivorship and corporate-action basis, label purge/15-session embargo, chronological OOS and fees/slippage plus baseline. Synthetic 520 **calendar days** are not eligible.
7. OpenBB: vendor terms, PIT and market tape (IEX vs SIP), RTH, basis and 477-coverage QC must pass before using *any* new data.
8. TimesFM: separately verify *model weights* licence (code licence does not license every checkpoint), inference capacity and fair fixed-ASOF OOS against Kronos.
9. Alpaca MCP: trading-capable tool surfaces must be absent from any credentialed execution environment; paper order is still an order. Default: not connected. Charts: only local data visualisation.
10. Human review of evidence, no hidden changes in 477 AL/STOP, core GitHub workflow, Canonical, CRYPTO or :57 ChatGPT task. Separate owner approval is required to merge or promote.

## Known blockers
- Real SDK versions/dependencies are not installed or tested in GitHub Actions.
- Private 500+ session PIT history, external vendor licence, third-party data access and financial OOS verification are absent.
- No source has authority to modify AL, STOP/2R, private Sheets, alerts or execute orders.

## Rollback
The new files are additive and in a draft PR; close the draft PR to discard. For an authorized future merge, rollback only via a scoped revert PR, not by resetting protected main.
