# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 12 Nasdaq Security Status PIT

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## Official public source
Nasdaq Security Status Updates:
https://www.nasdaqtrader.com/Trader.aspx?id=nasdaq-security-status-updates
Nasdaq Daily List product:
https://data.nasdaq.com/databases/NDL

## Confirmed event classes from public Security Status page
Observed on 2024-05-21:
- Issue Suspensions
- Financial Status Changes
- Anticipated Security Additions
- Security Additions
- Name/Symbol Changes

Example historical query:
https://www.nasdaqtrader.com/Trader.aspx?from=05/21/2024&id=nasdaq-security-status-updates&to=05/21/2024

## Candidate PIT reconstruction role
Name: NASDAQ_SECURITY_STATUS_LEDGER_V1
Potential use:
- official Nasdaq event ledger for additions, suspensions/deletions, financial-status transitions and symbol/name changes;
- build daily point-in-time universe diffs from current/archived master snapshots;
- detect delisting/suspension survivorship changes without relying on vendor-derived universes;
- feed corporate-action / identity exception queue.

## Hard limitation
The public table shows a Name/Symbol Changes event row but does not expose enough old->new symbol mapping detail in the visible table to reconstruct every rename by itself.
Therefore symbol-change reconstruction requires corroboration from another official source such as SEC filing/issuer notice/Nasdaq daily master/daily list metadata.
Do not claim full survivorship-free reconstruction from this page alone.

## Authority hierarchy
T0 = Nasdaq official status page + official Nasdaq current symbol/master + SEC/issuer for identity-changing actions.
Third-party datasets remain cross-check only.

## Cost
Public web source: $0 access observed.
Do not claim unlimited or guaranteed archival retention; availability and automation terms must be monitored.

END.
