#!/usr/bin/env python3
import json
import build_current_identity_proofs as m

def main():
    # A same-ASOF Nasdaq "Blank Checks" industry label must not bypass the
    # SEC/manual identity proof queue.  It is supporting evidence only.
    suspects=m.current_spac_suspects(
        {
          "TLAC":"Three Lions Acquisition Corp. - Ordinary Shares",
          "OPER":"Ordinary Operating Company - Common Stock",
        },
        {"TLAC":"Blank Checks","OPER":"Technology"},
    )
    assert suspects==["TLAC"],suspects

    assert m.parse_footer_date("File Creation Time: 1006202614:01|||||||")=="2026-10-06"
    assert m.SPAC_SUSPECT_RE.search("Churchill Capital Corp XIII - Class A Ordinary Shares")
    assert m.SPAC_SUSPECT_RE.search("Example Capital Corporation IV - Class A Ordinary Share")
    assert not m.SPAC_SUSPECT_RE.search("Capital One Financial Corporation - Common Stock")
    assert not m.SPAC_SUSPECT_RE.search("Privately Held Capital Corp - Common Stock")
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
                  "2":{"ticker":"CONFLICT","cik_str":333,"title":"Conflict Corp."},
                }
            if url==m.SEC_TICKERS_EXCHANGE:
                return {
                  "fields":["cik","name","ticker","exchange"],
                  "data":[
                    [2128462,"Three Lions Acquisition Corp.","TLAC","Nasdaq"],
                    [1234567,"Operating Corp.","OPER","Nasdaq"],
                    [2128462,"Three Lions Acquisition Corp.","TLACU","Nasdaq"],
                    [333,"Conflict Corp.","CONFLICT","Nasdaq"],
                    [444,"Conflict Other Corp.","CONFLICT","Nasdaq"],
                    [555,"Different Corp.","DUP","Nasdaq"],
                    [556,"Another Corp.","DUP","Nasdaq"],
                    [111,"Non Nasdaq","NONNAS","NYSE"]
                  ]
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
        assert cmap["TLACU"]==2128462 and "NONNAS" not in cmap
        assert "CONFLICT" not in cmap and "DUP" not in cmap
        assert m.SEC_CIK_DISCOVERY_DIAGNOSTICS["exchange_added_count"]==1
        assert m.SEC_CIK_DISCOVERY_DIAGNOSTICS["conflict_count"]==2
        def legacy_only_load(url):
            if url==m.SEC_TICKERS_EXCHANGE:
                raise RuntimeError("MOCK_SECONDARY_UNAVAILABLE")
            return fake_load(url)
        m.load_json_url=legacy_only_load
        legacy_only=m.sec_ticker_cik_map()
        assert legacy_only["TLAC"]==2128462 and "TLACU" not in legacy_only
        assert m.SEC_CIK_DISCOVERY_DIAGNOSTICS["status"]=="SECONDARY_UNAVAILABLE_LEGACY_FALLBACK_ONLY"
        def exchange_only_load(url):
            if url==m.SEC_TICKERS:
                raise RuntimeError("MOCK_PRIMARY_403")
            return fake_load(url)
        m.load_json_url=exchange_only_load
        via_exchange=m.sec_ticker_cik_map()
        assert via_exchange["TLAC"]==2128462 and via_exchange["TLACU"]==2128462
        assert "CONFLICT" not in via_exchange and "NONNAS" not in via_exchange
        assert m.SEC_CIK_DISCOVERY_DIAGNOSTICS["status"]=="PASS_EXCHANGE_ONLY_CIK_ROUTING"
        def blocked_both_load(url):
            if url in (m.SEC_TICKERS,m.SEC_TICKERS_EXCHANGE):
                raise RuntimeError("MOCK_OFFICIAL_SEC_403")
            return fake_load(url)
        m.load_json_url=blocked_both_load
        try:
            m.sec_ticker_cik_map()
            raise AssertionError("both unavailable should fail closed")
        except RuntimeError as e:
            assert str(e)=="SEC_CIK_ROUTING_UNAVAILABLE_PRIMARY_AND_SECONDARY"
        assert m.SEC_CIK_DISCOVERY_DIAGNOSTICS["status"]=="BOTH_SEC_TICKER_LISTS_UNAVAILABLE"
        # Independent mirror fallback routes only CIKs when both official
        # index endpoints return 403. No SIC, SPAC or AL is inferred.
        original_mirror=m.pinned_github_sec_cik_mirror
        try:
            m.pinned_github_sec_cik_mirror=lambda asof,subjects: (
                {"TLAC":2128462},
                {"mirror_commit":"a"*40,"mirror_source_sha256":"b"*64,
                 "mirror_exact_asof":asof,"mirror_discovered":1,
                 "mirror_scope":len(set(subjects)),"mirror_authority":"CIK_ROUTING_ONLY_OFFICIAL_SEC_SIC_REQUIRED"},
            )
            routed=m.sec_ticker_cik_map("2026-10-07",["TLAC","OPER"])
            assert routed=={"TLAC":2128462}
            assert m.SEC_CIK_DISCOVERY_DIAGNOSTICS["status"]=="PASS_PINNED_MIRROR_CIK_ONLY_SEC_SIC_REQUIRED"
            assert m.SEC_CIK_DISCOVERY_DIAGNOSTICS["classification_authority"] is False
            m.pinned_github_sec_cik_mirror=lambda *_: (_ for _ in ()).throw(ValueError("MIRROR_HASH_BAD"))
            try:
                m.sec_ticker_cik_map("2026-10-07",["TLAC"])
                raise AssertionError("MIRROR_CORRUPTION_ACCEPTED")
            except RuntimeError as e:
                assert str(e)=="SEC_CIK_ROUTING_UNAVAILABLE_PRIMARY_AND_SECONDARY"
            assert "MIRROR_HASH_BAD" in m.SEC_CIK_DISCOVERY_DIAGNOSTICS.get("mirror_error","")
        finally:
            m.pinned_github_sec_cik_mirror=original_mirror
        m.load_json_url=fake_load
        m.load_json_url=fake_load
        blank_row=m.sec_current_classification("TLAC","2026-10-06",cmap["TLAC"])
        assert blank_row and blank_row["is_blank_check"] is True and blank_row["sic"]==6770
        assert blank_row["evidence_date"]=="2026-09-30"
        operating_row=m.sec_current_classification("OPER","2026-10-06",cmap["OPER"])
        assert operating_row and operating_row["is_blank_check"] is False and operating_row["sic"]==3571
        assert operating_row["discovery_version"]==m.IDENTITY_DISCOVERY_VERSION
        assert m.sec_current_classification("WRONG","2026-10-06",cmap["OPER"]) is None
    finally:
        m.load_json_url=original_load

    # Verify the source snapshot itself: exact date, SHA256 and contradictory CIK
    # rows. Mock transport has no access to real GitHub or SEC.
    from unittest.mock import patch
    import hashlib
    from sec_mirror_cik_shadow import classify
    body=b'{"ticker":"TLAC","cik":2128462,"exchange":"Nasdaq"}\n'
    manifest={"snapshot_date":"2026-10-07",
              "last_success":{"sec_company_tickers_exchange":"2026-10-07"},
              "files":[{"name":"sec_company_tickers_exchange.jsonl",
                        "bytes":len(body),"sha256":hashlib.sha256(body).hexdigest()}]}
    upstream="https://raw.githubusercontent.com/TylerJForstrom/Stock-Data/"+"a"*40+"/data/symbols/current/"
    def mock_mirror_url(url,user_agent,timeout=30):
        if url.endswith("/git/ref/heads/main"):
            return json.dumps({"object":{"sha":"a"*40}}).encode()
        if url==upstream+"manifest.json":
            return json.dumps(manifest).encode()
        if url==upstream+"sec_company_tickers_exchange.jsonl":
            return body
        raise RuntimeError("UNEXPECTED_MIRROR_URL")
    with patch.object(m,"request_bytes",side_effect=mock_mirror_url):
        cik,diag=m.pinned_github_sec_cik_mirror("2026-10-07",["TLAC","NONE"])
        assert cik=={"TLAC":2128462} and diag["mirror_discovered"]==1
        assert diag["mirror_authority"]=="CIK_ROUTING_ONLY_OFFICIAL_SEC_SIC_REQUIRED"
        bad=dict(manifest,snapshot_date="2026-10-06")
        def bad_date(url,ua,timeout=30):
            if url==upstream+"manifest.json":return json.dumps(bad).encode()
            return mock_mirror_url(url,ua,timeout)
        with patch.object(m,"request_bytes",side_effect=bad_date):
            try:m.pinned_github_sec_cik_mirror("2026-10-07",["TLAC"])
            except ValueError:pass
            else:raise AssertionError("STALE_MIRROR_BYPASSED_DATE_GATE")
        def bad_hash(url,ua,timeout=30):
            if url==upstream+"sec_company_tickers_exchange.jsonl":return body+b"BAD"
            return mock_mirror_url(url,ua,timeout)
        with patch.object(m,"request_bytes",side_effect=bad_hash):
            try:m.pinned_github_sec_cik_mirror("2026-10-07",["TLAC"])
            except ValueError:pass
            else:raise AssertionError("CORRUPT_MIRROR_BYPASSED_DIGEST_GATE")

    # SEC 403/429 is a same-run transport circuit breaker; other errors
    # remain local. Classification remains exact SEC-SIC only.
    import urllib.error
    assert m.sec_submissions_transport_is_blocked(
        urllib.error.HTTPError("https://data.sec.gov/",403,"Denied",{},None))
    assert m.sec_submissions_transport_is_blocked(
        urllib.error.HTTPError("https://data.sec.gov/",429,"Slow",{},None))
    assert not m.sec_submissions_transport_is_blocked(
        urllib.error.HTTPError("https://data.sec.gov/",500,"Server",{},None))
    assert not m.sec_submissions_transport_is_blocked(
        RuntimeError("SYMBOL_LOCAL_UNAVAILABLE"))
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
        seed_rel=str(m.MANUAL_IDENTITY_SEED.relative_to(m.ROOT.parent)).replace("\\","/")
        seed_blob=m.file_blob_sha(m.MANUAL_IDENTITY_SEED) if m.MANUAL_IDENTITY_SEED.exists() else None
        with tempfile.NamedTemporaryFile(mode="w+",suffix=".json") as tmp:
            json.dump({
              "asof_et":"2026-10-06",
              "discovery_version":m.IDENTITY_DISCOVERY_VERSION,
              "discovery_coverage":{
                "manual_seed_registry_path":seed_rel,
                "manual_seed_registry_blob_sha":seed_blob,
                "coverage_complete":True,
                "unresolved_current_suspect_count":0,
                "unresolved_current_suspects":[],
              },
            },tmp); tmp.flush()
            assert m.exact_proofs_complete(Path("/tmp/identity.json"),Path(tmp.name),"2026-10-06") is True
        with tempfile.NamedTemporaryFile(mode="w+",suffix=".json") as tmp:
            json.dump({
              "asof_et":"2026-10-06",
              "discovery_version":m.IDENTITY_DISCOVERY_VERSION,
              "discovery_coverage":{
                "manual_seed_registry_path":seed_rel,
                "manual_seed_registry_blob_sha":seed_blob,
                "coverage_complete":False,
                "unresolved_current_suspect_count":1,
                "unresolved_current_suspects":["TLAC"],
              },
            },tmp); tmp.flush()
            assert m.exact_proofs_complete(Path("/tmp/identity.json"),Path(tmp.name),"2026-10-06") is False
    finally:
        m.validate_existing_identity=original_vi
        m.validate_existing_sec=original_vs

    # Manual SEC seeds are discovery evidence only and must remain bounded,
    # recent, official, and exact-ASOF Nasdaq-name revalidated.
    with tempfile.TemporaryDirectory(dir=m.ROOT) as td:
        old_seed=m.MANUAL_IDENTITY_SEED
        try:
            seed=Path(td)/"master_sec_identity_manual_seed_registry.json"
            seed.write_text(json.dumps({
              "schema":"XRAY_MASTER_SEC_IDENTITY_MANUAL_SEED_REGISTRY_V1",
              "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
              "authority":"OFFICIAL_SEC_EVIDENCE_DISCOVERY_SEED_ONLY",
              "records":{
                "TLAC":{"cik":"0002128462","sic":6770,"classification":"Blank Checks",
                        "is_blank_check":True,"evidence_date":"2026-09-01",
                        "source_url":"https://www.sec.gov/Archives/edgar/data/2128462/example-index.htm"},
                "ALIS":{"cik":"0002026767","sic":7374,"classification":"Services-Computer Processing & Data Preparation",
                        "is_blank_check":False,"evidence_date":"2026-09-04",
                        "source_url":"https://www.sec.gov/Archives/edgar/data/2026767/example-index.htm"},
                "OLD":{"cik":"0002000000","sic":6770,"classification":"Blank Checks",
                        "is_blank_check":True,"evidence_date":"2026-01-01",
                        "source_url":"https://www.sec.gov/Archives/edgar/data/2000000/example-index.htm"},
              },
            }))
            m.MANUAL_IDENTITY_SEED=seed
            rows,meta=m.manual_identity_seed_registry(
                "2026-10-06",
                {"TLAC":"Three Lions Acquisition Corp.",
                 "ALIS":"Calisa Acquisition Corp - Ordinary shares",
                 "OLD":"Old Acquisition Corp."},
            )
            assert set(rows)=={"TLAC","ALIS"}
            assert rows["TLAC"]["is_blank_check"] is True and rows["TLAC"]["sic"]==6770
            assert rows["ALIS"]["is_blank_check"] is False and rows["ALIS"]["sic"]==7374
            assert meta["record_count"]==2 and meta["blob_sha"]==m.file_blob_sha(seed)
            proof=dict(rows["TLAC"])
            proof.update({
              "same_asof_revalidated_without_sec_network":True,
              "revalidation_semantics":"MANUAL_OFFICIAL_SEC_EVIDENCE_WITHIN_120D_PLUS_SAME_ASOF_NASDAQ_SPAC_IDENTITY;NO_ALPHA_PASS",
              "same_asof_nasdaq_directory_footer":"File Creation Time: 1006202618:01|||||||",
              "same_asof_nasdaq_screener_industry":"",
            })
            assert m.valid_sec_spac_proof_row(proof,"2026-10-06")
        finally:
            m.MANUAL_IDENTITY_SEED=old_seed

    # Immutable membership-only directory snapshots outrank contaminated
    # current/support-plane state, but only when ASOF/footer/count are exact.
    from pathlib import Path
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        snap={
          "schema":"XRAY_NASDAQ_DIRECTORY_SNAPSHOT_V1",
          "asof_et":"2026-10-06",
          "source_directory_footer":"File Creation Time: 1006202618:01|||||||",
          "source_directory_date":"2026-10-06",
          "membership_only":True,
          "identity_decisions_reused":False,
          "source_queue_classification_ignored":True,
          "membership_count":2,
          "security_names":{"OPER":"Operating Corp. - Common Stock","TLAC":"Three Lions Acquisition Corp."},
          "industries":{"OPER":"Technology","TLAC":"Blank Checks"},
        }
        (root/"master_nasdaq_directory_snapshot_20261006.json").write_text(json.dumps(snap))
        frozen=m.frozen_exact_asof_directory("2026-10-06",root)
        assert frozen is not None
        names2,industries2,footer2=frozen
        assert names2["OPER"]=="Operating Corp. - Common Stock"
        assert industries2["TLAC"]=="Blank Checks"
        assert m.parse_footer_date(footer2)=="2026-10-06"
        bad=dict(snap); bad["source_directory_footer"]="File Creation Time: 1007202603:02|||||||"
        (root/"master_nasdaq_directory_snapshot_20261006.json").write_text(json.dumps(bad))
        assert m.frozen_exact_asof_directory("2026-10-06",root) is None

    # Historical replay must use the committed exact-ASOF identity snapshot,
    # never a later live Nasdaq directory as if it belonged to the target day.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        q0=["OPER"]; q0hash=__import__("hashlib").sha256("OPER".encode()).hexdigest()
        unknown0=["TLAC"]
        detail0={
          "TLAC":{
            "security_name":"Three Lions Acquisition Corp.",
            "same_asof_nasdaq_industry":"",
            "unknown_never_pass":True
          }
        }
        (root/"canonical_current_full_state.json").write_text(json.dumps({
          "schema":"XRAY_NASDAQ_SCREENER_SINA_V2",
          "asof_et":"2026-10-06",
          "official_footer":"File Creation Time: 1006202618:01|||||||",
          "identity_ruleset":"V6_ASOF_IDENTITY_AND_SPAC_PROOF_AT_MASTER",
          "identity_partition_policy":"MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD",
          "queue":q0,"queue_total":1,"queue_hash":q0hash,
          "raw_identity_total":2,
          "security_names":{"OPER":"Operating Corp. - Common Stock"},
          "identity_unknown_symbols":unknown0,
          "identity_unknown_detail":detail0,
          "discovery_meta":{"identity_partition_policy":"MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD"}
        }))
        (root/"canonical_current_master_manifest.json").write_text(json.dumps({
          "asof_et":"2026-10-06",
          "official_footer":"File Creation Time: 1006202618:01|||||||",
          "unknown_detail":detail0
        }))
        frozen=m.frozen_exact_asof_directory("2026-10-06",root)
        assert frozen is not None
        names,industries,footer=frozen
        assert names["OPER"]=="Operating Corp. - Common Stock"
        assert names["TLAC"]=="Three Lions Acquisition Corp."
        assert m.parse_footer_date(footer)=="2026-10-06"
        assert m.frozen_exact_asof_directory("2026-10-05",root) is None

        # A later-day contaminated canonical current snapshot must be ignored
        # in favor of an independently exact same-ASOF support snapshot.
        (root/"canonical_current_full_state.json").write_text(json.dumps({
          "schema":"XRAY_NASDAQ_SCREENER_SINA_V2",
          "asof_et":"2026-10-06",
          "official_footer":"File Creation Time: 1007202603:02|||||||",
          "identity_ruleset":"V6_ASOF_IDENTITY_AND_SPAC_PROOF_AT_MASTER",
          "identity_partition_policy":"MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD",
          "queue":[],"queue_total":0,"queue_hash":__import__("hashlib").sha256(b"").hexdigest(),
          "raw_identity_total":0,"security_names":{},"identity_unknown_symbols":[],"identity_unknown_detail":{},
          "discovery_meta":{"identity_partition_policy":"MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD"}
        }))
        (root/"canonical_current_master_manifest.json").write_text(json.dumps({
          "asof_et":"2026-10-06","official_footer":"File Creation Time: 1007202603:02|||||||","unknown_detail":{}
        }))
        q=["OPER"]; qhash=__import__("hashlib").sha256("OPER".encode()).hexdigest()
        (root/"sina_state.json").write_text(json.dumps({
          "schema":"XRAY_NASDAQ_SCREENER_SINA_V2","asof_et":"2026-10-06",
          "official_footer":"File Creation Time: 1006202618:01|||||||",
          "identity_ruleset":"V6_ASOF_IDENTITY_AND_SPAC_PROOF_AT_MASTER",
          "identity_partition_policy":"MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD",
          "queue":q,"queue_total":1,"queue_hash":qhash,"raw_identity_total":1,
          "security_names":{"OPER":"Operating Corp. - Common Stock"},
          "identity_unknown_symbols":[],"identity_unknown_detail":{},
          "discovery_meta":{"identity_partition_policy":"MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD"}
        }))
        frozen2=m.frozen_exact_asof_directory("2026-10-06",root)
        assert frozen2 is not None and frozen2[0]["OPER"]=="Operating Corp. - Common Stock"
        assert m.parse_footer_date(frozen2[2])=="2026-10-06"

    # Transport fallback must accept only a recent prior SEC SIC 6770 proof
    # that is revalidated by the exact-ASOF Nasdaq identity snapshot. This is
    # exclusion-only evidence and can never create alpha PASS.
    with tempfile.TemporaryDirectory() as td:
        sec_path=Path(td)/"master_sec_spac_proof_20261006.json"
        fallback_row=m.prior_blank_fallback(
            "TLAC",
            {"cik":"0002128462","sic":6770,"classification":"Blank Checks",
             "source_url":"https://www.sec.gov/edgar/browse/?CIK=2128462",
             "evidence_date":"2026-09-01"},
            "2026-10-06",
            {"TLAC":"Three Lions Acquisition Corp."},
            {"TLAC":""},
        )
        assert fallback_row is not None
        fallback_row["same_asof_nasdaq_directory_footer"]="File Creation Time: 1006202618:01|||||||"
        sec_path.write_text(json.dumps({
          "schema":"XRAY_MASTER_SEC_SPAC_PROOF_V1",
          "asof_et":"2026-10-06",
          "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
          "authority":"SEC_EDGAR_SIC_6770_EXACT_ASOF",
          "applicability":"EXACT_ASOF_ONLY_NO_FORWARD_CARRY",
          "proofs":{"TLAC":fallback_row},
        }))
        assert m.validate_existing_sec(sec_path,"2026-10-06")
        bad=json.loads(sec_path.read_text())
        bad["proofs"]["TLAC"]["revalidation_semantics"]="UNSAFE_FORWARD_CARRY"
        sec_path.write_text(json.dumps(bad))
        assert not m.validate_existing_sec(sec_path,"2026-10-06")

    print("XRAY_CURRENT_IDENTITY_PROOF_SELFTEST=PASS")

if __name__=="__main__":
    main()
