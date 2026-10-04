#!/usr/bin/env python3
from __future__ import annotations
import json, re, html as htmlmod, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
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
 "security_status":"https://www.nasdaqtrader.com/Trader.aspx?id=nasdaq-security-status-updates",
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
def parse_security_status_html(txt):
    rows=[]
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>",txt,flags=re.I|re.S):
        cells=[]
        for raw in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>",tr,flags=re.I|re.S):
            s=re.sub(r"<[^>]+>"," ",raw)
            s=htmlmod.unescape(re.sub(r"\s+"," ",s)).strip()
            cells.append(s)
        if len(cells)>=4 and re.fullmatch(r"\d{4}-\d{2}-\d{2}",cells[0] or ""):
            rows.append({
              "EffectiveDate":cells[0],"Symbol":cells[1].upper(),"CompanyName":cells[2],
              "IssueEvent":cells[3],"DowngradeReason":cells[4] if len(cells)>4 else "",
              "OldFinancialStatus":cells[5] if len(cells)>5 else "",
              "NewFinancialStatus":cells[6] if len(cells)>6 else "",
            })
    return rows

def pointer_asof():
    try:
        p=json.loads((ROOT/"chatgpt_canonical_state_v2.json").read_text())
        s=p.get("state_json") or {}
        if isinstance(s,str): s=json.loads(s)
        x=str(s.get("asof_et") or "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}",x): return x
    except Exception:
        pass
    return None

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
    # Official Security Status Updates, queried from current canonical ASOF
    # through today's New York calendar date. This captures forward-effective
    # additions/suspensions/status/name changes without inventing old->new identity.
    try:
        start=pointer_asof()
        end=datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        if not start: start=end
        def mmddyyyy(x):
            y,m,d=x.split("-"); return f"{m}/{d}/{y}"
        url=(SOURCES["security_status"]+"&from="+mmddyyyy(start)+"&to="+mmddyyyy(end))
        t=fetch_text("NASDAQ_SECURITY_STATUS",url,UA,timeout=20,cache_ttl=300)
        rows=parse_security_status_html(t)
        susp=sorted({r["Symbol"] for r in rows if "suspension" in r.get("IssueEvent","").lower() and r.get("Symbol")})
        out["sources"]["security_status"]={
          "status":"PASS","url":url,"query_start":start,"query_end":end,
          "row_count":len(rows),"rows":rows[:500],"suspension_symbols":susp,
          "symbol_change_mapping_rule":"UNKNOWN_UNLESS_CORROBORATED"
        }
    except Exception as e:
        out["sources"]["security_status"]={"status":"UNKNOWN","url":SOURCES["security_status"],"reason":f"{type(e).__name__}:{str(e)[:180]}"}

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
    halt_syms=out["sources"].get("trade_halts",{}).get("active_halt_symbols",[])
    susp_syms=out["sources"].get("security_status",{}).get("suspension_symbols",[])
    out["candidate_safety"]={
        "halt_guard_status":out["sources"].get("trade_halts",{}).get("status","UNKNOWN"),
        "security_status_guard_status":out["sources"].get("security_status",{}).get("status","UNKNOWN"),
        "active_halt_symbols":halt_syms,
        "security_status_suspension_symbols":susp_syms,
        "veto_symbols":sorted(set(halt_syms)|set(susp_syms)),
        "rule":"REGISTERED_RESEARCH_CANDIDATE_DELIVERY_MUST_FAIL_CLOSED_ON_ACTIVE_HALT_SECURITY_SUSPENSION_OR_UNKNOWN_OFFICIAL_SAFETY_FEED"
    }
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":out["status"],"sources":{k:v["status"] for k,v in out["sources"].items()}},sort_keys=True))
if __name__=="__main__": main()
