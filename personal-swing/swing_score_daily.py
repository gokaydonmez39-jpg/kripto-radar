#!/usr/bin/env python3
"""XRAY NASDAQ personal swing ranking V1: private, EOD-only, never an order.

Scoring is a technical *description*, NOT a calibrated probability of profit.
All 477-source provenance must match the existing immutable scan ledger.
Separate tab; no writes to EOD/AL/STOP/outbox/PANEL. No public signal output.
"""
import argparse
import hashlib
import json
import math
import os
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import daily_job
import engine
import private_lifecycle as life
import private_sheet_writer as writer
import runner

TAB = "SWING_SKOR_GUNLUK"
VERSION = "XRAY_SWING_SCORE_V1_20261105"
HEADER = (
    "KAYIT_KIMLIGI", "ASOF_ET", "EPIZOT_KIMLIGI", "SEMBOL", "KAYIT_TIPI",
    "SIRA", "SKOR_100", "TREND_20", "RSI_15", "RVOL_15", "REL_GUC_15",
    "LIKIDITE_10", "RISK_15", "FIYAT_YAPISI_10",
    "GUNCEL_IEX_CLOSE_USD", "ORIJINAL_REFERANS_USD", "ORIJINAL_STOP_USD",
    "ORIJINAL_HEDEF_2R_USD", "TEORIK_DEGISIM_YUZDE", "STOPA_MESAFE_YUZDE",
    "HEDEFE_MESAFE_YUZDE", "TAKIP_SEANSI", "RSI14", "RVOL20",
    "20SEANS_GETIRI_YUZDE", "RISK_NOTU", "KANIT_URL", "BILDIRIM_DURUMU",
    "BILDIRIM_ZAMANI_TR", "KAYIT_SHA256", "KAPSAM_SHA256",
    "ALGORITMA_SHA256", "SKOR_SURUMU", "ORT_IEX_DOLAR_HACMI",
    "ATR_RISK_YUZDE",
)
writer.require(len(HEADER) == 35, "SWING_SCORE_SCHEMA_INVALID")
READY = "READY_FOR_CHATGPT_DAILY_DIGEST"
REQUESTED = "REQUESTED_NOT_DEVICE_ACK"
MAX_OPEN = 4770
MAX_ROWS = 50000
SLUG = "https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/"

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def money(x):
    return "%.3f" % x

def percent(x):
    return "%.2f" % x

