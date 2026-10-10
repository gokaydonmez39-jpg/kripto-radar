#!/usr/bin/env python3
"""Immutable SAME-ASOF Nasdaq identity fingerprint, not a mutable market-state hash.
This controls ONLY Sina support-plane retry cursors, never canonical authority.
"""
from __future__ import annotations
import hashlib
import json


def _lines_sha(rows):
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def frozen_identity_fingerprint(frozen: dict) -> str:
    if not isinstance(frozen, dict):
        raise ValueError("FROZEN_IDENTITY_NOT_OBJECT")
    queue=frozen.get("queue")
    names=frozen.get("security_names")
    discovery=frozen.get("discovery")
    unknown=frozen.get("identity_unknown_symbols")
    detail=frozen.get("identity_unknown_detail")
    if (not isinstance(queue,list) or not queue
        or not all(isinstance(s,str) and s for s in queue)
        or len(queue)!=len(set(queue))
        or frozen.get("queue_hash")!=_lines_sha(queue)
        or not isinstance(names,dict) or set(names)!=set(queue)
        or not isinstance(discovery,dict) or set(discovery)!=set(queue)
        or not isinstance(unknown,list) or len(unknown)!=len(set(unknown))
        or set(unknown)&set(queue)
        or not isinstance(detail,dict) or set(detail)!=set(unknown)):
        raise ValueError("FROZEN_IDENTITY_SET_OR_HASH_INVALID")
    if not all(isinstance(discovery[s],dict) for s in queue):
        raise ValueError("FROZEN_IDENTITY_DISCOVERY_INVALID")
    excluded=frozen.get("explicit_excluded_reason_counts")
    if not isinstance(excluded,dict):
        raise ValueError("FROZEN_EXCLUDED_REASONS_INVALID")
    # Deliberately exclude source_state_hash, raw price, volume, derived
    # MC/HISTORY and mutable research statuses. Preserve EVERY actual
    # identifier, name, industry, UNKNOWN and legal-exclusion input.
    payload={
      "queue":queue,"queue_hash":frozen["queue_hash"],
      "security_names":names,
      "industry_by_symbol":{s:discovery[s].get("industry") for s in queue},
      "identity_unknown_symbols":unknown,
      "identity_unknown_detail":detail,
      "official_footer":frozen.get("official_footer"),
      "identity_authority":frozen.get("identity_authority"),
      "explicit_excluded_count":frozen.get("explicit_excluded_count"),
      "explicit_excluded_hash":frozen.get("explicit_excluded_hash"),
      "explicit_excluded_reason_counts":excluded,
    }
    return hashlib.sha256(json.dumps(
      payload,sort_keys=True,separators=(",",":"),ensure_ascii=False
    ).encode("utf-8")).hexdigest()
