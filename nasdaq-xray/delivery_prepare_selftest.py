#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,shutil,subprocess,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
SRC=HERE/"delivery_prepare.py"
POLICY="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
TASK="6a825366222081918997094d76e6ae46"

def bsha(p):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def candidate(key,sym,setup,dv30):
    return {
      "schema":"XRAY_RESEARCH_CANDIDATE_R92_V1","delivery_key":key,
      "asof_et":"2099-01-02","symbol":sym,"setup":setup,
      "entry_low":100.0,"entry_high":101.0,"chase_limit":102.0,"stop":96.0,
      "r1":116.0,"rr_basic":2.2,"rr_severe":1.7,"regime":"MIXED",
      "event_status":"CLEAN_TEST","mc_class":"MC_PASS_PRIMARY","mc_source":"BIGDATA_TEST",
      "dv30":dv30,"liquidity":"DV30_POLICY_PASS","pass_reason":"SELFTEST_ONLY",
      "g9_status":"G9_BLOCKED_FREE_AUTOMATION_PATH",
      "account_status":"ACCOUNT_BOOTSTRAP_READY_CREDENTIALS_REQUIRED",
      "registered_at_utc":"2099-01-03T00:00:00Z",
      "execution":"NONE","real_money":"NO-GO",
    }

def write_guard(p,active=None,status="PASS",suspended=None,security_status=None):
    active=active or []; suspended=suspended or []
    security_status=security_status or status
    veto=sorted(set(active)|set(suspended))
    g={
      "schema":"XRAY_OFFICIAL_SOURCE_GUARD_V1",
      "generated_at_utc":datetime.now(timezone.utc).isoformat(),
      "sources":{
        "trade_halts":{"status":status,"active_halt_symbols":active},
        "security_status":{"status":security_status,"suspension_symbols":suspended},
      },
      "candidate_safety":{"veto_symbols":veto},
    }
    (p/"canonical_official_source_guard.json").write_text(json.dumps(g))

def write_chain(p,unrelated_unknown=True,exact=True):
    symbols=["AAA","BBB"]+(["ZZZ"] if unrelated_unknown else [])
    price={
      "schema":"XRAY_CANONICAL_PRICE_DV30_V1","asof_et":"2099-01-02",
      "unknown_count":0,"pass_count":len(symbols),"pass_hash":"PASSHASH",
      "pass_symbols":symbols,
      "results":{
        "AAA":{"status":"PASS_PRICE_DV30","info":{"dv30":100000000.0}},
        "BBB":{"status":"PASS_PRICE_DV30","info":{"dv30":120000000.0}},
        **({"ZZZ":{"status":"PASS_PRICE_DV30","info":{"dv30":80000000.0}}} if unrelated_unknown else {}),
      }
    }
    (p/"canonical_current_price_dv30.json").write_text(json.dumps(price))
    mc_results={
      "AAA":{"status":"MC_PASS_PRIMARY","mode":"BIGDATA_EXACT"},
      "BBB":{"status":"MC_PASS_PRIMARY","mode":"BIGDATA_EXACT"},
    }
    if unrelated_unknown:
      mc_results["ZZZ"]={"status":"MC_UNKNOWN","mode":"UNRELATED_PROVIDER_GAP"}
    mc={
      "schema":"XRAY_MC_EPOCH_RESULT_V1","status":"COMMITTED","asof_et":"2099-01-02",
      "policy_hash":POLICY,"policy_version":"C4.17",
      "input_path":"nasdaq-xray/canonical_current_price_dv30.json",
      "input_pass_hash":"PASSHASH","input_count":len(symbols),
      "counts":{"MC_PASS_PRIMARY":2,"MC_UNKNOWN":1 if unrelated_unknown else 0,"TOTAL":len(symbols)},
      "primary_pass_symbols":["AAA","BBB"],
      "unknown_symbols":["ZZZ"] if unrelated_unknown else [],
      "results":mc_results,
    }
    mp=p/"canonical_mc_bridge_test.json"; mp.write_text(json.dumps(mc))
    history={
      "asof_et":"2099-01-02","source_mc_artifact":"canonical_mc_bridge_test.json",
      "source_mc_blob_sha":bsha(mp),
      "source_mc_policy_hash":POLICY if exact else "STALE_POLICY",
      "source_mc_policy_version":"C4.17",
    }
    (p/"canonical_current_history.json").write_text(json.dumps(history))
    return price,mc,mp

