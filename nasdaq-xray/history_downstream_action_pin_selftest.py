#!/usr/bin/env python3
"""Static immutability checks for two research-only encrypted HISTORY sources."""
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
FILES=(
    ROOT/".github/workflows/xray-massive-grouped-history-resume.yml",
    ROOT/".github/workflows/xray-twelve-history-resume.yml"
)
PINS=(
    "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
    "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
)
def require(ok,why):
    if not ok: raise ValueError("XRAY_HISTORY_ACTION_PIN:"+why)
def scan(x):
    require(not bool(re.search(r"^\s*ref:\s*main\s*$",x,re.M)),"MOVING_MAIN")
    require("ref: "+chr(36)+"{{ github.sha }}" in x,"MISSING_INVOCATION_SHA")
    require('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"' in x,"NO_SOURCE_CHECK")
    require(not bool(re.search(r"uses:\s*actions/[a-z0-9-]+@v\d",x)),"FLOATING_ACTION")
    require(all(p in x for p in PINS),"MISSING_ACTION_PINS")
    require("cancel-in-progress: false" in x,"CHECKPOINT_CANCELLATION")
    require("XRAY_MASSIVE_NONDISPLAY_LICENSE_OK" in x
            if "Massive Grouped" in x else "XRAY_TWELVE_NONDISPLAY_LICENSE_OK" in x,
            "MISSING_NONDISPLAY_LICENSE")
    return True
def negative(why,x):
    try:scan(x)
    except ValueError:return
    raise AssertionError("XRAY_HISTORY_ACTION_PIN_NEGATIVE_BYPASS:"+why)
def main():
    g,t=[f.read_text() for f in FILES]
    require(scan(g) and scan(t),"VALID_WORKFLOWS")
    negative("FLOATING_CHECKOUT",g.replace(PINS[0],"actions/checkout@v4"))
    negative("FLOATING_SETUP",g.replace(PINS[1],"actions/setup-python@v5"))
    negative("FLOATING_UPLOAD",t.replace(PINS[2],"actions/upload-artifact@v4"))
    negative("MOVING_REF",t.replace("ref: "+chr(36)+"{{ github.sha }}","ref: main"))
    negative("SOURCE_CHECK_MISSING",g.replace('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',"true"))
    negative("CANCELLATION",g.replace("cancel-in-progress: false","cancel-in-progress: true"))
    negative("LICENSE_REMOVAL",t.replace("XRAY_TWELVE_NONDISPLAY_LICENSE_OK","XRAY_TWELVE_RIGHTS_UNKNOWN"))
    print("XRAY_HISTORY_ACTION_PINS=PASS_2_POSITIVE_7_NEGATIVE_PYTHON_O_SAFE_NO_VENDOR")

if __name__=="__main__":main()
