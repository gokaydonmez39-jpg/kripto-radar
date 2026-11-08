#!/usr/bin/env python3
"""Independent Cove-method-inspired bracket/robustness research for personal 477.

NOT Cove Trader code or a NinjaTrader plugin. No broker, live orders, API requests,
Sheets writes, notifications, alpha certification or modification of XRAY AL/STOP.
Only deterministic, read-only analysis of a privately supplied verified-format
bundle. Source authority, PIT legality and OOS remain external HOLD gates.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
import argparse
import hashlib
import json
import math
from pathlib import Path

import exchange_calendars as ec
import engine
import runner

INPUT_SCHEMA="XRAY_COVE_METHOD_SHADOW_INPUT_V1"
OUTPUT_SCHEMA="XRAY_COVE_METHOD_SHADOW_RESULT_V1"
EXPECTED=477
MAX_BARS=180
MAX_EPISODES=477*15
MAX_SENSITIVITY=12
MAX_HOLD_SESSIONS=15
ALLOWED_FEED="ALPACA_IEX_DAILY_RAW_1DAY"
CALENDAR="XNAS"
VALID_DECISIONS=frozenset(("GAP_BELOW_STOP_OPEN_PROXY",
    "GAP_ABOVE_TARGET_OPEN_PROXY","BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS",
    "STOP_TOUCHED","TARGET_TOUCHED","TIME_EXIT_CLOSE_PROXY","OPEN"))
TERMINAL_WINS=frozenset(("TARGET_TOUCHED","GAP_ABOVE_TARGET_OPEN_PROXY"))
TERMINAL_AMBIGUOUS="BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS"


def require(ok,reason):
    if not ok:
        raise ValueError("COVE_SHADOW_"+reason)


def number(value):
    return type(value) in (int,float) and math.isfinite(value)


def session_date(text,reason):
    require(type(text) is str and len(text)==10,reason)
    try:
        parsed=date.fromisoformat(text)
    except ValueError:
        raise ValueError("COVE_SHADOW_"+reason) from None
    require(parsed.isoformat()==text,reason)
    return text


def _validate_cost(bps,commission,multipliers):
    require(number(bps) and 0<=bps<=1000,"INVALID_COST")
    require(number(commission) and 0<=commission<=50,"INVALID_COST")
    require(type(multipliers) in (tuple,list) and
            1<=len(multipliers)<=MAX_SENSITIVITY,"INVALID_MULTIPLIERS")
    require(all(number(x) and 0.2<=x<=3.0 for x in multipliers),
            "INVALID_MULTIPLIERS")
    require(1.0 in multipliers and len(set(multipliers))==len(multipliers),
            "INVALID_MULTIPLIERS")


def _validate_bar(symbol,bar,asof,calendar):
    require(type(bar) is dict,"BAD_BAR_SCHEMA")
    timestamp=bar.get("timestamp")
    require(type(timestamp) is str,"BAD_BAR_TIMESTAMP")
    try:
        instant=datetime.fromisoformat(timestamp.replace("Z","+00:00"))
    except ValueError:
        raise ValueError("COVE_SHADOW_BAD_BAR_TIMESTAMP") from None
    require(instant.tzinfo is not None,"BAD_BAR_TIMESTAMP")
    day=timestamp[:10]
    session_date(day,"BAD_BAR_DATE")
    require(day<=asof,"FUTURE_BAR")
    require(calendar.is_session(day),"NON_XNAS_BAR")
    vals=[bar.get(k) for k in ("open","high","low","close","volume")]
    require(all(number(x) and x>0 for x in vals),"INVALID_OHLC")
    o,h,l,c,_=vals
    require(l<=o<=h and l<=c<=h,"INVALID_OHLC")
    return day


def _bars_for_symbol(symbol,bars,asof,calendar):
    require(type(bars) is list and len(bars)<=MAX_BARS,"BAD_BARS_LENGTH")
    days={}
    for b in bars:
        d=_validate_bar(symbol,b,asof,calendar)
        require(d not in days,"DUPLICATE_BAR")
        days[d]=b
    ordered=sorted(days)
    require(len(ordered)>=52 and ordered[-1]==asof,
            "NONCONTIGUOUS_52_XNAS")
    recent=ordered[-52:]
    expected=[str(x.date()) for x in calendar.sessions_in_range(recent[0],asof)]
    require(recent==expected,"NONCONTIGUOUS_52_XNAS")
    return days


def _validate_episode(ep,symbols,asof,calendar,bar_days):
    require(type(ep) is dict,"BAD_EPISODE_SCHEMA")
    day=session_date(ep.get("asof_et"),"BAD_EPISODE_ASOF")
    require(calendar.is_session(day),"BAD_EPISODE_ASOF")
    require(day<=asof,"FUTURE_EPISODE")
    symbol=ep.get("symbol")
    require(type(symbol) is str and symbol in symbols and
            ep.get("id")==day+"|"+symbol,"BAD_EPISODE_IDENTITY")
    require(day in bar_days,"MISSING_ENTRY_BAR")
    entry=ep.get("reference_close")
    stop=ep.get("stop")
    target=ep.get("target_2r")
    require(all(number(x) and x>0 for x in (entry,stop,target))
            and stop<entry<target,"INVALID_LEVEL_GEOMETRY")
    require(abs(target-(entry+2*(entry-stop)))<=0.025,"NON_2R_LEVEL")
    require(abs(float(bar_days[day]["close"])-entry)<=0.005,
            "ENTRY_SOURCE_CLOSE_MISMATCH")
    return day,symbol,entry,stop,target


def _path(ep,bar_days,completed_days,stop,target,bps,commission):
    entry=ep["reference_close"]
    risk=entry-stop
    require(risk>0,"INVALID_RISK")
    status="OPEN"
    terminal_day=None
    min_exit=max_exit=None
    seen=0
    for day in completed_days:
        seen+=1
        bar=bar_days[day]
        o,h,l,c=(bar[x] for x in ("open","high","low","close"))
        if o<=stop:
            status="GAP_BELOW_STOP_OPEN_PROXY"
            min_exit=max_exit=o
        elif o>=target:
            status="GAP_ABOVE_TARGET_OPEN_PROXY"
            min_exit=max_exit=o
        elif l<=stop and h>=target:
            status=TERMINAL_AMBIGUOUS
            min_exit,max_exit=stop,target
        elif l<=stop:
            status="STOP_TOUCHED"
            min_exit=max_exit=stop
        elif h>=target:
            status="TARGET_TOUCHED"
            min_exit=max_exit=target
        elif seen==MAX_HOLD_SESSIONS:
            status="TIME_EXIT_CLOSE_PROXY"
            min_exit=max_exit=c
        if status!="OPEN":
            terminal_day=day
            break
    require(status in VALID_DECISIONS,"UNKNOWN_PATH_STATE")
    if status=="OPEN":
        return {"status":status,"completed":False,"ambiguous":False,
                "min_net_r":None,"max_net_r":None,"day":None}
    # Entry and exit bps are *hypothetical* per-share friction proxies;
    # no claim of an executable, consolidated fill.
    def net_r(exit_proxy):
        friction=(entry+exit_proxy)*bps/10000.0+2*commission
        return (exit_proxy-entry-friction)/risk
    return {"status":status,"completed":True,
            "ambiguous":status==TERMINAL_AMBIGUOUS,
            "min_net_r":net_r(min_exit),"max_net_r":net_r(max_exit),
            "day":terminal_day}


def _wilson(successes,total):
    if total==0:
        return None
    z=1.959963984540054
    p=successes/total
    denominator=1+z*z/total
    center=(p+z*z/(2*total))/denominator
    radius=z*math.sqrt((p*(1-p)+z*z/(4*total))/total)/denominator
    return {"lower":round(max(0.,center-radius),6),
            "upper":round(min(1.,center+radius),6),
            "n":total,"target_first_n":successes}


def _summarize(paths,total):
    counts=Counter(p["status"] for p in paths)
    completed=[p for p in paths if p["completed"]]
    definitive=[p for p in completed if not p["ambiguous"]]
    wins=sum(p["status"] in TERMINAL_WINS for p in definitive)
    def avg(key):
        return round(sum(x[key] for x in completed)/len(completed),6) if completed else None
    if not total:
        state="HOLD_NO_EPISODES"
    elif not completed:
        state="HOLD_NO_CLOSED_EPISODES"
    else:
        state="DESCRIPTIVE_ONLY_NOT_PIT_OOS"
    return {"status":state,"episodes":total,"completed":len(completed),
            "unresolved_open":counts.get("OPEN",0),
            "ambiguous":counts.get(TERMINAL_AMBIGUOUS,0),
            "gap_proxy_cases":counts.get("GAP_BELOW_STOP_OPEN_PROXY",0)
                               +counts.get("GAP_ABOVE_TARGET_OPEN_PROXY",0),
            "terminal_counts":dict(sorted(counts.items())),
            "net_r_min_mean":avg("min_net_r"),
            "net_r_max_mean":avg("max_net_r"),
            "wilson_win_rate_95pct":_wilson(wins,len(definitive)),
            "real_fills_verified":False,
            "open_trade_pnl_assumed":False}


def run_bundle(bundle,*,slippage_bps=0.0,commission_per_share=0.0,
               stop_multipliers=(0.8,1.0,1.2)):
    """Pure offline, provenance-constrained analysis; no fetching, writes or trades.

    Input self-attestation alone is NOT independent vendor or Sheet evidence.
    The caller must custody the original IEX raw and private sheet receipts.
    """
    _validate_cost(slippage_bps,commission_per_share,stop_multipliers)
    require(type(bundle) is dict and bundle.get("schema")==INPUT_SCHEMA,
            "BAD_INPUT_SCHEMA")
    asof=session_date(bundle.get("asof_et"),"BAD_ASOF")
    engine.validate_asof(asof)  # official session and completed-clock gate
    require(bundle.get("feed")==ALLOWED_FEED,"SOURCE_FEED_DRIFT")
    counts=bundle.get("source_counts")
    require(type(counts) is dict and
            counts.get("requested")==EXPECTED and
            counts.get("processed")==EXPECTED and
            counts.get("valid")==EXPECTED and
            counts.get("missing")==0 and
            counts.get("final") is True,
            "SOURCE_NOT_477_FINAL")
    scope=sorted(runner.get_scope(
        watchlist_file=str(Path(__file__).with_name("nasdaq_watchlist_477.json")),
        asof=asof))
    require(len(scope)==EXPECTED and len(set(scope))==EXPECTED,
            "SOURCE_SCOPE_NOT_477")
    require(bundle.get("scope_sha256")==runner.sha_symbols(scope) and
            bundle.get("algorithm_sha256")==runner.analysis_fingerprint(),
            "SHA_MISMATCH")
    episodes=bundle.get("episodes")
    raw=bundle.get("bars_by_symbol")
    require(type(episodes) is list and len(episodes)<=MAX_EPISODES,
            "EPISODES_NOT_LIST_OR_BOUNDED")
    require(type(raw) is dict,"BAD_PROVIDER_BUNDLE")
    symbol_set=set(scope)
    # Avoid an unrequested ticker or undisclosed extra data, even for an
    # apparently benign empty-episode case.
    ep_symbols=set()
    keys=set()
    for ep in episodes:
        require(type(ep) is dict,"BAD_EPISODE_SCHEMA")
        ident=ep.get("id")
        require(type(ident) is str and ident not in keys,"DUPLICATE_EPISODE")
        keys.add(ident)
        sym=ep.get("symbol")
        require(type(sym) is str and sym in symbol_set and
                ident==str(ep.get("asof_et"))+"|"+sym,
                "BAD_EPISODE_IDENTITY")
        ep_symbols.add(sym)
    require(set(raw).issubset(ep_symbols),"UNREQUESTED_BARS")
    require(set(raw)==ep_symbols,"MISSING_SYMBOL_BARS")
    calendar=ec.get_calendar(CALENDAR)
    verified={sym:_bars_for_symbol(sym,raw[sym],asof,calendar)
              for sym in sorted(ep_symbols)}
    prepared=[]
    for ep in episodes:
        day,symbol,entry,stop,target=_validate_episode(
            ep,symbol_set,asof,calendar,verified[ep["symbol"]])
        due=[str(x.date()) for x in calendar.sessions_in_range(day,asof)
             if str(x.date())>day][:MAX_HOLD_SESSIONS]
        require(all(x in verified[symbol] for x in due),
                "MISSING_FOLLOWUP_SESSION")
        prepared.append((ep,verified[symbol],due,entry,stop,target))
    baseline=[]
    for ep,bars,due,entry,stop,target in prepared:
        baseline.append(_path(ep,bars,due,stop,target,slippage_bps,
                              commission_per_share))
    baseline_summary=_summarize(baseline,len(prepared))
    comparison=[]
    for multiplier in stop_multipliers:
        paths=[]
        for ep,bars,due,entry,stop,target in prepared:
            base_risk=entry-stop
            hypothetical_stop=entry-base_risk*multiplier
            hypothetical_target=entry+2*base_risk*multiplier
            # A 3x or wider stop could move <=0 for very volatile entries.
            require(hypothetical_stop>0,"COUNTERFACTUAL_STOP_NONPOSITIVE")
            paths.append(_path(ep,bars,due,hypothetical_stop,
                               hypothetical_target,slippage_bps,
                               commission_per_share))
        comparison.append({"stop_risk_multiplier":multiplier,
                           "summary":_summarize(paths,len(prepared))})
    # Only the canonical 1.0 pass is the base engine's 2R path; all other
    # figures are counterfactual DIAGNOSTICS, not parameter recommendations.
    try:
        custody=hashlib.sha256(json.dumps(bundle,sort_keys=True,
            ensure_ascii=False,allow_nan=False,
            separators=(",",":")).encode("utf-8")).hexdigest()
    except (TypeError,ValueError):
        raise ValueError("COVE_SHADOW_BAD_INPUT_JSON") from None
    return {"schema":OUTPUT_SCHEMA,"asof_et":asof,"scope":EXPECTED,
            "feed":ALLOWED_FEED,"source_bundle_sha256":custody,
            "data_authority":"SUPPLIED_BUNDLE_NOT_INDEPENDENT_RECEIPT",
            "alpha_claim":"HOLD_UNVERIFIED_PIT_OOS",
            "real_execution":"NONE","orders":False,"writes":False,
            "notifications":False,"historical_replay":False,
            "slippage_bps_each_side":slippage_bps,
            "commission_per_share_each_side":commission_per_share,
            "baseline":baseline_summary,
            "robustness":{"baseline_multiplier":1.0,
                 "counterfactual":comparison,
                 "recommendation":"NONE_DIAGNOSTIC_ONLY"},
            "limitations":["Single-exchange IEX OHLC not consolidated SIP",
                "Same-day both-touch intrabar ordering unknowable from 1Day bars",
                "Gap and costs are research price proxies, not broker fills",
                "No independent PIT issuer/rights/3x31 OOS or paper-trade proof",
                "Cove Trader source/library/product not installed"]}


def main(argv=None):
    parser=argparse.ArgumentParser(
        description="Private input bundle -> research-only aggregate JSON; no trade")
    parser.add_argument("--input",required=True,
                        help="Path to private input bundle JSON; never public-commit it")
    parser.add_argument("--slippage-bps",type=float,default=0.0)
    parser.add_argument("--commission-per-share",type=float,default=0.0)
    args=parser.parse_args(argv)
    try:
        data=json.loads(Path(args.input).read_text(encoding="utf-8"))
        result=run_bundle(data,slippage_bps=args.slippage_bps,
                          commission_per_share=args.commission_per_share)
    except (ValueError,TypeError,KeyError,PermissionError,OSError):
        # Private input, symbol, bar and financial details are never logged.
        print(json.dumps({"status":"COVE_SHADOW_HOLD_BAD_OR_UNATTESTED_INPUT",
                          "orders":False,"writes":False,"alpha_claim":"HOLD"}))
        return 3
    # No episode identities or provider bars are emitted in public logs.
    print(json.dumps(result,sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
