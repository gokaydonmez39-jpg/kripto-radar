#!/usr/bin/env python3
"""XRAY Kronos V2 — bounded 477 real IEX close forecasts, immutable monthly ledger.

Independent post-EOD research consumer. No orders, AL/STOP edits, alert sends,
device ACK, baseline replacement, upstream model change or historical replay.
A model's invalid OHLC geometry never becomes a repaired/full candle forecast:
only independently finite, strictly positive raw CLOSE may be preserved with
RESEARCH_CLOSE_ONLY; native OHLC quality stays HOLD.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
import hashlib
import json
import math
import os
import re
from urllib.parse import quote

import kronos_shadow as k

VERSION_V2 = "XRAY_KRONOS_CLOSE_ONLY_V2_20261107"
PARTITION_PREFIX = "KRONOS2_"
MAX_ROWS_PER_MONTH = 40000
MAX_GRID_CELLS = 9000000
WRITE_BATCH_ROWS = 180
EXPECTED = 477
MODEL_STATUS_FULL = "RESEARCH_ONLY"
MODEL_STATUS_CLOSE = "RESEARCH_CLOSE_ONLY"
QUALITY_PREFIX = "HOLD_QC_"


def month_sheet(asof):
    k.require(isinstance(asof,str) and
              re.fullmatch(r'20\d{2}-\d{2}-\d{2}',asof) is not None,
              "KRONOS2_BAD_ASOF")
    try:
        valid=date.fromisoformat(asof).isoformat()==asof
    except ValueError:
        valid=False
    k.require(valid,"KRONOS2_BAD_ASOF")
    return PARTITION_PREFIX + asof[:7].replace("-", "_")


def choose_sheet_id(name, existing_ids):
    chosen=100000000 + int(hashlib.sha256(name.encode()).hexdigest()[:7],16)
    k.require(chosen not in existing_ids,"KRONOS2_SHEET_ID_CONFLICT")
    return chosen


def read_partition(api, name):
    path=quote(f"'{name}'!A1:T",safe="")
    d=api.request("/values/"+path+"?valueRenderOption=FORMATTED_VALUE")
    matrix=d.get("values",[])
    k.require(isinstance(matrix,list) and 0<len(matrix)<=MAX_ROWS_PER_MONTH,
              "KRONOS2_PARTITION_READ_LIMIT")
    k.require(tuple(matrix[0])==k.HEADERS,"KRONOS2_HEADER_DRIFT")
    rows=[]
    blank_seen=False
    for r in matrix[1:]:
        if not r or all(x=="" for x in r):
            blank_seen=True
            continue
        k.require(bool(r[0]),"KRONOS2_PARTITION_ROW_WITHOUT_ID")
        k.require(not blank_seen,"KRONOS2_INTERNAL_BLANK_ROW")
        k.require(len(r)<=20,"KRONOS2_ROW_TOO_WIDE")
        padded=list(r)+[""]*(20-len(r))
        k.require(padded[19]==k.canonical_sha(padded[:19]) and
                  padded[16]==VERSION_V2 and
                  padded[17] in (MODEL_STATUS_FULL,MODEL_STATUS_CLOSE)
                  or (padded[17].startswith(QUALITY_PREFIX) and
                      padded[16]==VERSION_V2 and
                      padded[19]==k.canonical_sha(padded[:19]) and
                      padded[5]==padded[6]==padded[15]==""),
                  "KRONOS2_TAMPERED_OR_WRONG_VERSION")
        k.require(padded[1][:7]==name[len(PARTITION_PREFIX):].replace("_","-"),
                  "KRONOS2_PARTITION_ASOF_DRIFT")
        k.require(padded[0]==f"{padded[1]}|{padded[2]}|H{padded[3]}",
                  "KRONOS2_ROW_IDENTITY_DRIFT")
        rows.append(padded)
    k.require(len({x[0] for x in rows})==len(rows),
              "KRONOS2_DUPLICATE_LEDGER_KEYS")
    k.require([x[0] for x in rows]==sorted([x[0] for x in rows],
                                         key=lambda s:(s.split("|")[0],s.split("|")[1],
                                                       int(s.split("H")[-1]))),
              "KRONOS2_LEDGER_OUT_OF_ORDER")
    return rows



def require_full_horizon_cohorts(rows, reason):
    """Validate exact H1/H5/H12 per symbol in each completed historical ASOF.

    A 1431-row count alone is not proof of a full 477-symbol cohort: for
    example, H1/H2/H12 with a recomputed valid row SHA must fail closed.
    This structural check does not claim PIT identity or financial OOS PASS.
    """
    allowed={str(h) for h in k.HORIZONS}
    by_asof={}
    for row in rows:
        day=row[1]
        symbol=row[2]
        horizon=row[3]
        symbols=by_asof.setdefault(day,{})
        horizons=symbols.setdefault(symbol,set())
        k.require(horizon in allowed and horizon not in horizons,reason)
        horizons.add(horizon)
    k.require(all(
        len(symbols)==EXPECTED and all(hs==allowed for hs in symbols.values())
        for symbols in by_asof.values()
    ),reason)

def private_authority(api, asof):
    """477 IEX + source/policy/swing independent authenticated gate."""
    import runner
    import private_sheet_writer as writer
    import swing_score_daily as score
    from pathlib import Path

    api.check_metadata()
    scans=writer.rows_only(api.read("TARAMA_KAYITLARI","J"),writer.SCAN_HEADER)
    k.require(scans and scans[-1][0]==asof and
              sum(row[0]==asof for row in scans)==1,
              "KRONOS2_LAST_SCAN_ASOF")
    last=scans[-1]
    k.require([writer.numeric(last[i]) for i in (2,3,4,5)] ==
              [477,477,477,0] and str(last[6]).upper()=="TRUE",
              "KRONOS2_SOURCE_NOT_477_PASS")
    # EOD hashes the *original ordered* personal watchlist. Sorting is
    # allowed only for deterministic inference scheduling, never source SHA.
    source_order=runner.get_scope(
        watchlist_file=str(Path(__file__).with_name("nasdaq_watchlist_477.json")),
        asof=asof)
    symbols=sorted(source_order)
    k.require(len(symbols)==EXPECTED and len(set(symbols))==EXPECTED,
              "KRONOS2_NOT_EXACT_SCOPE")
    sha=runner.sha_symbols(source_order)
    policy=runner.analysis_fingerprint()
    proof=writer.scan_source_proof(last[9])
    k.require(proof["scopeSHA"]==sha and proof["algorithmSHA"]==policy,
              "KRONOS2_SOURCE_SHA_CONFLICT")
    values=score.normalize_rows(score.score_read(api))
    k.require(values and tuple(values[0])==score.HEADER,
              "KRONOS2_SCORE_HEADER")
    summary=[r for r in values[1:] if r and r[0]==asof+"|SUMMARY"]
    k.require(len(summary)==1 and
              summary[0][30]==sha and summary[0][31]==policy and
              summary[0][27] in ("READY_FOR_CHATGPT_DAILY_DIGEST",
                                  "REQUESTED_NOT_DEVICE_ACK") and
              int(summary[0][7])==0 and
              int(summary[0][5])==int(summary[0][6]),
              "KRONOS2_SCORE_NOT_READY")
    return symbols,sha,policy,last[0]


def forecast_classification(frame):
    """Raw decoded OHLC are never adjusted. Preserve only raw CLOSE on geometry error."""
    try:
        closes=k.validate_prediction(frame,1.0)
        return closes,MODEL_STATUS_FULL,"IEX_RAW_AMOUNT_OHLC_MEAN_VOLUME_PROXY"
    except k.ShadowHold as exc:
        code=str(exc)
        if code!="KRONOS_INVALID_FORECAST_GEOMETRY":
            return None,QUALITY_PREFIX+code.replace("KRONOS_INVALID_FORECAST_","").replace(
                "KRONOS_WRONG_PRED_LENGTH","LENGTH"),"MODEL_OUTPUT_UNUSABLE"
        k.require(len(frame)==k.PRED_LEN,"KRONOS2_CLOSE_ONLY_BAD_LENGTH")
        try:
            closes=[float(row["close"]) for _,row in frame.iterrows()]
        except (ValueError,TypeError,KeyError):
            return None,"HOLD_QC_CLOSE_SCHEMA","MODEL_OUTPUT_UNUSABLE"
        if not all(math.isfinite(x) and x>0 for x in closes):
            return None,"HOLD_QC_CLOSE_INVALID","MODEL_OUTPUT_UNUSABLE"
        return closes,MODEL_STATUS_CLOSE,"RAW_CLOSE_ONLY__NATIVE_OHLC_GEOMETRY_INVALID"


def predict_frame(predictor, candles, future_sessions):
    import pandas as pd
    recent=candles[-k.LOOKBACK:]
    data=pd.DataFrame([{field:float(row[field]) for field in (
        "open","high","low","close","volume")} for row in recent])
    data["amount"]=data["volume"]*data[["open","high","low","close"]].mean(axis=1)
    x_time=pd.Series(pd.to_datetime([str(v["timestamp"])[:10] for v in recent]))
    y_time=pd.Series(pd.to_datetime(future_sessions))
    return predictor.predict(df=data,x_timestamp=x_time,y_timestamp=y_time,
                             pred_len=k.PRED_LEN,T=0.6,top_k=0,top_p=0.90,
                             sample_count=1,verbose=False)


def build_v2_rows(symbol,asof,scope_sha,policy_sha,scan_id,candles,
                  closes,status,policy):
    if closes is None:
        # Existing 1/5/12 hold helper rejects unclassified geometry.
        k.require(status.startswith(QUALITY_PREFIX),"KRONOS2_BAD_HOLD_STATUS")
        raw=k.build_qc_hold_rows(symbol,asof,scope_sha,policy_sha,
                                 scan_id,candles,"KRONOS_INVALID_FORECAST_GEOMETRY")
    else:
        raw=k.build_rows(symbol,asof,scope_sha,policy_sha,scan_id,candles,closes)
    for row in raw:
        row[16]=VERSION_V2
        row[17]=status
        row[18]=policy
        row[19]=k.canonical_sha(row[:19])
    return raw


def make_predictions(symbols,asof,scope_sha,policy_sha,scan_id,
                     read_batch,predictor_factory,existing_rows=None):
    """Revalidate all IEX sources; infer only symbols NOT already persisted.

    A stochastic model cannot reproduce old sampled predictions on retry.
    The immutable, verified prefix stays authoritative. A source drift,
    partial H1/H5/H12 group or provenance conflict stops before any POST.
    """
    import engine
    prior=list(existing_rows or [])
    n_horizons=len(k.HORIZONS)
    k.require(len(prior)<=len(symbols)*n_horizons and
              len(prior)%n_horizons==0,
              "KRONOS2_RESTART_PARTIAL_HORIZONS")
    completed=len(prior)//n_horizons
    expected_prefix=[
        f"{asof}|{symbol}|H{h}"
        for symbol in symbols[:completed] for h in k.HORIZONS
    ]
    k.require([r[0] for r in prior]==expected_prefix,
              "KRONOS2_RESTART_NOT_EXACT_PREFIX")
    bars=read_batch(symbols,asof)
    k.require(isinstance(bars,dict) and set(bars)==set(symbols),
              "KRONOS2_PROVIDER_SCOPE_DRIFT")
    future=k.future_xnas_days(asof)
    predictor=predictor_factory() if completed<len(symbols) else None
    result=[]
    counts=Counter()
    for i,symbol in enumerate(symbols):
        candles=k.validate_candles(bars[symbol],asof)
        analyzed=engine.analyze(symbol,candles,asof)
        k.require(analyzed.get("sessions",0)>=52 and
                  analyzed.get("decision") in ("AL","IZLE","ELE"),
                  "KRONOS2_SOURCE_NOT_ANALYZABLE")
        if i<completed:
            original=prior[i*n_horizons:(i+1)*n_horizons]
            raw_source=[
                {field:b[field] for field in (
                    "timestamp","open","high","low","close","volume")}
                for b in candles[-k.LOOKBACK:]
            ]
            expected_input_sha=k.canonical_sha(raw_source)
            expected_close=f"{float(candles[-1]['close']):.6f}"
            k.require(all(
                r[13]==scan_id and r[14]==expected_input_sha and
                r[4]==expected_close and
                r[19]==k.canonical_sha(r[:19]) for r in original),
                "KRONOS2_RESTART_SOURCE_DRIFT")
            k.require(len({r[17] for r in original})==1 and
                      len({r[15] for r in original})==1,
                      "KRONOS2_RESTART_HORIZON_INCONSISTENCY")
            status=original[0][17]
            k.require(status in (MODEL_STATUS_FULL,MODEL_STATUS_CLOSE)
                      or status.startswith(QUALITY_PREFIX),
                      "KRONOS2_RESTART_STATUS_DRIFT")
            result.extend(original)
            counts[status]+=1
            continue
        # A recoverable model exception must not drop 476 unrelated rows.
        # Only the failed symbol gets three immutable QC HOLD records.
        # A source or provenance failure remains a hard cohort-level HOLD.
        try:
            frame=predict_frame(predictor,candles,future)
        except k.ShadowHold:
            raise
        except (RuntimeError,ValueError,TypeError,IndexError):
            closes,status,policy=None,"HOLD_QC_MODEL_RUNTIME","MODEL_OUTPUT_UNUSABLE"
        else:
            closes,status,policy=forecast_classification(frame)
        counts[status]+=1
        result.extend(build_v2_rows(symbol,asof,scope_sha,policy_sha,scan_id,
                                    candles,closes,status,policy))
    k.require(len(result)==len(symbols)*n_horizons and
              len({r[0] for r in result})==len(result),
              "KRONOS2_INCOMPLETE_PREDICTIONS")
    return result,counts


def metadata_and_sheet(api, asof):
    name=month_sheet(asof)
    meta=api.request("?fields=properties(timeZone),sheets.properties(sheetId,title,gridProperties(rowCount,columnCount))")
    k.require(meta.get("properties",{}).get("timeZone")=="Europe/Istanbul",
              "KRONOS2_TIMEZONE_DRIFT")
    sheets=[s["properties"] for s in meta.get("sheets",[]) if "properties" in s]
    k.require(sum(int(s.get("gridProperties",{}).get("rowCount",0))*
                  int(s.get("gridProperties",{}).get("columnCount",0)) for s in sheets)
              + EXPECTED*3*20 < MAX_GRID_CELLS,
              "KRONOS2_SHEET_GLOBAL_CAPACITY")
    found=[s for s in sheets if s.get("title")==name]
    k.require(len(found)<=1,"KRONOS2_DUPLICATE_SHEET")
    return name,found[0]["sheetId"] if found else None,\
           {s["sheetId"] for s in sheets if type(s.get("sheetId")) is int}


def require_previous_month_complete(api, asof):
    """Read-only first-of-month custody gate; never backfill or repair history.

    The current monthly partition may be empty at a new month boundary.
    A pre-existing preceding-month partition must be nonempty and contain
    exactly 477*3 immutable SHA-validated rows per ASOF, or new writes HOLD.
    """
    previous_day=date.fromisoformat(asof).replace(day=1)-timedelta(days=1)
    name=month_sheet(previous_day.isoformat())
    metadata=api.request(
        "?fields=properties(timeZone),sheets.properties(sheetId,title,gridProperties(rowCount,columnCount))")
    k.require(metadata.get("properties",{}).get("timeZone")=="Europe/Istanbul",
              "KRONOS2_PREVIOUS_MONTH_TZ_DRIFT")
    matches=[s["properties"] for s in metadata.get("sheets",[])
             if "properties" in s and s["properties"].get("title")==name]
    k.require(len(matches)<=1,"KRONOS2_PREVIOUS_MONTH_DUPLICATE_TAB")
    if not matches:
        return False
    rows=read_partition(api,name)
    counts=Counter(row[1] for row in rows)
    k.require(bool(counts) and
              all(count==EXPECTED*len(k.HORIZONS)
                  for count in counts.values()),
              "KRONOS2_PREVIOUS_MONTH_PARTIAL_HOLD")
    require_full_horizon_cohorts(rows,"KRONOS2_PREVIOUS_MONTH_HORIZON_HOLD")
    return True


def ensure_month_sheet(api,name,sid,occupied):
    import private_sheet_writer as writer
    if sid is not None:
        return sid
    new_id=choose_sheet_id(name,occupied)
    body={"requests":[
        {"addSheet":{"properties":{"sheetId":new_id,"title":name,
           "gridProperties":{"rowCount":1,"columnCount":20,"frozenRowCount":1}}}},
        writer.as_cells([list(k.HEADERS)],new_id),
    ]}
    # One POST, never retry an ambiguous write.
    api.request(":batchUpdate",method="POST",body=body)
    return new_id


def synchronize(api, asof, read_batch, predictor_factory=k.load_predictor,
                *, stage=None):
    """Same exact EOD authority; diagnostic labels are static and non-sensitive."""
    import private_sheet_writer as writer
    def mark(label):
        if stage is not None:
            stage(label)
    month=month_sheet(asof)
    mark("SOURCE_AUTHORITY")
    symbols,scope_sha,policy_sha,scan_id=private_authority(api,asof)
    mark("PARTITION_METADATA")
    name,sid,used=metadata_and_sheet(api,asof)
    assert name==month
    mark("PARTITION_READ")
    before=read_partition(api,name) if sid is not None else []
    k.require(all(row[1]<=asof for row in before),"KRONOS2_FUTURE_LEDGER")
    previous=[row for row in before if row[1]<asof]
    current=[row for row in before if row[1]==asof]
    # On the first ASOF of a new monthly partition, check the preceding
    # month before any inference or write. Never silently drop partial
    # previous-month records at the calendar boundary.
    if not previous:
        mark("PRIOR_MONTH_CUSTODY")
        require_previous_month_complete(api,asof)
    k.require(before==previous+current,
              "KRONOS2_NONAPPEND_CURRENT_DATA")
    # A prior interrupted ASOF cannot be silently treated as an accepted
    # history when beginning the next session. Require complete prior months.
    prior_counts=Counter(row[1] for row in previous)
    k.require(all(count==EXPECTED*len(k.HORIZONS)
                  for count in prior_counts.values()),
              "KRONOS2_PRIOR_ASOF_PARTIAL_HOLD")
    require_full_horizon_cohorts(previous,"KRONOS2_PRIOR_ASOF_HORIZON_HOLD")
    expected_ids={f"{asof}|{s}|H{h}" for s in symbols for h in k.HORIZONS}
    k.require(set(r[0] for r in current).issubset(expected_ids),
              "KRONOS2_ASOF_SCOPE_MISMATCH")
    k.require(all(r[11]==scope_sha and r[12]==policy_sha and
                  r[7]==k.MODEL_ID and r[8]==k.MODEL_REV and
                  r[9]==k.TOKENIZER_REV and r[10]==k.KRONOS_CODE_REV for r in current),
              "KRONOS2_ASOF_PROVENANCE_DRIFT")
    if len(current)==EXPECTED*3:
        return {"status":"KRONOS2_IDEMPOTENT_READBACK",
                "asof_et":asof,"scope":EXPECTED,"rows_written":0,
                "close_only":len({r[2] for r in current if r[17]==MODEL_STATUS_CLOSE}),
                "qc_hold":len({r[2] for r in current if r[17].startswith(QUALITY_PREFIX)}),
                "orders":False}
    def traced_read_batch(*args):
        mark("IEX_SOURCE")
        return read_batch(*args)
    def traced_predictor_factory():
        mark("MODEL_LOAD")
        model=predictor_factory()
        mark("MODEL_INFERENCE")
        return model
    rows,counts=make_predictions(symbols,asof,scope_sha,policy_sha,
                                 scan_id,traced_read_batch,traced_predictor_factory,
                                 existing_rows=current)
    if current:
        k.require(rows[:len(current)]==current,
                  "KRONOS2_RESTART_IMMUTABLE_PREFIX_DRIFT")
    k.require(len(previous)+len(rows)<MAX_ROWS_PER_MONTH,
              "KRONOS2_MONTH_CAPACITY")
    # Verify the pre-write ledger did not change during expensive CPU inference.
    if sid is not None:
        k.require(read_partition(api,name)==before,
                  "KRONOS2_CONCURRENT_WRITE_DETECTED")
    mark("SHEET_WRITE")
    sid=ensure_month_sheet(api,name,sid,used)
    # All 477 model results are already computed. Append in bounded chunks
    # and verify each original row exactly; interrupted run is resumable.
    written=0
    at=len(current)
    while at<len(rows):
        chunk=rows[at:at+WRITE_BATCH_ROWS]
        expected_prefix=previous+rows[:at+len(chunk)]
        try:
            api.request(":batchUpdate",method="POST",
                        body={"requests":[writer.as_cells(chunk,sid)]})
        except Exception:
            # A lost HTTP receipt cannot distinguish a committed POST from
            # a rejected POST. GET is safe; NEVER send the same chunk twice.
            try:
                recovered=read_partition(api,name)
            except Exception:
                raise k.ShadowHold(
                    "KRONOS2_AMBIGUOUS_POST_READBACK_UNAVAILABLE") from None
            k.require(recovered==expected_prefix,
                      "KRONOS2_AMBIGUOUS_POST_NOT_CONFIRMED")
        at+=len(chunk)
        written+=len(chunk)
        mark("SHEET_READBACK")
        observed=read_partition(api,name)
        k.require(observed==expected_prefix,
                  "KRONOS2_CHUNK_READBACK_MISMATCH")
    k.require(len(previous)+len(rows)==len(read_partition(api,name)),
              "KRONOS2_FINAL_READBACK")
    qc=sum(counts[s] for s in counts if s.startswith(QUALITY_PREFIX))
    close_only=counts.get(MODEL_STATUS_CLOSE,0)
    status=("KRONOS2_PRIVATE_READBACK_WITH_QC_HOLD" if qc else
            "KRONOS2_PRIVATE_READBACK_CLOSE_ONLY" if close_only else
            "KRONOS2_PRIVATE_READBACK_FULL_GEOMETRY")
    return {"status":status,"asof_et":asof,"scope":EXPECTED,
            "rows_written":written,"full_geometry":counts.get(MODEL_STATUS_FULL,0),
            "close_only":close_only,"qc_hold":qc,"orders":False,
            "model_quality_full_pass":not bool(qc or close_only),
            "decision_influence":"NO_GO"}


def main():
    import engine
    import private_sheet_writer as writer
    phase="SESSION_CLOCK"
    try:
        asof=k.eligible_shadow_asof()
        # First V2 session is a fresh forecast; never replay the old 2026-11-06
        # V1 shadow observations or manufacture pre-deployment history.
        if asof is not None and asof < "2026-11-09":
            print(json.dumps({"status":"KRONOS2_NOT_STARTED_BEFORE_2026_11_09",
                              "orders":False}))
            return 0
        if asof is None:
            print(json.dumps({"status":"KRONOS2_NOT_DUE","orders":False}))
            return 0
        phase="SHEET_AUTH"
        secret=os.environ.get("XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON","")
        k.require(bool(secret),"KRONOS2_AUTH_MISSING")
        api=writer.SheetApi(secret)
        def mark(label):
            nonlocal phase
            phase=label
        out=synchronize(api,asof,engine.live_read,stage=mark)
        print(json.dumps(out,sort_keys=True))
        return 3 if out.get("qc_hold",0) else 0
    except Exception as exc:
        # Never log exception messages, symbols, model outputs, provider data,
        # account IDs, credentials or tracebacks. Only allowlisted stage and
        # static source-invariant error codes may reach public CI.
        raw=str(exc) if isinstance(exc,k.ShadowHold) else ""
        reason=(raw if re.fullmatch(r"(?:KRONOS|KRONOS2)_[A-Z0-9_]{3,80}",raw)
                else "KRONOS2_UNCLASSIFIED")
        allowed_stages={
            "SESSION_CLOCK","SHEET_AUTH","SOURCE_AUTHORITY",
            "PARTITION_METADATA","PARTITION_READ","PRIOR_MONTH_CUSTODY",
            "IEX_SOURCE","MODEL_LOAD","MODEL_INFERENCE",
            "SHEET_WRITE","SHEET_READBACK"}
        safe_stage=phase if phase in allowed_stages else "UNKNOWN"
        kind=type(exc).__name__
        allowed_kinds={"ShadowHold","RuntimeError","ValueError","TypeError",
                       "KeyError","OSError","MemoryError","ImportError",
                       "AttributeError","PermissionError","AssertionError"}
        safe_kind=kind if kind in allowed_kinds else "OTHER"
        print(json.dumps({"status":"KRONOS2_HOLD","reason_code":reason,
                          "stage":safe_stage,"exception_family":safe_kind,
                          "orders":False},sort_keys=True))
        return 3


if __name__=="__main__":
    raise SystemExit(main())
