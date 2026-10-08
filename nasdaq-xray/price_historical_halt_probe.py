#!/usr/bin/env python3
"""Zero-dollar official Nasdaq historical-halt probe for PRICE/DV30 gaps.

NON-CANONICAL diagnostic/evidence-candidate only.
It never creates PASS/FAIL and never manufactures bars.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN != PASS.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRICE = ROOT / "canonical_current_price_dv30.json"
OUT = ROOT / "price_historical_halt_probe_state.json"
BASE = "https://www.nasdaqtrader.com/rss.aspx"
UA = "NASDAQ-SWING-XRAY/1.0 research github.com/gokaydonmez39-jpg/kripto-radar"

def parse_rss(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    rows = []
    for item in root.findall(".//item"):
        row = {}
        for child in list(item):
            tag = child.tag.split("}")[-1]
            row[tag] = (child.text or "").strip()
        rows.append(row)
    return rows

def parse_et_time(value: str):
    s = str(value or "").strip()
    if not s:
        return None
    s = re.sub(r"\.(\d+)$", "", s)
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            pass
    return None

def normalize_mmddyyyy(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%m%d%Y")

def source_url(session_date: str) -> str:
    return BASE + "?" + urllib.parse.urlencode({
        "feed": "tradehalts",
        "haltdate": normalize_mmddyyyy(session_date),
    })

def fetch_rows(session_date: str) -> tuple[list[dict], dict]:
    url = source_url(session_date)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml,application/xml,text/xml,*/*;q=0.2",
        "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read(2_000_000)
        return parse_rss(raw), {
            "url": url,
            "http_status": int(getattr(r, "status", 200)),
            "final_url": str(r.geturl()),
            "content_type": str(r.headers.get("Content-Type") or ""),
        }

def full_session_halt_candidate(row: dict, sym: str, session_date: str):
    if str(row.get("IssueSymbol") or "").strip().upper() != sym.upper():
        return None
    market = str(row.get("Market") or "").strip().upper()
    if market != "NASDAQ":
        return None
    hd = str(row.get("HaltDate") or "").strip()
    # Nasdaq feed uses MM/DD/YYYY.
    try:
        halt_date = datetime.strptime(hd, "%m/%d/%Y").date().isoformat()
    except Exception:
        return None
    if halt_date != session_date:
        return None
    ht = parse_et_time(row.get("HaltTime"))
    if ht is None or ht > time(9, 30):
        return None
    rd = str(row.get("ResumptionDate") or "").strip()
    rt = parse_et_time(row.get("ResumptionTradeTime"))
    # Historical absence of a published resume date/time cannot independently
    # establish a *full* RTH halt. Keep the hypothesis UNKNOWN, not FAIL.
    if not rd or rt is None:
        return None
    try:
        resume_date = datetime.strptime(rd, "%m/%d/%Y").date().isoformat()
    except Exception:
        return None
    if resume_date < session_date:
        return None
    if resume_date == session_date and rt <= time(16, 0):
        return None
    return {
        "symbol": sym.upper(),
        "session_date": session_date,
        "market": market,
        "halt_date": hd,
        "halt_time_et": str(row.get("HaltTime") or ""),
        "reason_code": str(row.get("ReasonCode") or ""),
        "resumption_date": rd,
        "resumption_trade_time_et": str(row.get("ResumptionTradeTime") or ""),
        "proof": "NASDAQ_TRADER_HISTORICAL_FULL_SESSION_HALT_CANDIDATE",
        "decision_direction": "FAIL_ONLY_CANDIDATE_NEVER_PASS",
    }

def candidate_missing_sessions(price: dict) -> dict[str, list[str]]:
    out = {}
    for sym,rec in sorted((price.get("results") or {}).items()):
        status=str(rec.get("status") or "")
        if status not in {"BLOCK_CURRENT_RUN","UNKNOWN"}:
            continue
        # BLOCK_CURRENT_RUN keeps provider evidence under block_recovery_attempt;
        # persisted UNKNOWN keeps the same zero-dollar provider result in info.
        attempt = rec.get("block_recovery_attempt") or {}
        pres = attempt.get("provider_result") or {}
        if not pres and status=="UNKNOWN":
            pres = rec.get("info") or {}
        sina = pres.get("sina_result") or {}
        n = sina.get("known_session_count")
        missing = sina.get("missing_sessions") or []
        # Bounded probe: only near-complete exact30 gaps. Broad/new-listing
        # coverage is handled by the separate official listing registry.
        if isinstance(n, int) and n >= 29 and 0 < len(missing) <= 2:
            out[sym] = sorted({str(x)[:10] for x in missing if x})
    return out

def selftest():
    xml = b"""<?xml version="1.0"?><rss><channel><item>
