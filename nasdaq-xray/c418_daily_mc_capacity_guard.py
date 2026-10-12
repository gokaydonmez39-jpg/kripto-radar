#!/usr/bin/env python3
"""C4.17 shadow-only gate: can a FREE daily provider refresh the FULL MC cohort?

Daily quota sufficiency is necessary, not sufficient: a valid vendor license,
independent upstream lineage, filing-acceptance PIT, all share classes/ADRs,
corporate actions, and evidence propagation remain separate gates.
No network access, credentials, orders, AL promotion, or canonical writes.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT_SCHEMA = "XRAY_C418_DAILY_MC_CAPACITY_GUARD_V1"


def require(condition: bool, label: str) -> None:
    if not condition:
        raise ValueError("C418_DAILY_MC_CAPACITY_FAIL_CLOSED:" + label)


def integer(value: object, *, minimum: int, label: str) -> int:
    require(type(value) is int and value >= minimum, label)
    return value


def strings_unique(rows: object, *, label: str) -> set[str]:
    require(isinstance(rows, list) and all(isinstance(s, str) and s for s in rows), label)
    require(len(rows) == len(set(rows)), label + "_DUPLICATE")
    return set(rows)


def evaluate(master: dict, price: dict, inventory: dict) -> dict:
    require(all(isinstance(x, dict) for x in (master, price, inventory)), "BAD_INPUT")
    asof = master.get("asof_et")
    require(isinstance(asof, str) and dt.date.fromisoformat(asof).isoformat() == asof, "ASOF_DATE")
    require(price.get("asof_et") == asof, "MASTER_PRICE_EPOCH")
    for obj in (master, price, inventory):
        require(obj.get("execution") == "NONE" and obj.get("real_money") == "NO-GO", "FROZEN_EXECUTION")
        require(obj.get("unknown_never_pass") is True, "UNKNOWN_FAIL_CLOSED")
    require(inventory.get("effective_policy") == "C4.17", "POLICY_DRIFT")
    ms = strings_unique(master.get("pass_symbols"), label="MASTER_PASS_SYMBOLS")
    mu = strings_unique(master.get("unknown_symbols"), label="MASTER_UNKNOWN_SYMBOLS")
    ps = strings_unique(price.get("pass_symbols"), label="PRICE_PASS_SYMBOLS")
    require(not ms.intersection(mu), "MASTER_PASS_UNKNOWN_OVERLAP")
    require(ps.issubset(ms) and not ps.intersection(mu), "PRICE_NOT_IDENTITY_PASS")
    require(integer(master.get("pass_count"), minimum=0, label="MASTER_COUNT") == len(ms), "MASTER_COUNT_MISMATCH")
    require(integer(master.get("unknown_count"), minimum=0, label="MASTER_UNKNOWN_COUNT") == len(mu), "MASTER_UNKNOWN_COUNT_MISMATCH")
    require(integer(price.get("pass_count"), minimum=0, label="PRICE_COUNT") == len(ps), "PRICE_COUNT_MISMATCH")
    require(price.get("source_master_count") == len(ms), "PRICE_MASTER_BINDING")
    require(price.get("source_master_queue_hash") == master.get("queue_hash"), "PRICE_MASTER_HASH_BINDING")
    require(integer(price.get("unknown_count"), minimum=0, label="PRICE_UNKNOWN") == 0, "PRICE_UNKNOWN_NOT_ZERO")
    require(integer(price.get("blocked_count"), minimum=0, label="PRICE_BLOCKED") == 0, "PRICE_BLOCKED_NOT_ZERO")
    sources = inventory.get("sources")
    require(isinstance(sources, list) and len(sources) >= 1, "MISSING_SOURCES")
    ids = [s.get("id") if isinstance(s, dict) else None for s in sources]
    require(len(ids) == len(set(ids)) and all(isinstance(s, str) for s in ids), "SOURCE_IDS_INVALID")
    require(ids.count("BUSINESSQUANT") == 1, "BQ_ROW_COUNT")
    bq = sources[ids.index("BUSINESSQUANT")]
    require(bq.get("quota_mode") == "30_REQUESTS_PER_DAY", "BQ_QUOTA_PROVENANCE_CHANGED")
    daily = integer(bq.get("daily_requests"), minimum=1, label="BQ_DAILY_REQUESTS")
    batch = integer(bq.get("max_tickers_per_historic_call"), minimum=1, label="BQ_BATCH")
    require(bq.get("historical_mc_slug") == "market-capitalization-daily", "BQ_METRIC_CHANGED")
    calls = (len(ps) + batch - 1) // batch
    quota_days = (calls + daily - 1) // daily
    sustainable = calls <= daily
    reasons = []
    if not sustainable:
        reasons.append("BQ_HISTORIC_MC_FREE_QUOTA_BELOW_DAILY_FULL_COHORT")
    if bq.get("automated_non_display_primary_license_verified") is not True:
        reasons.append("BQ_PRIMARY_NONDISPLAY_LICENSE_NOT_PROVEN")
    if bq.get("report_date_alone_not_pit") is True:
        reasons.append("BQ_HISTORICAL_MC_ROW_DATE_NOT_FILING_ACCEPTANCE_PIT")
    if bq.get("runner_key_attested") is not True:
        reasons.append("BQ_RUNNER_KEY_NOT_ATTESTED")
    # Entire diagnostic cannot be a PRIMARY MC approval under *any* circumstances.
    return {
        "schema": REPORT_SCHEMA,
        "asof_et": asof,
        "source_cohort_price_pass": len(ps),
        "source_master_identity_pass": len(ms),
        "source_master_identity_unknown": len(mu),
        "provider_rows_unchanged": len(sources),
        "BQ": {
            "daily_free_requests": daily,
            "tickers_per_historical_mc_call": batch,
            "required_full_cohort_calls": calls,
            "maximum_tickers_per_day": daily * batch,
            "minimum_quota_calendar_days": quota_days,
            "full_cohort_daily_refresh_with_this_quota": sustainable,
            "min_days_not_same_session_authority": True,
        },
        "reason_codes": reasons,
        "status": "SHADOW_DAILY_REFRESH_BLOCKED" if reasons else "SHADOW_QUOTA_FEASIBLE_NOT_PRIMARY",
        "can_create_PRIMARY": False,
        "can_register_R92": False,
        "can_enable_G9": False,
        "production_go": False,
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "vendor_raw_data_persisted": False,
    }


def selftest() -> None:
    # Synthetic metadata ONLY; never market bars, share counts or provider facts.
    syms = [f"TEST{i:04d}" for i in range(514)]
    master = {"asof_et": "2026-10-09", "pass_symbols": syms,
              "pass_count": 514, "unknown_symbols": ["UNKNOWN1"], "unknown_count": 1,
              "queue_hash": "a" * 64, "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True}
    price = {"asof_et": "2026-10-09", "pass_symbols": syms[:], "pass_count": 514,
             "source_master_count": 514, "source_master_queue_hash": "a" * 64,
             "unknown_count": 0, "blocked_count": 0, "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True}
    inv = {"effective_policy": "C4.17", "sources": [{"id": "BUSINESSQUANT", "quota_mode": "30_REQUESTS_PER_DAY", "daily_requests": 30,
            "max_tickers_per_historic_call": 5, "historical_mc_slug": "market-capitalization-daily",
            "automated_non_display_primary_license_verified": False, "report_date_alone_not_pit": True,
            "runner_key_attested": False}], "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True}
    r = evaluate(master, price, inv)
    require(r["BQ"]["required_full_cohort_calls"] == 103 and r["BQ"]["minimum_quota_calendar_days"] == 4, "ARITHMETIC_514")
    require(r["BQ"]["maximum_tickers_per_day"] == 150 and not r["BQ"]["full_cohort_daily_refresh_with_this_quota"], "DAILY_QUOTA")
    require(not r["production_go"] and not r["can_create_PRIMARY"] and not r["can_register_R92"], "FALSE_PROMOTION")
    for n in (0, 1, 5, 150, 151, 514, 520):
        mm = copy.deepcopy(master); pp = copy.deepcopy(price)
        pp["pass_symbols"] = mm["pass_symbols"][:min(n, 514)] if n <= 514 else mm["pass_symbols"] + [f"EXTRA{i}" for i in range(n-514)]
        if n > 514: mm["pass_symbols"] = pp["pass_symbols"][:]; mm["pass_count"] = n; pp["source_master_count"] = n
        pp["pass_count"] = n
        res = evaluate(mm, pp, inv)
        require(res["BQ"]["required_full_cohort_calls"] == (n+4)//5, "DYNAMIC_COHORT_ARITHMETIC")
        require(res["can_create_PRIMARY"] is False and res["production_go"] is False, "FALSE_PRIMARY")
    negative = [
        ("MASTER_PASS_UNKNOWN_OVERLAP", lambda m,p,i: m["unknown_symbols"].append(m["pass_symbols"][0])),
        ("MASTER_PRICE_EPOCH", lambda m,p,i: p.update(asof_et="2026-10-08")),
        ("PRICE_NOT_IDENTITY_PASS", lambda m,p,i: p["pass_symbols"].__setitem__(0,"INVALID")),
        ("PRICE_MASTER_HASH_BINDING", lambda m,p,i: p.update(source_master_queue_hash="b"*64)),
        ("PRICE_COUNT_MISMATCH", lambda m,p,i: p.update(pass_count=515)),
        ("PRICE_UNKNOWN_NOT_ZERO", lambda m,p,i: p.update(unknown_count=1)),
        ("PRICE_BLOCKED_NOT_ZERO", lambda m,p,i: p.update(blocked_count=1)),
        ("FROZEN_EXECUTION", lambda m,p,i: p.update(real_money="GO")),
        ("POLICY_DRIFT", lambda m,p,i: i.update(effective_policy="C4.18")),
        ("BQ_BATCH", lambda m,p,i: i["sources"][0].update(max_tickers_per_historic_call=0)),
        ("BQ_DAILY_REQUESTS", lambda m,p,i: i["sources"][0].update(daily_requests=True)),
        ("MISSING_SOURCES", lambda m,p,i: i.update(sources=[])),
        ("BQ_ROW_COUNT", lambda m,p,i: i["sources"][0].update(id="SEC_EDGAR")),
        ("BQ_QUOTA_PROVENANCE_CHANGED", lambda m,p,i: i["sources"][0].update(quota_mode="UNLIMITED")),
    ]
    for code, mutate in negative:
        m,p,i = copy.deepcopy(master),copy.deepcopy(price),copy.deepcopy(inv)
        mutate(m,p,i)
        try: evaluate(m,p,i)
        except ValueError as err:
            require(code in str(err), "WRONG_NEGATIVE_REASON:" + code + ":" + str(err))
        else: raise RuntimeError("UNSAFE_MUTANT_ACCEPTED:" + code)
    print(f"XRAY_C418_DAILY_MC_CAPACITY_SELFTEST=PASS_7_DYNAMIC_14_NEGATIVE_OPTIMIZER_SAFE_NO_PRIMARY")


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", type=Path)
    args=ap.parse_args()
    if args.selftest:
        selftest(); return
    master=json.loads((ROOT / "canonical_current_master_manifest.json").read_text())
    price=json.loads((ROOT / "canonical_current_price_dv30.json").read_text())
    inventory=json.loads((ROOT / "c418_provider_inventory_20261012.json").read_text())
    result=evaluate(master,price,inventory)
    if args.out:
        # Never serialize this diagnostic to a tracked GitHub source directory.
        require(not args.out.resolve().is_relative_to(ROOT.parent.resolve()), "PUBLIC_REPO_OUTPUT_FORBIDDEN")
        args.out.write_text(json.dumps(result,sort_keys=True,indent=2) + "\n")
    print("XRAY_C418_DAILY_MC_CAPACITY=" + result["status"])
    print("XRAY_C418_BQ_REQUIRED_CALLS=" + str(result["BQ"]["required_full_cohort_calls"]))
    print("XRAY_C418_DAILY_MC_NO_PRIMARY_NO_GO=PASS")

if __name__ == "__main__":
    main()
