#!/usr/bin/env python3
import csv, io, json, tempfile, urllib.request, zipfile
from datetime import datetime, timezone
from pathlib import Path

OUT=Path(__file__).resolve().parent/"stooq_symbol_probe.json"
URL="https://static.stooq.com/db/h/d_us_txt.zip"
TARGETS={"BLLN","CBRS","DFTX","EQPT","FRVO","HONA","INIO","MDLN","MMED","NAVN","QNT","SKHY","SOLS","SPCX","VSNT"}
UA="NASDAQ-SWING-XRAY/1.0"

def norm(x):
    x=(x or "").strip().upper()
    if x.endswith(".US"): x=x[:-3]
    return x

res={
  "schema":"XRAY_STOOQ_BULK_HISTORY_PROBE_V1",
  "updated_at_utc":datetime.now(timezone.utc).isoformat(),
  "execution":"NONE","real_money":"NO-GO","source":URL,
  "results":{}
}
try:
    with tempfile.TemporaryDirectory() as td:
        zpath=Path(td)/"d_us_txt.zip"
        req=urllib.request.Request(URL,headers={"User-Agent":UA})
        with urllib.request.urlopen(req,timeout=120) as r, open(zpath,"wb") as w:
            while True:
                b=r.read(1024*1024)
                if not b: break
                w.write(b)
        res["zip_bytes"]=zpath.stat().st_size
        found=set()
        with zipfile.ZipFile(zpath) as zf:
            for name in zf.namelist():
                if not name.lower().endswith(".txt"): continue
                try:
                    raw=zf.read(name).decode("utf-8","ignore")
                    rd=csv.reader(io.StringIO(raw))
                    next(rd,None)
                    rows=[]
                    for r in rd:
                        if len(r)<9: continue
                        s=norm(r[0])
                        if s not in TARGETS: continue
                        d=r[2]
                        try:
                            c=float(r[7]);v=float(r[8])
                        except Exception:
                            continue
                        if len(d)==8 and c>0 and v>=0:
                            rows.append((d,c,v))
                    if not rows: continue
                    s=norm(next(csv.reader(io.StringIO(raw))).pop(0) if False else "")
                except Exception:
                    continue
                # A Stooq text file is one symbol. Recover symbol from first data row.
                try:
                    rd2=csv.reader(io.StringIO(raw)); next(rd2,None); first=next(rd2)
                    sym=norm(first[0])
                except Exception:
                    continue
                if sym not in TARGETS: continue
                rows.sort(key=lambda x:x[0])
                found.add(sym)
                res["results"][sym]={
                  "rows":len(rows),"first":rows[0][0],"last":rows[-1][0],
                  "has_asof_20261002":any(x[0]=="20261002" for x in rows)
                }
        for s in sorted(TARGETS-found):
            res["results"][s]={"rows":0,"status":"MISSING"}
    res["status"]="PASS"
except Exception as e:
    res["status"]="ERROR"
    res["error"]=type(e).__name__+":"+str(e)[:500]
OUT.write_text(json.dumps(res,indent=2,sort_keys=True)+"\n")
print(json.dumps(res,sort_keys=True))
