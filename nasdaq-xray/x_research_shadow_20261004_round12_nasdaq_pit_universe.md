# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 12 Nasdaq PIT Universe

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## Official Nasdaq public-event unlock
Data News 2024-2: https://www.nasdaqtrader.com/TraderNews.aspx?id=DN2024-2
Symbol Directory / rights note: https://nasdaqtrader.com/trader.aspx?id=symbollookup
Security Status Updates: https://www.nasdaqtrader.com/Trader.aspx?id=nasdaq-security-status-updates
Definitions: https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs
Paid Daily List description: https://nasdaqtrader.com/Trader.aspx?id=DailyListPD

Official finding:
- Nasdaq's paid Daily List remains a $3,500/month organization product and has full historical corporate-action data back to 1999.
- Effective 2024 pricing change announcement explicitly states a public/no-additional-fee subset will include Financial Status, Market Categories, Issue events (Additions, Delistings, etc.), Ex-Dates and other information.
- Symbol Directory rights note says Nasdaq Events Data (Security Status Updates, Ex-Date, When Distributed/When Issued, Nasdaq Listed) is provided without restriction or further licensing requirement.
- Public Security Status search returns historical rows at least back to 2024-05-21.

Example official history:
https://www.nasdaqtrader.com/Trader.aspx?from=05%2F21%2F2024&id=nasdaq-security-status-updates&to=05%2F21%2F2024
Rows include Issue Suspensions, Security Additions, Financial Status Changes and Name/Symbol Changes.

## Candidate architecture
Name: NASDAQ_PIT_UNIVERSE_20240521_V1
Goal: build a survivorship-aware, official-source Nasdaq universe from the public-event start forward without paid Daily List.

Forward/reconstruction design:
1. Persist current `nasdaqlisted.txt` snapshots with file-creation timestamp.
2. Ingest all public Security Status rows by effective date from 2024-05-21 onward.
3. Event classes: Security Additions, Anticipated Security Additions, Issue Suspensions, Issue Deletions, Name/Symbol Changes, Market Class Changes, Financial Status Changes.
4. Maintain immutable symbol/entity event ledger.
5. Current master + event ledger can reconstruct candidate membership backward/forward only where event mapping is complete.
6. Validate issuer identity through SEC CIK/exchange/ticker and issuer IR when symbol/name changes are ambiguous.
7. Filter ETF/ETN/ADR/SPAC/warrant/unit/etc. under existing XRAY security-type rules; ambiguity => UNRESOLVED.

## Critical limitation
The free Security Status web table does NOT expose the paid Daily List's full `New Symbol` / `New Company Name` fields for Name/Symbol Changes.
Therefore a symbol-change row alone cannot reconstruct an exact old->new mapping.
Repair hierarchy:
- same-day/next-day official Nasdaq master diff when locally captured;
- SEC filing/issuer IR exact ticker-change evidence;
- official Nasdaq/Listing Center notices where available;
- otherwise mapping UNKNOWN, no inferred continuity.

## Historical scope
Public event history is not proven equivalent to the full paid Daily List before 2024-05-21.
Do NOT claim survivorship-free history back to 1999 from this route.
Practical scope:
- robust official forward PIT snapshots from integration time;
- partial/reconstructable official history from 2024-05-21 onward;
- pre-2024 research remains separate/unverified unless an authoritative free source is found.

## Why this matters
This can reduce dependence on paid/provider security-master data and improve:
- survivorship-bias controls;
- delisting/suspension exclusion;
- symbol-change identity;
- deficiency/delinquency/bankruptcy risk;
- market-tier changes;
- event replay.

END.
