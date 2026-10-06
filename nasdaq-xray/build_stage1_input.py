#!/usr/bin/env python3
from __future__ import annotations
import json,os,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MC=Path(os.getenv("XRAY_POST_MC",str(ROOT/"canonical_mc_current.json")))
HISTORY=Path(os.getenv("XRAY_POST_HISTORY",str(ROOT/"canonical_current_history.json")))
LEGAL=Path(os.getenv("XRAY_POST_LEGAL",str(ROOT/"canonical_current_legal.json")))
OUT=Path(os.getenv("XRAY_STAGE1_INPUT_OUT",str(ROOT/"canonical_current_stage1_input.json")))
TASK="6a825366222081918997094d76e6ae46"

def blob_sha(p:Path):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def relpath(p:Path):
    try:return str(p.relative_to(ROOT.parent)).replace("\\","/")
    except Exception:return str(p)

def main():
    mc=json.loads(MC.read_text()); h=json.loads(HISTORY.read_text()); lg=json.loads(LEGAL.read_text())
    asof=mc["asof_et"]
    assert mc["task_id"]==h["task_id"]==lg["task_id"]==TASK
    assert h["asof_et"]==lg["asof_et"]==asof
    assert mc["execution"]==h["execution"]==lg["execution"]=="NONE"
    assert mc["real_money"]==h["real_money"]==lg["real_money"]=="NO-GO"
    assert int(h.get("unknown_count",0))==0 and int((lg.get("counts") or {}).get("UNKNOWN_LEGAL",0))==0
    primary=set(mc.get("primary_pass_symbols") or [])
    watch=set(mc.get("fallback_watch_symbols") or [])
    hp=set(h.get("pass_symbols") or [])
    lp=set(lg.get("pass_symbols") or [])
    eligible=primary|watch
    assert hp<=eligible and lp<=hp
    syms=sorted(lp)
    inherited_caps=lg.get("state_caps") or h.get("state_caps") or mc.get("state_caps") or {}
    inherited_r92=set(lg.get("r92_ineligible") or h.get("r92_ineligible") or mc.get("r92_ineligible") or [])
    obj={
      "schema":"XRAY_CANONICAL_STAGE1_INPUT_V2","task_id":TASK,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "source_mc_path":relpath(MC),"source_mc_blob_sha":blob_sha(MC),
      "source_history_path":relpath(HISTORY),"source_history_blob_sha":blob_sha(HISTORY),
      "source_legal_path":relpath(LEGAL),"source_legal_blob_sha":blob_sha(LEGAL),
      "source_mc_policy_hash":mc.get("policy_hash"),"source_mc_policy_version":mc.get("policy_version"),
      "source_history_pass_hash":h.get("pass_hash"),"source_legal_pass_hash":lg.get("pass_hash"),
      "current_core_mc_pass":syms,"current_core_symbols":syms,"current_core_count":len(syms),
      "state_caps":{s:("WATCH" if s in watch else inherited_caps.get(s,"NORMAL")) for s in syms},
      "r92_ineligible":sorted((inherited_r92|watch)&set(syms)),
      "included_fallback_watch_symbols":sorted(set(syms)&watch),
      "included_fallback_watch_count":len(set(syms)&watch),
      "excluded_fallback_watch_symbols":sorted(watch-set(syms)),
      "excluded_fallback_watch_count":len(watch-set(syms))
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"asof":asof,"current_core_count":len(syms),"fallback_watch_excluded":len(watch)},sort_keys=True))
if __name__=="__main__":main()
