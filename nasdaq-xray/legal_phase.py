#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent
HISTORY=Path(os.getenv("XRAY_LEGAL_HISTORY", str(ROOT/"canonical_history_20260930.json")))
MASTER=Path(os.getenv("XRAY_LEGAL_MASTER", str(ROOT/"canonical_full_hard_gate_20260930_state.json")))
PROOF=Path(os.getenv("XRAY_LEGAL_PROOF", str(ROOT/"canonical_legal_proof_20260930.json")))
OUT=Path(os.getenv("XRAY_LEGAL_OUT", str(ROOT/"canonical_legal_20260930.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
ASOF_ENV=os.getenv("XRAY_ASOF")
SUSPECT=re.compile(r"\\bacquisition\\b|\\bspac\\b|\\bblank check\\b",re.I)

def blob_sha(p:Path):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def relpath(p:Path):
    try:return str(p.relative_to(ROOT.parent)).replace("\\","/")
    except Exception:return str(p)

def main():
    h=json.loads(HISTORY.read_text());m=json.loads(MASTER.read_text())
    asof=ASOF_ENV or h.get("asof_et")
    assert h["schema"] in {"XRAY_CANONICAL_HISTORY_V1","XRAY_CANONICAL_HISTORY_V2"} and h["task_id"]==TASK_ID and h["asof_et"]==asof
    if h["schema"]=="XRAY_CANONICAL_HISTORY_V2":
        assert h["input_count"]==456 and h["pass_count"]==442 and h["unknown_count"]==0
        assert h["c4_14_scope"]["mode"]=="MC_PRIMARY_PASS_ONLY"
        assert h["r92_ineligible"]==[] and set(h["state_caps"].values())=={"NORMAL"}
    assert m["task_id"]==TASK_ID and m["asof_et"]==asof
    proof={}
    if PROOF.exists():
        try:
            x=json.loads(PROOF.read_text())
            if x.get("schema")=="XRAY_CANONICAL_LEGAL_PROOF_V1" and x.get("task_id")==TASK_ID and x.get("asof_et")==asof:
                proof=x.get("proofs") or {}
        except Exception:pass
    results={};unknown=[];blocked=[];passed=[]
    for s in h["pass_symbols"]:
        name=str((m.get("security_names") or {}).get(s) or "")
        disc=(m.get("discovery") or {}).get(s) or {}
        industry=str(disc.get("industry") or "").strip()
        if industry.lower()=="blank checks":
            results[s]={"status":"BLOCK_LEGAL_SHELL","reason":"NASDAQ_SAME_RUN_INDUSTRY_BLANK_CHECKS","security_name":name}
            blocked.append(s);continue
        if SUSPECT.search(name):
            pv=proof.get(s)
            if pv and pv.get("decision")=="OPERATING_PASS" and pv.get("source") in {"SEC","ISSUER","NASDAQ_OFFICIAL","BIGDATA_SEC_GROUNDED"}:
                results[s]={"status":"PASS_LEGAL","reason":"EXPLICIT_OPERATING_PROOF","proof":pv};passed.append(s)
            elif pv and pv.get("decision")=="SHELL_BLOCK":
                results[s]={"status":"BLOCK_LEGAL_SHELL","reason":"EXPLICIT_SHELL_PROOF","proof":pv};blocked.append(s)
            else:
                results[s]={"status":"UNKNOWN_LEGAL","reason":"SUSPECT_SPAC_ACQUISITION_REQUIRES_PROOF","security_name":name,"industry":industry}
                unknown.append(s)
            continue
        results[s]={"status":"PASS_LEGAL","reason":"NO_SPAC_SHELL_INDICATOR_IN_OFFICIAL_IDENTITY_OR_SCREENER","security_name":name}
        passed.append(s)
    obj={
      "schema":"XRAY_CANONICAL_LEGAL_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "source_history_schema":h.get("schema"),
      "source_history_path":relpath(HISTORY),"source_history_blob_sha":blob_sha(HISTORY),
      "source_history_pass_hash":h.get("pass_hash"),
      "source_master_path":relpath(MASTER),"source_master_blob_sha":blob_sha(MASTER),
      "source_proof_path":relpath(PROOF) if PROOF.exists() else None,
      "source_proof_blob_sha":blob_sha(PROOF) if PROOF.exists() else None,
      "input_count":len(h["pass_symbols"]),
      "counts":{"PASS_LEGAL":len(passed),"BLOCK_LEGAL_SHELL":len(blocked),"UNKNOWN_LEGAL":len(unknown)},
      "pass_symbols":sorted(passed),"blocked_symbols":sorted(blocked),"unknown_symbols":sorted(unknown),
      "pass_hash":hashlib.sha256("\n".join(sorted(passed)).encode()).hexdigest(),
      "state_caps":h.get("state_caps") or {},"r92_ineligible":h.get("r92_ineligible") or [],
      "results":dict(sorted(results.items()))
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"counts":obj["counts"],"unknown_symbols":obj["unknown_symbols"],"pass_hash":obj["pass_hash"]},sort_keys=True))
if __name__=="__main__":main()
