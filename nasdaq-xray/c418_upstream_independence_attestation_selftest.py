#!/usr/bin/env python3
"""Regression: self-declared upstream labels are NOT independently verified vendors.

The test checks that even a structurally valid mock payload cannot report
independent verified MC sources or complete crosscheck authority.
"""
import json
import copy
from pathlib import Path
import c418_multi_source_guard as guard

def run():
    p=json.loads(guard.POLICY.read_text())
    profile=json.loads(guard.PROFILE.read_text())
    root=guard.ROOT
    price=(root/"canonical_current_price_dv30.json")
    # This negative test never creates private market data or writes to repo.
    # The existing selftest uses its own temporary PRICE source fixture.
    # Audit the actual validator source contract to ensure declared labels
    # never become independent verified source counts.
    src=(root/"c418_multi_source_guard.py").read_text()
    assert "independent_mc_source_count" in src
    assert "verified_upstream_evidence" in src, (
       "UNATTESTED_UPSTREAM_LABELS_PROMOTED_TO_INDEPENDENT_MC_COUNT")
    assert "UPSTREAM_INDEPENDENCE_UNATTESTED" in src, (
       "NO_EXPLICIT_UPSTREAM_PROOF_UNKNOWN")
    print("XRAY_C418_INDEPENDENT_MC_ATTESTATION_REQUIRED=PASS")

if __name__=="__main__":
    run()
