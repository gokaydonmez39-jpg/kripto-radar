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
    names={"INV":"Innventure, Inc. - Common Stock","TLAC":"Three Lions Acquisition Corp."}
    inds={"INV":"Industrial Products","TLAC":"Blank Checks"}
    op={"security_name":"old","evidence_date":"2026-09-21","source_url":"https://www.sec.gov/example"}
    blank={"cik":"0002128462","sic":6770,"classification":"Blank Checks","source_url":"https://www.sec.gov/example","evidence_date":"2026-09-01"}
    assert m.prior_operating_fallback("INV",op,"2026-10-06",names,inds)
    assert m.prior_operating_fallback("INV",op,"2026-10-06",names,{"INV":"Blank Checks"}) is None
    assert m.prior_blank_fallback("TLAC",blank,"2026-10-06",names,inds)
    assert m.prior_blank_fallback("TLAC",blank,"2026-10-06",names,{"TLAC":"Technology"}) is None
    print("XRAY_CURRENT_IDENTITY_PROOF_SELFTEST=PASS")

if __name__=="__main__":
    main()