<IssueSymbol>GRAL</IssueSymbol><IssueName>GRAIL, Inc.</IssueName><Market>NASDAQ</Market>
<HaltDate>09/23/2026</HaltDate><HaltTime>06:55:00.000</HaltTime><ReasonCode>T1</ReasonCode>
<ResumptionDate>09/24/2026</ResumptionDate><ResumptionTradeTime>04:00:00</ResumptionTradeTime>
</item></channel></rss>"""
    row = parse_rss(xml)[0]
    ev = full_session_halt_candidate(row, "GRAL", "2026-09-23")
    assert ev and ev["proof"] == "NASDAQ_TRADER_HISTORICAL_FULL_SESSION_HALT_CANDIDATE", ev
    intraday = dict(row, HaltTime="12:00:00.000", ResumptionDate="09/23/2026", ResumptionTradeTime="13:00:00")
    assert full_session_halt_candidate(intraday, "GRAL", "2026-09-23") is None
    # A halt without an independently published resumption is not proven
    # to span the full regular session; avoid a false terminal FAIL.
    assert full_session_halt_candidate(dict(row, ResumptionDate=""), "GRAL", "2026-09-23") is None
    assert full_session_halt_candidate(dict(row, ResumptionTradeTime=""), "GRAL", "2026-09-23") is None
    assert full_session_halt_candidate(dict(row, ResumptionDate="09/23/2026", ResumptionTradeTime="16:00:00"), "GRAL", "2026-09-23") is None
    assert full_session_halt_candidate(dict(row, ResumptionDate="09/23/2026", ResumptionTradeTime="16:00:01"), "GRAL", "2026-09-23") is not None
    wrong_market = dict(row, Market="NYSE")
    assert full_session_halt_candidate(wrong_market, "GRAL", "2026-09-23") is None
    sample={
        "blocked_symbols":[],
        "results":{
            "GRAL":{"status":"UNKNOWN","info":{"sina_result":{
                "known_session_count":29,"missing_sessions":["2026-09-23"]
            }}},
            "NEW":{"status":"UNKNOWN","info":{"sina_result":{
                "known_session_count":5,"missing_sessions":["2026-09-23"]
            }}},
            "PASS":{"status":"PASS_PRICE_DV30","info":{"sina_result":{
                "known_session_count":29,"missing_sessions":["2026-09-23"]
            }}},
        },
    }
    assert candidate_missing_sessions(sample)=={"GRAL":["2026-09-23"]}
    print("XRAY_PRICE_HISTORICAL_HALT_PROBE_SELFTEST=PASS")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    price = json.loads(PRICE.read_text(encoding="utf-8"))
    assert price.get("schema") == "XRAY_CANONICAL_PRICE_DV30_V1"
    assert price.get("execution") == "NONE" and price.get("real_money") == "NO-GO"
    assert price.get("unknown_never_pass") is True

    candidates = candidate_missing_sessions(price)
    results = {}
    date_cache = {}
    date_diagnostics = {}
    for sym, dates in sorted(candidates.items()):
        evidence = []
        errors = []
        # Official RSS field diagnostics are discovery-only. Never promote
        # classifications from field text without the strict validator.
        official_symbol_rows = []
        for d in dates:
            if d not in date_cache:
                try:
                    rows0, meta0 = fetch_rows(d)
                    date_cache[d] = ("PASS", rows0, meta0)
                    date_diagnostics[d] = {
                        "status": "PASS",
                        "row_count": len(rows0),
                        "halt_dates": sorted({str(x.get("HaltDate") or "") for x in rows0 if x.get("HaltDate")}),
                        "issue_symbols": sorted({str(x.get("IssueSymbol") or "").strip().upper() for x in rows0 if x.get("IssueSymbol")})[:200],
                        "meta": meta0,
                    }
                except Exception as e:
                    err = {
                        "url": source_url(d),
                        "reason": f"{type(e).__name__}:{str(e)[:180]}",
                    }
                    date_cache[d] = ("UNKNOWN", None, err)
                    date_diagnostics[d] = {"status": "UNKNOWN", **err}
            status, rows, meta = date_cache[d]
            if status != "PASS":
                errors.append({"session_date": d, **meta})
                continue
            matches = []
            for row in rows:
                if any(str(v).strip().upper() == sym for v in row.values()):
                    official_symbol_rows.append({
                        key: str(row.get(key) or "")[:85] for key in sorted(row)
                        if key in {"IssueSymbol","HaltDate","HaltTime","Market",
                                   "ResumptionDate","ResumptionTradeTime",
                                   "ReasonCode","IssueName","Mkt","Symbol"}
                    })
                ev = full_session_halt_candidate(row, sym, d)
                if ev:
                    ev["source_url"] = meta["url"]
                    matches.append(ev)
            evidence.extend(matches)
        explained = {x["session_date"] for x in evidence}
        results[sym] = {
            "status": "FULL_SESSION_HALT_CANDIDATE" if set(dates) and set(dates) <= explained else "UNKNOWN_UNRESOLVED",
            "classification_applied": False,
            "missing_sessions": dates,
            "official_evidence": evidence,
            "official_symbol_rows_diagnostic": official_symbol_rows[:3],
            "errors": errors,
        }

    obj = {
        "schema": "XRAY_PRICE_HISTORICAL_HALT_PROBE_V1",
        "authority": "NON_CANONICAL_NASDAQ_TRADER_PRIMARY_EVIDENCE_CANDIDATE_ONLY",
        "asof_et": price.get("asof_et"),
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "classification_applied": False,
        "source_price_path": "nasdaq-xray/canonical_current_price_dv30.json",
        "candidate_scope": sorted(candidates),
        "candidate_scope_count": len(candidates),
        "queried_dates": sorted(date_cache),
        "date_diagnostics": date_diagnostics,
        "results": results,
        "rule": "ONLY_OFFICIAL_NASDAQ_HISTORICAL_HALT_ROWS_CAN_EXPLAIN_NEAR_COMPLETE_EXACT30_GAPS;NO_EVIDENCE_REMAINS_UNKNOWN",
    }
    OUT.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "scope": len(candidates),
        "full_session_halt_candidates": sorted(k for k,v in results.items() if v["status"]=="FULL_SESSION_HALT_CANDIDATE"),
        "unknown": sorted(k for k,v in results.items() if v["status"]!="FULL_SESSION_HALT_CANDIDATE"),
        "date_probe_diagnostics": {
            d: {"status": x.get("status"), "row_count": x.get("row_count"),
                "reason": x.get("reason"), "http_status": x.get("http_status"),
                "error_type": str(x.get("reason") or "").split(":")[0]}
            for d,x in date_diagnostics.items()
        },
        "matching_symbol_halt_row_counts": {
            sym: len(r.get("official_evidence") or []) for sym,r in results.items()
        },
        "official_symbol_rows_diagnostic": {
            sym: rec.get("official_symbol_rows_diagnostic", [])
            for sym,rec in results.items()
        },
    }, sort_keys=True))

if __name__ == "__main__":
    main()