def build(candidate_values, scan_values, alert_values, asof, read_batch):
    """Pure function apart from caller-injected market bar reader."""
    writer.require(isinstance(asof, str) and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", asof),
                   "SWING_SCORE_BAD_ASOF")
    writer.require(date.fromisoformat(asof).isoformat() == asof, "SWING_SCORE_BAD_DATE")
    scans = writer.rows_only(scan_values, writer.SCAN_HEADER)
    writer.require(scans and scans[-1][0] == asof and
                   sum(r[0] == asof for r in scans) == 1,
                   "SWING_SCORE_LAST_SCAN_ASOF_DRIFT")
    scan = scans[-1]
    writer.require(writer.canonical_natural_scan_source(scan),
                   "SWING_SCORE_NON_NATURAL_SOURCE")
    writer.require(len(scan) >= 10 and
                   [writer.numeric(scan[i]) for i in (2, 3, 4, 5)] == [477, 477, 477, 0] and
                   str(scan[6]).upper() == "TRUE" and
                   str(scan[8]).startswith(SLUG),
                   "SWING_SCORE_SCAN_NOT_FINAL_477")
    scope = runner.get_scope(watchlist_file=str(Path(__file__).with_name(
        "nasdaq_watchlist_477.json")), asof=asof)
    scope_sha = runner.sha_symbols(scope)
    policy_sha = runner.analysis_fingerprint()
    proof = writer.scan_source_proof(scan[9])
    writer.require(proof["scopeSHA"] == scope_sha and
                   proof["algorithmSHA"] == policy_sha,
                   "SWING_SCORE_SOURCE_SHA_DRIFT")
    episodes = life.decode_open_episodes(candidate_values, asof)
    writer.require(len(episodes) <= MAX_OPEN, "SWING_SCORE_TOO_MANY_EPISODES")
    writer.require(isinstance(alert_values, list) and alert_values and
                   tuple(alert_values[0]) == life.ALERT_HEADER,
                   "SWING_SCORE_ALERT_HEADER_DRIFT")
    suppressed = set()
    seen_events = set()
    for row in alert_values[1:]:
        if not row or not row[0]:
            continue
        writer.require(len(row) >= 18 and row[0] not in seen_events,
                       "SWING_SCORE_ALERT_DUPLICATE")
        seen_events.add(row[0])
        if row[5] == "AL_NEW_EPISODE" and row[17] == "DUPLICATE_ACTIVE_EPISODE_NO_NEW_ALERT":
            suppressed.add(row[1])
    symbols = sorted(set(e["symbol"] for e in episodes))
    bars = read_batch(symbols, asof) if symbols else {}
    writer.require(isinstance(bars, dict), "SWING_SCORE_SOURCE_NOT_DICT")
    indicators = {}
    returns = {}
    for symbol in symbols:
        observations = bars.get(symbol)
        if not isinstance(observations, list):
            indicators[symbol] = None
            continue
        state = engine.analyze(symbol, observations, asof)
        if "close" not in state:
            indicators[symbol] = None
            continue
        ordered = sorted((x for x in observations if str(x.get("timestamp", ""))[:10] <= asof),
                         key=lambda x: x["timestamp"])
        writer.require(len(ordered) >= 52 and
                       str(ordered[-1]["timestamp"])[:10] == asof,
                       "SWING_SCORE_BAR_DATE_MISMATCH")
        ret = ordered[-1]["close"] / ordered[-21]["close"] - 1.
        if not math.isfinite(ret):
            indicators[symbol] = None
            continue
        volume20 = sum(x["volume"] for x in ordered[-21:-1]) / 20.
        ma20_old = sum(x["close"] for x in ordered[-25:-5]) / 20.
        indicators[symbol] = (state, ordered[-1], ret, volume20, ma20_old)
        returns[symbol] = ret
    # Unique-symbol cohort only: duplicated historical entries never distort percentiles.
    ranked_returns = sorted(returns.values())

    def component_score(symbol):
        state, last, ret, avg_vol, prior_ma20 = indicators[symbol]
        close = state["close"]
        ma20, ma50 = state["sma20"], state["sma50"]
        rsi, rvol = state["rsi14"], state["relative_iex_volume"]
        atr_risk = state["atr_risk_pct"]
        trend = (8 if close > ma20 else 0) + (6 if ma20 > ma50 else 0) + (6 if ma20 > prior_ma20 else 0)
        momentum = clamp(15 - abs(rsi - 62.) * 0.65, 0, 15)
        volume = clamp((rvol - 0.6) * 15 / 1.8, 0, 15)
        if len(ranked_returns) == 1:
            relstrength = 7.5
        else:
            below = sum(v < ret for v in ranked_returns)
            equal = sum(v == ret for v in ranked_returns)
            relstrength = 15 * (below + (equal - 1) / 2) / (len(ranked_returns) - 1)
        dollars = close * avg_vol
        liquid = clamp(10 * math.log10(max(dollars, 1) / 500000) / math.log10(20), 0, 10)
        risk = clamp((8 - atr_risk) * 15 / 6, 0, 15)
        prior_hi = state["prior_high20"]
        near = clamp(1 - (prior_hi - close) / prior_hi / 0.08, 0, 1)
        structure = 6 * near
        stretch = (close / ma20 - 1) if ma20 > 0 else -1
        structure += 4 if 0 <= stretch <= 0.08 else (2 if stretch > 0.08 else 0)
        parts = [trend, momentum, volume, relstrength, liquid, risk, structure]
        writer.require(all(math.isfinite(v) for v in parts), "SWING_SCORE_NONFINITE")
        return [round(p, 1) for p in parts], round(sum(parts), 1), dollars, ret, last

    prepared = []
    for e in episodes:
        symbol = e["symbol"]
        original = e["reference_close"]
        stop, target = e["stop"], e["target_2r"]
        tag = "ONCEKI_AL_BASKILANDI" if e["id"] in suppressed else "NORMAL_IZLEME"
        parts = [""] * 7
        score, last_close, dollar_volume, ret, lastbar = "", "", "", "", None
        if indicators[symbol] is None:
            tag += ";HOLD_VERI_YETERSIZ"
        else:
            parts, score, dollar_volume, ret, lastbar = component_score(symbol)
            last_close = indicators[symbol][0]["close"]
            # Tracker should have closed any prior-day STOP/2R hit already.
            # Opening-day bar is allowed, since AL only forms at its close.
            if e["days_held"] > 0 and (
                lastbar["low"] <= stop or lastbar["high"] >= target
            ):
                tag += ";HOLD_LIFECYCLE_VS_IEX_BAR"
                score = ""
                parts = [""] * 7
        pnl = percent((last_close / original - 1) * 100) if last_close != "" else ""
        stopgap = percent((last_close - stop) / last_close * 100) if last_close != "" else ""
        targetgap = percent((target - last_close) / last_close * 100) if last_close != "" else ""
        if last_close != "" and last_close <= stop:
            tag += ";GUNCEL_FIYAT_STOP_ALTINDA"
        prepared.append({
            "ep": e, "symbol": symbol, "score": score, "parts": parts,
            "last_close": last_close, "pnl": pnl, "stopgap": stopgap,
            "targetgap": targetgap, "ret": ret, "dollars": dollar_volume,
            "tag": tag, "state": indicators[symbol][0] if indicators[symbol] else None,
        })
    prepared.sort(key=lambda x: (x["score"] == "", -(x["score"] or 0),
                                 x["ep"]["id"]))
    scored = sum(item["score"] != "" for item in prepared)
    digest_data = [(x["ep"]["id"], x["score"], x["tag"], x["last_close"])
                   for x in prepared]
    digest = hashlib.sha256(json.dumps(
        {"asof": asof, "source": scope_sha, "policy": policy_sha,
         "rows": digest_data, "version": VERSION},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()

    def empty():
        return [""] * len(HEADER)
    result = []
    summary = empty()
    summary[0:7] = [asof + "|SUMMARY", asof, "", "", "SUMMARY",
                    str(len(episodes)), str(scored)]
    summary[7], summary[8] = str(len(episodes) - scored), str(len(symbols))
    summary[26:33] = [scan[8], READY, "", digest, scope_sha, policy_sha, VERSION]
    result.append(summary)
    rank = 0
    for item in prepared:
        e, st = item["ep"], item["state"]
        is_score = item["score"] != ""
        if is_score:
            rank += 1
        row = empty()
        row[0:7] = [asof + "|" + e["id"], asof, e["id"], e["symbol"],
                    "EPISODE", str(rank) if is_score else "HOLD",
                    str(item["score"]) if is_score else ""]
        row[7:14] = [str(x) if x != "" else "" for x in item["parts"]]
        row[14:22] = [
            money(item["last_close"]) if item["last_close"] != "" else "",
            money(e["reference_close"]), money(e["stop"]), money(e["target_2r"]),
            item["pnl"], item["stopgap"], item["targetgap"], str(e["days_held"])
        ]
        row[22:26] = [
            str(st["rsi14"]) if st else "",
            str(st["relative_iex_volume"]) if st else "",
            percent(item["ret"] * 100) if item["ret"] != "" else "",
            item["tag"]
        ]
        row[26:33] = [scan[8], "", "", digest, scope_sha, policy_sha, VERSION]
        row[33:35] = [
            money(item["dollars"]) if item["dollars"] != "" else "",
            str(st["atr_risk_pct"]) if st else ""
        ]
        writer.require(len(row) == len(HEADER), "SWING_SCORE_COL_COUNT")
        result.append(row)
    writer.require(len(result) == len(episodes) + 1, "SWING_SCORE_LOST_EPISODE")
    return result

def require_score_ledger(matrix, header, ready, requested, timestamp_check, require):
    """Validate without modifying rows. Header-only is a valid empty ledger.

    Google values API omits trailing empty cells; a row can therefore end at
    version (column 33). An interior blank row or malformed nonempty row is
    not silently dropped. Summary request is *not* device ACK. No inference of
    actual delivery, score validity, or historical receipt authenticity.
    """
    require(type(matrix) is list and bool(matrix) and
            type(matrix[0]) is list and tuple(matrix[0]) == tuple(header),
            "SWING_SCORE_HEADER_DRIFT")
    require(len(header) == 35, "SWING_SCORE_COL_COUNT")
    seen = set()
    for row in matrix[1:]:
        require(type(row) is list and 33 <= len(row) <= 35 and
                all(type(v) is str for v in row),
                "SWING_SCORE_LEDGER_ROW_SHAPE")
        key, asof, ep, symbol, kind = row[:5]
        valid_date = False
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", asof):
            try:
                valid_date = date.fromisoformat(asof).isoformat() == asof
            except ValueError:
                pass
        require(valid_date and bool(key) and key not in seen,
                "SWING_SCORE_LEDGER_IDENTITY")
        seen.add(key)
        require(all(re.fullmatch(r"[a-f0-9]{64}", row[i]) is not None
                    for i in (29, 30, 31)) and bool(row[32]),
                "SWING_SCORE_LEDGER_PIN")
        state, stamp = row[27:29]
        if kind == "SUMMARY":
            require(key == asof + "|SUMMARY" and ep == symbol == "",
                    "SWING_SCORE_LEDGER_IDENTITY")
            require((state == ready and stamp == "") or
                    (state == requested and timestamp_check(stamp, asof)),
                    "SWING_SCORE_LEDGER_DELIVERY")
        elif kind == "EPISODE":
            ep_asof, sep, ep_symbol = ep.partition("|")
            ep_date_valid = False
            if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", ep_asof):
                try:
                    ep_date_valid = date.fromisoformat(ep_asof).isoformat() == ep_asof
                except ValueError:
                    pass
            require(sep == "|" and ep_date_valid and ep_asof <= asof and
                    re.fullmatch(r"[A-Z][A-Z0-9.]{0,15}", symbol) is not None and
                    ep_symbol == symbol and key == asof + "|" + ep,
                    "SWING_SCORE_LEDGER_IDENTITY")
            require(state == stamp == "", "SWING_SCORE_LEDGER_DELIVERY")
        else:
            require(False, "SWING_SCORE_LEDGER_IDENTITY")
    return matrix


def score_read(api):
    # Read every occupied row, not merely the first 50,000. Google Sheets
    # appendCells extends the grid; truncated old ASOF keys would falsely
    # appear missing. Reject oversized ledgers instead of silently replaying.
    address = quote("'" + TAB + "'!A1:AI", safe="")
    matrix = api.request("/values/" + address +
                         "?valueRenderOption=FORMATTED_VALUE").get("values", [])
    writer.require(isinstance(matrix, list) and len(matrix) <= MAX_ROWS,
                   "SWING_SCORE_READ_CAPACITY_REACHED")
    return require_score_ledger(matrix, HEADER, READY, REQUESTED,
                                _request_timestamp, writer.require)


def normalize_rows(matrix):
    return [list(r) + [""] * (len(HEADER) - len(r)) for r in matrix]

def _request_timestamp(value, event_asof):
    """Validate canonical request timestamp; never infer transport/device ACK."""
    if type(value) is not str or type(event_asof) is not str:
        return False
    try:
        stamp = datetime.strptime(value, "%Y-%m-%d %H:%M TRT")
        day = date.fromisoformat(event_asof)
        return (stamp.strftime("%Y-%m-%d %H:%M TRT") == value and
                day.isoformat() == event_asof and stamp.date() >= day)
    except ValueError:
        return False


def _delivery_only_progress(before, after, *, score_ledger):
    """Exact immutable rows, one-way request transitions only; no ACK authority.

    The scoring algorithm uses an alert's identity and suppression class, not
    its pending/requested delivery status. Prior score SUMMARY delivery cells
    are also separate from the immutable score. No row may be added, removed,
    reordered, suppressed, reactivated, or changed in any other column.
    """
    header = HEADER if score_ledger else life.ALERT_HEADER
    width = len(header)
    if (type(before) is not list or type(after) is not list or not before or
            len(before) != len(after) or type(before[0]) is not list or
            type(after[0]) is not list or tuple(before[0]) != header or
            tuple(after[0]) != header):
        return False
    status_col, time_col = (27, 28) if score_ledger else (17, 18)
    old_state, new_state = ((READY, REQUESTED) if score_ledger else
                            (life.EVENT_PENDING, "ALERT_REQUESTED_NOT_DEVICE_ACK"))
    for old, new in zip(before[1:], after[1:]):
        if old == new:
            continue
        if (type(old) is not list or type(new) is not list or
                not status_col < len(old) <= width or
                not time_col < len(new) <= width or
                any(type(v) is not str for v in old + new)):
            return False
        a = old + [""] * (width - len(old))
        b = new + [""] * (width - len(new))
        if (not a[0] or (score_ledger and a[4] != "SUMMARY") or
                a[status_col] != old_state or a[time_col] != "" or
                b[status_col] != new_state or
                not _request_timestamp(b[time_col], a[1 if score_ledger else 4]) or
                any(a[i] != b[i] for i in range(width)
                    if i not in (status_col, time_col))):
            return False
    return True


def synchronize(api, asof, read_batch, *, on_phase=None):
    # Fixed categorical diagnostics only; no source data or exception text
    # is exported. Existing callers need not provide a phase observer.
    phase=on_phase if on_phase is not None else lambda value: None
    phase("SHEET_METADATA")
    api.check_metadata()
    metadata = api.request("?fields=properties(timeZone),sheets.properties(sheetId,title)")
    writer.require(metadata.get("properties", {}).get("timeZone") == "Europe/Istanbul",
                   "SWING_SCORE_SHEET_TIMEZONE_DRIFT")
    matches = [s["properties"]["sheetId"] for s in metadata.get("sheets", [])
               if s.get("properties", {}).get("title") == TAB]
    writer.require(len(matches) == 1 and type(matches[0]) is int,
                   "SWING_SCORE_TAB_MISSING_OR_DUPLICATE")
    tabid = matches[0]
    phase("SCORE_LEDGER_READ")
    before = score_read(api)
    writer.require(before and tuple(before[0]) == HEADER,
                   "SWING_SCORE_HEADER_DRIFT")
    phase("SOURCE_LEDGER_READ")
    candidates = api.read("ADAY_GECMISI", "M")
    scans = api.read("TARAMA_KAYITLARI", "J")
    alerts = api.read("UYARI_OLAYLARI", "T")
    phase("SOURCE_VALIDATE_AND_SCORE")
    rows = build(candidates, scans, alerts, asof, read_batch)
    phase("EXISTING_SCORE_VALIDATE")
    existing = [r for r in before[1:] if r and r[0]]
    writer.require(len({r[0] for r in existing}) == len(existing),
                   "SWING_SCORE_EXISTING_KEY_DUPLICATE")
    current = [r for r in existing if len(r) > 1 and r[1] == asof]
    if current:
        actual = {r[0]:r for r in current}
        writer.require(set(actual) == {r[0] for r in rows},
                       "SWING_SCORE_EXISTING_DAY_INCOMPLETE")
        for new in rows:
            old = actual[new[0]]
            # The hourly ChatGPT task may only update digest's delivery cells.
            immutable = [i for i in range(len(HEADER))
                         if i not in ((27, 28) if new[4] == "SUMMARY" else ())]
            writer.require(all((old[i] if len(old)>i else "") == new[i]
                               for i in immutable),
                           "SWING_SCORE_EXISTING_DAY_CONTENT_DRIFT")
        return {"status":"SWING_SCORE_IDEMPOTENT_READBACK_PASS","asof_et":asof,
                "active_episodes":len(rows)-1,"scoreable":int(rows[0][6]),
                "new_rows":0,"execution":"NONE"}
    # Pure, immutable idempotent replay is allowed even when the ledger
    # has no remaining append headroom. Only NEW ASOF rows need that room.
    writer.require(len(existing) + len(rows) < MAX_ROWS,
                   "SWING_SCORE_CAPACITY_REACHED")
    writer.require(not existing or max(r[1] for r in existing) < asof,
                   "SWING_SCORE_HISTORICAL_BACKFILL_REJECTED")
    phase("PREWRITE_REVALIDATE")
    latest_before = score_read(api)
    latest_candidates = api.read("ADAY_GECMISI", "M")
    latest_scans = api.read("TARAMA_KAYITLARI", "J")
    latest_alerts = api.read("UYARI_OLAYLARI", "T")
    writer.require(
        latest_candidates == candidates and latest_scans == scans and
        _delivery_only_progress(before, latest_before, score_ledger=True) and
        _delivery_only_progress(alerts, latest_alerts, score_ledger=False),
        "SWING_SCORE_CONCURRENT_MODIFICATION")
    if latest_before != before or latest_alerts != alerts:
        # At most one extra read-only snapshot, only after a verified benign
        # request-state transition. The final comparison is still exact.
        # No second market-data fetch, no second POST, no historical replay.
        writer.require(score_read(api) == latest_before and
                       api.read("ADAY_GECMISI", "M") == candidates and
                       api.read("TARAMA_KAYITLARI", "J") == scans and
                       api.read("UYARI_OLAYLARI", "T") == latest_alerts,
                       "SWING_SCORE_CONCURRENT_MODIFICATION")
    before = latest_before
    phase("APPEND_GATE_OR_POST")
    api.request(":batchUpdate",method="POST",
                body={"requests":[writer.as_cells(rows,tabid)]})
    phase("POST_READBACK")
    after = score_read(api)
    writer.require(len(after) == len(before) + len(rows) and
                   _delivery_only_progress(before, after[:len(before)],
                                           score_ledger=True) and
                   normalize_rows(after[len(before):]) == rows,
                   "SWING_SCORE_READBACK_MISMATCH")
    return {"status":"SWING_SCORE_PRIVATE_READBACK_PASS","asof_et":asof,
            "active_episodes":len(rows)-1,"scoreable":int(rows[0][6]),
            "new_rows":len(rows),"execution":"NONE"}

def publish_action_receipt(result):
    """Categorical, secret-free GitHub step output; not a delivery receipt.

    A zero-exit pre-session NOOP is fundamentally different from a verified
    private Google Sheets score readback. Only a fixed status and ISO ASOF
    can cross from the private scoring step into workflow-level acceptance.
    """
    status=result.get("status") if isinstance(result,dict) else None
    accepted={
        "SWING_SCORE_NO_COMPLETED_SESSION",
        "SWING_SCORE_PRIVATE_READBACK_PASS",
        "SWING_SCORE_IDEMPOTENT_READBACK_PASS",
    }
    if status not in accepted:
        raise ValueError("SWING_SCORE_ACTION_RECEIPT_UNRECOGNIZED_STATUS")
    asof=result.get("asof_et","")
    if status == "SWING_SCORE_NO_COMPLETED_SESSION":
        if asof not in ("",None):
            raise ValueError("SWING_SCORE_NO_SESSION_WITH_ASOF")
        asof=""
    else:
        if (type(asof) is not str or
                re.fullmatch(r"20\d{2}-\d{2}-\d{2}",asof) is None or
                date.fromisoformat(asof).isoformat() != asof):
            raise ValueError("SWING_SCORE_ACTION_RECEIPT_BAD_ASOF")
    destination=os.environ.get("GITHUB_OUTPUT")
    if destination:
        with open(destination,"a",encoding="utf-8") as stream:
            stream.write("score_status="+status+"\n")
            stream.write("score_asof_et="+asof+"\n")

# Only exact static reason strings from the local contracts may leave this
# private process. Regex-only or prefix-only filtering would permit exfiltration.
_SAFE_HOLD_CODES=frozenset((
    "EPOCH_LEASE_CONSUMER_UNVERIFIED",
    "EPOCH_LEASE_MODE_UNRECOGNIZED",
    "EPOCH_LEASE_TOKEN_MISSING",
    "EXISTING_SCAN_SOURCE_PROOF_MISSING_OR_MALFORMED",
    "GOOGLE_AUTH_CONFIGURATION_INVALID",
    "GOOGLE_SHEETS_METHOD_SCOPE_INVALID",
    "GOOGLE_SHEETS_POST_SCOPE_INVALID",
    "GOOGLE_SHEETS_READ_RETRY_EXHAUSTED",
    "GOOGLE_SHEETS_RESPONSE_INVALID",
    "GOOGLE_SHEETS_TRANSPORT_IO_ERROR",
    "GOOGLE_TOKEN_NOT_AVAILABLE",
    "INVALID_EXISTING_LEVEL",
    "LIFECYCLE_DUPLICATE_ID",
    "LIFECYCLE_FUTURE_OR_UNVERIFIED_COUNT",
    "LIFECYCLE_HEADER_DRIFT",
    "LIFECYCLE_IDENTITY_CONFLICT",
    "LIFECYCLE_INCOMPLETE_ROW",
    "LIFECYCLE_INVALID_PRICE_GEOMETRY",
    "LIFECYCLE_INVALID_START_DATE",
    "LIFECYCLE_INVALID_START_SESSION",
    "LIFECYCLE_MISSING_LEVELS",
    "LIFECYCLE_NON_2R_OR_TAMPERED_LEVEL",
    "LIFECYCLE_OPEN_COUNT_OUTSIDE_RANGE",
    "LIFECYCLE_TOO_MANY_EPISODES",
    "LIFECYCLE_UNKNOWN_STATUS",
    "NATURAL_EOD_WRITER_IDENTITY_UNVERIFIED",
    "PRIVATE_SHEET_ID_NOT_CONFIGURED",
    "SHEET_HEADER_DRIFT",
    "SHEET_METADATA",
    "SHEET_MISSING",
    "SHEET_PANEL_IDENTITY_MISMATCH",
    "SHEET_READ_CAPACITY_REACHED",
    "SHEET_TAB_OR_ID_DRIFT",
    "SHEET_TIMEZONE_DRIFT",
    "SOURCE_LASTMILE_MODE_UNRECOGNIZED",
    "SOURCE_LASTMILE_PROVENANCE_UNVERIFIED",
    "SOURCE_LASTMILE_TOKEN_MISSING",
    "SWING_SCORE_ACTION_RECEIPT_BAD_ASOF",
    "SWING_SCORE_ACTION_RECEIPT_UNRECOGNIZED_STATUS",
    "SWING_SCORE_ALERT_DUPLICATE",
    "SWING_SCORE_ALERT_HEADER_DRIFT",
    "SWING_SCORE_BAD_ASOF",
    "SWING_SCORE_BAD_DATE",
    "SWING_SCORE_BAR_DATE_MISMATCH",
    "SWING_SCORE_CAPACITY_REACHED",
    "SWING_SCORE_COL_COUNT",
    "SWING_SCORE_CONCURRENT_MODIFICATION",
    "SWING_SCORE_EXISTING_DAY_CONTENT_DRIFT",
    "SWING_SCORE_EXISTING_DAY_INCOMPLETE",
    "SWING_SCORE_EXISTING_KEY_DUPLICATE",
    "SWING_SCORE_HEADER_DRIFT",
    "SWING_SCORE_HISTORICAL_BACKFILL_REJECTED",
    "SWING_SCORE_HOLD",
    "SWING_SCORE_LAST_SCAN_ASOF_DRIFT",
    "SWING_SCORE_LEDGER_ROW_SHAPE",
    "SWING_SCORE_LEDGER_IDENTITY",
    "SWING_SCORE_LEDGER_PIN",
    "SWING_SCORE_LEDGER_DELIVERY",
    "SWING_SCORE_LOST_EPISODE",
    "SWING_SCORE_NONCURRENT_NATURAL_ASOF",
    "SWING_SCORE_NONFINITE",
    "SWING_SCORE_NON_NATURAL_SOURCE",
    "SWING_SCORE_NO_SESSION_WITH_ASOF",
    "SWING_SCORE_PRIVATE_AUTH_MISSING",
    "SWING_SCORE_READBACK_MISMATCH",
    "SWING_SCORE_READ_CAPACITY_REACHED",
    "SWING_SCORE_SCAN_NOT_FINAL_477",
    "SWING_SCORE_SHEET_TIMEZONE_DRIFT",
    "SWING_SCORE_SOURCE_NOT_DICT",
    "SWING_SCORE_SOURCE_SHA_DRIFT",
    "SWING_SCORE_TAB_MISSING_OR_DUPLICATE",
    "SWING_SCORE_TOO_MANY_EPISODES",
))
_SAFE_PHASES=frozenset(("SESSION_SELECT","NATURAL_SOURCE_GATE","PRIVATE_AUTH",
    "SHEET_METADATA","SCORE_LEDGER_READ","SOURCE_LEDGER_READ",
    "SOURCE_VALIDATE_AND_SCORE","EXISTING_SCORE_VALIDATE","PREWRITE_REVALIDATE",
    "APPEND_GATE_OR_POST","POST_READBACK","RECEIPT_PUBLICATION"))

def safe_hold_receipt(exc,phase):
    reason="UNCLASSIFIED"
    if type(exc) is writer.HandoffBlocked and len(exc.args)==1:
        raw=exc.args[0]
        if type(raw) is str and raw in _SAFE_HOLD_CODES:
            reason=raw
    return {"status":"SWING_SCORE_HOLD","reason_type":type(exc).__name__,
            "reason_code":reason,
            "failure_phase":phase if phase in _SAFE_PHASES else "UNCLASSIFIED",
            "execution":"NONE"}

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--asof",default="")
    args=parser.parse_args(argv)
    failure_phase="SESSION_SELECT"
    def observe_phase(value):
        nonlocal failure_phase
        failure_phase=value
    try:
        asof=args.asof or daily_job.current_completed_session()
        if asof is None:
            result={"status":"SWING_SCORE_NO_COMPLETED_SESSION",
                    "execution":"NONE"}
            publish_action_receipt(result)
            print(json.dumps(result,sort_keys=True))
            return 0
        # The CLI --asof cannot override the current natural completed
        # session to produce an old private score. Reject foreign workflows
        # before Google auth or market bars can be accessed.
        observe_phase("NATURAL_SOURCE_GATE")
        writer.verify_natural_eod_writer_identity(os.environ)
        current=daily_job.current_completed_session()
        writer.require(asof==current,"SWING_SCORE_NONCURRENT_NATURAL_ASOF")
        observe_phase("PRIVATE_AUTH")
        credential=os.environ.get("XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON","")
        writer.require(bool(credential),"SWING_SCORE_PRIVATE_AUTH_MISSING")
        api=writer.SheetApi(credential)
        result=synchronize(api, asof, engine.live_read,on_phase=observe_phase)
        observe_phase("RECEIPT_PUBLICATION")
        publish_action_receipt(result)
        print(json.dumps(result,sort_keys=True))
        return 0
    except Exception as exc:
        # Never leak user symbols, market bars, tokens, URLs, row contents.
        print(json.dumps(safe_hold_receipt(exc,failure_phase),sort_keys=True))
        return 3

if __name__=="__main__":
    raise SystemExit(main())
