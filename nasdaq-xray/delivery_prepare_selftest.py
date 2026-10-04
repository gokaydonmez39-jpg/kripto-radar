#!/usr/bin/env python3
from __future__ import annotations
import json, shutil, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
SRC=HERE/"delivery_prepare.py"

def candidate(key,sym,setup):
    return {
        "schema":"XRAY_RESEARCH_CANDIDATE_R92_V1",
        "delivery_key":key,"asof_et":"2099-01-02","symbol":sym,"setup":setup,
        "entry_low":100.0,"entry_high":101.0,"chase_limit":102.0,"stop":96.0,
        "r1":111.0,"rr_basic":2.2,"rr_severe":1.7,"regime":"TEST",
        "event_status":"CLEAN_TEST","mc_class":"MC_PASS_PRIMARY","mc_source":"SELFTEST",
        "dv20":100000000,"liquidity":"DV20_POLICY_PASS","pass_reason":"SELFTEST_ONLY",
        "g9_status":"BLOCKED_TEST","account_status":"UNKNOWN_TEST",
        "registered_at_utc":"2099-01-03T00:00:00Z",
        "execution":"NONE","real_money":"NO-GO",
    }

def pointer(r92,keys):
    return {
        "schema":"XRAY_GITHUB_DURABLE_STATE_V3","authority":"GITHUB_CURRENT_POINTER",
        "execution":"NONE","real_money":"NO-GO",
        "state_json":{
            "task_id":"6a825366222081918997094d76e6ae46",
            "r92":r92,"delivery_keys":keys,
        }
    }

def write_guard(p,active=None,status="PASS",suspended=None,security_status=None):
    active=active or []
    suspended=suspended or []
    security_status=security_status or status
    veto=sorted(set(active)|set(suspended))
    g={
        "schema":"XRAY_OFFICIAL_SOURCE_GUARD_V1",
        "status":"PASS" if status=="PASS" and security_status=="PASS" else "DEGRADED",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "sources":{
          "trade_halts":{"status":status,"active_halt_symbols":active},
          "security_status":{"status":security_status,"suspension_symbols":suspended},
        },
        "candidate_safety":{"veto_symbols":veto},
    }
    (p/"canonical_official_source_guard.json").write_text(json.dumps(g))

def run_case(p,expect_ok):
    cp=subprocess.run([sys.executable,str(p/"delivery_prepare.py")],cwd=p,text=True,capture_output=True)
    if expect_ok and cp.returncode!=0:
        raise AssertionError(cp.stdout+"\n"+cp.stderr)
    if not expect_ok and cp.returncode==0:
        raise AssertionError("negative safety case unexpectedly passed")
    return cp

