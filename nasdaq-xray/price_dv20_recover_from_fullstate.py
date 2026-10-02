#!/usr/bin/env python3
from __future__ import annotations
import json, os, hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from price_dv20_phase import eval_one, expected20

ROOT=Path(__file__).resolve().parent
INPUT=Path(os.getenv("XRAY_FULLSTATE_INPUT",str(ROOT/"canonical_full_hard_gate_20260930_state.json")))
OUT=Path(os.getenv("XRAY_PRICE_DV20_RECOVER_OUT",str(ROOT/"canonical_price_dv20_20260930.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_PHASE_WORKERS","12"))
DEFER_TO_BRIDGE=os.getenv("XRAY_DYNAMIC_AUTHENTICATED_PRICE_BRIDGE","0")=="1"
HARD_PRICE=10.0
HARD_DV20=50_000_000.0


def num(x):
    try:
        v=float(x)
        return v if v==v and abs(v)!=float("inf") else None
    except Exception:
        return None

def load_exception_bridge(asof,queue_hash):
    path=ROOT/f"canonical_resolver_bridge_{asof.replace('-','')}.json"
    if not path.exists():
        return {},{"status":"ABSENT","path":str(path)}
    try:
        obj=json.loads(path.read_text())
        if obj.get("schema")!="XRAY_RESOLVER_EPOCH_RESULT_V1" or obj.get("status")!="COMMITTED":
            raise ValueError("SCHEMA_OR_STATUS")
        if obj.get("task_id")!=TASK_ID or obj.get("execution")!="NONE" or obj.get("real_money")!="NO-GO":
            raise ValueError("SAFETY_OR_TASK")
        if obj.get("asof_et")!=asof or obj.get("queue_hash")!=queue_hash:
            raise ValueError("BINDING")
        if (
          obj.get("compiled_policy_hash")!="a663cd5046e36cfb8f6b4674d0e9bea4c92edcf5398e73c8c4ed9eb01da36d60"
          or obj.get("compiled_policy_version")!="C4.12"
          or obj.get("compiled_policy_blob_sha")!="2d335057b717f849274068e01837e5ea034d96de"
        ):
            raise ValueError("POLICY_BINDING")
        if obj.get("settlement_required") is True and obj.get("settlement_status")!="PASS":
            raise ValueError("SETTLEMENT_BINDING")
        prs=obj.get("price_resolutions") or {}
        if not isinstance(prs,dict): raise ValueError("PRICE_RESOLUTIONS")
        compact=obj.get("price_resolution_compact")
        encoding=obj.get("result_encoding")
        if compact is not None:
            if encoding not in {"ALPACA_SIP_COMPACT_V1","ALPACA_SIP_COMPACT_V2","RALLIES_SCANNER_EXACT20_V1"} or not isinstance(compact,dict):
                raise ValueError("COMPACT_ENCODING")
            src="RALLIES_CANDLESTICK_SCANNER_EXACT20_PRIMARY" if encoding=="RALLIES_SCANNER_EXACT20_V1" else "ALPACA_HISTORICAL_SIP_DAILY_BATCH_NON_G9"
            if encoding=="RALLIES_SCANNER_EXACT20_V1":
                fp=compact.get("fail_price_symbols") or []
                fd=compact.get("fail_dv20_symbols") or []
                ps=compact.get("pass_price_dv20_symbols") or []
                bc=compact.get("block_current_run") or {}
                un=compact.get("unresolved_symbols") or []
                if not all(isinstance(x,list) for x in [fp,fd,ps,un]) or not isinstance(bc,dict):
                    raise ValueError("RALLIES_COMPACT_TYPES")
                groups=[set(fp),set(fd),set(ps),set(bc),set(un)]
                vals=[fp,fd,ps,bc,un]
                if any(len(g)!=len(v) for g,v in zip(groups,vals)):
                    raise ValueError("RALLIES_COMPACT_DUPLICATES")
                for i in range(len(groups)):
                    for j in range(i+1,len(groups)):
                        if groups[i]&groups[j]: raise ValueError("RALLIES_COMPACT_OVERLAP")
                req=set(obj.get("price_unknown_symbols") or obj.get("symbols") or [])
                if set().union(*groups)!=req: raise ValueError("RALLIES_COMPACT_COVERAGE")
                for sym in fp:
                    prs[sym]={"decision":"FAIL_PRICE","source":src,"proof":"RALLIES_ASOF_CLOSE_LE_10","compact_terminal_proof":True}
                for sym in fd:
                    prs[sym]={"decision":"FAIL_DV20","source":src,"proof":"RALLIES_EXACT20_MEDIAN_LT_GATE","compact_terminal_proof":True}
                for sym in ps:
                    prs[sym]={
                      "decision":"PASS_PRICE_DV20","known_session_count":20,"missing_sessions":[],
                      "no_synthetic_bar":True,"source":src,"proof":"RALLIES_EXACT20_MEDIAN_GE_GATE",
                      "compact_terminal_proof":True,
                    }
                allowed_block_reasons={
                  "INSUFFICIENT_20_USABLE_DV20_SESSIONS_CONFIRMED",
                  "RALLIES_PRIMARY_EXACT20_INCOMPLETE_SPLIT_OR_SOURCE_ALIGNMENT_RISK",
                  "RALLIES_PRIMARY_EXACT20_INCOMPLETE_ZERO_TRADE_PLACEHOLDER_AMBIGUITY",
                  "NO_USABLE_ASOF_MARKET_DATA_CURRENT_RUN",
                }
                for sym,val in bc.items():
                    if not isinstance(val,dict) or val.get("reason") not in allowed_block_reasons:
                        raise ValueError("RALLIES_COMPACT_BLOCK_CURRENT")
                    n=val.get("observed_usable_sessions")
                    if n is not None and (not isinstance(n,int) or n<0 or n>=20):
                        raise ValueError("RALLIES_COMPACT_BLOCK_COUNT")
                    prs[sym]={
                      "decision":"BLOCK_CURRENT_RUN","reason":val["reason"],
                      "observed_usable_sessions":n,"source":src,
                      "proof":"FAIL_CLOSED_CURRENT_RUN_NONPASS",
                      "corroboration":val.get("corroboration"),
                    }
            elif encoding=="ALPACA_SIP_COMPACT_V2":
                fp=compact.get("fail_price") or {}
                fd=compact.get("fail_dv20") or {}
                pm=compact.get("pass_price_dv20") or {}
                bc=compact.get("block_current_run") or {}
                bp=compact.get("block_post_asof_listing") or {}
                un=compact.get("unresolved_symbols") or []
                if not all(isinstance(x,dict) for x in [fp,fd,pm,bc,bp]) or not isinstance(un,list):
                    raise ValueError("COMPACT_V2_TYPES")
                groups=[set(fp),set(fd),set(pm),set(bc),set(bp),set(un)]
                vals=[fp,fd,pm,bc,bp,un]
                if any(len(g)!=len(v) for g,v in zip(groups,vals)):
                    raise ValueError("COMPACT_DUPLICATES")
                for i in range(len(groups)):
                    for j in range(i+1,len(groups)):
                        if groups[i]&groups[j]: raise ValueError("COMPACT_OVERLAP")
                req=set(obj.get("price_unknown_symbols") or obj.get("symbols") or [])
                if set().union(*groups)!=req: raise ValueError("COMPACT_COVERAGE")
                for sym,val in fp.items():
                    px=num(val)
                    if px is None or px>HARD_PRICE: raise ValueError("COMPACT_FAIL_PRICE_GATE")
                    prs[sym]={"decision":"FAIL_PRICE","price":px,"source":src,"proof":"ASOF_CLOSE_LE_10"}
                for sym,val in fd.items():
                    if not isinstance(val,(list,tuple)) or len(val)<3: raise ValueError("COMPACT_FAIL_DV20_VALUE")
                    px=num(val[0]); metric=num(val[1]); proof=str(val[2])
                    if px is None or px<=HARD_PRICE or metric is None or metric>=HARD_DV20:
                        raise ValueError("COMPACT_FAIL_DV20_GATE")
                    if proof not in {"EXACT20_MEDIAN_LT_GATE","DV20_UPPER_BOUND_LT_GATE"}:
                        raise ValueError("COMPACT_FAIL_DV20_PROOF")
                    rec={"decision":"FAIL_DV20","price":px,"source":src,"proof":proof}
                    if proof=="EXACT20_MEDIAN_LT_GATE": rec["dv20"]=metric
                    else: rec["dv20_upper_bound"]=metric
                    prs[sym]=rec
                for sym,val in pm.items():
                    if not isinstance(val,(list,tuple)) or len(val)<2: raise ValueError("COMPACT_PASS_VALUE")
                    px=num(val[0]); dv=num(val[1])
                    if px is None or px<=HARD_PRICE or dv is None or dv<HARD_DV20:
                        raise ValueError("COMPACT_PASS_GATE")
                    prs[sym]={
                      "decision":"PASS_PRICE_DV20","price":px,"dv20":dv,
                      "known_session_count":20,"missing_sessions":[],"no_synthetic_bar":True,
                      "source":src,"proof":"EXACT20_MEDIAN_GE_GATE",
                    }
                for sym,val in bc.items():
                    if not isinstance(val,dict) or val.get("trade_status")!="Halted" or not val.get("last_bar"):
                        raise ValueError("COMPACT_BLOCK_CURRENT")
                    prs[sym]={"decision":"BLOCK_CURRENT_RUN","trade_status":"Halted","last_bar":val["last_bar"],"source":src,"proof":"HALTED_NO_ASOF_BAR"}
                for sym,val in bp.items():
                    d=(val or {}).get("first_trade_date") if isinstance(val,dict) else val
                    if not d or str(d)<=asof: raise ValueError("COMPACT_POST_ASOF")
                    prs[sym]={"decision":"BLOCK_POST_ASOF_LISTING","first_trade_date":str(d),"source":src,"proof":"FIRST_VALID_BAR_AFTER_ASOF"}
            else:
                fp=compact.get("fail_price_symbols") or []
                fd=compact.get("fail_dv20_symbols") or []
                pm=compact.get("pass_price_dv20") or {}
                bc=compact.get("block_current_run") or {}
                bp=compact.get("block_post_asof_listing") or {}
                un=compact.get("unresolved_symbols") or []
                if not all(isinstance(x,list) for x in [fp,fd,un]) or not all(isinstance(x,dict) for x in [pm,bc,bp]):
                    raise ValueError("COMPACT_TYPES")
                groups=[set(fp),set(fd),set(pm),set(bc),set(bp),set(un)]
                if any(len(g)!=len(v) for g,v in zip(groups,[fp,fd,pm,bc,bp,un])):
                    raise ValueError("COMPACT_DUPLICATES")
                for i in range(len(groups)):
                    for j in range(i+1,len(groups)):
                        if groups[i]&groups[j]: raise ValueError("COMPACT_OVERLAP")
                req=set(obj.get("price_unknown_symbols") or obj.get("symbols") or [])
                if set().union(*groups)!=req: raise ValueError("COMPACT_COVERAGE")
                # V1 is accepted for historical backward compatibility only.
                for sym in fp: prs[sym]={"decision":"FAIL_PRICE","source":src,"proof":"ASOF_CLOSE_LE_10","compact_terminal_proof":True}
                for sym in fd: prs[sym]={"decision":"FAIL_DV20","source":src,"proof":"EXACT20_OR_UPPER_BOUND_LT_GATE","compact_terminal_proof":True}
                for sym,val in pm.items():
                    px=num(val[0] if isinstance(val,(list,tuple)) else val.get("price"))
                    dv=num(val[1] if isinstance(val,(list,tuple)) else val.get("dv20"))
                    if px is None or px<=HARD_PRICE or dv is None or dv<HARD_DV20: raise ValueError("COMPACT_PASS_GATE")
                    prs[sym]={"decision":"PASS_PRICE_DV20","price":px,"dv20":dv,"known_session_count":20,"missing_sessions":[],"no_synthetic_bar":True,"source":src,"proof":"EXACT20_MEDIAN_GE_GATE"}
                for sym,val in bc.items():
                    if not isinstance(val,dict) or val.get("trade_status")!="Halted" or not val.get("last_bar"): raise ValueError("COMPACT_BLOCK_CURRENT")
                    prs[sym]={"decision":"BLOCK_CURRENT_RUN","trade_status":"Halted","last_bar":val["last_bar"],"source":src,"proof":"HALTED_NO_ASOF_BAR"}
                for sym,val in bp.items():
                    d=(val or {}).get("first_trade_date") if isinstance(val,dict) else val
                    if not d or str(d)<=asof: raise ValueError("COMPACT_POST_ASOF")
                    prs[sym]={"decision":"BLOCK_POST_ASOF_LISTING","first_trade_date":str(d),"source":src,"proof":"FIRST_VALID_BAR_AFTER_ASOF"}
        return prs,{"status":"PASS","path":str(path),"symbol_hash":obj.get("symbol_hash"),"source_result_task_id":obj.get("source_result_task_id"),"result_encoding":encoding or "EXPANDED_V1"}
    except Exception as e:
        return {},{"status":"INVALID","path":str(path),"reason":f"{type(e).__name__}:{str(e)[:160]}"}

def valid_bridge_price_resolution(x,asof):
    if not isinstance(x,dict): return False
    d=x.get("decision")
    px=num(x.get("price"))
    if d=="FAIL_PRICE":
        if x.get("compact_terminal_proof") is True:
            return bool(x.get("source")) and bool(x.get("proof"))
        return px is not None and px<=HARD_PRICE and bool(x.get("source")) and bool(x.get("proof"))
    if d=="FAIL_DV20":
        if x.get("compact_terminal_proof") is True:
            return bool(x.get("source")) and bool(x.get("proof"))
        dv=num(x.get("dv20"))
        if dv is not None:
            return px is not None and px>HARD_PRICE and dv<HARD_DV20 and bool(x.get("source")) and bool(x.get("proof"))
        n=x.get("observed_completed_sessions")
        return (
          px is not None and px>HARD_PRICE and isinstance(n,int) and 0<=n<20
          and x.get("reason")=="EXACT20_INSUFFICIENT_LISTED_SESSIONS"
          and x.get("no_synthetic_bar") is True and bool(x.get("source")) and bool(x.get("proof"))
        )
    if d=="PASS_PRICE_DV20":
        known=x.get("known_session_count")
        if x.get("compact_terminal_proof") is True:
            return (
              known==20 and (x.get("missing_sessions") or [])==[]
              and x.get("no_synthetic_bar") is True
              and x.get("source")=="RALLIES_CANDLESTICK_SCANNER_EXACT20_PRIMARY"
              and x.get("proof")=="RALLIES_EXACT20_MEDIAN_GE_GATE"
            )
        dv=num(x.get("dv20"))
        return (
          px is not None and px>HARD_PRICE and dv is not None and dv>=HARD_DV20
          and known==20 and (x.get("missing_sessions") or [])==[]
          and x.get("no_synthetic_bar") is True
          and bool(x.get("source")) and bool(x.get("proof"))
        )
    if d=="BLOCK_CURRENT_RUN":
        if x.get("source")=="RALLIES_CANDLESTICK_SCANNER_EXACT20_PRIMARY":
            return x.get("reason") in {
              "INSUFFICIENT_20_USABLE_DV20_SESSIONS_CONFIRMED",
              "RALLIES_PRIMARY_EXACT20_INCOMPLETE_SPLIT_OR_SOURCE_ALIGNMENT_RISK",
              "RALLIES_PRIMARY_EXACT20_INCOMPLETE_ZERO_TRADE_PLACEHOLDER_AMBIGUITY",
              "NO_USABLE_ASOF_MARKET_DATA_CURRENT_RUN",
            } and bool(x.get("proof"))
        return x.get("trade_status")=="Halted" and bool(x.get("last_bar")) and bool(x.get("source"))
    if d=="BLOCK_POST_ASOF_LISTING":
        return bool(x.get("first_trade_date")) and str(x.get("first_trade_date"))>asof and bool(x.get("source"))
    return False

def main():
    s=json.loads(INPUT.read_text())
    asof=s.get("asof_et")
    assert s["task_id"]==TASK_ID and isinstance(asof,str) and len(asof)==10
    queue=s["queue"];old=s["results"];assert len(queue)==len(old) and len(queue)>3000
    results={};redo=[]
    for sym in queue:
        r=old[sym];st=r.get("status");info=r.get("info")
        if st=="PASS":
            if not (
              isinstance(info,dict)
              and info.get("known_session_count")==20
              and (info.get("missing_sessions") or [])==[]
              and info.get("no_synthetic_bar") is True
              and num(info.get("dv20")) is not None
              and num(info.get("dv20"))>=HARD_DV20
            ):
                redo.append(sym)
                continue
            results[sym]={"status":"PASS_PRICE_DV20","info":info,"provenance":"FULLSTATE_EXACT20_PASS"}
        elif st=="FAIL_PRICE":
            results[sym]={"status":"FAIL_PRICE","info":info,"provenance":"FULLSTATE_TERMINAL_FAIL"}
        elif st=="FAIL_DV20":
            results[sym]={"status":"FAIL_DV20","info":info,"provenance":"FULLSTATE_TERMINAL_FAIL"}
        else:
            redo.append(sym)
    exp20=expected20(asof)
    if DEFER_TO_BRIDGE:
        for sym in redo:
            results[sym]={
              "status":"UNKNOWN",
              "info":{"reason":"AUTHENTICATED_SIP_RESOLVER_BRIDGE_REQUIRED"},
              "provenance":"DYNAMIC_BRIDGE_DEFERRED",
            }
    else:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs={ex.submit(eval_one,sym,exp20,asof):sym for sym in redo}
            for fut in as_completed(futs):
                sym,st,info,meta=fut.result()
                results[sym]={"status":st,"info":info,"provider_meta":meta,"provenance":"POLICY_ORDER_REEVALUATION"}
    bridge_price,exception_bridge_meta=load_exception_bridge(asof,s["queue_hash"])
    for sym,br in sorted(bridge_price.items()):
        if sym not in results or results[sym].get("status")!="UNKNOWN":
            continue
        if not valid_bridge_price_resolution(br,asof):
            continue
        st=br["decision"]
        results[sym]={
          "status":st,
          "info":{k:v for k,v in br.items() if k!="decision"},
          "provenance":"AUTHENTICATED_TASKSTATE_RESOLVER_BRIDGE",
        }

    counts={}
    for r in results.values():counts[r["status"]]=counts.get(r["status"],0)+1
    unknown=sorted(s for s,r in results.items() if r["status"]=="UNKNOWN")
    passes=sorted(s for s,r in results.items() if r["status"]=="PASS_PRICE_DV20")
    obj={
      "schema":"XRAY_CANONICAL_PRICE_DV20_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "source_master_queue_hash":s["queue_hash"],"source_master_count":len(queue),
      "expected20":exp20,"gate_order":["PRICE","DV20"],"thresholds":{"price":">10","dv20":">=50000000 exact20 median"},
      "reused_terminal_count":len(queue)-len(redo),"reevaluated_count":len(redo),
      "exception_bridge_meta":exception_bridge_meta,
      "counts":dict(sorted(counts.items())),"unknown_count":len(unknown),"unknown_symbols":unknown,
      "pass_count":len(passes),"pass_symbols":passes,
      "pass_hash":hashlib.sha256("\n".join(passes).encode()).hexdigest(),
      "results":dict(sorted(results.items()))
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"reused":obj["reused_terminal_count"],"reevaluated":obj["reevaluated_count"],"counts":obj["counts"],"unknown_count":obj["unknown_count"],"pass_count":obj["pass_count"],"pass_hash":obj["pass_hash"]},sort_keys=True))
if __name__=="__main__":main()
