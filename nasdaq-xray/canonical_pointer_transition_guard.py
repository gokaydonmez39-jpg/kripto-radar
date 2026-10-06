#!/usr/bin/env python3
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
def load(p): return json.loads(Path(p).read_text())
def state_hash(rev,state):
    raw=f"XRAY_STATE_REGISTER_V1\n{rev}\n"+json.dumps(state,ensure_ascii=False,separators=(",",":"))
    return hashlib.sha256(raw.encode()).hexdigest()
def blob(p): return subprocess.check_output(["git","hash-object",str(p)],cwd=REPO,text=True).strip()
def main():
    pp=ROOT/"chatgpt_canonical_state_v2.json"; tp=ROOT/"canonical_current_terminal.json"
    p=load(pp); t=load(tp); s=p["state_json"]; rev=int(p["revision"])
    assert p["schema"]=="XRAY_GITHUB_DURABLE_STATE_V3"
    assert p["execution"]=="NONE" and p["real_money"]=="NO-GO"
    assert int(s["revision"])==rev and s["schema"]=="XRAY_STATE_REGISTER_V1"
    assert state_hash(rev,s)==p["state_hash"]
    snap=REPO/p["immutable_snapshot_path"]; q=load(snap)
    assert q["revision"]==rev and q["state_hash"]==p["state_hash"] and q["state_json"]==s
    assert state_hash(rev,q["state_json"])==q["state_hash"]
    assert s["asof_et"]==t["asof_et"]
    if t["full_end_to_end_research_pass"] is not True:
        assert t["terminal_result"]=="PARTIAL_UNKNOWN"
        assert s["status"]=="TERMINAL_PARTIAL_UNKNOWN"
        a=t["asof_et"]
        assert not any(str(x).startswith(f"DAILY|{a}|") for x in s.get("daily_keys",[]))
        assert not any(f"DAILY_{a}" in str(x) for x in s.get("delivery_keys",[]))
        assert not any(isinstance(x,dict) and x.get("asof_et")==a for x in s.get("completed_epochs",[]))
        assert s.get("r92")==[] and s.get("r93")==[]
    proof=p.get("source_proof") or {}
    if proof.get("recovery_type")=="HASH_CHAIN_RECOVERY_REBASE":
        ap=REPO/proof["anchor_snapshot_path"]; a=load(ap)
        assert state_hash(int(a["revision"]),a["state_json"])==a["state_hash"]==proof["anchor_state_hash"]
        assert p["prev_state_hash"]==a["state_hash"]
    for k,m in (t.get("evidence") or {}).items():
        if not isinstance(m,dict): continue
        rel=m.get("path"); sha=m.get("blob_sha")
        if rel and sha and str(rel).startswith("nasdaq-xray/"):
            fp=REPO/rel
            if fp.exists(): assert blob(fp)==sha,(k,blob(fp),sha)
    print(json.dumps({"XRAY_POINTER_TRANSITION_GUARD":"PASS","revision":rev,"state_hash":p["state_hash"],"asof_et":s["asof_et"],"status":s["status"]},sort_keys=True))
if __name__=="__main__": main()
