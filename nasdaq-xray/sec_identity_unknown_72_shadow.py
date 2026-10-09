#!/usr/bin/env python3
"""Read-only current official SEC SIC diagnosis of frozen 2026-10-08 unknowns.

SEC submissions SIC today is NOT historical ASOF issuer status and a
non-6770 SIC NEVER proves de-SPAC merger completion. Outputs operational
classifications only and never modifies master or admits a trading signal.
"""
import argparse
import collections
import json
import os
import time
from pathlib import Path
from sec_free_mc_multisymbol_pit_audit import git_blob_sha,map_ciks,SEC_MAP
from sec_official_free_mc_transport_probe import get_json,valid_operator_contact

ROOT=Path(__file__).resolve().parent

def scope():
    b=(ROOT/"canonical_current_master_manifest.json").read_bytes()
    j=json.loads(b)
    syms=j.get("unknown_symbols") or []
    if (j.get("asof_et")!="2026-10-08"
            or len(syms)!=int(j.get("unknown_count",-1))
            or len(set(syms))!=len(syms) or not syms):
        raise ValueError("EXACT_MASTER_UNKNOWN_SCOPE_INVALID")
    if set(syms)&set(j.get("pass_symbols") or []):
        raise ValueError("MASTER_IDENTITY_UNKNOWN_INTERSECTS_PASS")
    return j["asof_et"],sorted(syms),git_blob_sha(b)

def classify(sub,expected_cik):
    if str(sub.get("cik") or "").lstrip("0")!=expected_cik.lstrip("0"):
        return "UNKNOWN_SEC_CIK_MISMATCH"
    sic=sub.get("sic")
    desc=str(sub.get("sicDescription") or "").casefold().strip()
    try:sic=int(sic)
    except (TypeError,ValueError):return "UNKNOWN_SEC_SIC_MISSING"
    if sic<=0:return "UNKNOWN_SEC_SIC_INVALID"
    if sic==6770:
        if desc and not desc.startswith("blank checks"):
            return "UNKNOWN_SEC_SIC_DESCRIPTION_CONFLICT"
        return "SEC_CURRENT_SIC_6770_SHADOW_EXCLUSION_CANDIDATE"
    if desc.startswith("blank checks"):
        return "UNKNOWN_SEC_SIC_DESCRIPTION_CONFLICT"
    return "SEC_CURRENT_NON6770_MERGER_COMPLETION_UNPROVEN"

def selftest():
    assert classify({"cik":123,"sic":6770,"sicDescription":"Blank Checks"},"0000000123").startswith("SEC_CURRENT_SIC_6770")
    assert classify({"cik":123,"sic":7374,"sicDescription":"Computer"},"0000000123")=="SEC_CURRENT_NON6770_MERGER_COMPLETION_UNPROVEN"
    assert classify({"cik":123,"sic":7374,"sicDescription":"Blank Checks"},"0000000123")=="UNKNOWN_SEC_SIC_DESCRIPTION_CONFLICT"
    assert classify({"cik":123,"sic":6770,"sicDescription":"Computer"},"0000000123")=="UNKNOWN_SEC_SIC_DESCRIPTION_CONFLICT"
    assert classify({"cik":123,"sic":6770},"0000000999")=="UNKNOWN_SEC_CIK_MISMATCH"
    assert classify({"cik":123},"0000000123")=="UNKNOWN_SEC_SIC_MISSING"
    print("XRAY_SEC_72_SELFTEST=PASS_CURRENT_SIC_NEVER_OPERATING_PASS")

def run():
    asof,syms,blob=scope()
    out={"schema":"XRAY_SEC_CURRENT_IDENTITY_UNKNOWN_SHADOW_V1",
         "asof_et":asof,"master_git_blob_sha":blob,"requested_count":len(syms),
         "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
         "master_modified":False,"master_identity_pass_change":0,
         "official_sic_is_current_not_historical_pit":True,
         "sec_nonblank_is_not_merged_operating_proof":True,
         "c417_primary_mc_count":0,"research_candidate_count":0,
         "statuses":{},"counts":{},"transport":"NOT_RUN"}
    ua=os.environ.get("XRAY_SEC_USER_AGENT","")
    if not valid_operator_contact(ua):
        return dict(out,transport="BLOCKED_SEC_CONTACT")
    try:
        routes=map_ciks(get_json(SEC_MAP,ua))
    except ValueError as exc:
        return dict(out,transport="BLOCKED_SEC_TICKER_MAP",failure_code=str(exc))
    for i,sym in enumerate(syms):
        cik=routes.get(sym)
        if not cik:
            out["statuses"][sym]="UNKNOWN_NO_CURRENT_NASDAQ_CIK"
            continue
        try:
            sub=get_json(f"https://data.sec.gov/submissions/CIK{cik}.json",ua)
            out["statuses"][sym]=classify(sub,cik)
        except ValueError as exc:
            out["statuses"][sym]="UNKNOWN_SEC_TRANSPORT"
            if str(exc) in ("SEC_HTTP_403","SEC_HTTP_429"):
                for remaining in syms[i+1:]:
                    out["statuses"][remaining]="UNKNOWN_NOT_ATTEMPTED_SEC_FAIR_ACCESS"
                out["transport"]="BLOCKED_SEC_FAIR_ACCESS"
                break
        if i+1<len(syms):time.sleep(0.26)
    out["counts"]=dict(sorted(collections.Counter(out["statuses"].values()).items()))
    if out["transport"]=="NOT_RUN":
        out["transport"]="SEC_CURRENT_SIC_SHADOW_COMPLETE"
    return out

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--output")
    a=p.parse_args()
    if a.selftest:selftest()
    else:
        report=run()
        if a.output:Path(a.output).write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
        print("XRAY_SEC_72_STATUS="+report["transport"])
        print("XRAY_SEC_72_COUNTS="+json.dumps(report["counts"],sort_keys=True))
        print("XRAY_SEC_72_MASTER_PASS_ADDED=0_SHADOW_ONLY")
        if report["transport"].startswith("BLOCKED_"):raise SystemExit(2)
