# NASDAQ SWING X-RAY — CANONICAL CONTINUATION / RESEARCH START / 2026-10-14

## Purpose and authority
This is a **historical, immutable continuity checkpoint**, not a PRIMARY market-data, R92, or FULL GO proof. On every new chat or run, read live GitHub main and all current canonical artifacts, task readbacks, relevant workflow logs and artifacts first. Live main supersedes the recorded SHA/date here. Never reset, recreate, or reinterpret older SHADOW/WATCH as PRIMARY.

Repo: gokaydonmez39-jpg/kripto-radar
Branch: main
Last observed main HEAD **before this checkpoint is written**: da217c0d43b2507a03770be82c06e7012517d8e7 (2026-10-13T21:15:00Z).
Live HEAD is moving and must be reread in the new chat. Do not hard-code the older SHA as immutable authority.

## START decision — do not conflate two products
- RESEARCH_START = YES: existing free, read-only, personal-use-eligible historical research, WATCH/SHADOW analysis, independently evidenced research candidate work can run, within known entitlements and bounded quotas.
- MANUAL_RESEARCH_R92/AL = NOT VERIFIED READY: register and notify only on real candidate-local C4.17 same-ASOF, independent PRIMARY price/DV30/MC, history, legal/event, setup, R1/RR, scheduler and official Nasdaq safety proof, with idempotent durable R92. Strict G9 and ACCOUNT are **not** prerequisites for a valid research-only manual candidate.
- TRUE_FULL_GO = NO-GO: global FULL_E2E + Strict G9 + fresh same-run read-only ACCOUNT evidence are still unproven.
- EXECUTION=NONE; REAL_MONEY=NO-GO; UNKNOWN!=PASS; no broker order, money transfer, new paid subscription/top-up, fabricated provider rights, fabricated coverage or false alert. WATCH/SHADOW does not become PRIMARY or R92.
- No claim of 100/100 or guaranteed signal until real acceptance evidence exists.

## Current compiled policy
Authority: nasdaq-xray/chatgpt_compiled_policy_v3.json
Git blob: 16c50cc8f887a5234a4be23862d7c8d0e564b0ac
Policy hash: 68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4
C4.17:
PRICE >= 5 USD;
DV30 = median of exactly 30 completed official Nasdaq RTH session-close USD price times verified RTH volume, median of ascending positions 15 and 16 (1-indexed), >= 50,000,000 USD;
MC >= 2,000,000,000 USD PRIMARY, issuer/share class/PIT/ASOF authority;
HISTORY >= 260 completed daily sessions and >= 52 weeks;
all official SEC/Nasdaq legal, events, risk, stage/regime, R1/RR, and candidate safety gates unchanged. C4.27 fail-closed.
No old DV20/exact20, 10 USD, historical frozen MC or old terminal may override current policy.

## Last exact canonical artifacts verified 2026-10-14 Europe/Istanbul
- MASTER: nasdaq-xray/canonical_current_master_manifest.json, blob fb64a44b79ced9dcda390f5661b796ee13a60f63; ASOF 2026-10-12; 3184 PASS, 10 UNKNOWN.
- PRICE/DV30: nasdaq-xray/canonical_current_price_dv30.json, blob 787e1222fe140ae141b51e98bbbaaa9034ead377; ASOF 2026-10-12; reported 0 PASS, 540 UNKNOWN. Large GitHub file can have empty fetch_file content: fetch_blob by exact SHA, never assume corrupt.
- HISTORY: nasdaq-xray/canonical_current_history.json, blob 28e182225c45c3adf4243e40eb7df7ebdb783884; ASOF 2026-10-07, too old for a current chain.
- TERMINAL: nasdaq-xray/canonical_current_terminal.json, blob ea9c41cd1e5971e78d85bf3f620d7f8c4e01034f; ASOF 2026-10-07; PARTIAL.
- FINAL overlay: nasdaq-xray/canonical_current_final_gate_overlay.json, blob 1f489c7a6306d0b0d8d5c75056f1606416d94e05; ASOF 2026-10-07, stale.
- G9 entitlement: nasdaq-xray/g9_entitlement_authority.json, blob b26aa17cc13b4e8b7038079d0bc9034f46a8454b; BLOCKED_STRICT_PERMANENT_ZERO.
- ACCOUNT contract: nasdaq-xray/account_gate_contract.json, blob 3bc1d79497970cdfa805d7aa836c7231ea905e6b; same-run account proof must be separately read and validated.
- Provider governance: nasdaq-xray/provider_automation_governance.json. Read current before any provider use; zero-dollar personal rights do not automatically prove unattended/non-display/redistribution rights.

