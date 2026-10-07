#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import sina_stage as s


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    old_root = s.ROOT
    old_seed = s.MANUAL_IDENTITY_SEED
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            seed = root / "master_sec_identity_manual_seed_registry.json"
            seed.write_text('{"fixture":"manual-sec-seed"}\n', encoding="utf-8")
            s.ROOT = root
            s.MANUAL_IDENTITY_SEED = seed

            asof = "2026-10-06"
            proof_path = root / "master_sec_spac_proof_20261006.json"
            row = {
                "cik": "0002083689",
                "sic": 6770,
                "classification": "Blank Checks",
                "source_url": "https://www.sec.gov/Archives/edgar/data/2083689/example-index.htm",
                "evidence_date": "2026-07-17",
                "same_asof_revalidated_without_sec_network": True,
                "revalidation_semantics": "MANUAL_OFFICIAL_SEC_EVIDENCE_WITHIN_120D_PLUS_SAME_ASOF_NASDAQ_SPAC_IDENTITY;NO_ALPHA_PASS",
                "same_asof_nasdaq_directory_footer": "File Creation Time: 1006202617:01|||||||",
                "same_asof_nasdaq_security_name": "Activate Energy Acquisition Corp. - Class A Ordinary Share",
                "same_asof_nasdaq_screener_industry": "",
                "manual_seed_registry_path": "nasdaq-xray/master_sec_identity_manual_seed_registry.json",
                "manual_seed_registry_blob_sha": s.git_blob_sha(seed),
            }
            write_json(proof_path, {
                "schema": "XRAY_MASTER_SEC_SPAC_PROOF_V1",
                "asof_et": asof,
                "execution": "NONE",
                "real_money": "NO-GO",
                "unknown_never_pass": True,
                "authority": "SEC_EDGAR_SIC_6770_EXACT_ASOF",
                "applicability": "EXACT_ASOF_ONLY_NO_FORWARD_CARRY",
                "proofs": {"AEAQ": row},
            })

            proofs, blob = s.load_sec_spac_proof(asof)
            assert set(proofs) == {"AEAQ"}
            assert proofs["AEAQ"]["sic"] == 6770
            assert blob == s.git_blob_sha(proof_path)

            bad = json.loads(proof_path.read_text(encoding="utf-8"))
            bad["proofs"]["AEAQ"]["manual_seed_registry_blob_sha"] = "0" * 40
            write_json(proof_path, bad)
            try:
                s.load_sec_spac_proof(asof)
            except RuntimeError as exc:
                assert str(exc) == "SEC_SPAC_PROOF_MANUAL_SEED_PROVENANCE_INVALID:AEAQ"
            else:
                raise AssertionError("TAMPERED_MANUAL_SEED_BLOB_MUST_FAIL_CLOSED")

        print("SINA_IDENTITY_PROOF_CONSUMER_SELFTEST=PASS")
    finally:
        s.ROOT = old_root
        s.MANUAL_IDENTITY_SEED = old_seed


if __name__ == "__main__":
    main()
