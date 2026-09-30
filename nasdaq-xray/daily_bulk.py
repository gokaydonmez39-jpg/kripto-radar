#!/usr/bin/env python3
"""XRAY daily bulk hard-gate engine.
Source: Stooq bulk US daily ZIP + official NasdaqTrader universe state.
Research/forward-test only. EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent
UNIVERSE_STATE = ROOT / "state.json"
OUT = ROOT / "daily_state.json"
ZIP_URL = "https://static.stooq.com/db/h/d_us_txt.zip"
TASK_ID = "6a825366222081918997094d76e6ae46"

def sha(items):
    return hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()

def download(url, dst):
    req = urllib.request.Request(url, headers={"User-Agent":"NASDAQ-SWING-XRAY/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r, open(dst, "wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

def norm_symbol(t):
    t = t.strip().upper()
    if t.endswith(".US"):
        t = t[:-3]
    # Stooq commonly uses hyphen where official Nasdaq may use class separator punctuation.
    return t

def parse_file(raw):
    text = raw.decode("utf-8", errors="ignore")
    rows = []
    rd = csv.reader(io.StringIO(text))
    header = next(rd, None)
    for r in rd:
        if len(r) < 9:
            continue
        try:
            ticker = norm_symbol(r[0])
            date = r[2]
            close = float(r[7])
            vol = float(r[8])
            if len(date) == 8 and close > 0 and vol > 0:
                rows.append((date, close, vol, ticker))
        except Exception:
            continue
    rows.sort(key=lambda x: x[0])
    return rows

def main():
    if not UNIVERSE_STATE.exists():
        raise RuntimeError("OFFICIAL_UNIVERSE_STATE_MISSING")
    u = json.loads(UNIVERSE_STATE.read_text())
    if u.get("status") != "UNIVERSE_BOOTSTRAP_PASS":
        raise RuntimeError("OFFICIAL_UNIVERSE_NOT_PASS")

    # Re-fetch official symbols directly so this stage has exact symbol identities, not only a hash.
    nasdaq_url = u["universe"]["source"]
    req = urllib.request.Request(nasdaq_url, headers={"User-Agent":"NASDAQ-SWING-XRAY/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        txt = r.read().decode("utf-8")
    lines = [x.strip("\r") for x in txt.splitlines() if x.strip() and not x.startswith("File Creation Time:")]
    rd = csv.DictReader(io.StringIO("\n".join(lines)), delimiter="|")
    official = set()
    for row in rd:
        s = (row.get("Symbol") or "").strip().upper()
        if not s:
            continue
        # Deterministic obvious exclusions available in official directory.
        if row.get("Test Issue") != "N":
            continue
        if row.get("ETF") == "Y":
            continue
        if row.get("NextShares") == "Y":
            continue
        official.add(s)

    with tempfile.TemporaryDirectory() as td:
        zpath = Path(td) / "d_us_txt.zip"
        download(ZIP_URL, zpath)
        zsize = zpath.stat().st_size
        passed = []
        price_pass = []
        dv20_pass = []
        history260 = []
        matched = set()
        provider_missing = set(official)
        malformed = 0

        with zipfile.ZipFile(zpath) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
            for name in names:
                low = name.lower()
                # Avoid ETFs and non-stock folders; exact Nasdaq identity is enforced by official set.
                if "etfs" in low or "funds" in low:
                    continue
                try:
                    rows = parse_file(zf.read(name))
                except Exception:
                    malformed += 1
                    continue
                if not rows:
                    continue
                symbol = rows[-1][3]
                if symbol not in official:
                    continue
                matched.add(symbol)
                provider_missing.discard(symbol)

                if len(rows) >= 260:
                    history260.append(symbol)
                last_close = rows[-1][1]
                if last_close > 10:
                    price_pass.append(symbol)
                if len(rows) >= 20:
                    last20 = rows[-20:]
                    dv20 = median([c*v for _, c, v, _ in last20])
                    if dv20 >= 50_000_000:
                        dv20_pass.append(symbol)
                    if last_close > 10 and dv20 >= 50_000_000 and len(rows) >= 260:
                        passed.append(symbol)

        passed = sorted(set(passed))
        price_pass = sorted(set(price_pass))
        dv20_pass = sorted(set(dv20_pass))
        history260 = sorted(set(history260))
        matched = sorted(matched)
        provider_missing = sorted(provider_missing)

    out = {
        "schema":"XRAY_GITHUB_DAILY_BULK_V1",
        "task_id":TASK_ID,
        "execution":"NONE",
        "real_money":"NO-GO",
        "unknown_never_pass":True,
        "updated_at_utc":datetime.now(timezone.utc).isoformat(),
        "source":{
            "provider":"STOOQ_BULK",
            "url":ZIP_URL,
            "zip_bytes":zsize,
            "authority":"PRICE_DV20_HISTORY_ACCELERATOR_NOT_G9",
        },
        "official_basic_universe":len(official),
        "provider_matched":len(matched),
        "provider_missing":len(provider_missing),
        "provider_missing_hash":sha(provider_missing),
        "malformed_files":malformed,
        "price_gt10":len(price_pass),
        "dv20_ge50m":len(dv20_pass),
        "history_ge260":len(history260),
        "price_dv20_history_pass":len(passed),
        "price_dv20_history_pass_hash":sha(passed),
        "candidate_symbols":passed,
        "status":"PRICE_DV20_HISTORY_PASS_PARTIAL_CANONICAL",
        "remaining_hard_gate":"MARKET_CAP_AND_LEGAL_SHELL_AND_DEEP",
        "g9":"G9_BLOCKED_FREE_AUTOMATION_PATH",
        "notes":[
            "Stooq bulk is an accelerator/cross-source path, not G9.",
            "Market-cap is not inferred from price or volume.",
            "Provider-missing symbols remain UNKNOWN, never FAIL/PASS."
        ],
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k:out[k] for k in [
        "official_basic_universe","provider_matched","provider_missing",
        "price_gt10","dv20_ge50m","history_ge260","price_dv20_history_pass","status"
    ]}, sort_keys=True))

if __name__ == "__main__":
    main()