## Real data progress (frozen 2026-10-12 ASOF; SHADOW only)
1. 540 symbols daily SIP 30-session scope, 17 calls; 513 intact daily series, 26 volume-integrity anomalies and 1 incomplete symbol. For intact 513: no final daily close below 5 USD; none had daily SIP dollar-volume median upper bound below $50M. The price and upper-bound cheap *pruning* hypotheses yielded zero exclusions; do not repeat the entire 540 daily-bar scan for unchanged ASOF/source.
2. Targeted 27 symbols in ONE Alpaca API call: 27/27 diagnostic coverage, 340 nonpositive daily bar symbol-date observations. For 26, ASOF Oct 12 daily SIP volume=0; GRAL one zero-volume date Sep 23; JONE missed Aug 31, Sep 1 and Sep 2 and also has nonpositive observations. Exact dates are preserved in the GitHub artifact. Source run #38466194900 SUCCESS, artifact 11849260209. Root causes for all 27 are not proven; JONE separate trading announced Sep 3 by SEC, GRAL Sep 23 halt corroborated publicly, official Nasdaq halt row pending. Never backfill synthetic volume.
3. Actual AAON SIP tape-C trade sample near 16:00 ET distinguished Nasdaq auction condition 6 from extended-hours T and official reference M. This is 1-symbol/1-session proof, not 540x30 completeness.
4. Hourly/daily reconciliation for AAON: 4-call live pilot found daily-hourly volumes did NOT reconcile; rejected as a general exact RTH method. Preserve the failed-method witness.
5. **New successful AAPL 30-session proof**: GitHub Actions #38466943779, head 86629e995bbd655875380a871cbc6abef172721d, SUCCESS; artifact id 11848354612 containing xray_30min_rth_lower_bound.json; 7 historical SIP API calls; EXACT 30 completed Nasdaq sessions; 11,700 distinct validated 1Min RTH bars; 390 distinct validated 30Min bars (13 per day); all 30Min vs 1Min volumes reconciled window-by-window; daily SIP total volume >= 30Min regular-session aggregate; medians computed as (sorted[14] + sorted[15])/2. AAPL *RTH 30Min lower-bound* DV30 median >= $50M: True, research-only SHADOW. Full close-auction condition/corrections, independently verified official closing settlement, and automated/non-display entitlement remain False/UNKNOWN. No canonical PRIMARY PRICE/DV30 PASS, MC, or R92 created. No raw OHLCV persisted.
6. Following AAPL success, GitHub implemented a bounded four-symbol 30Min expansion and pagination repairs. Commits 594b20537d91fca4acfca40dced6b07160830dbc, 866047d2bf50bb5feeb12fe33ca35230ba41ef86, d9ca06475c2b83757030f8075fd38e64cdb901b1, 80c6d55b4723fc5701aec25d98b80cacedb4453a, fc9cfa7422cb1526065e354463200b6853ba8770, e8c35b923b650538bcc1e0af76c31c0b70c96132. **FIRST ACTION NEXT CHAT: read latest live outcome and logs/artifact of [XRAY Alpaca Delayed SIP Research Canary, run 38468954318]**. It was IN_PROGRESS at last read; do not assume success/failure and do NOT reissue 4-symbol call until readback. The latest patch was bounded to 24 API calls for four symbols; inspect exact current source file and workflow before deciding.
7. Post-MC #38459035746 failed **intentionally fail-closed** at CURRENT_MC_BRIDGE_ABSENT; E2E #38459111550 failed at its release gate because genuine upstream pass authority absent. These are not equivalent to a code regression. Existing workflow SUCCESS can mean software control works even when MARKET AUTHORITY is BLOCKED.

