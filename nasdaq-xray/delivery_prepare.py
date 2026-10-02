#!/usr/bin/env python3
"""Prepare a fail-closed XRAY RESEARCH AL ADAYI backup notification.

Authority is the canonical durable pointer. A candidate is deliverable only after
the canonical task has registered an exact R92 object and its unique delivery_key
in the same successful pointer CAS. G9/account are reported, not required, for a
research-only candidate. EXECUTION always remains NONE and REAL_MONEY NO-GO.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POINTER = ROOT / "chatgpt_canonical_state_v2.json"
OUT = ROOT / "material_alert_issue.md"
META = ROOT / "material_alert_meta.json"

if not POINTER.exists():
    print("XRAY_DELIVERY_NOOP=NO_POINTER")
    raise SystemExit(0)

p = json.loads(POINTER.read_text())
if p.get("schema") != "XRAY_GITHUB_DURABLE_STATE_V3":
    raise RuntimeError("DELIVERY_POINTER_SCHEMA_FAIL")
if p.get("authority") != "GITHUB_CURRENT_POINTER":
    raise RuntimeError("DELIVERY_POINTER_AUTHORITY_FAIL")
if p.get("execution") != "NONE" or p.get("real_money") != "NO-GO":
    raise RuntimeError("DELIVERY_POINTER_SAFETY_LOCK_FAIL")

s = p.get("state_json") or {}
if isinstance(s, str):
    s = json.loads(s)
if not isinstance(s, dict):
    raise RuntimeError("DELIVERY_STATE_JSON_INVALID")
if s.get("task_id") != "6a825366222081918997094d76e6ae46":
    raise RuntimeError("DELIVERY_CANONICAL_TASK_MISMATCH")

delivery_keys = set(s.get("delivery_keys") or [])
r92 = s.get("r92") or []
if not isinstance(r92, list):
    raise RuntimeError("DELIVERY_R92_NOT_LIST")

required = [
    "delivery_key","asof_et","symbol","setup","entry_low","entry_high",
    "chase_limit","stop","r1","rr_basic","regime","event_status",
    "mc_class","dv20","pass_reason","registered_at_utc",
]
eligible = []
for x in r92:
    if not isinstance(x, dict):
        continue
    if x.get("schema") != "XRAY_RESEARCH_CANDIDATE_R92_V1":
        continue
    if x.get("execution") != "NONE" or x.get("real_money") != "NO-GO":
        raise RuntimeError("DELIVERY_R92_SAFETY_LOCK_FAIL")
    if x.get("delivery_key") not in delivery_keys:
        continue
    missing = [k for k in required if x.get(k) is None]
    if missing:
        raise RuntimeError("DELIVERY_R92_FIELDS_MISSING:" + ",".join(missing))
    eligible.append(x)

if not eligible:
    print("XRAY_DELIVERY_NOOP=NO_REGISTERED_RESEARCH_CANDIDATE")
    raise SystemExit(0)

# The GitHub workflow deduplicates by delivery_key, so selecting the newest
# registered candidate is safe. Canonical emits at most top3 and every candidate
# receives its own unique delivery key.
eligible.sort(key=lambda x: (str(x.get("registered_at_utc","")), str(x.get("delivery_key",""))))
x = eligible[-1]

g9 = str(x.get("g9_status") or s.get("g9_status") or "UNKNOWN")
account = str(x.get("account_status") or s.get("account_status") or "UNKNOWN")
rr_severe = x.get("rr_severe")
mc_source = x.get("mc_source") or "UNSPECIFIED"
liquidity = x.get("liquidity") or "DV20_POLICY_PASS"

body = f"""# XRAY RESEARCH AL ADAYI

**Research / forward-test only. Broker emri veya otomatik execution değildir.**

- Delivery key: `{x['delivery_key']}`
- Symbol: **{x['symbol']}**
- Setup: **{x['setup']}**
- ASOF: **{x['asof_et']}**
- Entry band: **{x['entry_low']} – {x['entry_high']}**
- Chase veto: **{x['chase_limit']}**
- Stop / invalidity: **{x['stop']}**
- R1: **{x['r1']}**
- RR basic: **{x['rr_basic']}**
- RR severe: **{rr_severe if rr_severe is not None else 'N/A'}**
- Regime: **{x['regime']}**
- Event status: **{x['event_status']}**
- MC: **{x['mc_class']}** / {mc_source}
- DV20: **{x['dv20']}**
- Liquidity: **{liquidity}**
- Pass reason: {x['pass_reason']}
- G9: **{g9}**
- Account: **{account}**
- Registered UTC: **{x['registered_at_utc']}**
- EXECUTION: **NONE**
- REAL_MONEY: **NO-GO**

Bu bildirim yalnızca canonical durable pointer'a başarılı CAS ile önceden kaydedilmiş
R92 araştırma adayından üretilmiştir. G9/account eksikliği research adayını bastırmaz;
TRUE FULL GO / GREEN için bu iki kapı ayrıca PASS olmalıdır.
"""
OUT.write_text(body, encoding="utf-8")
META.write_text(json.dumps({
    "delivery_key": x["delivery_key"],
    "symbol": x["symbol"],
    "asof_et": x["asof_et"],
    "execution": "NONE",
    "real_money": "NO-GO",
}, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
print("XRAY_DELIVERY_READY=PASS")
print("XRAY_DELIVERY_KEY=" + x["delivery_key"])
print("XRAY_DELIVERY_SYMBOL=" + x["symbol"])
