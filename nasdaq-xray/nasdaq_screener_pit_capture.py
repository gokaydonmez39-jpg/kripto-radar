#!/usr/bin/env python3
"""Zero-dollar Nasdaq screener PIT shadow capture.

Purpose:
- capture Nasdaq's public screener market-cap surface after the regular session,
- bind rows only when the capture date equals the canonical research ASOF,
- cross-check each screener last sale against the canonical completed RTH close,
- preserve every mismatch as UNKNOWN/non-authoritative.

This file never changes C4.17 production MC authority.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
PRICE=ROOT/"canonical_current_price_dv30.json"
CURRENT=ROOT/"nasdaq_screener_pit_current.json"
ARCHIVE_DIR=ROOT/"evidence"/"nasdaq_screener_pit"
URL="https://api.nasdaq.com/api/screener/stocks"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
NY=ZoneInfo("America/New_York")
POST_CLOSE_FLOOR=time(16,10)
CLOSE_ABS_TOL=0.02
CLOSE_REL_TOL=0.0001


def parse_num(value):
    try:
        if value is None:
            return None
        s=str(value).replace("$","").replace(",","").strip()
        if not s or s in {"N/A","--"}:
            return None
        v=float(s)
        return v if math.isfinite(v) else None
    except Exception:
        return None


def close_match(screener_last, canonical_close):
    a=parse_num(screener_last)
    b=parse_num(canonical_close)
    if a is None or b is None or a<=0 or b<=0:
        return False, None
    diff=abs(a-b)
    tol=max(CLOSE_ABS_TOL,CLOSE_REL_TOL*max(abs(a),abs(b)))
    return diff<=tol, {"abs_diff":diff,"tolerance":tol}


def fetch_rows():
    params={
        "tableonly":"true",
        "limit":"25",
        "offset":"0",
        "exchange":"NASDAQ",
        "download":"true",
    }
    url=URL+"?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={
        "User-Agent":UA,
        "Accept":"application/json,text/plain,*/*",
        "Origin":"https://www.nasdaq.com",
        "Referer":"https://www.nasdaq.com/market-activity/stocks/screener",
    })
    with urllib.request.urlopen(req,timeout=60) as r:
        obj=json.loads(r.read().decode("utf-8"))
        final_url=str(r.geturl())
    data=obj.get("data") or {}
    rows=data.get("rows") or ((data.get("table") or {}).get("rows") or [])
    if len(rows)<1000:
        raise RuntimeError(f"NASDAQ_SCREENER_TOO_FEW_ROWS:{len(rows)}")
    return rows,final_url


def build_state(rows,price_state,now_utc=None,source_url=URL):
    now_utc=now_utc or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        raise RuntimeError("CAPTURE_TIME_MUST_BE_TZ_AWARE")
    now_utc=now_utc.astimezone(timezone.utc)
    now_et=now_utc.astimezone(NY)
    asof=str(price_state.get("asof_et") or "")
    if not asof:
        raise RuntimeError("PRICE_ASOF_MISSING")
    if price_state.get("execution")!="NONE" or price_state.get("real_money")!="NO-GO":
        raise RuntimeError("PRICE_SAFETY_MISMATCH")
    if price_state.get("unknown_never_pass") is not True:
        raise RuntimeError("PRICE_UNKNOWN_POLICY_MISMATCH")

    pass_symbols=sorted(set(str(x).upper() for x in (price_state.get("pass_symbols") or []) if str(x)))
    results=price_state.get("results") or {}
    row_by_symbol={}
    for row in rows:
        sym=str((row or {}).get("symbol") or "").strip().upper()
        if sym:
            row_by_symbol[sym]=row

    same_session_post_close=(
        now_et.date().isoformat()==asof
        and now_et.timetz().replace(tzinfo=None)>=POST_CLOSE_FLOOR
    )

    scoped={}
    eligible=[]
    reasons={}
    for sym in pass_symbols:
        src=row_by_symbol.get(sym)
        canonical_close=parse_num((((results.get(sym) or {}).get("info") or {}).get("price")))
        if src is None:
            reason="NASDAQ_SCREENER_SYMBOL_MISSING"
            scoped[sym]={
                "status":"UNKNOWN",
                "reason":reason,
                "canonical_rth_close":canonical_close,
                "shadow_eligible":False,
            }
            reasons[reason]=reasons.get(reason,0)+1
            continue

        last=parse_num(src.get("lastsale"))
        mc=parse_num(src.get("marketCap"))
        matched,match_meta=close_match(last,canonical_close)
        if not same_session_post_close:
            reason="CAPTURE_NOT_SAME_ASOF_POST_CLOSE"
        elif canonical_close is None:
            reason="CANONICAL_RTH_CLOSE_MISSING"
        elif last is None:
            reason="NASDAQ_LASTSALE_MISSING"
        elif mc is None or mc<=0:
            reason="NASDAQ_MARKET_CAP_MISSING_OR_NONPOSITIVE"
        elif not matched:
            reason="NASDAQ_LASTSALE_RTH_CLOSE_MISMATCH"
        else:
            reason=None

        rec={
            "status":"SHADOW_ELIGIBLE" if reason is None else "UNKNOWN",
            "reason":reason,
            "shadow_eligible":reason is None,
            "canonical_rth_close":canonical_close,
            "nasdaq_lastsale":last,
            "nasdaq_market_cap_usd":mc,
            "close_match":bool(matched),
            "close_match_meta":match_meta,
        }
        if reason is None:
            implied_shares=mc/last
            rec["implied_shares_from_screener"]=implied_shares
            rec["rebased_market_cap_usd"]=implied_shares*canonical_close
            rec["eligible_asof_et"]=asof
            eligible.append(sym)
        else:
            reasons[reason]=reasons.get(reason,0)+1
        scoped[sym]=rec

    return {
        "schema":"XRAY_NASDAQ_SCREENER_PIT_SHADOW_V1",
        "execution":"NONE",
        "real_money":"NO-GO",
        "unknown_never_pass":True,
        "alpha_authority":False,
        "production_mc_authority_changed":False,
        "source":"NASDAQ_PUBLIC_SCREENER",
        "source_url":source_url,
        "retrieved_at_utc":now_utc.isoformat(),
        "retrieved_at_et":now_et.isoformat(),
        "asof_et":asof,
        "same_session_post_close":same_session_post_close,
        "close_match_abs_tolerance_usd":CLOSE_ABS_TOL,
        "close_match_relative_tolerance":CLOSE_REL_TOL,
        "scope_kind":"CANONICAL_PRICE_DV30_PASS_ONLY",
        "scope_count":len(pass_symbols),
        "eligible_count":len(eligible),
        "eligible_symbols":eligible,
        "unknown_count":len(pass_symbols)-len(eligible),
        "reason_counts":dict(sorted(reasons.items())),
        "records":scoped,
        "policy_note":"SHADOW ONLY. A row is eligible only for zero-dollar PIT research when captured after the regular close on the same ASOF and Nasdaq last sale matches the canonical completed RTH close. No row can create C4.17 production MC PASS.",
    }


def canonical_bytes(obj):
    return (json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode("utf-8")


def write_outputs(state):
    CURRENT.write_bytes(canonical_bytes(state))
    if state.get("same_session_post_close") is not True:
        return None
    ARCHIVE_DIR.mkdir(parents=True,exist_ok=True)
    stamp=datetime.fromisoformat(str(state["retrieved_at_utc"])).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p=ARCHIVE_DIR/f"nasdaq_screener_pit_{state['asof_et'].replace('-','')}_{stamp}.json"
    payload=canonical_bytes(state)
    if p.exists():
        if p.read_bytes()!=payload:
            raise RuntimeError("PIT_ARCHIVE_IMMUTABILITY_VIOLATION")
    else:
        p.write_bytes(payload)
    return p


def main():
    price=json.loads(PRICE.read_text(encoding="utf-8"))
    rows,source_url=fetch_rows()
    state=build_state(rows,price,source_url=source_url)
    archive=write_outputs(state)
    print(json.dumps({
        "status":"PASS",
        "asof_et":state["asof_et"],
        "same_session_post_close":state["same_session_post_close"],
        "scope_count":state["scope_count"],
        "eligible_count":state["eligible_count"],
        "unknown_count":state["unknown_count"],
        "archive":str(archive) if archive else None,
    },sort_keys=True))


if __name__=="__main__":
    main()
