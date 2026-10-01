#!/usr/bin/env python3
"""NASDAQ SWING X-RAY bootstrap data plane.
Research/forward-test only. EXECUTION=NONE. REAL_MONEY=NO-GO.
"""
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

TASK_ID = "6a825366222081918997094d76e6ae46"
BRIDGE_BUILD = "2026-10-01.2"
URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OUT = Path(__file__).resolve().parent / "state.json"

req = Request(URL, headers={"User-Agent": "NASDAQ-SWING-XRAY/1.0"})
with urlopen(req, timeout=30) as r:
    text = r.read().decode("utf-8", errors="strict")

lines = [x.strip("\r") for x in text.splitlines() if x.strip()]
footer = next((x for x in reversed(lines) if x.startswith("File Creation Time:")), None)
if not footer:
    raise RuntimeError("NASDAQ_DIRECTORY_FOOTER_MISSING")

data = "\n".join(x for x in lines if not x.startswith("File Creation Time:"))
rows = list(csv.DictReader(io.StringIO(data), delimiter="|"))
rows = [r for r in rows if r.get("Symbol")]
symbols = sorted({r["Symbol"].strip() for r in rows if r.get("Symbol")})
if not symbols:
    raise RuntimeError("NASDAQ_DIRECTORY_EMPTY")

payload = {
    "schema": "XRAY_GITHUB_DATAPLANE_V1",
    "task_id": TASK_ID,
    "execution": "NONE",
    "real_money": "NO-GO",
    "unknown_never_pass": True,
    "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    "universe": {
        "source": URL,
        "footer": footer,
        "raw_rows": len(rows),
        "unique_symbols": len(symbols),
        "symbols_hash": hashlib.sha256("\n".join(symbols).encode()).hexdigest(),
    },
    "status": "UNIVERSE_BOOTSTRAP_PASS",
    "g9": "G9_BLOCKED_FREE_AUTOMATION_PATH",
}
OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(payload, sort_keys=True))
