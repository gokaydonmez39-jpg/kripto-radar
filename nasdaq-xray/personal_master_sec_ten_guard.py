#!/usr/bin/env python3
"""Strict, reversible ten-issuer CIK routing / SPAC exclusion research audit."""
import argparse
import copy
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parent
MASTER=ROOT/"research/master_20261012_sec_pit_frozen_manifest.json"
CURRENT_MASTER=ROOT/"canonical_current_master_manifest.json"
FROZEN_MASTER_SHA="fb64a44b79ced9dcda390f5661b796ee13a60f63"
SEC=ROOT/"research/master_ten_sec_cik_sic_resolution_20261012_v1.json"
RESEARCH=ROOT/"research/personal_master_20261012_sec_cik_exclusion_v1.json"
POLICY=ROOT/"personal_research_technical_policy_v1.json"
def blob(path):
    raw=path.read_bytes()
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
def must(ok,reason):
    if not ok:raise ValueError("MASTER_TEN_PERSONAL_"+reason)
def validate(m,s,p,o,blobs):
    must(blobs["master"]==FROZEN_MASTER_SHA,"HISTORICAL_MASTER_IMMUTABLE_SHA")
    keys=sorted(m["unknown_symbols"])
    must(len(keys)==10 and m["unknown_count"]==10,"SOURCE")
    must(s.get("asof_et")==m.get("asof_et")==o.get("asof_et")=="2026-10-12","ASOF")
    must(p.get("can_override_canonical_unknown") is False
         and p.get("can_create_r92") is False,"PERSONAL_POLICY")
    must(s.get("source_master_git_blob_sha")==blobs["master"]
         and o.get("source_master_blob_sha")==blobs["master"]
         and o.get("source_ten_cik_sic_blob_sha")==blobs["sec"]
         and o.get("source_policy_blob_sha")==blobs["policy"],"BLOBS")
    must(s.get("cik_matched_count")==10 and s.get("cik_unmapped_count")==0,"CIK_CENSUS")
    must(set(s.get("rows") or {})==set(keys)
         and set(o.get("resolved_conservative_exclusions") or {})==set(keys),
         "TEN_EXACT_SYMBOLS")
    must(o.get("personal_research_unknown_identity_count")==0
         and o.get("production_master_unknown_remains")==10
         and o.get("personal_research_pass_count")==m.get("pass_count")
         and o.get("new_spac_exclusions_count")==10
         and o.get("personal_research_total_excluded_count")==
             m.get("explicit_excluded_count")+10,"NO_CROSS_PROMOTION")
    must(o.get("canonical_master_mutated") is False
         and o.get("operating_class_positive_promotions")==0
         and o.get("can_create_r92") is False and
         o.get("full_go") is False and
         o.get("execution")=="NONE" and
         o.get("real_money")=="NO-GO","NO_ALPHA")
    for symbol in keys:
        v=s["rows"][symbol]
        w=o["resolved_conservative_exclusions"][symbol]
        must(type(v.get("cik")) is str and re.fullmatch(r"\d{10}",v["cik"])
             and w.get("cik")==v["cik"],"CIK_"+symbol)
        uri=urlsplit(v["sec_filing_url"])
        must(uri.scheme=="https" and uri.netloc=="www.sec.gov"
             and uri.path.startswith("/Archives/edgar/data/"),"SEC_URL_"+symbol)
        d=date.fromisoformat(v["filing_evidence_date"])
        must(d<=date.fromisoformat(m["asof_et"]),"LOOKAHEAD_"+symbol)
        must(v.get("do_not_auto_promote_to_operating") is True and
             w.get("listed_class_not_promoted") is True and
             w.get("classification")=="EXCLUDED_PENDING_DE_SPAC_OPERATING_PROOF"
             and w.get("requires_fresh_post_combination_proof") is True,
             "EXCLUSION_"+symbol)
    must(s["rows"]["IPXG"]["cik"]=="0002088805"
         and s["rows"]["HCAC"]["cik"]=="0002079013"
         and 6770 in s["rows"]["HCAC"].get("competing_2026_sic_codes",[])
         and 3341 in s["rows"]["HCAC"].get("competing_2026_sic_codes",[]),
         "IPXG_HCAC_IDENTITIES")
    return {"schema":"XRAY_PERSONAL_MASTER_CIK10_SELFTEST_RESULT_V1",
            "source_master_git_blob_sha":blobs["master"],
            "source_sec_git_blob_sha":blobs["sec"],
            "source_personal_master_git_blob_sha":blobs["research"],
            "asof_et":"2026-10-12",
            "issuer_cik_matched":10,"personal_unknown_issuer_cik":0,
            "personal_operating_excluded":10,"personal_pass_created":0,
            "production_unknown_unchanged":10,
            "r92_created":False,"real_money":"NO-GO"}
def selftest(m,s,p,o,sha):
    validate(m,s,p,o,sha)
    current=json.loads(CURRENT_MASTER.read_text())
    if current.get("asof_et")!="2026-10-12":
        try:
            validate(current,s,p,o,{**sha,"master":blob(CURRENT_MASTER)})
        except (ValueError,KeyError):
            pass
        else:
            raise RuntimeError("LIVE_MASTER_REUSED_AS_HISTORICAL_PIT")
    tests=[
      lambda x:x["o"].update(personal_research_unknown_identity_count=1),
      lambda x:x["o"].update(source_master_blob_sha="0"*40),
      lambda x:x["s"]["rows"].pop("HCAC"),
      lambda x:x["s"]["rows"]["HCAC"].update(cik="0000000000"),
      lambda x:x["s"]["rows"]["IPXG"].update(cik="0000000001"),
      lambda x:x["s"]["rows"]["ALIS"].update(filing_evidence_date="2026-10-14"),
      lambda x:x["s"]["rows"]["MACI"].update(sec_filing_url="https://example.net/bad"),
      lambda x:x["o"].update(operating_class_positive_promotions=1),
      lambda x:x["o"]["resolved_conservative_exclusions"]["HCAC"].update(
        classification="PASS_OPERATING"),
      lambda x:x["o"].update(production_master_unknown_remains=0)]
    for i,change in enumerate(tests):
        x=copy.deepcopy({"m":m,"s":s,"p":p,"o":o,"sha":sha})
        change(x)
        try:validate(x["m"],x["s"],x["p"],x["o"],x["sha"])
        except (ValueError,KeyError):continue
        raise AssertionError("FALSE_RESEARCH_PASS_"+str(i))
    print("XRAY_PERSONAL_TEN_CIK_SPAC_SELFTEST=PASS_10_NEGATIVES_IMMUTABLE_OCT12_ARCHIVE")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    m=json.loads(MASTER.read_text())
    s=json.loads(SEC.read_text())
    p=json.loads(POLICY.read_text())
    o=json.loads(RESEARCH.read_text())
    sha={"master":blob(MASTER),"sec":blob(SEC),
         "policy":blob(POLICY),"research":blob(RESEARCH)}
    if args.selftest:selftest(m,s,p,o,sha);return
    out=validate(m,s,p,o,sha)
    if args.out is not None:
        if args.out.resolve().is_relative_to(ROOT.parent.resolve()):
            raise ValueError("NO_PRODUCTION_WRITE")
        args.out.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("XRAY_PERSONAL_CIK_EXACT=10_OF_10")
    print("XRAY_PERSONAL_CONSERVATIVE_EXCLUSION=10")
    print("XRAY_C417_MASTER_UNKNOWN_REMAINS=10")

if __name__=="__main__":main()
