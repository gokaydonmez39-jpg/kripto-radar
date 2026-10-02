#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os
from datetime import datetime,timedelta
from pathlib import Path
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
STAGE1=Path(os.getenv("XRAY_EVENT_STAGE1",str(ROOT/"canonical_current_stage1.json")))
DEEP=Path(os.getenv("XRAY_EVENT_DEEP",str(ROOT/"canonical_current_deep_geometry.json")))
REGIME=Path(os.getenv("XRAY_EVENT_REGIME",str(ROOT/"canonical_current_regime.json")))
OUT=Path(os.getenv("XRAY_EVENT_REQUEST_OUT",str(ROOT/"canonical_current_event_request.json")))
TASK="6a825366222081918997094d76e6ae46"
POLICY=ROOT/"chatgpt_compiled_policy_v3.json"
POLICY_BLOB="2dda2b520cb49f2dab02a971cb8993f927970220"
POLICY_HASH="9a7fdf46c2bda80343c4ecf0aca5eeb853faee435f758139e3f3f2582050e5c6"
POLICY_VERSION="C4.12"

def blob_sha(p:Path)->str:
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def hash_lines(xs):
    return hashlib.sha256("\n".join(xs).encode()).hexdigest()

def sessions(asof):
    d=datetime.fromisoformat(asof).date()
    cal=mcal.get_calendar("NASDAQ")
    sched=cal.schedule(start_date=(d-timedelta(days=40)).isoformat(),end_date=(d+timedelta(days=25)).isoformat())
    ds=[x.date().isoformat() for x in sched.index]
    if asof not in ds: raise RuntimeError("ASOF_NOT_OFFICIAL_SESSION")
    i=ds.index(asof)
    past=ds[max(0,i-9):i+1]
    future=ds[i+1:i+9]
    if len(past)!=10 or len(future)!=8: raise RuntimeError("SESSION_WINDOW_INCOMPLETE")
    return past,future

def main():
    s=json.loads(STAGE1.read_text()); d=json.loads(DEEP.read_text()); r=json.loads(REGIME.read_text())
    pol=json.loads(POLICY.read_text())
    assert blob_sha(POLICY)==POLICY_BLOB
    assert pol.get("schema")=="XRAY_GITHUB_COMPILED_POLICY_V3" and pol.get("policy_hash")==POLICY_HASH
    pp=json.loads(pol["payload_json"])
    assert pp.get("version")==POLICY_VERSION and pp.get("execution")=="NONE" and pp.get("real_money")=="NO-GO"
    asof=s["asof_et"]
    assert s["task_id"]==d["task_id"]==r["task_id"]==TASK
    assert d["asof_et"]==r["asof_et"]==asof
    assert s["execution"]==d["execution"]==r["execution"]=="NONE"
    assert s["real_money"]==d["real_money"]==r["real_money"]=="NO-GO"
    assert int(s.get("unknown_count",0))==0
    assert int(r.get("breadth_missing_count",0))==0
    assert int(d.get("unknown_history_count",0))==0
    weekly=sorted(set(s.get("weekly_pass") or []))
    assert len(weekly)==int(s.get("weekly_pass_count",len(weekly)))
    assert int(d.get("input_weekly_pass_count",-1))==len(weekly)
    past,future=sessions(asof)
    finalists=sorted(set(
        (d.get("a_geometry") or [])+
        (d.get("b_breakout") or [])+
        (d.get("b_armed") or [])+
        (d.get("d_geometry_rs") or [])
    ))
    assert set(finalists)<=set(weekly)
    obj={
      "schema":"XRAY_EVENT_EPOCH_REQUEST_V1","status":"READY","task_id":TASK,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "compiled_policy_path":"nasdaq-xray/chatgpt_compiled_policy_v3.json",
      "compiled_policy_blob_sha":POLICY_BLOB,
      "compiled_policy_hash":POLICY_HASH,
      "compiled_policy_version":POLICY_VERSION,
      "weekly_scope":weekly,"weekly_scope_count":len(weekly),"weekly_scope_hash":hash_lines(weekly),
      "geometry_scope":finalists,"geometry_scope_count":len(finalists),"geometry_scope_hash":hash_lines(finalists),
      "past_family_c_sessions":past,"future_horizon_sessions":future,
      "market_close_semantics":"ASOF_COMPLETED_RTH;EVENT_AFTER_ASOF_CLOSE_BEFORE_NEXT_RTH_COUNTS_INSIDE_HORIZON",
      "source_stage1_path":"nasdaq-xray/canonical_current_stage1.json","source_stage1_blob_sha":blob_sha(STAGE1),
      "source_regime_path":"nasdaq-xray/canonical_current_regime.json","source_regime_blob_sha":blob_sha(REGIME),
      "source_deep_geometry_path":"nasdaq-xray/canonical_current_deep_geometry.json","source_deep_geometry_blob_sha":blob_sha(DEEP),
      "required_discovery":{"provider":"BIGDATA_CORPORATE_CALENDAR","exchanges":["XNAS","XNGS","XNMS","XNCM","XNGM"],"category":"earnings-call"},
      "official_confirmation":"ISSUER_IR_OR_SEC_PRIMARY;DISCOVERY_ONLY_NEVER_BLOCKS_OR_CLEARS_BY_ITSELF"
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"asof":asof,"weekly_scope_count":len(weekly),"geometry_scope_count":len(finalists),"past":past,"future":future},sort_keys=True))

if __name__=="__main__": main()
