#!/usr/bin/env python3
import json, hashlib
from pathlib import Path

OLD_VERSION="C4.14"
NEW_VERSION="C4.15"
OLD_HASH="bc4ad11c4029bf5feb5399ae3aa7af9c9c8dd7ad6c44119bac4e5734287b931e"
NEW_HASH="7454b9156b6161f1bd3f44d150f71e03f99b471466ce364aa5a490e29e39a015"
OLD_BLOB="b41a40403c03e8884ee90d5cce2e0844d2bea0cd"
NEW_BLOB="a11947566c170d47e4d806a9e17bd8830d7c83fc"

policy_path=Path("nasdaq-xray/chatgpt_compiled_policy_v3.json")
top=json.loads(policy_path.read_text())
old_payload=json.loads(top["payload_json"])
assert old_payload["version"]==OLD_VERSION
assert top["policy_hash"]==OLD_HASH

payload=json.loads(top["payload_json"])
payload["version"]=NEW_VERSION
s=payload["settlement"]
s["sequential"]="oldest-first completed RTH; after ASOF close+15m require Alpaca delayed-SIP completed-session daily bar for AAPL+NVDA+one prior-current-core; exact same session; Rallies exact daily plus Longbridge US quote regular-session OHLC must each match SIP to $0.01 display precision when Longbridge quote timestamp binds the same official RTH close; for stale catch-up, Nasdaq official historical same-ASOF row may replace Longbridge only when present and exact-session bound; otherwise settlement UNKNOWN; vendor volume differences diagnostic only; stop first FAIL/UNKNOWN"
s["primary"]="ALPACA_HISTORICAL_SIP_DAILY_AFTER_15M"
s["crosscheck"]="Rallies exact daily + Longbridge regular-session quote OHLC for latest completed session; Longbridge timestamp must bind same official RTH close and OHLC rounded to 0.01 must equal Alpaca SIP. For stale catch-up only, Nasdaq official historical same-ASOF OHLC may replace Longbridge when available. Massive/Polygon is optional diagnostic only and never required under zero-dollar hard cap."
s["latest_session_crosscheck"]="LONGBRIDGE_US_QUOTE_REGULAR_SESSION_OHLC__SAME_ASOF_OFFICIAL_RTH_CLOSE_TIMESTAMP__RALLIES_MATCH__ALPACA_SIP_PRIMARY"
s["stale_session_crosscheck"]="NASDAQ_OFFICIAL_HISTORICAL_SAME_ASOF_IF_AVAILABLE_ELSE_UNKNOWN"
s["massive_polygon_role"]="OPTIONAL_DIAGNOSTIC_ONLY_NOT_REQUIRED"
s["zero_dollar_fail_closed"]=True
payload["settlement_change"]={
    "id":"SETTLEMENT_ZERO_DOLLAR_CROSSCHECK_V2",
    "base_policy_hash":OLD_HASH,
    "base_policy_version":OLD_VERSION,
    "reason":"Massive/Polygon daily OHLC is NOT_ENTITLED on the zero-dollar runtime. Replace only the settlement crosscheck with an already-authorized zero-dollar Longbridge quote path for the latest completed session; retain Alpaca delayed-SIP as primary and Rallies as independent exact-daily crosscheck. No alpha thresholds or candidate rules change.",
    "observed_20261002":{
        "AAPL":{"alpaca":[333.26,334.54,330.61,333.69],"rallies":[333.26,334.54,330.61,333.69],"longbridge":[333.26,334.54,330.61,333.69],"longbridge_timestamp":"2026-10-02T20:00:01Z"},
        "NVDA":{"alpaca":[236.055,237.88,233.6,233.95],"rallies":[236.055,237.88,233.6,233.95],"longbridge":[236.055,237.88,233.6,233.95],"longbridge_timestamp":"2026-10-02T20:00:00Z"},
        "MSFT":{"alpaca":[519.385,522.5,513.66,517.53],"rallies":[519.385,522.5,513.66,517.53],"longbridge":[519.385,522.5,513.66,517.53],"longbridge_timestamp":"2026-10-02T20:00:01Z"},
    },
    "invariants":["NO_ALPHA_THRESHOLD_CHANGE","NO_UNIVERSE_CHANGE","NO_PRICE_DV20_CHANGE","NO_MC_CHANGE","NO_HISTORY_THRESHOLD_CHANGE","NO_SETUP_CHANGE","NO_G9_CHANGE","NO_ACCOUNT_CHANGE","NO_EXECUTION_CHANGE","SETTLEMENT_CROSSCHECK_ONLY"],
}
payload_json=json.dumps(payload,separators=(",",":"),ensure_ascii=False)
assert hashlib.sha256(payload_json.encode()).hexdigest()==NEW_HASH