def write_terminal(p,keys=("AAA|B","BBB|C"),candidate_local=True):
    final_results={}
    for key in keys:
      sym,fam=key.split("|")
      final_results[key]={
        "result":"PRE_G9_TECH_PASS","pre_g9_tech_pass":True,
        "technical_hard_pass":True,"r92_eligible":True,"state_cap":"NORMAL",
        "candidate_legal_review_status":"PASS","family":fam,"event_status":"CLEAN_TEST",
      }
    final={
      "schema":"XRAY_FINAL_TECH_SHADOW_V1","asof_et":"2099-01-02",
      "source_compiled_policy_hash":POLICY,"source_compiled_policy_version":"C4.17",
      "policy_semantics_exact":True,"lifecycle_semantics_exact":True,
      "results":final_results,
    }
    fp=p/"canonical_current_final_tech.json"; fp.write_text(json.dumps(final))
    price=p/"canonical_current_price_dv30.json"; mc=p/"canonical_mc_bridge_test.json"
    checks={
      "candidate_local_research_pass":candidate_local,
      "alpha_semantic_conformance_exact":True,"alpha_source_binding_exact":True,
      "lifecycle_frozen_semantics_exact":True,"candidate_legal_guard_exact_binding":True,
      "all_finalists_detailed_legal_review_exact":True,"mc_exact_price_pass_set":True,
      "semantic_provenance_chain_exact":True,
    }
    terminal={
      "schema":"XRAY_CANONICAL_CURRENT_TERMINAL_V1","task_id":TASK,"asof_et":"2099-01-02",
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "candidate_local_research_pass":candidate_local,
      "r92_candidates":list(keys) if candidate_local else [],
      "sets":{"pre_g9_tech_pass":list(keys) if candidate_local else []},
      "checks":checks,
      "candidate_delivery_safety":{"status":"PASS","vetoed_candidates":[]},
      "evidence":{
        "price":{"path":"nasdaq-xray/canonical_current_price_dv30.json","blob_sha":bsha(price)},
        "mc":{"path":"nasdaq-xray/canonical_mc_bridge_test.json","blob_sha":bsha(mc)},
        "final":{"path":"nasdaq-xray/canonical_current_final_tech.json","blob_sha":bsha(fp)},
      },
    }
    tp=p/"canonical_current_terminal.json"; tp.write_text(json.dumps(terminal))
    return tp,fp

def pointer(p,r92,keys):
    tp=p/"canonical_current_terminal.json"; fp=p/"canonical_current_final_tech.json"
    return {
      "schema":"XRAY_GITHUB_DURABLE_STATE_V3","authority":"GITHUB_CURRENT_POINTER",
      "execution":"NONE","real_money":"NO-GO",
      "state_json":{
        "task_id":TASK,"asof_et":"2099-01-02","r92":r92,"delivery_keys":keys,
        "deep_final_evidence":{
          "terminal_path":"nasdaq-xray/canonical_current_terminal.json",
          "terminal_blob_sha":bsha(tp),
          "final_path":"nasdaq-xray/canonical_current_final_tech.json",
          "final_blob_sha":bsha(fp),
        },
      }
    }

def run_case(p,expect_ok=True):
    cp=subprocess.run([sys.executable,str(p/"delivery_prepare.py")],cwd=p,text=True,capture_output=True)
    if expect_ok and cp.returncode!=0:
      raise AssertionError(cp.stdout+"\n"+cp.stderr)
    if not expect_ok and cp.returncode==0:
      raise AssertionError("negative case unexpectedly passed: "+cp.stdout)
    return cp

