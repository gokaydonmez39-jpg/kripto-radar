"""XRAY NASDAQ Personal 477 NEON V3 research shadow, no trading or alerts.

Runs only on the original 477 IEX RAW 1Day batch reads already made by
runner.scan. The result is a private ephemeral file, never a public artifact,
Sheet write, signal, card, push, or EOD/source attestation. Experimental model.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import hashlib
import json
import math
import os
import re
from bisect import bisect_left, bisect_right
from statistics import mean, stdev

import exchange_calendars as ec

WEIGHTS = {"trend": ".30", "momentum": ".25", "relative_strength": ".20",
           "volatility_safety": ".15", "continuity": ".10"}
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.]{0,15}$")
SHA = re.compile(r"^[a-f0-9]{64}$")


class NeonHold(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise NeonHold(code)


def positive(x):
    return type(x) in (int, float) and math.isfinite(x) and x > 0


def clamp(x):
    return min(100., max(0., x))


def scope_digest(master):
    require(type(master) is list and len(master) == 477 and
            len(set(master)) == 477 and
            all(type(s) is str and SYMBOL.fullmatch(s) for s in master),
            "MASTER_NOT_EXACT_477")
    return hashlib.sha256(("\n".join(master) + "\n").encode("ascii")).hexdigest()


def session_dates(asof, now_utc):
    require(type(asof) is str and re.fullmatch(r"20\d\d-\d\d-\d\d", asof),
            "BAD_ASOF")
    require(isinstance(now_utc, datetime) and now_utc.tzinfo is not None and
            now_utc.utcoffset() is not None, "UNVERIFIED_CLOCK")
    cal = ec.get_calendar("XNAS")
    require(cal.is_session(asof), "NOT_XNAS_SESSION")
    cutoff = cal.session_close(asof).to_pydatetime().astimezone(timezone.utc) + timedelta(minutes=45)
    now = now_utc.astimezone(timezone.utc)
    require(cutoff <= now <= cutoff + timedelta(hours=10), "OUTSIDE_NATURAL_SOURCE_WINDOW")
    return [x.date().isoformat() for x in cal.sessions_window(asof, -52)]


def validated_bars(symbol, provided, dates):
    require(type(provided) is list and len(provided) >= 52, "RAW_BARS_INCOMPLETE")
    days = {}
    for bar in provided:
        require(type(bar) is dict and type(bar.get("timestamp")) is str,
                "RAW_BAR_SCHEMA_INVALID")
        try:
            stamp = datetime.fromisoformat(bar["timestamp"].replace("Z", "+00:00"))
        except (ValueError, TypeError) as exc:
            raise NeonHold("RAW_BAR_TIMESTAMP_INVALID") from exc
        require(stamp.tzinfo is not None and stamp.utcoffset() is not None,
                "RAW_BAR_TIMESTAMP_NAIVE")
        # Normalize to UTC before assigning any official XNAS session date.
        # A calendar-date prefix in a different offset is not authoritative.
        day = stamp.astimezone(timezone.utc).date().isoformat()
        require(day <= dates[-1], "RAW_BAR_FROM_FUTURE")
        if day < dates[0]:
            continue
        require(day not in days, "DUPLICATE_RAW_BAR_SESSION")
        require(all(positive(bar.get(k)) for k in ("open", "high", "low", "close", "volume")),
                "RAW_BAR_NONFINITE_OR_MISSING")
        require(bar["low"] <= min(bar["open"], bar["close"]) <=
                max(bar["open"], bar["close"]) <= bar["high"],
                "RAW_BAR_OHLC_GEOMETRY")
        days[day] = bar
    require(sorted(days) == dates, "RAW_BAR_52_XNAS_GAP")
    return [days[d] for d in dates]


def indicators(bars):
    close = [r["close"] for r in bars]
    ma20, ma50 = mean(close[-20:]), mean(close[-50:])
    older_ma20 = mean(close[-25:-5])
    previous_high20 = max(r["high"] for r in bars[-21:-1])
    diffs = [close[i] - close[i-1] for i in range(38, 52)]
    up = sum(max(v, 0) for v in diffs)
    down = sum(max(-v, 0) for v in diffs)
    rsi = 100. if down == 0 else 100. - 100. / (1. + up / down)
    tr = [max(bars[i]["high"] - bars[i]["low"],
              abs(bars[i]["high"] - close[i-1]),
              abs(bars[i]["low"] - close[i-1])) for i in range(38, 52)]
    atr = mean(tr)
    average_volume20 = mean(r["volume"] for r in bars[-21:-1])
    require(positive(atr) and positive(average_volume20), "RAW_ATR_OR_VOLUME_INVALID")
    persistence = sum(close[i] > mean(close[i-19:i+1]) for i in range(47, 52)) / 5
    return {"close": close[-1], "sma20": ma20, "sma50": ma50,
            "older_sma20": older_ma20, "prior_high20": previous_high20,
            "rsi14": rsi, "atr14": atr,
            "rvol20": bars[-1]["volume"] / average_volume20,
            "return20": close[-1] / close[-21] - 1.,
            "continuity": 100. * persistence,
            "iex_dollar_volume20": close[-1] * average_volume20,
            "last_timestamp": bars[-1]["timestamp"]}


def compare_snapshot(row, m):
    for source, observed, tolerance in (
        ("close", m["close"], .00051),
        ("atr14", m["atr14"], .00051),
        ("sma20", m["sma20"], .00051),
        ("sma50", m["sma50"], .00051),
        ("prior_high20", m["prior_high20"], .00051),
        ("rsi14", m["rsi14"], .0051),
        ("relative_iex_volume", m["rvol20"], .00051)):
        # RSI=0 is a valid observed downtrend, not missing market data.
        valid = (type(row.get(source)) in (int, float) and
                 math.isfinite(row[source]) and
                 (row[source] >= 0 if source == "rsi14" else row[source] > 0))
        require(valid and abs(row[source] - observed) <= tolerance,
                "SNAPSHOT_INDICATOR_DRIFT")
    if row["decision"] == "AL":
        ref, atr = row["close"], row["atr14"]
        require(ref >= 5 and 0 < 2*atr/ref <= .08 and
                45 <= row["rsi14"] <= 75 and row["relative_iex_volume"] >= 1.3 and
                ref >= row["sma20"] >= row["sma50"] > 0 and
                ref >= row["prior_high20"] > 0 and
                m["iex_dollar_volume20"] >= 500000,
                "SOURCE_AL_POLICY_DRIFT")
        stop, target = row.get("indicative_stop"), row.get("indicative_target_2r")
        require(positive(stop) and positive(target) and stop < ref < target and
                abs(stop - (ref - 2*atr)) <= .005 and
                abs(target - (ref + 2*(ref-stop))) <= .005,
                "SOURCE_AL_STOP_2R_DRIFT")


def evaluate(snapshot, master, raw_by_symbol, *, expected_policy_sha, now_utc, source_event):
    """Pure fail-closed computation. A score cannot create a new AL event."""
    scope_sha = scope_digest(master)
    require(type(expected_policy_sha) is str and SHA.fullmatch(expected_policy_sha),
            "EXPECTED_POLICY_SHA_INVALID")
    require(type(snapshot) is dict and snapshot.get("schema") == "XRAY_PERSONAL_SWING_V3" and
            snapshot.get("feed") == "ALPACA_IEX_DAILY_ONE_EXCHANGE", "SNAPSHOT_SCHEMA_OR_FEED")
    require(snapshot.get("scope_sha256") == scope_sha and
            snapshot.get("analysis_fingerprint_sha256") == expected_policy_sha,
            "SNAPSHOT_SCOPE_OR_POLICY_SHA_DRIFT")
    require(source_event in ("schedule", "workflow_dispatch"), "SHADOW_SOURCE_EVENT_UNTRUSTED")
    require(snapshot.get("valid_data_coverage_complete") is True and
            snapshot.get("new_signal_publishable") is True and
            snapshot.get("not_broker") is True and
            snapshot.get("auto_trading") is False and
            snapshot.get("orders_sent") == 0 and
            snapshot.get("failed_groups") == [], "SNAPSHOT_NOT_FINAL_SAFE")
    for key in ("requested_symbols", "processed_symbols", "valid_data_symbols"):
        require(type(snapshot.get(key)) is int and snapshot[key] == 477,
                "SNAPSHOT_COVERAGE_NOT_477")
    require(snapshot.get("remaining_symbols") == 0 and
            snapshot.get("insufficient_data_symbols") == 0, "SNAPSHOT_MISSING_ROWS")
    asof = snapshot.get("asof_et")
    dates = session_dates(asof, now_utc)
    require(type(raw_by_symbol) is dict and set(raw_by_symbol) == set(master),
            "RAW_BAR_UNIVERSE_INCOMPLETE")
    originals = snapshot.get("rows")
    require(type(originals) is list and len(originals) == 477 and
            all(type(r) is dict and r.get("asof_et") == asof and
                r.get("decision") in ("AL", "IZLE", "ELE") for r in originals),
            "SNAPSHOT_ROWS_INVALID")
    counts = snapshot.get("counts")
    require(type(counts) is dict and counts.get("START") == 477 and
            counts.get("TEKNIK_AL_ADAYI") == sum(r["decision"] == "AL" for r in originals) and
            counts.get("YAKIN_IZLE") == sum(r["decision"] == "IZLE" for r in originals) and
            counts.get("ELE") == sum(r["decision"] == "ELE" for r in originals) and
            counts.get("VERI_YETERSIZ") == 0, "SNAPSHOT_COUNTS_DRIFT")
    by_symbol = {r.get("symbol"):r for r in originals}
    require(len(by_symbol) == 477 and set(by_symbol) == set(master),
            "SNAPSHOT_ROWS_DUPLICATE_OR_MISSING")
    measures = {}
    for symbol in master:
        bars = validated_bars(symbol, raw_by_symbol[symbol], dates)
        measured = indicators(bars)
        compare_snapshot(by_symbol[symbol], measured)
        measures[symbol] = measured
    returns = sorted(m["return20"] for m in measures.values())
    output = []
    for symbol in master:
        m, source = measures[symbol], by_symbol[symbol]
        rel = 100*(bisect_left(returns, m["return20"]) +
                   (bisect_right(returns, m["return20"]) -
                    bisect_left(returns, m["return20"]) - 1)/2)/(477-1)
        factors = {"trend": 25. * sum((m["close"] > m["sma20"],
                                       m["sma20"] > m["sma50"],
                                       m["sma20"] > m["older_sma20"],
                                       m["close"] > m["prior_high20"])),
                   "momentum": clamp(100. - 2.5 * abs(m["rsi14"] - 60.)),
                   "relative_strength": rel,
                   "volatility_safety": clamp(100*(1.-(2*m["atr14"]/m["close"])/.08)),
                   "continuity": m["continuity"]}
        require(all(math.isfinite(v) and 0 <= v <= 100 for v in factors.values()),
                "SCORE_FACTOR_INVALID")
        rounded = {k: round(v, 4) for k,v in factors.items()}
        score = sum(Decimal(str(rounded[k])) * Decimal(w) for k,w in WEIGHTS.items())
        score = score.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
        status = "SOURCE_AL_NOT_DELIVERY_AUTHORITY" if source["decision"] == "AL" else "NO_NEW_AL"
        corridor = "HOLD_OUTBOX_NOT_ATTESTED" if source["decision"] == "AL" else (
            "YAKINDAN_IZLE" if score >= 75 else "BEKLE")
        output.append({"symbol":symbol, "score":str(score), "score_delta":None,
                       "factors":rounded, "rank":None,
                       "decision_corridor":corridor,
                       "source_decision":source["decision"], "signal_status":status,
                       "bar_asof":asof, "last_valid_bar_time":m["last_timestamp"],
                       "liquidity": "PASS_IEX_SINGLE_VENUE" if m["iex_dollar_volume20"]>=500000
                       else "FAIL_IEX_SINGLE_VENUE",
                       "spread":"UNKNOWN", "gap":"UNKNOWN", "fills_guaranteed":False,
                       "source_event":source_event, "orders_sent":0})
    ranked = sorted(output, key=lambda r: (-Decimal(r["score"]), r["symbol"]))
    for i, row in enumerate(ranked,1):
        row["rank"] = i
    require(len(ranked) == 477 and len({r["symbol"] for r in ranked}) == 477,
            "SCORE_ROW_LOSS")
    return {"schema":"XRAY_NASDAQ_NEON_V3_EPHEMERAL_SHADOW_V1",
            "asof_et":asof, "scope_sha256":scope_sha,
            "policy_sha256":expected_policy_sha, "source_event":source_event,
            "model":"UNVALIDATED_5_FACTORS_30_25_20_15_10",
            "counts":{"master":477, "scored":477, "na":0,
                      "source_al_not_authorized_to_send":sum(r["source_decision"]=="AL" for r in ranked)},
            "source_attribution":"ORIGINAL_IEX_READ_BATCH_NO_NEW_NETWORK_CALL",
            "external_source_receipt":"NOT_INDEPENDENTLY_ATTESTED",
            "empirical_oos_verified":False,
            "chatgpt_card_written":False, "ios_push": "UNKNOWN", "iphone_ack":"UNKNOWN",
            "notification_sent":False,"orders_sent":0,
            "rows":ranked}


def risk_cohort_counts(master, raw_by_symbol, *, asof, now_utc):
    """Advisory aggregate counts on the existing exact 52-session capture.

    Sample standard deviation of last 20 simple close returns, annualized
    using sqrt(252). A >=10% negative open/previous-close discontinuity is a
    review flag, NOT a confirmed gap loss: corporate action and execution
    attribution remain UNKNOWN. The illustrative 60/10 percent thresholds
    are NOT a calibrated model, order gate, or ranking input.
    """
    scope_digest(master)
    dates = session_dates(asof, now_utc)
    require(len(dates) == 52, "RISK_CALENDAR_CONTRACT")
    require(type(raw_by_symbol) is dict and set(raw_by_symbol) == set(master),
            "RISK_CAPTURE_SCOPE")
    high = low = discontinuity = 0
    for symbol in master:
        bars = validated_bars(symbol, raw_by_symbol[symbol], dates)
        returns = [bars[i]["close"] / bars[i-1]["close"] - 1.
                   for i in range(1, len(bars))]
        vol = stdev(returns[-20:]) * math.sqrt(252.)
        minimum = min(bars[i]["open"] / bars[i-1]["close"] - 1.
                      for i in range(1, len(bars)))
        require(math.isfinite(vol) and math.isfinite(minimum), "RISK_NONFINITE")
        high += vol >= .60
        low += vol <= .10
        discontinuity += minimum <= -.10
    # Only cohort counts and source/authority labels leave this function.
    # Never emit symbol classifications, OHLCV, candidate IDs or trade levels.
    return {"schema": "XRAY_477_RISK_COUNTS_SHADOW_V1",
            "status": "COHORT_COUNTS_READY_RESEARCH_ONLY",
            "asof_et": asof, "symbols": 477, "sessions": len(dates),
            "high_vol20_count": high, "low_vol20_count": low,
            "negative_open_close_discontinuity_10_count": discontinuity,
            "vol20_thresholds": "ANNUALIZED_SAMPLE_STD_GE_0.60_LE_0.10",
            "basis": "ORIGINAL_IEX_CAPTURE_NOT_CONSOLIDATED",
            "corporate_action_clearance": "UNKNOWN", "spread": "UNKNOWN",
            "extra_market_requests": 0, "production_decision_authority": False,
            "orders_sent": 0, "notification_sent": False}


class Capture:
    """A tap on the existing provider call. Does not add a market-data request."""
    def __init__(self, provider, symbols, asof):
        require(callable(provider), "SOURCE_NOT_CALLABLE")
        scope_digest(symbols)
        self.provider, self.master, self.symbols, self.asof = provider, list(symbols), set(symbols), asof
        self.raw = {}
        self.capture_failed = False

    def read(self, symbols, asof):
        # The PRIMARY provider call retains its original exceptions/semantics.
        result = self.provider(symbols, asof)
        if self.capture_failed:
            return result
        try:
            if asof == self.asof and isinstance(result, dict):
                for symbol in symbols:
                    if symbol in self.symbols and isinstance(result.get(symbol), list):
                        self.raw[symbol] = result[symbol][-53:]
        except Exception:
            # Shadow-only extraction must not turn a successful IEX read into
            # primary runner failure or a half-trusted 477 factor result.
            self.raw.clear()
            self.capture_failed = True
        return result

    def finish(self, snapshot, *, expected_policy_sha, now_utc, source_event, output_file):
        require(not self.capture_failed, "RAW_CAPTURE_FAILED")
        result = evaluate(snapshot, self.master, self.raw,
                          expected_policy_sha=expected_policy_sha,
                          now_utc=now_utc, source_event=source_event)
        path = Path(output_file)
        payload = json.dumps(result,sort_keys=True,ensure_ascii=False,allow_nan=False)
        temp = path.with_suffix(path.suffix + '.tmp')
        temp.write_text(payload,encoding='utf-8')
        os.replace(temp,path)
        outcome = {"status":"NEON_SHADOW_477_READY_PRIVATE_NO_DELIVERY",
                   "scored":result["counts"]["scored"],"asof":result["asof_et"],
                   "orders_sent":0,"notification_sent":False}
        # Independent advisory failure boundary AFTER the original atomic NEON
        # file write. No extra provider read, no alteration of the NEON payload,
        # no extra Sheet write, no change to AL/score/Guardian/lease authority.
        risk = {"schema": "XRAY_477_RISK_COUNTS_SHADOW_V1",
                "status": "SKIPPED_NON_NATURAL", "production_decision_authority": False}
        if source_event == "schedule":
            try:
                risk = risk_cohort_counts(self.master, self.raw,
                                          asof=self.asof, now_utc=now_utc)
            except Exception:
                # Fixed redacted failure, never publish exception text/rows.
                risk = {"schema": "XRAY_477_RISK_COUNTS_SHADOW_V1",
                        "status": "HOLD_RISK_SHADOW", "production_decision_authority": False}
        outcome["risk_shadow"] = risk
        return outcome
