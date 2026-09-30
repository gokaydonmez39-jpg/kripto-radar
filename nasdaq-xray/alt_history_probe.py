#!/usr/bin/env python3
import json, time
from datetime import datetime, timezone
from pathlib import Path
import akshare as ak

OUT=Path(__file__).resolve().parent/"alt_history_probe.json"
BUILD="2026-10-01.2"
symbols=["AAPL","MSFT","NVDA"]
results={}\nspot_probe={}

for sym in symbols:
    rec={}
    try:
        df=ak.stock_us_daily(symbol=sym, adjust="")
        rec["sina_count"]=0 if df is None else int(len(df))
        if df is not None and not df.empty:
            rec["sina_first"]=str(df.iloc[0].to_dict())
            rec["sina_last"]=str(df.iloc[-1].to_dict())
            rec["sina_pass"]=len(df)>=260
        else:
            rec["sina_pass"]=False
    except Exception as e:
        rec["sina_pass"]=False
        rec["sina_error"]=f"{type(e).__name__}:{str(e)[:220]}"
    try:
        df2=ak.stock_us_hist(symbol="105."+sym, period="daily", start_date="20240101", end_date="20500101", adjust="")
        rec["eastmoney_count"]=0 if df2 is None else int(len(df2))
        rec["eastmoney_pass"]=bool(df2 is not None and len(df2)>=260)
    except Exception as e:
        rec["eastmoney_pass"]=False
        rec["eastmoney_error"]=f"{type(e).__name__}:{str(e)[:220]}"
    results[sym]=rec
    time.sleep(1.2)

try:
    spot=ak.stock_us_spot()
    spot_probe["count"]=0 if spot is None else int(len(spot))
    spot_probe["columns"]=[] if spot is None else [str(x) for x in spot.columns]
    if spot is not None and not spot.empty:
        row=spot[spot.astype(str).apply(lambda r: r.str.contains("AAPL", case=False, na=False).any(), axis=1)]
        spot_probe["aapl_rows"]=row.head(3).to_dict(orient="records")
        spot_probe["sample"]=spot.head(3).to_dict(orient="records")
    spot_probe["pass"]=bool(spot is not None and len(spot)>1000)
except Exception as e:
    spot_probe["pass"]=False
    spot_probe["error"]=f"{type(e).__name__}:{str(e)[:300]}"

status="PASS" if any(r.get("sina_pass") for r in results.values()) else "FAIL"
out={
 "updated_at_utc":datetime.now(timezone.utc).isoformat(),
 "status":status,
 "results":results,\n "spot_probe":spot_probe,
 "execution":"NONE","real_money":"NO-GO"
}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(json.dumps(out,sort_keys=True))
