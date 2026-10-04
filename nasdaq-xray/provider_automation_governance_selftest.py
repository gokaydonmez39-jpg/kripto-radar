#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
j=json.loads((ROOT/"provider_automation_governance.json").read_text())
assert j["schema"]=="XRAY_PROVIDER_AUTOMATION_GOVERNANCE_V1"
assert j["execution"]=="NONE" and j["real_money"]=="NO-GO"
assert j["unknown_never_pass"] is True and j["no_paid_fallback"] is True
a=j["providers"]["ALPHASTOCKS"]
assert a["unattended_automation_allowed"] is False
assert a["cutover"] is False
assert "UNKNOWN" in a["production_effect"]
assert j["providers"]["ALPACA"]["live_sip_g9_allowed"] is False
assert j["providers"]["BIGDATA"]["paid_top_up_allowed"] is False
assert j["providers"]["LONGBRIDGE"]["broad_market_data_core_allowed"] is False
print("XRAY_PROVIDER_AUTOMATION_GOVERNANCE_SELFTEST=PASS")
