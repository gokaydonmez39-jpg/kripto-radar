#!/usr/bin/env python3
"""NASDAQ SWING X-RAY external hard-gate stage V4.
Identity authority: fresh NasdaqTrader directory + deterministic explicit type exclusions.
OHLCV accelerator: Eastmoney direct NASDAQ history (market id 105).
Research/forward-test only. EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import random
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas_market_calendars as mcal

TASK_ID = "6a825366222081918997094d76e6ae46"
BUILD = "2026-10-01.6"
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
HIST_URL = "https://63.push2his.eastmoney.com/api/qt/stock/kline/get"
ROOT = Path(__file__).resolve().parent
STATE = ROOT / "eastmoney_state.json"
CAND = ROOT / "market_candidates.json"

NEW_PER_RUN = int(os.getenv("XRAY_EM_HISTORY_BATCH", "30"))
RETRY_PER_RUN = int(os.getenv("XRAY_EM_RETRY_BATCH", "10"))
WORKERS = int(os.getenv("XRAY_EM_HISTORY_WORKERS", "2"))
MAX_ATTEMPTS = int(os.getenv("XRAY_EM_MAX_ATTEMPTS", "4"))
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

TYPE_PATTERNS = [
    ("WARRANT", re.compile(r"\bwarrants?\b", re.I)),
    ("RIGHT", re.compile(r"\brights?\b", re.I)),
    ("UNIT", re.compile(r"\bunits?\b", re.I)),
    ("PREFERRED", re.compile(r"\bpreferred\b|\bpreference\b", re.I)),
    ("DEBT", re.compile(r"\bsenior notes?\b|\bsubordinated notes?\b|\bnotes? due\b|\bdebentures?\b|\bbonds?\b", re.I)),
    ("ETN", re.compile(r"\betn\b|exchange[- ]traded notes?", re.I)),
    ("FUND", re.compile(r"\bfund\b", re.I)),
]

def sha_lines(items):
    return hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()

def request_bytes(url, headers=None, timeout=35, retries=3):
    last = None
    hdr = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
    if headers:
        hdr.update(headers)
    for k in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            last = exc
            time.sleep(0.7 * (k + 1) + random.uniform(0.1, 0.45))
    raise last

def get_text(url, headers=None, timeout=35, retries=3):
    return request_bytes(url, headers, timeout, retries).decode("utf-8")

def get_json(url, params=None, headers=None, timeout=45, retries=3):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    return json.loads(get_text(url, headers, timeout, retries))

def official_nasdaq():
    text = get_text(NASDAQ_URL)
    lines = [line.strip("\r") for line in text.splitlines() if line.strip()]
    footer = next((line for line in reversed(lines) if line.startswith("File Creation Time:")), None)
    body = "\n".join(line for line in lines if not line.startswith("File Creation Time:"))
    rows = list(csv.DictReader(io.StringIO(body), delimiter="|"))

    included = {}
    excluded = {}
    for row in rows:
        symbol = (row.get("Symbol") or "").strip().upper()
        security_name = (row.get("Security Name") or "").strip()
        if not symbol:
            continue

        reason = None
        if row.get("Test Issue") != "N":
            reason = "TEST_ISSUE"
        elif row.get("ETF") == "Y":
            reason = "ETF"
        elif row.get("NextShares") == "Y":
            reason = "NEXTSHARES"
        else:
            for label, pattern in TYPE_PATTERNS:
                if pattern.search(security_name):
                    reason = label
                    break

        if reason:
            excluded[symbol] = {"reason": reason, "security_name": security_name}
        else:
            included[symbol] = security_name

    if not footer or not included:
        raise RuntimeError("NASDAQ_DIRECTORY_INVALID")
    return included, excluded, footer

def completed_sessions():
    calendar = mcal.get_calendar("NASDAQ")
    now = datetime.now(timezone.utc)
    schedule = calendar.schedule(
        start_date=(now.date() - timedelta(days=900)).isoformat(),
        end_date=(now.date() + timedelta(days=1)).isoformat(),
    )
    sessions = []
    for idx, row in schedule.iterrows():
        if row["market_close"].to_pydatetime() <= now:
            sessions.append(idx.date().isoformat())
    if len(sessions) < 260:
        raise RuntimeError("CALENDAR_TOO_SHORT")
    return sessions[-520:], sessions[-1], sessions[-20:]

def parse_hist(symbol, asof, expected20):
    params = {
        "secid": "105." + symbol,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "0",
        "beg": "20200101",
        "end": "20500000",
        "lmt": "2000",
    }
    try:
        time.sleep(random.uniform(0.06, 0.20))
        payload = get_json(
            HIST_URL,
            params=params,
            headers={"Referer": "https://quote.eastmoney.com/"},
            timeout=12,
            retries=2,
        )
        klines = ((payload.get("data") or {}).get("klines") or [])
        by_date = {}
        for line in klines:
            parts = line.split(",")
            if len(parts) < 7:
                continue
            day = parts[0]
            try:
                close = float(parts[2])
                volume = float(parts[5])
            except Exception:
                continue
            if (
                day <= asof
                and close > 0
                and volume > 0
                and math.isfinite(close)
                and math.isfinite(volume)
            ):
                by_date[day] = (close, volume)

        if asof not in by_date:
            return "UNKNOWN_STATIC", "ASOF_MISSING"

        missing = [day for day in expected20 if day not in by_date]
        if missing:
            return "UNKNOWN_STATIC", {"reason": "EXACT20_MISSING", "dates": missing}

        price = by_date[asof][0]
        dollar_volumes = sorted(by_date[day][0] * by_date[day][1] for day in expected20)
        dv20 = (dollar_volumes[9] + dollar_volumes[10]) / 2.0
        bars = len(by_date)
        info = {
            "price": price,
            "dv20": dv20,
            "bars": bars,
            "secid": "105." + symbol,
        }

        if price <= 10:
            return "FAIL_PRICE", info
        if dv20 < 50_000_000:
            return "FAIL_DV20", info
        if bars < 260:
            return "FAIL_HISTORY", info
        return "PASS", info
    except Exception as exc:
        return "UNKNOWN_RETRY", type(exc).__name__ + ":" + str(exc)[:160]

def load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def atomic_write(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)

def exclusion_counts(excluded):
    out = {}
    for value in excluded.values():
        reason = value["reason"]
        out[reason] = out.get(reason, 0) + 1
    return dict(sorted(out.items()))

def build_state(queue, security_names, excluded, footer, asof, expected20):
    excluded_serial = [
        symbol + "|" + excluded[symbol]["reason"]
        for symbol in sorted(excluded)
    ]
    return {
        "schema": "XRAY_EASTMONEY_RESUMABLE_V4",
        "build": BUILD,
        "task_id": TASK_ID,
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "source": "EASTMONEY_HISTORY_ACCELERATOR_NOT_G9",
        "identity_authority": "NASDAQTRADER_EXPLICIT_TYPE_FILTER_V1",
        "official_footer": footer,
        "asof_et": asof,
        "expected20": expected20,
        "queue": queue,
        "queue_hash": sha_lines(queue),
        "queue_total": len(queue),
        "security_names": {symbol: security_names[symbol] for symbol in queue},
        "explicit_excluded_count": len(excluded),
        "explicit_excluded_hash": sha_lines(excluded_serial),
        "explicit_excluded_reason_counts": exclusion_counts(excluded),
        "cursor": 0,
        "results": {},
        "status": "HISTORY_PARTIAL",
    }

def count_results(results):
    counts = {}
    for result in results.values():
        status = result.get("status")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))

def main():
    security_names, excluded, footer = official_nasdaq()
    _, asof, expected20 = completed_sessions()
    queue = sorted(security_names)
    queue_hash = sha_lines(queue)

    state = load_json(STATE)
    if (
        state.get("schema") != "XRAY_EASTMONEY_RESUMABLE_V4"
        or state.get("queue_hash") != queue_hash
        or state.get("asof_et") != asof
    ):
        state = build_state(queue, security_names, excluded, footer, asof, expected20)

    results = state.setdefault("results", {})

    retry_symbols = [
        symbol
        for symbol in sorted(results)
        if results[symbol].get("status") == "UNKNOWN_RETRY"
        and int(results[symbol].get("attempts", 0)) < MAX_ATTEMPTS
    ][:RETRY_PER_RUN]

    start = int(state.get("cursor", 0))
    end = min(start + NEW_PER_RUN, len(queue))
    new_symbols = queue[start:end]

    work = []
    seen = set()
    for symbol in retry_symbols + new_symbols:
        if symbol not in seen:
            seen.add(symbol)
            work.append(symbol)

    run_results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(parse_hist, symbol, asof, expected20): symbol
            for symbol in work
        }
        for future in as_completed(futures):
            symbol = futures[future]
            status, info = future.result()
            run_results.append((symbol, status, info))

    for symbol, status, info in run_results:
        previous = results.get(symbol) or {}
        attempts = int(previous.get("attempts", 0)) + 1
        if status == "UNKNOWN_RETRY" and attempts >= MAX_ATTEMPTS:
            status = "UNKNOWN_RETRY_EXHAUSTED"
        results[symbol] = {
            "status": status,
            "info": info,
            "attempts": attempts,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    state["cursor"] = end
    state["processed_new_this_run"] = len(new_symbols)
    state["processed_retry_this_run"] = len(retry_symbols)
    state["counts"] = count_results(results)
    state["pending_retry"] = sum(
        1
        for result in results.values()
        if result.get("status") == "UNKNOWN_RETRY"
        and int(result.get("attempts", 0)) < MAX_ATTEMPTS
    )
    state["build"] = BUILD
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    state["status"] = (
        "HISTORY_COMPLETE"
        if end >= len(queue) and state["pending_retry"] == 0
        else "HISTORY_PARTIAL"
    )
    state["state_hash"] = hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    atomic_write(STATE, state)

    candidates = {}
    for symbol, result in results.items():
        if result.get("status") != "PASS":
            continue
        info = dict(result.get("info") or {})
        info["security_name"] = state["security_names"].get(symbol)
        candidates[symbol] = info

    candidate_state = {
        "schema": "XRAY_MARKET_CANDIDATES_V4",
        "task_id": TASK_ID,
        "asof_et": asof,
        "execution": "NONE",
        "real_money": "NO-GO",
        "source": "NASDAQTRADER_EXPLICIT_TYPE_FILTER_PLUS_EASTMONEY_PRICE_DV20_HISTORY",
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    atomic_write(CAND, candidate_state)

    print(json.dumps({
        "status": state["status"],
        "asof": asof,
        "queue_total": len(queue),
        "explicit_excluded": len(excluded),
        "cursor": end,
        "processed_new": len(new_symbols),
        "processed_retry": len(retry_symbols),
        "pending_retry": state["pending_retry"],
        "counts": state["counts"],
        "candidate_count": len(candidates),
    }, sort_keys=True))

if __name__ == "__main__":
    main()
