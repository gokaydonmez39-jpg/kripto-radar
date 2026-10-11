#!/usr/bin/env python3
"""No-provider GitHub workflow SHA fence contract tests for Massive MC shadow."""
import re
from pathlib import Path
P=Path(__file__).resolve().parent.parent/".github/workflows/xray-massive-mc-resume-shadow.yml"
A="a"*40
B="b"*40

def require(ok,why):
    if not ok: raise ValueError("XRAY_MASSIVE_SOURCE_FENCE:"+why)

def exact(invoked,checkout):
    require(bool(re.fullmatch(r"[0-9a-f]{40}",invoked or "")),"BAD_INVOCATION_SHA")
    require(bool(re.fullmatch(r"[0-9a-f]{40}",checkout or "")),"BAD_CHECKOUT_SHA")
    require(checkout==invoked,"MIXED_SOURCE_EPOCH")
    return True

def negative(label,fn):
    try: fn()
    except ValueError:return
    raise RuntimeError("MASSIVE_WORKFLOW_SOURCE_NEGATIVE_BYPASS:"+label)

def main():
    s=P.read_text(encoding="utf-8")
    require("ref: "+chr(36)+"{{ github.sha }}" in s,"REF_NOT_INVOCATION_SHA")
    require(not re.search(r"^\s*ref:\s*main\s*$",s,re.M),"MOVING_REF")
    require(s.count('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"')>=2,
            "MISSING_POST_SETUP_SECOND_READBACK")
    require("XRAY_MASSIVE_MC_SOURCE_EPOCH=PASS_EXACT_INVOCATION" in s,
            "MISSING_SOURCE_EPOCH_RECEIPT")
    for pin in ("checkout@11d5960a326750d5838078e36cf38b85af677262",
                "setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
                "upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"):
        require(pin in s,"MOVING_ACTION:"+pin)
    require("cancel-in-progress: false" in s,"ENCRYPTED_CHECKPOINT_RACE")
    require("XRAY_MASSIVE_NONDISPLAY_LICENSE_OK" in s,
            "LICENSE_PRECONDITION_REMOVED")
    require("python nasdaq-xray/massive_mc_resume_shadow.py --selftest" in s,
            "PROVIDER_SELFTEST_MISSING")
    require(exact(A,A),"IDENTICAL_SHA_POSITIVE")
    require(exact(B,B),"DIFFERENT_VALID_SHA_POSITIVE")
    negative("HEAD_DRIFT",lambda:exact(A,B))
    negative("EMPTY_HEAD",lambda:exact(A,""))
    negative("INVALID_SHA",lambda:exact("xyz",A))
    negative("UPPERCASE",lambda:exact(A.upper(),A))
    print("XRAY_MASSIVE_WORKFLOW_SOURCE_EPOCH=PASS_2_POSITIVE_4_NEGATIVE_PYTHON_O_SAFE_NO_PROVIDER")

if __name__=="__main__":main()
