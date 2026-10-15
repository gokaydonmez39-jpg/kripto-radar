#!/usr/bin/env python3
"""Fail-closed PIT-safe independent SEC issuer diagnostic; NEVER an identity PASS.

This validator only checks the immutable-format issuer evidence audit against
the canonical UNKNOWN partition. SEC URLs are human-verified references, not
freshly downloaded or machine-attested SEC filing bytes in this execution.
No data provider, brokerage, GitHub mutation or notification calls.
"""
from __future__ import annotations
import argparse
import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "research/sec_nine_unknown_issuer_evidence_20261014.json"
MASTER = ROOT / "canonical_current_master_manifest.json"
EXPECTED = {"ALIS", "BSAA", "FACT", "FVN", "HCAC", "IPXG", "MACI", "MCGA", "WTG"}
NONPROMOTION_FALSE = (
    "raw_data_present", "market_price_present",
    "provider_licensed_for_canonical", "can_change_master",
    "can_promote_identity", "can_change_price_dv30",
    "can_change_mc", "can_create_r92", "device_receipt_attested",
)

def require(ok: bool, reason: str):
    if not ok:
        raise ValueError("XRAY_NINE_SEC_UNKNOWN_VETO:" + reason)

def validate(audit: dict, master: dict) -> dict:
    require(type(audit) is dict and type(master) is dict, "NONOBJECT_INPUT")
    require(audit.get("schema") == "XRAY_SEC_NINE_UNKNOWN_ISSUER_CAUSAL_AUDIT_V1", "SCHEMA")
    require(audit.get("authority") == "OFFICIAL_SEC_DISCOVERY_ONLY_NO_IDENTITY_PROMOTION", "AUTHORITY")
    require(audit.get("source_eligibility") == "RESEARCH_DIAGNOSTIC_ONLY_NOT_ASOF_SEC_OPERATING_COMPLETION", "SOURCE_SCOPE")
    require(audit.get("asof_et") == master.get("asof_et") == "2026-10-14", "EPOCH")
    require(audit.get("execution") == master.get("execution") == "NONE", "EXECUTION")
    require(audit.get("real_money") == master.get("real_money") == "NO-GO", "MONEY")
    require(audit.get("unknown_never_pass") is master.get("unknown_never_pass") is True, "FAIL_CLOSED")
    for key in NONPROMOTION_FALSE:
        require(audit.get(key) is False, "NO_PROMOTION_" + key)
    unknown = master.get("unknown_symbols")
    detail = master.get("unknown_detail")
    require(type(unknown) is list and set(unknown) == EXPECTED and len(unknown) == 9,
            "CANONICAL_UNKNOWN_SCOPE_DRIFT")
    require(type(detail) is dict and set(detail) == EXPECTED, "CANONICAL_DETAIL_SCOPE")
    require(master.get("unknown_count") == 9 and master.get("pass_count") == 3185,
            "CANONICAL_PARTITION_COUNT")
    records = audit.get("records")
    require(type(records) is list and len(records) == 9
            and audit.get("scope_count") == 9, "RECORD_SCOPE")
    seen = set()
    for item in records:
        require(type(item) is dict, "BAD_RECORD")
        s = item.get("symbol")
        require(type(s) is str and s in EXPECTED and s not in seen, "DUPLICATE_OR_OUTSIDE_TICKER")
        seen.add(s)
        require(item.get("security_name") == detail[s].get("security_name"), "WRONG_NASDAQ_IDENTITY_" + s)
        require(detail[s].get("unknown_never_pass") is True, "MASTER_UNKNOWN_VIOLATED_" + s)
        cik = item.get("cik")
        require(type(cik) is str and re.fullmatch(r"[0-9]{10}", cik) is not None
                and int(cik) > 0, "BAD_ISSUER_CIK_" + s)
        require(item.get("disposition") == "UNKNOWN_EXACT_ASOF_LIFECYCLE_NO_IDENTITY_PASS", "PROMOTION_" + s)
        require(item.get("source_authority") == "OFFICIAL_SEC_DISCOVERY_ONLY_NO_COMPLETION_ATTESTATION",
                "FALSE_LIFECYCLE_AUTHORITY_" + s)
        require(item.get("unknown_never_pass") is True, "RECORD_PROMOTION_" + s)
        require(type(item.get("limitation")) is str and len(item["limitation"]) >= 20,
                "MISSING_LIMITATION_" + s)
        url = item.get("sec_source_url")
        sic = item.get("sec_issuer_sic")
        date = item.get("sec_filing_date")
        if s == "HCAC":
            require(sic is None and date is None
                    and url == "https://www.sec.gov/edgar/browse/?CIK=2079013&owner=exclude",
                    "UNDATED_HCAC_ASOF_PROMOTION")
        else:
            require(type(sic) is int and sic > 0 and sic != 6770, "CROSS_FILER_SIC_OR_BLANK_PROMOTION_" + s)
            require(type(date) is str and re.fullmatch(r"2026-[0-9]{2}-[0-9]{2}", date) is not None
                    and date <= audit["asof_et"], "FUTURE_EVIDENCE_" + s)
            # Using an index belonging to the other S-4 joint filer (e.g. the
            # 6770 co-filer of MACI) is NOT a valid source for this issuer.
            require(type(url) is str and url.startswith(
                "https://www.sec.gov/Archives/edgar/data/" + str(int(cik)) + "/"),
                "WRONG_ISSUER_SEC_URL_" + s)
    require(seen == EXPECTED, "NINE_SCOPE_INCOMPLETE")
    return {"status": "PASS_RESEARCH_DIAGNOSTIC_ONLY", "scope": 9,
            "unknown_kept": sorted(seen), "identity_pass_created": 0,
            "canonical_price_pass_created": 0, "mc_primary_created": 0,
            "r92_created": 0, "device_receipt_attested": False,
            "execution": "NONE", "real_money": "NO-GO"}

