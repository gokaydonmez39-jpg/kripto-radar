#!/usr/bin/env python3
"""Isolated deterministic negative tests for history_phase.py source invariants.
No imports of Akshare, no API, no vendor OHLCV, no trading authority.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

HERE=Path(__file__).resolve().parent
SOURCE=HERE/"history_phase.py"
TASK="6a825366222081918997094d76e6ae46"

def require(ok,why):
    if not ok:raise RuntimeError("HISTORY_OPTIMIZED_GUARD_SELFTEST:"+why)

def module_for(*functions):
    doc=ast.parse(SOURCE.read_text(encoding="utf-8"))
    subset=[node for node in doc.body if isinstance(node,ast.FunctionDef) and node.name in functions]
    require({n.name for n in subset}==set(functions),"MISSING_FUNCTION")
    return compile(ast.fix_missing_locations(ast.Module(body=subset,type_ignores=[])),str(SOURCE),"exec")

def expect_guard(label, fn):
    try:fn()
    except AssertionError as e:
        require("XRAY_HISTORY_GATE:" in str(e),"UNEXPECTED_ERROR:"+label)
        return
    raise RuntimeError("HISTORY_OPTIMIZED_GUARD_BYPASS:"+label)

def run():
    tree=ast.parse(SOURCE.read_text(encoding="utf-8"))
    original=[node for node in ast.walk(tree) if isinstance(node,ast.Assert)]
    require(not original,"UNSAFE_OPTIMIZABLE_ASSERT_REMAINS")
    require(SOURCE.read_text().count("HISTORY_SOURCE_GUARD_L")==41,
            "EXACT_41_GUARDS_MISSING")
    with tempfile.TemporaryDirectory(prefix="xray_hist_guard_") as td:
        repo=Path(td);root=repo/"nasdaq-xray";root.mkdir()
        data=root/"test_current_mc_input.json"
        data.write_text('{"test":"source"}\n',encoding="utf-8")
        def sha(path):
            b=path.read_bytes()
            return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()
        rel=lambda p:p.relative_to(repo).as_posix()
        ns={"json":json,"os":os,"Path":Path,"ROOT":root,"INPUT":data,
            "TASK_ID":TASK,"HARD_DAILY":260,"HARD_WEEKLY":52,
            "blob_sha":sha,"relpath":rel,
            "mc_partition_semantic_equivalent":lambda x,y:True}
        exec(module_for("require","load_history_bridge","bridge_resolution"),ns)
        src={"policy_hash":"a"*64,"policy_version":"C4.17",
             "input_blob_sha":"b"*40,
             "input_path":"nasdaq-xray/canonical_current_price_dv30.json"}
        bridge=root/"canonical_history_evidence_bridge_20261009_v1.json"
        valid={"schema":"XRAY_HISTORY_EVIDENCE_BRIDGE_V1",
             "status":"READY","task_id":TASK,"asof_et":"2026-10-09",
             "execution":"NONE","real_money":"NO-GO",
             "unknown_never_pass":True,"no_threshold_change":True,
             "no_synthetic_bars":True,"thresholds":{"daily":260,"weekly_completed":52},
             "source_mc_path":rel(data),"source_mc_blob_sha":sha(data),
             "source_mc_policy_hash":src["policy_hash"],
             "source_mc_policy_version":src["policy_version"],
             "entries":{"TEST":{"outcome":"UNKNOWN_HISTORY"}},
             "scope_symbols":["TEST"],"counts":{"TOTAL":1}}
        def load(v,source=src):
            bridge.write_text(json.dumps(v,sort_keys=True)+"\n",encoding="utf-8")
            return ns["load_history_bridge"](source,"2026-10-09")
        require(set(load(valid))=={"TEST"},"EXACT_BINDING_POSITIVE")
        negatives={
            "SCHEMA":("schema","UNKNOWN"),
            "STATUS":("status","READY_OLD"),
            "TASK":("task_id","other"),
            "ASOF":("asof_et","2026-10-08"),
            "EXECUTION":("execution","TRADE"),
            "REAL_MONEY":("real_money","GO"),
            "UNKNOWN":("unknown_never_pass",False),
            "THRESHOLD_CHANGE":("no_threshold_change",False),
            "SYNTHETIC":("no_synthetic_bars",False),
            "SOURCE_MC_BLOB":("source_mc_blob_sha","f"*40),
            "SOURCE_MC_PATH":("source_mc_path","nasdaq-xray/missing.json"),
            "POLICY_HASH":("source_mc_policy_hash","z"*64),
            "POLICY_VERSION":("source_mc_policy_version","C4.0"),
            "SCOPE":("scope_symbols",["OTHER"]),
            "TOTAL":("counts",{"TOTAL":2}),
        }
        for label,(field,value) in negatives.items():
            wrong=copy.deepcopy(valid);wrong[field]=value
            expect_guard(label,lambda item=wrong:load(item))
        for name,key,value in (("DAILY","daily",259),("WEEKLY","weekly_completed",51)):
            wrong=copy.deepcopy(valid);wrong["thresholds"][key]=value
            expect_guard(name,lambda item=wrong:load(item))
        mode_base={"mode":"RALLIES_CROSS_SOURCE_EXACT_HISTORY_PASS_V1",
                   "outcome":"PASS_HISTORY","source":"RALLIES_CONNECTOR_DAILY",
                   "proof":"RALLIES_EXACT_ASOF_PLUS_LAGGING_CROSS_SOURCE_OVERLAP",
                   "no_synthetic_bars":True,"can_create_pass":True}
        for name,key,val in (("RALLIES_SOURCE","source","YAHOO"),
                             ("RALLIES_PROOF","proof","UNKNOWN"),
                             ("RALLIES_SYNTHETIC","no_synthetic_bars",False),
                             ("RALLIES_NO_PASS","can_create_pass",False)):
            wrong=dict(mode_base);wrong[key]=val;ns["HISTORY_BRIDGE"]={"TEST":wrong}
            expect_guard(name,lambda:ns["bridge_resolution"]("TEST","2026-10-09"))
        require(ns["bridge_resolution"]("UNREGISTERED","2026-10-09") is None,
                "UNREGISTERED_SYMBOL_FAIL_CLOSED_POSITIVE")
        # Latest production entrypoint guards must also be explicit and
        # non-optimizable, not merely the bridge loader.
        text=SOURCE.read_text()
        for evidence in ("HISTORY_SOURCE_GUARD_L774","HISTORY_SOURCE_GUARD_L776",
                         "HISTORY_SOURCE_GUARD_L785"):
            require(evidence in text,"MAIN_INPUT_GUARD_MISSING:"+evidence)
    print("XRAY_HISTORY_OPTIMIZED_INVARIANTS=PASS_2_POSITIVE_21_NEGATIVE_41_GUARDS_NO_PROVIDER")

if __name__=="__main__":run()
