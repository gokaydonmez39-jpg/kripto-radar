#!/usr/bin/env python3
import build_current_identity_proofs as m

def main():
    assert m.parse_footer_date("File Creation Time: 1006202614:01|||||||")=="2026-10-06"
    a,s=m.proof_paths("2026-10-06")
    assert a.name=="master_asof_identity_proof_20261006.json"
    assert s.name=="master_sec_spac_proof_20261006.json"
    try:
        m.parse_footer_date("bad")
        raise AssertionError("bad footer accepted")
    except RuntimeError:
        pass
    print("XRAY_CURRENT_IDENTITY_PROOF_SELFTEST=PASS")

if __name__=="__main__":
    main()
