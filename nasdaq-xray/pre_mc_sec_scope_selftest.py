#!/usr/bin/env python3
"""Red-green exact SEC full-file vs Nasdaq scope binding regression.

An exact-asof SEC proof file can validly contain rows not in today's Nasdaq
common-share membership. Only its applied subset excludes, but full-file
content, count and blob SHA must be bound in the current MASTER manifest.
No provider I/O, trading, market-cap or alpha PASS.
"""
from __future__ import annotations
from sina_stage import build_full_identity_from_directory,build_discovery_from_snapshot,sha_lines

def selftest():
    listed={"ACQS":"Acquisition Corp Ordinary shares","AAA":"Operating Inc"}
    proofs={
        "ACQS":{"sic":6770,"cik":"0000000001"},
        "OUTSIDE_NASDAQ":{"sic":6770,"cik":"0000000002"},
    }
    for builder in (
        lambda:build_full_identity_from_directory(listed,proofs,{}),
        lambda:build_discovery_from_snapshot(listed,{},proofs,{}),
    ):
        queue,discovery,meta,excluded=builder()
        assert queue==["AAA"],"SEC_ACTUAL_LISTED_BLANK_CHECK_NOT_EXCLUDED"
        assert set(excluded)=={"ACQS"},"SEC_NONLISTED_INVALID_EXCLUSION"
        assert meta["sec_spac_proof_count"]==len(proofs), (
            "BUG_SEC_PROOF_FILE_COUNT_CONFUSED_WITH_APPLIED_NASDAQ_SUBSET")
        assert meta["sec_spac_proof_hash"]==sha_lines(sorted(proofs)), (
            "BUG_SEC_PROOF_FULL_FILE_HASH_NOT_BOUND")
        assert meta["sec_spac_proof_applied_count"]==1
        assert meta["sec_spac_proof_applied_hash"]==sha_lines(["ACQS"])
    print("XRAY_PREMC_SEC_FULL_ARTIFACT_VS_APPLIED_SUBSET_SELFTEST=PASS_2_SCOPES_0_ALPHA")

if __name__=="__main__":
    selftest()
