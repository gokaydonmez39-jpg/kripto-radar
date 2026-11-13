# A14 historical terminal classification

Research-only, read-only. No watchlist, entry price, stop, target, historical row,
notification or workflow schedule changes.

The original 12 November XNAS downstream run (43359116196) had one historical
corporate terminal, zero large raw open gaps and zero historical issuance close
mismatches. Its older witness used the same REVIEW_REQUIRED label for a known
historical non-price terminal and for new raw-data anomalies.

Public source cross-check:
- [Nasdaq Corporate Actions Alert 2026-806](https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2026-806)
- [Issuer SEC 8-K](https://www.sec.gov/Archives/edgar/data/1428439/000119312526451874/d181620d8k.htm)
- [Exchange Form 25-NSE](https://www.sec.gov/Archives/edgar/data/1428439/000135445726001058/0001354457-26-001058-index.htm)

These sources establish the November 6 last trading date and November 9 trading
suspension. The issuer 8-K independently corroborates the closure and suspension.
This does not prove a vendor corporate-action feed, absence of other corporate
actions, execution price, or scientific qualification.

HISTORICAL_TERMINAL_CENSORED_NOT_CLEARANCE distinguishes an intact, already
recorded non-price terminal when no raw anomalies exist. It still exits 3 and
never releases the A14 scientific gate. Gaps or reference drift remain
REVIEW_REQUIRED. A post-last-trade bar or invalid terminal still fails closed.
Do not replay the previous EOD to validate a change. Only a future natural
research run can supply new production evidence.
