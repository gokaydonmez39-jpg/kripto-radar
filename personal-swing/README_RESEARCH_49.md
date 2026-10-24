# XRAY 49-source research evidence lane — 2026-10-24

Status: OFFLINE RESEARCH MODULE; NOT LIVE PRODUCTION.
No API network calls, broker access, orders, private Google Sheets writes, or user-facing alert emission.

## Implemented and guarded
1. research_sources_v1.json: 49 sources in supplied sequence and P0/P1/P2/P3 levels. Every source has unattended collection OFF and no AL promotion rights. Source 50 has not been supplied.
2. research_evidence.py: offline SEC filings (8-K, 10-K, 10-Q, Form 4, 13F) with issuer CIK/ticker and acceptance UTC checks; SEC document accession/link validation; Form4 P/S/M distinction and amendment status; 13F filing lag; FRED/ALFRED vintages with explicit publication UTC timestamp.
3. test_research_evidence.py: negative tests for identity, future filings, amendment, option exercise vs purchases, 13F lag, vintage revisions and missing release proof.
4. Existing 477-stock engine thresholds, fixed stops and targets, 15-session candidate journal, C4.17 policy and ChatGPT task prompts are UNCHANGED.

## Safe offline execution
cd personal-swing
python -m unittest -q test_research_evidence
python -O -m unittest -q test_research_evidence
python research_evidence.py --symbol CVLT --cik VERIFIED_CIK --cutoff-utc 2026-10-23T20:00:00Z --sec-json /private/submissions.json --output /private/readonly-evidence.json

The timestamp and ticker above are EXAMPLES, not a claim that a SEC CIK, official XNAS session, cutoff, authentic payload, or live event has been attested. Use an actual verified issuer CIK and independently verify official session/early close calendars.

For Form 4 optionally pass --form4-xml /private/form4.xml --form4-accepted-utc ISO_UTC.
For macro optionally pass --fred-json /private/fred.json --fred-series GDP --fred-release-times-json /private/release_times.json.
Release-times JSON requires keys observation_date|realtime_start and explicitly attested ISO-UTC release timestamps. A missing publication instant results in UNKNOWN, not historical knowledge.

## Eight source-plan decision gates
1. SEC issuer events: offline metadata parser DONE; live SEC fair-access client, provenance authentication, verified issuer-class links, official event semantics, API limits and licensing remain PENDING.
2. 15-session followup: KEEP the current Sheets + tracker authorities. Source join, exact session calendar, event key and sheet readback remain PENDING.
3. Macro: ALFRED vintage reader DONE offline. Live FRED API key, macro release timestamps, rights, walk-forward out-of-sample comparison are PENDING; no macro AL veto.
4. Insiders: Form 4 P/S/M reader DONE offline. 10b5-1 flag UNKNOWN unless independently examined within the full filing. No trade inference.
5. 13F: delayed-publication PIT helper DONE; Dataroma, WhaleWisdom, 13f.info remain manual or rights-gated. Never signal on quarter-end alone.
6. AQR/Damodaran/PortfolioVisualizer/CFA: methodology references ONLY. No proven alpha benefit or running factor model; out-of-sample and ablation PENDING.
7. GitHub -> private Sheets -> ChatGPT phone: LIVE E2E PENDING. No third-party source in the list supplies or fixes this plumbing.
8. C4.17/R92 evidence: SEPARATE BLOCKED chain, cannot be unlocked by secondary market-cap sites or omitted issuer evidence.

## Compliance and release
SEC official docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
SEC fair access: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
FRED API: https://fred.stlouisfed.org/docs/api/fred/series_observations.html

Do not scrape or feed unrelated third-party sites automatically without explicit current terms, permission and endpoint documentation.
OFFLINE parser payloads are NEVER authenticated as SEC/FRED live fetches. They cannot cause live AL, registered R92, candidate transitions, critical user notifications, risk veto, or trading.
Only merge this sidecar after normal and -O tests pass and the PR is reviewed. Rollback: revert these added independent files and the CI test command. No production credentials are needed.