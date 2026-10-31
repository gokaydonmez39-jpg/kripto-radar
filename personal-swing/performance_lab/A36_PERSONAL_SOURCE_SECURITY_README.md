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
- Edges are **static import statements** to same-directory modules and literal workflow references to tracked Python files. A workflow reference is **not** claimed to execute. Dynamic imports, shell interpolation, untracked code, undocumented workflows and vendor behavior are out of scope.
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
