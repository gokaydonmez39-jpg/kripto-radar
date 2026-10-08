#!/usr/bin/env python3
"""C4.17 WATCH diagnostics, not a BUY/AL signal or live market-data authority.
Inputs: exact local canonical immutable-source chain. Never creates GO or orders.
"""
import argparse
import copy
import hashlib
import json
import math
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
FILES={
    "terminal":"canonical_current_terminal.json",
    "master":"canonical_current_master_manifest.json",
    "full_state":"canonical_current_full_state.json",
    "price":"canonical_current_price_dv30.json",
    "history":"canonical_current_history.json",
    "deep":"canonical_current_deep_full.json",
    "final":"canonical_current_final_tech.json",
}
CHECK=("master","full_state","price","history","deep","final")


def read(root,name):
    path=root/name
    raw=path.read_bytes()
    return json.loads(raw),hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()


def build(root):
    t,terminal_blob=read(root,FILES["terminal"])
    evidence=t.get("evidence") or {}
    sources={}
    discrepancies=[]
    for key,filename in FILES.items():
        if key=="terminal":
            continue
        try:
            obj,sha=read(root,filename)
            sources[key]=(obj,sha)
            bound=evidence.get(key) or {}
            if bound.get("path")!="nasdaq-xray/"+filename or bound.get("blob_sha")!=sha:
                discrepancies.append(key+":SOURCE_BLOB_OR_PATH_DRIFT")
            if obj.get("asof_et")!=t.get("asof_et"):
                discrepancies.append(key+":ASOF_MISMATCH")
        except Exception as exc:
            discrepancies.append(key+":SOURCE_READ_"+type(exc).__name__)
    if (t.get("execution")!="NONE" or t.get("real_money")!="NO-GO"
        or t.get("unknown_never_pass") is not True):
        discrepancies.append("TERMINAL_SAFETY_HEADER")
    for key in ("master","full_state","price","history","deep","final"):
        if key in sources and (sources[key][0].get("execution")!="NONE" or
                               sources[key][0].get("real_money")!="NO-GO"):
            discrepancies.append(key+":SAFETY_HEADER")
    try:
        mc_ref=evidence.get("mc") or {}
        mc_path=str(mc_ref.get("path") or "")
        if not (mc_path.startswith("nasdaq-xray/canonical_mc_bridge_") and mc_path.endswith(".json")
                and "/" not in mc_path[len("nasdaq-xray/"):]):
            raise ValueError("MC_PATH")
        mc,mcsha=read(root,mc_path.removeprefix("nasdaq-xray/"))
        if mcsha!=mc_ref.get("blob_sha"):
            discrepancies.append("MC_IMMUTABLE_BLOB_DRIFT")
        if "price" in sources and mc.get("input_blob_sha")!=sources["price"][1]:
            discrepancies.append("MC_PRICE_BINDING_DRIFT")
        if mc.get("asof_et")!=t.get("asof_et"):
            discrepancies.append("MC_ASOF")
    except Exception as exc:
        discrepancies.append("MC_READ_"+type(exc).__name__)
    if "final" in sources and "deep" in sources:
        if sources["final"][0].get("source_deep_blob_sha")!=sources["deep"][1]:
            discrepancies.append("FINAL_DEEP_BINDING")
    exact=not discrepancies
    deep=sources.get("deep",({},None))[0]
    final=sources.get("final",({},None))[0]
    stage=sorted(set(deep.get("b_armed_rs_event_watch") or []))
    final_rows=final.get("results") or {}
    risk_rejections=[]
    for key,row in sorted(final_rows.items()):
        risk_value=(row.get("geometry") or {}).get("risk_percent")
        if isinstance(risk_value,bool) or not isinstance(risk_value,(int,float)):
            raise AssertionError("MISSING_OR_INVALID_FINAL_RISK:"+key)
        risk=float(risk_value)
        if not math.isfinite(risk) or risk<=0:
            raise AssertionError("INVALID_FINAL_RISK:"+key)
        if risk>0.08 and (row.get("pre_g9_tech_pass") is True or row.get("technical_hard_pass") is True):
            raise AssertionError("C4_17_RISK_FAIL_MUST_NEVER_PROMOTE:"+key)
        risk_rejections.append({
            "key":key,"family":row.get("family"),"risk_pct":round(100*risk,3),
            "risk_limit_pct":8.0,"rr_basic":(row.get("rr") or {}).get("basic"),
            "rr_severe":(row.get("rr") or {}).get("severe"),
            "lifecycle":row.get("lifecycle"),"event_status":row.get("event_status"),
            "mc_cap":row.get("state_cap"),"result":row.get("result"),
            "blockers":list(row.get("diagnostic_blockers") or []),
            "al":False,
        })
    risk_rejections.sort(key=lambda row:(abs(row["risk_pct"]-8.0),row["key"]))
    watched=[{
        "symbol":sym,"setup":"B_ARMED","class":"WATCH_ONLY_PENDING_EVENT_OR_BREAKOUT",
        "missing":"NO_CONFIRMED_EVENT_CLEAN_BREAKOUT_AND_NON_ALPHA_GATES",
        "al":False,
    } for sym in stage]
    return {
      "schema":"XRAY_C417_RESEARCH_WATCH_RADAR_V1","asof_et":t.get("asof_et"),
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "alpha_authority":False,"decision_authority":False,"g9_authority":False,
      "source_exact":exact,"binding_discrepancies":sorted(set(discrepancies)),
      "status":"WATCH_RESEARCH_EXACT" if exact else "STALE_SNAPSHOT_WATCH_BLOCKED",
      "observed_b_watch_count":len(watched),
      "live_watch_count":len(watched) if exact else 0,
      "research_watch":watched if exact else [],
      "stale_observations_not_live":watched if not exact else [],
      "rejected_final_count":len(risk_rejections),
      "rejected_final_diagnostics":risk_rejections,
      "pre_g9_al_count":int(final.get("pre_g9_tech_pass_count") or 0),
      "buy_candidates":[],"go":False,"orders":[],
      "source_blobs":{"terminal":terminal_blob,**{k:v[1] for k,v in sources.items()}},
      "disclaimer":"Not AL, not executable, not current if source_exact=false. No threshold relaxation.",
    }


