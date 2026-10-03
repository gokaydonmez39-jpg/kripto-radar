#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
SRC=HERE/"strict_g9_probe.py"

def load_mod():
    spec=importlib.util.spec_from_file_location("strict_g9_probe_test",SRC)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def run_case(authority, adapters, expect_status, expect_refresh_calls):
    mod=load_mod()
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        auth=td/"authority.json"
        contract=td/"adapters.json"
        out=td/"out.json"
        auth.write_text(json.dumps(authority))
        contract.write_text(json.dumps({
          "schema":"XRAY_G9_PROVIDER_ADAPTER_CONTRACT_V1",
          "adapters":adapters,
        }))
        mod.AUTH=auth
        mod.ADAPTER_CONTRACT=contract
        mod.OUT=out
        mod.os.environ.pop("WEALTHNOW_API_KEY",None)
        mod.os.environ.pop("PAPER_INVEST_API_KEY",None)
        mod.os.environ.pop("CLEARSTREET_API_KEY",None)
        calls={"refresh":0,"get_json":0,"depth":0,"paper":0}
        def fake_refresh():
            calls["refresh"]+=1
            return None,"","SELFTEST_NO_TOKEN"
        def fake_get_json(*args,**kwargs):
            calls["get_json"]+=1
            raise AssertionError("unexpected provider snapshot call")
        def fake_depth(*args,**kwargs):
            calls["depth"]+=1
            raise AssertionError("unexpected provider depth call")
        def fake_paper(*args,**kwargs):
            calls["paper"]+=1
            raise AssertionError("unexpected Paper provider call")
        mod.refresh_token=fake_refresh
        mod.get_json=fake_get_json
        mod.stream_first_depth=fake_depth
        mod.paper_request_json=fake_paper
        mod.is_rth=lambda: False
        mod.main()
        j=json.loads(out.read_text())
        assert j["status"]==expect_status,(j,expect_status)
        assert calls["refresh"]==expect_refresh_calls,(calls,j)
        assert calls["get_json"]==0 and calls["depth"]==0 and calls["paper"]==0,(calls,j)
        assert j["execution"]=="NONE" and j["real_money"]=="NO-GO"
        assert j["g9_pass"] is False
        return j

def main():
    # 1) Negative/unproven authority MUST stop before credentials/network.
    j=run_case(
      {"provider":"NONE_CURRENTLY_QUALIFYING","status":"BLOCKED_STRICT_PERMANENT_ZERO"},
      {"NONE_CURRENTLY_QUALIFYING":{"status":"BLOCKED_NO_PROVIDER_SELECTED"}},
      "BLOCKED_ENTITLEMENT_AUTHORITY_UNPROVEN",0)
    assert j["adapter_status"]=="BLOCKED_NO_PROVIDER_SELECTED"

    # 2) Even PROVEN authority cannot run without an implemented adapter.
    run_case(
      {"provider":"UNKNOWN_VENDOR","status":"PROVEN"},
      {},
      "BLOCKED_PROVIDER_ADAPTER_NOT_IMPLEMENTED",0)

    # 3) An IMPLEMENTED adapter with no runtime dispatch also fails before auth.
    run_case(
      {"provider":"SYNTHETIC_VENDOR","status":"PROVEN"},
      {"SYNTHETIC_VENDOR":{"status":"IMPLEMENTED"}},
      "BLOCKED_PROVIDER_DISPATCH_NOT_IMPLEMENTED",0)

    # 4) Wealthnow negative authority also stops before any provider call.
    j=run_case(
      {"provider":"WEALTHNOW","status":"BLOCKED_STRICT_PERMANENT_ZERO"},
      {"WEALTHNOW":{"status":"IMPLEMENTED"}},
      "BLOCKED_ENTITLEMENT_AUTHORITY_UNPROVEN",0)
    assert j["adapter_status"]=="IMPLEMENTED"

    # 5) PROVEN Wealthnow may reach its dispatch, but missing scheduler secret
    # remains NOT_CONFIGURED and cannot trigger a data call.
    j=run_case(
      {"provider":"WEALTHNOW","status":"PROVEN"},
      {"WEALTHNOW":{"status":"IMPLEMENTED"}},
      "NOT_CONFIGURED",0)
    assert j["reason"]=="WEALTHNOW_API_KEY_NOT_CONFIGURED"

    # 6) Paper Invest negative authority must stop before auth/data calls.
    j=run_case(
      {"provider":"PAPER_INVEST","status":"BLOCKED_STRICT_PERMANENT_ZERO"},
      {"PAPER_INVEST":{"status":"IMPLEMENTED"}},
      "BLOCKED_ENTITLEMENT_AUTHORITY_UNPROVEN",0)
    assert j["adapter_status"]=="IMPLEMENTED"

    # 7) PROVEN Paper Invest can reach dispatch, but missing secret remains
    # NOT_CONFIGURED with no provider call.
    j=run_case(
      {"provider":"PAPER_INVEST","status":"PROVEN"},
      {"PAPER_INVEST":{"status":"IMPLEMENTED"}},
      "NOT_CONFIGURED",0)
    assert j["reason"]=="PAPER_INVEST_API_KEY_NOT_CONFIGURED"

    source=SRC.read_text()
    assert "https://api.paperinvest.io/v1/auth/token" in source
    assert "/v1/market-data/quote/" in source
    assert "/v1/market-data/trade/" in source
    for forbidden in ("/v1/orders","create_order","place_order","cancel_order"):
        assert forbidden not in source, forbidden

    # 8) Clear Street negative authority must stop before any provider call.
    j=run_case(
      {"provider":"CLEAR_STREET","status":"BLOCKED_STRICT_PERMANENT_ZERO"},
      {"CLEAR_STREET":{"status":"IMPLEMENTED"}},
      "BLOCKED_ENTITLEMENT_AUTHORITY_UNPROVEN",0)
    assert j["adapter_status"]=="IMPLEMENTED"

    # 9) PROVEN Clear Street may reach dispatch, but a missing API-key secret
    # remains NOT_CONFIGURED and cannot trigger market-data calls.
    j=run_case(
      {"provider":"CLEAR_STREET","status":"PROVEN"},
      {"CLEAR_STREET":{"status":"IMPLEMENTED"}},
      "NOT_CONFIGURED",0)
    assert j["reason"]=="CLEARSTREET_API_KEY_NOT_CONFIGURED"

    source=SRC.read_text()
    assert "https://api.clearstreet.com/v1/market-data/snapshot" in source
    assert "bid_timestamp" in source and "ask_timestamp" in source
    assert "last_trade" in source

    # 10) Only PROVEN + implemented + known TradeStation dispatch may reach auth.
    j=run_case(
      {"provider":"TRADESTATION","status":"PROVEN"},
      {"TRADESTATION":{"status":"IMPLEMENTED"}},
      "NOT_CONFIGURED",1)
    assert j["reason"]=="SELFTEST_NO_TOKEN"

    print("XRAY_STRICT_G9_FAIL_CLOSED_SELFTEST=PASS")

if __name__=="__main__":
    main()
