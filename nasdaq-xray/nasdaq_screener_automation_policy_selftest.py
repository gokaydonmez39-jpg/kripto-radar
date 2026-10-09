#!/usr/bin/env python3
"""Fail closed: Nasdaq.com website screener automation requires written consent.

This test is deliberately network-free.  A vendor endpoint may exist without
granting automated analytics, caching, data-mining or redistribution rights.
Current official NasdaqTrader membership + SEC evidence keep identity alive.
"""
from __future__ import annotations
import inspect,json
from pathlib import Path
from unittest.mock import patch
import build_current_identity_proofs as identity

ROOT=Path(__file__).resolve().parent

def selftest():
    gov=json.loads((ROOT/"provider_automation_governance.json").read_text())
    rule=gov["providers"]["NASDAQ_PUBLIC_SCREENER"]
    assert rule["unattended_automation_allowed"] is False
    assert rule["written_grant_required"] is True
    assert rule["cutover"] is False
    with patch("urllib.request.urlopen",side_effect=AssertionError("UNLICENSED_NASDAQ_SCREENER_NETWORK_CALL")) as call:
        data=identity.official_screener_industries()
    call.assert_not_called()
    assert data=={},"UNAUTHORIZED_NASDAQ_SCREENER_INDUSTRY_MUST_NOT_BE_COLLECTED"
    impl=inspect.getsource(identity.official_screener_industries)
    assert "urlopen" not in impl and "request_bytes" not in impl
    # No industry means name/SEC remain fail-closed; never hallucinate Blank Checks.
    assert identity.current_spac_suspects(
        {"SHELL":"Shell Acquisition Corp Class A","OPER":"Operating Incorporated"},{}
    )==["SHELL"]
    main=inspect.getsource(identity.main)
    assert '"same_asof_nasdaq_screener_fallback_used":False' in main
    print("XRAY_NASDAQ_WEB_SCREENER_LICENSE_GUARD_SELFTEST=PASS_0_WEB_CALLS_NO_AUTOMATED_CONTENT_NO_FALSE_SPAC_PASS")

if __name__=="__main__":
    selftest()
