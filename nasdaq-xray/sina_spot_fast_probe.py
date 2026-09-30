#!/usr/bin/env python3
import json, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime, timezone

OUT=Path(__file__).resolve().parent/"sina_spot_fast_probe.json"
BUILD="2026-10-01.2"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

def urshift(x,n):
    return (x & 0xffffffff) >> (n & 31)

def r64(s,b):
    x=(s | (s << 6))
    return urshift(x,b%6) & 63

def sina_hash(s):
    alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_$'
    a=[]; c=[]
    bs=s.encode('utf-8')
    for i,c0 in enumerate(bs):
        c.append(c0)
        if len(c)==3 or i==len(bs)-1:
            while len(c)<3: c.append(0)
            a.append((c[0]>>2)&63)
            a.append(((c[1]>>4)|(c[0]<<6))&63)
            a.append(((c[1]<<4)|(c[2]>>2))&63)
            a.append(c[2]&63)
            c=[]
    while len(a)<16:a.append(0)
    r=0
    for i in range(len(a)):
        r ^= (r64(a[i] ^ (r | i), i) ^ r64(i,r)) & 63
    for i in range(len(a)):
        a[i]=(r64((r | (i & a[i])),r)^a[i])&63
        r += a[i]
    for i in range(16,len(a)):
        a[i%16]^=(a[i]+(i>>4))&63
    return ''.join(alphabet[a[i]] for i in range(16))

page=1; num=20
decoded=f"US_CategoryService.getList?page={page}&num={num}&sort=mktcap&asc=0&market=NASDAQ&id="
token=sina_hash(decoded)
base=f"http://stock.finance.sina.com.cn/usstock/api/jsonp.php/IO.XSRV2.CallbackList[{token}]/US_CategoryService.getList"
params={"page":str(page),"num":str(num),"sort":"mktcap","asc":"0","market":"NASDAQ","id":""}
url=base+"?"+urllib.parse.urlencode(params)
req=urllib.request.Request(url,headers={"User-Agent":UA,"Referer":"https://finance.sina.com.cn/stock/usstock/sector.shtml"})
with urllib.request.urlopen(req,timeout=35) as r:
    txt=r.read().decode("utf-8","replace")
start=txt.find("({"); end=txt.rfind(");")
if start<0 or end<0: raise RuntimeError("JSONP_PARSE_FAIL")
obj=json.loads(txt[start+1:end])
rows=obj.get("data") or []
aapl=[x for x in rows if str(x.get("symbol","")).upper()=="AAPL"]
out={
 "updated_at_utc":datetime.now(timezone.utc).isoformat(),
 "count_reported":obj.get("count"),
 "rows_returned":len(rows),
 "keys":sorted(rows[0].keys()) if rows else [],
 "sample":rows[:2],
 "aapl":aapl[:1],
 "status":"PASS" if rows else "FAIL",
 "execution":"NONE","real_money":"NO-GO"
}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(json.dumps(out,sort_keys=True))
