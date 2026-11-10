# XRAY NASDAQ — eight candidate execution readiness V4 (2026-11-07)

**Decision:** `PREPARED_OFFLINE_WITH_EXPLICIT_HOLDS`; NOT actual third-party SDK integration, NOT a provider licence, NOT a new EOD source, NOT a live OOS/alpha certificate. Use only in `personal-swing/research_lab/` on the existing **draft PR #403**. Do not merge automatically.

## Grounded current state and immutable boundary

- Personal NASDAQ only: 477 raw Alpaca IEX 1Day RTH, 52 sessions operational scanner, immutable 2×ATR STOP and 4×ATR target, 15-XNAS-session episode tracking, `EXECUTION=NONE`, `NO_ORDER`.
- `nasdaq-xray/` canonical and the separate crypto project are out of scope; no new paid service, GitHub cron, ChatGPT task, model API, broker credential, Sheet write, order or alert.
- Existing approved research paths are left intact: `qlib_pit_readiness_shadow.py`, `a37_anchored_walkforward_shadow.py`, `unified_research_88.json`, `xray-research-source-lab.yml`, and Kronos V2.
- Verified source review commits and blob IDs are recorded as **source examination references only**, not as hashes of an installed wheel and not as a licence attestation. See `candidate_independent_preflight.py`.
- New preflight reads package *distribution metadata* without importing third-party candidate SDKs. Even if a package is installed, it reports `DISTRIBUTION_METADATA_ONLY_NO_SDK_PASS` (not framework execution).

## Priority-ordered execution plan and acceptance criteria

| Stage | Candidate | Pass evidence required | Current decision |
|---|---|---|---|
| P0 | Existing 477 EOD | Original core/README/flows unchanged, PR draft scoped to research_lab | Original PR CI only; keep core untouched |
| P0 | Alpaca MCP | Server-side removal of **all** order/paper-order/trading tools plus transport/auth separation, proven independently | BLOCKED: current official V2 is trading-capable; do not connect |
| P0 | Eight-candidate registry | All original 88 registry records and aliases immutable; no new production permissions | Deterministic tests PASS |
| P1 | Pydantic AI-slim | Pinned runtime install in a temporary, no-secrets, egress-restricted sandbox; real `TestModel` smoke; current stdlib/Pydantic baseline comparison; dependency SBOM | SDK NOT INSTALLED/NOT RUN in current environment |
| P1 | MCP Use | Isolated real package; enumerate actual tools/resources/prompts; reject unknown tools and writable transport even when client claims read-only | SDK NOT INSTALLED/NOT RUN |
| P1 | Qlib | Real no-secrets import/adapter and dependency audit; `>=500` **verified XNAS sessions** with actual 477 PIT data, issuer lineage, rights, 15-session purge, 3 OOS folds, fees/slippage and baselines | Existing structural tests only; PIT/OOS HOLD |
| P1 | OpenBB V5 | Real SDK isolated; provider entitlement and tape/adjustment/first-known proof; 477 same-ASOF coverage; never replace IEX automatically | Registry/adapter mocks only; LIVE PROVIDER HOLD |
| P2 | TimesFM | Model weight licence and exact checkpoint hash; CPU capacity; same-ASOF forecast vs Kronos with independent OOS | Code review only; 3.0 weights non-commercial/self-hosted restriction |
| P2 | OpenBB MCP | Exact V5 MCP server/tool roster, read-only authorization, no account/API/telemetry leakage | Alias of OpenBB; not a second provider |
| P2 | TradingView Lightweight Charts | Locally bundled exact JS version, offline-only static rendering, attribution/accessibility, no new feed | Visualization only, no execution |
| P2 | Kronos V2 | First eligible new session and private Sheet readback with matching ASOF, source SHA and device receipt separately | Requires future eligible EOD and proper data evidence |

## Evidence and tests actually executable now

```bash
cd personal-swing/research_lab
python candidate_independent_preflight.py
python candidate_independent_preflight.py --require-production  # expected exit 3
python -m unittest -v test_candidate_guard test_candidate_shadow test_candidate_release_gate test_candidate_independent_preflight
python -O -m unittest -v test_candidate_guard test_candidate_shadow test_candidate_release_gate test_candidate_independent_preflight
```

