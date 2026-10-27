# XRAY Scientific Methodology Laboratory — wave A0
This work implements *independently written methods*, informed by scientific risk methodology described in [Stefan Jansen's ML4T](https://github.com/stefan-jansen/machine-learning-for-trading), purged cross-validation literature, and the research use of [GS Quant](https://github.com/goldmansachs/gs-quant).
**It does not install or claim runtime integration of ML4T, purgedcv, vectorbt, GS Quant, DeepEval or Promptfoo.**

## Scope and safety
This is a **purely offline evidence/testing module**, not an alpha source. It does not import NASDAQ or CRYPTO decision code; it has no network, credentials, orders, Sheet writes, or alert delivery. Entry timing requires signal_index < entry_index; same-close fill is forbidden. Synthetic OHLC adverse first-hit and gap are deterministic conservative research conventions, not proof of actual fills. Purging uses **session indices**, not calendar days.

## Falsification ladder
1. Identity/as-of: future, stale, duplicate and malformed bars rejected.
2. Purging: label intervals overlapping held-out events + post-event embargo removed; 15-session episodes need 15-session overlap accounting when trained on historical episodes.
3. Costs: next-open assumptions and symmetric bps; no actual execution claims.
4. Taleb tails: same-bar double barrier => STOP_FIRST; gap down through stop => adverse open.
5. Gauss/Shannon: explicit descriptive uncertainty; insufficient data => no estimate.
6. Deming/Turing: run both normal and Python -O; compare independent baselines before promotion.

## Admission status
**A0_METHOD_SHADOW_TEST_ONLY**, not A1 backtest deployment. ML4T Python >=3.14 requires a separate pinned environment; gs-quant>=3.10 has optional API-gated services. Future integration must have real licensed, point-in-time data, out-of-sample holdout and explicit user approval. No automatic production promotion.
