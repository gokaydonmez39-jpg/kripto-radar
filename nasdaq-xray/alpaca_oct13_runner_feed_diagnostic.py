#!/usr/bin/env python3
"""Three authorized single-name Oct13 Alpaca feed probes; no OHLCV export."""
import argparse,json,os,urllib.parse,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CHECKS=("sip","iex","delayed_sip")
def check(ok,reason):
    if not ok:raise ValueError("XRAY_ALPACA_FEED_DIAGNOSTIC_"+reason)
def plan(feed):
    check(feed in CHECKS,"FEED")
    return {"symbols":"AAPL","timeframe":"1Day","feed":feed,
            "sort":"asc","adjustment":"raw","limit":"2",
            "start":"2026-10-13T00:00:00-04:00",
            "end":"2026-10-14T00:00:00-04:00"}
def selftest():
    check(len(CHECKS)==3 and len(set(CHECKS))==3,"THREE_DISTINCT_FEEDS")
    for feed in CHECKS:
        p=plan(feed)
        check(p["start"][:10]=="2026-10-13" and
              p["end"][:10]=="2026-10-14","EXACT_DAY")
    for feed in ("all","sip2",""):
        try:plan(feed)
        except ValueError:pass
        else:raise AssertionError("ARBITRARY_FEED_ACCEPTED")
    print("XRAY_ALPACA_OCT13_FEED_SELFTEST=PASS_EXACT_ASOF_THREE_READONLY")
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.selftest:selftest();return
    check(args.out and not args.out.resolve().is_relative_to(ROOT.parent.resolve()),
          "EPHEMERAL_REPORT")
    k=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    v=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    report={"schema":"XRAY_ALPACA_20261013_GITHUB_RUNNER_FEED_DIFFERENTIAL_V1",
            "asof_et":"2026-10-13","statuses":{},
            "http_requests":0,"feed_count_max":3,
            "no_vendor_bars_persisted":True,"never_substitute_iex_for_sip":True,
            "candidate_primary_created":False,"r92_created":False,
            "execution":"NONE","real_money":"NO-GO"}
    def save():
        args.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    save()
    if not (k and v):
        report["configuration_status"]="MISSING_RUNNER_DATA_CREDENTIALS"
        save();return
    for feed in CHECKS:
        p=plan(feed)
        url="https://data.alpaca.markets/v2/stocks/bars?"+urllib.parse.urlencode(p)
        req=urllib.request.Request(url,headers={"APCA-API-KEY-ID":k,
            "APCA-API-SECRET-KEY":v,"Accept":"application/json"})
        report["http_requests"]+=1
        try:
            with urllib.request.urlopen(req,timeout=15) as res:
                raw=res.read(200001)
                status=int(res.status)
            if len(raw)>200000:raise ValueError("BODY_LIMIT")
            parsed=json.loads(raw)
            good=(isinstance(parsed,dict) and isinstance(parsed.get("bars"),dict))
            report["statuses"][feed]={"http":status,"schema_valid":good,
                                      "has_aapl_bar":bool((parsed.get("bars") or {}).get("AAPL")) if good else False}
        except urllib.error.HTTPError as e:
            report["statuses"][feed]={"http":int(e.code),"schema_valid":False}
            if e.code==429:
                report["stop"]="RATE_LIMIT_NO_RETRY"
                save();break
        except (urllib.error.URLError,TimeoutError,ValueError):
            report["statuses"][feed]={"http":None,"schema_valid":False,
                                      "reason":"NETWORK_OR_SCHEMA_ERROR"}
        save()
    print("XRAY_ALPACA_RUNNER_FEED_HTTP="+json.dumps({
        x:v.get("http") for x,v in report["statuses"].items()},sort_keys=True))
    print("XRAY_ALPACA_RUNNER_FEED_DIFFERENTIAL_RESEARCH_ONLY=PASS")
if __name__=="__main__":main()
