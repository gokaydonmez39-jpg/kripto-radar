"""Validate a real n8n CLI execution, not an extracted JavaScript simulation."""
import json
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_text(encoding="utf-8")
decoded = []
for line_start in (i for i, ch in enumerate(raw) if ch == "{" and (i == 0 or raw[i - 1] == "\n")):
    try:
        item, _ = json.JSONDecoder().raw_decode(raw[line_start:])
    except json.JSONDecodeError:
        continue
    if isinstance(item, dict):
        decoded.append(item)
expected = {"system": "XRAY_NASDAQ_PERSONAL", "status": "ACCEPTED",
            "reason": "READ_ONLY_CANDIDATE",
            "event_key": "XRAY_NASDAQ_PERSONAL|EOD_ACCEPTED|2026-11-10",
            "may_notify": False, "may_dispatch": False, "may_trade": False,
            "source_authentication": "CALLER_WITNESS_NOT_ATTESTED", "fixture_only": True}
results = []
for item in decoded:
    data = item.get("data", {})
    result = data.get("resultData", {}) if isinstance(data, dict) else {}
    if not isinstance(result, dict) or result.get("error"):
        continue
    run = result.get("runData", {}).get("Synthetic contract", [])
    for node in run:
        results.extend(x.get("json") for channel in node.get("data", {}).get("main", []) if channel for x in channel)
if len(results) != 1 or results[0] != expected:
    raise SystemExit("N8N_REAL_RUNTIME_OUTPUT_MISMATCH")
print("N8N_REAL_RUNTIME_SYNTHETIC_MANUAL_ONLY_PASS")
