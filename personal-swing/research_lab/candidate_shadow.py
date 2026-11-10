#!/usr/bin/env python3
"""No-network, no-LLM, no-vendor-API XRAY candidate integration boundary.

Processes only caller-supplied synthetic/offline JSON. Never imports a candidate
SDK. Refuses capability escalation and never issues AL, orders, alerts, or writes.
This is an interface-contract prototype, NOT an executed SDK integration.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import math
import re
from typing import Any
from candidate_guard import validate, EXPECTED_URLS

RECORD_SCHEMA = 'XRAY_RESEARCH_EVIDENCE_SHADOW_V1'
TOOL_SCHEMA = 'XRAY_MCP_TOOL_MANIFEST_OFFLINE_V1'
PROVIDER_SCHEMA = 'XRAY_PROVIDER_CONTRACT_OFFLINE_V1'
ALLOWED_TOOLS = frozenset({
    'get_sec_filing_metadata', 'get_public_repository_metadata',
    'get_official_release_notes', 'get_openbb_provider_schema'
})
ALLOWED_STATUS = frozenset({'DOCS_VERIFIED', 'OFFLINE_MOCK_PASS', 'HOLD'})
SHA_PATTERN = re.compile(r'^[0-9a-f]{40}$')
SYMBOL_PATTERN = re.compile(r'^[A-Z][A-Z0-9.]{0,14}$')


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _date_only(raw: Any, code: str) -> date:
    require(type(raw) is str, code)
    try:
        value = date.fromisoformat(raw)
        require(value.isoformat() == raw, code)
        return value
    except ValueError as exc:
        raise ValueError(code) from exc


def _utc(raw: Any) -> datetime:
    require(type(raw) is str and raw.endswith('Z'), 'TIMESTAMP_NOT_UTC')
    try:
        parsed = datetime.fromisoformat(raw[:-1] + '+00:00')
    except ValueError as exc:
        raise ValueError('INVALID_TIMESTAMP') from exc
    require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
            'TIMESTAMP_NOT_UTC')
    require(parsed.isoformat(timespec='seconds').replace('+00:00','Z') == raw,
            'TIMESTAMP_NOT_CANONICAL')
    return parsed


def _candidate_index(manifest: dict) -> dict:
    validate(manifest)
    return {c['id']: c for c in manifest['candidates']}


def validate_offline_observation(manifest: dict, observation: dict) -> dict:
    """Rejects fabricated live/PIT/production statuses and wrong source pins."""
    index = _candidate_index(manifest)
    require(type(observation) is dict and observation.get('schema') == RECORD_SCHEMA,
            'EVIDENCE_SCHEMA_INVALID')
    candidate = observation.get('candidate_id')
    require(type(candidate) is str and candidate in index, 'UNKNOWN_CANDIDATE')
    require(observation.get('source_url') == EXPECTED_URLS[candidate],
            'EVIDENCE_SOURCE_URL_MISMATCH')
    require(observation.get('source_sha') == index[candidate]['upstream_snapshot_sha'],
            'EVIDENCE_SOURCE_SHA_MISMATCH')
    require(observation.get('status') in ALLOWED_STATUS, 'UNAUTHORIZED_STATUS')
    require(observation.get('mode') == 'OFFLINE_FIXTURE_ONLY',
            'EXTERNAL_RUNTIME_NOT_AUTHORIZED')
    _date_only(observation.get('asof_et'), 'INVALID_ASOF')
    observed = _utc(observation.get('observed_at_utc'))
    require(observed.date() >= date.fromisoformat(observation['asof_et']),
            'OBSERVED_BEFORE_ASOF')
    evidence = observation.get('evidence')
    require(type(evidence) is dict and len(evidence) <= 20, 'INVALID_EVIDENCE')
    # Literal data only: do not deserialize arbitrary objects or act on URLs.
    require(all(type(k) is str and len(k) <= 80 for k in evidence),
            'INVALID_EVIDENCE_KEY')
    require(all(type(v) in (str, int, float, bool, type(None)) and
                not (type(v) is float and not math.isfinite(v)) and
                (type(v) is not str or len(v) <= 2000)
                for v in evidence.values()), 'INVALID_EVIDENCE_VALUE')
    for flag in ('may_generate_al', 'may_write_private_sheet', 'may_emit_alert',
                 'may_place_order', 'may_fetch_vendor_api', 'model_executed'):
        require(observation.get(flag) is False, 'AUTHORITY_ESCALATION_' + flag)
    return {
        'schema': RECORD_SCHEMA, 'candidate_id': candidate,
        'source_sha': index[candidate]['upstream_snapshot_sha'],
        'status': observation['status'], 'result': 'OFFLINE_EVIDENCE_SHAPE_PASS_ONLY',
        'production_authorized': False, 'live_data_verified': False,
        'may_generate_al': False, 'may_place_order': False,
    }


def audit_mock_mcp_tools(payload: dict) -> dict:
    """Static mock tool-list gate; does not connect to or run an MCP server."""
    require(type(payload) is dict and payload.get('schema') == TOOL_SCHEMA,
            'MCP_MANIFEST_INVALID')
    require(payload.get('mode') == 'MOCK_METADATA_ONLY', 'MCP_LIVE_CONNECT_DENIED')
    require(payload.get('candidate_id') in ('mcp-use', 'openbb-mcp', 'alpaca-mcp'),
            'UNKNOWN_MCP_CANDIDATE')
    tools = payload.get('tools')
    require(type(tools) is list and len(tools) <= 20, 'INVALID_MCP_TOOLS')
    names = set()
    for item in tools:
        require(type(item) is dict and set(item) == {'name','read_only','side_effects'},
                'MCP_TOOL_FIELDS_INVALID')
        name = item.get('name')
        require(type(name) is str and name in ALLOWED_TOOLS, 'MCP_TOOL_DENIED')
        require(name not in names, 'DUPLICATE_MCP_TOOL')
        names.add(name)
        require(item.get('read_only') is True and item.get('side_effects') is False,
                'MCP_SIDE_EFFECT_DENIED')
    # Some MCP server manifests may hide capabilities behind prompts/resources;
    # this check only certifies a caller-supplied mock list, not a real server.
    return {'status':'MOCK_MCP_ALLOWLIST_PASS_ONLY', 'checked_tools':len(names),
            'connected_server':False, 'server_credentials_checked':False,
            'may_place_order':False, 'production_authorized':False}


def audit_local_provider_contract(payload: dict) -> dict:
    """Detects PIT/venue/basis claims; no market prices ingested."""
    require(type(payload) is dict and payload.get('schema') == PROVIDER_SCHEMA,
            'PROVIDER_SCHEMA_INVALID')
    require(payload.get('mode') == 'OFFLINE_FIXTURE_ONLY', 'PROVIDER_LIVE_DENIED')
    require(payload.get('candidate_id') in ('openbb-v5', 'qlib'),
            'WRONG_PROVIDER_CANDIDATE')
    asof = _date_only(payload.get('asof_et'), 'INVALID_ASOF')
    cutoff = _utc(payload.get('decision_cutoff_utc'))
    seen = _utc(payload.get('known_at_utc'))
    require(cutoff.date() >= asof, 'ASOF_AFTER_DECISION_CUTOFF')
    require(seen <= cutoff, 'PIT_LOOKAHEAD')
    symbol = payload.get('symbol')
    require(type(symbol) is str and SYMBOL_PATTERN.fullmatch(symbol) is not None,
            'INVALID_SYMBOL')
    require(payload.get('venue') in ('IEX', 'US_CONSOLIDATED'), 'UNKNOWN_VENUE')
    require(payload.get('basis') in ('RAW','SPLIT_ADJUSTED','SPLIT_DIVIDEND_ADJUSTED'),
            'UNKNOWN_ADJUSTMENT_BASIS')
    require(payload.get('rights_independently_verified') is False,
            'UNAUTHORIZED_RIGHTS_CERTIFICATION')
    # Different tape or adjustment is NOT an alternative canonical IEX bar.
    comparable = payload.get('venue') == 'IEX' and payload.get('basis') == 'RAW'
    return {'status': 'MOCK_CONTRACT_ONLY_HOLD_PRODUCTION',
            'candidate_id': payload['candidate_id'], 'ticker': symbol,
            'canonical_contract_compatible_claim': comparable,
            'rights_independently_verified':False,
            'market_data_fetched':False, 'production_authorized':False}


def main() -> int:
    """One-shot CLI accepts a local manifest plus local fixture; no side effects."""
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['evidence','mcp-tools','provider'])
    parser.add_argument('--fixture', required=True)
    parser.add_argument('--manifest', default=str(Path(__file__).with_name('candidate_manifest.json')))
    args = parser.parse_args()
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
        validate(manifest)
        payload = json.loads(Path(args.fixture).read_text(encoding='utf-8'))
        if args.operation == 'evidence':
            result = validate_offline_observation(manifest, payload)
        elif args.operation == 'mcp-tools':
            result = audit_mock_mcp_tools(payload)
        else:
            result = audit_local_provider_contract(payload)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({'status':'HOLD', 'reason':str(exc)},sort_keys=True))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