def selftest(audit: dict, master: dict):
    good = validate(audit, master)
    require(good["identity_pass_created"] == 0, "SELFTEST_FALSE_IDENTITY")
    mutations = [
        ("ASOF_DRIFT", lambda a,m: a.update(asof_et="2026-10-15")),
        ("FALSE_ENTITLEMENT", lambda a,m: a.update(provider_licensed_for_canonical=True)),
        ("R92_PROMOTION", lambda a,m: a.update(can_create_r92=True)),
        ("DUPLICATE", lambda a,m: a["records"][0].update(symbol=a["records"][1]["symbol"])),
        ("WRONG_NAME", lambda a,m: a["records"][2].update(security_name="Other Issuer")),
        ("WRONG_CIK_SOURCE", lambda a,m: a["records"][6].update(
            sec_source_url="https://www.sec.gov/Archives/edgar/data/2107979/000121390026092711/x-index.htm")),
        ("CROSSFILER_BLANK", lambda a,m: a["records"][6].update(sec_issuer_sic=6770)),
        ("SEC_FUTURE", lambda a,m: a["records"][7].update(sec_filing_date="2026-10-16")),
        ("HCAC_UNDATED_MISREAD", lambda a,m: a["records"][4].update(sec_issuer_sic=3341)),
        ("MASTER_FALSE_PASS", lambda a,m: m.update(unknown_symbols=m["unknown_symbols"][:-1])),
        ("MASTER_SCOPE_COUNT", lambda a,m: m.update(pass_count=3186)),
        ("MISSING_CIK", lambda a,m: a["records"][1].update(cik="")),
        ("FAKE_PHONE", lambda a,m: a.update(device_receipt_attested=True)),
    ]
    for name, mutation in mutations:
        a,m = copy.deepcopy(audit),copy.deepcopy(master)
        mutation(a,m)
        try:
            validate(a,m)
        except ValueError:
            continue
        raise RuntimeError("XRAY_SEC_NINE_UNSAFE_MUTATION_ACCEPTED:" + name)
    print("XRAY_NINE_SEC_UNKNOWN_SELFTEST=PASS_13_FAIL_CLOSED_MUTANTS_ZERO_PROMOTION")
    return good

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    arg = parser.parse_args()
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    result = selftest(audit,master) if arg.selftest else validate(audit,master)
    print("XRAY_NINE_SEC_PIT_DIAGNOSTIC=" + json.dumps(result,sort_keys=True))

if __name__ == "__main__":
    main()
