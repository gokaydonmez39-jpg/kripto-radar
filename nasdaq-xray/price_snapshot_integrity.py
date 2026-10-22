#!/usr/bin/env python3
"""Dependency-free, shared fail-closed C4.17 PRICE snapshot partition integrity."""
from __future__ import annotations
import hashlib


def price_snapshot_integrity(px,frozen_asof):
    """Structural integrity is not the same as resolver completeness.

    UNKNOWN/BLOCK_CURRENT_RUN are legitimate fail-closed intermediate states.
    Treat the snapshot as corrupt only when its safety/binding/count structure
    is internally inconsistent.
    """
    try:
        counts=px.get("counts") or {}
        results=px.get("results") or {}
        unknown=list(px.get("unknown_symbols") or [])
        blocked=list(px.get("blocked_symbols") or [])
        passes=list(px.get("pass_symbols") or [])
        source_count=int(px.get("source_master_count",-1))
        # Rebuild canonical partitions from every decision-bearing row.
        # Merely matching declared counts and subset membership can otherwise
        # admit a forged PASS row from a cached UNKNOWN baseline.
        statuses={}
        allowed={
          "PASS_PRICE_DV30","UNKNOWN","BLOCK_CURRENT_RUN",
          "FAIL_PRICE","FAIL_DV30","FAIL_PRICE_NO_ASOF_BAR",
          "FAIL_DV30_INSUFFICIENT_SESSIONS","BLOCK_POST_ASOF_LISTING",
        }
        for sym,row in results.items():
            if not isinstance(sym,str) or not isinstance(row,dict):
                return False
            state=row.get("status")
            if state not in allowed:
                return False
            statuses[state]=statuses.get(state,0)+1
        actual_unknown=sorted(sym for sym,row in results.items() if row["status"]=="UNKNOWN")
        actual_blocked=sorted(sym for sym,row in results.items() if row["status"]=="BLOCK_CURRENT_RUN")
        actual_passes=sorted(sym for sym,row in results.items() if row["status"]=="PASS_PRICE_DV30")
        if not isinstance(counts,dict) or any(type(n) is not int or n<0 for n in counts.values()):
            return False
        return bool(
          frozen_asof and px.get("asof_et")==frozen_asof
          and px.get("execution")=="NONE" and px.get("real_money")=="NO-GO"
          and px.get("unknown_never_pass") is True
          and source_count>0 and len(results)==source_count
          and counts==statuses
          and unknown==actual_unknown
          and blocked==actual_blocked
          and passes==actual_passes
          and type(px.get("unknown_count")) is int and px["unknown_count"]==len(actual_unknown)
          and type(px.get("blocked_count")) is int and px["blocked_count"]==len(actual_blocked)
          and type(px.get("pass_count")) is int and px["pass_count"]==len(actual_passes)
          and px.get("pass_hash")==hashlib.sha256("\n".join(actual_passes).encode()).hexdigest()
        )
    except Exception:
        return False
