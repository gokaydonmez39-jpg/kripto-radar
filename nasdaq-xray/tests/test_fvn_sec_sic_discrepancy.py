#!/usr/bin/env python3
"""PIT SEC index-vs-manual SIC contradiction regression; no network, no alpha.

FVN manual seed says SIC 6770 but *its own same-accession SEC S-4/A index*
explicitly identifies Future Vision II Acquisition Corp CIK 2010653
with SIC 7373. A false exclusion-only SEC claim can corrupt the master.
Never manufacture a 6770 identity proof from a contradicted source.
"""
import ast
import copy
import json
import re
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SEC_INDEX="https://www.sec.gov/Archives/edgar/data/2110070/000182912626006424/0001829126-26-006424-index.htm"
FVN_SOURCE="https://www.sec.gov/Archives/edgar/data/2010653/000182912626006424/futurevision2_s4a.htm"

def read_producer():
    source=(ROOT/"build_current_identity_proofs.py").read_text()
    tree=ast.parse(source)
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="manual_identity_seed_registry")
    ns={"ROOT":ROOT,"MANUAL_IDENTITY_SEED":ROOT/"master_sec_identity_manual_seed_registry.json",
        "json":json,"re":re,"datetime":datetime,
        "SPAC_SUSPECT_RE":re.compile(r"\\bacquisition\\b|\\bspac\\b",re.I),
        "sec_source_binds_cik":lambda url,cik:f"/data/{int(cik)}/" in url,
        "file_blob_sha":lambda path:"OFFLINE_ONLY_SHA"}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(ROOT/"build_current_identity_proofs.py"),"exec"),ns)
    return ns["manual_identity_seed_registry"]

def run():
    reg=json.loads((ROOT/"master_sec_identity_manual_seed_registry.json").read_text())
    assert reg["authority"]=="OFFICIAL_SEC_EVIDENCE_DISCOVERY_SEED_ONLY"
    assert reg["execution"]=="NONE" and reg["real_money"]=="NO-GO"
    assert reg["unknown_never_pass"] is True
    assert reg["records"]["FVN"]["cik"]=="0002010653"
    assert reg["records"]["FVN"]["sic"]==6770
    assert reg["records"]["FVN"]["is_blank_check"] is True
    assert reg["records"]["FVN"]["source_url"]==FVN_SOURCE
    # Registry is immutable historical input: counter-evidence is additive,
    # not a rewrite that would silently break 577 master SEC proof SHA edges.
    audit=json.loads((ROOT/"master_sec_sic_discrepancies_20261009.json").read_text())
    assert audit["schema"]=="XRAY_SEC_MANUAL_SOURCE_SIC_DISCREPANCY_V1"
    assert audit["asof_et"]=="2026-10-09"
    assert audit["execution"]=="NONE" and audit["real_money"]=="NO-GO"
    assert audit["unknown_never_pass"] is True and audit["alpha_authority"] is False
    rec=audit["discrepancies"]["FVN"]
    assert rec["cik"]=="0002010653" and rec["source_url"]==FVN_SOURCE
    assert rec["official_index_url"]==SEC_INDEX
    assert rec["official_filing_date"]=="2026-06-12"
    assert rec["manual_seed_sic"]==6770 and rec["official_sec_filer_sic"]==7373
    assert rec["action"]=="VETO_MANUAL_SIC6770_BLANK_PROOF_KEEP_UNKNOWN"
    names={"FVN":"Future Vision II Acquisition Corporation - Ordinary Shares",
           "IBAC":"IB Acquisition Corp. - Common Stock",
           "NBRG":"Newbridge Acquisition Limited - Class A Ordinary Share"}
    consumer=read_producer()
    rows,meta=consumer("2026-10-09",names)
    assert set(rows)=={"IBAC","NBRG"},("FVN_FALSE_BLANK_PROOF_ESCAPED",rows)
    assert rows["IBAC"]["sic"]==6770 and rows["NBRG"]["sic"]==6770
    assert rows["IBAC"]["is_blank_check"] is True and rows["NBRG"]["is_blank_check"] is True
    # The counter-evidence was not known for the 7-Oct historical producer run.
    old,_=consumer("2026-10-07",names)
    assert not {"FVN","IBAC","NBRG"} & set(old)
    assert "FVN" not in rows and "FVN" not in old
    source=(ROOT/"build_current_identity_proofs.py").read_text()
    assert "master_sec_sic_discrepancies_20261009.json" in source
    assert "OFFICIAL_SEC_SIC_DISCREPANCY" in source
    print("XRAY_FVN_CONTRADICTED_SIC6770=VETOED_KEEP_UNKNOWN_IBAC_NBRG_PRESERVED_NO_ALPHA")

if __name__=="__main__":run()
