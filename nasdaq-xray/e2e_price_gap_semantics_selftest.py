#!/usr/bin/env python3
"""Live current source-gap diagnostic regression. Never creates trading PASS."""
from e2e_production_readiness import snapshot,read,scope_readiness
def selftest():
    p=read("canonical_current_price_dv30.json")
    o=snapshot()
    blocks=set(o["blockers"])
    unknown=p.get("unknown_count")
    blocked=p.get("blocked_count")
    assert ("PRICE_UNKNOWN_CURRENT" in blocks)==(unknown!=0), (
        "UNKNOWN_CURRENT_MERGED_INTO_BLOCKED_COUNT")
    assert ("PRICE_BLOCKED_30_SESSION_BARS" in blocks)==(blocked!=0), (
        "PRICE_BLOCKED_REPORTED_WHEN_REAL_BLOCKED_COUNT_ZERO")
    assert o["price_blocked_count"]==blocked
    # A valid empty PASS set is not a broken count. Zero != missing key.
    m=read("canonical_current_master_manifest.json")
    same_partition=(
        p.get("asof_et")==m.get("asof_et")
        and p.get("source_master_queue_hash")==m.get("queue_hash")
        and p.get("source_master_count")==m.get("queue_total")
        and set(p.get("results") or {})==set(m.get("pass_symbols") or [])
        and int(p.get("pass_count",-1))==len(p.get("pass_symbols") or [])
    )
    if same_partition and p.get("pass_count")==0:
        assert "PRICE_PARTITION_NOT_EXACT_CURRENT" not in blocks, (
            "VALID_ZERO_PASS_PARTITION_MISLABELLED_INVALID")

    assert not o["ready_for_current_research_signal"] or (
        o["candidate_local_source_chain_attested"] is True)
    assert scope_readiness(["PRICE_UNKNOWN_CURRENT"],True)["full_universe_source_coverage_attested"] is False
    assert scope_readiness(["PRICE_UNKNOWN_CURRENT"],True)["candidate_local_source_chain_attested"] is True
    assert o["actual_device_delivery_receipt_attested"] is False
    print("XRAY_E2E_PRICE_GAP_SELFTEST=PASS_UNKNOWN_SEPARATE_BLOCKED_ZERO_ALPHA")
if __name__=="__main__":
    selftest()