out=dict(top)
out["policy_hash"]=NEW_HASH
out["source_proof"]={
    "base_policy_path":"nasdaq-xray/chatgpt_compiled_policy_v3.json",
    "base_policy_blob_sha":OLD_BLOB,
    "base_policy_hash":OLD_HASH,
    "base_policy_version":OLD_VERSION,
    "repair_reason":"Zero-dollar settlement crosscheck migration only: Massive/Polygon entitlement unavailable; live 2026-10-02 AAPL/NVDA/MSFT Alpaca delayed-SIP, Rallies and Longbridge regular-session OHLC matched to $0.01.",
    "invariants":["NO_ALPHA_THRESHOLD_CHANGE","NO_UNIVERSE_CHANGE","NO_PRICE_DV20_CHANGE","NO_MC_CHANGE","NO_HISTORY_THRESHOLD_CHANGE","NO_SETUP_CHANGE","NO_G9_CHANGE","NO_ACCOUNT_CHANGE","NO_EXECUTION_CHANGE","SETTLEMENT_CROSSCHECK_ONLY"],
}
out["payload_json"]=payload_json
policy_content=json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
blob=hashlib.sha1((f"blob {len(policy_content.encode())}\0").encode()+policy_content.encode()).hexdigest()
assert blob==NEW_BLOB,(blob,NEW_BLOB)
policy_path.write_text(policy_content)

active=[
    "nasdaq-xray/build_current_event_request.py",
    "nasdaq-xray/build_current_event_state.py",
    "nasdaq-xray/build_current_resolver_request.py",
    "nasdaq-xray/build_current_terminal.py",
    "nasdaq-xray/price_dv20_recover_from_fullstate.py",
    ".github/workflows/xray-canonical-current-pre-mc.yml",
    ".github/workflows/xray-canonical-current-post-mc.yml",
    ".github/workflows/xray-canonical-current-final.yml",
]
for name in active:
    p=Path(name)
    t=p.read_text()
    before=(t.count(OLD_VERSION),t.count(OLD_HASH),t.count(OLD_BLOB))
    assert any(before),(name,before)
    t=t.replace(OLD_HASH,NEW_HASH).replace(OLD_BLOB,NEW_BLOB).replace(OLD_VERSION,NEW_VERSION)
    if name=="nasdaq-xray/build_current_resolver_request.py":
        old="ALPACA_HISTORICAL_SIP_DAILY_AFTER_15M__AAPL_NVDA_PLUS_ONE_PRIOR_CURRENT_CORE__RALLIES_MASSIVE_OHLC_0_01_CROSSCHECK__SIP_VOLUME_AUTHORITY__FAIL_CLOSED__DELAYED_SIP_NEVER_G9"
        new="ALPACA_HISTORICAL_SIP_DAILY_AFTER_15M__AAPL_NVDA_PLUS_ONE_PRIOR_CURRENT_CORE__RALLIES_LONGBRIDGE_QUOTE_OHLC_0_01_CROSSCHECK__SIP_VOLUME_AUTHORITY__FAIL_CLOSED__DELAYED_SIP_NEVER_G9"
        assert old in t
        t=t.replace(old,new)
        old2="ALPACA_SIP_BATCH_PRIMARY__MASSIVE_SETTLEMENT_CROSSCHECK__NEVER_G9__FAIL_CLOSED__SAME_ASOF_QUEUE_BINDING"
        new2="ALPACA_SIP_BATCH_PRIMARY__RALLIES_LONGBRIDGE_LATEST_SETTLEMENT_CROSSCHECK__NEVER_G9__FAIL_CLOSED__SAME_ASOF_QUEUE_BINDING"
        assert old2 in t
        t=t.replace(old2,new2)
    p.write_text(t)
    assert OLD_HASH not in t and OLD_BLOB not in t,(name,"old pin remains")

p=Path(".github/workflows/xray-dynamic-policy-invariants.yml")
t=p.read_text()
assert 'assert p["version"]=="C4.14"' in t
p.write_text(t.replace('assert p["version"]=="C4.14"','assert p["version"]=="C4.15"'))

# Direct policy invariants: alpha semantics are byte-structurally unchanged.
for key in ["universe","hard_gates","mc","setups","technicals","events","lifecycle","g9","r92_r93"]:
    assert payload.get(key)==old_payload.get(key),(key,"DRIFT")
assert payload["policy_change"]==old_payload["policy_change"]

# New settlement proof checks.
assert payload["settlement"]["primary"]=="ALPACA_HISTORICAL_SIP_DAILY_AFTER_15M"
assert payload["settlement"]["massive_polygon_role"]=="OPTIONAL_DIAGNOSTIC_ONLY_NOT_REQUIRED"
assert payload["settlement"]["zero_dollar_fail_closed"] is True
assert payload["settlement_change"]["base_policy_hash"]==OLD_HASH
assert payload["settlement_change"]["base_policy_version"]==OLD_VERSION
for sym in ["AAPL","NVDA","MSFT"]:
    o=payload["settlement_change"]["observed_20261002"][sym]
    assert o["alpaca"]==o["rallies"]==o["longbridge"],sym

print(json.dumps({
    "status":"PASS",
    "new_version":NEW_VERSION,
    "new_policy_hash":NEW_HASH,
    "new_policy_blob":NEW_BLOB,
    "alpha_semantics_unchanged":True,
    "settlement_only_change":True,
},sort_keys=True))
