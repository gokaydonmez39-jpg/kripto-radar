# XRAY NASDAQ A36 — Personal Source Graph + Security Coverage Witness

## Decision and frozen boundary

**Pure read-only research.** The source was informed by:

- Graphify-Labs/graphify, Apache-2.0, `graphifyy` upstream manifest 0.9.99; the repo already contains `nasdaq-xray/graphify_c417_sha_lineage_shadow.py` and `nasdaq-xray/research/graphify_workflow_dag_audit.py` for a **separate** canonical-research purpose.
- Cloudflare/security-audit-skill, MIT, with coverage-ledger and `confirmed / needs_validation / rejected` evidence discipline.
- addyosmani/agent-skills, MIT, from which exactly three process safeguards are adopted: **pre-change scope contract**, **red/green negative testing**, **source-SHA and rollback checkpoint**.

**This is not installation or execution of any of these three upstream packages.** A36 is a transparent, standard-library static witness specific to `personal-swing` and its GitHub Actions references. Claims of Graphify-native extraction, full Cloudflare security audit, runtime reachability, absence of vulnerabilities, signal performance, or portfolio alpha are forbidden.

No new persistent task, schedule, production secret, provider API, Sheet read/write, alert, broker/order, published private data, dependency, or changes to AL/IZLE/ELE and 15-session rules. XRAY CRYPTO is untouched. No third-party model/cloud/API usage or fees.

## Inputs and exactly what A36 proves

- Input is **only Git-tracked** Python files under `personal-swing/` and relevant YAML files under `.github/workflows/` matching `personal|nasdaq-backtesting-challenger`.
- Fail closed on symlink escape, unexpected path, too many files/bytes, broken Python AST, invalid SHA, missing coverage, changed source hash, or graph edge without an existing target and exact source line.
- Edges are **static literal import statements** to same-directory or nested/relative Git-tracked `.py` modules (as of A38), and literal workflow references to tracked Python files. A workflow reference is **not** claimed to execute. Dynamic imports, shell interpolation, untracked code, undocumented workflows and vendor behavior are out of scope.
- Security leads such as unpinned action refs, `pull_request_target`, or unresolved literal script paths produce only `needs_validation` with `severity: null`. They are **not confirmed exploits** or production release blockers by themselves.
- Public GitHub CI prints **counts, HEAD SHA and a salted-free deterministic coverage hash**, not code contents, candidate stock symbols, price bars, Sheet records or credentials.

## Reproducible tests / acceptance contract

The existing `personal-swing` and `.github/workflows/` files must remain byte-for-byte unchanged. Four new A36 files are permitted. CI is pull-request-only, with `contents: read`, pinned checkout/setup-python actions, no secrets and no scheduled/manual dispatch.

1. `python -m unittest -v test_a36_personal_source_audit`
2. `python -O -m unittest -v test_a36_personal_source_audit`
3. `python personal-swing/performance_lab/a36_personal_source_audit.py --audit-repo . --min-edges 20 --min-workflow-edges 2`
4. Same CLI under `python -O`, checking identical structural counts/hashes for the frozen tree SHA.

Tests must demonstrate both trigger and recovery: e.g. unpinned-action lead vs SHA-pinned clean reference, changed-source hash rejected vs original hash accepted, `pull_request_target` produces `needs_validation` vs plain PR benign, and incorrect edge/coverage rejected vs valid edges accepted. An explicit human manual sample of **20 actual source edges** still remains a separate evidence gate before declaring full coverage acceptance.

The test workflow is the only new runtime route; it never calls Python package installers, performs Graphify extraction, uploads artifacts, or runs production Python jobs. **The GitHub-hosted runner is not network-isolated**; the A36 code contains no network client or outbound action, which is narrower than claiming a kernel-enforced zero-egress environment. Consequently the full native Graphify-and-Cloudflare sandbox gate remains **HOLD**.

## Rollback

Before main promotion, keep a draft PR. To reject the change close the PR and delete the isolated branch; current `main` is unaffected. If independently approved and merged later, revert only the A36 merge commit, preserving all previous personal-swing A34/A35 files, workflows and existing NASDAQ coordinator. Never delete historical candidate/outbox data.

## Scientific/production state

A clean source graph and green synthetic tests are **not** a vulnerability clearance, not a successful 2 November EOD scan, not mobile delivery ACK and not investment performance validation. All broader FINAL gates remain unchanged.

