#!/usr/bin/env python3
from __future__ import annotations
import json, os, ssl, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
AUTH=ROOT/"g9_entitlement_authority.json"
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

def main():
    authority=json.loads(AUTH.read_text())
    base={
      "schema":"XRAY_STRICT_G9_RUNTIME_V1",
      "provider":"TRADESTATION",
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
        # Continue to technical probe if credentials exist, but it cannot become PASS.
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
