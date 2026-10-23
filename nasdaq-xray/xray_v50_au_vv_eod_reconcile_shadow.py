#!/usr/bin/env python3
"""XRAY v50: strictly synthetic, provider-vs-UTP A3 EOD scope acceptance.

UTP 2025 v3.0a AU is per issue (multiple preliminary/final reports),
VV is cumulative for ALL Nasdaq issues. Fractional shares are scaled to
1,000,000 integer units. Provider bar/auction is NOT independent settled SIP.
This offline *thought experiment* never creates provider rights or price/R92 GO.

Official historical reference: https://utpplan.com/DOC/UtpBinaryOutputSpec-3.0a.pdf
Compare to archived current v4.1 RT-242 before actual provider implementation.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
import re
from typing import Any

SCHEMA = 'XRAY_V50_A3_SYNTHETIC_EOD_AU_VV_SCOPE_V1'
SAMPLE = 'SYNTHETIC_REFERENCE_ONLY_NO_SIP_DATA'
SOURCE = 'https://utpplan.com/DOC/UtpBinaryOutputSpec-3.0a.pdf'
AUCTION_DOC = 'https://docs.alpaca.markets/us/v1.1/reference/stockauctionsingle-1'
PHASES = ('INITIAL_PRELIMINARY', 'SECOND_PRELIMINARY', 'FINAL_AFTER_END_TRADE_REPORTING')


class EODScopeBlocked(ValueError):
    pass


def require(p: bool, code: str) -> None:
    if p is not True:
        raise EODScopeBlocked('XRAY_V50_' + code)


def micros(n: Any, label: str) -> int:
    # Never float shares (SIP fractional trade precision is up to 6 decimals).
    require(type(n) is int and 0 <= n < 1_000_000_000_000_000_000, label)
    return n


def keys(obj: Any, want: set[str], code: str) -> None:
    require(type(obj) is dict and set(obj) == want, code)


def audit(doc: Any) -> dict:
    keys(doc, {'schema','sample_type','utp_spec','auction_doc','symbol',
               'session_day','et_open','et_close','synthetic_replay',
               'utp_issue_summaries','utp_all_issues_snapshot',
               'provider_auction','actual_evidence_attested'}, 'DOC_FIELDS')
    require(doc['schema'] == SCHEMA and doc['sample_type'] == SAMPLE and
            doc['utp_spec'] == SOURCE and doc['auction_doc'] == AUCTION_DOC,
            'SOURCE_AND_SYNTHETIC_PROVENANCE')
    require(doc['symbol'] == 'AAPL' and type(doc['symbol']) is str,
            'FIXTURE_SYMBOL_SCOPE')
    when = doc['session_day']
    require(type(when) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', when) is not None,
            'FIXTURE_DAY_FORMAT')
    try:
        d = date.fromisoformat(when)
    except ValueError as exc:
        raise EODScopeBlocked('XRAY_V50_FIXTURE_DATE_INVALID') from exc
    require(d.isoformat() == when and when == '2026-10-22' and d.weekday() < 5,
            'FIXTURE_EPOCH')
    require(doc['et_open'] == '09:30' and doc['et_close'] == '16:00',
            'RTH_CLOCK_SCOPE')
    require(doc['actual_evidence_attested'] is False, 'FALSE_EXTERNAL_ATTESTATION')

    sample = doc['synthetic_replay']
    terms = {'original_microshares','canceled_microshares',
             'corrected_delta_microshares','net_all_hours_microshares',
             'extended_hours_microshares','rth_continuous_microshares',
             'closing_auction_microshares','rth_including_auction_microshares'}
    keys(sample, terms, 'REPLAY_FIELDS')
    for k in terms:
        micros(sample[k], 'INTEGER_MICROSHARES_'+k)
    require(sample['canceled_microshares'] <= sample['original_microshares'],
            'CANCEL_GT_ORIGINAL')
    net = (sample['original_microshares'] - sample['canceled_microshares'] +
           sample['corrected_delta_microshares'])
    require(net == sample['net_all_hours_microshares'], 'NET_CORRECTION_MATH')
    rth = sample['rth_continuous_microshares'] + sample['closing_auction_microshares']
    require(rth == sample['rth_including_auction_microshares'],
            'AUCTION_DOUBLE_COUNT_OR_MISSING')
    require(rth + sample['extended_hours_microshares'] == net,
            'RTH_VS_ALL_HOURS_SCOPE')

    reports = doc['utp_issue_summaries']
    require(type(reports) is list and len(reports) == len(PHASES),
            'ALL_THREE_ISSUE_SUMMARIES_REQUIRED')
    volumes = []
    for idx, record in enumerate(reports):
        keys(record, {'category','message_type','scope','issue','session_day',
                      'phase','volume_microshares','synthetic_end_report_control_seen'},
             'ISSUE_SUMMARY_FIELDS')
        require(record['category'] == 'A' and record['message_type'] == 'U' and
                record['scope'] == 'ISSUE_FULL_REPORTED_DAY' and
                record['issue'] == doc['symbol'] and record['session_day'] == when,
                'ISSUE_AU_MESSAGE_SCOPE')
        require(record['phase'] == PHASES[idx], 'ISSUE_REPORT_PHASE_ORDER')
        require(record['synthetic_end_report_control_seen'] is (idx == 2),
                'FINAL_REQUIRES_END_TRADE_REPORTING')
        volumes.append(micros(record['volume_microshares'], 'ISSUE_SUMMARY_VOLUME'))
    # Early phases need not be monotonic: real late cancels/corrections can reduce it.
    require(volumes[-1] == net, 'FINAL_ISSUE_VOLUME_VS_CORRECTED_REPLAY')

    vv = doc['utp_all_issues_snapshot']
    keys(vv, {'category','message_type','scope','session_day','volume_microshares'},
         'ALL_ISSUES_FIELDS')
    require(vv['category'] == 'V' and vv['message_type'] == 'V' and
            vv['scope'] == 'ALL_NASDAQ_ISSUES_ALL_MARKETS' and
            vv['session_day'] == when, 'VV_ALL_ISSUES_NOT_SYMBOL_SCOPE')
    micros(vv['volume_microshares'], 'VV_VOLUME')
    # Never compare VV aggregate to one stock, even if numeric values coincide.

    auction = doc['provider_auction']
    keys(auction, {'source','scope','issue','session_day','volume_microshares',
                   'real_auction_trade_ids_matched'}, 'AUCTION_FIELDS')
    require(auction['source'] == 'ALPACA_HISTORICAL_AUCTIONS_SYNTHETIC' and
            auction['scope'] == 'ONE_ISSUE_CLOSING_AUCTION' and
            auction['issue'] == doc['symbol'] and auction['session_day'] == when and
            auction['real_auction_trade_ids_matched'] is False,
            'PROVIDER_AUCTION_IS_NOT_OFFICIAL_TRADE_MATCH')
    require(micros(auction['volume_microshares'], 'AUCTION_VOLUME') ==
            sample['closing_auction_microshares'], 'AUCTION_COMPONENT_MISMATCH')
    require(auction['volume_microshares'] <= rth, 'AUCTION_GT_RTH')
    raw = json.dumps(doc,sort_keys=True,separators=(',', ':'),ensure_ascii=False)
    return {
        'schema': 'XRAY_V50_A3_SYNTHETIC_RECONCILIATION_RESEARCH_ONLY_V1',
        'status': 'SYNTHETIC_SCOPE_AND_MATH_ONLY_NO_EXTERNAL_EVIDENCE',
        'symbol': doc['symbol'], 'session_day': when,
        'fractional_unit': 'MICROSHARES_1E6_INTEGER',
        'three_synthetic_au_phases_checked': True,
        'synthetic_end_trading_report_final_required': True,
        'vv_all_issues_is_not_one_issue_reference': True,
        'rth_closing_auction_counted_once': True,
        'rth_and_all_hours_have_distinct_denominators': True,
        'synthetic_net_corrections_arithmetic_checked': True,
        'synthetic_reference_sha256': sha256(raw.encode()).hexdigest(),
        'real_utp_au_final_received': False,
        'real_utp_vv_received': False,
        'independent_real_per_issue_reference_verified': False,
        'actual_correction_lineage_and_source_coverage_verified': False,
        'actual_provider_auction_verified': False,
        'legal_non_display_entitlement_verified': False,
        'official_session_and_venue_verified': False,
        'official_2026_utp_spec_runtime_mapping_verified': False,
        'actual_90_symbol_session_completeness_verified': False,
        'a0_release_ready': False, 'a1_release_ready': False,
        'a2_release_ready': False, 'a3_release_ready': False,
        'canonical_price_pass': False, 'issuer_mc_pass': False,
        'g9_pass': False, 'c417_pass': False, 'registered_r92_count': 0,
        'iphone_receipt_attested': False, 'broker': False, 'orders': [],
        'execution': 'NONE', 'real_money': 'NO-GO', 'unknown_never_pass': True,
    }


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser()
    parser.add_argument('fixture',type=Path)
    args=parser.parse_args()
    print(json.dumps(audit(json.loads(args.fixture.read_text(encoding='utf-8'))),
                     indent=2, sort_keys=True))