#!/usr/bin/env python3
"""Authenticated old Massive report-period records must be discarded, never replayed."""
import copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import massive_mc_resume_shadow as mc
import massive_mc_shadow_probe as probe
def main():
    scope={"asof_et":"2026-10-09","symbols":["TEST"],"scope_hash":"fake-scope",
           "price_blob_sha":"fake-price","master_price_content_binding_exact":True}
    f=mc.make_fernet("unit-test-legacy-fake-secret-32characters-long")
    old=mc.fresh_checkpoint(scope)
    rec=mc.clean_record("TEST",scope["asof_et"],probe.classify("TEST",{
        "ticker":"TEST","active":True,"market":"stocks","primary_exchange":"XNAS",
        "type":"CS","currency_name":"usd","cik":"0000123456","market_cap":2_300_000_000}))
    rec["source"]="MASSIVE_REFERENCE_TICKER_OVERVIEW_PIT"
    rec.pop("filing_acceptance_pit_attested")
    rec.pop("possible_historical_filing_lookahead")
    old["records"]["TEST"]=rec
    old["request_count_cumulative"]=1
    assert not mc.exact_checkpoint(old,scope)
    crypt=f.encrypt(json.dumps(old,sort_keys=True).encode())
    fresh,reused=mc.restore(crypt,f,scope)
    assert reused is False and fresh["records"]=={} and fresh["request_count_cumulative"]==0
    assert mc.checkpoint_candidate_state(crypt,f,scope)=="STALE"
    # Legacy authenticated data MUST NOT transfer vendor market_cap into new checkpoint.
    assert "2300000000" not in json.dumps(fresh)
    for label,mutate in (
        ("alpha",lambda d:d.update(alpha_authority=True)),
        ("policy",lambda d:d.update(policy_unchanged="C4.18")),
        ("source",lambda d:d["records"]["TEST"].update(source="MASSIVE_UNRELATED")),
        ("mixed_semantics",lambda d:d["records"]["TEST"].update(filing_acceptance_pit_attested=True)),
        ("missing_scope",lambda d:d.update(price_blob_sha="WRONG")),
    ):
        changed=copy.deepcopy(old);mutate(changed)
        broken=f.encrypt(json.dumps(changed,sort_keys=True).encode())
        try:
            got,_=mc.restore(broken,f,scope)
            # A mismatched exact SHA may be treated as an authenticated stale epoch.
            if label=="missing_scope":
                assert got["records"]=={};continue
        except ValueError:
            continue
        raise AssertionError("WRONG_LEGACY_CHECKPOINT_ACCEPTED:"+label)
    try:mc.restore(crypt[:-10]+b"tampered",f,scope)
    except ValueError:pass
    else:raise AssertionError("TAMPERED_CIPHERTEXT_ACCEPTED")
    print("XRAY_MASSIVE_LEGACY_REPORT_DATE=AUTHENTICATED_STALE_DISCARD_NO_MC_REUSE_6_NEGATIVES")
if __name__=="__main__":main()
