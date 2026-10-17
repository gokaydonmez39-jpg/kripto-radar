#!/usr/bin/env python3
"""XRAY Omega manual BUY research START kernel: independent, READ-ONLY decision DAG.

Cross-check current official source partitions with verified research receipt.
This module NEVER registers R92, changes canonical artifacts, phones a user,
invokes a provider, promises an AL, integrates a broker, or submits an order.
Any candidate release still requires existing independent delivery_prepare.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMA = "XRAY_OMEGA_BUY_ONLY_START_GATE_V1"
TASK = "6a825366222081918997094d76e6ae46"
POLICY_SHA256 = "68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
FILES = {
    "master": "canonical_current_master_manifest.json",
    "price": "canonical_current_price_dv30.json",
    "history_root": "orchestrator_state.json",
    "history_canonical": "canonical_current_history.json",
    "terminal": "canonical_current_terminal.json",
    "pointer": "chatgpt_canonical_state_v2.json",
    "manual": "manual_decision_policy_v1.json",
    "notify": "notification_channel_policy_v1.json",
}
HARD_GATES = (
    ("price_min_usd", 5),
    ("dv30_min_usd", 50000000),
    ("mc_min_usd", 2000000000),
    ("history_min_daily_bars", 260),
    ("risk_max_percent", 8),
)


def need(ok, code):
    if not ok:
        raise ValueError("OMEGA_START_" + code)


def exact_set(xs):
    return (type(xs) is list and len(xs) == len(set(xs))
            and all(type(x) is str and x and x == x.upper() for x in xs))


def safety(o):
    return (type(o) is dict and o.get("execution") == "NONE"
            and o.get("real_money") == "NO-GO")


def price_partition(px, master):
    """No count-only proof and no unclassified positive/UNKNOWN symbols."""
    if px.get("schema") != "XRAY_CANONICAL_PRICE_DV30_V1":
        return False, "PRICE_SCHEMA"
    rows = px.get("results")
    ps, us, bs = (px.get(k) for k in ("pass_symbols", "unknown_symbols", "blocked_symbols"))
    if not (type(rows) is dict and all(exact_set(g) for g in (ps, us, bs))):
        return False, "PRICE_PARTITION_SET_TYPE"
    p, u, b = set(ps), set(us), set(bs)
    if p & u or p & b or u & b:
        return False, "PRICE_PARTITION_OVERLAP"
    if not all(type(px.get(k)) is int for k in ("pass_count", "unknown_count", "blocked_count")):
        return False, "PRICE_PARTITION_COUNTS_TYPE"
    if (len(p), len(u), len(b)) != (
            px["pass_count"], px["unknown_count"], px["blocked_count"]):
        return False, "PRICE_PARTITION_COUNTS"
    if (type(master.get("queue_total")) is not int
            or len(rows) != master["queue_total"]
            or px.get("source_master_count") != master["queue_total"]
            or px.get("source_master_queue_hash") != master.get("queue_hash")):
        return False, "PRICE_MASTER_QUEUE_EXACT"
    if not all(type(v) is dict and type(v.get("status")) is str for v in rows.values()):
        return False, "PRICE_ROWS"
    if p != {s for s, v in rows.items() if v["status"] == "PASS_PRICE_DV30"}:
        return False, "PRICE_FALSE_PASS"
    if u != {s for s, v in rows.items() if v["status"].startswith("UNKNOWN")}:
        return False, "PRICE_FALSE_UNKNOWN"
    if not b.issubset(rows):
        return False, "PRICE_BLOCKED_NOT_IN_SCOPE"
    if (master.get("asof_et") != px.get("asof_et")
            or not safety(master) or not safety(px)
            or px.get("unknown_never_pass") is not True):
        return False, "PRICE_SOURCE_ASOF_OR_SAFETY"
    return True, "PRICE_PARTITION_COUNTS_HASH_AND_ROWS_CONSISTENT"


def research_receipt(rc, asof):
    """Existing independent 3-artifact receipt is evidence of RESEARCH only."""
    if rc is None:
        return {"available": False, "verified": False, "watch_count": 0,
                "watch_symbols": [], "cohort_count": 0}
    need(type(rc) is dict and rc.get("schema") ==
         "XRAY_PERSONAL_RESEARCH_OPERATIONS_ACCEPTANCE_V1", "RECEIPT_SCHEMA")
    need(safety(rc) and rc.get("asof_et") == asof, "RECEIPT_ASOF_OR_SAFETY")
    need(rc.get("research_all_three_artifacts_same_asof_and_sha") is True
         and rc.get("research_cohort_full_symbolic_partition_checked") is True,
         "RECEIPT_CROSS_ARTIFACT_NOT_PROVEN")
    need(rc.get("c417_primary_price_mc_release_attested") is False
         and rc.get("operational_final_with_real_user_delivery_attested") is False
         and rc.get("registered_R92_count") == 0 and rc.get("orders") == [],
         "RECEIPT_SHADOW_FALSELY_CLAIMS_RELEASE")
    names = rc.get("research_watch_symbols")
    families = rc.get("research_watch_families")
    need(exact_set(names) and type(families) is dict
         and set(families) == set(names)
         and rc.get("research_technical_watch_count") == len(names),
         "RECEIPT_WATCH_SCOPE")
    need(type(rc.get("rth_research_proxy_count")) is int
         and rc["rth_research_proxy_count"] >= len(names),
         "RECEIPT_RESEARCH_SCOPE")
    return {"available": True, "verified": True,
            "watch_count": len(names), "watch_symbols": names,
            "cohort_count": rc["rth_research_proxy_count"],
            "not_primary": True}


def evaluate(pack, expected_asof, receipt=None):
    """Deterministic triage; cannot grant alpha or user notification authority."""
    need(type(expected_asof) is str and len(expected_asof) == 10, "EXPECTED_ASOF")
    need(type(pack) is dict and set(pack) == set(FILES), "EXACT_REQUIRED_FILES")
    m, px, hr, hc, t, ptr, pol, notify = (
        pack[k] for k in ("master", "price", "history_root", "history_canonical",
                          "terminal", "pointer", "manual", "notify"))
    need(all(safety(o) for o in (m, px, hr, hc, t, ptr, pol, notify)),
         "GLOBAL_EXECUTION_LOCK")
    need(m.get("asof_et") == px.get("asof_et") == expected_asof,
         "MASTER_PRICE_MUST_MATCH_COMPLETED_SESSION")
    need(pol.get("schema") == "XRAY_MANUAL_DECISION_RESEARCH_MODE_V1"
         and pol.get("parent_policy_sha256") == POLICY_SHA256
         and all(pol.get("hard_gates", {}).get(k) == v for k, v in HARD_GATES)
         and pol.get("hard_gates", {}).get("history_min_daily_bars") == 260
         and pol.get("unknown_never_pass") is True,
         "MANUAL_C417_THRESHOLDS")
    need(pol.get("broker_access_required") is False
         and pol.get("broker_account_read_required") is False
         and pol.get("broker_trade_access_allowed") is False
         and pol.get("g9", {}).get("mandatory_for_research_signal") is False
         and pol.get("account", {}).get("mandatory_for_research_signal") is False,
         "NO_BROKER_NO_G9_REQUIRED")
    need(notify.get("user_delivery_authority_task_id") == TASK
         or notify.get("user_visible_event_scope") != "VERIFIED_REGISTERED_R92_BUY_ONLY"
         or notify.get("watch_and_early_research_internal_only") is not True
         or notify.get("source_and_data_faults_internal_only") is not True
         or notify.get("dedup_required") is not True
         or notify.get("unknown_never_pass") is not True,
         "ONLY_REGISTERED_AL_NOTIFICATIONS")
    part_ok, part_reason = price_partition(px, m)
    # Fail closed on corrupt partitions. It must NEVER be spun into a repair.
    need(part_ok, part_reason)
    research = research_receipt(receipt, expected_asof)
    s = ptr.get("state_json")
    need(type(s) is dict and s.get("task_id") == TASK,
         "POINTER_CANONICAL_TASK")
    need(ptr.get("schema") == "XRAY_GITHUB_DURABLE_STATE_V3"
         and ptr.get("authority") == "GITHUB_CURRENT_POINTER",
         "POINTER_CANONICAL_AUTHORITY")
    r92 = s.get("r92")
    need(type(r92) is list, "REGISTERED_R92_LIST")
    terminal_current = (t.get("schema") == "XRAY_CANONICAL_CURRENT_TERMINAL_V1"
                        and t.get("asof_et") == expected_asof
                        and s.get("asof_et") == expected_asof)
    history_current = hc.get("asof_et") == expected_asof
    root_current = hr.get("asof_et") == expected_asof
    # A nonempty R92 is NEVER sufficient; independent delivery_prepare must
    # verify MC PRIMARY, Final, event, exact blobs, levels and current halts.
    blockers = []
    if m.get("unknown_count", -1) != 0:
        blockers.append(("P1", "IDENTITY_11_REMAINING", "Resolve official SEC/Nasdaq identities for relevant candidate-local scope"))
    if px.get("unknown_count", -1):
        blockers.append(("P0", "C417_PRICE_UNKNOWN", "Recover exact 30 completed official RTH volume*close for unresolved symbols"))
    if px.get("pass_count", 0) == 0:
        blockers.append(("P0", "NO_CANONICAL_PRICE_PASS", "Prove at least one issuer's exact full PRICE/DV30 record; proxy bound is not enough"))
    if not root_current or hr.get("unknown_count", -1):
        blockers.append(("P0", "HISTORY_ROOT_UNKNOWN", "Verify independent 260 daily and 52 weekly history/issuer continuity"))
    if not history_current:
        blockers.append(("P0", "HISTORY_DOWNSTREAM_STALE", "Regenerate exact same-ASOF canonical history bound to authorized MC"))
    if not terminal_current or t.get("candidate_local_research_pass") is not True:
        blockers.append(("P0", "TERMINAL_OR_POINTER_STALE", "Rebuild same-ASOF candidate-local Final/terminal/pointer after source proof"))
    if not r92:
        blockers.append(("P0", "NO_REGISTERED_R92", "Complete source+event+risk+technical checks then register only genuine R92"))
    if not pol.get("delivery", {}).get("enabled_in_this_shadow", True):
        blockers.append(("P1", "RESEARCH_SHADOW_NOT_USER_DELIVERY",
                         "Keep shadow internal until independent candidate-level delivery acceptance"))
    if notify.get("platform_iphone_receipt_attested") is not True:
        blockers.append(("P2", "DEVICE_DELIVERY_ACK_UNPROVEN",
                         "Test actual device receipt independently; never infer from workflow SUCCESS"))
    # PRIMARY MC cannot be inferred from current research receipt, historical
    # terminal or empty PRICE PASS. Always require independent current bridge.
    blockers.insert(2, ("P0", "CURRENT_PRIMARY_MC_NOT_ATTESTED_BY_THIS_GATE",
                        "Verify exact current PRICE pass set against authorized point-in-time issuer/class PRIMARY MC"))
    priority = {"P0": 0, "P1": 1, "P2": 2}
    blockers.sort(key=lambda x: priority[x[0]])
    names = research["watch_symbols"] if research["verified"] else []
    # Research-only priorities, not a ticker recommendation or investment action.
    return {
        "schema": SCHEMA, "asof_et": expected_asof, "execution": "NONE",
        "real_money": "NO-GO", "unknown_never_pass": True,
        "mode": "PERSONAL_NASDAQ_BUY_ONLY_MANUAL_RESEARCH",
        "research_start": "READY_FOR_SOURCE_REMEDIATION"
                          if root_current and research["verified"]
                          else "SOURCE_OR_CROSS_ARTIFACT_RESEARCH_INCOMPLETE",
        "buy_signal_start": "BLOCKED_INDEPENDENT_CURRENT_R92_PROOF",
        "buy_signal_issued": False, "orders": [], "broker_access_required": False,
        "g9_strict_required": False, "fully_authorized_primary_mc": False,
        "release_authority": "EXISTING_CANONICAL_R92_AND_DELIVERY_PREPARE_ONLY",
        "this_report_is_release_authority": False,
        "canonical": {
            "master_asof": m.get("asof_et"), "master_identity_unknown": m.get("unknown_count"),
            "price_partition_exact": part_ok, "price_pass": px["pass_count"],
            "price_unknown": px["unknown_count"], "history_root_unknown": hr.get("unknown_count"),
            "history_root_asof": hr.get("asof_et"),
            "history_downstream_asof": hc.get("asof_et"),
            "terminal_asof": t.get("asof_et"), "pointer_asof": s.get("asof_et"),
            "registered_r92": len(r92),
        },
        "research": research, "first_external_evidence_gate": "EXACT30_RTH_AND_PRIMARY_MC",
        "focus_research_symbols": names, "focus_is_buy_recommendation": False,
        "blocked_count": len(blockers),
        "ordered_blocker_dag": [
            {"priority": p, "code": code, "required_action": action}
            for p, code, action in blockers
        ],
    }


def selftest():
    def safe(**kw):
        return dict(execution="NONE", real_money="NO-GO", **kw)
    asof = "2026-10-16"
    master = safe(asof_et=asof, queue_total=3, queue_hash="test", unknown_count=1)
    px = safe(schema="XRAY_CANONICAL_PRICE_DV30_V1", asof_et=asof,
              source_master_count=3, source_master_queue_hash="test",
              unknown_never_pass=True, pass_count=1, unknown_count=1,
              blocked_count=0, pass_symbols=["AAA"], unknown_symbols=["BBB"],
              blocked_symbols=[], results={
                  "AAA": {"status":"PASS_PRICE_DV30"},
                  "BBB": {"status":"UNKNOWN"},
                  "CCC": {"status":"FAIL_PRICE"}})
    policy = safe(schema="XRAY_MANUAL_DECISION_RESEARCH_MODE_V1",
                  parent_policy_sha256=POLICY_SHA256,
                  hard_gates=dict(HARD_GATES, history_min_daily_bars=260),
                  unknown_never_pass=True, broker_access_required=False,
                  broker_account_read_required=False, broker_trade_access_allowed=False,
                  g9={"mandatory_for_research_signal":False},
                  account={"mandatory_for_research_signal":False},
                  delivery={"enabled_in_this_shadow":False})
    notify = safe(user_delivery_authority_task_id=TASK,
                  user_visible_event_scope="VERIFIED_REGISTERED_R92_BUY_ONLY",
                  watch_and_early_research_internal_only=True,
                  source_and_data_faults_internal_only=True,
                  dedup_required=True, unknown_never_pass=True,
                  platform_iphone_receipt_attested=False)
    ptr = safe(schema="XRAY_GITHUB_DURABLE_STATE_V3",
               authority="GITHUB_CURRENT_POINTER",
               state_json={"task_id": TASK, "asof_et":"2026-10-07","r92":[]})
    pack={"master": master, "price": px,
          "history_root":safe(asof_et=asof, unknown_count=214),
          "history_canonical":safe(asof_et="2026-10-07"),
          "terminal":safe(schema="XRAY_CANONICAL_CURRENT_TERMINAL_V1",
                          asof_et="2026-10-07", candidate_local_research_pass=False),
          "pointer":ptr,"manual":policy,"notify":notify}
    rc=safe(schema="XRAY_PERSONAL_RESEARCH_OPERATIONS_ACCEPTANCE_V1",
            asof_et=asof, research_all_three_artifacts_same_asof_and_sha=True,
            research_cohort_full_symbolic_partition_checked=True,
            c417_primary_price_mc_release_attested=False,
            operational_final_with_real_user_delivery_attested=False,
            registered_R92_count=0, orders=[],
            research_watch_symbols=["AAA"], research_watch_families={"AAA":["B"]},
            research_technical_watch_count=1, rth_research_proxy_count=2)
    out=evaluate(pack, asof, rc)
    need(out["research_start"]=="READY_FOR_SOURCE_REMEDIATION"
         and out["canonical"]["price_unknown"]==1
         and out["canonical"]["price_pass"]==1
         and not out["buy_signal_issued"] and out["orders"] == []
         and not out["broker_access_required"] and not out["g9_strict_required"],
         "SELFTEST_BASELINE")
    mutations=[
        ("PRICE_OVERLAP",lambda p,r:p["price"]["unknown_symbols"].append("AAA")),
        ("PRICE_FALSE_PASS",lambda p,r:p["price"]["results"]["AAA"].update(status="UNKNOWN")),
        ("PRICE_FALSE_UNKNOWN",lambda p,r:p["price"]["unknown_symbols"].remove("BBB")),
        ("PRICE_COUNT_FORGERY",lambda p,r:p["price"].update(unknown_count=2)),
        ("PRICE_ROW_FORGERY",lambda p,r:p["price"]["results"].pop("BBB")),
        ("PRICE_QUEUE_HASH",lambda p,r:p["price"].update(source_master_queue_hash="bad")),
        ("ASOF_DRIFT",lambda p,r:p["master"].update(asof_et="2026-10-15")),
        ("POLICY_PRICE_WEAKENED",lambda p,r:p["manual"]["hard_gates"].update(price_min_usd=1)),
        ("POLICY_MC_WEAKENED",lambda p,r:p["manual"]["hard_gates"].update(mc_min_usd=100)),
        ("POLICY_DV30_WEAKENED",lambda p,r:p["manual"]["hard_gates"].update(dv30_min_usd=20)),
        ("POLICY_RISK_WEAKENED",lambda p,r:p["manual"]["hard_gates"].update(risk_max_percent=20)),
        ("BROKER_REQUIRED",lambda p,r:p["manual"].update(broker_access_required=True)),
        ("ACCOUNT_REQUIRED",lambda p,r:p["manual"]["account"].update(mandatory_for_research_signal=True)),
        ("G9_REQUIRED",lambda p,r:p["manual"]["g9"].update(mandatory_for_research_signal=True)),
        ("WATCH_ALERTS_ENABLED",lambda p,r:p["notify"].update(watch_and_early_research_internal_only=False)),
        ("ORDER_ENABLED",lambda p,r:p["pointer"].update(execution="TRADE")),
        ("FAKE_R92_IN_RESEARCH",lambda p,r:r.update(registered_R92_count=1)),
        ("FAKE_MC_PASS_IN_RESEARCH",lambda p,r:r.update(c417_primary_price_mc_release_attested=True)),
        ("RESEARCH_ASOF_DRIFT",lambda p,r:r.update(asof_et="2026-10-15")),
        ("RESEARCH_SCOPE_FORGERY",lambda p,r:r.update(research_technical_watch_count=999)),
    ]
    for label,mutate in mutations:
        p,r=copy.deepcopy(pack),copy.deepcopy(rc)
        mutate(p,r)
        try:
            evaluate(p,asof,r)
        except (ValueError,TypeError):
            continue
        raise AssertionError("OMEGA_START_FALSE_POSITIVE_"+label)
    print("XRAY_OMEGA_BUY_START_SELFTEST=PASS_20_ADVERSARIAL_NEGATIVES_NO_AL_NO_BROKER")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--asof")
    ap.add_argument("--research-receipt",type=Path)
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:
        selftest()
        return
    need(args.asof is not None, "OFFICIAL_COMPLETED_SESSION_REQUIRED")
    pack={k:json.loads((ROOT/f).read_text(encoding="utf-8"))
          for k,f in FILES.items()}
    rc=json.loads(args.research_receipt.read_text(encoding="utf-8")) if args.research_receipt else None
    obj=evaluate(pack,args.asof,rc)
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(obj,sort_keys=True,ensure_ascii=False,
                  separators=(",",":"),allow_nan=False)+"\n",encoding="utf-8")
    print("XRAY_OMEGA_RESEARCH_START="+obj["research_start"])
    print("XRAY_OMEGA_BUY_SIGNAL_START="+obj["buy_signal_start"])
    print("XRAY_OMEGA_CANONICAL_PRIMARY_PRICE_PASS="+str(obj["canonical"]["price_pass"]))
    print("XRAY_OMEGA_REAL_REGISTERED_R92="+str(obj["canonical"]["registered_r92"]))
    print("XRAY_OMEGA_BLOCKER_COUNT="+str(obj["blocked_count"]))
    print("XRAY_OMEGA_AUTO_ORDERS=FORBIDDEN")


if __name__ == "__main__":
    main()
