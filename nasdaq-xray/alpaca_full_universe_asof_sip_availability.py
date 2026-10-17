#!/usr/bin/env python3
"""Independent delayed historical SIP exact-ASOF coverage census, no trading.

Reads the current, integrity-bound SINA identity queue, not the current root
watch (which may be empty while Sina publishes its latest daily close).
Measures daily bar presence only, NEVER history/DV30/MC/C4.17/AL/R92 PASS.
No OHLCV, price, volume or vendor response may be written to the report.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

from source_epoch_freshness_guard import last_complete_session

ROOT = Path(__file__).resolve().parent
BATCH = 100
MAX_REQUESTS = 180
SCHEMA = "XRAY_ALPACA_PERSONAL_UNIVERSE_ASOF_SIP_COVERAGE_V1"
NY = ZoneInfo("America/New_York")


def need(ok, reason):
    if not ok:
        raise ValueError("XRAY_PERSONAL_FULL_UNIVERSE_SIP_" + reason)


class RequestBudget:
    """Shared fail-closed transport-attempt budget: debit BEFORE every HTTP call."""
    def __init__(self, limit):
        need(type(limit) is int and limit > 0, "CALL_BUDGET_LIMIT_INVALID")
        self.limit = limit
        self.used = 0

    def debit(self):
        need(self.used < self.limit, "CALL_BUDGET")
        self.used += 1


def sha(symbols):
    return hashlib.sha256("\n".join(symbols).encode()).hexdigest()


def scope(sina, root, now):
    need(sina.get("execution") == root.get("execution") == "NONE" and
         sina.get("real_money") == root.get("real_money") == "NO-GO",
         "READ_ONLY_SOURCE")
    asof = last_complete_session(now)
    need(sina.get("asof_et") == root.get("asof_et") == asof,
         "SOURCE_LATEST_COMPLETED_EPOCH_REQUIRED")
    q = sina.get("queue")
    need(type(q) is list and len(q) > 0 and
         all(type(s) is str and s for s in q) and
         q == sorted(set(q)) and
         len(q) == sina.get("queue_total") == root.get("queue_total") and
         sha(q) == sina.get("queue_hash") == root.get("queue_hash"),
         "EXACT_FULL_QUEUE_SHA_OR_COUNT")
    need(sina.get("unknown_never_pass") is True,
         "SOURCE_UNKNOWN_SAFETY")
    return asof, q


def validate_one(bar, asof):
    """Presence witness only. Does NOT establish official RTH dollar volume."""
    if type(bar) is not dict:
        return False
    try:
        raw = bar["t"]
        stamp = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        c, v = bar["c"], bar["v"]
        if stamp.tzinfo is None or (type(c) not in (int, float)) or (
                type(v) not in (int, float)):
            return False
        return (stamp.astimezone(NY).date().isoformat() == asof and
                math.isfinite(c) and c > 0 and math.isfinite(v) and
                v > 0 and float(v).is_integer())
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def historical_request_window(asof, now):
    """Basic historical SIP: never request into the future or last 15 minutes.

    Use the actual official exchange close, including 13:00 ET early closes.
    An end at 23:59 ET can be IN THE FUTURE and yield HTTP 403 on Basic.
    """
    need(now.tzinfo is not None, "NAIVE_CLOCK")
    now = now.astimezone(dt.timezone.utc)
    expected = last_complete_session(now)
    need(asof == expected, "STALE_EPOCH_FOR_PROVIDER_CALL")
    rows = mcal.get_calendar("NASDAQ").schedule(
        start_date=asof, end_date=asof)
    need(len(rows) == 1, "OFFICIAL_SESSION_NOT_FOUND")
    close = rows.iloc[0]["market_close"].to_pydatetime()
    start = dt.datetime.combine(dt.date.fromisoformat(asof), dt.time(), NY)
    end = close + dt.timedelta(minutes=5)
    need(start < end and end <= now-dt.timedelta(minutes=15),
         "BASIC_HISTORICAL_15M_DELAY_HORIZON")
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


def query_sip(symbols, asof, key, secret, opener=urllib.request.urlopen,
              page_cap=8, budget=None, window_fn=historical_request_window):
    """One bounded multi-symbol request family; honour all returned pages."""
    need(bool(key and secret), "ALPACA_CREDENTIALS_NOT_CONFIGURED")
    need(budget is None or isinstance(budget, RequestBudget),
         "CALL_BUDGET_OBJECT_INVALID")
    start, end = window_fn(asof, dt.datetime.now(dt.timezone.utc))
    base = "https://data.alpaca.markets/v2/stocks/bars"
    pages, output, token = 0, {}, None
    while True:
        need(pages < page_cap, "PAGINATION_BOUND_EXCEEDED")
        params = {"symbols": ",".join(symbols), "timeframe": "1Day",
                  "start": start, "end": end, "feed": "sip",
                  "adjustment": "raw", "limit": 10000}
        if token is not None:
            params["page_token"] = token
        url = base + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
            "User-Agent": "xray-personal-asof-coverage/1.0"})
        if budget is not None:
            budget.debit()
        with opener(req, timeout=24) as response:
            doc = json.loads(response.read())
        need(type(doc) is dict and type(doc.get("bars")) is dict,
             "INVALID_SIP_RESPONSE")
        need(set(doc["bars"]).issubset(set(symbols)), "FOREIGN_SYMBOL_IN_RESPONSE")
        for sym, bars in doc["bars"].items():
            need(type(bars) is list, "INVALID_BARS_STRUCTURE")
            if sym in output:
                output[sym].extend(bars)
            else:
                output[sym] = list(bars)
        pages += 1
        new_token = doc.get("next_page_token")
        need(new_token is None or
             (type(new_token) is str and bool(new_token) and new_token != token),
             "INVALID_PAGE_TOKEN")
        if new_token is None:
            break
        token = new_token
    return output, pages


def classify(asof, symbols, provider, batch=BATCH):
    """Full partition, provider outages explicit UNKNOWN, no false sources."""
    need(type(batch) is int and 1 <= batch <= BATCH, "BATCH_SIZE")
    labels = {}
    requests, circuit = 0, False
    reason = None
    for offset in range(0, len(symbols), batch):
        group = symbols[offset:offset + batch]
        if circuit:
            for sym in group:
                labels[sym] = reason
            continue
        try:
            bars, pages = provider(group, asof)
            need(type(bars) is dict and type(pages) is int and
                 1 <= pages <= 8, "PROVIDER_SCHEMA")
            requests += pages
            need(requests <= MAX_REQUESTS, "CALL_BUDGET")
            need(set(bars).issubset(set(group)), "FOREIGN_PROVIDER_SYMBOL")
            for sym in group:
                rows = bars.get(sym, [])
                need(type(rows) is list, "BARS_NOT_LIST")
                good = [row for row in rows if validate_one(row, asof)]
                labels[sym] = (
                    "OBSERVED_SIP_DAILY_ASOF_SHADOW"
                    if len(good) == 1 and len(rows) == 1
                    else "UNKNOWN_DAILY_MISSING_OR_INTEGRITY")
        except urllib.error.HTTPError as e:
            # Bad request for one group does not prove the next group empty.
            # Auth, throttle, and server trouble still stop the entire run.
            local = e.code in (400, 404, 422)
            reason = ("UNKNOWN_SIP_HTTP_429_STOP" if e.code == 429 else
                      "UNKNOWN_SIP_HTTP_" + str(e.code))
            if not local:
                circuit = True
            for sym in group:
                labels[sym] = reason
        except (ValueError, TypeError) as e:
            # Invalid provider payload affects this batch only; never PASS.
            # Exceeding the shared call budget must stop every further call.
            budget = isinstance(e, ValueError) and (
                str(e) == "XRAY_PERSONAL_FULL_UNIVERSE_SIP_CALL_BUDGET")
            reason = ("UNKNOWN_SIP_CALL_BUDGET_STOP" if budget else
                      "UNKNOWN_SIP_SOURCE_OR_INTEGRITY_" + type(e).__name__)
            if budget:
                circuit = True
            for sym in group:
                labels[sym] = reason
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # Transport outage: stop rather than burning repeated credits.
            reason = "UNKNOWN_SIP_SOURCE_OR_INTEGRITY_" + type(e).__name__
            circuit = True
            for sym in group:
                labels[sym] = reason
    need(set(labels) == set(symbols) and len(labels) == len(symbols),
         "PARTITION_INCOMPLETE")
    return labels, requests, circuit


def census(state, root, now, provider):
    asof, names = scope(state, root, now)
    labels, calls, circuit = classify(asof, names, provider)
    counts = dict(sorted(collections.Counter(labels.values()).items()))
    need(sum(counts.values()) == len(names), "COUNT_PARTITION")
    return {
        "schema": SCHEMA, "asof_et": asof,
        "source": "ALPACA_HISTORICAL_DELAYED_SIP_1DAY",
        "source_sina_queue_sha256": sha(names),
        "source_sina_queue_count": len(names),
        "measured_scope_count": len(labels),
        "all_scope_classified": True,
        "classification_counts": counts,
        "source_circuit_breaker_open": circuit,
        "upstream_page_requests": calls,
        "symbol_classifications": dict(sorted(labels.items())),
        "source_bar_presence_is_not_canonical_260_52_or_dv30": True,
        "no_vendor_ohlcv_persisted": True,
        "no_canonical_promotion": True,
        "registered_R92_count": 0,
        "execution": "NONE", "real_money": "NO-GO",
        "status": "PERSONAL_SIP_DAILY_SOURCE_COVERAGE_RESEARCH_ONLY",
    }


def selftest():
    asof = "2026-10-14"
    now = dt.datetime(2026, 10, 14, 22, 0, tzinfo=dt.timezone.utc)
    names = ["AAPL", "BSP", "NVDA"]
    root = {"asof_et": asof, "queue_total": 3,
            "queue_hash": sha(names), "execution": "NONE", "real_money": "NO-GO"}
    state = dict(root, queue=names, unknown_never_pass=True)
    need(scope(state, root, now)[1] == names, "POSITIVE_SCOPE")
    def record(c=200, v=100000):
        return {"t": asof + "T04:00:00Z", "c": c, "v": v}
    def fake(sub, day):
        return {"AAPL": [record()], "NVDA": [record()]}, 1
    out = census(state, root, now, fake)
    need(out["classification_counts"] == {
        "OBSERVED_SIP_DAILY_ASOF_SHADOW": 2,
        "UNKNOWN_DAILY_MISSING_OR_INTEGRITY": 1} and
        out["registered_R92_count"] == 0 and
        out["upstream_page_requests"] == 1, "POSITIVE_NO_ALPHA")
    req_start, req_end = historical_request_window(asof, now)
    need(req_end.startswith("2026-10-14T20:05:00+00:00")
         and req_start.startswith("2026-10-14T00:00:00-04:00"),
         "NO_FUTURE_END_HORIZON")
    need(validate_one(record(v=1.5), asof) is False and
         validate_one(record(c=-1), asof) is False and
         validate_one({"t": "2026-10-13T04:00:00Z", "c": 1, "v": 1}, asof)
         is False, "FRACTIONAL_STALE_NEGATIVES")
    def negative(gate, value):
        try:
            gate()
        except ValueError as e:
            need(value in str(e), "NEGATIVE_REASON_" + value)
        else:
            raise AssertionError("UNSAFE_SCOPE_ACCEPTED_" + value)
    negative(lambda: scope(dict(state, queue=["AAPL", "NVDA", "BSP"]),
                           root, now), "EXACT_FULL_QUEUE")
    negative(lambda: scope(state, dict(root, asof_et="2026-10-13"),
                           now), "SOURCE_LATEST")
    negative(lambda: scope(state, root, dt.datetime(
        2026, 10, 15, 22, 0, tzinfo=dt.timezone.utc)), "SOURCE_LATEST")
    negative(lambda: scope(dict(state, unknown_never_pass=False),
                           root, now), "SOURCE_UNKNOWN")
    negative(lambda: scope(state, dict(root, execution="BROKER"),
                           now), "READ_ONLY")
    def limited(sub, day):
        raise urllib.error.HTTPError("https://example.invalid", 429,
                                     "limited", {}, None)
    limited_result = census(state, root, now, limited)
    need(limited_result["classification_counts"] ==
         {"UNKNOWN_SIP_HTTP_429_STOP": 3} and
         limited_result["source_circuit_breaker_open"], "HTTP429_FAIL_CLOSED")
    foreign_labels, foreign_calls, foreign_circuit = classify(
        asof, names, lambda sub, day: ({"OUTSIDE": [record()]}, 1))
    need(foreign_circuit is False and foreign_calls == 1 and
         set(foreign_labels.values()) ==
             {"UNKNOWN_SIP_SOURCE_OR_INTEGRITY_ValueError"},
         "FOREIGN_SYMBOL_LOCAL_UNKNOWN")
    four = ["AAPL","BSP","NVDA","QQQ"]
    good = lambda sub,day: ({sym:[record()] for sym in sub},1)
    batches = []
    def broken_first(sub,day):
        batches.append(tuple(sub))
        if "AAPL" in sub: raise ValueError("bad provider payload")
        return good(sub,day)
    isolated,used,stopped = classify(asof,four,broken_first,batch=2)
    need(not stopped and used == 1 and len(batches) == 2
         and isolated["AAPL"] == isolated["BSP"] ==
             "UNKNOWN_SIP_SOURCE_OR_INTEGRITY_ValueError"
         and isolated["NVDA"] == isolated["QQQ"] ==
             "OBSERVED_SIP_DAILY_ASOF_SHADOW",
         "SCHEMA_FAILURE_MUST_NOT_ERASE_OTHER_BATCH")
    def bad_request(sub,day):
        if "AAPL" in sub:
            raise urllib.error.HTTPError("https://example.invalid",400,
                                        "bad one batch",{},None)
        return good(sub,day)
    h400,used,stopped = classify(asof,four,bad_request,batch=2)
    need(not stopped and used == 1
         and h400["AAPL"] == "UNKNOWN_SIP_HTTP_400"
         and h400["NVDA"] == "OBSERVED_SIP_DAILY_ASOF_SHADOW",
         "HTTP400_BATCH_ISOLATION")
    def denied(sub,day):
        raise urllib.error.HTTPError("https://example.invalid",403,
                                    "denied",{},None)
    auth,used,stopped = classify(asof,four,denied,batch=2)
    need(stopped and used == 0 and set(auth.values()) ==
         {"UNKNOWN_SIP_HTTP_403"},"AUTH403_GLOBAL_STOP")
    def unavailable(sub,day):
        raise urllib.error.URLError("endpoint unavailable")
    transport,used,stopped = classify(asof,four,unavailable,batch=2)
    need(stopped and used == 0 and set(transport.values()) ==
         {"UNKNOWN_SIP_SOURCE_OR_INTEGRITY_URLError"},
         "NETWORK_GLOBAL_STOP")
    global MAX_REQUESTS
    old_cap = MAX_REQUESTS
    try:
        MAX_REQUESTS = 1
        def too_many(sub,day):
            return good(sub,day) if "AAPL" in sub else (
                good(sub,day)[0],2)
        budget,used,stopped = classify(asof,four,too_many,batch=2)
        need(stopped and used == 3
             and budget["AAPL"] == "OBSERVED_SIP_DAILY_ASOF_SHADOW"
             and budget["QQQ"] == "UNKNOWN_SIP_CALL_BUDGET_STOP",
             "BUDGET_EXHAUSTION_GLOBAL_STOP")
    finally:
        MAX_REQUESTS = old_cap
    need(out["no_vendor_ohlcv_persisted"] is True and
         all("c" not in str(v) for v in out["symbol_classifications"].values()
             if False), "NO_RAW_VENDOR")
    from io import BytesIO
    attempts = []
    def fake_http(req, timeout):
        attempts.append(req.full_url)
        if len(attempts) == 1:
            response = {"bars": {"AAPL": [record()]},
                        "next_page_token": "next"}
        else:
            response = {"bars": {}, "next_page_token": None}
        return BytesIO(json.dumps(response).encode("utf-8"))
    fake_window = lambda day, moment: (
        "2026-10-14T00:00:00-04:00", "2026-10-14T20:05:00+00:00")
    one = RequestBudget(1)
    negative(lambda: query_sip(["AAPL"], asof, "TEST_ID", "TEST_SECRET",
                                opener=fake_http, page_cap=3, budget=one,
                                window_fn=fake_window), "CALL_BUDGET")
    need(one.used == 1 and len(attempts) == 1,
         "SECOND_PAGE_MUST_NOT_SPEND_PAST_HARD_CAP")
    attempts.clear()
    two = RequestBudget(2)
    rows, pages = query_sip(["AAPL"], asof, "TEST_ID", "TEST_SECRET",
                            opener=fake_http, page_cap=3, budget=two,
                            window_fn=fake_window)
    need(two.used == pages == 2 and len(attempts) == 2 and
         len(rows["AAPL"]) == 1, "TWO_PAGE_ATTEMPTS_EXACT")
    negative(lambda: RequestBudget(True), "CALL_BUDGET_LIMIT_INVALID")
    failed = RequestBudget(1)
    def failed_http(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 403, "denied", {}, None)
    try:
        query_sip(["AAPL"], asof, "TEST_ID", "TEST_SECRET",
                  opener=failed_http, budget=failed, window_fn=fake_window)
    except urllib.error.HTTPError:
        need(failed.used == 1, "HTTP403_COUNTS_TOWARD_QUOTA")
    else:
        raise AssertionError("HTTP403_NOT_RAISED")
    print("XRAY_PERSONAL_SIP_HTTP_ATTEMPT_BUDGET=PASS_2PAGE_HARD_CAP_AND_HTTP403_COUNTS")
    print("XRAY_PERSONAL_FULL_UNIVERSE_SIP_SELFTEST=PASS_BATCH_SCHEMA_HTTP400_ISOLATION_QUOTA_AUTH_TRANSPORT_FAIL_CLOSE")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    need(a.out is not None and
         not a.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "REPO_WRITES_FORBIDDEN")
    state = json.loads((ROOT / "sina_state.json").read_text())
    root = json.loads((ROOT / "orchestrator_state.json").read_text())
    key = os.getenv("XRAY_ALPACA_DATA_KEY_ID")
    secret = os.getenv("XRAY_ALPACA_DATA_SECRET_KEY")
    now = dt.datetime.now(dt.timezone.utc)
    budget = RequestBudget(MAX_REQUESTS)
    def provider(sub, asof):
        return query_sip(sub, asof, key, secret, budget=budget)
    result = census(state, root, now, provider)
    completed_pages = result["upstream_page_requests"]
    need(type(completed_pages) is int and
         0 <= completed_pages <= budget.used <= MAX_REQUESTS,
         "HTTP_ATTEMPT_ACCOUNTING_INVALID")
    result["upstream_completed_page_requests"] = completed_pages
    result["upstream_page_requests"] = budget.used
    result["upstream_failed_or_unclassified_page_attempts"] = (
        budget.used - completed_pages)
    a.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("XRAY_PERSONAL_FULL_UNIVERSE_SIP_COVERAGE=" +
          json.dumps({"asof_et": result["asof_et"],
                      "scope": result["source_sina_queue_count"],
                      "counts": result["classification_counts"],
                      "page_requests": result["upstream_page_requests"],
                      "status": result["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()
