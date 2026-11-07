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


## QC isolation patch (2026-11-07)

After genuine 2026-11-06 EOD 477/477 PASS, isolated Kronos workflow #42331090998 failed with `KRONOS_INVALID_FORECAST`: at least one generated candle failed OHLC/volume validation. The fix **does not repair, clamp, substitute, or promote invalid market-model outputs**. It classifies nonfinite values, nonpositive prices, negative predicted volume, OHLC geometry and horizon/schema errors into fixed code categories. A failing model-output series yields three immutable `HOLD_QC_*` rows for that symbol with blank prediction fields; valid symbols are processed independently. All 1/5/12 rows are atomically appended once, and the existing Sheet readback check remains mandatory. Any QC hold makes the job's exit code nonzero, so no `KRONOS_SHADOW_PRIVATE_READBACK_PASS` or PREMIUM probability can be claimed.

A protected main merge changing the research workflow itself has a one-shot `push` research-only recheck. It **does not rerun the personal EOD workflow** and **adds no cron**. This is for observing current completed ASOF and cannot write core AL/STOP/Guardian/PANEL data. Once ASOF is recorded, a recheck remains idempotent and does not overwrite QC evidence. Any actual model-quality improvement must be tested and applied to a new future ASOF.

## Known limitations

As of 7 November 2026, upstream remains subject to open questions on original checkpoint leakage/provenance (issues #265/#307), and open RoPE cross-attention inference repair (#425). This sidecar does not falsely claim that unresolved upstream issues are fixed. It is a research trial, not a verified forecasting edge. It also does not install a production OOS-validation or model-performance claims pipeline; those require independent review and promotion.


## Weekend research ASOF acceptance (2026-11-07)

A controlled post-merge recheck on Saturday initially emitted `KRONOS_SHADOW_NO_COMPLETED_SESSION` because the **producer-only** `daily_job.current_completed_session()` rejects scans later than 10 hours after EOD. That short expiry is correct for the main 477 producer and remains **unchanged**.

Kronos (downstream research only) now derives the latest fully completed official XNAS session from the same independent calendar and allows it for at most 72 hours past close+45m, including Saturday. It separately requires the latest unique **authenticated Sheet scan** to match that exact ASOF with 477/477 and SHA, plus zero-HOLD same-ASOF score summary. It cannot use future, unfinished, stale, duplicate or unverified sessions. This is a Kronos-only temporal gate; no EOD, Guardian, original AL/STOP or historical ledger edit.


## Automatic OOS audit and 477 CPU evidence (2026-11-07)

The shadow workflow runs `kronos_oos_audit.py` after its model stage (even if the
quality gate fails). The audit is strictly read-only: it checks the immutable
20-column ledger, each original `ASOF|SYMBOL|H1/H5/H12`, the stored SHA-256,
model revisions, QC blank prices, and official future XNAS session deadlines.
Before the target exchange session completes, **NO** realized price API is
queried for that forecast. After completion it compares recorded predicted
close vs actual Alpaca IEX raw 1Day close at that exact future date and vs the
fixed original IEX close (persistence baseline). Reported measures are MAE
percent and directional accuracy, grouped separately by 1/5/12 sessions.

All OOS indicators are exploratory. Even after 60 verified pairs and at least
four distinct ASOF dates per horizon, the status is **SAMPLE_REVIEW_REQUIRED**,
not alpha PASS. Trade costs, risk-adjusted results, time-series dependency,
multi-testing, regime robustness, OOS purging, survivorship, and baseline
comparison with original XRAY scores must still be independently verified.
Real 2026-11-06 H1/H5/H12 close outcomes are not available on Saturday
2026-11-07; no claimed outcome exists.

A dedicated PR-only **477 synthetic CPU benchmark** loads the exact pinned
Kronos-small model and actually runs 477 separate artificial 40-input/12-step
series on a CPU Actions runner with 29-minute job limit. The benchmark measures
inference seconds, peak RSS and QC failure count; it does **not** call Alpaca,
read private symbols, write Google Sheets, or prove financial quality. Budget
gate: all 477 must finish inference in at most 1300 seconds and peak RSS <=8192 MB;
otherwise capacity HOLD. Even a successful synthetic performance run is not a
live 477 source/readback permission.

**Independent 477 storage bottleneck:** current ledger uses THREE rows per
symbol (H1/H5/H12), so 477 symbols require 1431 new rows per ASOF. At a bound
of 20000 rows, a ledger can hold only ~13 complete 477-symbol sessions
(ignoring existing rows). A future 477 research expansion therefore requires a
separately reviewed partitioned/compacted, immutable, readback-safe ledger
with idempotent multi-batch writes, asof-bound provenance and an operational
quota test. Increasing MAX_OPEN_SYMBOLS from 32 or resizing the Sheet alone
does not satisfy these conditions. Do not do this automatically.

No new cron, no extra ChatGPT automation, no private inference on pull_request,
no modifications to existing 477 scanner, A34/Guardian, AL/STOP/2R, notification
event ledger, or canonical/crypto research systems.


## One-shot real 477 IEX **no-write** quality probe

The opt-in **one-shot** real NASDAQ benchmark is triggered only on a
protected-main merge of the existing workflow with an exact, distinct commit
subject `test(personal-477): one-shot live Kronos 477 IEX research probe`.
It does NOT add a cron, an automated daily 477 predictor, a database, or a
ChatGPT task. It verifies original same-ASOF private 477/477 scan + Swing
score SHA evidence, reads actual Alpaca IEX 1Day raw 52-session observations
for the exact 477 point-in-time symbol set, loads the pinned small model once,
and computes 12-step prediction QC for each symbol. It reports ONLY counts
(477 / valid / QC categories), CPU seconds and peak RSS. NO symbols, OHLCV
market data, predictions, Google rows, alerts, trades or artifacts are
published or written. Exceeding the source, memory, CPU or quality gates
fails closed.

A real 477 probe without a persistent, partitioned per-ASOF research ledger
is NOT 477 automatic daily production integration. A good real-data QC count
also does NOT establish model accuracy or incremental trading alpha.


## V2 477 real close-only research (added 7 November 2026)

### Why a second model-output mode is necessary

The pinned Kronos decoder independently emits raw predicted OPEN/HIGH/LOW/CLOSE/VOLUME
without OHLC ordering constraints. In the authenticated 2026-11-06 real IEX
477 sample it generated 119/477 unphysical OHLC paths. This is a native
model quality limitation, not an HTTP error. **V2 does not clamp, project,
sort high/low or claim to repair those invalid paths.** Instead, when
the raw predicted CLOSE remains finite and positive over all 12 horizons
and ONLY native OHLC geometry fails, V2 retains those original closes as
`RESEARCH_CLOSE_ONLY`. It explicitly labels `RAW_CLOSE_ONLY__NATIVE_OHLC_GEOMETRY_INVALID`.
This is a separate close-only research estimand, never native predicted
high/low/volume and never a model-quality PASS. Invalid/negative/nonfinite
closes are kept as blank `HOLD_QC_*` forecasts. Full native-valid paths
are `RESEARCH_ONLY`.

### Automatic bounded 477 research and long-term identity

The independent `kronos-v2-full-477-research` workflow job starts **only
after an actual successful protected-main 477 EOD `workflow_run`**, first
eligible XNAS ASOF **2026-11-09** (no 2026-11-06 replay). It uses the existing
Alpaca IEX raw 52-session market-data source and authenticated private
477/477 scan SHA + Swing score 0-HOLD readback, with the existing pinned
Kronos-small model and fixed sampling configuration. Exactly 477 distinct
symbols generate 1/5/12-session close forecast research rows: 1431 per ASOF.

Separate date-bound `KRONOS2_YYYY_MM` private Google Sheets monthly
partitions hold the same exact 20-column schema, model and source SHA,
single `ASOF|SYMBOL|H{1,5,12}` keys and per-row SHA. The create action uses
one addSheet+header batch POST. Subsequent appends are **at most 180 rows
per POST**, each followed by exact readback. Writes have **no blind
retries**: if interrupted, the next valid same-ASOF execution must
recompute the full deterministic cohort, verify all earlier entries are
an exact prefix and only append the missing suffix. Any mismatch is
a fail-closed HOLD; old history is never replaced or edited.

The software stops before a projected private Sheet **9 million-cell**
budget or 40,000 occupied rows in one monthly partition. This is a
bounded, not perpetual, free Sheets solution. Old month data must be
archived with full custody/restore tests *before* the budget is reached;
no automatic deletion/overwrite is permitted. Quarterly audits of
remaining capacity and OOS data retention are required.

The pre-existing 21-open-symbol V1 shadow ledger and its 2026-11-06
63 entries stay immutable, and the original AL/STOP, 0-100 Swing score,
Guardian/A34, event ledger, single ChatGPT :57 task and canonical/crypto
projects remain unchanged. V2 outputs **do not** grant execution or
change rankings.

### Research progress versus real acceptance

`KRONOS2_PRIVATE_READBACK_CLOSE_ONLY` proves complete 477 data delivery
with explicitly **unresolved native OHLC quality HOLD**. Only
`KRONOS2_PRIVATE_READBACK_FULL_GEOMETRY` proves all 477 native
decoded OHLC paths were geometrically admissible; neither proves predictive
skill. `KRONOS2_PRIVATE_READBACK_WITH_QC_HOLD` means at least one
even close-only forecast is unusable, and the job fails.

The model's scientific validity needs forecasts frozen at their original
timestamps and then realized outcomes from completed XNAS sessions only.
The OOS audit includes V1 and recent V2 monthly research (30-day
rolling audit) and reports full-native versus close-only status counts
separately, never extrapolating to live trading alpha. Validated market
performance and incremental Alpha stay NO-GO until sufficient
independent post-cutoff observations, purged walk-forward, explicit
cost/slippage baselines, risk drawdowns, and reproducible statistical tests.

**NO_ORDER; NO_NEW_CRON; NO_NEW_CHATGPT_TASK; NO_HISTORY_REPLAY.**


### Legacy writer retirement and incident recovery

On ASOF 2026-11-09 and later, the old 21-open-symbol V1 writer explicitly
returns `KRONOS_SHADOW_V1_ARCHIVED_NO_NEW_WRITES` without initializing a
Google Sheets writer. The original 63 immutable 2026-11-06 rows stay intact;
the old workflow still performs a separate **read-only** realized-horizon
OOS audit, including V2 monthly partitions. This prevents silent double
inference and two overlapping portfolios of new daily forecasts.

Failure recovery: halt only the V2 independent research job or revert
this V2 addition; original EOD AL/STOP/Guardian/A34 and old immutable
research history are not modified. Partial V2 monthly rows may be
continued only after exact SHA-prefix comparison. Any quality/provenance
or source ambiguity is HOLD; never delete, replay or overwrite
historical rows to make a test pass.
