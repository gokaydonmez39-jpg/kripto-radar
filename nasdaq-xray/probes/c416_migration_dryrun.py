#!/usr/bin/env python3
import json, hashlib
from pathlib import Path

OLD_VERSION="C4.15"
NEW_VERSION="C4.16"
OLD_HASH="7454b9156b6161f1bd3f44d150f71e03f99b471466ce364aa5a490e29e39a015"
OLD_BLOB="a11947566c170d47e4d806a9e17bd8830d7c83fc"

policy_path=Path("nasdaq-xray/chatgpt_compiled_policy_v3.json")
top=json.loads(policy_path.read_text())
old_payload=json.loads(top["payload_json"])
assert old_payload["version"]==OLD_VERSION
assert top["policy_hash"]==OLD_HASH
assert old_payload["settlement_change"]["id"]=="SETTLEMENT_ZERO_DOLLAR_CROSSCHECK_V2"

payload=json.loads(top["payload_json"])
payload["version"]=NEW_VERSION
s=payload["settlement"]
s["preferred_primary"]="ALPACA_HISTORICAL_SIP_DAILY_AFTER_15M"
s["connector_failover"]="RALLIES_LONGBRIDGE_DUAL_SOURCE_SETTLEMENT_V1"
s["connector_failover_activation"]="ONLY_AFTER_BOUNDED_ALPACA_CONNECTOR_INTERNAL_ERROR_OR_UNAVAILABLE; NEVER after an Alpaca market-data mismatch; fail closed"
s["connector_failover_rule"]="For exact settlement symbols only, require Rallies exact same-ASOF daily OHLCV plus Longbridge US quote regular-session OHLCV; Longbridge timestamp must bind the same ASOF official 16:00 ET RTH close; both sources Normal/current, no stale/halted/placeholder; O/H/L/C must match after 0.01 rounding; both volumes finite positive and relative volume difference <=5%; otherwise settlement UNKNOWN"
s["volume_authority"]="Preferred path: Alpaca SIP completed-session volume. Connector-failover path: no single-source authority; require both Rallies and Longbridge finite positive volumes with relative difference <=5%."
s["g9_separation"]="All historical/delayed SIP and Rallies/Longbridge settlement evidence is explicitly NON-G9 and cannot satisfy G9 A-D"
s["zero_dollar_fail_closed"]=True

obs2={
  "AAPL":{"rallies":{"o":333.26,"h":334.54,"l":330.61,"c":333.69,"v":34091128.043588},"longbridge":{"o":333.26,"h":334.54,"l":330.61,"c":333.69,"v":33271833,"timestamp":"2026-10-02T20:00:01Z","trade_status":"Normal"}},
  "NVDA":{"rallies":{"o":236.055,"h":237.88,"l":233.6,"c":233.95,"v":135132341.832298},"longbridge":{"o":236.055,"h":237.88,"l":233.6,"c":233.95,"v":135024286,"timestamp":"2026-10-02T20:00:00Z","trade_status":"Normal"}},
  "MSFT":{"rallies":{"o":519.385,"h":522.5,"l":513.66,"c":517.53,"v":18334529.176252},"longbridge":{"o":519.385,"h":522.5,"l":513.66,"c":517.53,"v":17816757,"timestamp":"2026-10-02T20:00:01Z","trade_status":"Normal"}}
}
hist1={
  "AAPL":{"rallies_volume":36247958.016695,"longbridge_volume":34957583},
  "NVDA":{"rallies_volume":98387391.635157,"longbridge_volume":97066749},
  "MSFT":{"rallies_volume":19698870.535577,"longbridge_volume":18878627}
}
def rel(a,b):
    return abs(float(a)-float(b))/max(float(a),float(b))
for sym,o in obs2.items():
    r=o["rallies"]; l=o["longbridge"]
    assert all(round(float(r[k]),2)==round(float(l[k]),2) for k in ["o","h","l","c"]),sym
    assert float(r["v"])>0 and float(l["v"])>0
    assert rel(r["v"],l["v"])<=0.05,(sym,rel(r["v"],l["v"]))
    assert l["timestamp"].startswith("2026-10-02T20:00:0")
    assert l["trade_status"]=="Normal"
for sym,o in hist1.items():
    assert rel(o["rallies_volume"],o["longbridge_volume"])<=0.05,(sym,rel(o["rallies_volume"],o["longbridge_volume"]))