with tempfile.TemporaryDirectory() as td:
    p=Path(td)
    shutil.copy2(SRC,p/"delivery_prepare.py")
    a=candidate("DELIVERY|RESEARCH_AL_ADAYI|2099-01-02|AAA|B|abc123","AAA","B")
    b=candidate("DELIVERY|RESEARCH_AL_ADAYI|2099-01-02|BBB|C|def456","BBB","C")
    # Research delivery MUST remain independent from TRUE-FULL-GO final gates.
    # Prove a fully registered technical candidate is still deliverable while
    # strict G9 and account are both blocked.
    b["g9_status"]="G9_BLOCKED_FREE_AUTOMATION_PATH"
    b["account_status"]="ACCOUNT_BLOCKED_SCOPE_NOT_GRANTED_OR_ACCOUNT_UNSUPPORTED"
    unregistered=candidate("DELIVERY|RESEARCH_AL_ADAYI|2099-01-02|CCC|D|zzz999","CCC","D")
    ptr=pointer([a,b,unregistered],[a["delivery_key"],b["delivery_key"]])
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(ptr))
    write_guard(p)
    cp=run_case(p,True)
    assert "XRAY_DELIVERY_READY=PASS" in cp.stdout
    assert "XRAY_DELIVERY_COUNT=2" in cp.stdout
    batch=json.load(open(p/".delivery_work/batch.json"))
    assert len(batch["candidates"])==2
    assert {x["symbol"] for x in batch["candidates"]}=={"AAA","BBB"}
    body_text="\n".join(p.read_text() for p in (p/".delivery_work").glob("*.md"))
    assert "G9_BLOCKED_FREE_AUTOMATION_PATH" in body_text
    assert "ACCOUNT_BLOCKED_SCOPE_NOT_GRANTED_OR_ACCOUNT_UNSUPPORTED" in body_text
    for x in batch["candidates"]:
        body=(p.parent/x["body_file"]) if not str(x["body_file"]).startswith(".") else p/x["body_file"]
        # production paths are repository-root relative; in selftest resolve basename safely.
        matches=list((p/".delivery_work").glob("*"+x["symbol"]+"*"))
        if not matches:
            matches=list((p/".delivery_work").glob("*.md"))
        assert matches
    # Negative halt-veto test: a registered candidate on the current official
    # active-halt set must never be delivered.
    halted=candidate("DELIVERY|RESEARCH_AL_ADAYI|2099-01-02|HALT|B|halt001","HALT","B")
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer([halted],[halted["delivery_key"]])))
    write_guard(p,["HALT"])
    if (p/".delivery_work").exists(): shutil.rmtree(p/".delivery_work")
    cp_halt=run_case(p,False)
    assert "DELIVERY_OFFICIAL_SAFETY_VETO:HALT" in (cp_halt.stdout+cp_halt.stderr)

    # Negative unknown-halt-feed test.
    safe=candidate("DELIVERY|RESEARCH_AL_ADAYI|2099-01-02|SAFE|B|safe001","SAFE","B")
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer([safe],[safe["delivery_key"]])))
    write_guard(p,status="UNKNOWN")
    if (p/".delivery_work").exists(): shutil.rmtree(p/".delivery_work")
    cp_guard=run_case(p,False)
    assert "DELIVERY_OFFICIAL_HALT_FEED_UNKNOWN" in (cp_guard.stdout+cp_guard.stderr)

    # Negative official Security Status suspension veto.
    suspended=candidate("DELIVERY|RESEARCH_AL_ADAYI|2099-01-02|SUSP|B|susp001","SUSP","B")
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer([suspended],[suspended["delivery_key"]])))
    write_guard(p,suspended=["SUSP"])
    if (p/".delivery_work").exists(): shutil.rmtree(p/".delivery_work")
    cp_susp=run_case(p,False)
    assert "DELIVERY_OFFICIAL_SAFETY_VETO:SUSP" in (cp_susp.stdout+cp_susp.stderr)

    # Negative unknown Security Status feed: do not deliver when official
    # listing/suspension safety is unavailable.
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer([safe],[safe["delivery_key"]])))
    write_guard(p,security_status="UNKNOWN")
    if (p/".delivery_work").exists(): shutil.rmtree(p/".delivery_work")
    cp_sec=run_case(p,False)
    assert "DELIVERY_OFFICIAL_SECURITY_STATUS_UNKNOWN" in (cp_sec.stdout+cp_sec.stderr)

    # Negative max3 test: even fully registered candidates fail closed if
    # the canonical pointer violates the compiled delivery cap.
    cap=[
        candidate(f"DELIVERY|RESEARCH_AL_ADAYI|2099-01-02|CAP{i}|B|cap{i:03d}",f"CAP{i}","B")
        for i in range(1,5)
    ]
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer(cap,[x["delivery_key"] for x in cap])))
    write_guard(p)
    if (p/".delivery_work").exists(): shutil.rmtree(p/".delivery_work")
    cp_cap=run_case(p,False)
    assert "DELIVERY_R92_COUNT_EXCEEDS_MAX3" in (cp_cap.stdout+cp_cap.stderr)

    # Negative safety-lock test: invalid real-money state must fail closed.
    bad=candidate("DELIVERY|RESEARCH_AL_ADAYI|2099-01-02|BAD|B|bad001","BAD","B")
    bad["real_money"]="GO"
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer([bad],[bad["delivery_key"]])))
    write_guard(p)
    if (p/".delivery_work").exists(): shutil.rmtree(p/".delivery_work")
    run_case(p,False)

print("XRAY_DELIVERY_PREPARE_SELFTEST=PASS")
