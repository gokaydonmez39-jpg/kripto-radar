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
    original=m.request_bytes
    try:
        fake=b"""<html><body>
        <h1>Churchill Capital Corp XIII XIII, XIIIU, XIIIW on Nasdaq</h1>
        <div>CIK: (Central Index Key) 0002114229</div>
        <div>SIC: (Standard Industrial Classification) 6770 - Blank Checks</div>
        </body></html>"""
        m.request_bytes=lambda url,user_agent,timeout=45: fake
        row=m.sec_entity_landing_row("XIII","2026-10-06",2114229,True,"2026-09-16")
        assert row and row["sic"]==6770 and row["classification"]=="Blank Checks"
        assert row["same_asof_sec_entity_landing_revalidated"] is True
        assert row["evidence_date"]=="2026-09-16"
        assert m.sec_entity_landing_row("WRONG","2026-10-06",2114229,True,"2026-09-16") is None
        assert m.sec_entity_landing_row("XIII","2026-10-06",2114229,False,"2026-09-16") is None
        assert m.sec_entity_landing_row("XIII","2026-10-06",2114229,True,"2026-10-07") is None
    finally:
        m.request_bytes=original

    # Current same-ASOF SEC discovery must work without any prior-day seed.
    original_load=m.load_json_url
    try:
        def fake_load(url):
            if url==m.SEC_TICKERS:
                return {
                  "0":{"ticker":"TLAC","cik_str":2128462,"title":"Three Lions Acquisition Corp."},
                  "1":{"ticker":"OPER","cik_str":1234567,"title":"Operating Corp."},
                }
            if "CIK0002128462.json" in url:
                return {
                  "tickers":["TLAC"],"sic":"6770","sicDescription":"Blank Checks",
                  "filings":{"recent":{"filingDate":["2026-09-30","2026-10-07"]}},
                }
            if "CIK0001234567.json" in url:
                return {
                  "tickers":["OPER"],"sic":"3571","sicDescription":"Electronic Computers",
                  "filings":{"recent":{"filingDate":["2026-09-29"]}},
                }
            raise AssertionError("unexpected URL "+url)
        m.load_json_url=fake_load
        cmap=m.sec_ticker_cik_map()
        assert cmap["TLAC"]==2128462 and cmap["OPER"]==1234567
        blank_row=m.sec_current_classification("TLAC","2026-10-06",cmap["TLAC"])
        assert blank_row and blank_row["is_blank_check"] is True and blank_row["sic"]==6770
        assert blank_row["evidence_date"]=="2026-09-30"
        operating_row=m.sec_current_classification("OPER","2026-10-06",cmap["OPER"])
        assert operating_row and operating_row["is_blank_check"] is False and operating_row["sic"]==3571
        assert operating_row["discovery_version"]==m.IDENTITY_DISCOVERY_VERSION
        assert m.sec_current_classification("WRONG","2026-10-06",cmap["OPER"]) is None
    finally:
        m.load_json_url=original_load

    # Missing exact-ASOF SEC SPAC proof must never be treated as a complete proof set.
    from pathlib import Path
    import tempfile
    original_vi=m.validate_existing_identity
    original_vs=m.validate_existing_sec
    try:
        m.validate_existing_identity=lambda path,asof: True
        m.validate_existing_sec=lambda path,asof: True
        missing=Path("/tmp/xray_missing_sec_spac_proof.json")
        if missing.exists():
            missing.unlink()
        assert m.exact_proofs_complete(Path("/tmp/identity.json"),missing,"2026-10-06") is False
        with tempfile.NamedTemporaryFile() as tmp:
            assert m.exact_proofs_complete(Path("/tmp/identity.json"),Path(tmp.name),"2026-10-06") is True
    finally:
        m.validate_existing_identity=original_vi
        m.validate_existing_sec=original_vs

    print("XRAY_CURRENT_IDENTITY_PROOF_SELFTEST=PASS")

if __name__=="__main__":
    main()
