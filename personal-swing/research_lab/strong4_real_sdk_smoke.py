#!/usr/bin/env python3
"""Four actual SDK smoke tests on SYNTHETIC INPUTS ONLY.

CI invokes in Docker --network none --read-only with no secrets.
An SDK smoke test is not evidence of PIT, OOS alpha, legal data rights,
safe broker integration or production performance.
"""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import math
import os

VERSIONS={"pydantic":"2.14.3","quantstats":"0.0.86","vectorbt":"1.2.0","duckdb":"2.0.0"}
SECRET_NAMES=("OPENAI_API_KEY","ANTHROPIC_API_KEY","GITHUB_TOKEN","APCA_API_KEY_ID",
              "APCA_API_SECRET_KEY","XRAY_ALPACA_DATA_KEY_ID","XRAY_ALPACA_DATA_SECRET_KEY",
              "XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON","XRAY_PRIVATE_SPREADSHEET_ID")

def guard(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)

def run(key: str) -> dict:
    guard(key in VERSIONS,"UNKNOWN_SDK")
    guard(os.environ.get("XRAY_DOCKER_NO_NETWORK")=="1","MISSING_NETWORK_BOUNDARY")
    guard(os.environ.get("XRAY_DOCKER_NO_SECRETS")=="1","MISSING_SECRET_BOUNDARY")
    guard(all(not os.environ.get(k) for k in SECRET_NAMES),"CREDENTIAL_PRESENT")
    version=importlib.metadata.version(key)
    guard(version==VERSIONS[key],"UNEXPECTED_PACKAGE_VERSION")
    metrics={}
    if key=="pydantic":
        from datetime import date
        from typing import Literal
        from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, ValidationError, field_validator
        class Evidence(BaseModel):
            model_config=ConfigDict(strict=True,extra="forbid",frozen=True)
            asof_et: str
            symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.]{0,14}$")
            source: Literal["Alpaca IEX"]
            close: FiniteFloat
            may_place_order: Literal[False] = False
            may_write_private_sheet: Literal[False] = False

            @field_validator("asof_et")
            @classmethod
            def check_date(cls, value: str) -> str:
                try:
                    if date.fromisoformat(value).isoformat()!=value:
                        raise ValueError("NONCANONICAL_ASOF")
                except ValueError as exc:
                    raise ValueError("INVALID_ASOF") from exc
                return value

        clean={"asof_et":"2026-11-06","symbol":"AAPL","source":"Alpaca IEX",
               "close":123.5,"may_place_order":False,"may_write_private_sheet":False}
        valid=Evidence.model_validate(clean)
        guard(valid.may_place_order is False and valid.may_write_private_sheet is False,
              "PERSISTENT_CAPABILITY_FLAG_NOT_DENIED")
        invalids=[
            {"may_place_order":True},
            {"may_write_private_sheet":True},
            {"source":"SIP"},
            {"asof_et":"2026-02-30"},
            {"symbol":"INVALID!"},
            {"close":float("nan")},
            {"may_place_order":"false"},
            {"unknown_access":True},
        ]
        rejected=0
        for patch in invalids:
            try:
                Evidence.model_validate({**clean,**patch})
            except ValidationError:
                rejected+=1
        guard(rejected==len(invalids),"PYDANTIC_NEGATIVE_FAIL_OPEN")
        metrics["negative_permission_source_time_price_and_extra_cases_rejected"]=rejected
    elif key=="quantstats":
        import pandas as pd
        import quantstats as qs
        from statistics import mean,pstdev
        vals=[0.012,-0.016,0.009,0.005,-0.011,0.007]*50
        returns=pd.Series(vals,index=pd.bdate_range("2024-01-02",periods=len(vals)))
        maximum=float(qs.stats.max_drawdown(returns))
        wealth=[1.0]
        for value in vals:
            wealth.append(wealth[-1]*(1+value))
        peak=wealth[0]
        independent=0.0
        for current in wealth:
            peak=max(peak,current)
            independent=min(independent,current/peak-1)
        guard(math.isfinite(maximum) and abs(maximum-independent)<1e-8,
              "QUANTSTATS_DRAWDOWN_BASELINE_DRIFT")
        sharpe=float(qs.stats.sharpe(returns,rf=0,periods=252))
        guard(math.isfinite(sharpe),"QUANTSTATS_SHARPE_NONFINITE")
        metrics["drawdown_matches_independent_arithmetic"]=True
        metrics["returns_count"]=len(vals)
        metrics["sharpe_is_finite"]=True
    elif key=="vectorbt":
        import vectorbt as vbt
        import pandas as pd
        idx=pd.bdate_range("2025-06-02",periods=12)
        close=pd.Series([100.,101.,102.,103.,98.,99.,100.,104.,103.,105.,106.,107.],index=idx)
        entries=pd.Series([False,True,False,False,False,False,False,False,False,False,False,False],index=idx)
        exits=pd.Series([False,False,False,True,False,False,False,False,False,False,False,False],index=idx)
        pf=vbt.Portfolio.from_signals(close,entries,exits,
                                      init_cash=10000.,fees=0.001,slippage=0.001,freq="1D")
        final=float(pf.value().iloc[-1])
        guard(math.isfinite(final) and final>0,"VECTORBT_INVALID_SYNTHETIC_EQUITY")
        metrics["finite_portfolio_value"]=True
        metrics["fees_and_slippage_parameters_tested"]=True
        metrics["real_stop_2r_not_tested"]=True
    else:
        import duckdb
        con=duckdb.connect(database=":memory:")
        try:
            con.execute("CREATE TABLE shadow (symbol VARCHAR, asof_et VARCHAR, score DOUBLE)")
            con.executemany("INSERT INTO shadow VALUES (?,?,?)",
                            [("AAPL","2026-11-06",1.2),("MU","2026-11-06",2.3),
                             ("AAPL","2026-11-05",1.0)])
            count,distinct_count=con.execute(
                "SELECT COUNT(*), COUNT(DISTINCT symbol) FROM shadow").fetchone()
            guard(count==3 and distinct_count==2,"DUCKDB_READBACK_DRIFT")
            metrics["in_memory_sql_readback_pass"]=True
            metrics["persistent_file_written"]=False
        finally:
            con.close()
    return {
        "schema":"XRAY_STRONG4_REAL_SDK_SYNTHETIC_SMOKE_V1",
        "sdk":key,"package_version":version,
        "status":"REAL_SDK_SYNTHETIC_ONLY_PASS",
        "metrics":metrics,"real_market_data_used":False,
        "model_alpha_verified":False,"real_pit_verified":False,
        "production_authorized":False,"broker_connected":False,
        "may_issue_al":False,"may_change_stop_target":False,"may_place_order":False
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--sdk",choices=sorted(VERSIONS),required=True)
    args=parser.parse_args()
    try:
        print(json.dumps(run(args.sdk),sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status":"HOLD","sdk":args.sdk,
                          "error_type":type(exc).__name__,
                          "error":str(exc)[:180],
                          "production_authorized":False},sort_keys=True))
        return 3
if __name__=="__main__":raise SystemExit(main())
