#!/usr/bin/env python3
from __future__ import annotations
import collections, glob, hashlib, json, math, re, sys
from pathlib import Path
from statistics import median
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"canonical_alpha_calibration_audit.json"
TARGET_COMPARABLE_SESSIONS=60
CURRENT_POLICY_VERSION="C4.17"

def load(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}

def terminal_date(path: Path, obj: dict):
    a=str(obj.get("asof_et") or "")
    if a:
        return a
    m=re.search(r"(20\d{6})",path.name)
    if m:
        x=m.group(1)
        return f"{x[:4]}-{x[4:6]}-{x[6:]}"
    return ""

def paired_final(path: Path, asof: str):
    if path.name=="canonical_current_terminal.json":
        return ROOT/"canonical_current_final_tech.json"
    tag=asof.replace("-","")
    return ROOT/f"canonical_final_tech_{tag}.json"

def git_blob_sha(path: Path) -> str:
    data=path.read_bytes()
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\\0"+data).hexdigest()


def comparable_evidence(terminal: dict, final: dict, fp: Path,
                        asof: str, version: str, has_dv30: bool) -> tuple[bool, list[str]]:
    """Empirical calibration only: no partial/stale snapshot is one full session."""
    checks={
        "C417_POLICY_EXACT": version==CURRENT_POLICY_VERSION
            and final.get("source_compiled_policy_version")==CURRENT_POLICY_VERSION,
        "DV30_SCOPE_PRESENT": has_dv30,
        "COMPLETED_E2E": terminal.get("full_end_to_end_research_pass") is True
            and terminal.get("status")=="FULL_E2E_RESEARCH_PASS",
        "FINAL_SAME_ASOF": bool(asof and terminal.get("asof_et")==asof
            and final.get("asof_et")==asof),
        "FINAL_BLOB_EXACT": False,
    }
    link=(terminal.get("evidence") or {}).get("final") or {}
    if fp.is_file():
        checks["FINAL_BLOB_EXACT"]=(
            link.get("path")=="nasdaq-xray/"+fp.name
            and link.get("blob_sha")==git_blob_sha(fp)
        )
    rejected=sorted(k for k,passed in checks.items() if not passed)
    return not rejected,rejected


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        fp=Path(td)/"canonical_current_final_tech.json"
        final={"asof_et":"2026-10-08","source_compiled_policy_version":"C4.17"}
        fp.write_text(json.dumps(final))
        t={"asof_et":"2026-10-08","status":"FULL_E2E_RESEARCH_PASS",
           "full_end_to_end_research_pass":True,
           "evidence":{"final":{"path":"nasdaq-xray/"+fp.name,
                                "blob_sha":git_blob_sha(fp)}}}
        ok,why=comparable_evidence(t,final,fp,"2026-10-08","C4.17",True)
        assert ok and not why,(ok,why)
        from copy import deepcopy
        tests=[
            ("terminal_partial",lambda x,y:x.update(status="PARTIAL")),
            ("e2e_missing",lambda x,y:x.update(full_end_to_end_research_pass=False)),
            ("policy_drift",lambda x,y:y.update(source_compiled_policy_version="C4.14")),
            ("final_stale",lambda x,y:y.update(asof_et="2026-10-07")),
            ("blob_drift",lambda x,y:x["evidence"]["final"].update(blob_sha="0"*40)),
            ("path_drift",lambda x,y:x["evidence"]["final"].update(path="nasdaq-xray/fake.json")),
        ]
        for name,mutation in tests:
            case=deepcopy(t);v=deepcopy(final);mutation(case,v)
            valid,errors=comparable_evidence(case,v,fp,"2026-10-08","C4.17",True)
            assert not valid and errors,(name,errors)
        assert not comparable_evidence(t,final,fp,"2026-10-08","C4.17",False)[0]
        assert not comparable_evidence(t,final,fp,"2026-10-08","C4.14",True)[0]
        fp.unlink()
        assert not comparable_evidence(t,final,fp,"2026-10-08","C4.17",True)[0]
    print("XRAY_ALPHA_CALIBRATION_SOURCE_EXACT_SELFTEST=PASS_POSITIVE_9_NEGATIVE")


