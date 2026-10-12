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

    # RED regressions for actual G9 technical payload ingestion:
    # NaN/Inf and timezone-naive timestamps must never create technical PASS.
    mod=load_mod()
    assert mod.parse_ts("2026-10-12T09:00:00") is None, "NAIVE_TIMESTAMP_ACCEPTED"
    assert mod.best([{"Price":"Infinity","TimeStamp":"2026-10-12T09:00:00Z"}],"bid") is None, "INFINITE_DEPTH_ACCEPTED"
    assert mod.exact_symbol_row([{"symbol":"aaPl"}],"AAPL") is None, "CASE_COLLIDED_ISSUER_ACCEPTED"
    for triplet in ((float("nan"),100,100),(1,float("inf"),1),(True,2,2),
                    (100,99,100),(0,1,1)):
        try:
            mod.strict_triplet(*triplet)
        except ValueError:
            continue
        raise AssertionError("INVALID_G9_PRICE_TRIPLET_ACCEPTED")
    assert mod.strict_triplet(10,11,10.5)==(10.0,11.0,10.5)
    # RED: preauthority probe is SHADOW but must not accept corrupt provider
    # prices or infer timezone from an unspecified runner locale.
    from datetime import datetime,timezone,timedelta
    spec=importlib.util.spec_from_file_location("g9_preauth_shadow_test",
                                                HERE/"g9_preauthority_probe.py")
    pre=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pre)
    n=datetime(2026,10,12,14,0,tzinfo=timezone.utc)
    valid=n-timedelta(seconds=5)
    assert pre.parse_ts("2026-10-12T14:00:00") is None,"PREAUTH_NAIVE_TIMESTAMP_ACCEPTED"
    assert pre.parse_ts(float("nan")) is None,"PREAUTH_NAN_EPOCH_ACCEPTED"
    for b,a,l in ((float("nan"),101,100),(99,float("inf"),100),
                  (99,101,float("-inf")),(True,101,100),(101,99,100)):
        try:pre.validate_triplet(b,a,l,valid,valid,n)
        except (ValueError,TypeError,RuntimeError):continue
        raise AssertionError("PREAUTH_INVALID_QUOTE_ACCEPTED")
    assert pre.validate_triplet(99,101,100,valid,valid,n)[:3]==(99.0,101.0,100.0)
    print("XRAY_STRICT_G9_FAIL_CLOSED_SELFTEST=PASS")

if __name__=="__main__":
    main()
