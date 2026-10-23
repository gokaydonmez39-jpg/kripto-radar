#!/usr/bin/env python3
"""XRAY A0 rights-evidence INTAKE audit, OFFLINE SHADOW, never legal authorization.

This records only sanitized evidence *metadata*; it never accepts accounts,
credentials, contracts, person names, paid data or private agreement text.
No external source can be independently authenticated from a caller's JSON:
even all submitted evidence never authorizes a market-data request.
Original refs: RT-260 RT-247 RT-248 RT-243 in XRAY v42 gate catalog.
"""
from __future__ import annotations
import argparse
from datetime import date
import json
from pathlib import Path
import re

SCHEMA = 'XRAY_V45_A0_EVIDENCE_INTAKE_SHADOW_V1'
CATALOG_SCHEMA = 'XRAY_V42_CURATED_SOURCE_TO_GATE_CONTRACT_V1'
SOURCES = ('RT-260', 'RT-247', 'RT-248', 'RT-243')
CLAIMS = (
    'account_specific_plan_and_feed',
    'historical_sip_trades_quotes_and_bars',
    'unattended_github_runner_processing',
    'non_display_usage_classification',
    'private_cache_and_retention',
    'public_or_mobile_derived_outputs',
    'full_cancel_correction_replay_provision',
)
STATUSES = ('MISSING', 'SUBMITTED_UNREVIEWED', 'PROVIDER_DENIED')
ASOF = date(2026, 10, 23)

class RightsBlocked(ValueError):
    pass


def require(cond: bool, reason: str) -> None:
    if cond is not True:
        raise RightsBlocked('XRAY_V45_' + reason)


def _day(s: str) -> date:
    require(type(s) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', s) is not None,
            'DATE_FORMAT')
    try:
        d = date.fromisoformat(s)
    except ValueError as e:
        raise RightsBlocked('XRAY_V45_DATE_INVALID') from e
    require(d.isoformat() == s and d <= ASOF, 'FUTURE_DATE')
    return d


def audit(metadata: dict) -> dict:
    """Fail-closed intake check; metadata is not a credential or legal grant."""
    require(type(metadata) is dict and set(metadata) == {
        'schema', 'asof_date', 'catalog_schema', 'provider', 'usage',
        'catalog_source_ids', 'claims'}, 'DOCUMENT_SHAPE')
    require(metadata['schema'] == SCHEMA and metadata['asof_date'] == ASOF.isoformat(),
            'FIXED_EPOCH')
    require(metadata['catalog_schema'] == CATALOG_SCHEMA and
            metadata['catalog_source_ids'] == list(SOURCES), 'UPSTREAM_PROVENANCE')
    require(metadata['provider'] == 'ALPACA' and
            metadata['usage'] == 'PRIVATE_PERSONAL_RESEARCH_UNATTENDED_RUNNER',
            'EXACT_USAGE_AND_PROVIDER')
    claims = metadata['claims']
    require(type(claims) is dict and set(claims) == set(CLAIMS), 'CLAIM_SET')
    counts = {k: 0 for k in STATUSES}
    missing = []
    denied = []
    for claim in CLAIMS:
        item = claims[claim]
        require(type(item) is dict and set(item) == {
            'status', 'document_sha256', 'document_date'}, 'CLAIM_SHAPE')
        status = item['status']
        require(type(status) is str and status in STATUSES, 'CLAIM_STATUS')
        fingerprint = item['document_sha256']
        docdate = item['document_date']
        if status == 'MISSING':
            require(fingerprint is None and docdate is None, 'EMPTY_CLAIM_METADATA')
            missing.append(claim)
        else:
            require(type(fingerprint) is str and
                    re.fullmatch(r'[a-f0-9]{64}', fingerprint) is not None,
                    'DOCUMENT_FINGERPRINT_ONLY')
            _day(docdate)
            if status == 'PROVIDER_DENIED':
                denied.append(claim)
        counts[status] += 1
    decision = ('BLOCKED_PROVIDER_DENIAL' if denied else
                'BLOCKED_MISSING_USER_APPLICABLE_EVIDENCE' if missing else
                'BLOCKED_AWAIT_EXTERNAL_ENTITLEMENT_REVIEW')
    # An arbitrary SHA never verifies the source, effective contract, signatory,
    # usage fees, legal applicability, or whether the end user is a subscriber.
    # Never hash or output sensitive source documents, IDs, or raw vendor data.
    return {
        'schema': 'XRAY_V45_A0_RIGHTS_EVIDENCE_RESEARCH_RESULT_V1',
        'asof_date': ASOF.isoformat(),
        'status': decision,
        'claim_count': len(CLAIMS),
        'missing_claims': missing,
        'denied_claims': denied,
        'submitted_unreviewed_count': counts['SUBMITTED_UNREVIEWED'],
        'independent_provider_entitlement_attested': False,
        'lawful_unattended_runner_use_attested': False,
        'non_display_and_retention_rights_attested': False,
        'a0_release_ready': False,
        'may_run_vendor_historical_backfill': False,
        'source_claims_are_not_legal_approval': True,
        'a1_release_ready': False,
        'a2_pagination_complete': False,
        'a3_trade_correction_complete': False,
        'canonical_price_pass': False,
        'issuer_mc_pass': False,
        'g9_pass': False,
        'c417_pass': False,
        'registered_r92_count': 0,
        'iphone_receipt_attested': False,
        'execution': 'NONE',
        'real_money': 'NO-GO',
        'broker': False,
        'orders': [],
        'unknown_never_pass': True,
    }


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument('metadata_file',type=Path)
    args=p.parse_args()
    obj=json.loads(args.metadata_file.read_text(encoding='utf-8'))
    print(json.dumps(audit(obj),sort_keys=True,ensure_ascii=False))

if __name__ == '__main__':
    main()