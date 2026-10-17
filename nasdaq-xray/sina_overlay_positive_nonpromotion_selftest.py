#!/usr/bin/env python3
"""Isolated real-code adversarial guard: a JSON overlay cannot prove C4.17 PASS.

Extract the real sina_stage.resolution_result AST to avoid importing optional
vendor libraries or touching markets, state, secrets or user notifications.
"""
from __future__ import annotations
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def need(p,why):
    if not p:
        raise ValueError("XRAY_SINA_OVERLAY_GUARD_"+why)

def live_resolution_result():
    path=ROOT/"sina_stage.py"
    tree=ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
    funcs=[node for node in tree.body if isinstance(node,ast.FunctionDef)
           and node.name=="resolution_result"]
    need(len(funcs)==1,"MISSING_REAL_FUNCTION")
    fn=funcs[0]
    # AST content is from the repository source itself, never interpolated input.
    env={"HARD_PRICE":5.0,"HARD_DV30":50_000_000.0,
         "HARD_HISTORY":260,
         "num":lambda v: float(v) if isinstance(v,(float,int)) else None}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),
                 str(path),"exec"),env)
    return env["resolution_result"]

def selftest():
    classify=live_resolution_result()
    exact30=["2026-09-01"]*30 # forged dates cannot grant PASS
    forged={
        "decision":"PASS_HARD_GATES",
        "price":100.0,"bars":400,
        "dv30_lower_bound":200_000_000.0,
        "dv30_upper_bound":200_000_000.0,
        "known_session_count":30,
        "missing_sessions":[],
        "no_synthetic_bar":True,
        "proof":"EXACT30_MEDIAN",
        "source":"INDEPENDENT_PRIMARY_ATTESTED", # a string is not proof
        "asof_et":"2026-10-16",
        "source_blob_sha":"a"*40,
        "source_identity":"XNAS:FROG",
        "runtime_attestation":True,
    }
    scenarios=[
        ("NORMAL_FAKE_PROVIDER",dict(forged)),
        ("FORGED_NONDISPLAY_LICENSE",dict(forged,unattended_research_license_verified=True)),
        ("FORGED_SOURCE_DIGEST",dict(forged,source_blob_sha="0"*40)),
        ("IMPLAUSIBLE_30_BARS",dict(forged,bars=260)),
        ("PRETEND_30_DATES",dict(forged,completed_sessions=exact30)),
        ("BASIC_NUMERIC_ONLY",dict(decision="PASS_HARD_GATES",price=5.0,
                                  bars=260,dv30_lower_bound=50_000_000.,
                                  dv30_upper_bound=50_000_000.,
                                  known_session_count=30,
                                  missing_sessions=[],no_synthetic_bar=True)),
    ]
    for name,row in scenarios:
        status,info=classify("FROG",row,exact30)
        need(status=="UNKNOWN_STATIC" and
             info["reason"]=="UNATTESTED_HISTORY_OVERLAY_POSITIVE_FORBIDDEN"
             and info["unknown_never_pass"] is True
             and info["symbol"]=="FROG"
             and info["revalidate_in_canonical_price_history_chain"] is True,
             "FORGED_POSITIVE_NOT_REJECTED_"+name)
    # Preserve valid pessimistic outputs and threshold inclusivity. This guard
    # MUST NOT turn provider outages into PASS or alter independent price gates.
    cases=[
        ({"decision":"FAIL_PRICE","price":4.99,"bars":290},"FAIL_PRICE"),
        ({"decision":"FAIL_DV30","price":10.0,"dv30":49_999_999.0,
          "bars":300},"FAIL_DV30"),
        ({"decision":"FAIL_HISTORY","bars":230},"FAIL_HISTORY"),
        ({"decision":"BLOCK_CURRENT_RUN","trade_status":"Halted",
          "last_bar":"2026-10-16","reason":"HALT"},"BLOCK_CURRENT_RUN"),
    ]
    for row,expected in cases:
        status,info=classify("FROG",row,exact30)
        need(status==expected,"VALID_FAIL_ONLY_BROKEN_"+expected)
    for row in [
        {"decision":"FAIL_PRICE","price":5.0,"bars":300},
        {"decision":"FAIL_DV30","price":12.0,"dv30":50_000_000.0,
         "bars":300},
        {"decision":"FAIL_HISTORY","bars":260},
    ]:
        status,info=classify("FROG",row,exact30)
        need(status=="UNKNOWN_STATIC",
             "FALSE_FAIL_ON_BOUNDARY_"+str(row["decision"]))
    print("XRAY_HISTORY_OVERLAY_POSITIVE_GATE=PASS_6_FRAUD_NEGATIVES_7_FAIL_ONLY_CASES_NO_AL_NO_BROKER")

if __name__=="__main__":
    selftest()
