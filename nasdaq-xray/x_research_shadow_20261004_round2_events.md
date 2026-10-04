# XRAY X Deep-Mining Shadow Research — 2026-10-04 / Round 2 Events

STATUS=SHADOW_RESEARCH_ONLY
PRODUCTION_ALPHA_CHANGE=NO
EXECUTION=NONE
REAL_MONEY=NO-GO
UNKNOWN_NEVER_PASS=TRUE

## X discovery accounts observed
### SEC Filings Digest
Handle: @USCorpFilings
Observed role: automated disclosure/event summaries, often linked to SEC/company filing material.
Classification: DISCOVERY_TRIGGER_ONLY
Potential tags:
- management_change
- merger_business_combination
- contract_termination
- product_launch
- investor_presentation
- capital_structure/share_authorization
- commercial_update
Guard: never clear or veto event risk from the X post itself; resolve ticker/CIK and verify the exact filing on SEC/issuer IR.

### FDA Tracker
Handle: @fda_tracker
Observed role: PDUFA-date discovery, sometimes linking directly to SEC filing evidence.
Classification: BIOTECH_CATALYST_DISCOVERY_ONLY
Guard: FDA does not publish a complete forward-looking PDUFA calendar; every candidate date must resolve to FDA notice, issuer filing or issuer release. Unknown month/quarter must remain a window, never invented exact day.

### Insider trading
Handle: @insider_daily
Observed role: Form 4 transaction discovery with transaction date / filing date / amount.
Classification: FORM4_DISCOVERY_ONLY
Guard: resolve to SEC Form 4 XML/filing before use; social post or Yahoo link is not authority.

### Stock Halt Alerts
Handle: @stockhaltalerts
Observed role: halt discovery.
Classification: HALT_DISCOVERY_ONLY
Guard: official Nasdaq Trader/primary exchange halt source is authority; social alert never clears/resolves a halt state.

## Event discovery architecture
X_POST
 -> HANDLE_TRUST_CLASS
 -> ENTITY/TICKER_RESOLUTION
 -> EVENT_TYPE_CLASSIFIER
 -> PRIMARY_SOURCE_RESOLVER
 -> TIMESTAMP_NORMALIZER
 -> EVENT_HORIZON_INTERSECTION
 -> CANDIDATE_IMPACT
 -> PASS / VETO / UNKNOWN

Hard rule:
NO_PRIMARY_SOURCE => UNKNOWN
SOCIAL_ONLY => NEVER_PASS
CONFLICTING_PRIMARY_SOURCES => UNKNOWN

## Free-event data candidates validated outside X
- SEC EDGAR official APIs/raw filing XML: free official authority with fair-access constraints; preferred for 8-K/10-Q/10-K/Form 4 and corporate disclosures.
- FDA official datasets/notices: authority for FDA actions/performance data, but no complete official forward-looking PDUFA calendar.
- Equibles self-hosted core: candidate local cache/index layer for SEC/XBRL/13F/FINRA/FRED/CFTC/CBOE/FDA discovery. It cannot replace primary-source verification.
- pdufa.bio: useful secondary discovery dataset with row-level source links; not primary authority.

## X ingestion constraint
Official X developer access is usage-priced in 2026; therefore a production dependency on the X API violates the project's permanent-$0/unlimited requirement.
Decision:
- interactive/web-index X mining = research/discovery;
- production event engine = SEC/Nasdaq/IR/FDA official + local cache;
- X event accounts = optional accelerator only when accessible at zero incremental cost;
- no TRUE_FULL_GO dependency on X.

## Smart automation enhancement candidate
Build a shadow EVENT_DISCOVERY_SCORE, never alpha:
- source_class: official_account / automated_filings_bot / analyst / community
- primary_link_present
- ticker_resolvable
- event_type_confidence
- timestamp_freshness
- duplicate_cluster_size
- cross-source corroboration
- primary_source_verified
Only primary_source_verified may promote an event fact into canonical evidence.

END.
