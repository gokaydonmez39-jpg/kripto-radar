#!/usr/bin/env python3
from __future__ import annotations
import json, os, ssl, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
AUTH=ROOT/"g9_entitlement_authority.json"
ADAPTER_CONTRACT=ROOT/"g9_provider_adapter_contract.json"
OUT=ROOT/"strict_g9_runtime_state.json"
SYMBOLS=("AAPL","NVDA")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def parse_ts(s):
    if not s: return None
    s=str(s).replace("Z","+00:00")
    try: return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception: return None

def write(obj):
    OUT.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":obj.get("status"),"g9_pass":obj.get("g9_pass",False),"reason":obj.get("reason")},sort_keys=True))

def is_rth():
    et=datetime.now(ZoneInfo("America/New_York"))
    if et.weekday()>=5: return False
    minutes=et.hour*60+et.minute
    return 570 <= minutes < 960

def refresh_token():
    cid=os.getenv("TRADESTATION_CLIENT_ID","").strip()
    rt=os.getenv("TRADESTATION_REFRESH_TOKEN","").strip()
    sec=os.getenv("TRADESTATION_CLIENT_SECRET","").strip()
    if not cid or not rt: return None,None,"TRADESTATION_CREDENTIALS_NOT_CONFIGURED"
    form={"grant_type":"refresh_token","client_id":cid,"refresh_token":rt}
    if sec: form["client_secret"]=sec
    req=urllib.request.Request(
        "https://signin.tradestation.com/oauth/token",
        data=urllib.parse.urlencode(form).encode(),
        headers={"Content-Type":"application/x-www-form-urlencoded","Accept":"application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req,timeout=20,context=ssl.create_default_context()) as r:
        j=json.loads(r.read().decode())
    token=j.get("access_token")
    scope=j.get("scope","")
    if not token: return None,scope,"TOKEN_REFRESH_NO_ACCESS_TOKEN"
    return token,scope,None

def get_json(token,url):
    req=urllib.request.Request(url,headers={"Authorization":f"Bearer {token}","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=20,context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode())

def stream_first_depth(token,symbol):
    url=f"https://api.tradestation.com/v3/marketdata/stream/marketdepth/quotes/{symbol}?maxlevels=1"
    req=urllib.request.Request(url,headers={"Authorization":f"Bearer {token}","Accept":"application/vnd.tradestation.streams.v3+json"})
    dec=json.JSONDecoder(); buf=""
    deadline=time.time()+20
    with urllib.request.urlopen(req,timeout=20,context=ssl.create_default_context()) as r:
        while time.time()<deadline:
            chunk=r.read(4096)
            if not chunk: break
            buf += chunk.decode("utf-8","ignore")
            while True:
                s=buf.lstrip()
                if not s: break
                try:
                    obj,end=dec.raw_decode(s)
                except json.JSONDecodeError:
                    break
                buf=s[end:]
                if isinstance(obj,dict) and obj.get("Bids") and obj.get("Asks"):
                    return obj
                if isinstance(obj,dict) and obj.get("Error"):
                    raise RuntimeError(f"TRADESTATION_STREAM_ERROR:{obj.get('Error')}:{obj.get('Message')}")
    raise RuntimeError("NO_MARKET_DEPTH_EVENT")

def best(side,kind):
    rows=side or []
    out=[]
    for x in rows:
        try:
            px=float(x.get("Price"))
            ts=parse_ts(x.get("TimeStamp"))
            if px>0 and ts: out.append((px,ts,x.get("Name")))
        except Exception: pass
    if not out: return None
    return max(out,key=lambda x:x[0]) if kind=="bid" else min(out,key=lambda x:x[0])


def wealthnow_snapshot(token,symbol):
    url="https://firm.wealthnow.io/api/v3/fundamentals/price_snapshot?"+urllib.parse.urlencode({"ticker":symbol})
    req=urllib.request.Request(url,headers={"X-API-Key":token,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=20,context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode())

def run_wealthnow_technical(base):
    token=os.getenv("WEALTHNOW_API_KEY","").strip()
    if not token:
        base.update({"status":"NOT_CONFIGURED","reason":"WEALTHNOW_API_KEY_NOT_CONFIGURED","scheduler_callability":"BLOCKED_MISSING_SECRET"})
        write(base); return
    if not is_rth():
        base.update({"technical_status":"NOT_RTH_NO_FRESHNESS_JUDGMENT","status":"WAITING_RTH","reason":"STRICT_G9_REQUIRES_LIVE_RTH_FRESHNESS_PROOF"})
        write(base); return
    try:
        utcnow=datetime.now(timezone.utc)
        details={}
        for sym in SYMBOLS:
            j=wealthnow_snapshot(token,sym)
            snap=j.get("snapshot") if isinstance(j,dict) else None
            if not isinstance(snap,dict):
                raise RuntimeError(f"WEALTHNOW_SNAPSHOT_SCHEMA_MISMATCH_{sym}")
            if str(snap.get("market_session") or snap.get("session") or "").lower()!="regular":
                raise RuntimeError(f"WEALTHNOW_NOT_REGULAR_SESSION_{sym}")
            if snap.get("is_stale") is not False:
                raise RuntimeError(f"WEALTHNOW_STALE_OR_UNKNOWN_{sym}")
            bid=float(snap["bid"]); ask=float(snap["ask"]); last=float(snap["price"])
            qts=parse_ts(snap.get("quote_as_of"))
            tts=parse_ts(snap.get("as_of") or snap.get("time"))
            if min(bid,ask,last)<=0 or bid>ask or not qts or not tts:
                raise RuntimeError(f"WEALTHNOW_INVALID_QUOTE_{sym}")
            quote_age=(utcnow-qts).total_seconds()
            trade_age=(utcnow-tts).total_seconds()
            skew=abs((qts-tts).total_seconds())
            if quote_age<0 or trade_age<0:
                raise RuntimeError(f"WEALTHNOW_FUTURE_TIMESTAMP_{sym}")
            if quote_age>60:
                raise RuntimeError(f"WEALTHNOW_QUOTE_STALE_{sym}:{quote_age:.1f}")
            if trade_age>60:
                raise RuntimeError(f"WEALTHNOW_TRADE_STALE_{sym}:{trade_age:.1f}")
            if skew>15:
                raise RuntimeError(f"WEALTHNOW_QUOTE_TRADE_SKEW_{sym}:{skew:.1f}")
            details[sym]={
              "bid":bid,"ask":ask,"last":last,
              "bid_event_timestamp":qts.isoformat(),"ask_event_timestamp":qts.isoformat(),"trade_timestamp":tts.isoformat(),
              "quote_age_seconds":round(quote_age,3),"trade_age_seconds":round(trade_age,3),
              "max_quote_trade_skew_seconds":round(skew,3),
              "source_label":snap.get("source"),"is_delayed":False
            }
        base["scheduler_callability"]="PASS"
        base["technical_evidence"]=details
        base["technical_status"]="PASS"
        base.update({"status":"G9_PASS","reason":"A_B_C_D_ALL_PROVEN","g9_pass":True})
    except Exception as e:
        base.update({"technical_status":"FAIL_CLOSED","status":"G9_NOT_PASS","reason":f"{type(e).__name__}:{str(e)[:240]}","g9_pass":False})
    write(base)


def paper_event_ts(value):
    if value is None:
        return None
    try:
        if isinstance(value,(int,float)):
            x=float(value)
            if x>10_000_000_000:
                x/=1000.0
            return datetime.fromtimestamp(x,tz=timezone.utc)
        s=str(value).strip()
        if s.replace(".","",1).isdigit():
            x=float(s)
            if x>10_000_000_000:
                x/=1000.0
            return datetime.fromtimestamp(x,tz=timezone.utc)
        return parse_ts(s)
    except Exception:
        return None

def paper_request_json(method,url,token=None,payload=None):
    headers={"Accept":"application/json"}
    data=None
    if token:
        headers["Authorization"]=f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"]="application/json"
        data=json.dumps(payload,separators=(",",":")).encode()
    req=urllib.request.Request(url,data=data,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=20,context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode())

def run_paper_invest_technical(base):
    api_key=os.getenv("PAPER_INVEST_API_KEY","").strip()
    if not api_key:
        base.update({"status":"NOT_CONFIGURED","reason":"PAPER_INVEST_API_KEY_NOT_CONFIGURED","scheduler_callability":"BLOCKED_MISSING_SECRET"})
        write(base); return
    if not is_rth():
        base.update({"technical_status":"NOT_RTH_NO_FRESHNESS_JUDGMENT","status":"WAITING_RTH","reason":"STRICT_G9_REQUIRES_LIVE_RTH_FRESHNESS_PROOF"})
        write(base); return
    try:
        auth=paper_request_json("POST","https://api.paperinvest.io/v1/auth/token",payload={"apiKey":api_key})
        token=((auth.get("token") or auth.get("access_token") or auth.get("accessToken")) if isinstance(auth,dict) else None)
        if not token:
            raise RuntimeError("PAPER_AUTH_NO_ACCESS_TOKEN")
        utcnow=datetime.now(timezone.utc)
        details={}
        for sym in SYMBOLS:
            q=paper_request_json("GET",f"https://api.paperinvest.io/v1/market-data/quote/{sym}",token=token)
            t=paper_request_json("GET",f"https://api.paperinvest.io/v1/market-data/trade/{sym}",token=token)
            if not isinstance(q,dict) or not isinstance(t,dict):
                raise RuntimeError(f"PAPER_SCHEMA_MISMATCH_{sym}")
            bid=float(q["bid"]); ask=float(q["ask"])
            last=float(t.get("price"))
            qts=paper_event_ts(q.get("timestamp"))
            tts=paper_event_ts(t.get("timestamp"))
            if min(bid,ask,last)<=0 or bid>ask or not qts or not tts:
                raise RuntimeError(f"PAPER_INVALID_QUOTE_TRADE_{sym}")
            quote_age=(utcnow-qts).total_seconds()
            trade_age=(utcnow-tts).total_seconds()
            skew=abs((qts-tts).total_seconds())
            if quote_age<0 or trade_age<0:
                raise RuntimeError(f"PAPER_FUTURE_TIMESTAMP_{sym}")
            if quote_age>60:
                raise RuntimeError(f"PAPER_QUOTE_STALE_{sym}:{quote_age:.1f}")
            if trade_age>60:
                raise RuntimeError(f"PAPER_TRADE_STALE_{sym}:{trade_age:.1f}")
            if skew>15:
                raise RuntimeError(f"PAPER_QUOTE_TRADE_SKEW_{sym}:{skew:.1f}")
            details[sym]={
              "bid":bid,"ask":ask,"last":last,
              "bid_event_timestamp":qts.isoformat(),
              "ask_event_timestamp":qts.isoformat(),
              "trade_timestamp":tts.isoformat(),
              "quote_age_seconds":round(quote_age,3),
              "trade_age_seconds":round(trade_age,3),
              "max_quote_trade_skew_seconds":round(skew,3),
              "is_delayed":False,
              "provider_claim":"REALTIME_NBBO"
            }
        base["scheduler_callability"]="PASS"
        base["technical_evidence"]=details
        base["technical_status"]="PASS"
        base.update({"status":"G9_PASS","reason":"A_B_C_D_ALL_PROVEN","g9_pass":True})
    except Exception as e:
        base.update({"technical_status":"FAIL_CLOSED","status":"G9_NOT_PASS","reason":f"{type(e).__name__}:{str(e)[:240]}","g9_pass":False})
    write(base)

def run_clearstreet_technical(base):
    token=os.getenv("CLEARSTREET_API_KEY","").strip()
    if not token:
        base.update({"status":"NOT_CONFIGURED","reason":"CLEARSTREET_API_KEY_NOT_CONFIGURED","scheduler_callability":"BLOCKED_MISSING_SECRET"})
        write(base); return
    if not is_rth():
        base.update({"technical_status":"NOT_RTH_NO_FRESHNESS_JUDGMENT","status":"WAITING_RTH","reason":"STRICT_G9_REQUIRES_LIVE_RTH_FRESHNESS_PROOF"})
        write(base); return
    try:
        utcnow=datetime.now(timezone.utc)
        details={}
        for sym in SYMBOLS:
            url="https://api.clearstreet.com/v1/market-data/snapshot?"+urllib.parse.urlencode({"instrument_ids":sym})
            j=get_json(token,url)
            rows=j.get("data") if isinstance(j,dict) else None
            if not isinstance(rows,list) or not rows:
                raise RuntimeError(f"CLEARSTREET_SNAPSHOT_SCHEMA_MISMATCH_{sym}")
            snap=next((x for x in rows if isinstance(x,dict) and str(x.get("symbol") or "").upper()==sym),rows[0])
            if not isinstance(snap,dict):
                raise RuntimeError(f"CLEARSTREET_SNAPSHOT_ROW_INVALID_{sym}")
            quote=snap.get("last_quote")
            trade=snap.get("last_trade")
            if not isinstance(quote,dict) or not isinstance(trade,dict):
                raise RuntimeError(f"CLEARSTREET_QUOTE_TRADE_MISSING_{sym}")
            bid=float(quote["bid"]); ask=float(quote["ask"]); last=float(trade["price"])
            bts=parse_ts(quote.get("bid_timestamp"))
            ats=parse_ts(quote.get("ask_timestamp"))
            tts=parse_ts(trade.get("timestamp"))
            if min(bid,ask,last)<=0 or bid>ask or not bts or not ats or not tts:
                raise RuntimeError(f"CLEARSTREET_INVALID_NBBO_TRADE_{sym}")
            bid_age=(utcnow-bts).total_seconds()
            ask_age=(utcnow-ats).total_seconds()
            trade_age=(utcnow-tts).total_seconds()
            quote_age=max(bid_age,ask_age)
            skew=max(abs((bts-tts).total_seconds()),abs((ats-tts).total_seconds()))
            if bid_age<0 or ask_age<0 or trade_age<0:
                raise RuntimeError(f"CLEARSTREET_FUTURE_TIMESTAMP_{sym}")
            if quote_age>60:
                raise RuntimeError(f"CLEARSTREET_QUOTE_STALE_{sym}:{quote_age:.1f}")
            if trade_age>60:
                raise RuntimeError(f"CLEARSTREET_TRADE_STALE_{sym}:{trade_age:.1f}")
            if skew>15:
                raise RuntimeError(f"CLEARSTREET_QUOTE_TRADE_SKEW_{sym}:{skew:.1f}")
            details[sym]={
              "bid":bid,"ask":ask,"last":last,
              "bid_event_timestamp":bts.isoformat(),
              "ask_event_timestamp":ats.isoformat(),
              "trade_timestamp":tts.isoformat(),
              "bid_venue":quote.get("bid_venue"),
              "ask_venue":quote.get("ask_venue"),
              "trade_venue":trade.get("venue"),
              "quote_age_seconds":round(quote_age,3),
              "trade_age_seconds":round(trade_age,3),
              "max_quote_trade_skew_seconds":round(skew,3),
              "is_delayed":False,
              "provider_claim":"NATIONAL_NBBO"
            }
        base["scheduler_callability"]="PASS"
        base["technical_evidence"]=details
        base["technical_status"]="PASS"
        base.update({"status":"G9_PASS","reason":"A_B_C_D_ALL_PROVEN","g9_pass":True})
    except Exception as e:
        base.update({"technical_status":"FAIL_CLOSED","status":"G9_NOT_PASS","reason":f"{type(e).__name__}:{str(e)[:240]}","g9_pass":False})
    write(base)


def main():
    authority=json.loads(AUTH.read_text())
    adapter_contract=json.loads(ADAPTER_CONTRACT.read_text())
    provider=str(authority.get("provider") or "UNSPECIFIED").upper()
    adapter=(adapter_contract.get("adapters") or {}).get(provider) or {}
    base={
      "schema":"XRAY_STRICT_G9_RUNTIME_V1",
      "provider":provider,
      "adapter_contract_schema":adapter_contract.get("schema"),
      "adapter_status":adapter.get("status","MISSING"),
      "generated_at_utc":now_iso(),
      "execution":"NONE",
      "real_money":"NO-GO",
      "alpha_authority":False,
      "required":{"A":"consolidated Tape-C/NBBO lineage","B":"bid+ask+last with independent quote/trade timestamps","C":"lawful intended automated permanent-$0 entitlement","D":"canonical scheduler callability"},
      "authority_status":authority.get("status"),
      "g9_pass":False,
    }
    if authority.get("status")!="PROVEN":
        base.update({"status":"BLOCKED_ENTITLEMENT_AUTHORITY_UNPROVEN","reason":"PRIMARY_SOURCE_LINEAGE_OR_AUTOMATED_PERMANENT_ZERO_RIGHT_NOT_PROVEN"})
        # Fail closed before any provider call. Negative/unproven entitlement
        # evidence is authoritative for strict G9 and must not trigger
        # credential refreshes or technical probes that cannot become PASS.
        write(base); return

    if adapter.get("status")!="IMPLEMENTED":
        base.update({"status":"BLOCKED_PROVIDER_ADAPTER_NOT_IMPLEMENTED","reason":"PROVEN_AUTHORITY_HAS_NO_IMPLEMENTED_STRICT_G9_RUNTIME_ADAPTER"})
        write(base); return

    if provider=="WEALTHNOW":
        run_wealthnow_technical(base); return

    if provider=="PAPER_INVEST":
        run_paper_invest_technical(base); return

    if provider=="CLEAR_STREET":
        run_clearstreet_technical(base); return

    if provider!="TRADESTATION":
        base.update({"status":"BLOCKED_PROVIDER_DISPATCH_NOT_IMPLEMENTED","reason":"IMPLEMENTED_ADAPTER_HAS_NO_RUNTIME_DISPATCH"})
        write(base); return

    token=None
    try:
        token,scope,err=refresh_token()
        base["oauth_scope_observed"]=scope
        if err:
            base.setdefault("status","NOT_CONFIGURED")
            base.setdefault("reason",err)
            write(base); return
        base["scheduler_callability"]="PASS"
    except Exception as e:
        base.update({"status":"AUTH_OR_CONNECTIVITY_UNKNOWN","reason":f"{type(e).__name__}:{str(e)[:220]}"})
        write(base); return

    if not is_rth():
        base.update({"technical_status":"NOT_RTH_NO_FRESHNESS_JUDGMENT"})
        base.setdefault("status","BLOCKED_ENTITLEMENT_AUTHORITY_UNPROVEN" if authority.get("status")!="PROVEN" else "WAITING_RTH")
        base.setdefault("reason","STRICT_G9_REQUIRES_LIVE_RTH_FRESHNESS_PROOF")
        write(base); return

    try:
        snap=get_json(token,"https://api.tradestation.com/v3/marketdata/quotes/"+",".join(SYMBOLS))
        rows=snap.get("Quotes") if isinstance(snap,dict) else None
        if not isinstance(rows,list): raise RuntimeError("QUOTE_SNAPSHOT_SCHEMA_MISMATCH")
        by={str(x.get("Symbol","")).upper():x for x in rows}
        details={}
        utcnow=datetime.now(timezone.utc)
        for sym in SYMBOLS:
            q=by.get(sym)
            if not q: raise RuntimeError(f"MISSING_QUOTE_{sym}")
            mf=q.get("MarketFlags") or {}
            if mf.get("IsDelayed") is not False:
                raise RuntimeError(f"DELAYED_OR_UNKNOWN_QUOTE_{sym}")
            bid=float(q["Bid"]); ask=float(q["Ask"]); last=float(q["Last"])
            tt=parse_ts(q.get("TradeTime"))
            if min(bid,ask,last)<=0 or bid>ask or not tt:
                raise RuntimeError(f"INVALID_QUOTE_{sym}")
            depth=stream_first_depth(token,sym)
            b=best(depth.get("Bids"),"bid"); a=best(depth.get("Asks"),"ask")
            if not b or not a: raise RuntimeError(f"MISSING_DEPTH_TIMESTAMP_{sym}")
            best_bid,bid_ts,bid_venue=b
            best_ask,ask_ts,ask_venue=a
            if best_bid>best_ask: raise RuntimeError(f"CROSSED_DEPTH_{sym}")
            quote_age=max((utcnow-bid_ts).total_seconds(),(utcnow-ask_ts).total_seconds())
            trade_age=(utcnow-tt).total_seconds()
            skew=max(abs((bid_ts-tt).total_seconds()),abs((ask_ts-tt).total_seconds()))
            if quote_age<0 or trade_age<0: raise RuntimeError(f"FUTURE_TIMESTAMP_{sym}")
            if quote_age>60: raise RuntimeError(f"QUOTE_STALE_{sym}:{quote_age:.1f}")
            if trade_age>60: raise RuntimeError(f"TRADE_STALE_{sym}:{trade_age:.1f}")
            if skew>15: raise RuntimeError(f"QUOTE_TRADE_SKEW_{sym}:{skew:.1f}")
            # The participant-depth inside market must not contradict the L1 snapshot.
            if abs(best_bid-bid)>0.011 or abs(best_ask-ask)>0.011:
                raise RuntimeError(f"DEPTH_L1_MISMATCH_{sym}")
            details[sym]={
              "snapshot_bid":bid,"snapshot_ask":ask,"snapshot_last":last,
              "bid_event_timestamp":bid_ts.isoformat(),"ask_event_timestamp":ask_ts.isoformat(),"trade_timestamp":tt.isoformat(),
              "quote_age_seconds":round(quote_age,3),"trade_age_seconds":round(trade_age,3),"max_quote_trade_skew_seconds":round(skew,3),
              "bid_participant":bid_venue,"ask_participant":ask_venue,"is_delayed":False
            }
        base["technical_evidence"]=details
        base["technical_status"]="PASS_AWAITING_ENTITLEMENT_AUTHORITY"
        if authority.get("status")=="PROVEN":
            base.update({"status":"G9_PASS","reason":"A_B_C_D_ALL_PROVEN","g9_pass":True})
        else:
            base.update({"status":"BLOCKED_ENTITLEMENT_AUTHORITY_UNPROVEN","reason":"TECHNICAL_B_D_PASS_BUT_A_C_REQUIRE_PRIMARY_SOURCE_PROOF","g9_pass":False})
    except Exception as e:
        base.update({"technical_status":"FAIL_CLOSED","status":"G9_NOT_PASS","reason":f"{type(e).__name__}:{str(e)[:240]}","g9_pass":False})
    write(base)

if __name__=="__main__":
    main()
