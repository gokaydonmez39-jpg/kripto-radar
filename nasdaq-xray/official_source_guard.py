#!/usr/bin/env python3
from __future__ import annotations
import json, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from resilience_runtime import fetch_text

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"canonical_official_source_guard.json"
UA={"User-Agent":"NASDAQ-SWING-XRAY/1.0 research github.com/gokaydonmez39-jpg/kripto-radar","Accept":"*/*"}
SOURCES={
 "trading_system_adds_deletes":"https://www.nasdaqtrader.com/dynamic/SymDir/TradingSystemAddsDeletes.txt",
 "trade_halts":"https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts",
 "system_status_ipo":"https://www.nasdaqtrader.com/rss.aspx?feed=systemstatus&subject=IPO",
 "system_status_selfhelp":"https://www.nasdaqtrader.com/rss.aspx?feed=systemstatus&subject=SELFHELP",
}
def now(): return datetime.now(timezone.utc).isoformat()
def parse_pipe(txt):
    ls=[x for x in txt.splitlines() if x.strip()]
    if not ls: raise ValueError("EMPTY_PIPE_FILE")
    hdr=ls[0].split("|"); rows=[]
    for line in ls[1:]:
        if line.startswith("File Creation Time:"): continue
        vals=line.split("|")
        if len(vals)>=len(hdr):
            rows.append(dict(zip(hdr,vals)))
    return rows
def parse_rss(txt):
    root=ET.fromstring(txt); out=[]
    for item in root.findall(".//item"):
        row={}
        for child in list(item):
            tag=child.tag.split("}")[-1]
            row[tag]=(child.text or "").strip()
        out.append(row)
    return out
def main():
    out={"schema":"XRAY_OFFICIAL_SOURCE_GUARD_V1","execution":"NONE","real_money":"NO-GO","alpha_authority":False,
         "authority":"NASDAQTRADER_OFFICIAL_SAFETY_AND_PIT_SUPPORT","generated_at_utc":now(),"sources":{},
         "rules":{"halt_poll_min_seconds":60,"security_status_symbol_change_mapping":"UNKNOWN_UNLESS_CORROBORATED","unknown_never_pass":True}}
    # Current add/delete delta
    try:
        t=fetch_text("NASDAQ_ADDS_DELETES",SOURCES["trading_system_adds_deletes"],UA,timeout=20,cache_ttl=300)
        rows=parse_pipe(t)
        out["sources"]["trading_system_adds_deletes"]={"status":"PASS","url":SOURCES["trading_system_adds_deletes"],"row_count":len(rows),"rows":rows[:250]}
    except Exception as e:
        out["sources"]["trading_system_adds_deletes"]={"status":"UNKNOWN","url":SOURCES["trading_system_adds_deletes"],"reason":f"{type(e).__name__}:{str(e)[:180]}"}
    # Halt feed: record official rows; do not infer active/resumed state beyond feed fields.
    try:
        t=fetch_text("NASDAQ_TRADE_HALTS",SOURCES["trade_halts"],UA,timeout=20,cache_ttl=60)
        rows=parse_rss(t)
        # Active-halt classification uses only explicit official feed fields:
        # no ResumptionTradeTime/ResumptionDate => still unresolved/active for
        # candidate-safety purposes. No inference from reason code or age.
        active=sorted({
            str(x.get("IssueSymbol") or "").strip().upper()
            for x in rows
            if str(x.get("IssueSymbol") or "").strip()
            and not str(x.get("ResumptionTradeTime") or "").strip()
            and not str(x.get("ResumptionDate") or "").strip()
        })
        out["sources"]["trade_halts"]={
            "status":"PASS","url":SOURCES["trade_halts"],"item_count":len(rows),
            "items":rows[:250],"active_halt_symbols":active,
            "active_halt_count":len(active),
            "active_state_rule":"EXPLICIT_EMPTY_RESUMPTION_FIELDS_ONLY"
        }
    except Exception as e:
        out["sources"]["trade_halts"]={"status":"UNKNOWN","url":SOURCES["trade_halts"],"reason":f"{type(e).__name__}:{str(e)[:180]}"}
    for k in ("system_status_ipo","system_status_selfhelp"):
        try:
            t=fetch_text("NASDAQ_"+k.upper(),SOURCES[k],UA,timeout=20,cache_ttl=60)
            rows=parse_rss(t)
            out["sources"][k]={"status":"PASS","url":SOURCES[k],"item_count":len(rows),"items":rows[:100]}
        except Exception as e:
            out["sources"][k]={"status":"UNKNOWN","url":SOURCES[k],"reason":f"{type(e).__name__}:{str(e)[:180]}"}
    sts=[v.get("status") for v in out["sources"].values()]
    out["status"]="PASS" if sts and all(x=="PASS" for x in sts) else "DEGRADED"
    out["candidate_safety"]={
        "halt_guard_status":out["sources"].get("trade_halts",{}).get("status","UNKNOWN"),
        "active_halt_symbols":out["sources"].get("trade_halts",{}).get("active_halt_symbols",[]),
        "rule":"REGISTERED_RESEARCH_CANDIDATE_DELIVERY_MUST_FAIL_CLOSED_ON_ACTIVE_HALT_OR_UNKNOWN_HALT_FEED"
    }
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":out["status"],"sources":{k:v["status"] for k,v in out["sources"].items()}},sort_keys=True))
if __name__=="__main__": main()