def selftest():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        asof="2026-10-07"
        payload={key:{"asof_et":asof,"execution":"NONE","real_money":"NO-GO"}
                 for key in CHECK}
        payload["deep"]["b_armed_rs_event_watch"]=["TEST"]
        payload["final"]["results"]={"TEST|D":{
            "family":"D","geometry":{"risk_percent":0.12},
            "pre_g9_tech_pass":False,"technical_hard_pass":False,
            "rr":{"basic":1.0,"severe":0.8},"result":"FAIL_RISK_GEOMETRY",
            "diagnostic_blockers":["RISK_PERCENT_GT_8PCT"]}}
        payload["final"]["pre_g9_tech_pass_count"]=0
        for key,obj in payload.items():
            (root/FILES[key]).write_text(json.dumps(obj)+"\n")
        evidence={key:{"path":"nasdaq-xray/"+FILES[key],
                       "blob_sha":read(root,FILES[key])[1]} for key in CHECK}
        payload["final"]["source_deep_blob_sha"]=evidence["deep"]["blob_sha"]
        (root/FILES["final"]).write_text(json.dumps(payload["final"])+"\n")
        evidence["final"]["blob_sha"]=read(root,FILES["final"])[1]
        mcname="canonical_mc_bridge_20261007_c417_dv30_vtest.json"
        (root/mcname).write_text(json.dumps({"asof_et":asof,"input_blob_sha":evidence["price"]["blob_sha"]}))
        evidence["mc"]={"path":"nasdaq-xray/"+mcname,"blob_sha":read(root,mcname)[1]}
        (root/FILES["terminal"]).write_text(json.dumps({
            "asof_et":asof,"execution":"NONE","real_money":"NO-GO",
            "unknown_never_pass":True,"evidence":evidence}))
        r=build(root)
        assert r["source_exact"] and r["live_watch_count"]==1 and not r["buy_candidates"]
        assert r["rejected_final_count"]==1 and r["go"] is False
        (root/FILES["master"]).write_text(json.dumps({"asof_et":asof,"execution":"NONE","real_money":"NO-GO","x":"drift"}))
        r=build(root)
        assert not r["source_exact"] and not r["research_watch"]
        assert r["stale_observations_not_live"][0]["symbol"]=="TEST"
        altered=copy.deepcopy(payload["final"])
        altered["results"]["TEST|D"]["pre_g9_tech_pass"]=True
        (root/FILES["final"]).write_text(json.dumps(altered))
        try:
            build(root)
            raise AssertionError("UNSAFE_CANDIDATE_ACCEPTED")
        except AssertionError as e:
            assert "C4_17_RISK_FAIL_MUST_NEVER_PROMOTE" in str(e)
        for invalid in (None,0.0,-0.01,float("nan"),float("inf"),True,"0.02"):
            unsafe=copy.deepcopy(payload["final"])
            if invalid is None:
                del unsafe["results"]["TEST|D"]["geometry"]["risk_percent"]
            else:
                unsafe["results"]["TEST|D"]["geometry"]["risk_percent"]=invalid
            (root/FILES["final"]).write_text(json.dumps(unsafe)+"\n")
            try:
                build(root)
                raise AssertionError("INVALID_RISK_ACCEPTED")
            except AssertionError as e:
                assert "FINAL_RISK" in str(e),str(e)
    print("XRAY_WATCH_RESEARCH_FAIL_CLOSED_SELFTEST=PASS invalid_risk_cases=7")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out")
    args=parser.parse_args()
    if args.selftest:
        selftest()
    else:
        if not args.out:
            parser.error("--out required")
        result=build(ROOT)
        Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print(json.dumps({k:result[k] for k in (
            "status","source_exact","observed_b_watch_count","live_watch_count",
            "rejected_final_count","pre_g9_al_count","binding_discrepancies")},sort_keys=True))
