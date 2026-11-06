# Kronos shadow research — XRAY NASDAQ personal 477

Status: research-only integration. **Not** an AL/STOP/2R predictor or trading engine.

## Source and scope

- Repository: `shiyu-coder/Kronos` at pinned commit `67b630e67f6a18c9e9be918d9b4337c960db1e9a` (no floating master).
- Model: `NeoQuasar/Kronos-small`, revision `901c26c1332695a2a8f243eb2f37243a37bea320`.
- Tokenizer: `NeoQuasar/Kronos-Tokenizer-base`, revision `0e0117387f39004a9016484a186a908917e22426`.
- Runs on the **existing** personal 477 GitHub workflow's successful `workflow_run`, not a new cron or ChatGPT automation.
- Forecasted cohort is **only unique symbols with open, verified episodes**, maximum 32. It DOES NOT claim 477/477 Kronos inference. If the cohort exceeds 32, it HOLDs, never silently truncates.
- Uses the exact existing `personal-swing` IEX 1Day raw source, strict latest completed XNAS session, signed universe/policy SHA, and the latest `SWING_SKOR_GUNLUK` 0-HOLD summary.
- Input history is 52 valid completed XNAS sessions; the Kronos context is the last 40. The output horizon is 12 future XNAS sessions; rows report the 1st, 5th and 12th predictions.
- IEX does not provide consolidated traded amount. `amount` is a derived proxy: mean OHLC * IEX volume, explicitly tagged and never presented as actual market turnover.
- The only write destination is a separate, pre-created private `KRONOS_TAHMIN_GUNLUK` tab. Never touches `PANEL`, `ADAY_GECMISI`, `TARAMA_KAYITLARI`, `UYARI_OLAYLARI`, or `SWING_SKOR_GUNLUK`.

## Controls

- `model.eval()` and `tokenizer.eval()` are explicitly applied. CPU-only inference, `T=0.6`, `top_p=0.90`, `sample_count=1` (NOT a calibrated probability distribution), RNG seed 123.
- Generated OHLCV is checked for finite, positive prices, consistent OHLC geometry and non-negative volume. Invalid outputs produce full-day `HOLD` with **no Sheet write**.
- `ASOF|SYMBOL|HORIZON` row ID, input SHA and forecast SHA are immutable. Existing ASOF is read back and verified, not recomputed or replayed. One append-only batch POST; readback after write; never retry an unknown POST outcome automatically.
- Public Actions logs contain categorical status and aggregate counts only; no private symbols, forecasts, market bars, credentials or auth bodies. No artifacts or model-generated alerts.
- Kronos code is pulled by exact SHA. Floating release or unpinned weights are forbidden.

## Promotion gates

`SHADOW_CODE_READY` requires offline unit tests green, code/revision pins, and separate tab header readback. `SHADOW_LIVE_ACCEPTED` additionally requires real completed-EOD workflow success, a successful private Sheet readback, measured 30-minute CPU budget, and no invalid candles or permission errors.

`ALL_477_ENABLED` is **not** implemented by this pilot. A later PR requires a measured batch/timeout budget and data provider rate-limit evidence. `DECISION_INFLUENCE_ENABLED` is **not** implemented: require clean pretraining-cutoff provenance, chronological point-in-time OOS with purging/embargo, four independent test regimes, costs/slippage, frozen hyperparameters, cross-sectional tests vs unchanged XRAY and persistence baselines, and significant net incremental benefit.

A model loss improvement, attractive forecast chart or positive return in a cherry-picked sample never satisfies promotion. Source code and inference failure do not block the existing XRAY EOD/Guardian/A34 pipeline. Model research signal cannot modify the core seven scores, episode identity, stop, target, actual alerts or the single :57 ChatGPT task.

## Rollback

Disable or revert `.github/workflows/xray-personal-kronos-shadow.yml`. Because the new workflow is independent and the Sheet tab contains only research rows, the core personal radar remains untouched. Do not delete historical research evidence; stop new writes instead.

## Known limitations

As of 7 November 2026, upstream remains subject to open questions on original checkpoint leakage/provenance (issues #265/#307), and open RoPE cross-attention inference repair (#425). This sidecar does not falsely claim that unresolved upstream issues are fixed. It is a research trial, not a verified forecasting edge. It also does not install a production OOS-validation or model-performance claims pipeline; those require independent review and promotion.
