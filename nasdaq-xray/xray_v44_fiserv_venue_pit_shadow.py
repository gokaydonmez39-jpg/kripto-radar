#!/usr/bin/env python3
"""XRAY A1/A5 narrow SEC evidence witness for the Fiserv FI->FISV listing transfer.

Sources: SEC 8-K filed 2025-10-29 (prospective), SEC 10-K filed
2026-02-19 (retrospective). This is NOT a daily security master or a
price/volume, license, order, R92 or trade execution authority.

Never use a subsequently filed disclosure to certify a historical decision.
"""
from __future__ import annotations
from datetime import date
import re

EVIDENCE = (
    {"source_id": "RT-240", "document": "SEC_8K", "published": "2025-10-29",
     "url": "https://www.sec.gov/Archives/edgar/data/798354/000119312525254670/d17957d8k.htm",
     "role": "CONTEMPORANEOUS_TRANSFER_PLAN_NOT_REALIZED"},
    {"source_id": "RT-263", "document": "SEC_10K", "published": "2026-02-19",
     "url": "https://www.sec.gov/Archives/edgar/data/798354/000079835426000009/fi-20251231.htm",
     "role": "RETROSPECTIVE_TRANSFER_CONFIRMATION"},
)
TRANSFER_DAY = date(2025, 11, 11)
PUBLIC_8K_DAY = date(2025, 10, 29)
PUBLIC_10K_DAY = date(2026, 2, 19)

class VenueEvidenceBlocked(ValueError):
    pass


def require(b: bool, label: str) -> None:
    if b is not True:
        raise VenueEvidenceBlocked('XRAY_V44_' + label)


def parse_date(value: str) -> date:
    require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) is not None,
            'ISO_DATE')
    try:
        parsed = date.fromisoformat(value)
    except ValueError as ex:
        raise VenueEvidenceBlocked('XRAY_V44_INVALID_DATE') from ex
    require(parsed.isoformat() == value, 'CANONICAL_DATE')
    return parsed


def audit(query: dict) -> dict:
    """Validate a narrow, read-only historical Fiserv *evidence* claim.

    ``evidence_published_by`` is the decision's knowledge cutoff, not a
    shortcut to reconstruct later-confirmed 2025 facts in a 2025 backtest.
    """
    require(type(query) is dict and set(query) == {
        'issuer_cik', 'issuer', 'session_date', 'decision_asof_date', 'scope'},
        'SCHEMA')
    require(query['issuer_cik'] == '0000798354' and query['issuer'] == 'Fiserv, Inc.',
            'ISSUER_ID')
    require(query['scope'] == 'US_LISTED_COMMON_STOCK', 'ISSUE_SCOPE')
    session = parse_date(query['session_date'])
    decision = parse_date(query['decision_asof_date'])
    require(PUBLIC_8K_DAY <= session <= date(2026, 10, 22),
            'BOUNDED_SCOPE')
    require(PUBLIC_8K_DAY <= decision <= date(2026, 10, 23),
            'DECISION_EPOCH')
    require(decision >= session, 'FUTURE_SESSION')
    require(session.weekday() < 5, 'WEEKEND_NOT_A_LISTING_SESSION')

    if session < TRANSFER_DAY:
        expected_symbol, expected_venue = 'FI', 'NYSE'
    else:
        expected_symbol, expected_venue = 'FISV', 'NASDAQ'

    # Contemporary 8-K publishes a *prospective* Nov 11 transfer, not
    # independent proof the transfer happened on that date.
    plan_known = decision > PUBLIC_8K_DAY
    realized_confirmed_at_decision = decision > PUBLIC_10K_DAY
    # 10-K on Feb19 2026 confirms *the transfer date*, not uninterrupted
    # each-day NASDAQ listing through Oct 2026. Daily historical security
    # master audit is still required (Nasdaq Daily List is a paid product).
    return {
        'schema': 'XRAY_V44_FISERV_PIT_VENUE_SHADOW_ONLY_V1',
        'issuer_cik': query['issuer_cik'],
        'session_date': session.isoformat(),
        'decision_asof_date': decision.isoformat(),
        'expected_symbol_from_transfer_document_research_only': expected_symbol,
        'expected_primary_listing_venue_research_only': expected_venue,
        'contemporaneous_plan_was_published_asof_decision': plan_known,
        'filing_intraday_acceptance_time_proven': False,
        'retrospective_transfer_confirmed_asof_decision': realized_confirmed_at_decision,
        'future_disclosure_excluded_from_historical_decision': not realized_confirmed_at_decision,
        'transfer_effective_date': TRANSFER_DAY.isoformat(),
        'listing_change_source_8k': EVIDENCE[0]['url'],
        'post_event_confirmation_source_10k': EVIDENCE[1]['url'] if realized_confirmed_at_decision else None,
        'post_event_confirmation_used_in_decision': realized_confirmed_at_decision,
        'daily_listing_master_complete': False,
        'all_historical_venue_sessions_attested': False,
        'cross_venue_260_session_replay_authorized': False,
        'official_market_calendar_individually_attested': False,
        'point_in_time_market_cap_attested': False,
        'source_data_licensing_rights_attested': False,
        'a1_release_ready': False,
        'canonical_price_pass': False,
        'issuer_mc_pass': False,
        'g9_pass': False,
        'c417_pass': False,
        'registered_r92_count': 0,
        'iphone_receipt_attested': False,
        'execution': 'NONE', 'real_money': 'NO-GO', 'broker': False, 'orders': [],
        'unknown_never_pass': True,
        'status': ('RETROSPECTIVE_TRANSFER_DATE_DOCUMENTED_DAILY_SCOPE_UNKNOWN'
                   if realized_confirmed_at_decision else
                   'CONTEMPORANEOUS_PLAN_ONLY_EXECUTION_UNCONFIRMED_ASOF'),
    }