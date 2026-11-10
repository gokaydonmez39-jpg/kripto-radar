#!/usr/bin/env python3
"""ROKU delisting P0: independent, read-only admission diagnostic.

This *does not* repair the live EOD runner or release AL signals. It recognizes
one pinned, manually reviewed event and gives a deterministic reason to HOLD
until a replacement policy and a historical-episode treatment are approved.
The supplied data are inputs, not independently authenticated source receipts.
No HTTP, broker access, position updates, Sheets writes, or order routing.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re

import exchange_calendars as ec

UNIVERSE = 477
OLD_SYMBOL = 'ROKU'
SUCCESSOR_SECURITY = 'FOXA'
LAST_TRADING_DATE = '2026-11-06'
EFFECTIVE_ASOF = '2026-11-09'
CASH_USD_PER_SHARE = Decimal('95.30')
STOCK_RATIO = Decimal('0.9799')
NASDAQ_NOTICE = 'https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2026-806'
SEC_FILING = 'https://www.sec.gov/Archives/edgar/data/1428439/000119312526451874/d181620d8k.htm'
TICKER = re.compile(r'^[A-Z][A-Z0-9.]{0,14}$')
STATUS = 'P0_DELISTED_MEMBER_REPLACEMENT_REQUIRED'


class CorporateActionHold(ValueError):
    """Fail closed before authorizing any change to production decisions."""


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise CorporateActionHold(reason)


def valid_session(value: object) -> bool:
    if type(value) is not str or re.fullmatch(r'20\d{2}-\d{2}-\d{2}', value) is None:
        return False
    try:
        normalized = date.fromisoformat(value).isoformat()
        return normalized == value and bool(ec.get_calendar('XNAS').is_session(value))
    except (TypeError, ValueError, OverflowError):
        return False


def money(value: object, reason: str) -> Decimal:
    need(type(value) is str, reason)
    try:
        n = Decimal(value)
    except (InvalidOperation, TypeError):
        raise CorporateActionHold(reason) from None
    need(n.is_finite() and n > 0, reason)
    return n


def assess(watchlist: list[str], action: dict, provider: dict,
           episode: dict, *, asof_et: str) -> dict:
    """Assess only a pinned corporate event, without mutating any inputs.

    Exact 477 historical identities are preserved. The effective live set has
    476 active names and one unresolved member; this is not a 477/477 PASS.
    An existing FOXA issuer is never joined with ROKU's pre-merger price tape.
    """
    need(valid_session(asof_et), 'NOT_XNAS_SESSION')
    need(type(watchlist) is list and len(watchlist) == UNIVERSE,
         'EXACT_477_REQUIRED')
    need(all(type(s) is str and TICKER.fullmatch(s) for s in watchlist)
         and len(set(watchlist)) == UNIVERSE,
         'DUPLICATE_OR_INVALID_SCOPE')
    need(watchlist.count(OLD_SYMBOL) == 1, 'ROKU_SCOPE_MISMATCH')
    need(watchlist.count(SUCCESSOR_SECURITY) == 1, 'SUCCESSOR_SCOPE_MISMATCH')
    need(type(action) is dict and action.get('symbol') == OLD_SYMBOL
         and action.get('successor_security') == SUCCESSOR_SECURITY,
         'ACTION_IDENTITY_MISMATCH')
    need(action.get('last_trading_date') == LAST_TRADING_DATE
         and action.get('effective_asof_et') == EFFECTIVE_ASOF,
         'OFFICIAL_DATE_MISMATCH')
    need(action.get('nasdaq_notice') == NASDAQ_NOTICE
         and action.get('sec_filing') == SEC_FILING,
         'OFFICIAL_REFERENCE_MISMATCH')
    need(money(action.get('cash_usd_per_share'), 'MERGER_TERMS_NOT_PINNED')
         == CASH_USD_PER_SHARE
         and money(action.get('successor_shares_per_share'),
                   'MERGER_TERMS_NOT_PINNED') == STOCK_RATIO,
         'MERGER_TERMS_NOT_PINNED')
    need(type(episode) is dict
         and type(episode.get('asof_et')) is str
         and valid_session(episode['asof_et'])
         and episode['asof_et'] <= LAST_TRADING_DATE
         and episode.get('id') == episode['asof_et'] + '|ROKU'
         and episode.get('symbol') == OLD_SYMBOL
         and type(episode.get('status')) is str
         and episode['status'].startswith('AÇIK • '),
         'HISTORICAL_EPISODE_IDENTITY_INVALID')
    ref = money(episode.get('reference_close'), 'HISTORICAL_LEVELS_INVALID')
    stop = money(episode.get('original_stop'), 'HISTORICAL_LEVELS_INVALID')
    target = money(episode.get('original_target_2r'), 'HISTORICAL_LEVELS_INVALID')
    need(stop < ref < target and
         abs(target - (ref + 2 * (ref - stop))) <= Decimal('0.025'),
         'HISTORICAL_LEVELS_INVALID')
    need(type(provider) is dict and provider.get('symbol') == OLD_SYMBOL,
         'PROVIDER_SHAPE_INVALID')
    dates = provider.get('bar_dates')
    need(type(dates) is list and bool(dates) and
         all(valid_session(d) for d in dates) and
         dates == sorted(set(dates)), 'PROVIDER_SHAPE_INVALID')
    need(LAST_TRADING_DATE in dates, 'LAST_TRADING_BAR_MISSING')
    need(all(day <= LAST_TRADING_DATE for day in dates),
         'DELISTING_BAR_CONFLICT')
    # A present-day inactive provider record must never be backdated to a
    # pre-merger ASOF. Even for past dates we issue no independent EOD PASS.
    if asof_et < EFFECTIVE_ASOF:
        return {
            'schema': 'XRAY_PERSONAL_ROKU_CA_GATE_V1',
            'asof_et': asof_et,
            'status': 'NOT_EFFECTIVE_ASOF',
            'historical_universe_count': UNIVERSE,
            'active_tradable_count': UNIVERSE,
            'ready_for_477_eod': False,
            'allow_any_al_release': False,
            'source_evidence': 'REFERENCED_NOT_INDEPENDENTLY_VERIFIED_BY_CODE',
            'modify_watchlist': False,
            'write_sheets': False,
            'orders': False,
            'execution': 'NONE',
            'authorize_replay': False,
        }
    need(provider.get('asset_status') == 'inactive'
         and provider.get('tradable') is False,
         'ASSET_INACTIVITY_UNCONFIRMED')
    return {
        'schema': 'XRAY_PERSONAL_ROKU_CA_GATE_V1',
        'asof_et': asof_et,
        'status': STATUS,
        'historical_universe_count': UNIVERSE,
        'active_tradable_count': UNIVERSE - 1,
        'unresolved_slot_count': 1,
        'unresolved_episode_count': 1,
        'successor_already_in_scope': True,
        'merger_consideration': {'cash_usd': str(CASH_USD_PER_SHARE),
                                 'foxa_shares': str(STOCK_RATIO)},
        'episode_outcome': 'CORPORATE_ACTION_REVIEW_PENDING',
        'original_stop': str(episode['original_stop']),
        'original_target_2r': str(episode['original_target_2r']),
        'realized_return_pct': None,
        'ready_for_477_eod': False,
        'allow_any_al_release': False,
        'owner_approval_required': True,
        'source_evidence': 'REFERENCED_NOT_INDEPENDENTLY_VERIFIED_BY_CODE',
        'replacement_policy': 'MANUALLY_APPROVED_NEW_UNIQUE_52_SESSION_IEX_SECURITY_REQUIRED',
        'modify_watchlist': False,
        'write_sheets': False,
        'orders': False,
        'execution': 'NONE',
        'authorize_replay': False,
    }
