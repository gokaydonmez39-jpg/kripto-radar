#!/usr/bin/env python3
"""Prove scheduled historical SIP canary consumes the now-verified private key pair.

The existing Python canary expects legacy XRAY_ALPACA_API_* env names.
Only the workflow's secret REFERENCE changes; no secret values are logged.
"""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
WORKFLOW=ROOT/".github/workflows/xray-alpaca-delayed-sip-research.yml"
PY=ROOT/"nasdaq-xray/alpaca_delayed_sip_research_shadow.py"

def main():
    w=WORKFLOW.read_text()
    p=PY.read_text()
    assert 'os.getenv("XRAY_ALPACA_API_KEY_ID"' in p
    assert 'os.getenv("XRAY_ALPACA_API_SECRET_KEY"' in p
    assert 'XRAY_ALPACA_API_KEY_ID: ${{ secrets.XRAY_ALPACA_DATA_KEY_ID }}' in w,(
      "CANARY_MISSING_VERIFIED_ALPACA_KEY_ID_SECRET")
    assert 'XRAY_ALPACA_API_SECRET_KEY: ${{ secrets.XRAY_ALPACA_DATA_SECRET_KEY }}' in w,(
      "CANARY_MISSING_VERIFIED_ALPACA_SECRET_KEY")
    assert 'ref: main' not in w
    assert 'github.sha' in w and 'GITHUB_SHA' in w
    assert 'permissions:\n  contents: read' in w
    assert 'schedule:' in w and 'workflow_dispatch:' in w
    print("XRAY_SCHEDULED_DELAYED_SIP_PRIVATE_SECRET_ALIAS=PASS_SHA_BOUND_NO_GO")

if __name__=="__main__":
    main()
