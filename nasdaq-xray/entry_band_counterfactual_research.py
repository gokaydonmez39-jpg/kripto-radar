#!/usr/bin/env python3
"""Research-only lower-entry counterfactual, NEVER an entry-model or AL override."""
import argparse,hashlib,json,math,pathlib,datetime
ROOT=pathlib.Path(__file__).resolve().parent
F=ROOT/"canonical_current_final_tech.json"
T=ROOT/"canonical_current_terminal.json"
def gitsha(path):
    b=path.read_bytes()
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
def rr(E,S,T,A,c):
    cost=c*A
    den=E-S+2*cost
    return (T-E-2*cost)/den if den>0 else float("-inf")
def calculate(E,S,T,A):
    if not all(math.isfinite(float(x)) for x in (E,S,T,A)) or min(E,A)<=0:
        raise ValueError("NONFINITE_OR_NONPOSITIVE_ENTRY_ATR")
    risk=(E-S)/E
    return risk,rr(E,S,T,A,.10),rr(E,S,T,A,.25)
def rowcheck(row):
    g=row.get("levels") or {}
    P=float(g["P"]); E=float(g["entry_model"]); S=float(g["S0"]); T=float(g["T1"]); A=float(g["A"])
    if not (A>0 and E>=P>0):
        raise ValueError("INVALID_ENTRY_BAND")
    current=calculate(E,S,T,A); lower=calculate(P,S,T,A)
    stored=row.get("geometry") or {}
    rrs=row.get("rr") or {}
    if abs(current[0]-float(stored["risk_percent"]))>1e-9 or abs(current[1]-float(rrs["basic"]))>1e-9 or abs(current[2]-float(rrs["severe"]))>1e-9:
        raise ValueError("PRODUCTION_MATH_DISAGREEMENT")
    # No threshold changes: D C4.17 = 8% risk, basic 2, severe 1.5
    if row.get("family")!="D":
        return {"evaluated":False,"reason":"FAMILY_NOT_D_NO_COUNTERFACTUAL_AUTHORITY"}
    return {"evaluated":True,
        "risk_current_pct":round(current[0]*100,4),
        "risk_low_pct":round(lower[0]*100,4),
        "rr_current_basic":round(current[1],4),
        "rr_low_basic":round(lower[1],4),
        "rr_low_severe":round(lower[2],4),
        "risk_low_pass":bool(0<=lower[0]<=.08),
        "rr_low_both_pass":bool(lower[1]>=2 and lower[2]>=1.5),
        "overlap":bool(row.get("target_overlap")),
        "lifecycle":str(row.get("lifecycle")),
        "event":str(row.get("event_status")),
        "not_alpha":True}
def selftest():
    assert calculate(100,95,115,2)[0]==.05
    assert calculate(100,95,115,2)[1]>2
    assert calculate(100,95,115,2)[2]>1.5
    assert calculate(100,95,100,2)[1]<0
    assert calculate(100,90,120,2)[0]>.08
    fixture={"family":"D","levels":{"P":98,"entry_model":100,"S0":95,"T1":115,"A":2},
             "geometry":{"risk_percent":calculate(100,95,115,2)[0]},
             "rr":{"basic":calculate(100,95,115,2)[1],"severe":calculate(100,95,115,2)[2]},
             "target_overlap":False,"lifecycle":"ENTRY_BAND","event_status":"CLEAN_DISCOVERY"}
    assert rowcheck(fixture)["risk_low_pass"]
    bad=json.loads(json.dumps(fixture));bad["geometry"]["risk_percent"]=.99
    try:rowcheck(bad);raise AssertionError("BAD_PRODUCTION_VALUE_ACCEPTED")
    except ValueError:pass
    print("XRAY_ENTRY_BAND_COUNTERFACTUAL_SELFTEST=PASS cases=7")
def run(out):
    j=json.loads(F.read_text());t=json.loads(T.read_text())
    assert j.get("source_compiled_policy_version")=="C4.17","POLICY_VERSION_DRIFT"
    sha=gitsha(F);bound=(t.get("evidence") or {}).get("final") or {}
    exact=(bound.get("path")=="nasdaq-xray/canonical_current_final_tech.json"
            and bound.get("blob_sha")==sha and t.get("asof_et")==j.get("asof_et"))
    results={}
    for key,v in sorted((j.get("results") or {}).items()):
        results[key]=rowcheck(v)
    d=[v for v in results.values() if v["evaluated"]]
    status="SOURCE_EXACT_RESEARCH_DIAGNOSTIC" if exact else "STALE_TERMINAL_RESEARCH_DIAGNOSTIC_ONLY"
    obj={"schema":"XRAY_C417_ENTRY_BAND_COUNTERFACTUAL_V1","asof_et":j.get("asof_et"),
        "final_blob_sha":sha,"terminal_blob_sha":gitsha(T),
        "terminal_final_binding_exact":exact,"status":status,
        "source_rows":len(results),"D_rows_evaluated":len(d),
        "lower_band_risk_pass":sum(x["risk_low_pass"] for x in d),
        "lower_band_risk_and_rr_pass":sum(x["risk_low_pass"] and x["rr_low_both_pass"] and not x["overlap"] for x in d),
        "d_reasons":results,
        "caution":"Counterfactual only. Frozen E_MODEL unchanged, no price data obtained and no alpha gates changed.",
        "execution":"NONE","real_money":"NO-GO","alpha_authority":False,"g9_pass":False,"account_pass":False,
        "orders":[],"buy_candidates":[]}
    pathlib.Path(out).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
    print("XRAY_COUNTERFACTUAL="+status+" total="+str(len(d))+" risk_low="+str(obj["lower_band_risk_pass"])+" risk_rr_low="+str(obj["lower_band_risk_and_rr_pass"]))
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--selftest",action="store_true");ap.add_argument("--out")
    a=ap.parse_args()
    if a.selftest:selftest()
    else:
        if not a.out:ap.error("--out required")
        run(a.out)