The calendar probe accepts a **private local JSON list of date strings**:

```bash
python candidate_independent_preflight.py --xnas-dates-file /PRIVATE/xnas_sessions.json
```

It uses the existing `exchange_calendars` XNAS calendar to reject weekends, omitted exchanges sessions, duplicate dates, short history, and a relaxed 500-session threshold. A 500-session **synthetic** test demonstrates the calendar checker only; it **does not** verify a market vendor's rights, actual price bars, 477 historical constituents, first-seen timestamps, corporate actions, embargo or statistical outperformance. The command *never* converts calendar shape to market-authority PASS.

## Upstream-specific findings (official read-only GitHub evidence)

- Pydantic AI-slim: source `pydantic_ai_slim/pyproject.toml` at `pydantic/pydantic-ai` snapshot `58b007e6...`, inspected Git blob `93c40fc...`; MIT. Its dependencies are dynamically versioned; a source SHA is not a locked dependency tree. A true reproducible wheel lock/SBOM remains required.
- MCP Use: Python metadata at `mcp-use/mcp-use` commit `ac0b6a5...`, blob `20243758...`; package `1.7.1`, dependencies include MCP, LangChain, httpx, Pydantic, authlib; MIT. It is not a certified no-egress broker boundary.
- Qlib: `microsoft/qlib` SHA `5435523...`, pyproject blob `54a44ab...`; MIT, imports/deps can include redis, pymongo, MLflow, LightGBM, CVXPY. No actual Qlib was imported in this work.
- OpenBB V5: `openbq-org/OpenBB` SHA `8c69d8d...`, `openbb_platform/pyproject.toml` blob `b28f727...`; Apache-2.0, `openbb` 5.0.0 and `openbb-mcp-server[cli]>=2.0.1` packages are declared. No provider entitlements are implied.
- TimesFM: `google-research/timesfm` SHA `e51928e...`, README blob `804951f...`; source Apache-2.0, but model weights 3.0 have an additional self-hosted non-commercial restriction. Weights not downloaded.
- Alpaca MCP: `alpacahq/alpaca-mcp-server` SHA `63cc427...`, README blob `fe3f7e3...` describes v2 dynamically discovered tools and real/paper trading capabilities. Client-side tool filtering alone is not a reliable no-order boundary. No connection/credential is authorized.
- Lightweight Charts: the repo is Apache-2.0, but a pinned bundle/build hash and offline UI validation remain absent.

## Pre-mortem: fail closed, do not invent PASS

1. GitHub runner cannot download a pinned dependency or sandbox has network egress: **SDK_RUNTIME=HOLD**. No fallback to a secret-bearing runner.
2. A vendor TOS/redistribution rule or 477 PIT lineage is unclear: **PROVIDER_PIT=HOLD**, original IEX unchanged.
3. MCP tool roster includes a writable/paper-order tool: **MCP_PRODUCTION=HOLD**, no MCP connection.
4. 500 dates exist but 500 licensed, timestamped IEX bars per actual 477 historical issuer do not: **REAL_PIT_500=HOLD**, calendar-only PASS is not upgraded.
5. OOS walk-forward or fixed-cost benchmark fails: **MODEL_ALPHA=UNKNOWN/FAIL**, no signal promotion.
6. CPU/memory/GitHub runner minutes exceed free budget: cancel isolated test, no new spending and no replacement of EOD.
7. A PR CI fails: fix only the candidate-specific branch, don't change main or replay historical AL/STOP.

## Status, review, rollback

**Prepared:** audit scope, pinned upstream document metadata, package-availability preflight, calendar-shaped historical intake guard, 16 new independent negative/positive tests in both Python modes. This may be merged only after independent review, not by automation.

**Unavailable here:** live SDK imports/tests (`pydantic_ai`, `mcp_use`, `qlib`, `openbb` were not installed), full transitive SBOM, a paid-service-free live provider data contract, 477×500 historical PIT bars, model OOS and the first eligible future Kronos V2 EOD.

Revert policy: close draft PR before merge; if merged later, scoped revert PR with independent review. Keep `main`, canonical and crypto unchanged.