def main():
    terminals=[]
    seen=set()
    # Prefer the canonical current pointer for a repeated ASOF. One session
    # can never contribute more than one observation to calibration.
    for p in [ROOT/"canonical_current_terminal.json"]+sorted(ROOT.glob("canonical_terminal_20??????.json")):
        if not p.exists():
            continue
        t=load(p)
        asof=terminal_date(p,t)
        if not asof or asof in seen:
            continue
        seen.add(asof)
        fp=paired_final(p,asof)
        f=load(fp) if fp.exists() else {}
        version=str(t.get("compiled_policy_version") or f.get("source_compiled_policy_version") or "")
        counts=t.get("counts") or {}
        pre=int(counts.get("pre_g9_tech_pass",f.get("pre_g9_tech_pass_count",0)) or 0)
        final_count=int(counts.get("final_confirmed_candidates",f.get("fresh_current_candidate_count",0)) or 0)
        has_dv30=("price_dv30_pass" in counts) or (p.name=="canonical_current_terminal.json")
        comparable,rejection_reasons=comparable_evidence(
            t,f,fp,asof,version,has_dv30)
        terminals.append({
          "asof_et":asof,
          "terminal_path":f"nasdaq-xray/{p.name}",
          "final_path":f"nasdaq-xray/{fp.name}" if fp.exists() else None,
          "terminal_status":t.get("status"),
          "terminal_result":t.get("terminal_result"),
          "full_end_to_end_research_pass":t.get("full_end_to_end_research_pass"),
          "compiled_policy_version":version or None,
          "dv30_semantics_observed":has_dv30,
          "comparable_to_current_c417":comparable,
          "calibration_exclusion_reasons":rejection_reasons,
          "final_confirmed_candidates":final_count,
          "pre_g9_tech_pass":pre,
        })

    current=load(ROOT/"canonical_current_final_tech.json")
    results=current.get("results") or {}
    kill=collections.Counter()
    fam=collections.Counter()
    risk_values=[]; rr_basic=[]; rr_severe=[]
    risk_fail=rrb_fail=rrs_fail=overlap=0
    for key,row in sorted(results.items()):
        result=str(row.get("result") or "UNKNOWN")
        kill[result]+=1
        fam[str(row.get("family") or key.split("|")[-1])]+=1
        g=row.get("geometry") or {}
        rr=row.get("rr") or {}
        rp=g.get("risk_percent")
        if isinstance(rp,(int,float)) and math.isfinite(rp):
            risk_values.append(float(rp))
        b=rr.get("basic")
        if isinstance(b,(int,float)) and math.isfinite(b): rr_basic.append(float(b))
        s=rr.get("severe")
        if isinstance(s,(int,float)) and math.isfinite(s): rr_severe.append(float(s))
        risk_fail += int(row.get("risk_pass") is False)
        rrb_fail += int(rr.get("basic_pass") is False)
        rrs_fail += int(rr.get("severe_pass") is False)
        overlap += int(row.get("target_overlap") is True)

    test_src=(ROOT/"test_alpha_semantics.py").read_text() if (ROOT/"test_alpha_semantics.py").exists() else ""
    reachability_declared="FULL_R1_TO_PRE_G9_REACHABILITY" in test_src and 'reach["result"]=="PRE_G9_TECH_PASS"' in test_src
    comparable=[x for x in terminals if x["comparable_to_current_c417"]]
    zero_all=[x["asof_et"] for x in terminals if x["pre_g9_tech_pass"]==0]
    zero_comp=[x["asof_et"] for x in comparable if x["pre_g9_tech_pass"]==0]
    sample_ok=len(comparable)>=TARGET_COMPARABLE_SESSIONS
    status="CALIBRATION_SAMPLE_READY" if sample_ok else "INSUFFICIENT_POINT_IN_TIME_CURRENT_POLICY_SAMPLE"
    out={
      "schema":"XRAY_ALPHA_CALIBRATION_AUDIT_V1",
      "generated_at_utc":datetime.now(timezone.utc).isoformat(),
      "execution":"NONE","real_money":"NO-GO","alpha_authority":False,
      "unknown_never_pass":True,"no_threshold_change":True,
      "current_policy_version":CURRENT_POLICY_VERSION,
      "target_comparable_sessions":TARGET_COMPARABLE_SESSIONS,
      "comparable_current_policy_session_count":len(comparable),
      "status":status,
      "calibration_pass":bool(sample_ok),
      "reason":(
        "At least 60 source-exact completed point-in-time C4.17 sessions are available."
        if sample_ok else
        "Fewer than 60 complete, exact-final-SHA-bound C4.17+DV30 session snapshots exist; partial/stale and mixed-policy terminal outputs cannot prove signal scarcity or excessive thresholds."
      ),
      "observed_terminal_snapshots":terminals,
      "observed_snapshot_count":len(terminals),
      "zero_pre_g9_snapshot_dates":zero_all,
      "zero_pre_g9_comparable_dates":zero_comp,
      "mixed_policy_history_present":any(not x["comparable_to_current_c417"] for x in terminals),
      "positive_reachability_test_declared":reachability_declared,
      "current_finalist_diagnostics":{
        "asof_et":current.get("asof_et"),
        "candidate_count":len(results),
        "pre_g9_count":int(current.get("pre_g9_tech_pass_count",0) or 0),
        "family_counts":dict(sorted(fam.items())),
        "kill_reason_counts":dict(sorted(kill.items())),
        "risk_fail_count":risk_fail,
        "rr_basic_fail_count":rrb_fail,
        "rr_severe_fail_count":rrs_fail,
        "target_overlap_count":overlap,
        "risk_percent_min":min(risk_values) if risk_values else None,
        "risk_percent_median":median(risk_values) if risk_values else None,
        "risk_percent_max":max(risk_values) if risk_values else None,
        "rr_basic_max":max(rr_basic) if rr_basic else None,
        "rr_severe_max":max(rr_severe) if rr_severe else None,
      },
      "interpretation":{
        "functional_reachability":(
          "DECLARED_POSITIVE_TEST_EXISTS" if reachability_declared else "UNKNOWN"
        ),
        "empirical_calibration":"NOT_PROVEN" if not sample_ok else "SAMPLE_SIZE_READY_FOR_REVIEW",
        "zero_signal_claim":"CURRENT_SCOPE_ONLY_UNTIL_FULL_COVERAGE_AND_CALIBRATION_EVIDENCE_COMPLETE",
      },
    }
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":status,"snapshots":len(terminals),"comparable":len(comparable),
                      "current_candidates":len(results),"current_pre_g9":out["current_finalist_diagnostics"]["pre_g9_count"],
                      "kill_reasons":out["current_finalist_diagnostics"]["kill_reason_counts"]},sort_keys=True))

if __name__=="__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
