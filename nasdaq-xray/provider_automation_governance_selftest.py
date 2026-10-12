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
rallies=j["providers"]["RALLIES"]
assert rallies["positive_price_dv30_promotion_allowed"] is False
assert rallies["passive_reader_positive_promotion_allowed"] is False
assert rallies["automated_non_display_runner_entitlement"]=="NOT_ATTESTED"
assert rallies["unadjusted_official_rth_integer_volume_lineage"]=="NOT_ATTESTED"
assert rallies["unverified_existing_passive_reader_price_dv30"]=="QUARANTINE_UNKNOWN_NOT_AUTHORITY"
assert rallies["no_threshold_change"] is True and rallies["no_fabricated_pass"] is True
assert rallies["paid_top_up_allowed"] is False
assert "fractional" in rallies["volume_integrity"].lower()
print("XRAY_PROVIDER_AUTOMATION_GOVERNANCE_SELFTEST=PASS")

# READINESS_WORKFLOW_RUN_REBIND_PROBE_2026_10_05: no semantic change.
