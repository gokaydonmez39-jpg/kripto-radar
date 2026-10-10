#!/usr/bin/env python3
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from price_dv30_phase import expected30
from price_dv30_recover_from_fullstate import (
    official_recent_listing_terminal,
    apply_official_recent_listing_fail_only,
)

ROOT=Path(__file__).resolve().parent
REGISTRY=ROOT/"price_official_listing_registry.json"
ASOF="2026-10-09"
EXPECTED_SYMBOLS={"ACCV","ADRX","AIOK","BBCI","CHWM","ETRA","OIG","RTSN","RZAI","TBCV","TRXB","WQEY","XIII"}


def main():
    registry=json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry.get("schema")=="XRAY_PRICE_OFFICIAL_LISTING_REGISTRY_V1"
    assert registry.get("authority")=="OFFICIAL_LISTING_DATE_FAIL_ONLY"
    assert registry.get("execution")=="NONE"
    assert registry.get("real_money")=="NO-GO"
    assert registry.get("unknown_never_pass") is True
    assert set(registry.get("records") or {})==EXPECTED_SYMBOLS

    exp30=expected30(ASOF)
    assert len(exp30)==30 and exp30[-1]==ASOF,exp30

    for sym in sorted(EXPECTED_SYMBOLS):
        ev=official_recent_listing_terminal(registry,sym,ASOF,exp30)
        assert ev is not None,(sym,exp30[0],registry["records"][sym])
        assert ev.get("reason")=="OFFICIAL_RECENT_LISTING_LT_30_COMPLETED_SESSIONS",ev
        assert ev.get("proof")=="OFFICIAL_FIRST_TRADE_DATE_AFTER_EXACT30_WINDOW_START",ev
        assert ev.get("decision_direction")=="FAIL_ONLY_NEVER_PASS",ev
        assert ev.get("no_synthetic_bar") is True,ev
        assert 0 < int(ev.get("max_possible_completed_sessions_in_exact30_window",-1)) < 30,ev
        assert ev.get("source_url"),ev

    # A symbol absent from the official registry can never be terminalized.
    assert official_recent_listing_terminal(registry,"GRAL",ASOF,exp30) is None

    # Listing at or before the first exact-30 session does not prove
    # insufficient history and must remain unresolved by this helper.
    edge=deepcopy(registry)
    edge["records"]["TEST"]={
        "first_trade_date":exp30[0],
        "authority":"ISSUER_IR_PRIMARY",
        "source_url":"https://issuer.example.test/official",
        "evidence_kind":"TEST",
    }
    assert official_recent_listing_terminal(edge,"TEST",ASOF,exp30) is None

    # Future listing evidence cannot classify the current ASOF.
    future=deepcopy(registry)
    future["records"]["TEST"]={
        "first_trade_date":"2026-10-12",
        "authority":"SEC_PRIMARY",
        "source_url":"https://www.sec.gov/example",
        "evidence_kind":"TEST",
    }
    assert official_recent_listing_terminal(future,"TEST",ASOF,exp30) is None

    # Unapproved authority is fail-closed.
    bad=deepcopy(registry)
    bad["records"]["TEST"]={
        "first_trade_date":"2026-10-01",
        "authority":"UNOFFICIAL_AGGREGATOR",
        "source_url":"https://example.test",
        "evidence_kind":"TEST",
    }
    assert official_recent_listing_terminal(bad,"TEST",ASOF,exp30) is None

    # Persisted UNKNOWN/BLOCK states must be terminalized by official listing proof,
    # while pre-existing PASS/FAIL decisions remain byte-semantically untouched.
    sample={
        "ACCV":{"status":"UNKNOWN","info":{"reason":"OLD_UNRESOLVED"}},
        "ADRX":{"status":"BLOCK_CURRENT_RUN","info":{"reason":"OLD_BLOCK"}},
        "BBCI":{"status":"BLOCK_CURRENT_RUN","info":{"reason":"OFFICIAL_FIRST_TRADING_DATE_BLOCK"}},
        "CHWM":{"status":"PASS_PRICE_DV30","info":{"sentinel":"KEEP_PASS"}},
        "ETRA":{"status":"FAIL_DV30","info":{"sentinel":"KEEP_FAIL"}},
    }
    pass_before=deepcopy(sample["CHWM"])
    fail_before=deepcopy(sample["ETRA"])
    changed=apply_official_recent_listing_fail_only(sample,registry,ASOF,exp30)
    assert set(changed)=={"ACCV","ADRX","BBCI"},changed
    assert sample["ACCV"]["status"]=="FAIL_DV30_INSUFFICIENT_SESSIONS",sample["ACCV"]
    assert sample["ADRX"]["status"]=="FAIL_DV30_INSUFFICIENT_SESSIONS",sample["ADRX"]
    assert sample["BBCI"]["status"]=="FAIL_DV30_INSUFFICIENT_SESSIONS",sample["BBCI"]
    assert sample["BBCI"]["info"]["max_possible_completed_sessions_in_exact30_window"]==3
    assert sample["CHWM"]==pass_before,sample["CHWM"]
    assert sample["ETRA"]==fail_before,sample["ETRA"]
    assert sample["ACCV"]["info"]["decision_direction"]=="FAIL_ONLY_NEVER_PASS"
    assert sample["ADRX"]["info"]["decision_direction"]=="FAIL_ONLY_NEVER_PASS"
    assert sample["BBCI"]["info"]["source_url"]=="https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-717"
    assert official_recent_listing_terminal(registry,"BBCI","2026-10-06",expected30("2026-10-06")) is None

    # Pinned 9-Oct production PRICE proof: accept both the prior four-UNKNOWN
    # state and the exact in-place 3 FAIL + 1 UNKNOWN result. Never infer GO.
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    if price["asof_et"]==ASOF:
        four=["AIOK","GRAL","RTSN","TRXB"]
        ipo=["AIOK","RTSN","TRXB"]
        assert price["pass_count"]==514 and len(price["pass_symbols"])==514
        assert set(price["pass_symbols"]).isdisjoint(four)
        assert price["results"]["GRAL"]["status"]=="UNKNOWN"
        assert price["unknown_symbols"] in (four,["GRAL"]), "UNEXPECTED_PRICE_UNKNOWN_TRANSITION"
        sample_real={x:deepcopy(price["results"][x]) for x in four}
        changed_real=apply_official_recent_listing_fail_only(sample_real,registry,ASOF,exp30)
        if price["unknown_symbols"]==four:
            assert changed_real==ipo,changed_real
            assert price["unknown_count"]==4
            print("XRAY_09_OCT_IPO_FAIL_ONLY=PASS_PRIOR_FOUR_UNKNOWN_EXACT_REPLAY")
        else:
            assert changed_real==[],changed_real
            assert price["unknown_count"]==1
            assert all(price["results"][x]["status"]=="FAIL_DV30_INSUFFICIENT_SESSIONS"
                       for x in ipo)
            print("XRAY_09_OCT_IPO_FAIL_ONLY=PASS_COMMITTED_THREE_FAIL_ONE_UNKNOWN")
        assert sample_real["GRAL"]==price["results"]["GRAL"]
        assert all(sample_real[x]["status"]=="FAIL_DV30_INSUFFICIENT_SESSIONS"
                   for x in ipo)
        assert all(sample_real[x]["info"]["max_possible_completed_sessions_in_exact30_window"]==1
                   and sample_real[x]["info"]["first_trade_date"]==ASOF for x in ipo)
        assert not any(sample_real[x]["status"]=="PASS_PRICE_DV30" for x in four)
    else:
        print("XRAY_09_OCT_REPLAY_SKIPPED_CURRENT_PRICE_MOVED_TO_NEW_ASOF")

    print("XRAY_PRICE_OFFICIAL_LISTING_SELFTEST=PASS")
    print(json.dumps({
        "asof":ASOF,
        "exact30_start":exp30[0],
        "terminalized_expected":sorted(EXPECTED_SYMBOLS),
        "terminalized_count":len(EXPECTED_SYMBOLS),
        "pass_path_exists":False,
    },sort_keys=True))


if __name__=="__main__":
    main()
