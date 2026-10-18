#!/usr/bin/env python3
"""XRAY C4.17 two independent Rallies EOD source/rights forensic gates.

Offline and diagnostic only. A market-data vendor must separately attest
unattended non-display rights, volume lineage, same-ASOF source bytes and
full C4.17 checks. This module NEVER supplies price/MC/R92/AL authority.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
SCHEMA = "XRAY_RALLIES_AUTHORITY_DOUBLE_GATE_AUDIT_V1"


def require(ok, label):
    if not ok:
        raise ValueError("XRAY_RALLIES_DOUBLE_GATE_" + label)


def iso(s):
    require(type(s) is str and re.fullmatch(r"\d{4}-\d\d-\d\d",s) is not None,
            "ASOF_FORMAT")
    try: d=date.fromisoformat(s)
    except ValueError as e: raise ValueError("XRAY_RALLIES_DOUBLE_GATE_ASOF_DATE") from e
    require(d.isoformat()==s,"ASOF_CANONICAL")
    return d


def unique_symbols(values, name):
    require(type(values) is list, name+"_TYPE")
    require(len(values)==len(set(values)) and
            all(type(x) is str and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}",x)
                for x in values),name+"_INVALID")
    return set(values)



def historical_primary_inventory(asof, names):
    """Classify *filenames*, not vendor proof, by their exact DV30 evidence epoch.

    Earlier classifications and future-dated files are not current evidence.
    This inventory never attests licensing, RTH volume, prices or R92.
    """
    current = iso(asof)
    require(type(names) in (list, tuple) and all(type(x) is str for x in names),
            "INVENTORY_FILENAME_LIST")
    prior, same, future = [], [], []
    for name in set(names):
        if "/" in name or "\\\\" in name:
            continue
        match = re.fullmatch(
            r"rallies_dv30_(\d{8})_classification(?:_v([1-9][0-9]*))?\.json",
            name,
        )
        if match is None:
            continue
        if match.group(2) is not None and int(match.group(2)) < 2:
            continue
        stamp = match.group(1)
        try:
            stamped = date.fromisoformat(
                f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}")
        except ValueError:
            continue
        if stamped < current:
            prior.append((stamped, name))
        elif stamped == current:
            same.append(name)
        else:
            future.append(name)
    latest = max((d for d, _ in prior), default=None)
    return {
        "asof_et": current.isoformat(),
        "same_asof_artifact_present": bool(same),
        "same_asof_candidates": sorted(same),
        "latest_prior_asof_et": latest.isoformat() if latest else None,
        "prior_candidate_count": len(prior),
        "future_candidate_count": len(future),
        "old_evidence_never_rolls_forward": True,
        "raw_vendor_data_attested": False,
        "runner_license_attested": False,
        "may_promote_price_pass": False,
        "may_promote_r92": False,
        "execution": "NONE",
        "real_money": "NO-GO",
    }

def inspect(master, price, governance, terminal, primary_bytes=None):
    """No provider calls. Reject corrupted evidence before producing verdict."""
    require(all(type(x) is dict for x in (master,price,governance,terminal)),
            "DOCUMENT_TYPE")
    asof=iso(master.get("asof_et"))
    require(iso(price.get("asof_et"))==asof,"MASTER_PRICE_ASOF_MISMATCH")
    terminal_asof=iso(terminal.get("asof_et"))
    require(terminal_asof<=asof,"TERMINAL_FUTURE_EPOCH")
    for name,doc in (("MASTER",master),("PRICE",price),("GOV",governance),("TERMINAL",terminal)):
        require(doc.get("execution")=="NONE" and doc.get("real_money")=="NO-GO",
                name+"_NO_TRADE_CONTRACT")
    require(master.get("unknown_never_pass") is True and
            price.get("unknown_never_pass") is True and
            governance.get("unknown_never_pass") is True,"UNKNOWN_NEVER_PASS")
    require(governance.get("schema")=="XRAY_PROVIDER_AUTOMATION_GOVERNANCE_V1",
            "GOVERNANCE_SCHEMA")
    passed=unique_symbols(master.get("pass_symbols"),"MASTER_PASS")
    master_unknown=unique_symbols(master.get("unknown_symbols"),"MASTER_UNKNOWN")
    require(not passed.intersection(master_unknown),"MASTER_PARTITION_OVERLAP")
    require(type(master.get("pass_count")) is int and master["pass_count"]==len(passed)
        and type(master.get("unknown_count")) is int
        and master["unknown_count"]==len(master_unknown),"MASTER_COUNTS")
    require(price.get("schema")=="XRAY_CANONICAL_PRICE_DV30_V1",
            "PRICE_SCHEMA")
    require(price.get("source_master_queue_hash")==master.get("pass_hash")
        and price.get("source_master_count")==len(passed),
        "MASTER_QUEUE_LINEAGE")
    rows=price.get("results")
    require(type(rows) is dict and set(rows)==passed,"PRICE_SCOPE_EXACT")
    pxpass=unique_symbols(price.get("pass_symbols"),"PRICE_PASS")
    unknown=unique_symbols(price.get("unknown_symbols"),"PRICE_UNKNOWN")
    blocked=unique_symbols(price.get("blocked_symbols"),"PRICE_BLOCKED")
    require(not pxpass.intersection(unknown|blocked) and
            not unknown.intersection(blocked),"PRICE_PARTITION_OVERLAP")
    require(all(type(price.get(k)) is int and price[k]==len(v)
                for k,v in (("pass_count",pxpass),("unknown_count",unknown),
                            ("blocked_count",blocked))),"PRICE_COUNTS")
    require(all((rows.get(s) or {}).get("status")=="UNKNOWN" for s in unknown),
            "UNKNOWN_ROW_STATUS")
    require({sym for sym,row in rows.items()
             if isinstance(row,dict) and row.get("status")=="UNKNOWN"}==unknown,
            "UNKNOWN_PARTITION_EXACT")
    require(all((rows.get(s) or {}).get("status")=="PASS_PRICE_DV30" for s in pxpass),
            "PRICE_PASS_ROW_STATUS")
    provider=(governance.get("providers") or {}).get("RALLIES") or {}
    claimed_entitlement=(provider.get("automated_non_display_runner_entitlement")=="ATTESTED"
                          and provider.get("positive_price_dv30_promotion_allowed") is True
                          and provider.get("passive_reader_positive_promotion_allowed") is True)
    claimed_volume=(provider.get("unadjusted_official_rth_integer_volume_lineage")=="ATTESTED")
    full_claim=bool(claimed_entitlement and claimed_volume and
                    provider.get("paid_top_up_allowed") is False)
    reasons=Counter(str(((rows.get(s) or {}).get("info") or {}).get("reason")
                       or "NO_REASON") for s in unknown)
    blockers=[]
    if primary_bytes is None:
        state="MISSING"
        blockers.append("MISSING_SAME_ASOF_RALLIES_CLASSIFICATION")
        source_digest=None
    else:
        require(type(primary_bytes) is bytes,"PRIMARY_BYTES_TYPE")
        source_digest=hashlib.sha256(primary_bytes).hexdigest()
        try:
            witness=json.loads(primary_bytes.decode("utf-8"))
        except (ValueError,UnicodeError):
            witness=None
        state="PRESENT_RESEARCH_ONLY"
        if not isinstance(witness,dict):
            state="INVALID"
            blockers.append("INVALID_RALLIES_CLASSIFICATION_BYTES")
        elif (witness.get("asof_et")!=asof.isoformat()
              or witness.get("schema")!="XRAY_RALLIES_DV30_CLASSIFICATION_V1"
              or witness.get("authority")!="C4.17_RALLIES_EXACT30_PRIMARY"
              or witness.get("execution")!="NONE"
              or witness.get("real_money")!="NO-GO"
              or witness.get("unknown_never_pass") is not True):
            state="INVALID"
            blockers.append("RALLIES_CLASSIFICATION_WRONG_ASOF_OR_SCHEMA")
    if not claimed_entitlement:
        blockers.append("RALLIES_AUTOMATED_NONDISPLAY_ENTITLEMENT_UNATTESTED")
    if not claimed_volume:
        blockers.append("RALLIES_RTH_INTEGER_VOLUME_NOT_ATTESTED")
    if unknown:
        blockers.append("PRICE_UNKNOWN_NEEDS_AUTHENTICATED_SIP_BRIDGE")
    if terminal_asof<asof:
        blockers.append("CANONICAL_TERMINAL_ASOF_STALE")
    r92=terminal.get("r92_candidates")
    require(type(r92) is list,"TERMINAL_R92_TYPE")
    if r92:
        blockers.append("TERMINAL_CLAIMS_R92_BUT_SOURCE_GATES_BLOCKED")
    if pxpass and (state!="PRESENT_RESEARCH_ONLY" or not full_claim):
        raise ValueError("XRAY_RALLIES_DOUBLE_GATE_UNATTESTED_CANONICAL_PRICE_PASS")
    # This is solely a diagnostic; even a complete-looking uploaded
    # classification is NOT source license, raw-bar lineage or R92 proof.
    blockers.append("RAW_RALLIES_VENDOR_SESSION_BYTES_NOT_INDEPENDENTLY_ATTESTED_BY_AUDIT")
    return {
        "schema":SCHEMA,
        "status":"BLOCKED_SOURCE_EVIDENCE_OR_RIGHTS",
        "asof_et":asof.isoformat(),
        "canonical_terminal_asof_et":terminal_asof.isoformat(),
        "price_pass_count":len(pxpass),
        "price_unknown_count":len(unknown),
        "unknown_reason_counts":dict(sorted(reasons.items())),
        "source_state":{
            "status":state,
            "source_sha256":source_digest,
            "is_full_rallies_authority_attested":False,
            "same_asof_file_is_not_raw_vendor_proof":True
        },
        "governance_state":{
            "rallies_license_and_volume_claimed":full_claim,
            "entitlement_claimed":claimed_entitlement,
            "integer_volume_lineage_claimed":claimed_volume,
            "rights_independently_proven_by_this_audit":False,
        },
        "blockers":sorted(set(blockers)),
        "full_e2e_source_attested_by_this_audit":False,
        "may_promote_price_pass":False,
        "may_promote_r92":False,
        "may_notify_user":False,
        "buy_signals":0,
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    a=parser.parse_args()
    def load(path):
        return json.loads((ROOT/path).read_text(encoding="utf-8"))
    master=load("canonical_current_master_manifest.json")
    price=load("canonical_current_price_dv30.json")
    gov=load("provider_automation_governance.json")
    term=load("canonical_current_terminal.json")
    asof=iso(price["asof_et"])
    prefix=f"rallies_dv30_{asof.strftime('%Y%m%d')}_classification"
    directory=ROOT/"evidence"
    paths=[]
    for path in directory.glob(prefix+"*.json"):
        name=path.stem
        if name==prefix: paths.append((1,path))
        else:
            tail=name.removeprefix(prefix)
            if re.fullmatch(r"_v[2-9][0-9]*",tail):
                paths.append((int(tail[2:]),path))
    witness=max(paths,key=lambda x:x[0])[1].read_bytes() if paths else None
    result=inspect(master,price,gov,term,witness)
    result["historical_primary_inventory"]=historical_primary_inventory(
        asof.isoformat(), [p.name for p in directory.iterdir() if p.is_file()]
    )
    result["primary_expected_path"]="nasdaq-xray/evidence/"+prefix+".json"
    result["primary_selected_file"]=("nasdaq-xray/evidence/"+max(paths,key=lambda x:x[0])[1].name) if paths else None
    target=a.out.resolve()
    require(not target.is_relative_to(ROOT.parent.resolve()),"REPO_WRITE_NOT_ALLOWED")
    target.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"asof_et":result["asof_et"],
                      "primary":result["source_state"]["status"],
                      "unknown":result["price_unknown_count"],
                      "rights_attested":result["governance_state"]["rallies_license_and_volume_claimed"],
                      "blockers":result["blockers"],"AL":result["buy_signals"]},
                     sort_keys=True))


if __name__=="__main__":
    main()
