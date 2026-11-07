#!/usr/bin/env python3
"""Fail-closed candidate preflight: never promotes a model, SDK or provider.

Uses only local catalogue statements. A source SHA is a reference, not an
installed package or a verified licence. This command never imports candidate
packages, reads credentials, uses the network, writes to GitHub/Sheets, or trades.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from candidate_guard import validate

# Frozen pre-registered checkpoints; nothing here can authorize production.
# Tests and code intentionally never accept caller-supplied 'PASS' overrides.
GATES = {
    'pydantic-ai': (
        'UPSTREAM_DEPENDENCY_AND_LICENSE_AUDIT',
        'REAL_SDK_OFFLINE_MODEL_TEST_NO_API',
        'SCHEMA_VALIDATION_VS_STDLIB_BASELINE',
        'TIME_MEMORY_AND_ZERO_COST_BUDGET',
        'ISOLATED_NO_SECRETS_RUNTIME_ATTESTATION',
    ),
    'mcp-use': (
        'UPSTREAM_DEPENDENCY_AND_LICENSE_AUDIT',
        'REAL_SDK_OFFLINE_MOCK_SERVER_SMOKE',
        'ALL_TOOL_RESOURCE_PROMPT_SURFACES_ENUMERATED',
        'TRANSPORT_AUTH_AND_NETWORK_DENY_VERIFIED',
        'ISOLATED_NO_SECRETS_RUNTIME_ATTESTATION',
    ),
    'qlib': (
        'UPSTREAM_DEPENDENCY_AND_LICENSE_AUDIT',
        'REAL_QLIB_RUNTIME_OFFLINE_SMOKE',
        'AT_LEAST_500_VERIFIED_XNAS_SESSIONS',
        'POINT_IN_TIME_AND_CORPORATE_ACTION_PROOF',
        'FIFTEEN_SESSION_PURGE_EMBARGO',
        'BENCHMARK_FEES_SLIPPAGE_AND_CHRONOLOGICAL_OOS',
    ),
    'openbb-v5': (
        'UPSTREAM_DEPENDENCY_AND_LICENSE_AUDIT',
        'REAL_OPENBB_SDK_OFFLINE_MOCK_SMOKE',
        'VENDOR_RIGHTS_AND_NO_COST_PROOF',
        'PIT_VENUE_RTH_RAW_AND_CORPORATE_ACTION_PROOF',
        'FULL_477_READ_ONLY_COMPARISON',
    ),
    'timesfm': (
        'SOURCE_LICENSE_AND_MODEL_WEIGHTS_LICENSE_VERIFIED',
        'EXACT_MODEL_HASH_CPU_MEMORY_BUDGET',
        'TIMESFM_RUNTIME_OFFLINE_SMOKE',
        'SAME_ASOF_PIT_HORIZON_VS_KRONOS',
        'INDEPENDENT_CHRONOLOGICAL_OOS',
    ),
    'openbb-mcp': (
        'OPENBB_V5_FEATURE_VERSION_PIN_AND_LICENSE',
        'OFFLINE_REAL_MCP_SERVER_WITHOUT_SECRETS',
        'NO_WRITE_TOOL_RESOURCE_PROMPT_SIDE_EFFECTS',
        'VENDOR_ACCESS_RIGHTS_AND_NETWORK_DENY',
    ),
    'alpaca-mcp': (
        'NO_ORDER_EVEN_PAPER_TRANSPORT_ISOLATION',
        'REAL_TOOL_ENUMERATION_NO_HIDDEN_ORDER_CAPABILITY',
        'DATA_ONLY_AUTH_AND_PIT_RIGHTS',
        'NO_SECRETS_EXPOSURE_IN_RESEARCH_RUNNER',
    ),
    'tradingview-charts': (
        'JS_BUNDLE_PIN_AND_LICENCE_ATTRIBUTION',
        'STATIC_OFFLINE_RENDER_NO_NETWORK',
        'NO_NEW_PROVIDER_FEED_OR_PRIVATE_EXPORT',
        'VISUAL_PARITY_AND_ACCESSIBILITY',
    ),
}

BLOCKERS = {
    'SDK_RUNTIME': 'Third-party SDK has not been installed or exercised in a no-secrets runner',
    'MARKET_PIT': 'Historical market provenance, event timing, legal rights and OOS evidence unavailable',
    'COST': 'Zero-new-spend / free runner capacity not independently demonstrated',
    'AUTHORITY': 'No tool/model may issue AL, alter STOP/2R, send alert, write private Sheets, or place orders',
    'ACTIVATION': 'Production promotion requires a separate owner approval and independent CI/readback',
}


def assess(manifest: dict) -> dict:
    validation = validate(manifest)
    # Validate verifies the exact source identities, policy and all 8 candidates.
    candidates = manifest['candidates']
    if set(GATES) != {c['id'] for c in candidates}:
        raise ValueError('RELEASE_GATE_COVERAGE_DRIFT')
    rows = []
    for c in candidates:
        source_sha = c.get('upstream_snapshot_sha')
        if not isinstance(source_sha, str) or len(source_sha) != 40 or any(x not in '0123456789abcdef' for x in source_sha):
            raise ValueError('UNPINNED_UPSTREAM_SOURCE_' + c['id'])
        rows.append({
            'id': c['id'], 'group': c['group'],
            'source_url': c['url'], 'snapshot_sha': source_sha,
            'existing_registry_key': c['existing_registry_key'],
            'ready_for_isolated_review': True,
            'runtime_sdk_verified': False,
            'vendor_pit_verified': False,
            'financial_alpha_verified': False,
            'production_authorized': False,
            'status': 'BLOCKED_PENDING_EXTERNAL_EVIDENCE',
            'required_independent_gates': list(GATES[c['id']]),
            'passed_independent_gates': [],
        })
    return {
        'schema': 'XRAY_NASDAQ_CANDIDATE_RELEASE_GATE_V1',
        'catalogue': validation['status'],
        'snapshot_date_tr': manifest['snapshot_date_tr'],
        'total': len(rows), 'research_review_ready': len(rows),
        'sdk_execution_pass': 0, 'live_pit_pass': 0,
        'production_authorized': 0, 'new_workflows_created': 0,
        'invariant': 'EXECUTION=NONE; NO_ORDER; NO_AL_STOP_CHANGE',
        'global_blockers': BLOCKERS.copy(),
        'candidates': rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', default=str(Path(__file__).with_name('candidate_manifest.json')))
    parser.add_argument('--require-production', action='store_true', help='Fail closed unless production admission independently proven; currently always HOLD')
    args = parser.parse_args()
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
        result = assess(manifest)
        # The command has no pathway to promote a candidate on self-claims.
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        if args.require_production:
            return 3
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({'status': 'HOLD', 'reason': str(exc)}, sort_keys=True))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
