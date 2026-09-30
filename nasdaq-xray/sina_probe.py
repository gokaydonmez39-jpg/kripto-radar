#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path
import akshare as ak

OUT=Path(__file__).resolve().parent/"sina_probe.json"
symbols=["AAPL","MSFT","NVDA"]
out={"updated_at_utc":datetime.now(timezone.utc).isoformat(),"results":{},"execution":"NONE","real_money":"NO-GO"}
for s in symbols:
    try:
        df=ak.stock_us_daily(symbol=s, adjust="")
        rows=len(df)
        last=None
        if rows:
            r=df.tail(1).iloc[0].to_dict()
            last={k:(str(v) if k=="date" else float(v) if hasattr(v,"__float__") else str(v)) for k,v in r.items()}
        out["results"][s]={"rows":rows,"last":last,"status":"PASS" if rows>=260 else "FAIL"}
    except Exception as e:
        out["results"][s]={"status":"ERROR","error":type(e).__name__+":"+str(e)[:300]}
out["status"]="PASS" if all(v.get("status")=="PASS" for v in out["results"].values()) else "FAIL"
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,default=str)+"\n")
print(json.dumps(out,sort_keys=True,default=str))