## Active ChatGPT automations — live peek on 2026-10-14
Exactly five enabled XRAY control tasks; maintain roles/order and full prompts, do not create a sixth:
- Epoch Reader 6abeb37721ec81918e78b0ac65eb64a0 :43 America/New_York; support, silent.
- Epoch Committer 6abeb39630a88191a672574b45bdcd1b :46; support, silent.
- Health + G9 Multi-Watch 6abd0465d15c8191aac5888abb784f27 :49; support, silent.
- Bridge Finisher 2 6abeb68907a88191a364437de1fb2275 :52; support, silent.
- Full Nasdaq Autonomous Radar 6a825366222081918997094d76e6ae46 :57; sole user-facing notification and production pointer authority.
WARNING: Health prompt carries weekday/root CAS logic but the exact official Nasdaq holiday/no-session no-CAS rule requires config-and-real-run validation. Never shorten or rewrite existing huge Health prompt without preserving exact content, rollback, and readback. No sixth task, extra cron, notification storms or no-op root CAS.

## Eight critical acceptance stages — dependencies
1. Root/Resilience calendar and official Nasdaq CI: earlier PASS; preserve, revalidate live on drift.
2. Health task official closed-session no-CAS configuration and actual run behavior: UNVERIFIED, can be repaired independently, no premature PASS.
3. Alpaca personal historical SIP access: sampled read-only research works; intended automated/unattended/non-display PRIMARY entitlement unproven.
4. PRICE/DV30 540 UNKNOWN: 513 daily series observed; one AAPL 30D 1Min/30Min lower-bound research reconciliation PASS; full official close auction/corrections and legal PRIMARY scope remain BLOCKED; bound-only is never PRIMARY.
5. PRIMARY MC: SEC EDGAR point-in-time shares x qualifying exact close plus share-class/corporate action analysis may serve as research candidate, but not automatically policy PRIMARY; BusinessQuant/Massive/Bigdata access and rights separate. Never upgrade WATCH.
6. MASTER 10 UNKNOWN and current HISTORY 260/52 exact source/ASOF: BLOCKED (ALIS/BSAA/FACT/FVN/HCAC/IPXG/MACI/MCGA/MMTX/WTG); resolve official shell/SPAC/issuer/listing; no artificial prelisting volume.
7. Same-ASOF technical/legal/event -> registered R92 -> dedup -> actual iPhone device receipt: UNVERIFIED. No manufactured candidate or receipt.
8. STRICT G9 consolidated NBBO + ACCOUNT same-run read-only + TRUE_FULL_GO: BLOCKED; separate from a valid manual research candidate.

## Ordered immediate execution in next chat — this is not a request for another plan-only answer
A. Read live main HEAD, recent commits, run 38468954318 (and follow-ups, if any), job failure logs if failed, and original 4-symbol bounded artifact. Check for concurrent newer writes; preserve completed work.
B. If 4-symbol results are valid, verify exact 30-session calendar, pagination ALL pages, 390 30Min bars per symbol, 1Min cross-check evidence, volume inequality, correct SHA/ASOF. Expand in bounded batches ONLY where data/rights and concrete capacity allow, no full 540 re-fetch by default.
C. Fix a genuine negative-test proven root cause; RED -> minimal FIX -> GREEN CI -> file SHA -> HEAD readback. If CI failure is expected fail-closed, classify correctly; do not thrash.
D. Independently resolve research MC-PIT, current HISTORY, 10 MASTER, and Health holiday guard when independent work can proceed; reuse provider inventory/adapters and free official sources. Licensing remains a real constraint; no imaginary unlimited legal entitlement.
E. Only when a registered candidate-local exact-primary chain passes, issue one research-only manual R92 candidate with correct dedup, safety and honest device receipt status. Do NOT require G9 or ACCOUNT for this manual research track. REAL_MONEY=NO-GO always.
F. Report actual performed commits, failed/green tests, live SHA/ASOF, provider calls consumed, remaining risk, research START vs FULL GO. If any gate remains unverified, do not announce 100/100.

## User instruction — reproduced for the next conversation