payload["settlement_fallback_change"]={
  "id":"SETTLEMENT_ZERO_DOLLAR_CONNECTOR_FAILOVER_V1",
  "base_policy_hash":OLD_HASH,
  "base_policy_version":OLD_VERSION,
  "reason":"ChatGPT Alpaca connector returned tool-level internal errors across bars, snapshots, latest quote/trade and asset reads. Add a settlement-only zero-dollar failover that requires two independent authenticated sources to agree; never weaken any alpha or G9 rule.",
  "activation":"ALPACA_CONNECTOR_INTERNAL_ERROR_OR_UNAVAILABLE_ONLY_AFTER_BOUNDED_ATTEMPTS",
  "fallback":"RALLIES_LONGBRIDGE_DUAL_SOURCE_SETTLEMENT_V1",
  "requirements":{
    "scope":"exact settlement symbols only: AAPL+NVDA+one prior-current-core",
    "same_asof":True,
    "longbridge_rth_close_timestamp":"same ASOF official 16:00 ET close",
    "ohlc_rounding":"all O/H/L/C equal after 0.01 rounding",
    "volume":"both finite positive; relative difference <=5%",
    "status":"Longbridge Normal/current; no stale/halted/placeholder",
    "failure":"any mismatch/missing/stale/auth/tool ambiguity => settlement UNKNOWN",
    "g9":"NON-G9"
  },
  "observed_20261002":obs2,
  "historical_volume_precedent_20261001":hist1,
  "invariants":["NO_ALPHA_THRESHOLD_CHANGE","NO_UNIVERSE_CHANGE","NO_PRICE_DV20_CHANGE","NO_MC_CHANGE","NO_HISTORY_THRESHOLD_CHANGE","NO_SETUP_CHANGE","NO_EVENT_CHANGE","NO_G9_CHANGE","NO_ACCOUNT_CHANGE","NO_EXECUTION_CHANGE","SETTLEMENT_FAILOVER_ONLY","UNKNOWN_NEVER_PASS"]
}

# Preserve all alpha semantics and prior migration evidence.
alpha_keys=["universe","hard_gates","mc","dv20","technical","technicals","geometry","setups","r1_rr","regime","events_account","lifecycle","g9","r92_r93","coverage","delivery","policy_change","mc_fail_evidence","settlement_change"]
for key in alpha_keys:
    if key in old_payload:
        assert payload.get(key)==old_payload.get(key),(key,"DRIFT")
assert payload["settlement"]["primary"]==old_payload["settlement"]["primary"]
assert payload["settlement"]["crosscheck"]==old_payload["settlement"]["crosscheck"]
assert payload["settlement"]["latest_session_crosscheck"]==old_payload["settlement"]["latest_session_crosscheck"]
assert payload["settlement"]["stale_session_crosscheck"]==old_payload["settlement"]["stale_session_crosscheck"]
assert payload["settlement"]["massive_polygon_role"]==old_payload["settlement"]["massive_polygon_role"]

payload_json=json.dumps(payload,separators=(",",":"),ensure_ascii=False)
new_hash=hashlib.sha256(payload_json.encode()).hexdigest()
out=dict(top)
out["policy_hash"]=new_hash
out["source_proof"]={
  "base_policy_path":"nasdaq-xray/chatgpt_compiled_policy_v3.json",
  "base_policy_blob_sha":OLD_BLOB,
  "base_policy_hash":OLD_HASH,
  "base_policy_version":OLD_VERSION,
  "repair_reason":"Settlement-only connector failover: Alpaca connector tool-level outage; Rallies+Longbridge dual-source exact-ASOF fail-closed fallback.",
  "invariants":payload["settlement_fallback_change"]["invariants"],
  "observed_20261002":obs2,
  "historical_volume_precedent_20261001":hist1
}
out["payload_json"]=payload_json
policy_content=json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
new_blob=hashlib.sha1((f"blob {len(policy_content.encode())}\0").encode()+policy_content.encode()).hexdigest()
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
    p=Path(name); t=p.read_text()
    before=(t.count(OLD_VERSION),t.count(OLD_HASH),t.count(OLD_BLOB))
    assert any(before),(name,before)
    t=t.replace(OLD_HASH,new_hash).replace(OLD_BLOB,new_blob).replace(OLD_VERSION,NEW_VERSION)
    if name=="nasdaq-xray/build_current_resolver_request.py":
        marker='ALPACA_SIP_BATCH_PRIMARY__RALLIES_LONGBRIDGE_LATEST_SETTLEMENT_CROSSCHECK__NEVER_G9__FAIL_CLOSED__SAME_ASOF_QUEUE_BINDING'
        replacement='ALPACA_SIP_PREFERRED__RALLIES_LONGBRIDGE_DUAL_SOURCE_CONNECTOR_FAILOVER__NEVER_G9__FAIL_CLOSED__SAME_ASOF_QUEUE_BINDING'
        assert marker in t
        t=t.replace(marker,replacement)
    p.write_text(t)
    assert OLD_HASH not in t and OLD_BLOB not in t,(name,"old pin remains")

