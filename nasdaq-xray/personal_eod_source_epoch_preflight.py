#!/usr/bin/env python3
"""Fail closed before paid/quota-bounded SIP research on mixed Git epochs.

No source requests, vendor bars, orders, C4.17 release or R92 are generated.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = {"root": "orchestrator_state.json",
         "master": "canonical_current_master_manifest.json",
         "price": "canonical_current_price_dv30.json"}


class EpochMismatch(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise EpochMismatch("XRAY_PERSONAL_EOD_PREFLIGHT_" + reason)


def validate(root: dict, master: dict, price: dict, latest: str) -> dict:
    require(all(type(x) is dict for x in (root, master, price)),
            "SOURCE_SCHEMA")
    asofs = [x.get("asof_et") for x in (root, master, price)]
    require(all(type(x) is str and len(x) == 10 for x in asofs),
            "ASOF_INVALID")
    require(asofs[0] == asofs[1] == asofs[2],
            "ROOT_MASTER_PRICE_EPOCH_DRIFT_NO_PROVIDER_CALL")
    require(asofs[0] == latest,
            "LATEST_COMPLETED_SESSION_NOT_BOUND_NO_PROVIDER_CALL")
    for document in (root, master, price):
        require(document.get("execution") == "NONE" and
                document.get("real_money") == "NO-GO",
                "SOURCE_EXECUTION_SAFETY")
    watch = root.get("watch_radar")
    technical = root.get("candidate_technical_funnel")
    require(type(watch) is dict and type(technical) is dict,
            "LOCAL_CANDIDATE_SCOPE_MISSING")
    count = watch.get("watchlist_count")
    rows = watch.get("watchlist")
    require(type(count) is int and count > 0 and type(rows) is list and
            len(rows) == count and
            watch.get("all_eligible_candidates_tracked") is True and
            watch.get("watchlist_cap") is None,
            "LOCAL_SCOPE_INCOMPLETE")
    symbols = [x.get("symbol") for x in rows if type(x) is dict]
    require(len(symbols) == count and all(type(s) is str and s for s in symbols)
            and len(set(symbols)) == count, "LOCAL_SCOPE_DUPLICATE")
    ev, pending = technical.get("evaluated_count"), technical.get("pending_count")
    require(type(ev) is int and type(pending) is int and
            ev >= 0 and pending >= 0 and ev + pending == count,
            "TECHNICAL_PARTITION_INVALID")
    require(watch.get("asof_et") == asofs[0] and
            technical.get("asof_et") == asofs[0],
            "TECHNICAL_ASOF_DRIFT")
    require(master.get("unknown_never_pass") is True and
            price.get("unknown_never_pass") is True,
            "CANONICAL_UNKNOWN_GUARD")
    return {"asof_et": latest, "tracked": count,
            "technical_evaluated": ev, "technical_pending": pending,
            "execution": "NONE", "real_money": "NO-GO",
            "release_authorized": False}


def latest_completed_session() -> str:
    from datetime import datetime, timedelta, timezone
    import pandas_market_calendars as mcal
    now = datetime.now(timezone.utc)
    calendar = mcal.get_calendar("NASDAQ")
    schedule = calendar.schedule(
        start_date=(now.date() - timedelta(days=15)).isoformat(),
        end_date=(now.date() + timedelta(days=1)).isoformat())
    completed = [idx.date().isoformat() for idx, row in schedule.iterrows()
                 if row["market_close"].to_pydatetime() <= now]
    require(bool(completed), "OFFICIAL_COMPLETED_SESSION_UNAVAILABLE")
    return completed[-1]


def selftest() -> None:
    latest = "2026-10-13"
    root = {
        "asof_et": latest, "execution": "NONE", "real_money": "NO-GO",
        "watch_radar": {
            "asof_et": latest, "watchlist_count": 2,
            "watchlist": [{"symbol": "AAA"}, {"symbol": "BBB"}],
            "all_eligible_candidates_tracked": True, "watchlist_cap": None,
        },
        "candidate_technical_funnel": {
            "asof_et": latest, "evaluated_count": 1, "pending_count": 1,
        }
    }
    master = {"asof_et": latest, "execution": "NONE", "real_money": "NO-GO",
              "unknown_never_pass": True}
    price = dict(master)
    assert validate(root, master, price, latest)["tracked"] == 2
    import copy
    def rejected(modify, reason):
        r, m, p = copy.deepcopy((root, master, price))
        modify(r, m, p)
        try:
            validate(r, m, p, latest)
        except EpochMismatch as exc:
            assert reason in str(exc), (reason, str(exc))
        else:
            raise AssertionError("UNSAFE_EPOCH_GATE_PASSED:" + reason)
    rejected(lambda r,m,p: m.update(asof_et="2026-10-12"), "EPOCH_DRIFT")
    rejected(lambda r,m,p: r.update(asof_et="2026-10-12"), "EPOCH_DRIFT")
    rejected(lambda r,m,p: p.update(asof_et="2026-10-12"), "EPOCH_DRIFT")
    rejected(lambda r,m,p: r["watch_radar"].update(watchlist_count=3),
             "LOCAL_SCOPE_INCOMPLETE")
    rejected(lambda r,m,p: r["candidate_technical_funnel"].update(pending_count=2),
             "TECHNICAL_PARTITION_INVALID")
    rejected(lambda r,m,p: r["watch_radar"]["watchlist"].__setitem__(1, {"symbol":"AAA"}),
             "LOCAL_SCOPE_DUPLICATE")
    rejected(lambda r,m,p: p.update(execution="BROKER"), "SOURCE_EXECUTION_SAFETY")
    rejected(lambda r,m,p: m.update(unknown_never_pass=False),
             "CANONICAL_UNKNOWN_GUARD")
    try:
        validate(root, master, price, "2026-10-14")
    except EpochMismatch as exc:
        assert "LATEST_COMPLETED_SESSION_NOT_BOUND" in str(exc)
    else:
        raise AssertionError("STALE_SOURCE_ACCEPTED")
    print("XRAY_PERSONAL_EOD_EPOCH_PREFLIGHT_SELFTEST=PASS_9_NEGATIVES_NO_PROVIDER_NO_R92")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    a = parser.parse_args()
    if a.selftest:
        selftest()
        return
    documents = {name: json.loads((ROOT / filename).read_text())
                 for name, filename in FILES.items()}
    proof = validate(documents["root"], documents["master"],
                     documents["price"], latest_completed_session())
    print("XRAY_PERSONAL_EOD_EPOCH_PREFLIGHT=PASS_" +
          json.dumps(proof, sort_keys=True))


if __name__ == "__main__":
    main()
