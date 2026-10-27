# XRAY NASDAQ purgedcv / XNAS proof — research-only

Sources: [MIT purgedcv](https://github.com/landtml/purgedcv), pinned commit `aee3396422192d18bc30d376dfe9e31b2399abab`, and [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars) 4.x (already a production dependency).

This independent CI job installs purgedcv from the exact commit, tests 15-session-overlap purging using a second brute-force oracle, tests embargo subset properties and tampered/downsampled labels, and verifies true XNAS regular/early closes and DST. Synthetic index is for an isolated laboratory only; the 52 XNAS session test uses the exchange calendar. It does not create new AL decisions, trade executions, returns, notifications, private data, or credentials.

**Admission gate:** CI success proves numerical/data-integrity contracts, not alpha/profitability or fully usable live backtesting. Future A1 must use actual licensed point-in-time historical data, disclosed transaction costs, frozen strategy and out-of-sample experiments. Production strategy and 15-session lifecycle remain unchanged.