p=Path(".github/workflows/xray-dynamic-policy-invariants.yml")
t=p.read_text()
assert 'assert p["version"]=="C4.15"' in t
p.write_text(t.replace('assert p["version"]=="C4.15"','assert p["version"]=="C4.16"'))

validator=Path(".github/workflows/xray-validate-compiled-policy-v3.yml")
validator.write_text(f'''name: XRAY Validate Compiled Policy V3

on:
  push:
    branches: [main]
    paths:
      - ".github/workflows/xray-validate-compiled-policy-v3.yml"
      - "nasdaq-xray/chatgpt_compiled_policy_v3.json"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - name: Validate C4.16 settlement connector failover
        run: |
          python - <<'PYV'
          import json,hashlib
          top=json.load(open("nasdaq-xray/chatgpt_compiled_policy_v3.json"))
          assert top["schema"]=="XRAY_GITHUB_COMPILED_POLICY_V3"
          assert top["execution"]=="NONE" and top["real_money"]=="NO-GO"
          payload=top["payload_json"]; h=hashlib.sha256(payload.encode()).hexdigest()
          assert h==top["policy_hash"]=="{new_hash}"
          x=json.loads(payload)
          assert x["schema"]=="XRAY_COMPILED_POLICY_V1" and x["version"]=="C4.16"
          assert x["unknown_never_pass"] is True and x["zero_dollar_hard_cap"] is True
          assert x["hard_gates"]["price"]==">10"
          assert x["hard_gates"]["market_cap"]==">=2000000000 USD"
          assert x["hard_gates"]["dv20"]=="median exactly20 completed official-RTH Close*regular-session Volume >=50000000"
          assert x["policy_change"]["id"]=="MC_TWO_SOURCE_SUBTHRESHOLD_FAIL_EVIDENCE_V1"
          assert x["settlement_change"]["id"]=="SETTLEMENT_ZERO_DOLLAR_CROSSCHECK_V2"
          f=x["settlement_fallback_change"]
          assert f["id"]=="SETTLEMENT_ZERO_DOLLAR_CONNECTOR_FAILOVER_V1"
          assert f["base_policy_hash"]=="{OLD_HASH}" and f["base_policy_version"]=="C4.15"
          assert f["fallback"]=="RALLIES_LONGBRIDGE_DUAL_SOURCE_SETTLEMENT_V1"
          assert f["requirements"]["volume"]=="both finite positive; relative difference <=5%"
          assert f["requirements"]["failure"].endswith("settlement UNKNOWN")
          assert f["requirements"]["g9"]=="NON-G9"
          s=x["settlement"]
          assert s["primary"]=="ALPACA_HISTORICAL_SIP_DAILY_AFTER_15M"
          assert s["preferred_primary"]=="ALPACA_HISTORICAL_SIP_DAILY_AFTER_15M"
          assert s["connector_failover"]=="RALLIES_LONGBRIDGE_DUAL_SOURCE_SETTLEMENT_V1"
          assert s["massive_polygon_role"]=="OPTIONAL_DIAGNOSTIC_ONLY_NOT_REQUIRED"
          assert s["zero_dollar_fail_closed"] is True
          sp=top["source_proof"]
          assert sp["base_policy_hash"]=="{OLD_HASH}"
          assert sp["base_policy_blob_sha"]=="{OLD_BLOB}"
          assert sp["base_policy_version"]=="C4.15"
          print({{"status":"PASS","policy_hash":h,"version":x["version"]}})
          PYV
''')

print(json.dumps({
 "status":"PASS",
 "new_version":NEW_VERSION,
 "new_policy_hash":new_hash,
 "new_policy_blob":new_blob,
 "alpha_semantics_unchanged":True,
 "settlement_failover_only":True,
 "oct2_volume_relative_diff":{sym:rel(o["rallies"]["v"],o["longbridge"]["v"]) for sym,o in obs2.items()},
 "oct1_volume_relative_diff":{sym:rel(o["rallies_volume"],o["longbridge_volume"]) for sym,o in hist1.items()}
},sort_keys=True))
