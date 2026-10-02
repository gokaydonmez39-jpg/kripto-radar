#!/usr/bin/env python3
"""Prepare fail-closed XRAY RESEARCH AL ADAYI backup notifications.

Authority is the canonical durable pointer. Candidates are deliverable only after
canonical registered complete R92 records and their unique delivery keys in the
same successful pointer CAS. G9/account are reported, not required, for research.
EXECUTION always remains NONE and REAL_MONEY NO-GO.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POINTER = ROOT / "chatgpt_canonical_state_v2.json"
WORK = ROOT / ".delivery_work"
BATCH = WORK / "batch.json"

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
    "chase_limit","stop","r1","rr_basic","rr_severe","regime","event_status",
    "mc_class","mc_source","dv20","liquidity","pass_reason","g9_status",
    "account_status","registered_at_utc","execution","real_money",
]
eligible = []
seen = set()
for x in r92:
    if not isinstance(x, dict):
        continue
    if x.get("schema") != "XRAY_RESEARCH_CANDIDATE_R92_V1":
        continue
    if x.get("execution") != "NONE" or x.get("real_money") != "NO-GO":
        raise RuntimeError("DELIVERY_R92_SAFETY_LOCK_FAIL")
    key = x.get("delivery_key")
    if key not in delivery_keys:
        continue
    if key in seen:
        raise RuntimeError("DELIVERY_DUPLICATE_R92_KEY")
    seen.add(key)
    missing = [k for k in required if x.get(k) is None]
    if missing:
        raise RuntimeError("DELIVERY_R92_FIELDS_MISSING:" + ",".join(missing))
    eligible.append(x)

if not eligible:
    print("XRAY_DELIVERY_NOOP=NO_REGISTERED_RESEARCH_CANDIDATE")
    raise SystemExit(0)

eligible.sort(key=lambda x: (str(x["registered_at_utc"]), str(x["delivery_key"])))
WORK.mkdir(exist_ok=True)
entries = []

for idx, x in enumerate(eligible, 1):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", x["delivery_key"])[-140:]
    body_path = WORK / f"{idx:03d}_{safe}.md"
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
- RR severe: **{x['rr_severe']}**
- Regime: **{x['regime']}**
- Event status: **{x['event_status']}**
- MC: **{x['mc_class']}** / {x['mc_source']}
- DV20: **{x['dv20']}**
- Liquidity: **{x['liquidity']}**
- Pass reason: {x['pass_reason']}
- G9: **{x['g9_status']}**
- Account: **{x['account_status']}**
- Registered UTC: **{x['registered_at_utc']}**
- EXECUTION: **NONE**
- REAL_MONEY: **NO-GO**

Bu bildirim yalnızca canonical durable pointer'a başarılı CAS ile önceden kaydedilmiş
R92 araştırma adayından üretilmiştir. G9/account eksikliği research adayını bastırmaz;
TRUE FULL GO / GREEN için bu iki kapı ayrıca PASS olmalıdır.
"""
    body_path.write_text(body, encoding="utf-8")
    entries.append({
        "delivery_key": x["delivery_key"],
        "symbol": x["symbol"],
        "asof_et": x["asof_et"],
        "body_file": str(body_path.relative_to(ROOT.parent)),
        "execution": "NONE",
        "real_money": "NO-GO",
    })

BATCH.write_text(json.dumps({"candidates": entries}, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
print("XRAY_DELIVERY_READY=PASS")
print("XRAY_DELIVERY_COUNT=" + str(len(entries)))
