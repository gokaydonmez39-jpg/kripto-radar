#!/usr/bin/env python3
"""Authenticated private, read-only adapter for Cove-method research shadow.

Uses only Google Sheets READONLY OAuth scope and Alpaca IEX data REST. No
NinjaTrader, broker, orders, Sheet mutation, alerts, public rows or replay.
Runs after a real successful personal EOD receipt, not on PR or old ASOF.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import cove_shadow
import engine
import kronos_v2
import private_sheet_writer as writer
import runner
from performance_lab import private_flight_recorder as flight


class CovePrivateHold(ValueError):
    pass


def need(ok,code):
    if not ok:
        raise CovePrivateHold(code)


class ReadOnlySheetApi(writer.SheetApi):
    """Reuse verified GET schema checks with an OAuth *readonly* credential."""

    def __init__(self,secret,spreadsheet_id):
        from google.oauth2.service_account import Credentials
        from google.auth.transport.requests import Request as AuthRequest
        need(type(secret) is str and bool(secret),"MISSING_READ_ONLY_SERVICE_ACCOUNT")
        need(type(spreadsheet_id) is str and len(spreadsheet_id)>=20
             and spreadsheet_id.replace("-","").replace("_","").isalnum(),
             "INVALID_PRIVATE_SHEET_ID")
        info=json.loads(secret)
        need(type(info) is dict and info.get("type")=="service_account",
             "INVALID_SERVICE_ACCOUNT_TYPE")
        creds=Credentials.from_service_account_info(
            info,scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        creds.refresh(AuthRequest())
        need(bool(creds.token),"READ_ONLY_TOKEN_MISSING")
        self.token=creds.token
        self.base=writer.BATCH_ENDPOINT+spreadsheet_id
        self.sheet_ids=None

    def request(self,path,*,method="GET",body=None):
        need(method=="GET" and body is None,"READ_ONLY_WRITE_FORBIDDEN")
        return super().request(path,method="GET",body=None)

    def apply(self,*unused,**unused_kw):
        raise CovePrivateHold("READ_ONLY_WRITE_FORBIDDEN")


def _read_current(api):
    return (api.read("ADAY_GECMISI","M"),
            api.read("TARAMA_KAYITLARI","J"),
            api.read("UYARI_OLAYLARI","T"),
            api.read("PANEL","B"))


def build_private_bundle(api,asof,read_batch,*,stage=None):
    """Attest source, private lifecycle, then bind 477-count + episode bars.

    The exact source-policy SHA and same-ASOF score receipt are checked by the
    existing Kronos V2 authority (not model inference). The A21 flight
    recorder verifies immutable episode/event/PANEL identity separately.
    """
    def mark(label):
        if stage is not None:
            stage(label)
    need(callable(read_batch),"MISSING_READ_ONLY_PROVIDER")
    mark("SOURCE_AUTHORITY")
    symbols,scope_sha,policy_sha,scan_id=kronos_v2.private_authority(api,asof)
    need(scan_id==asof and len(symbols)==477,"AUTHORITY_ASOF_OR_SCOPE_MISMATCH")
    before=_read_current(api)
    mark("FLIGHT_RECORDER")
    receipt=flight.inspect(*before,expected_asof=asof)
    need(receipt["latest_verified_scan_asof"]==asof
         and receipt["unreserved_current_eod_al"]==0
         and receipt["unreserved_prior_eod_al"]==0
         and not receipt["panel_non_authoritative_stale"]
         and not receipt["panel_missing_asof"],"FLIGHT_RECORDER_NOT_READY")
    candidate_rows=writer.rows_only(before[0],writer.CANDIDATE_HEADER)
    scan_rows=writer.rows_only(before[1],writer.SCAN_HEADER)
    need(scan_rows and scan_rows[-1][0]==asof,"SCAN_ASOF_DRIFT")
    latest=scan_rows[-1]
    need(len(latest)>=10 and latest[6]=="TRUE"
         and [writer.numeric(latest[i]) for i in (2,3,4,5)]==[477,477,477,0],
         "SOURCE_NOT_477")
    mark("EPISODE_SCOPE")
    episode_list=[]
    ids=set()
    for row in candidate_rows:
        need(len(row)>=8,"INCOMPLETE_EPISODE_ROW")
        key=str(row[0])
        need(key not in ids,"DUPLICATE_EPISODE_ROW")
        ids.add(key)
        need(str(row[7]).startswith(("AÇIK","KAPALI")),"UNKNOWN_EPISODE_STATE")
        # Only the officially verified, already-closed historical ROKU issuer
        # is excluded from the CURRENT prospective price-model cohort.
        # It remains intact in the private ledger and in the independent
        # Flight Recorder audit; GNTX is NEVER a ROKU price-history alias.
        reviewed_roku_closure = (
            asof >= "2026-11-10" and
            len(row) >= 11 and str(row[2]) == "ROKU" and
            str(row[1]) < "2026-11-10" and
            key == str(row[1])+"|ROKU" and
            str(row[7]).startswith("KAPALI • CORPORATE_ACTION_REVIEW • ") and
            str(row[8]) == "2026-11-09" and
            str(row[9]) == "CORPORATE_ACTION_REVIEW" and
            str(row[10]) == ""
        )
        if reviewed_roku_closure:
            continue
        episode_list.append({
            "id":key,
            "asof_et":str(row[1]),
            "symbol":str(row[2]),
            "reference_close":writer.numeric(row[4]),
            "stop":writer.numeric(row[5]),
            "target_2r":writer.numeric(row[6])
        })
    active_symbols=sorted({e["symbol"] for e in episode_list})
    need(set(active_symbols).issubset(set(symbols)),"UNREVIEWED_PIT_EPISODE")
    if active_symbols:
        mark("IEX_SOURCE")
        bars=read_batch(active_symbols,asof)
        need(type(bars) is dict and set(bars)==set(active_symbols),
             "PROVIDER_SYMBOL_SCOPE_MISMATCH")
    else:
        bars={}
    # The private sheet cannot change between attestation and output.
    mark("SOURCE_RECHECK")
    need(_read_current(api)==before,"CONCURRENT_PRIVATE_SOURCE_DRIFT")
    return {
        "schema":cove_shadow.INPUT_SCHEMA,
        "asof_et":asof,
        "feed":cove_shadow.ALLOWED_FEED,
        "scope_sha256":scope_sha,
        "algorithm_sha256":policy_sha,
        "source_counts":{"requested":477,"processed":477,"valid":477,
                         "missing":0,"final":True},
        "episodes":episode_list,
        "bars_by_symbol":bars
    }


def run_private(asof,api,read_batch,*,slippage_bps=5.,
                commission_per_share=0.005,stage=None):
    """Private in-memory result only; caller must not publish metrics/logs."""
    source=build_private_bundle(api,asof,read_batch,stage=stage)
    if stage is not None:
        stage("RESEARCH_MATH")
    result=cove_shadow.run_bundle(
        source,slippage_bps=slippage_bps,
        commission_per_share=commission_per_share)
    need(result["scope"]==477 and result["alpha_claim"]==
         "HOLD_UNVERIFIED_PIT_OOS" and result["orders"] is False
         and result["writes"] is False,"SHADOW_CONTRACT_DRIFT")
    return result


def main():
    # No command arguments, output files, schedule creation or privileged API.
    phase="AUTH"
    try:
        secret=os.environ.get("XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON")
        sheet_id=os.environ.get("XRAY_PRIVATE_SPREADSHEET_ID")
        need(bool(secret) and bool(sheet_id),"MISSING_READ_ONLY_AUTH")
        api=ReadOnlySheetApi(secret,sheet_id)
        phase="ASOF"
        asof=engine.trading_asof().isoformat()
        phase="AUTHENTICATED_READBACK"
        def mark(label):
            nonlocal phase
            phase=label
        result=run_private(asof,api,engine.live_read,stage=mark)
        # Never claim a live research PASS for a valid but empty source cohort.
        need(result["baseline"]["episodes"]>0 and
             result["baseline"]["status"]!="HOLD_NO_EPISODES",
             "NO_PRIVATE_EPISODES")
        phase="DONE"
        # Safe public status: no candidate names, prices, counts, forecast
        # details, SHA-derived private payload, Google IDs or credentials.
        need(result["orders"] is False and result["writes"] is False,
             "MUTATION_POLICY_DRIFT")
        print("COVE_SHADOW_POST_EOD=READONLY_RESEARCH_PASS_NO_PUBLIC_METRICS;NO_ORDERS;NO_AL_STOP_CHANGE;OOS_HOLD")
        return 0
    except Exception:
        # Any provider / credential / private data exception stays private.
        # Never print raw exception text or traceback into public GitHub logs.
        safe=phase if phase in (
            "AUTH","ASOF","AUTHENTICATED_READBACK","SOURCE_AUTHORITY",
            "FLIGHT_RECORDER","EPISODE_SCOPE","IEX_SOURCE",
            "SOURCE_RECHECK","RESEARCH_MATH","DONE") else "UNKNOWN"
        print("COVE_SHADOW_POST_EOD=HOLD_NO_DATA_PUBLISHED_NO_WRITES;STAGE="+safe)
        return 3


if __name__=="__main__":
    raise SystemExit(main())
