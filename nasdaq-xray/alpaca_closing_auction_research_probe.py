#!/usr/bin/env python3
"""One-call SIP auction *availability* witness for four authenticated RTH gaps.

This never validates official DV30, any trade corrections, source redistribution
rights, broker/account availability, R92 or AL. Never persist auction rows.
Reference: https://docs.alpaca.markets/us/reference/stockauctions-1
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone, date
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from alpaca_rth497_temporal_gap_canary import sample_from_parent, need

SCHEMA="XRAY_PERSONAL_SIP_AUCTION_ACCESSIBILITY_WITNESS_V1"
BASE="https://data.alpaca.markets/v2/stocks/auctions"
MAX_REQUESTS=1
MAX_BYTES=250000
MAX_ROWS=128
TARGET=4


def targets(parent, now):
    asof, selected, _=sample_from_parent(parent,now)
    causes=parent["symbol_rth_integrity_failure_codes"]
    syms=sorted(causes)
    need(len(syms)==TARGET and set(syms).issubset(selected),
         "AUCTION_EXACT_PARENT_GAP_TARGET")
    return asof,syms


def classify(parent, now, credentials, opener=urllib.request.urlopen):
    asof,syms=targets(parent,now)
    proof={"schema":SCHEMA,"asof_et":asof,
           "parent_rth_cohort_size":parent["joint_cohort_count"],
           "target_group":"EXACT_FOUR_PARENT_RTH_INTEGRITY_GAPS_ONLY",
           "target_count":TARGET,
           "symbol_set_sha256":parent["joint_history260_daily30_cohort_sha256"],
           "source_endpoint":BASE,"requested_feed":"sip",
           "api_calls":0,"api_call_budget":MAX_REQUESTS,
           "provider_status":"NOT_REQUESTED","response_pagination_complete":False,
           "returned_symbol_coverage_count":0,
           "returned_auction_rows_count":0,
           "no_vendor_auction_prices_or_volumes_persisted":True,
           "auction_data_is_research_only_not_trade_eligibility":True,
           "official_auction_correction_and_sale_conditions_attested":False,
           "official_c417_primary_dv30_attested":False,
           "official_c417_price_attested":False,
           "registered_R92_count":0,"orders":[],
           "execution":"NONE","real_money":"NO-GO",
           "source_rights_not_inferred":True,
           "user_notification_sent":False}
    key,secret=credentials
    if not (type(key) is str and type(secret) is str and
            bool(key.strip()) and bool(secret.strip())):
        proof["provider_status"]="UNKNOWN_MISSING_READONLY_MARKET_DATA_CREDENTIALS"
        return proof
    next_day=(date.fromisoformat(asof)+timedelta(days=1)).isoformat()
    params={"symbols":",".join(syms),"start":asof+"T00:00:00Z",
            "end":next_day+"T00:00:00Z",
            "asof":asof,"feed":"sip","limit":str(MAX_ROWS),"sort":"asc"}
    request=urllib.request.Request(BASE+"?"+urllib.parse.urlencode(params),
        headers={"APCA-API-KEY-ID":key,
                 "APCA-API-SECRET-KEY":secret,
                 "Accept":"application/json",
                 "User-Agent":"XRAY-personal-no-trading-auction-research"})
    proof["api_calls"]=1
    try:
        with opener(request,timeout=15) as res:
            if getattr(res,"status",None)!=200:
                proof["provider_status"]="UNKNOWN_HTTP_NON200"
                return proof
            payload=res.read(MAX_BYTES+1)
            if len(payload)>MAX_BYTES:
                proof["provider_status"]="UNKNOWN_RESPONSE_OVERSIZE"
                return proof
        obj=json.loads(payload)
        if type(obj) is not dict or type(obj.get("auctions")) is not dict:
            proof["provider_status"]="UNKNOWN_AUCTION_SCHEMA"
            return proof
        result=obj["auctions"]
        if set(result)-set(syms):
            proof["provider_status"]="UNKNOWN_FOREIGN_SYMBOL"
            return proof
        if any(type(rows) is not list or len(rows)>MAX_ROWS
               or any(type(row) is not dict for row in rows)
               for rows in result.values()):
            proof["provider_status"]="UNKNOWN_INVALID_AUCTION_ROWS"
            return proof
        count=sum(len(rows) for rows in result.values())
        if count>MAX_ROWS:
            proof["provider_status"]="UNKNOWN_RESPONSE_LIMIT"
            return proof
        proof["returned_symbol_coverage_count"]=sum(bool(rows) for rows in result.values())
        proof["returned_auction_rows_count"]=count
        token=obj.get("next_page_token")
        if token is not None and (type(token) is not str or not token):
            proof["provider_status"]="UNKNOWN_INVALID_PAGE_TOKEN"
        elif token:
            proof["provider_status"]="UNKNOWN_PAGINATED_AUCTION_SOURCE"
        else:
            proof["provider_status"]="OBSERVED_SIP_AUCTION_ROWS_RESEARCH_ONLY"
            proof["response_pagination_complete"]=True
    except urllib.error.HTTPError as exc:
        proof["provider_status"]="UNKNOWN_HTTP_"+str(exc.code)
    except (urllib.error.URLError,TimeoutError,OSError):
        proof["provider_status"]="UNKNOWN_PROVIDER_TIMEOUT_OR_NETWORK"
    except (UnicodeDecodeError,ValueError):
        proof["provider_status"]="UNKNOWN_INVALID_JSON"
    return proof


def selftest():
    class Response:
        status=200
        def __init__(self,data): self.data=json.dumps(data).encode()
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return self.data[:n]
    # Real source validator uses 260/30 session context. Reuse its independent
    # offline fixture and avoid hardcoding any market-date or population.
    from alpaca_rth497_temporal_gap_canary import (
        PARENT, sha, sample_from_parent)
    import alpaca_rth497_temporal_gap_canary as canary
    from unittest.mock import patch
    import datetime as dt
    # Mock ONLY the proven parent boundary, test target scope and provider.
    parent={"joint_cohort_count":496,
            "joint_history260_daily30_cohort_sha256":"a"*64,
            "symbol_rth_integrity_failure_codes":{
                "CACC":"EARLY_AND_FULL_BAR_COUNTS_EXACT",
                "LGND":"EARLY_AND_FULL_BAR_COUNTS_EXACT",
                "LQDA":"EARLY_AND_FULL_BAR_COUNTS_EXACT",
                "PLXS":"EARLY_AND_FULL_BAR_COUNTS_EXACT"}}
    now=dt.datetime(2026,10,17,2,tzinfo=dt.timezone.utc)
    with patch.object(canary,"sample_from_parent",return_value=(
        "2026-10-16",sorted(["CACC","LGND","LQDA","PLXS",
                             "ABCD","MNOP","QRST","WXYZ"]),[])):
        # The imported bound function is the same Python symbol: patch local.
        with patch(__name__+".sample_from_parent",
            return_value=("2026-10-16",
                sorted(["CACC","LGND","LQDA","PLXS",
                        "ABCD","MNOP","QRST","WXYZ"]),[])):
            absent=classify(parent,now,("",""))
            need(absent["api_calls"]==0 and
                 absent["provider_status"].startswith("UNKNOWN_") and
                 absent["registered_R92_count"]==0,"AUCTION_NO_KEYS")
            calls=[]
            def opener(req,timeout):
                calls.append((req.full_url,timeout))
                args=urllib.parse.parse_qs(
                    urllib.parse.urlparse(req.full_url).query)
                need(args["feed"]==["sip"] and
                     args["symbols"]==["CACC,LGND,LQDA,PLXS"] and
                     args["asof"]==["2026-10-16"] and timeout==15,
                     "AUCTION_API_QUERY_SCOPE")
                return Response({"auctions":{"CACC":[{"t":"synthetic"}],
                                              "LGND":[],"LQDA":[],
                                              "PLXS":[]},"next_page_token":None})
            good=classify(parent,now,("key","secret"),opener)
            need(len(calls)==1 and good["api_calls"]==1 and
                 good["returned_auction_rows_count"]==1 and
                 good["returned_symbol_coverage_count"]==1 and
                 good["response_pagination_complete"] is True and
                 good["official_c417_primary_dv30_attested"] is False and
                 good["registered_R92_count"]==0 and good["orders"]==[],
                 "AUCTION_BOUNDED_ONE_CALL_NEVER_PRIMARY")
            for body,expected in (
                ({"auctions":{"OUTSIDE":[{}]}}, "UNKNOWN_FOREIGN_SYMBOL"),
                ({"auctions":{"CACC":"string"}},"UNKNOWN_INVALID_AUCTION_ROWS"),
                ({"auctions":{"CACC":[{}]},
                  "next_page_token":"page"},"UNKNOWN_PAGINATED_AUCTION_SOURCE"),
                ({"bad":"schema"},"UNKNOWN_AUCTION_SCHEMA"),
                ({"auctions":{"CACC":[{}]},
                  "next_page_token":5},"UNKNOWN_INVALID_PAGE_TOKEN")):
                out=classify(parent,now,("key","secret"),
                             lambda req,timeout,b=body:Response(b))
                need(out["provider_status"]==expected and
                     not out["official_c417_primary_dv30_attested"],
                     "AUCTION_BAD_SOURCE_NOT_PASS")
            try:
                targets({"joint_cohort_count":496,
                         "symbol_rth_integrity_failure_codes":{"CACC":"foo"}},now)
            except ValueError:pass
            else:raise AssertionError("OUTSIDE_COHORT_FALSE_PASS")
    print("XRAY_SIP_AUCTION_WITNESS_SELFTEST=PASS_BOUNDED_1CALL_5_NEGATIVES_NO_PRIMARY_NO_R92")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--parent",type=Path)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:selftest();return
    need(args.parent is not None and args.out is not None,
         "AUCTION_SOURCE_ARGS")
    parent=json.loads(args.parent.read_text())
    report=classify(parent,datetime.now(timezone.utc),(
        os.getenv("XRAY_ALPACA_DATA_KEY_ID","").strip(),
        os.getenv("XRAY_ALPACA_DATA_SECRET_KEY","").strip()))
    args.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("XRAY_SIP_AUCTION_ONE_CALL="+json.dumps({
        "asof_et":report["asof_et"],
        "provider_status":report["provider_status"],
        "api_calls":report["api_calls"],
        "row_count":report["returned_auction_rows_count"],
        "C417":False,"R92":0,"orders":0},sort_keys=True))


if __name__=="__main__":main()
