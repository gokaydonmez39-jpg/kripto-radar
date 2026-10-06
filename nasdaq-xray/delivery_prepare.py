#!/usr/bin/env python3
"""Prepare fail-closed XRAY RESEARCH AL ADAYI backup notifications.

Authority is the canonical durable pointer plus the exact current terminal.
A registered R92 candidate is deliverable only when its own candidate-local
C4.17 evidence is exact. Unrelated global coverage UNKNOWN may keep the
universe terminal PARTIAL but must not suppress an independently proven local
candidate. Candidate-local UNKNOWN never becomes PASS.
EXECUTION=NONE. REAL_MONEY=NO-GO.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POINTER = ROOT / "chatgpt_canonical_state_v2.json"
TERMINAL = ROOT / "canonical_current_terminal.json"
WORK = ROOT / ".delivery_work"
BATCH = WORK / "batch.json"
OFFICIAL_GUARD = ROOT / "canonical_official_source_guard.json"
CURRENT_PRICE = ROOT / "canonical_current_price_dv30.json"
CURRENT_HISTORY = ROOT / "canonical_current_history.json"
CURRENT_POLICY_HASH = "68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
TASK = "6a825366222081918997094d76e6ae46"

def git_blob_sha(p: Path):
    b = p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode() + b).hexdigest()

def repo_path(rel):
    q = Path(str(rel or ""))
    if not str(q):
        return q
    if q.is_absolute():
        return q
    if str(q).startswith("nasdaq-xray/"):
        return ROOT.parent / q
    return ROOT / q

def load_json(path: Path):
    return json.loads(path.read_text())

def current_chain_state():
    """Validate exact current DV30->MC lineage without demanding global MC_UNKNOWN=0."""
    try:
        px = load_json(CURRENT_PRICE)
        h = load_json(CURRENT_HISTORY)
        mc_path = repo_path(h.get("source_mc_artifact"))
        mc = load_json(mc_path) if mc_path.exists() else {}
        exact = bool(
            px.get("schema") == "XRAY_CANONICAL_PRICE_DV30_V1"
            and int(px.get("unknown_count", -1)) == 0
            and h.get("asof_et") == px.get("asof_et")
            and h.get("source_mc_policy_hash") == CURRENT_POLICY_HASH
            and h.get("source_mc_policy_version") == "C4.17"
            and h.get("source_mc_blob_sha") == git_blob_sha(mc_path)
            and mc.get("schema") == "XRAY_MC_EPOCH_RESULT_V1"
            and mc.get("status") == "COMMITTED"
            and mc.get("asof_et") == px.get("asof_et")
            and mc.get("policy_hash") == CURRENT_POLICY_HASH
            and mc.get("policy_version") == "C4.17"
            and mc.get("input_path") == "nasdaq-xray/canonical_current_price_dv30.json"
            and mc.get("input_pass_hash") == px.get("pass_hash")
            and int(mc.get("input_count", -1)) == int(px.get("pass_count", -2))
            and set((mc.get("results") or {}).keys()) == set(px.get("pass_symbols") or [])
        )
        return exact, px, h, mc_path, mc
    except Exception:
        return False, {}, {}, Path(), {}

def candidate_key(row):
    return f"{str(row.get('symbol') or '').upper()}|{str(row.get('setup') or '').upper()}"

def close_num(a, b):
    try:
        aa = float(a); bb = float(b)
        if not (math.isfinite(aa) and math.isfinite(bb)):
            return False
        return abs(aa - bb) <= max(1e-8, 1e-9 * max(abs(aa), abs(bb), 1.0))
    except Exception:
        return False

def validate_candidate_local_terminal(state, current_price, history, mc_path, mc, rows):
    """Exact candidate-local gate. Global unrelated UNKNOWN is intentionally not a veto."""
    if not TERMINAL.exists():
        raise RuntimeError("DELIVERY_CURRENT_TERMINAL_MISSING")
    t = load_json(TERMINAL)
    tblob = git_blob_sha(TERMINAL)
    asof = str(state.get("asof_et") or "")
    if not (
        t.get("schema") == "XRAY_CANONICAL_CURRENT_TERMINAL_V1"
        and t.get("task_id") == TASK
        and t.get("execution") == "NONE"
        and t.get("real_money") == "NO-GO"
        and t.get("unknown_never_pass") is True
        and str(t.get("asof_et") or "") == asof == str(current_price.get("asof_et") or "")
    ):
        raise RuntimeError("DELIVERY_TERMINAL_IDENTITY_OR_ASOF_MISMATCH")

    de = state.get("deep_final_evidence") or {}
    if not (
        de.get("terminal_path") == "nasdaq-xray/canonical_current_terminal.json"
        and de.get("terminal_blob_sha") == tblob
    ):
        raise RuntimeError("DELIVERY_POINTER_TERMINAL_BINDING_MISMATCH")

    checks = t.get("checks") or {}
    required_checks = [
        "candidate_local_research_pass",
        "alpha_semantic_conformance_exact",
        "alpha_source_binding_exact",
        "lifecycle_frozen_semantics_exact",
        "candidate_legal_guard_exact_binding",
        "all_finalists_detailed_legal_review_exact",
        "mc_exact_price_pass_set",
        "semantic_provenance_chain_exact",
    ]
    if t.get("candidate_local_research_pass") is not True:
        raise RuntimeError("DELIVERY_TERMINAL_CANDIDATE_LOCAL_NOT_PASS")
    if any(checks.get(k) is not True for k in required_checks):
        bad = [k for k in required_checks if checks.get(k) is not True]
        raise RuntimeError("DELIVERY_TERMINAL_LOCAL_CHECK_FAIL:" + ",".join(bad))

    build_safety = t.get("candidate_delivery_safety") or {}
    if build_safety.get("status") != "PASS":
        raise RuntimeError("DELIVERY_TERMINAL_BUILD_SAFETY_NOT_PASS")

    ev = t.get("evidence") or {}
    if (ev.get("price") or {}).get("blob_sha") != git_blob_sha(CURRENT_PRICE):
        raise RuntimeError("DELIVERY_TERMINAL_PRICE_BINDING_MISMATCH")
    if (ev.get("mc") or {}).get("path") != str(mc_path.relative_to(ROOT.parent)).replace("\\", "/"):
        raise RuntimeError("DELIVERY_TERMINAL_MC_PATH_MISMATCH")
    if (ev.get("mc") or {}).get("blob_sha") != git_blob_sha(mc_path):
        raise RuntimeError("DELIVERY_TERMINAL_MC_BLOB_MISMATCH")
    if history.get("source_mc_blob_sha") != git_blob_sha(mc_path):
        raise RuntimeError("DELIVERY_HISTORY_MC_BLOB_MISMATCH")

    final_meta = ev.get("final") or {}
    final_path = repo_path(final_meta.get("path"))
    if not final_path.exists() or final_meta.get("blob_sha") != git_blob_sha(final_path):
        raise RuntimeError("DELIVERY_TERMINAL_FINAL_BINDING_MISMATCH")
    if de.get("final_path") != final_meta.get("path") or de.get("final_blob_sha") != final_meta.get("blob_sha"):
        raise RuntimeError("DELIVERY_POINTER_FINAL_BINDING_MISMATCH")
    final = load_json(final_path)
    if not (
        final.get("schema") == "XRAY_FINAL_TECH_SHADOW_V1"
        and str(final.get("asof_et") or "") == asof
        and final.get("source_compiled_policy_hash") == CURRENT_POLICY_HASH
        and final.get("source_compiled_policy_version") == "C4.17"
        and final.get("policy_semantics_exact") is True
        and final.get("lifecycle_semantics_exact") is True
    ):
        raise RuntimeError("DELIVERY_FINAL_SEMANTIC_BINDING_FAIL")

    terminal_r92 = set(str(x) for x in (t.get("r92_candidates") or []))
    pre = set(str(x) for x in ((t.get("sets") or {}).get("pre_g9_tech_pass") or []))
    if not terminal_r92 or terminal_r92 != pre:
        raise RuntimeError("DELIVERY_TERMINAL_R92_SCOPE_INVALID")

    primary = set(str(x).upper() for x in (mc.get("primary_pass_symbols") or []))
    mc_results = mc.get("results") or {}
    price_results = current_price.get("results") or {}
    price_pass = set(str(x).upper() for x in (current_price.get("pass_symbols") or []))
    final_results = final.get("results") or {}

    for x in rows:
        key = candidate_key(x)
        sym = str(x.get("symbol") or "").upper()
        if key not in terminal_r92 or key not in pre:
            raise RuntimeError("DELIVERY_R92_NOT_TERMINAL_CANDIDATE:" + key)
        if str(x.get("asof_et") or "") != asof:
            raise RuntimeError("DELIVERY_R92_ASOF_MISMATCH:" + key)

        prow = price_results.get(sym) or {}
        if sym not in price_pass or prow.get("status") != "PASS_PRICE_DV30":
            raise RuntimeError("DELIVERY_R92_PRICE_DV30_NOT_PASS:" + key)
        dv30 = (prow.get("info") or {}).get("dv30")
        if x.get("dv30") is None or not close_num(x.get("dv30"), dv30):
            raise RuntimeError("DELIVERY_R92_DV30_BINDING_MISMATCH:" + key)
        if not str(x.get("liquidity") or "").startswith("DV30"):
            raise RuntimeError("DELIVERY_R92_LIQUIDITY_NOT_DV30:" + key)

        mrow = mc_results.get(sym) or {}
        if (
            sym not in primary
            or mrow.get("status") != "MC_PASS_PRIMARY"
            or x.get("mc_class") != "MC_PASS_PRIMARY"
        ):
            raise RuntimeError("DELIVERY_R92_MC_NOT_PRIMARY:" + key)

        frow = final_results.get(key) or {}
        if not (
            frow.get("result") == "PRE_G9_TECH_PASS"
            and frow.get("pre_g9_tech_pass") is True
            and frow.get("technical_hard_pass") is True
            and frow.get("r92_eligible") is True
            and frow.get("state_cap") != "WATCH"
            and frow.get("candidate_legal_review_status") == "PASS"
            and str(frow.get("family") or "").upper() == str(x.get("setup") or "").upper()
        ):
            raise RuntimeError("DELIVERY_R92_FINAL_LOCAL_PROOF_FAIL:" + key)
        if str(x.get("event_status") or "") != str(frow.get("event_status") or ""):
            raise RuntimeError("DELIVERY_R92_EVENT_BINDING_MISMATCH:" + key)
    return t

if not POINTER.exists():
    print("XRAY_DELIVERY_NOOP=NO_POINTER")
    raise SystemExit(0)

p = load_json(POINTER)
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
if s.get("task_id") != TASK:
    raise RuntimeError("DELIVERY_CANONICAL_TASK_MISMATCH")

delivery_keys = set(s.get("delivery_keys") or [])
r92 = s.get("r92") or []
if not isinstance(r92, list):
    raise RuntimeError("DELIVERY_R92_NOT_LIST")

required = [
    "delivery_key", "asof_et", "symbol", "setup", "entry_low", "entry_high",
    "chase_limit", "stop", "r1", "rr_basic", "rr_severe", "regime", "event_status",
    "mc_class", "mc_source", "liquidity", "pass_reason", "g9_status",
    "account_status", "registered_at_utc", "execution", "real_money",
]
eligible = []
seen = set()
for x in r92:
    if not isinstance(x, dict) or x.get("schema") != "XRAY_RESEARCH_CANDIDATE_R92_V1":
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
    if x.get("dv30") is None:
        missing.append("dv30")
    if missing:
        raise RuntimeError("DELIVERY_R92_FIELDS_MISSING:" + ",".join(missing))
    eligible.append(x)

if not eligible:
    print("XRAY_DELIVERY_NOOP=NO_REGISTERED_RESEARCH_CANDIDATE")
    raise SystemExit(0)
if len(eligible) > 3:
    raise RuntimeError("DELIVERY_R92_COUNT_EXCEEDS_MAX3")

chain_exact, current_price, current_history, current_mc_path, current_mc = current_chain_state()
if not chain_exact:
    print("XRAY_DELIVERY_NOOP=CURRENT_DV30_MC_CHAIN_INCOMPLETE")
    raise SystemExit(0)
if str(s.get("asof_et") or "") != str(current_price.get("asof_et") or ""):
    print("XRAY_DELIVERY_NOOP=POINTER_ASOF_NOT_CURRENT")
    raise SystemExit(0)

validate_candidate_local_terminal(
    s, current_price, current_history, current_mc_path, current_mc, eligible
)

# Current candidate safety is independently refreshed by the delivery workflow.
if not OFFICIAL_GUARD.exists():
    raise RuntimeError("DELIVERY_OFFICIAL_HALT_GUARD_MISSING")
g = load_json(OFFICIAL_GUARD)
if g.get("schema") != "XRAY_OFFICIAL_SOURCE_GUARD_V1":
    raise RuntimeError("DELIVERY_OFFICIAL_HALT_GUARD_SCHEMA_FAIL")
sources = g.get("sources") or {}
halts = sources.get("trade_halts") or {}
security = sources.get("security_status") or {}
if halts.get("status") != "PASS":
    raise RuntimeError("DELIVERY_OFFICIAL_HALT_FEED_UNKNOWN")
if security.get("status") != "PASS":
    raise RuntimeError("DELIVERY_OFFICIAL_SECURITY_STATUS_UNKNOWN")
raw_ts = g.get("generated_at_utc")
try:
    gt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - gt.astimezone(timezone.utc)).total_seconds()
except Exception as e:
    raise RuntimeError("DELIVERY_OFFICIAL_HALT_GUARD_TIME_UNPARSEABLE") from e
if age < -60 or age > 900:
    raise RuntimeError("DELIVERY_OFFICIAL_HALT_GUARD_STALE")
safety = g.get("candidate_safety") or {}
veto = set(str(x).upper() for x in (safety.get("veto_symbols") or []))
veto |= set(str(x).upper() for x in (halts.get("active_halt_symbols") or []))
veto |= set(str(x).upper() for x in (security.get("suspension_symbols") or []))
blocked = sorted({str(x.get("symbol") or "").upper() for x in eligible} & veto)
if blocked:
    raise RuntimeError("DELIVERY_OFFICIAL_SAFETY_VETO:" + ",".join(blocked))

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
- DV30: **{x['dv30']}**
- Liquidity: **{x['liquidity']}**
- Pass reason: {x['pass_reason']}
- G9: **{x['g9_status']}**
- Account: **{x['account_status']}**
- Registered UTC: **{x['registered_at_utc']}**
- EXECUTION: **NONE**
- REAL_MONEY: **NO-GO**

Bu bildirim yalnızca canonical durable pointer'a başarılı CAS ile önceden kaydedilmiş
ve exact current terminal tarafından candidate-local olarak doğrulanmış R92 araştırma
adayından üretilmiştir. Unrelated global UNKNOWN adayı bastırmaz; adayın kendi
UNKNOWN/binding/safety kusuru ise fail-closed kalır.
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
