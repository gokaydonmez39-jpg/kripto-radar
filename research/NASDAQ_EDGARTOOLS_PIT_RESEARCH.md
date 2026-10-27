# NASDAQ SEC EdgarTools PIT acceptance-time offline lab

Actual MIT [EdgarTools](https://github.com/dgunning/edgartools) version 5.62.1 is installed on a zero-secret runner. Entirely fictional SEC-style index-header HTML tests verify accession, CIK, accepted_at compared with a timezone-aware regular XNAS close. Future-dated 8-K must be **rejected** at earlier close, including 16:03 accepted filing versus 16:00 close.

This test does NOT download real SEC filings, inspect official timestamps across issuer chains, provide current corporate event feeds, or change existing NASDAQ candidate/stop/target/alerts. SEC rate limits/user-agent and PIT issuer mapping require independent production acceptance before future live use. No crypto scope or calls.