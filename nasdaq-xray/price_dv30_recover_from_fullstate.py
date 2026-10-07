#!/usr/bin/env python3
from __future__ import annotations
import json, os, hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from price_dv30_phase import eval_one, expected30, sina, nasdaq, classify

ROOT=Path(__file__).resolve().parent
INPUT=Path(os.getenv("XRAY_FULLSTATE_INPUT",str(ROOT/"canonical_full_hard_gate_20260930_state.json")))
OUT=Path(os.getenv("XRAY_PRICE_DV30_RECOVER_OUT",str(ROOT/"canonical_price_dv30_20260930.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_PHASE_WORKERS","12"))
DEFER_TO_BRIDGE=os.getenv("XRAY_DYNAMIC_AUTHENTICATED_PRICE_BRIDGE","0")=="1"
FORCE_POLICY_REPLAY=os.getenv("XRAY_PRICE_FORCE_POLICY_REPLAY","0")=="1"
USE_CURRENT_BASELINE=os.getenv("XRAY_PRICE_USE_CURRENT_BASELINE","0")=="1"
FORCE_LOCAL_REEVALUATION=os.getenv("XRAY_PRICE_FORCE_LOCAL_REEVALUATION","0")=="1"
HARD_PRICE=5.0
HARD_DV30=50_000_000.0
RESOLVER_REQUEST=Path(os.getenv("XRAY_CURRENT_RESOLVER_REQUEST",str(ROOT/"canonical_current_resolver_request.json")))
RESOLVER_CHUNK_MANIFEST=Path(os.getenv("XRAY_CURRENT_RESOLVER_CHUNK_MANIFEST",str(ROOT/"canonical_current_resolver_chunk_manifest.json")))


def git_blob_sha(path:Path)->str:
    b=path.read_bytes()
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()


def resolver_bridge_input_binding(obj,asof,queue_hash):
    """Bind a resolver bridge to the exact pre-run PRICE state and resolver scope.

    Exact blob binding remains preferred. A narrowly-scoped semantic rebind is
    allowed only when the bridge carries an explicit source_price_semantic_binding
    proving that the decision-bearing PRICE partition is identical despite a
    non-semantic canonical artifact rewrite. This never permits UNKNOWN->PASS.
    """
    try:
        if not OUT.exists() or not RESOLVER_REQUEST.exists() or not RESOLVER_CHUNK_MANIFEST.exists():
            return False,None,"CURRENT_INPUT_ARTIFACT_MISSING"
        prior_price_blob=git_blob_sha(OUT)
        prior_price=json.loads(OUT.read_text())
        price_blob_exact=(obj.get("source_price_blob_sha")==prior_price_blob)
        semantic_price_rebind=False
        if not price_blob_exact:
            sb=obj.get("source_price_semantic_binding") or {}
            current_pass=list(prior_price.get("pass_symbols") or [])
            current_unknown=list(prior_price.get("unknown_symbols") or [])
            current_blocked=list(prior_price.get("blocked_symbols") or [])
            semantic_price_rebind=bool(
              sb.get("schema")=="XRAY_PRICE_PARTITION_SEMANTIC_BINDING_V1"
              and sb.get("source_price_blob_sha")==obj.get("source_price_blob_sha")
              and sb.get("asof_et")==prior_price.get("asof_et")==asof
              and sb.get("queue_hash")==prior_price.get("source_master_queue_hash")==queue_hash
              and int(sb.get("queue_total",-1))==int(prior_price.get("source_master_count",-2))
              and list(sb.get("expected30") or [])==list(prior_price.get("expected30") or [])
              and list(sb.get("gate_order") or [])==list(prior_price.get("gate_order") or [])
              and (sb.get("thresholds") or {})==(prior_price.get("thresholds") or {})
              and int(sb.get("pass_count",-1))==int(prior_price.get("pass_count",-2))
              and sb.get("pass_hash")==prior_price.get("pass_hash")
              and list(sb.get("pass_symbols") or [])==current_pass
              and list(sb.get("unknown_symbols") or [])==current_unknown
              and list(sb.get("blocked_symbols") or [])==current_blocked
              and sb.get("unknown_never_pass") is True
              and sb.get("no_new_pass") is True
            )
            if not semantic_price_rebind:
                return False,None,"SOURCE_PRICE_BLOB_MISMATCH"
        q=json.loads(RESOLVER_REQUEST.read_text())
        cm=json.loads(RESOLVER_CHUNK_MANIFEST.read_text())
        if not (
          q.get("schema")=="XRAY_RESOLVER_EPOCH_REQUEST_V1"
          and q.get("status")=="READY"
          and q.get("task_id")==TASK_ID
          and q.get("execution")=="NONE" and q.get("real_money")=="NO-GO"
          and q.get("unknown_never_pass") is True
          and q.get("asof_et")==asof and q.get("queue_hash")==queue_hash
          and q.get("compiled_policy_blob_sha")=="16c50cc8f887a5234a4be23862d7c8d0e564b0ac"
          and q.get("compiled_policy_hash")=="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
          and q.get("compiled_policy_version")=="C4.17"
          and q.get("source_price_blob_sha")==prior_price_blob
        ):
            return False,None,"CURRENT_REQUEST_BINDING_MISMATCH"
        q_symbols=list(q.get("symbols") or [])
        b_symbols=list(obj.get("symbols") or [])
        q_unknown=list(q.get("price_unknown_symbols") or [])
        # Empty UNKNOWN is meaningful for a blocked-only resolver epoch. Do not
        # collapse [] into the whole symbol scope via Python's `or` fallback.
        b_unknown=(
          list(obj.get("price_unknown_symbols") or [])
          if "price_unknown_symbols" in obj
          else list(obj.get("symbols") or [])
        )
        q_blocked=list(q.get("price_blocked_symbols") or [])
        b_blocked=(
          list(obj.get("price_blocked_symbols") or [])
          if "price_blocked_symbols" in obj
          else []
        )
        if (
          q.get("symbol_hash")!=obj.get("symbol_hash")
          or int(q.get("symbol_count",-1))!=int(obj.get("symbol_count",-2))
          or q_symbols!=b_symbols
          or q_unknown!=b_unknown
          or q_blocked!=b_blocked
        ):
            return False,None,"CURRENT_REQUEST_SCOPE_MISMATCH"
        rq_blob=git_blob_sha(RESOLVER_REQUEST)
        cm_blob=git_blob_sha(RESOLVER_CHUNK_MANIFEST)
        if not (
          cm.get("schema")=="XRAY_RESOLVER_REQUEST_CHUNK_MANIFEST_V1"
          and cm.get("task_id")==TASK_ID
          and cm.get("execution")=="NONE" and cm.get("real_money")=="NO-GO"
          and cm.get("unknown_never_pass") is True
          and cm.get("asof_et")==asof
          and cm.get("request_blob_sha")==rq_blob
          and cm.get("queue_hash")==q.get("queue_hash")
          and cm.get("symbol_hash")==q.get("symbol_hash")
          and int(cm.get("symbol_count",-1))==int(q.get("symbol_count",-2))
          and cm.get("coverage_complete") is True
        ):
            return False,None,"CURRENT_MANIFEST_BINDING_MISMATCH"
        if semantic_price_rebind:
            role="SEMANTIC_REBIND_EXACT_PRICE_PARTITION_AND_SCOPE"
        else:
            role=(
              "EXACT_CURRENT_REQUEST_MANIFEST"
              if obj.get("source_request_blob_sha")==rq_blob and obj.get("source_manifest_blob_sha")==cm_blob
              else "SEMANTIC_REBIND_EXACT_SOURCE_PRICE_AND_SCOPE"
            )
        return True,role,None
    except Exception as exc:
        return False,None,"INPUT_BINDING_ERROR:"+type(exc).__name__


def monotonic_legacy_pass_reusable(prior_thresholds)->bool:
    """A PASS under the old stricter >10 price floor stays PASS under >=5
    when the DV30 rule and gate order are unchanged. This is monotonic reuse,
    not a new PASS and not a threshold relaxation beyond the current policy.
    """
    if not isinstance(prior_thresholds,dict): return False
    return (
      prior_thresholds.get("price")==">10"
      and prior_thresholds.get("dv30")==">=50000000 exact30 median"
      and HARD_PRICE==5.0 and HARD_DV30==50_000_000.0
    )


def num(x):
    try:
        v=float(x)
        return v if v==v and abs(v)!=float("inf") else None
    except Exception:
        return None

def price_snapshot_integrity(px,frozen_asof):
    """Structural integrity is not the same as resolver completeness.

    UNKNOWN/BLOCK_CURRENT_RUN are legitimate fail-closed intermediate states.
    Treat the snapshot as corrupt only when its safety/binding/count structure
    is internally inconsistent.
    """
    try:
        counts=px.get("counts") or {}
        results=px.get("results") or {}
        unknown=list(px.get("unknown_symbols") or [])
        blocked=list(px.get("blocked_symbols") or [])
        passes=list(px.get("pass_symbols") or [])
        source_count=int(px.get("source_master_count",-1))
        return bool(
          frozen_asof and px.get("asof_et")==frozen_asof
          and px.get("execution")=="NONE" and px.get("real_money")=="NO-GO"
          and px.get("unknown_never_pass") is True
          and source_count>0 and len(results)==source_count
          and sum(int(v) for v in counts.values())==source_count
          and int(px.get("unknown_count",-1))==len(unknown)==len(set(unknown))
          and int(px.get("blocked_count",counts.get("BLOCK_CURRENT_RUN",0)))==len(blocked)==len(set(blocked))
          and int(px.get("pass_count",-1))==len(passes)==len(set(passes))
          and set(unknown).issubset(results)
          and set(blocked).issubset(results)
          and set(passes).issubset(results)
        )
    except Exception:
        return False


def _compact_resolution_sets(compact):
    compact=compact or {}
    all_resolved=set()
    terminal=set()
    block_only=set()
    for key in ("fail_price_symbols","fail_dv30_symbols","pass_price_dv30_symbols"):
        vals=compact.get(key) or []
        if isinstance(vals,list):
            all_resolved.update(vals); terminal.update(vals)
    bc=compact.get("block_current_run") or {}
    if isinstance(bc,dict):
        all_resolved.update(bc); block_only.update(bc)
    # Compact V3 shapes are dictionaries.
    for key in ("fail_price","fail_dv30","pass_price_dv30","fail_no_asof_bar",
                "fail_dv30_insufficient_sessions","block_post_asof_listing"):
        vals=compact.get(key) or {}
        if isinstance(vals,dict):
            all_resolved.update(vals); terminal.update(vals)
    bc3=compact.get("block_current_run") or {}
    if isinstance(bc3,dict):
        all_resolved.update(bc3); block_only.update(bc3)
    return all_resolved,terminal,block_only


def bridge_refresh_relevant(px,bridge,asof,source_price_blob_sha=None):
    """Cheap scheduling predicate. Exact proof validation remains in load_exception_bridge."""
    try:
        if not (
          bridge.get("schema")=="XRAY_RESOLVER_EPOCH_RESULT_V1"
          and bridge.get("status")=="COMMITTED"
          and bridge.get("task_id")==TASK_ID
          and bridge.get("execution")=="NONE" and bridge.get("real_money")=="NO-GO"
          and bridge.get("unknown_never_pass") is True
          and bridge.get("asof_et")==asof
          and bridge.get("queue_hash")==px.get("source_master_queue_hash")
          and bridge.get("compiled_policy_version")=="C4.17"
          and bridge.get("compiled_policy_hash")=="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
        ):
            return False
        if source_price_blob_sha is not None and bridge.get("source_price_blob_sha")!=source_price_blob_sha:
            return False
        unknown=set(px.get("unknown_symbols") or [])
        blocked=set(px.get("blocked_symbols") or [])
        expanded=bridge.get("price_resolutions") or {}
        expanded_all=set(expanded) if isinstance(expanded,dict) else set()
        expanded_terminal={
          s for s,x in (expanded.items() if isinstance(expanded,dict) else [])
          if isinstance(x,dict) and x.get("decision")!="BLOCK_CURRENT_RUN"
        }
        compact_all,compact_terminal,_=_compact_resolution_sets(bridge.get("price_resolution_compact"))
        overrides=set((bridge.get("terminal_overrides") or {}).keys())
        # UNKNOWN may legitimately become another fail-closed BLOCK; an existing
        # BLOCK must only wake the workflow for a terminal resolution.
        return bool(
          unknown & (expanded_all|compact_all|overrides)
          or blocked & (expanded_terminal|compact_terminal|overrides)
        )
    except Exception:
        return False


def bridge_replacement_allowed(prior_status,decision):
    if prior_status=="UNKNOWN":
        return decision in {
          "FAIL_PRICE","FAIL_DV30","FAIL_PRICE_NO_ASOF_BAR",
          "FAIL_DV30_INSUFFICIENT_SESSIONS","PASS_PRICE_DV30",
          "BLOCK_CURRENT_RUN","BLOCK_POST_ASOF_LISTING",
        }
    if prior_status=="BLOCK_CURRENT_RUN":
        return decision in {
          "FAIL_PRICE","FAIL_DV30","FAIL_PRICE_NO_ASOF_BAR",
          "FAIL_DV30_INSUFFICIENT_SESSIONS","PASS_PRICE_DV30",
          "BLOCK_POST_ASOF_LISTING",
        }
    return False


def apply_terminal_overrides(prs,overrides):
    """Strict operator evidence may only turn an existing fail-closed block into
    a C4.17 terminal FAIL. It can never manufacture PASS or change non-blocked rows.
    """
    if overrides is None:return prs
    if not isinstance(overrides,dict):raise ValueError("TERMINAL_OVERRIDE_TYPES")
    source="ALPACA_SIP_RALLIES_MASSIVE_C4_17_NON_G9"
    for sym,x in overrides.items():
        prior=prs.get(sym) or {}
        if prior.get("decision")!="BLOCK_CURRENT_RUN":raise ValueError("TERMINAL_OVERRIDE_NOT_BLOCKED")
        if not isinstance(x,dict) or x.get("decision") not in {"FAIL_PRICE_NO_ASOF_BAR","FAIL_DV30_INSUFFICIENT_SESSIONS"}:
            raise ValueError("TERMINAL_OVERRIDE_DECISION")
        rec=dict(x);rec["source"]=source
        if not valid_bridge_price_resolution(rec,None):raise ValueError("TERMINAL_OVERRIDE_PROOF")
        prs[sym]=rec
    return prs

# Immutable bridge successor version numbers do not imply new wire encodings.
# Keep block-only/current-scope successors on RALLIES_SCANNER_EXACT30_V2 unless
# this loader and its regression tests explicitly add another encoding contract.
def expand_rallies_scanner_exact30_v2(compact,req):
    if not isinstance(compact,dict):
        raise ValueError("RALLIES_V2_TYPES")
    fp=compact.get("fail_price") or {}
    fd=compact.get("fail_dv30") or {}
    pm=compact.get("pass_price_dv30") or {}
    bc=compact.get("block_current_run") or {}
    un=compact.get("unresolved_symbols") or []
    if not all(isinstance(x,dict) for x in [fp,fd,pm,bc]) or not isinstance(un,list):
        raise ValueError("RALLIES_V2_TYPES")
    groups=[set(fp),set(fd),set(pm),set(bc),set(un)]
    vals=[fp,fd,pm,bc,un]
    if any(len(g)!=len(v) for g,v in zip(groups,vals)):
        raise ValueError("RALLIES_V2_DUPLICATES")
    for i in range(len(groups)):
        for j in range(i+1,len(groups)):
            if groups[i]&groups[j]:
                raise ValueError("RALLIES_V2_OVERLAP")
    if set().union(*groups)!=set(req):
        raise ValueError("RALLIES_V2_COVERAGE")
    src="RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9"
    out={}
    for sym,val in fp.items():
        px=num(val)
        if px is None or px>=HARD_PRICE:
            raise ValueError("RALLIES_V2_FAIL_PRICE_GATE")
        out[sym]={"decision":"FAIL_PRICE","price":px,"source":src,"proof":"ASOF_CLOSE_LT_5","compact_terminal_proof":True}
    for sym,val in fd.items():
        if not isinstance(val,dict):
            raise ValueError("RALLIES_V2_FAIL_DV30_VALUE")
        px=num(val.get("price")); metric=num(val.get("metric")); proof=str(val.get("proof") or "")
        n=val.get("known_session_count"); missing=val.get("missing_session_count")
        if px is None or px<HARD_PRICE or metric is None or metric>=HARD_DV30 or not isinstance(n,int):
            raise ValueError("RALLIES_V2_FAIL_DV30_GATE")
        rec={"decision":"FAIL_DV30","price":px,"source":src,"proof":proof,"known_session_count":n,
             "no_synthetic_bar":True,"compact_terminal_proof":True}
        if proof=="EXACT30_MEDIAN_LT_GATE":
            if n!=30 or missing not in {0,None}:
                raise ValueError("RALLIES_V2_EXACT30_PROOF")
            rec["dv30"]=metric; rec["missing_sessions"]=[]
        elif proof=="DV30_UPPER_BOUND_LT_GATE":
            if not (16<=n<30) or missing!=30-n:
                raise ValueError("RALLIES_V2_UPPER_BOUND_PROOF")
            rec["dv30_upper_bound"]=metric
            rec["missing_session_count"]=missing
        else:
            raise ValueError("RALLIES_V2_FAIL_DV30_PROOF")
        out[sym]=rec
    for sym,val in pm.items():
        if not isinstance(val,dict):
            raise ValueError("RALLIES_V2_PASS_VALUE")
        px=num(val.get("price")); dv=num(val.get("dv30")); n=val.get("known_session_count")
        if px is None or px<HARD_PRICE or dv is None or dv<HARD_DV30 or n!=30:
            raise ValueError("RALLIES_V2_PASS_GATE")
        out[sym]={"decision":"PASS_PRICE_DV30","price":px,"dv30":dv,"known_session_count":30,
                  "missing_sessions":[],"no_synthetic_bar":True,"source":src,
                  "proof":"EXACT30_MEDIAN_GE_GATE","compact_terminal_proof":True}
    allowed={
      "INSUFFICIENT_30_USABLE_DV30_SESSIONS_CONFIRMED",
      "RALLIES_PRIMARY_EXACT30_INCOMPLETE_SPLIT_OR_SOURCE_ALIGNMENT_RISK",
      "RALLIES_PRIMARY_EXACT30_INCOMPLETE_ZERO_TRADE_PLACEHOLDER_AMBIGUITY",
      "NO_USABLE_ASOF_MARKET_DATA_CURRENT_RUN",
      "CROSS_SOURCE_CURRENT_ASOF_ALIGNMENT_UNPROVEN",
      "UNKNOWN_INTEGRITY_CONFLICT",
    }
    for sym,val in bc.items():
        if not isinstance(val,dict) or val.get("reason") not in allowed:
            raise ValueError("RALLIES_V2_BLOCK_CURRENT")
        n=val.get("observed_usable_sessions")
        if n is not None and (not isinstance(n,int) or n<0 or n>=30):
            raise ValueError("RALLIES_V2_BLOCK_COUNT")
        out[sym]={"decision":"BLOCK_CURRENT_RUN","reason":val["reason"],"observed_usable_sessions":n,
                  "source":src,"proof":"FAIL_CLOSED_CURRENT_RUN_NONPASS",
                  "corroboration":val.get("corroboration"),"no_synthetic_bar":True}
    return out

def _resolver_bridge_rel(path):
    try:
        return str(path.relative_to(ROOT.parent)).replace("\\","/")
    except ValueError:
        return str(path).replace("\\","/")

def active_resolver_bridge_matches(rows):
    """Reduce exact/semantic matches to valid non-superseded resolver authority."""
    valid=[]
    superseded=set()
    repo_root=ROOT.parent.resolve()
    for row in rows:
        path,obj=row[0],row[1]
        sp=obj.get("supersedes_resolver_bridge_path")
        ss=obj.get("supersedes_resolver_bridge_blob_sha")
        if bool(sp)!=bool(ss):
            continue
        if sp:
            pred=(ROOT.parent/sp).resolve()
            if repo_root not in pred.parents or not pred.exists() or git_blob_sha(pred)!=ss:
                continue
            superseded.add(sp)
        valid.append(row)
    return [row for row in valid if _resolver_bridge_rel(row[0]) not in superseded]

def load_exception_bridge(asof,queue_hash):
    paths=sorted(ROOT.glob(f"canonical_resolver_bridge_{asof.replace('-','')}*.json"))
    matches=[]
    rejected=[]
    for path in paths:
        try:
            obj=json.loads(path.read_text())
            base_ok=(
              obj.get("schema")=="XRAY_RESOLVER_EPOCH_RESULT_V1"
              and obj.get("status")=="COMMITTED"
              and obj.get("task_id")==TASK_ID
              and obj.get("execution")=="NONE" and obj.get("real_money")=="NO-GO"
              and obj.get("asof_et")==asof and obj.get("queue_hash")==queue_hash
              and obj.get("compiled_policy_hash")=="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
              and obj.get("compiled_policy_version")=="C4.17"
              and obj.get("compiled_policy_blob_sha")=="16c50cc8f887a5234a4be23862d7c8d0e564b0ac"
              and (obj.get("settlement_required") is not True or obj.get("settlement_status")=="PASS")
            )
            binding_ok,binding_role,binding_reason=resolver_bridge_input_binding(obj,asof,queue_hash) if base_ok else (False,None,"BASE_BINDING")
            if base_ok and binding_ok:
                matches.append((path,obj,binding_role))
            else:
                rejected.append(str(path)+":"+str(binding_reason))
        except Exception:
            rejected.append(str(path))
    if len(matches)==0:
        return {},{"status":"ABSENT_CURRENT_POLICY","paths":[str(p) for p in paths],"rejected":rejected}
    matches=active_resolver_bridge_matches(matches)
    if len(matches)==0:
        return {},{"status":"NO_ACTIVE_CURRENT_POLICY","paths":[str(p) for p in paths],"rejected":rejected}
    if len(matches)!=1:
        return {},{"status":"AMBIGUOUS_CURRENT_POLICY","matches":[str(x[0]) for x in matches]}
    path,obj,binding_role=matches[0]
    try:
        if obj.get("schema")!="XRAY_RESOLVER_EPOCH_RESULT_V1" or obj.get("status")!="COMMITTED":
            raise ValueError("SCHEMA_OR_STATUS")
        if obj.get("task_id")!=TASK_ID or obj.get("execution")!="NONE" or obj.get("real_money")!="NO-GO":
            raise ValueError("SAFETY_OR_TASK")
        if obj.get("asof_et")!=asof or obj.get("queue_hash")!=queue_hash:
            raise ValueError("BINDING")
        if (
          obj.get("compiled_policy_hash")!="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
          or obj.get("compiled_policy_version")!="C4.17"
          or obj.get("compiled_policy_blob_sha")!="16c50cc8f887a5234a4be23862d7c8d0e564b0ac"
        ):
            raise ValueError("POLICY_BINDING")
        if obj.get("settlement_required") is True and obj.get("settlement_status")!="PASS":
            raise ValueError("SETTLEMENT_BINDING")
        prs=obj.get("price_resolutions") or {}
        if not isinstance(prs,dict): raise ValueError("PRICE_RESOLUTIONS")
        compact=obj.get("price_resolution_compact")
        encoding=obj.get("result_encoding")
        if compact is not None:
            if encoding not in {"ALPACA_SIP_COMPACT_V1","ALPACA_SIP_COMPACT_V2","ALPACA_SIP_RALLIES_COMPACT_V3","RALLIES_SCANNER_EXACT30_V1","RALLIES_SCANNER_EXACT30_V2"} or not isinstance(compact,dict):
                raise ValueError("COMPACT_ENCODING")
            src="RALLIES_CANDLESTICK_SCANNER_EXACT30_PRIMARY" if encoding in {"RALLIES_SCANNER_EXACT30_V1","RALLIES_SCANNER_EXACT30_V2"} else "ALPACA_HISTORICAL_SIP_DAILY_BATCH_NON_G9"
            if encoding=="RALLIES_SCANNER_EXACT30_V2":
                req=set(obj.get("price_unknown_symbols") or obj.get("symbols") or [])
                prs.update(expand_rallies_scanner_exact30_v2(compact,req))
            elif encoding=="RALLIES_SCANNER_EXACT30_V1":
                fp=compact.get("fail_price_symbols") or []
                fd=compact.get("fail_dv30_symbols") or []
                ps=compact.get("pass_price_dv30_symbols") or []
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
                    prs[sym]={"decision":"FAIL_PRICE","source":src,"proof":"RALLIES_ASOF_CLOSE_LT_5","compact_terminal_proof":True}
                for sym in fd:
                    prs[sym]={"decision":"FAIL_DV30","source":src,"proof":"RALLIES_EXACT30_MEDIAN_LT_GATE","compact_terminal_proof":True}
                for sym in ps:
                    prs[sym]={
                      "decision":"PASS_PRICE_DV30","known_session_count":30,"missing_sessions":[],
                      "no_synthetic_bar":True,"source":src,"proof":"RALLIES_EXACT30_MEDIAN_GE_GATE",
                      "compact_terminal_proof":True,
                    }
                allowed_block_reasons={
                  "INSUFFICIENT_30_USABLE_DV30_SESSIONS_CONFIRMED",
                  "RALLIES_PRIMARY_EXACT30_INCOMPLETE_SPLIT_OR_SOURCE_ALIGNMENT_RISK",
                  "RALLIES_PRIMARY_EXACT30_INCOMPLETE_ZERO_TRADE_PLACEHOLDER_AMBIGUITY",
                  "NO_USABLE_ASOF_MARKET_DATA_CURRENT_RUN",
                }
                for sym,val in bc.items():
                    if not isinstance(val,dict) or val.get("reason") not in allowed_block_reasons:
                        raise ValueError("RALLIES_COMPACT_BLOCK_CURRENT")
                    n=val.get("observed_usable_sessions")
                    if n is not None and (not isinstance(n,int) or n<0 or n>=30):
                        raise ValueError("RALLIES_COMPACT_BLOCK_COUNT")
                    prs[sym]={
                      "decision":"BLOCK_CURRENT_RUN","reason":val["reason"],
                      "observed_usable_sessions":n,"source":src,
                      "proof":"FAIL_CLOSED_CURRENT_RUN_NONPASS",
                      "corroboration":val.get("corroboration"),
                    }
            elif encoding=="ALPACA_SIP_RALLIES_COMPACT_V3":
                fp=compact.get("fail_price") or {}
                fd=compact.get("fail_dv30") or {}
                pm=compact.get("pass_price_dv30") or {}
                fna=compact.get("fail_no_asof_bar") or {}
                fis=compact.get("fail_dv30_insufficient_sessions") or {}
                bc=compact.get("block_current_run") or {}
                bp=compact.get("block_post_asof_listing") or {}
                un=compact.get("unresolved_symbols") or []
                if not all(isinstance(x,dict) for x in [fp,fd,pm,fna,fis,bc,bp]) or not isinstance(un,list):
                    raise ValueError("COMPACT_V3_TYPES")
                groups=[set(fp),set(fd),set(pm),set(fna),set(fis),set(bc),set(bp),set(un)]
                vals=[fp,fd,pm,fna,fis,bc,bp,un]
                if any(len(g)!=len(v) for g,v in zip(groups,vals)):
                    raise ValueError("COMPACT_V3_DUPLICATES")
                for i in range(len(groups)):
                    for j in range(i+1,len(groups)):
                        if groups[i]&groups[j]: raise ValueError("COMPACT_V3_OVERLAP")
                req=set(obj.get("price_unknown_symbols") or obj.get("symbols") or [])
                if set().union(*groups)!=req: raise ValueError("COMPACT_V3_COVERAGE")
                src="ALPACA_SIP_RALLIES_MASSIVE_C4_13_NON_G9"
                for sym,val in fp.items():
                    px=num(val)
                    if px is None or px>=HARD_PRICE: raise ValueError("COMPACT_V3_FAIL_PRICE")
                    prs[sym]={"decision":"FAIL_PRICE","price":px,"source":src,"proof":"ASOF_CLOSE_LT_5"}
                for sym,val in fd.items():
                    if not isinstance(val,(list,tuple)) or len(val)<3: raise ValueError("COMPACT_V3_FAIL_DV30_VALUE")
                    px=num(val[0]); metric=num(val[1]); proof=str(val[2])
                    if px is None or px<HARD_PRICE or metric is None or metric>=HARD_DV30: raise ValueError("COMPACT_V3_FAIL_DV30_GATE")
                    if proof not in {"EXACT30_MEDIAN_LT_GATE","DV30_UPPER_BOUND_LT_GATE"}: raise ValueError("COMPACT_V3_FAIL_DV30_PROOF")
                    rec={"decision":"FAIL_DV30","price":px,"source":src,"proof":proof}
                    if proof=="EXACT30_MEDIAN_LT_GATE": rec["dv30"]=metric
                    else: rec["dv30_upper_bound"]=metric
                    prs[sym]=rec
                for sym,val in pm.items():
                    if not isinstance(val,(list,tuple)) or len(val)<2: raise ValueError("COMPACT_V3_PASS_VALUE")
                    px=num(val[0]); dv=num(val[1])
                    if px is None or px<HARD_PRICE or dv is None or dv<HARD_DV30: raise ValueError("COMPACT_V3_PASS_GATE")
                    prs[sym]={"decision":"PASS_PRICE_DV30","price":px,"dv30":dv,"known_session_count":30,"missing_sessions":[],"no_synthetic_bar":True,"source":src,"proof":"EXACT30_MEDIAN_GE_GATE"}
                for sym,val in fna.items():
                    if not isinstance(val,dict) or val.get("proof")!="THREE_SOURCE_NO_ASOF_BAR":
                        raise ValueError("COMPACT_V3_NO_ASOF_PROOF")
                    sources=val.get("sources") or []
                    if set(sources)!={"ALPACA_SIP","RALLIES","MASSIVE"}:
                        raise ValueError("COMPACT_V3_NO_ASOF_SOURCES")
                    prs[sym]={"decision":"FAIL_PRICE_NO_ASOF_BAR","source":src,"proof":"THREE_SOURCE_NO_ASOF_BAR","sources":sorted(sources),"no_synthetic_bar":True}
                for sym,val in fis.items():
                    if not isinstance(val,dict): raise ValueError("COMPACT_V3_INSUFFICIENT_VALUE")
                    px=num(val.get("price")); n=val.get("known_session_count"); miss=val.get("missing_sessions") or []
                    if px is None or px<HARD_PRICE or not isinstance(n,int) or not (0<=n<30) or len(miss)!=(30-n):
                        raise ValueError("COMPACT_V3_INSUFFICIENT_GATE")
                    if val.get("proof")!="ALPACA_RALLIES_EXACT_MISSING_SET_MATCH":
                        raise ValueError("COMPACT_V3_INSUFFICIENT_PROOF")
                    prs[sym]={"decision":"FAIL_DV30_INSUFFICIENT_SESSIONS","price":px,"known_session_count":n,"missing_sessions":miss,"no_synthetic_bar":True,"source":src,"proof":"ALPACA_RALLIES_EXACT_MISSING_SET_MATCH"}
                for sym,val in bc.items():
                    if not isinstance(val,dict) or val.get("trade_status")!="Halted" or not val.get("last_bar"): raise ValueError("COMPACT_V3_BLOCK_CURRENT")
                    prs[sym]={"decision":"BLOCK_CURRENT_RUN","trade_status":"Halted","last_bar":val["last_bar"],"source":src,"proof":"HALTED_NO_ASOF_BAR"}
                for sym,val in bp.items():
                    d=(val or {}).get("first_trade_date") if isinstance(val,dict) else val
                    if not d or str(d)<=asof: raise ValueError("COMPACT_V3_POST_ASOF")
                    prs[sym]={"decision":"BLOCK_POST_ASOF_LISTING","first_trade_date":str(d),"source":src,"proof":"FIRST_VALID_BAR_AFTER_ASOF"}
            elif encoding=="ALPACA_SIP_COMPACT_V2":
                fp=compact.get("fail_price") or {}
                fd=compact.get("fail_dv30") or {}
                pm=compact.get("pass_price_dv30") or {}
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
                    if px is None or px>=HARD_PRICE: raise ValueError("COMPACT_FAIL_PRICE_GATE")
                    prs[sym]={"decision":"FAIL_PRICE","price":px,"source":src,"proof":"ASOF_CLOSE_LT_5"}
                for sym,val in fd.items():
                    if not isinstance(val,(list,tuple)) or len(val)<3: raise ValueError("COMPACT_FAIL_DV30_VALUE")
                    px=num(val[0]); metric=num(val[1]); proof=str(val[2])
                    if px is None or px<HARD_PRICE or metric is None or metric>=HARD_DV30:
                        raise ValueError("COMPACT_FAIL_DV30_GATE")
                    if proof not in {"EXACT30_MEDIAN_LT_GATE","DV30_UPPER_BOUND_LT_GATE"}:
                        raise ValueError("COMPACT_FAIL_DV30_PROOF")
                    rec={"decision":"FAIL_DV30","price":px,"source":src,"proof":proof}
                    if proof=="EXACT30_MEDIAN_LT_GATE": rec["dv30"]=metric
                    else: rec["dv30_upper_bound"]=metric
                    prs[sym]=rec
                for sym,val in pm.items():
                    if not isinstance(val,(list,tuple)) or len(val)<2: raise ValueError("COMPACT_PASS_VALUE")
                    px=num(val[0]); dv=num(val[1])
                    if px is None or px<HARD_PRICE or dv is None or dv<HARD_DV30:
                        raise ValueError("COMPACT_PASS_GATE")
                    prs[sym]={
                      "decision":"PASS_PRICE_DV30","price":px,"dv30":dv,
                      "known_session_count":30,"missing_sessions":[],"no_synthetic_bar":True,
                      "source":src,"proof":"EXACT30_MEDIAN_GE_GATE",
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
                fd=compact.get("fail_dv30_symbols") or []
                pm=compact.get("pass_price_dv30") or {}
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
                for sym in fp: prs[sym]={"decision":"FAIL_PRICE","source":src,"proof":"ASOF_CLOSE_LT_5","compact_terminal_proof":True}
                for sym in fd: prs[sym]={"decision":"FAIL_DV30","source":src,"proof":"EXACT30_OR_UPPER_BOUND_LT_GATE","compact_terminal_proof":True}
                for sym,val in pm.items():
                    px=num(val[0] if isinstance(val,(list,tuple)) else val.get("price"))
                    dv=num(val[1] if isinstance(val,(list,tuple)) else val.get("dv30"))
                    if px is None or px<HARD_PRICE or dv is None or dv<HARD_DV30: raise ValueError("COMPACT_PASS_GATE")
                    prs[sym]={"decision":"PASS_PRICE_DV30","price":px,"dv30":dv,"known_session_count":30,"missing_sessions":[],"no_synthetic_bar":True,"source":src,"proof":"EXACT30_MEDIAN_GE_GATE"}
                for sym,val in bc.items():
                    if not isinstance(val,dict) or val.get("trade_status")!="Halted" or not val.get("last_bar"): raise ValueError("COMPACT_BLOCK_CURRENT")
                    prs[sym]={"decision":"BLOCK_CURRENT_RUN","trade_status":"Halted","last_bar":val["last_bar"],"source":src,"proof":"HALTED_NO_ASOF_BAR"}
                for sym,val in bp.items():
                    d=(val or {}).get("first_trade_date") if isinstance(val,dict) else val
                    if not d or str(d)<=asof: raise ValueError("COMPACT_POST_ASOF")
                    prs[sym]={"decision":"BLOCK_POST_ASOF_LISTING","first_trade_date":str(d),"source":src,"proof":"FIRST_VALID_BAR_AFTER_ASOF"}
        prs=apply_terminal_overrides(prs,obj.get("terminal_overrides"))
        return prs,{"status":"PASS","path":str(path),"symbol_hash":obj.get("symbol_hash"),"source_result_task_id":obj.get("source_result_task_id"),"result_encoding":encoding or "EXPANDED_V1","terminal_override_count":len(obj.get("terminal_overrides") or {}),"input_binding_role":binding_role}
    except Exception as e:
        return {},{"status":"INVALID","path":str(path),"reason":f"{type(e).__name__}:{str(e)[:160]}"}

def valid_bridge_price_resolution(x,asof):
    if not isinstance(x,dict): return False
    d=x.get("decision")
    px=num(x.get("price"))
    if d=="FAIL_PRICE":
        if x.get("compact_terminal_proof") is True:
            return bool(x.get("source")) and bool(x.get("proof"))
        return px is not None and px<HARD_PRICE and bool(x.get("source")) and bool(x.get("proof"))
    if d=="FAIL_DV30":
        if x.get("compact_terminal_proof") is True:
            return bool(x.get("source")) and bool(x.get("proof"))
        dv=num(x.get("dv30"))
        if dv is not None:
            return px is not None and px>=HARD_PRICE and dv<HARD_DV30 and bool(x.get("source")) and bool(x.get("proof"))
        n=x.get("observed_completed_sessions")
        return (
          px is not None and px>=HARD_PRICE and isinstance(n,int) and 0<=n<30
          and x.get("reason")=="EXACT30_INSUFFICIENT_LISTED_SESSIONS"
          and x.get("no_synthetic_bar") is True and bool(x.get("source")) and bool(x.get("proof"))
        )
    if d=="FAIL_PRICE_NO_ASOF_BAR":
        return (
          x.get("proof")=="THREE_SOURCE_NO_ASOF_BAR"
          and set(x.get("sources") or [])=={"ALPACA_SIP","RALLIES","MASSIVE"}
          and x.get("no_synthetic_bar") is True
          and bool(x.get("source"))
        )
    if d=="FAIL_DV30_INSUFFICIENT_SESSIONS":
        n=x.get("known_session_count"); miss=x.get("missing_sessions") or []
        return (
          px is not None and px>=HARD_PRICE
          and isinstance(n,int) and 0<=n<30
          and len(miss)==30-n
          and x.get("proof")=="ALPACA_RALLIES_EXACT_MISSING_SET_MATCH"
          and x.get("no_synthetic_bar") is True
          and bool(x.get("source"))
        )
    if d=="PASS_PRICE_DV30":
        known=x.get("known_session_count")
        if x.get("compact_terminal_proof") is True:
            source_proof=(x.get("source"),x.get("proof"))
            return (
              known==30 and (x.get("missing_sessions") or [])==[]
              and x.get("no_synthetic_bar") is True
              and source_proof in {
                ("RALLIES_CANDLESTICK_SCANNER_EXACT30_PRIMARY","RALLIES_EXACT30_MEDIAN_GE_GATE"),
                ("RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9","EXACT30_MEDIAN_GE_GATE"),
              }
            )
        dv=num(x.get("dv30"))
        return (
          px is not None and px>=HARD_PRICE and dv is not None and dv>=HARD_DV30
          and known==30 and (x.get("missing_sessions") or [])==[]
          and x.get("no_synthetic_bar") is True
          and bool(x.get("source")) and bool(x.get("proof"))
        )
    if d=="BLOCK_CURRENT_RUN":
        if x.get("source") in {
          "RALLIES_CANDLESTICK_SCANNER_EXACT30_PRIMARY",
          "RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9",
        }:
            return (
              x.get("reason") in {
                "INSUFFICIENT_30_USABLE_DV30_SESSIONS_CONFIRMED",
                "RALLIES_PRIMARY_EXACT30_INCOMPLETE_SPLIT_OR_SOURCE_ALIGNMENT_RISK",
                "RALLIES_PRIMARY_EXACT30_INCOMPLETE_ZERO_TRADE_PLACEHOLDER_AMBIGUITY",
                "NO_USABLE_ASOF_MARKET_DATA_CURRENT_RUN",
                "CROSS_SOURCE_CURRENT_ASOF_ALIGNMENT_UNPROVEN",
                "UNKNOWN_INTEGRITY_CONFLICT",
              }
              and x.get("proof")=="FAIL_CLOSED_CURRENT_RUN_NONPASS"
              and x.get("no_synthetic_bar") is True
            )
        return x.get("trade_status")=="Halted" and bool(x.get("last_bar")) and bool(x.get("source"))
    if d=="BLOCK_POST_ASOF_LISTING":
        return bool(x.get("first_trade_date")) and str(x.get("first_trade_date"))>asof and bool(x.get("source"))
    return False

def global_asof_sentinel_nonterminal(redo,asof,exp30):
    """Fail-closed performance guard for a fresh full-universe ASOF publication lag.

    It may only reduce provider work; it never creates PASS/FAIL. If AAPL/MSFT/NVDA
    are all nonterminal on BOTH Sina and Nasdaq official, the full redo set stays
    UNKNOWN until a later scheduled run or authenticated resolver evidence.
    """
    anchors=("AAPL","MSFT","NVDA")
    rset=set(redo)
    if not all(x in rset for x in anchors):
        return False,{"status":"NOT_APPLICABLE","reason":"SENTINELS_NOT_ALL_IN_REDO"}
    proof={}
    for sym in anchors:
        sby,sm=sina(sym,asof)
        sst,sinfo=classify(sby,asof,exp30,"SINA_US_DAILY") if sby else ("UNKNOWN",{"reason":"SINA_UNAVAILABLE"})
        nby,nm=nasdaq(sym,asof)
        nst,ninfo=classify(nby,asof,exp30,"NASDAQ_OFFICIAL_HISTORICAL_API") if nby else ("UNKNOWN",{"reason":"NASDAQ_UNAVAILABLE"})
        s_has_asof=bool(sby and asof in sby)
        n_has_asof=bool(nby and asof in nby)
        proof[sym]={
          "sina_status":sst,"sina_result":sinfo,"sina_meta":sm,"sina_has_exact_asof":s_has_asof,
          "nasdaq_status":nst,"nasdaq_result":ninfo,"nasdaq_meta":nm,"nasdaq_has_exact_asof":n_has_asof,
        }
        # The fast-fail guard is only for a global publication lag. Seeing an
        # exact-ASOF bar on either zero-dollar source proves publication has
        # begun even when exact30 remains incomplete/UNKNOWN. Fall back to the
        # normal per-symbol fail-closed path; never manufacture PASS/FAIL here.
        if s_has_asof or n_has_asof or sst!="UNKNOWN" or nst!="UNKNOWN":
            return False,{"status":"TERMINAL_SENTINEL_OBSERVED","symbol":sym,"proof":proof}
    return True,{
      "status":"GLOBAL_SENTINELS_NONTERMINAL",
      "reason":"AAPL_MSFT_NVDA_SINA_AND_NASDAQ_OFFICIAL_ALL_UNKNOWN",
      "no_pass_or_fail_created":True,
      "proof":proof,
    }


def should_defer_redo_to_bridge(baseline_source,defer_enabled=None,force_local=None):
    """Authenticated bridge is incremental; publication replay may force local zero-dollar refresh."""
    if defer_enabled is None:
        defer_enabled=DEFER_TO_BRIDGE
    if force_local is None:
        force_local=FORCE_LOCAL_REEVALUATION
    return bool(defer_enabled and baseline_source!="FULL_STATE" and not force_local)


def publication_lag_artifact(px,asof):
    """Recognize only the fail-closed all-UNKNOWN snapshot caused by ASOF publication lag."""
    try:
        results=px.get("results") or {}
        n=int(px.get("source_master_count",-1))
        return bool(
          px.get("schema")=="XRAY_CANONICAL_PRICE_DV30_V1"
          and px.get("asof_et")==asof
          and px.get("execution")=="NONE" and px.get("real_money")=="NO-GO"
          and px.get("unknown_never_pass") is True
          and (px.get("thresholds") or {}).get("price")==">=5"
          and (px.get("thresholds") or {}).get("dv30")==">=50000000 exact30 median"
          and px.get("gate_order")==["PRICE","DV30"]
          and n>0 and len(results)==n
          and int(px.get("pass_count",-1))==0
          and int(px.get("blocked_count",(px.get("counts") or {}).get("BLOCK_CURRENT_RUN",0)) or 0)==0
          and int(px.get("unknown_count",-1))==n
          and (px.get("counts") or {})=={"UNKNOWN":n}
          and px.get("global_asof_sentinel_fast_fail") is True
          and (px.get("global_asof_sentinel") or {}).get("status")=="GLOBAL_SENTINELS_NONTERMINAL"
          and all(
            (row or {}).get("status")=="UNKNOWN"
            and (row or {}).get("provenance")=="GLOBAL_ASOF_SENTINEL_FAIL_CLOSED"
            and ((row or {}).get("info") or {}).get("reason")=="GLOBAL_ASOF_SENTINEL_NONTERMINAL_FAIL_CLOSED"
            for row in results.values()
          )
        )
    except Exception:
        return False


def publication_recheck(asof,exp30):
    """Cheap AAPL/MSFT/NVDA publication probe; it never writes a symbol decision."""
    if not isinstance(exp30,list) or len(exp30)!=30:
        return False,{"status":"INVALID_EXPECTED30","no_pass_or_fail_created":True}
    still_lag,meta=global_asof_sentinel_nonterminal(["AAPL","MSFT","NVDA"],asof,exp30)
    return bool(not still_lag and (meta or {}).get("status")=="TERMINAL_SENTINEL_OBSERVED"),meta


def deferred_bootstrap_artifact(px,asof):
    """Detect the poisoned bootstrap artifact produced by deferring the entire fresh universe."""
    try:
        results=px.get("results") or {}
        n=int(px.get("source_master_count",-1))
        return bool(
          px.get("schema")=="XRAY_CANONICAL_PRICE_DV30_V1"
          and px.get("asof_et")==asof
          and px.get("execution")=="NONE" and px.get("real_money")=="NO-GO"
          and px.get("unknown_never_pass") is True
          and (px.get("thresholds") or {}).get("price")==">=5"
          and (px.get("thresholds") or {}).get("dv30")==">=50000000 exact30 median"
          and px.get("gate_order")==["PRICE","DV30"]
          and n>3000 and len(results)==n
          and int(px.get("pass_count",-1))==0
          and int(px.get("blocked_count",(px.get("counts") or {}).get("BLOCK_CURRENT_RUN",0)) or 0)==0
          and int(px.get("unknown_count",-1))==n
          and (px.get("counts") or {})=={"UNKNOWN":n}
          and all((r or {}).get("provenance")=="DYNAMIC_BRIDGE_DEFERRED" for r in results.values())
        )
    except Exception:
        return False


def current_price_baseline_valid(prior,s,asof,queue):
    """Validate exact same-policy PRICE state before incremental resolver refresh."""
    try:
        return bool(
          prior.get("schema")=="XRAY_CANONICAL_PRICE_DV30_V1"
          and prior.get("task_id")==TASK_ID
          and prior.get("asof_et")==asof
          and prior.get("execution")=="NONE" and prior.get("real_money")=="NO-GO"
          and prior.get("unknown_never_pass") is True
          and prior.get("source_master_queue_hash")==s.get("queue_hash")
          and int(prior.get("source_master_count",-1))==len(queue)
          and set((prior.get("results") or {}).keys())==set(queue)
          and (prior.get("thresholds") or {}).get("price")==">=5"
          and (prior.get("thresholds") or {}).get("dv30")==">=50000000 exact30 median"
          and prior.get("gate_order")==["PRICE","DV30"]
          and price_snapshot_integrity(prior,asof)
        )
    except Exception:
        return False


def main():
    s=json.loads(INPUT.read_text())
    asof=s.get("asof_et")
    assert s["task_id"]==TASK_ID and isinstance(asof,str) and len(asof)==10
    queue=s["queue"];old=s["results"];assert len(queue)==len(old) and len(queue)>3000
    baseline_source="FULL_STATE"
    prior_thresholds={}
    if FORCE_POLICY_REPLAY or USE_CURRENT_BASELINE:
        if not OUT.exists():
            raise RuntimeError("PRICE_PRIOR_ARTIFACT_MISSING")
        prior=json.loads(OUT.read_text())
        common_binding=(
            prior.get("schema")=="XRAY_CANONICAL_PRICE_DV30_V1"
            and prior.get("task_id")==TASK_ID
            and prior.get("asof_et")==asof
            and prior.get("execution")=="NONE" and prior.get("real_money")=="NO-GO"
            and prior.get("source_master_queue_hash")==s.get("queue_hash")
            and int(prior.get("source_master_count",-1))==len(queue)
            and set((prior.get("results") or {}).keys())==set(queue)
        )
        if not common_binding:
            raise RuntimeError("PRICE_PRIOR_ARTIFACT_BINDING_INVALID")
        if USE_CURRENT_BASELINE and not current_price_baseline_valid(prior,s,asof,queue):
            raise RuntimeError("PRICE_CURRENT_BASELINE_INVALID")
        prior_thresholds=prior.get("thresholds") or {}
        old=prior["results"]
        baseline_source="CURRENT_PRICE_ARTIFACT" if USE_CURRENT_BASELINE else "PRIOR_PRICE_ARTIFACT"
    results={};redo=[];policy_redo=set()
    for sym in queue:
        r=old[sym];st=r.get("status");info=r.get("info")
        if USE_CURRENT_BASELINE:
            if st=="UNKNOWN":
                redo.append(sym)
                continue
            if st not in {
              "PASS_PRICE_DV30","FAIL_PRICE","FAIL_DV30","FAIL_PRICE_NO_ASOF_BAR",
              "FAIL_DV30_INSUFFICIENT_SESSIONS","BLOCK_CURRENT_RUN","BLOCK_POST_ASOF_LISTING",
            }:
                raise RuntimeError("PRICE_CURRENT_BASELINE_STATUS_INVALID:"+str(sym)+":"+str(st))
            kept=dict(r)
            kept["provenance"]="CURRENT_PRICE_SAME_POLICY_REUSE"
            results[sym]=kept
            continue
        if st in {"PASS","PASS_PRICE_DV30"}:
            monotonic_reuse=bool(FORCE_POLICY_REPLAY and monotonic_legacy_pass_reusable(prior_thresholds))
            exact_numeric_pass=(
              isinstance(info,dict)
              and info.get("known_session_count")==30
              and (info.get("missing_sessions") or [])==[]
              and info.get("no_synthetic_bar") is True
              and num(info.get("dv30")) is not None
              and num(info.get("dv30"))>=HARD_DV30
            )
            if not (monotonic_reuse or exact_numeric_pass):
                redo.append(sym)
                continue
            results[sym]={"status":"PASS_PRICE_DV30","info":info,
                          "provenance":("PRIOR_STRICTER_PRICE_PASS_MONOTONIC_REUSE" if monotonic_reuse
                                        else ("PRIOR_PRICE_REUSED_PASS" if FORCE_POLICY_REPLAY else "FULLSTATE_EXACT30_PASS"))}
        elif st=="FAIL_PRICE":
            px=num((info or {}).get("price")) if isinstance(info,dict) else None
            if FORCE_POLICY_REPLAY and (px is None or px>=HARD_PRICE):
                redo.append(sym);policy_redo.add(sym);continue
            results[sym]={"status":"FAIL_PRICE","info":info,
                          "provenance":"PRIOR_PRICE_REUSED_BELOW_NEW_FLOOR" if FORCE_POLICY_REPLAY else "FULLSTATE_TERMINAL_FAIL"}
        elif st in {"FAIL_DV30","FAIL_PRICE_NO_ASOF_BAR","FAIL_DV30_INSUFFICIENT_SESSIONS","BLOCK_CURRENT_RUN","BLOCK_POST_ASOF_LISTING"}:
            results[sym]={"status":st,"info":info,
                          "provenance":"PRIOR_PRICE_REUSED_POLICY_COMPATIBLE" if FORCE_POLICY_REPLAY else "FULLSTATE_TERMINAL_FAIL"}
        else:
            redo.append(sym)
    exp30=expected30(asof)
    defer_redo=should_defer_redo_to_bridge(baseline_source)
    sentinel_fast_fail=False
    sentinel_meta={"status":"NOT_EVALUATED"}
    if defer_redo:
        for sym in redo:
            if sym in policy_redo: continue
            results[sym]={
              "status":"UNKNOWN",
              "info":{"reason":"AUTHENTICATED_SIP_RESOLVER_BRIDGE_REQUIRED"},
              "provenance":"DYNAMIC_BRIDGE_DEFERRED",
            }
        if policy_redo:
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futs={ex.submit(eval_one,sym,exp30,asof):sym for sym in sorted(policy_redo)}
                for fut in as_completed(futs):
                    sym,st,info,meta=fut.result()
                    results[sym]={"status":st,"info":info,"provider_meta":meta,
                                  "provenance":"PRICE_POLICY_REPLAY_ZERO_DOLLAR_CHAIN"}
    else:
        if baseline_source=="FULL_STATE" and len(redo)>3000:
            sentinel_fast_fail,sentinel_meta=global_asof_sentinel_nonterminal(redo,asof,exp30)
        if sentinel_fast_fail:
            for sym in redo:
                results[sym]={
                  "status":"UNKNOWN",
                  "info":{
                    "reason":"GLOBAL_ASOF_SENTINEL_NONTERMINAL_FAIL_CLOSED",
                    "sentinel_status":sentinel_meta.get("status"),
                    "no_synthetic_bar":True,
                  },
                  "provider_meta":{"global_asof_sentinel":sentinel_meta},
                  "provenance":"GLOBAL_ASOF_SENTINEL_FAIL_CLOSED",
                }
        else:
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futs={ex.submit(eval_one,sym,exp30,asof):sym for sym in redo}
                for fut in as_completed(futs):
                    sym,st,info,meta=fut.result()
                    results[sym]={
                      "status":st,"info":info,"provider_meta":meta,
                      "provenance":"FULLSTATE_ZERO_DOLLAR_EXACT30" if baseline_source=="FULL_STATE" else "POLICY_ORDER_REEVALUATION",
                    }
    bridge_price,exception_bridge_meta=load_exception_bridge(asof,s["queue_hash"])
    for sym,br in sorted(bridge_price.items()):
        if sym not in results:
            continue
        prior_status=results[sym].get("status")
        if not valid_bridge_price_resolution(br,asof):
            continue
        st=br["decision"]
        if not bridge_replacement_allowed(prior_status,st):
            continue
        results[sym]={
          "status":st,
          "info":{k:v for k,v in br.items() if k!="decision"},
          "provenance":"AUTHENTICATED_TASKSTATE_RESOLVER_BRIDGE",
        }

    # Resolver BLOCK_CURRENT_RUN is fail-closed, but it must not silently
    # disappear from completeness. Re-evaluate non-halt blocks through the
    # independent zero-dollar exact30 chain (Sina -> Nasdaq official -> Yahoo
    # fail-only). Only terminal PASS/FAIL may replace the authenticated block.
    blocked_before=sorted(
        sym for sym,x in results.items()
        if x.get("status")=="BLOCK_CURRENT_RUN"
        and (x.get("info") or {}).get("trade_status")!="Halted"
    )
    recovered_blocks=[]
    if blocked_before:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs={ex.submit(eval_one,sym,exp30,asof):sym for sym in blocked_before}
            for fut in as_completed(futs):
                sym,st,info,meta=fut.result()
                if st in {"PASS_PRICE_DV30","FAIL_PRICE","FAIL_DV30"}:
                    results[sym]={
                      "status":st,"info":info,"provider_meta":meta,
                      "provenance":"BLOCK_CURRENT_RUN_ZERO_DOLLAR_RECOVERY",
                    }
                    recovered_blocks.append(sym)
                else:
                    results[sym]["block_recovery_attempt"]={
                      "status":"UNRESOLVED","provider_result":info,"provider_meta":meta
                    }

    counts={}
    for r in results.values():counts[r["status"]]=counts.get(r["status"],0)+1
    unknown=sorted(s for s,r in results.items() if r["status"]=="UNKNOWN")
    blocked=sorted(s for s,r in results.items() if r["status"]=="BLOCK_CURRENT_RUN")
    passes=sorted(s for s,r in results.items() if r["status"]=="PASS_PRICE_DV30")
    obj={
      "schema":"XRAY_CANONICAL_PRICE_DV30_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "source_master_queue_hash":s["queue_hash"],"source_master_count":len(queue),
      "expected30":exp30,"gate_order":["PRICE","DV30"],"thresholds":{"price":">=5","dv30":">=50000000 exact30 median"},
      "reused_terminal_count":len(queue)-len(redo),"reevaluated_count":len(redo),
      "policy_replay":FORCE_POLICY_REPLAY,"current_baseline_reuse":USE_CURRENT_BASELINE,
      "policy_replay_baseline_source":baseline_source,
      "bridge_defer_enabled":DEFER_TO_BRIDGE,
      "force_local_reevaluation":FORCE_LOCAL_REEVALUATION,
      "redo_deferred_to_bridge":defer_redo,
      "policy_replay_input_count":len(policy_redo),
      "global_asof_sentinel_fast_fail":sentinel_fast_fail,
      "global_asof_sentinel":sentinel_meta,
      "monotonic_legacy_pass_reuse_count":sum(1 for x in results.values() if x.get("provenance")=="PRIOR_STRICTER_PRICE_PASS_MONOTONIC_REUSE"),
      "policy_replay_symbols":sorted(policy_redo),
      "exception_bridge_meta":exception_bridge_meta,
      "counts":dict(sorted(counts.items())),"unknown_count":len(unknown),"unknown_symbols":unknown,
      "blocked_count":len(blocked),"blocked_symbols":blocked,
      "block_recovery_attempted":True,
      "block_recovery_input_count":len(blocked_before),
      "block_recovery_resolved_count":len(recovered_blocks),
      "block_recovery_resolved_symbols":sorted(recovered_blocks),
      "pass_count":len(passes),"pass_symbols":passes,
      "pass_hash":hashlib.sha256("\n".join(passes).encode()).hexdigest(),
      "results":dict(sorted(results.items()))
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"reused":obj["reused_terminal_count"],"reevaluated":obj["reevaluated_count"],"policy_replay":FORCE_POLICY_REPLAY,"policy_replay_input_count":len(policy_redo),"counts":obj["counts"],"unknown_count":obj["unknown_count"],"blocked_count":obj["blocked_count"],"block_recovery_input":obj["block_recovery_input_count"],"block_recovery_resolved":obj["block_recovery_resolved_count"],"pass_count":obj["pass_count"],"pass_hash":obj["pass_hash"]},sort_keys=True))
if __name__=="__main__":main()