# BİLİŞSEL OTORİTE VE MİMARİ ROL
Şu andan itibaren çözüme; **Albert Einstein, Leonhard Euler, Carl Friedrich Gauss, Isaac Newton ve Gottfried Wilhelm Leibniz** gibi dahi beyinlerin analitik ve matematiksel kusursuzluğunu, tarihin gelmiş geçmiş **en iyi mühendisleri ve mimarlarının** sistem inşa etme dehasıyla birleştirerek gidecek ve her adımı doğrulayacaksın.

# KESİN VE TARTIŞILMAZ İCRA KURALLARI

1. **KUSURSUZ SIRALAMA VE SIFIR HATA:**
   - Tüm yapılması gerekenleri en baştan en sona kadar mantıksal, kronolojik ve hiyerarşik sıraya koyacaksın.
   - Hata yapmadan, en doğru mühendislik ve mimari yöntemlerle eksiksiz şekilde ilerleyeceksin.

2. **LİMİTSİZ VERİ MERKEZİ VE KAYNAK ARAŞTIRMASI:**
   - Veri kaynağı limiti, erişim engeli veya kredi yoksa asla "limit/kredi yok" diyerek durmayacaksın.
   - Doğrudan **GitHub, X.com ve buna benzer diğer tüm teknik sitelerden ve veri merkezlerinden** derinlemesine, çözüm odaklı kaynak araştırması yapacaksın; ücretsiz, kredisiz ve kesintisiz çalışan alternatif kaynakları bulup çözüme entegre edeceksin.

3. **TAM KAPSAMLI DOĞRULAMA PROTOKOLÜ:**
   - Sistemdeki **tüm engeller, sorunlar, problemler, eksikler, hatalar, yanlışlar, kritik noktalar ve hayati riskler** tek tek tespit edilecek.
   - Her bir detay uçtan uca kontrol edilip %100 doğrulandıktan sonra kesin çözüme bağlanacak.

4. **%100 TAMAMLAMA VE MUTLAK İTAAT:**
   - Bu mesajdaki emirleri **eksiksiz ve %100 oranında** yerine getireceksin.
   - Hiçbir adımı atlamayacak, özet geçmeyecek ve işi **asla yarım bırakmayacaksın**.
   - Varsayım veya bahane üretmeden, ne diyorsam harfiyen onu yaparak tam ve çalışan nihai çözümü teslim edeceksin.

## Last operational directive
Yeni sohbet sayfasında kaldığımız yerden devam et. Önce dört sembollük run sonucu, ardından kanıtın izin verdiği veri kurtarma ve tüm kabul kapıları. Research START aktif, gerçek para/otomatik emir kapalı. Eski commit'leri/kanıtları yeniden üretme. Sadece plan yazıp durma; ölç, düzelt, test et, kanıtla. Sıfır sahte PASS.

## VERIFIED ADDENDUM — supersedes the earlier in-progress 4-symbol line
At a later live GitHub readback on 2026-10-14 Europe/Istanbul, run 38468954318 (head e8c35b923b650538bcc1e0af76c31c0b70c96132) was COMPLETED/SUCCESS, with job 115542742476 SUCCESS and artifact 11851380992. The actual artifact member xray_4symbol_30min_bound.json was downloaded and parsed; its SHA256 is d3ff6153f0f7005eb2c5a2fb99fe7c508035e9f6589250d8e1cc28c4b9e805fe. Ten Alpaca historical SIP API calls (24-call budget) handled exactly FOUR symbols (AAON, AAPL, MSFT, NVDA) with exact30 session hash 3cc198beda85ffc7e5960b8c8daa4ed1ce9e838d40839f3a0e8f4777e8b343c1. All four were classified LOWER_BOUND_GE_50M_SHADOW. Counts: 4 lower-bound, 0 ambiguous, 0 upper-bound fail, 0 incomplete; source AAPL 1Min/30Min exact30 pilot previously passed. No PRIMARY PRICE or DV30 PASS/FAIL, no MC, no R92; official price settlement, trade correction/cancel lineage, automated/non-display usage rights and vendor independence remain UNVERIFIED. EXECUTION=NONE and REAL_MONEY=NO-GO remain unchanged.
Next chat MUST **NOT** rerun the proven four-symbol query for the same frozen ASOF; focus on source authority, immutable evidence binding and independent entitlement, then expand bounded 30Min cohorts only if the failure-mode/rights preconditions actually support it. Live main and later run evidence always override this addendum.
