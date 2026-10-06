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
    op={"security_name":"Innventure, Inc. - Common Stock","evidence_date":"2026-09-21","source_url":"https://www.sec.gov/example"}
    blank={"cik":"0002128462","sic":6770,"classification":"Blank Checks","source_url":"https://www.sec.gov/example","evidence_date":"2026-09-01"}
    assert m.prior_operating_fallback("INV",op,"2026-10-06",names,inds)
    assert m.prior_operating_fallback("INV",op,"2026-10-06",names,{"INV":"Blank Checks"})
    bad=dict(op); bad["security_name"]="Different Name"
    assert m.prior_operating_fallback("INV",bad,"2026-10-06",names,inds) is None
    assert m.prior_blank_fallback("TLAC",blank,"2026-10-06",names,inds)
    assert m.prior_blank_fallback("TLAC",blank,"2026-10-06",names,{"TLAC":"Technology"})
    fjdi_names={"FJDI":"ARC Group Securities Acquisition I - Class A Ordinary Shares"}
    fjdi_old={"cik":"0002094712","sic":6770,"classification":"Blank Checks","source_url":"https://www.sec.gov/Archives/edgar/data/2094712/example","evidence_date":"2026-08-03"}
    assert m.prior_blank_fallback("FJDI",fjdi_old,"2026-10-06",fjdi_names,{"FJDI":""})
    stale=dict(fjdi_old); stale["evidence_date"]="2026-01-01"
    assert m.prior_blank_fallback("FJDI",stale,"2026-10-06",fjdi_names,{"FJDI":""}) is None
    assert m.prior_blank_fallback("XYZ",fjdi_old,"2026-10-06",{"XYZ":"Ordinary Operating Company"},{"XYZ":""}) is None
    print("XRAY_CURRENT_IDENTITY_PROOF_SELFTEST=PASS")

if __name__=="__main__":
    main()
