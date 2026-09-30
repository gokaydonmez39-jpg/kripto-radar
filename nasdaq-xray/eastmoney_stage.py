#!/usr/bin/env python3
"""NASDAQ SWING X-RAY deterministic external hard-gate stage V3.
Identity: fresh NasdaqTrader intersect official SEC Nasdaq registrants.
OHLCV accelerator: Eastmoney direct NASDAQ history (market id 105).
Research/forward-test only. EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
No result is promoted to G9 or live execution authority.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import random
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import median

import pandas_market_calendars as mcal

TASK_ID = "6a825366222081918997094d76e6ae46"
BUILD = "2026-10-01.3"
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
HIST_URL = "https://63.push2his.eastmoney.com/api/qt/stock/kline/get"
ROOT = Path(__file__).resolve().parent
STATE = ROOT / "eastmoney_state.json"
CAND = ROOT / "market_candidates.json"

NEW_PER_RUN = int(os.getenv("XRAY_EM_HISTORY_BATCH", "120"))
RETRY_PER_RUN = int(os.getenv("XRAY_EM_RETRY_BATCH", "30"))
WORKERS = int(os.getenv("XRAY_EM_HISTORY_WORKERS", "4"))
MAX_ATTEMPTS = int(os.getenv("XRAY_EM_MAX_ATTEMPTS", "4"))
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

def sha_lines(xs):
    return hashlib.sha256("\n".join(xs).encode("utf-8")).hexdigest()

def request_bytes(url, headers=None, timeout=35, retries=3):
    last = None
    hdr = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
    if headers:
        hdr.update(headers)
    for k in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(0.8 * (k + 1) + random.uniform(0.1, 0.5))
    raise last

def get_text(url, headers=None, timeout=35, retries=3):
    return request_bytes(url, headers, timeout, retries).decode("utf-8")

def get_json(url, params=None, headers=None, timeout=45, retries=3):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    return json.loads(get_text(url, headers, timeout, retries))

def official_nasdaq():
    text = get_text(NASDAQ_URL)
    lines = [x.strip("\r") for x in text.splitlines() if x.strip()]
    footer = next((x for x in reversed(lines) if x.startswith("File Creation Time:")), None)
    body = "\n".join(x for x in lines if not x.startswith("File Creation Time:"))
    rows = list(csv.DictReader(io.StringIO(body), delimiter="|"))
    out = set()
    for row in rows:
        s = (row.get("Symbol") or "").strip().upper()
        if not s:
            continue
        if row.get("Test Issue") != "N":
            continue
        if row.get("ETF") == "Y":
            continue
        if row.get("NextShares") == "Y":
            continue
        out.add(s)
    if not footer or not out:
        raise RuntimeError("NASDAQ_DIRECTORY_INVALID")
    return out, footer

def sec_nasdaq():
    data = get_json(
        SEC_TICKERS_URL,
        headers={"User-Agent": "NASDAQ-SWING-XRAY/1.0 research github.com/gokaydonmez39-jpg/kripto-radar"},
    )
    fields = data.get("fields") or []
    rows = data.get("data") or []
    idx = {name: i for i, name in enumerate(fields)}
    required = {"ticker", "exchange", "cik"}
    if not required.issubset(idx):
        raise RuntimeError("SEC_TICKER_SCHEMA_CHANGED")
    ticker_to_cik = {}
    cik_to_tickers = {}
    for row in rows:
        try:
            ticker = str(row[idx["ticker"]]).strip().upper()
            exch = str(row[idx["exchange"]]).strip().lower()
            cik = int(row[idx["cik"]])
        except Exception:
            continue
        if exch != "nasdaq" or not ticker:
            continue
        ticker_to_cik[ticker] = cik
        cik_to_tickers.setdefault(str(cik), []).append(ticker)
    if not ticker_to_cik:
        raise RuntimeError("SEC_NASDAQ_EMPTY")
    for k in cik_to_tickers:
        cik_to_tickers[k] = sorted(set(cik_to_tickers[k]))
    return ticker_to_cik, cik_to_tickers

def completed_sessions():
    cal = mcal.get_calendar("NASDAQ")
    now = datetime.now(timezone.utc)
    sched = cal.schedule(
        start_date=(now.date() - timedelta(days=900)).isoformat(),
        end_date=(now.date() + timedelta(days=1)).isoformat(),
    )
    out = []
    for idx, row in sched.iterrows():
        if row["market_close"].to_pydatetime() <= now:
            out.append(idx.date().isoformat())
    if len(out) < 260:
        raise RuntimeError("CALENDAR_TOO_SHORT")
    return out[-520:], out[-1], out[-20:]

def parse_hist(symbol, asof, expected20):
    params = {
        "secid": f"105.{symbol}",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "0",
        "beg": "20180101",
        "end": "20500000",
        "lmt": "3000",
    }
    try:
        time.sleep(random.uniform(0.04, 0.16))
        d = get_json(
            HIST_URL,
            params=params,
            headers={"Referer": "https://quote.eastmoney.com/"},
            timeout=45,
            retries=3,
        )
        kl = ((d.get("data") or {}).get("klines") or [])
        by_date = {}
        for line in kl:
            a = line.split(",")
            if len(a) < 7:
                continue
            dt = a[0]
            try:
                close = float(a[2])
                vol = float(a[5])
            except Exception:
                continue
            if (
                dt <= asof
                and close > 0
                and vol > 0
                and math.isfinite(close)
                and math.isfinite(vol)
            ):
                by_date[dt] = (close, vol)
        if asof not in by_date:
            return "UNKNOWN_STATIC", "ASOF_MISSING"
        missing20 = [d for d in expected20 if d not in by_date]
        if missing20:
            return "UNKNOWN_STATIC", {"reason": "EXACT20_MISSING", "dates": missing20}
        price = by_date[asof][0]
        dvs = sorted(by_date[d][0] * by_date[d][1] for d in expected20)
        dv20 = (dvs[9] + dvs[10]) / 2.0
        bars = len(by_date)
        info = {"price": price, "dv20": dv20, "bars": bars, "secid": f"105.{symbol}"}
        if price <= 10:
            return "FAIL_PRICE", info
        if dv20 < 50_000_000:
            return "FAIL_DV20", info
        if bars < 260:
            return "FAIL_HISTORY", info
        return "PASS", info
    except Exception as e:
        return "UNKNOWN_RETRY", f"{type(e).__name__}:{str(e)[:160]}"

def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def atomic_write(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

def rebuild_state(queue, cik_map, cik_to_tickers, footer, asof, expected20):
    return {
        "schema": "XRAY_EASTMONEY_RESUMABLE_V3",
        "build": BUILD,
        "task_id": TASK_ID,
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "source": "EASTMONEY_HISTORY_ACCELERATOR_NOT_G9",
        "identity_authority": "NASDAQTRADER_INTERSECT_SEC_NASDAQ",
        "official_footer": footer,
        "asof_et": asof,
        "expected20": expected20,
        "queue": queue,
        "queue_hash": sha_lines(queue),
        "queue_total": len(queue),
        "cursor": 0,
        "results": {},
        "cik_map": {s: cik_map[s] for s in queue},
        "multi_ticker_ciks": {
            cik: ts for cik, ts in cik_to_tickers.items()
            if len(ts) > 1 and any(t in set(queue) for t in ts)
        },
        "status": "HISTORY_PARTIAL",
    }

def result_counts(results):
    keys = [
        "PASS", "FAIL_PRICE", "FAIL_DV20", "FAIL_HISTORY",
        "UNKNOWN_STATIC", "UNKNOWN_RETRY", "UNKNOWN_RETRY_EXHAUSTED"
    ]
    out = {k: 0 for k in keys}
    for v in results.values():
        st = v.get("status")
        out[st] = out.get(st, 0) + 1
    return out

def main():
    ndq, footer = official_nasdaq()
    sec_map, cik_to_tickers = sec_nasdaq()
    _, asof, expected20 = completed_sessions()

    queue = sorted(ndq.intersection(sec_map.keys()))
    identity_hash = sha_lines(queue)
    state = load_state()

    # V2 did not preserve identities for definitive FAIL counters. Rebuild once into V3.
    # V3 stores every symbol-level result, so all future resumption is exact.
    if (
        state.get("schema") != "XRAY_EASTMONEY_RESUMABLE_V3"
        or state.get("queue_hash") != identity_hash
        or state.get("asof_et") != asof
    ):
        state = rebuild_state(queue, sec_map, cik_to_tickers, footer, asof, expected20)

    results = state.setdefault("results", {})

    retry_syms = sorted(
        s for s, v in results.items()
        if v.get("status") == "UNKNOWN_RETRY" and int(v.get("attempts", 0)) < MAX_ATTEMPTS
    )[:RETRY_PER_RUN]

    start = int(state.get("cursor", 0))
    end = min(start + NEW_PER_RUN, len(queue))
    new_syms = queue[start:end]
    work = []
    seen = set()
    for s in retry_syms + new_syms:
        if s not in seen:
            seen.add(s)
            work.append(s)

    run_results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(parse_hist, s, asof, expected20): s for s in work}
        for fut in as_completed(futs):
            s = futs[fut]
            status, info = fut.result()
            run_results.append((s, status, info))

    for sym, status, info in run_results:
        prev = results.get(sym) or {}
        attempts = int(prev.get("attempts", 0)) + 1
        if status == "UNKNOWN_RETRY" and attempts >= MAX_ATTEMPTS:
            status = "UNKNOWN_RETRY_EXHAUSTED"
        results[sym] = {
            "status": status,
            "info": info,
            "attempts": attempts,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    state["cursor"] = end
    state["processed_new_this_run"] = len(new_syms)
    state["processed_retry_this_run"] = len(retry_syms)
    state["build"] = BUILD
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    counts = result_counts(results)
    state["counts"] = counts
    pending_retry = sum(
        1 for v in results.values()
        if v.get("status") == "UNKNOWN_RETRY" and int(v.get("attempts", 0)) < MAX_ATTEMPTS
    )
    state["pending_retry"] = pending_retry
    state["status"] = (
        "HISTORY_COMPLETE"
        if end >= len(queue) and pending_retry == 0
        else "HISTORY_PARTIAL"
    )
    state["state_hash"] = hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    atomic_write(STATE, state)

    candidates = {}
    for sym, rec in results.items():
        if rec.get("status") == "PASS":
            info = dict(rec.get("info") or {})
            info["cik"] = state["cik_map"].get(sym)
            cik = str(info["cik"]) if info.get("cik") is not None else ""
            info["multi_ticker_cik"] = cik in state.get("multi_ticker_ciks", {})
            candidates[sym] = info

    cand = {
        "schema": "XRAY_MARKET_CANDIDATES_V2",
        "task_id": TASK_ID,
        "asof_et": asof,
        "execution": "NONE",
        "real_money": "NO-GO",
        "source": "NASDAQTRADER_SEC_IDENTITY_PLUS_EASTMONEY_PRICE_DV20_HISTORY",
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    atomic_write(CAND, cand)

    print(json.dumps({
        "status": state["status"],
        "asof": asof,
        "queue_total": len(queue),
        "cursor": end,
        "processed_new": len(new_syms),
        "processed_retry": len(retry_syms),
        "pending_retry": pending_retry,
        "counts": counts,
        "candidate_count": len(candidates),
    }, sort_keys=True))

if __name__ == "__main__":
    main()
