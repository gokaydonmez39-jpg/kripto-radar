#!/usr/bin/env python3
"""Offline push/schedule/manual market-HTTP gate tests; no provider calls."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/xray-alpaca-delayed-sip-research.yml"
GATED = (
    "Research-only bounded exact30 five-symbol historical SIP runner probe",
    "Authorized one-call full RTH minute coverage probe (never DV30)",
    "Bounded delayed-SIP health readback",
    "Enforce zero price publication zero GO",
)
PUSH_DENY = "        if: ${{ github.event_name != 'push' }}"
HEALTH_DENY = "        if: ${{ always() && github.event_name != 'push' }}"

def verify(source: str) -> None:
    if "  workflow_dispatch:" not in source or "  schedule:" not in source:
        raise ValueError("SCHEDULE_OR_MANUAL_ROUTE_REMOVED")
    for label in GATED:
        mark = "      - name: " + label + "\n"
        if source.count(mark) != 1:
            raise ValueError("MISSING_OR_DUPLICATE_PROBE:" + label)
        segment = source.split(mark, 1)[1].split("        run: |", 1)[0]
        if PUSH_DENY not in segment:
            raise ValueError("CODE_PUSH_COULD_SPEND_MARKET_QUOTA:" + label)
    upload = source.split("      - name: Upload health only\n", 1)
    if len(upload) != 2 or HEALTH_DENY not in upload[1].split("        uses:",1)[0]:
        raise ValueError("PUSH_WITHOUT_HEALTH_ARTIFACT")
    # Deliberate one-shot research remains opt-in, never on ordinary pushes.
    for key in ("run540shadow","run540bound","run30mbound","run4bound",
                "runbasket2","runlatest1day","runroot260","run27shadow",
                "runHourPilot"):
        if "contains(github.event.head_commit.message, '["+key+"]')" not in source:
            raise ValueError("ONE_SHOT_NOT_EXPLICITLY_OPT_IN:"+key)

def selftest() -> None:
    source=WORKFLOW.read_text()
    verify(source)
    for label in GATED:
        mark = "      - name: " + label + "\n"
        broken = source.replace(mark+PUSH_DENY+"\n",mark,1)
        if broken == source:
            raise RuntimeError("NEGATIVE_NOT_TRIGGERABLE:"+label)
        try: verify(broken)
        except ValueError: pass
        else: raise RuntimeError("INCIDENTAL_PUSH_FALSE_ACCEPT:"+label)
    try: verify(source.replace(HEALTH_DENY,"        if: always()",1))
    except ValueError: pass
    else: raise RuntimeError("UNBOUND_HEALTH_UPLOAD_ACCEPTED")
    print("XRAY_ALPACA_CODE_PUSH_ZERO_VENDOR_HTTP=PASS_5_NEGATIVES_SCHEDULE_MANUAL_PRESERVED")

if __name__=="__main__":
    selftest()