with tempfile.TemporaryDirectory() as td:
    p=Path(td)/"nasdaq-xray"; p.mkdir(); shutil.copy2(SRC,p/"delivery_prepare.py")
    a=candidate("DELIVERY|RESEARCH_AL_ADAYI|2099-01-02|AAA|B|a","AAA","B",100000000.0)
    b=candidate("DELIVERY|RESEARCH_AL_ADAYI|2099-01-02|BBB|C|b","BBB","C",120000000.0)

    # Positive: unrelated global MC_UNKNOWN must NOT suppress exact local candidates.
    write_chain(p,unrelated_unknown=True,exact=True)
    write_terminal(p)
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer(p,[a,b],[a["delivery_key"],b["delivery_key"]])))
    write_guard(p)
    cp=run_case(p,True)
    assert "XRAY_DELIVERY_READY=PASS" in cp.stdout
    assert "XRAY_DELIVERY_COUNT=2" in cp.stdout
    batch=json.load(open(p/".delivery_work/batch.json"))
    assert {x["symbol"] for x in batch["candidates"]}=={"AAA","BBB"}

    # Negative: malformed/unregistered R92 must never silently become
    # NO_REGISTERED_CANDIDATE. Only a genuinely empty R92 is a clean no-op.
    malformed=dict(a); malformed["schema"]="WRONG_R92_SCHEMA"
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(
        pointer(p,[malformed],[malformed["delivery_key"]])))
    cp=run_case(p,False)
    assert "DELIVERY_R92_REGISTRATION_SCHEMA_INVALID" in (cp.stdout+cp.stderr)
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(
        pointer(p,[a],[])))
    cp=run_case(p,False)
    assert "DELIVERY_R92_UNREGISTERED_KEY" in (cp.stdout+cp.stderr)
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(
        pointer(p,[],[])))
    cp=run_case(p,True)
    assert "XRAY_DELIVERY_NOOP=NO_REGISTERED_RESEARCH_CANDIDATE" in cp.stdout
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(
        pointer(p,[a,b],[a["delivery_key"],b["delivery_key"]])))

    # Positive: C4.17 A-family has its OWN RR floors (1.5 / 1.1);
    # a delivery-safety repair must never invent stricter alpha thresholds.
    a_family=dict(a); a_family["setup"]="A"
    a_family["rr_basic"]=1.5; a_family["rr_severe"]=1.1
    write_terminal(p,keys=("AAA|A",))
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(
        pointer(p,[a_family],[a_family["delivery_key"]])))
    cp=run_case(p,True)
    assert "XRAY_DELIVERY_READY=PASS" in cp.stdout
    write_terminal(p)
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(
        pointer(p,[a,b],[a["delivery_key"],b["delivery_key"]])))

    # Negative: stale policy/source chain remains fail-closed.
    write_chain(p,unrelated_unknown=True,exact=False)
    if (p/".delivery_work").exists(): shutil.rmtree(p/".delivery_work")
    cp=run_case(p,True)
    assert "XRAY_DELIVERY_NOOP=CURRENT_DV30_MC_CHAIN_INCOMPLETE" in cp.stdout
    write_chain(p,unrelated_unknown=True,exact=True)
    write_terminal(p)
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer(p,[a,b],[a["delivery_key"],b["delivery_key"]])))

    # Negative: candidate not in exact terminal R92/PRE_G9 scope.
    c=candidate("DELIVERY|RESEARCH_AL_ADAYI|2099-01-02|CCC|D|c","CCC","D",90000000.0)
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer(p,[c],[c["delivery_key"]])))
    cp=run_case(p,False)
    assert "DELIVERY_R92_NOT_TERMINAL_CANDIDATE:CCC|D" in (cp.stdout+cp.stderr)

    # Negative: fallback-WATCH can never be R92 even if a record claims otherwise.
    bad=dict(a); bad["mc_class"]="MC_PASS_FALLBACK_WATCH"
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer(p,[bad],[bad["delivery_key"]])))
    cp=run_case(p,False)
    assert "DELIVERY_R92_MC_NOT_PRIMARY:AAA|B" in (cp.stdout+cp.stderr)

    # Negative: DV30 record must bind to current exact price evidence.
    bad=dict(a); bad["dv30"]=999.0
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer(p,[bad],[bad["delivery_key"]])))
    cp=run_case(p,False)
    assert "DELIVERY_R92_DV30_BINDING_MISMATCH:AAA|B" in (cp.stdout+cp.stderr)

    # Negative: do not publish NaN/bool prices, inverted stop/chase, over-8%
    # stop risk, or RR below the frozen C4.17 B-family floors.
    for field,value,reason in [
        ("entry_low",float("nan"),"DELIVERY_R92_NONFINITE_GEOMETRY:entry_low"),
        ("stop",True,"DELIVERY_R92_NONFINITE_GEOMETRY:stop"),
        ("chase_limit",100.5,"DELIVERY_R92_LONG_GEOMETRY_INVALID"),
        ("r1",100.5,"DELIVERY_R92_LONG_GEOMETRY_INVALID"),
        ("stop",90.0,"DELIVERY_R92_RISK_PERCENT_EXCEEDS_8"),
        ("rr_basic",1.99,"DELIVERY_R92_RR_POLICY_FLOOR_FAILED"),
        ("rr_severe",1.49,"DELIVERY_R92_RR_POLICY_FLOOR_FAILED"),
        ("rr_basic",3.1,"DELIVERY_R92_RR_GEOMETRY_UPPER_BOUND"),
        ("rr_severe",3.1,"DELIVERY_R92_RR_GEOMETRY_UPPER_BOUND"),
        ("rr_severe",2.3,"DELIVERY_R92_RR_SEVERE_EXCEEDS_BASIC"),
    ]:
        bad=dict(a); bad[field]=value
        (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(
            pointer(p,[bad],[bad["delivery_key"]])))
        cp=run_case(p,False)
        assert reason in (cp.stdout+cp.stderr),(field,cp.stdout,cp.stderr)

    # Negative: pointer must bind exact current terminal blob.
    goodptr=pointer(p,[a],[a["delivery_key"]])
    goodptr["state_json"]["deep_final_evidence"]["terminal_blob_sha"]="0"*40
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(goodptr))
    cp=run_case(p,False)
    assert "DELIVERY_POINTER_TERMINAL_BINDING_MISMATCH" in (cp.stdout+cp.stderr)

    # Negative: terminal candidate-local gate false means no delivery.
    write_terminal(p,candidate_local=False)
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer(p,[a],[a["delivery_key"]])))
    cp=run_case(p,False)
    assert "DELIVERY_TERMINAL_CANDIDATE_LOCAL_NOT_PASS" in (cp.stdout+cp.stderr)

    # Restore exact local terminal for official safety tests.
    write_terminal(p)
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer(p,[a],[a["delivery_key"]])))
    write_guard(p,active=["AAA"])
    cp=run_case(p,False)
    assert "DELIVERY_OFFICIAL_SAFETY_VETO:AAA" in (cp.stdout+cp.stderr)

    write_guard(p,status="UNKNOWN")
    cp=run_case(p,False)
    assert "DELIVERY_OFFICIAL_HALT_FEED_UNKNOWN" in (cp.stdout+cp.stderr)

    write_guard(p,security_status="UNKNOWN")
    cp=run_case(p,False)
    assert "DELIVERY_OFFICIAL_SECURITY_STATUS_UNKNOWN" in (cp.stdout+cp.stderr)

    # Negative max3 cap is enforced before candidate-local evaluation.
    write_guard(p)
    cap=[candidate(f"DELIVERY|RESEARCH_AL_ADAYI|2099-01-02|CAP{i}|B|{i}",f"CAP{i}","B",100000000.0+i) for i in range(4)]
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer(p,cap,[x["delivery_key"] for x in cap])))
    cp=run_case(p,False)
    assert "DELIVERY_R92_COUNT_EXCEEDS_MAX3" in (cp.stdout+cp.stderr)

    # Negative safety lock.
    bad=dict(a); bad["real_money"]="GO"
    (p/"chatgpt_canonical_state_v2.json").write_text(json.dumps(pointer(p,[bad],[bad["delivery_key"]])))
    cp=run_case(p,False)
    assert "DELIVERY_R92_SAFETY_LOCK_FAIL" in (cp.stdout+cp.stderr)

print("XRAY_DELIVERY_PREPARE_SELFTEST=PASS_CANDIDATE_LOCAL_GLOBAL_UNKNOWN_INDEPENDENCE")
