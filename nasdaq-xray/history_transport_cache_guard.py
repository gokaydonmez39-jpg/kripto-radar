#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

TASK = "6a825366222081918997094d76e6ae46"
HARD_DAILY = 260


def cache_path(cache_dir: Path, symbol: str) -> Path:
    return cache_dir / (hashlib.sha256(symbol.encode()).hexdigest() + ".csv.gz")


def read_dates(path: Path, asof: str) -> list[str]:
    if not path.exists() or path.stat().st_size <= 0:
        return []
    out = set()
    try:
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as fh:
            rows = csv.DictReader(fh)
            if not rows.fieldnames:
                return []
            names = {str(x).lower(): x for x in rows.fieldnames}
            dcol = names.get("date")
            if not dcol:
                return []
            for row in rows:
                raw = str(row.get(dcol) or "")[:10]
                try:
                    d = date.fromisoformat(raw)
                except Exception:
                    continue
                if raw <= asof:
                    out.add(d.isoformat())
    except Exception:
        return []
    return sorted(out)


def evaluate(cache_dir: Path, history: dict, legal: dict, identity: dict, require_qqq: bool = True) -> tuple[bool, dict]:
    if history.get("task_id") != TASK or legal.get("task_id") != TASK:
        return False, {"reason": "TASK_MISMATCH"}
    if history.get("execution") != "NONE" or history.get("real_money") != "NO-GO" or history.get("unknown_never_pass") is not True:
        return False, {"reason": "HISTORY_SAFETY_INVALID"}
    if legal.get("execution") != "NONE" or legal.get("real_money") != "NO-GO":
        return False, {"reason": "LEGAL_SAFETY_INVALID"}
    asof = str(history.get("asof_et") or "")
    if not asof or legal.get("asof_et") != asof:
        return False, {"reason": "ASOF_MISMATCH"}

    legal_unknown = int((legal.get("counts") or {}).get("UNKNOWN_LEGAL", legal.get("unknown_count", 0)) or 0)
    if int(history.get("unknown_count", -1)) != 0 or legal_unknown != 0:
        return False, {"reason": "UPSTREAM_UNKNOWN"}

    hpass = set(history.get("pass_symbols") or [])
    scope = sorted(set(legal.get("pass_symbols") or []))
    if not set(scope).issubset(hpass):
        return False, {"reason": "LEGAL_SCOPE_NOT_HISTORY_PASS"}

    records = identity.get("records") or {}
    missing = {}
    checked = []

    def exact_current(sym: str) -> list[str]:
        p = cache_path(cache_dir, sym)
        ds = read_dates(p, asof)
        if not ds:
            missing[sym] = "CACHE_MISSING_OR_INVALID"
            return []
        if ds[-1] != asof:
            missing[sym] = f"ASOF_MISSING:{ds[-1]}"
            return []
        checked.append(sym)
        return ds

    for sym in scope:
        current = exact_current(sym)
        if not current:
            continue
        rec = records.get(sym) or {}
        if rec.get("mode") == "OFFICIAL_TICKER_CONTINUITY_COMPOSITE_HISTORY" and rec.get("cusip_unchanged") is True:
            pred = str(rec.get("predecessor_symbol") or "")
            eff = str(rec.get("effective_date") or "")
            if not pred or not eff:
                missing[sym] = "CONTINUITY_METADATA_INVALID"
                continue
            pred_dates = read_dates(cache_path(cache_dir, pred), asof)
            if not pred_dates:
                missing[sym] = "PREDECESSOR_CACHE_MISSING_OR_INVALID:" + pred
                continue
            combined = {d for d in pred_dates if d < eff} | {d for d in current if d >= eff}
            if len(combined) < HARD_DAILY:
                missing[sym] = f"COMPOSITE_LT{HARD_DAILY}:{len(combined)}"
                continue
        elif len(current) < HARD_DAILY:
            missing[sym] = f"CURRENT_LT{HARD_DAILY}:{len(current)}"

    if require_qqq:
        q = exact_current("QQQ")
        if q and len(q) < HARD_DAILY:
            missing["QQQ"] = f"CURRENT_LT{HARD_DAILY}:{len(q)}"

    detail = {
        "schema": "XRAY_HISTORY_TRANSPORT_CACHE_GUARD_V1",
        "asof_et": asof,
        "scope_count": len(scope),
        "required_qqq": bool(require_qqq),
        "checked_count": len(set(checked)),
        "missing_count": len(missing),
        "missing": dict(sorted(missing.items())),
        "authority": "TRANSPORT_CACHE_ONLY_NOT_ALPHA_AUTHORITY",
        "unknown_never_pass": True,
    }
    if missing:
        detail["reason"] = "CACHE_INCOMPLETE_OR_STALE"
        return False, detail
    detail["reason"] = "EXACT_ASOF_TRANSPORT_CACHE_COMPLETE"
    return True, detail


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--history", required=True)
    ap.add_argument("--legal", required=True)
    ap.add_argument("--identity", required=True)
    ap.add_argument("--no-qqq", action="store_true")
    args = ap.parse_args()
    history = json.loads(Path(args.history).read_text(encoding="utf-8"))
    legal = json.loads(Path(args.legal).read_text(encoding="utf-8"))
    identity = json.loads(Path(args.identity).read_text(encoding="utf-8"))
    ok, detail = evaluate(Path(args.cache_dir), history, legal, identity, require_qqq=not args.no_qqq)
    print("cache_ready=" + ("true" if ok else "false"))
    print("cache_reason=" + detail["reason"])
    print(json.dumps(detail, sort_keys=True))


if __name__ == "__main__":
    main()
