# Personal 477 — official event and vintage research pilot

## State and boundaries

Isolated offline research only. No new source or vendor credentials, collection
job, workflow edit, alerts, Sheet writes, order, change to the 477 universe,
Alpaca IEX 1Day/raw, initial close, STOP, 2R, or 15-XNAS-session lifecycle.
Nothing here is an operational-final acceptance gate. No claims of alpha.

## Release-clock contract

`research_evidence.py --official-events-json FILE` accepts a local JSON array.
SEC observations are bound to the expected issuer CIK, accession, SEC archive
path and the actual observation timestamp. 8-K Item 2.02 is a separate label
only when explicitly supplied; an unclassified 8-K is a review item. Acceptance
is not the first public release time. SEC labels are accession/item-specific.
Fed statements, press conferences and minutes are distinct. BLS CPI, PPI and
Employment Situation have distinct keys. A dated calendar observation never
becomes an actual release by reaching its scheduled time. A release is visible
only once an actual publication observation has been supplied and its observation
timestamp passes the cutoff. A later calendar scrape cannot demote a release.

Common fields: source, kind, status, url and observed_at with an explicit UTC
offset. SEC adds issuer_cik, accession, accepted_at and optional item.
Fed/BLS add event_id and scheduled_at for SCHEDULED, or published_at for
PUBLISHED. published_at cannot be later than observed_at. Scheduled and
published rows for the same event must use the same event_id and kind.
Event URLs are provenance hints, not a proof of independent acquisition.
Identical rows are harmless. Equally timed conflicting rows are quarantined.
The issuer-specific record refuses an observation of a different issuer.
A revised filing is not a fresh initial signal. Missing data cannot attest
no events, complete history, safety, or a clean baseline.

ALFRED retains the existing UTC-date input convention. Only independently
evidenced release clocks can be supplied for research comparisons. An older
vintage can extend into the next vintage's starting UTC day only when the
dates are contiguous, exactly one prior vintage exists, its release is known,
and the successor's known release is later on that day. On the timestamp
boundary the successor applies. Missing or overlapping vintage evidence is
not filled. Conflicting published rows for the applicable vintage are withheld,
and exact duplicates are order-independent. The standard FRED vintage or release
date by itself does not prove a specific FRED availability time.

## First measurements, before opening outcomes

1. Reuse the existing SEC Fundamental Shadow draft #419 for the one-issuer
   source acquisition pilot. No new collector or production schedule. Obtain
   a real authorized SEC contact configuration and direct source receipts.
   Compare original accession, identity, actual observation, filing cutoff
   and amendment chain. Compare first with ABNB public documents. Confirm
   10-K/10-Q/8-K distinctions. For Form 4 use the full document, not only the
   transaction code. Unproven public timing or entitlement remains HOLD.
2. Label the Fed and BLS official releases alongside the unchanged radar as
   context. Validate the before/at/after cutoff and calendar-vs-release tests.
   Validate the right to use each numeric FRED series and capture publication
   evidence before adding it to any comparison. No fallback to scraped data.
3. Compare the unchanged radar with exactly one additional event feature.
   Primary research hypothesis: the event group has a different 15-session
   theoretical stop-contact probability. Freeze the first feature as a SEC
   8-K Item 2.02 observed in the two completed XNAS sessions ending at the
   candidate decision cutoff. Compare against otherwise eligible episodes with
   equivalent known event coverage and no such event. Missing coverage is
   excluded and counted separately, not labeled no-event.
4. Primary outcome: fixed original STOP touched within 15 verified subsequent
   XNAS sessions, with explicit gap and ambiguous same-day STOP/2R handling
   using the unchanged baseline. Report the risk difference in percentage
   points. Secondary sensitivity: downside gaps, net R, and drawdown after
   documented cost assumptions. Use a market/sector baseline and consider
   AQR factors as an ex-post attribution check only. Use dated source versions
   where data was knowable in live research. AQR daily QMJ updates monthly.
   CFA model validation is a methodology reference. Damodaran is for valuation
   review, not the comparison feature. No 13F or Congress copy-trading.
5. Research eligibility floors, not statistical power: at least three
   chronologically disjoint OOS folds and at least 30 covered episodes per
   arm per fold (180 distinct eligible episodes is necessary for three folds).
   `research_oos_admission.assess_oos_readiness` verifies this structure on
   caller-supplied rows. It takes a chronological official session list, ordered
   inclusive fold start/end pairs, and unique episodes with a signal session,
   last verified session, Boolean PIT coverage, event flag and stop-contact
   outcome. The full original 15 subsequent sessions must be verified, even
   for an early touch. Outcomes crossing a fold edge do not count in that
   fold. This does not authenticate the input or fit a model.
   Exclude overlapping unresolved 15-session labels from the training edge.
   Measure dependence across issuer and session, report a
   cluster-robust 95% interval, and check effect stability by fold. The interval
   must exclude zero and the finding must survive cost and ambiguity sensitivity
   before it merits further research. These are not trading approval criteria.
   No claim until actual point-in-time cohort, coverage, and outcomes exist.

## Verification

Normal and optimized Python use the existing required read-only CI target via
`test_research_evidence`; no CI change required. Public source facts used in
fixtures are manual examples, not authenticated live captures. No automatic
merge or production promotion. Rollback: abandon the draft before merge.

Sources: [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces),
[SEC Fair Access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data),
[ALFRED vintage dates](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html),
[Fed calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm),
[BLS releases](https://www.bls.gov/schedule/news_release/),
[AQR QMJ](https://www.aqr.com/Insights/Datasets/Quality-Minus-Junk-Factors-Daily),
[CFA model validation](https://rpc.cfainstitute.org/research/foundation/2024/investment-model-validation).