## A38 Graphify-inspired structural benchmark (2026-11-01)

**No native Graphify execution.** External GitHub connectivity is unavailable in the execution sandbox, and `graphifyy` is not installed. The upstream benchmark required by the wider recommendation remains **NOT EXECUTED**; do not represent this as Graphify-native coverage or Graphify beating A36. Instead, A38 implements a bounded, source-level fix to the already merged A36 witness using Python's standard-library AST with *pre-registered synthetic ground truth*. This repair is useful independently of any upstream package.

- Baseline A36 missed four **unique** known relationships in the synthetic fixture (nested dotted imports, `from . import source`, `from .source import source`, and `from .. import source`). The original A36 prior to the patch produced **0 of 4 unique expected edges** on this fixture; this is a reproducible negative test, not a statement about real NASDAQ missing imports.
- A38 patched extractor detects **4/4 unique expected edges** without falsely linking untracked/stdlib imports; does not claim execution. Note: the fixture intentionally contains two import statements that refer to the same from/to module pair, so unique-pair recall is 4/4, not five.
- The new benchmark suite adds four fixture-based tests, including non-existent relative target, source/provenance, deterministic scan. The preexisting 13 A36 tests continue unchanged.
- The workflow now runs both test files in ordinary Python and `-O`, followed by the existing bounded tracked-repo witness. No additional dependencies, login, Graphify Cloud, storage, secrets, new scheduler, or production/symbol logic.
- `graphifyy` v0.9.99 upstream reference is architecture research only. No Graphify code was copied, imported, or executed.

**Acceptance boundary:** This is a useful **A36 coverage repair**, not certification of native Graphify versus A36, no measurement of Graphify CPU/runtime/cost, and no verified new market signal. The original source/line coverage limits, private-data isolation and rollback policy apply.


## A39: Trail of Bits property-method inspired source-graph closure (2026-11-01)

Upstream research reference: https://github.com/trailofbits/skills/blob/main/plugins/property-based-testing/skills/property-based-testing/SKILL.md (source read as untrusted documentation). No upstream package, skill prompts or Hypothesis runtime installed. This is a deterministic, standard-library invariant/property-inspired test suite, not randomized Hypothesis certification.

**Predeclared measurable gate:** At least 3/3 correct tracked project-root import relationships for nested Python modules, 0 externally absent targets counted as edges, ambiguous two-root import resolution not promoted to a proven relation, existing A36+A38 tests preserved, 23/23 regular and optimized tests passing. No live data, real-time import execution, market data rights, private files, other projects or broker authority.

**Reproduced defect:** The frozen pre-A39 A36 implementation returned 0/3 tracked edges for three syntactically explicit import forms from `personal-swing/research_lab/` into `personal-swing/performance_lab/`. These are fixture-grounded static *potential dependencies*, not demonstrated runtime execution.

**Minimal repair:** For literal absolute imports, scan both the calling file's parent and the declared `personal-swing/` root. Mark project-root-only edges `confidence: INFERRED` because `sys.path` is not runtime-verified; retain existing local-literal `confidence: EXTRACTED`. For `from pkg import submodule`, candidate `pkg/submodule.py` is recognized only if Git-tracked. Where both roots contain distinct matching files, produce `AMBIGUOUS_IMPORT_ROOTS` with `verdict: needs_validation`, no edge. Externally installed/dynamic names remain unlinked. 50 deterministic source-order permutations check reproducibility and prove no input mutation.

**Measured synthetic result:** 3/3 expected static candidate edges, 0 false positives against the predeclared negative fixture, 23/23 standard and 23/23 Python optimized tests pass locally. Coverage is bounded to this corpus; no security certification, no Graphify-native benchmark, no market alpha or fill claim. Prior source graph logic, trading rules, production dependencies, GitHub scheduled workflows, secrets, Sheets and CRYPTO untouched.

**CI:** Existing A36 PR-only workflow adds the single A39 test module to regular and optimized `unittest` commands; no runner, permission, scheduled or network client additions. A merge re-check on `main` is required before acceptance.

**Rollback:** Revert only A39's source, one new test file, README and workflow changes if the independent GitHub regressions fail. Never disable the other A36/A38 integrity gates to force PASS.
