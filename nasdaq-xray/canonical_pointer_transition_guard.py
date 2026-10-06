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
    # Pointer durability binds immutable canonical research evidence, not
    # mutable operational witnesses (halt/G9/account runtime files can refresh
    # after the terminal was built without changing alpha or terminal history).
    immutable_terminal_keys={"master","price","history","legal","stage1_input","stage1",
      "regime","deep_geometry","event_request","events","family_c","deep","final","policy","full_state"}
    for k in immutable_terminal_keys:
        m=(t.get("evidence") or {}).get(k) or {}
        rel=m.get("path"); sha=m.get("blob_sha")
        assert rel and sha,(k,m)
        fp=REPO/rel
        assert fp.exists(),(k,rel)
        assert blob(fp)==sha,(k,blob(fp),sha)
    mc=(t.get("evidence") or {}).get("mc") or {}
    assert mc.get("path") and mc.get("blob_sha")
    assert blob(REPO/mc["path"])==mc["blob_sha"]
    # The recovered pointer itself must persist exact terminal/evidence SHAs.
    df=s.get("deep_final_evidence") or {}
    assert df.get("terminal_path")=="nasdaq-xray/canonical_current_terminal.json"
    assert df.get("terminal_blob_sha")==blob(tp),(df.get("terminal_blob_sha"),blob(tp))
    evidence_fields=("master_identity_evidence","price_dv30_evidence","mc_evidence",
      "history_evidence","legal_evidence","stage1_evidence","regime_breadth_evidence",
      "event_evidence","settlement_resolver_evidence")
    for name in evidence_fields:
        m=s.get(name) or {}
        rel=m.get("path"); sha=m.get("blob_sha")
        assert rel and sha,(name,m)
        fp=REPO/rel
        assert fp.exists(),(name,rel)
        assert blob(fp)==sha,(name,blob(fp),sha)
    for rel_key,sha_key in (("deep_path","deep_blob_sha"),("final_path","final_blob_sha")):
        rel=df.get(rel_key); sha=df.get(sha_key)
        assert rel and sha,(rel_key,df)
        assert blob(REPO/rel)==sha,(rel_key,blob(REPO/rel),sha)
    print(json.dumps({"XRAY_POINTER_TRANSITION_GUARD":"PASS","revision":rev,"state_hash":p["state_hash"],"asof_et":s["asof_et"],"status":s["status"]},sort_keys=True))
if __name__=="__main__": main()
