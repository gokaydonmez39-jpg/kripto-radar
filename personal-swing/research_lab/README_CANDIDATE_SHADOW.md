# XRAY NASDAQ GODZILLA Ω — Candidate Research Shadow V1

## Authority and delivery boundary

**Research-only, offline, synthetic fixture acceptance** for the user's personal
477-symbol NASDAQ EOD project. This PR introduces no model or SDK imports, no
remote server, no market-price API, no broker or paper order, no Sheet update,
no alert, no cron, no secrets and **no production admission**. Public repository
scope is restricted to `personal-swing/research_lab/`; the separate
`nasdaq-xray/` and cryptocurrency systems are untouched.

This is a *sidecar interface contract*, not a full production integration. It
must never be described as an executed Qlib/OpenBB/Pydantic AI/MCP Use pipeline
or as verified financial alpha.

## Snapshot and existing code preservation

- Starting audited `main`: `f32765f3848e5984b084a96646151db422e12d7d`.
- Original 88-source catalogue blob SHA: `6547f095bae9c6ed7b5b43d55ba0fc11b0042d92`.
- `unified_research_88.json` is not modified. Its registry contract expects
  exactly 88 records, including `code:openbq-org/openbb` and
  `code:alpacahq/alpaca-mcp-server`; the latter is denied even in paper mode.
- Qlib PIT and A37 walk-forward synthetic gates already exist at
  `qlib_pit_readiness_shadow.py` and `a37_anchored_walkforward_shadow.py`;
  neither imports Qlib or establishes real PIT market provenance.
- The current Kronos V2 model and workflow are entirely out of scope. Its
  existing separate 477 EOD live acceptance remains HOLD until measured.

## Four strong candidates: roles and validation

| Candidate | Offline boundary | Future evidence required |
| --- | --- | --- |
| Pydantic AI | Typed observation fields; provenance and SHA; errors fail closed; **no actual Pydantic AI import** | Compare Pydantic/stdlib vs Pydantic AI benefits, explicit model/privacy/CPU budget |
| MCP Use | Static mock tool allowlist; papers/orders/private reads rejected; **no MCP server connection** | Tool discovery/transport/authorization review with isolated credentials and explicit owner approval |
| Microsoft Qlib | Existing synthetic 500+-row / 15-session purge structural methods; **no Qlib import** | Independently rights-cleared 500+ actual XNAS PIT sessions, point-in-time universe, issuer identity, corporate actions, walk-forward & baselines |
| OpenBB V5 | Synthetic provider venue, RAW-vs-adjusted and first-known timestamp checks; **no OpenBB import** | Actual vendor contracts/quotas, PIT provenance, source entitlement and external compliance review |

## Four helper technologies

| Helper | Status | Binding constraint |
| --- | --- | --- |
| Google TimesFM | Snapshot, no model loaded | Separate TimesFM 3.0 pretrained-weights license; independent OOS/CPU proof |
| OpenBB MCP | Existing OpenBB capability alias | No server started, mock schema only |
| Alpaca MCP | Existing registry alias | No connection; order-capable tool surface and credentials are prohibited |
| TradingView Lightweight Charts | Visual component candidate | No data-feed substitution, license attribution; no deployment |

## Executable code

`candidate_guard.py` validates all eight immutable candidate entries, exact
GitHub SHA snapshots, status and deny-all capabilities. `candidate_shadow.py`
implements three **local-only** operations: observation schema check, mocked MCP
tool-list audit, and mocked provider/PIT intake. It loads local JSON fixtures
only and has no network-client code. All outputs explicitly deny production.

From this directory:

```sh
python candidate_guard.py
python -m unittest -v test_candidate_guard test_candidate_shadow
python -O -m unittest -v test_candidate_guard test_candidate_shadow
python candidate_shadow.py evidence --fixture /PATH/TO/LOCAL_MOCK_EVIDENCE.json
python candidate_shadow.py mcp-tools --fixture /PATH/TO/LOCAL_MOCK_MCP_MANIFEST.json
python candidate_shadow.py provider --fixture /PATH/TO/LOCAL_MOCK_PROVIDER_CONTRACT.json
```

Replace `/PATH/...` with an existing LOCAL test-fixture path. The optional
operations are **not** automatically triggered in production. This directory's
`test_*.py` files are picked up automatically by the existing PR-path-filtered
`.github/workflows/xray-research-source-lab.yml`. No workflow file is added or
changed, and existing GitHub metadata checks remain unchanged.

## Admission and threat model

| Risk | Current proof | Gate for future promotion |
| --- | --- | --- |
| External dependency supply chain | Snapshot commit IDs checked by read-only GitHub queries | Lock exact dependencies/SBOM and inspect transitive licenses/security before running |
| Fake success claims | Candidate schema refuses production and executed-model claims | Independently verify actual model invocation, output, timestamps and readback |
| Prompt/tool injection | Strict mock tool allowlist and no dynamic dispatch | Real MCP transport, tool implementation, outbound network and permission audit |
| Leak/order/payment | No SDK/API/broker or secret access in files | Negative tests in an isolated zero-secret runner; explicit approval for any changed authority |
| Data validity | Local UTC/asof/venue/basis compatibility gates | Real issuer, corporate action, rights, venue, full 477 coverage, historical PIT evidence |
| Alpha performance | **NONE** | Preregistered multi-session OOS, 15-XNAS embargo, slippage/fees, buy-and-hold and market beta, no lookahead |
| Rollback | Add-only research files, no core modifications | Close draft PR; if later merged, revert only this candidate commit via approved PR |

**Operational success criteria fixed before tests:** normal Python and `-O`
tests both pass; registry remains 88, core 477; zero external SDK imports,
zero paid calls, zero secrets, zero orders, zero production changed files. The
manifest validator is *not* a substitute for vendor terms or execution QA.

## Release status

- Offline manifest/mock tests are a bounded **RESEARCH CONTRACT PASS** only.
- Any GitHub draft PR CI must be independently read back before claiming CI PASS.
- No merge/deploy/final production promotion without a separate explicit decision.
