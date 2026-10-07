#!/usr/bin/env python3
from __future__ import annotations
import json, os, hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
from price_dv30_phase import eval_one, expected30, sina, classify

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
OFFICIAL_GUARD=Path(os.getenv("XRAY_OFFICIAL_SOURCE_GUARD",str(ROOT/"canonical_official_source_guard.json")))
OFFICIAL_LISTING_REGISTRY=Path(os.getenv("XRAY_OFFICIAL_LISTING_REGISTRY",str(ROOT/"price_official_listing_registry.json")))


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


def c417_rallies_primary_path(asof):
    """Return the highest immutable same-ASOF Rallies classification successor."""
    stem=f"rallies_dv30_{str(asof).replace('-','')}_classification"
    base=ROOT/"evidence"/f"{stem}.json"
    candidates=[(1,base)] if base.is_file() else []
    for p in (ROOT/"evidence").glob(f"{stem}_v*.json"):
        try:
            version=int(p.stem.rsplit("_v",1)[1])
        except Exception:
            continue
        candidates.append((version,p))
    if not candidates:
        return base
    return max(candidates,key=lambda x:x[0])[1]


def load_c417_rallies_primary(asof,queue=None):
    """Load the highest immutable C4.17 Rallies exact30 authority for ASOF.

    Same-ASOF successors never overwrite predecessors. Any requested current
    queue must be fully covered before the authority can materialize PRICE/DV30.
    """
    path=c417_rallies_primary_path(asof)
    try:
        obj=json.loads(path.read_text())
        if not (
          obj.get("schema")=="XRAY_RALLIES_DV30_CLASSIFICATION_V1"
          and obj.get("asof_et")==asof
          and obj.get("execution")=="NONE" and obj.get("real_money")=="NO-GO"
          and obj.get("unknown_never_pass") is True
          and obj.get("authority")=="C4.17_RALLIES_EXACT30_PRIMARY"
          and list(obj.get("expected30") or [])==expected30(asof)
          and (obj.get("thresholds") or {}).get("price")==">=5"
          and (obj.get("thresholds") or {}).get("dv30")=="median exactly30 Close*Volume >=50000000"
          and (obj.get("audit") or {}).get("coverage_exact") is True
          and (obj.get("audit") or {}).get("no_synthetic_bar") is True
          and (obj.get("audit") or {}).get("no_forward_fill") is True
          and (obj.get("audit") or {}).get("unknown_never_pass") is True
          and (obj.get("audit") or {}).get("threshold_changed") is False
          and (obj.get("audit") or {}).get("alpha_policy_changed") is False
        ):
            raise ValueError("RALLIES_PRIMARY_SCHEMA_OR_POLICY")
        groups=[
          set((obj.get("fail_price") or {}).keys()),
          set((obj.get("fail_dv30") or {}).keys()),
          set((obj.get("pass_price_dv30") or {}).keys()),
          set((obj.get("block_current_run") or {}).keys()),
        ]
        if any(groups[i]&groups[j] for i in range(len(groups)) for j in range(i+1,len(groups))):
            raise ValueError("RALLIES_PRIMARY_PARTITION_OVERLAP")
        union=set().union(*groups)
        if len(union)!=int(obj.get("symbol_count",-1)):
            raise ValueError("RALLIES_PRIMARY_SYMBOL_COUNT")
        counts=obj.get("counts") or {}
        expected_counts={
          "FAIL_PRICE":len(groups[0]),
          "FAIL_DV30":len(groups[1]),
          "PASS_PRICE_DV30":len(groups[2]),
          "BLOCK_CURRENT_RUN":len(groups[3]),
        }
        if counts!=expected_counts:
            raise ValueError("RALLIES_PRIMARY_COUNTS")
        if queue is not None and not set(queue).issubset(union):
            raise ValueError("RALLIES_PRIMARY_CURRENT_QUEUE_COVERAGE")
        source_batches=obj.get("source_batches")
        if source_batches is not None:
            if not isinstance(source_batches,list) or not source_batches:
                raise ValueError("RALLIES_PRIMARY_SOURCE_BATCH_REFS")
            for ref in source_batches:
                if not isinstance(ref,dict) or not immutable_repo_blob_binding(ref.get("path"),ref.get("blob_sha")):
                    raise ValueError("RALLIES_PRIMARY_SOURCE_BATCH_BLOB_MISMATCH")
        predecessor_batches=obj.get("predecessor_batch_refs")
        if predecessor_batches is not None:
            if not isinstance(predecessor_batches,list) or not predecessor_batches:
                raise ValueError("RALLIES_PRIMARY_PREDECESSOR_BATCH_REFS")
            for ref in predecessor_batches:
                if not isinstance(ref,dict) or not immutable_repo_blob_binding(ref.get("path"),ref.get("blob_sha")):
                    raise ValueError("RALLIES_PRIMARY_PREDECESSOR_BATCH_BLOB_MISMATCH")
        roll_path=obj.get("source_rollforward_path")
        roll_blob=obj.get("source_rollforward_blob_sha")
        if bool(roll_path)!=bool(roll_blob):
            raise ValueError("RALLIES_PRIMARY_ROLLFORWARD_BINDING_PAIR")
        if roll_path and not immutable_repo_blob_binding(roll_path,roll_blob):
            raise ValueError("RALLIES_PRIMARY_ROLLFORWARD_BLOB_MISMATCH")
        pred_path=obj.get("predecessor_classification_path")
        pred_blob=obj.get("predecessor_classification_blob_sha")
        if bool(pred_path)!=bool(pred_blob):
            raise ValueError("RALLIES_PRIMARY_PREDECESSOR_BINDING_PAIR")
        if pred_path and not immutable_repo_blob_binding(pred_path,pred_blob):
            raise ValueError("RALLIES_PRIMARY_PREDECESSOR_BLOB_MISMATCH")
        return obj,{
          "status":"PASS","path":str(path),"blob_sha":git_blob_sha(path),
          "symbol_count":len(union),
          "pass_count":len(groups[2]),"block_count":len(groups[3]),
          "current_queue_count":len(queue) if queue is not None else None,
          "current_queue_covered":True if queue is not None else None,
        }
    except Exception as e:
        return None,{"status":"UNKNOWN","path":str(path),"reason":type(e).__name__+":"+str(e)[:160]}


def apply_c417_rallies_primary_partition(results,primary,queue):
    """Materialize the validated frozen C4.17 Rallies primary partition.

    This is not an upgrade from missing data: load_c417_rallies_primary() has
    already required exact current-queue coverage, exact30 policy invariants,
    disjoint classes, and frozen-ASOF provenance. The mapping preserves the
    published FAIL/PASS/BLOCK partition without weakening any threshold.
    """
    if not isinstance(primary,dict):
        return []
    fp=primary.get("fail_price") or {}
    fd=primary.get("fail_dv30") or {}
    pp=primary.get("pass_price_dv30") or {}
    bc=primary.get("block_current_run") or {}
    universe=set(fp)|set(fd)|set(pp)|set(bc)
    current=set(queue or [])
    if not current:
        raise RuntimeError("C417_RALLIES_PRIMARY_CURRENT_QUEUE_EMPTY")
    covered=current & universe
    source="RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9"
    changed=[]
    for sym in sorted(covered):
        if sym in fp:
            val=fp[sym] if isinstance(fp[sym],dict) else {}
            px=num(val.get("asof_close"))
            if px is None or px>=HARD_PRICE:
                raise RuntimeError("C417_RALLIES_PRIMARY_FAIL_PRICE_INVALID:"+sym)
            row={"status":"FAIL_PRICE","info":{
              "price":px,"source":source,"proof":"ASOF_CLOSE_LT_5",
              "no_synthetic_bar":True,
            },"provenance":"C417_RALLIES_PRIMARY_PARTITION"}
        elif sym in fd:
            val=fd[sym] if isinstance(fd[sym],dict) else {}
            px=num(val.get("asof_close")); dv=num(val.get("dv30_median"))
            known=val.get("known_session_count"); missing=list(val.get("missing_sessions") or [])
            if px is None or px<HARD_PRICE or dv is None or dv>=HARD_DV30 or known!=30 or missing:
                raise RuntimeError("C417_RALLIES_PRIMARY_FAIL_DV30_INVALID:"+sym)
            row={"status":"FAIL_DV30","info":{
              "price":px,"dv30":dv,"known_session_count":30,"missing_sessions":[],
              "source":source,"proof":"EXACT30_MEDIAN_LT_GATE","no_synthetic_bar":True,
            },"provenance":"C417_RALLIES_PRIMARY_PARTITION"}
        elif sym in pp:
            val=pp[sym] if isinstance(pp[sym],dict) else {}
            px=num(val.get("asof_close")); dv=num(val.get("dv30_median"))
            known=val.get("known_session_count"); missing=list(val.get("missing_sessions") or [])
            if px is None or px<HARD_PRICE or dv is None or dv<HARD_DV30 or known!=30 or missing:
                raise RuntimeError("C417_RALLIES_PRIMARY_PASS_INVALID:"+sym)
            row={"status":"PASS_PRICE_DV30","info":{
              "price":px,"dv30":dv,"known_session_count":30,"missing_sessions":[],
              "source":source,"proof":"EXACT30_MEDIAN_GE_GATE","no_synthetic_bar":True,
            },"provenance":"C417_RALLIES_PRIMARY_PARTITION"}
        else:
            val=bc[sym] if isinstance(bc[sym],dict) else {}
            row={"status":"BLOCK_CURRENT_RUN","info":{
              "reason":val.get("reason") or "RALLIES_PRIMARY_NONPASS",
              "observed_usable_sessions":val.get("observed_usable_sessions"),
              "missing_sessions":list(val.get("missing_sessions") or []),
              "zero_volume_sessions":list(val.get("zero_volume_sessions") or []),
              "source":source,"proof":"FAIL_CLOSED_CURRENT_RUN_NONPASS",
              "no_synthetic_bar":True,
            },"provenance":"C417_RALLIES_PRIMARY_PARTITION"}
        if results.get(sym)!=row:
            changed.append(sym)
        results[sym]=row
    return changed


def immutable_repo_blob_binding(rel_path,expected_blob):
    """Verify an immutable repo-relative evidence path against its Git blob SHA."""
    try:
        if not rel_path or not expected_blob:
            return False
        repo=ROOT.parent.resolve()
        p=(repo/str(rel_path)).resolve()
        p.relative_to(repo)
        return p.is_file() and git_blob_sha(p)==str(expected_blob)
    except Exception:
        return False


def c417_rallies_primary_pass_conflicts(px,queue=None):
    """Return current DV30 PASS symbols not authorized by C4.17 Rallies primary.

    Existing terminal FAIL rows are not conflicts: C4.17 explicitly permits
    stronger fail-only evidence to terminalize a Rallies fail-closed BLOCK.
    """
    primary,meta=load_c417_rallies_primary(px.get("asof_et"),queue)
    if primary is None:
        return [],meta
    primary_pass=set((primary.get("pass_price_dv30") or {}).keys())
    current_pass=set(px.get("pass_symbols") or [])
    return sorted(current_pass-primary_pass),meta


def apply_c417_rallies_primary_pass_veto(results,primary):
    """Fail closed any PASS that the C4.17 Rallies primary did not PASS.

    This never upgrades a symbol. Rallies BLOCK becomes BLOCK_CURRENT_RUN;
    any other primary non-PASS becomes UNKNOWN so no unsupported PASS survives.
    """
    if not isinstance(primary,dict):
        return []
    primary_pass=set((primary.get("pass_price_dv30") or {}).keys())
    primary_block=primary.get("block_current_run") or {}
    primary_fail_price=primary.get("fail_price") or {}
    primary_fail_dv30=primary.get("fail_dv30") or {}
    changed=[]
    for sym,row in sorted(results.items()):
        if row.get("status")!="PASS_PRICE_DV30" or sym in primary_pass:
            continue
        if sym in primary_block:
            val=primary_block[sym] if isinstance(primary_block[sym],dict) else {}
            results[sym]={
              "status":"BLOCK_CURRENT_RUN",
              "info":{
                "reason":val.get("reason") or "RALLIES_PRIMARY_NONPASS",
                "observed_usable_sessions":val.get("observed_usable_sessions"),
                "missing_sessions":list(val.get("missing_sessions") or []),
                "zero_volume_sessions":list(val.get("zero_volume_sessions") or []),
                "source":"RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9",
                "proof":"FAIL_CLOSED_CURRENT_RUN_NONPASS",
                "no_synthetic_bar":True,
              },
              "provenance":"C417_RALLIES_PRIMARY_PASS_VETO",
            }
        else:
            primary_state=(
              "FAIL_PRICE" if sym in primary_fail_price else
              "FAIL_DV30" if sym in primary_fail_dv30 else
              "MISSING_FROM_PRIMARY_PARTITION"
            )
            results[sym]={
              "status":"UNKNOWN",
              "info":{
                "reason":"C417_PRIMARY_DID_NOT_AUTHORIZE_PASS",
                "primary_state":primary_state,
                "no_synthetic_bar":True,
              },
              "provenance":"C417_RALLIES_PRIMARY_PASS_VETO",
            }
        changed.append(sym)
    return changed


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
        source_proof=(x.get("source"),x.get("proof"))
        if x.get("compact_terminal_proof") is True:
            return (
              known==30 and (x.get("missing_sessions") or [])==[]
              and x.get("no_synthetic_bar") is True
              and source_proof in {
                ("RALLIES_CANDLESTICK_SCANNER_EXACT30_PRIMARY","RALLIES_EXACT30_MEDIAN_GE_GATE"),
                ("RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9","EXACT30_MEDIAN_GE_GATE"),
              }
            )
        # C4.17 historical Alpaca SIP is settlement/fail-evidence authority,
        # not DV30 PASS authority. Longbridge PASS fallback is not implemented
        # in this loader yet; fail closed until an explicit tested wire contract exists.
        if x.get("source") not in {
          "RALLIES_CANDLESTICK_SCANNER_EXACT30_PRIMARY",
          "RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9",
        }:
            return False
        dv=num(x.get("dv30"))
        return (
          px is not None and px>=HARD_PRICE and dv is not None and dv>=HARD_DV30
          and known==30 and (x.get("missing_sessions") or [])==[]
          and x.get("no_synthetic_bar") is True
          and bool(x.get("proof"))
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
    """Disable the legacy dual-source publication fast-fail.

    Nasdaq web historical automation is intentionally disabled. A Sina-only
    sentinel would be a single-source global freeze, so canonical recovery now
    falls through to normal per-symbol fail-closed evaluation and authenticated
    resolver evidence. This helper never creates PASS/FAIL.
    """
    return False,{
      "status":"DISABLED_NO_SINGLE_SOURCE_GLOBAL_SENTINEL",
      "reason":"NASDAQ_WEB_AUTOMATION_DISABLED_NORMAL_FAIL_CLOSED_PATH_REQUIRED",
      "no_pass_or_fail_created":True,
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


def price_decision_semantic_view(obj):
    """Decision/evidence view used only to suppress metadata-only PRICE rewrites.

    Preserve bytes only when ASOF/queue/policy partitions and every symbol's
    status + evidence-bearing info are identical. Transient provenance/retry
    diagnostics are intentionally excluded. Any real gate/evidence/status
    change produces a new canonical artifact.
    """
    results=obj.get("results") or {}
    return {
      "schema":obj.get("schema"),
      "task_id":obj.get("task_id"),
      "asof_et":obj.get("asof_et"),
      "execution":obj.get("execution"),
      "real_money":obj.get("real_money"),
      "unknown_never_pass":obj.get("unknown_never_pass"),
      "source_master_queue_hash":obj.get("source_master_queue_hash"),
      "source_master_count":obj.get("source_master_count"),
      "expected30":list(obj.get("expected30") or []),
      "gate_order":list(obj.get("gate_order") or []),
      "thresholds":obj.get("thresholds") or {},
      "counts":obj.get("counts") or {},
      "unknown_count":obj.get("unknown_count"),
      "unknown_symbols":list(obj.get("unknown_symbols") or []),
      "blocked_count":obj.get("blocked_count"),
      "blocked_symbols":list(obj.get("blocked_symbols") or []),
      "pass_count":obj.get("pass_count"),
      "pass_symbols":list(obj.get("pass_symbols") or []),
      "pass_hash":obj.get("pass_hash"),
      "results":{
        s:{"status":(r or {}).get("status"),"info":(r or {}).get("info")}
        for s,r in sorted(results.items())
      },
    }



def _parse_nasdaq_et(date_text,time_text):
    d=str(date_text or "").strip()
    t=str(time_text or "").strip()
    if not d:
        return None
    if not t:
        t="00:00:00"
    for fmt in ("%m/%d/%Y %H:%M:%S.%f","%m/%d/%Y %H:%M:%S","%Y-%m-%d %H:%M:%S.%f","%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(d+" "+t,fmt)
        except ValueError:
            pass
    return None


def official_full_session_halt_terminal(guard,sym,asof):
    """Return fail-only official Nasdaq evidence when the entire ASOF RTH session was halted.

    This function can never create PASS. It only recognizes an existing
    BLOCK_CURRENT_RUN whose official Nasdaq halt began no later than 09:30 ET
    on ASOF and whose scheduled resumption is absent or strictly after 16:00 ET.
    """
    try:
        if not isinstance(guard,dict) or guard.get("schema")!="XRAY_OFFICIAL_SOURCE_GUARD_V1":
            return None
        th=((guard.get("sources") or {}).get("trade_halts") or {})
        if th.get("status")!="PASS":
            return None
        asof_open=datetime.strptime(str(asof)+" 09:30:00","%Y-%m-%d %H:%M:%S")
        asof_close=datetime.strptime(str(asof)+" 16:00:00","%Y-%m-%d %H:%M:%S")
        for row in th.get("items") or []:
            if str(row.get("IssueSymbol") or "").strip().upper()!=str(sym).upper():
                continue
            if str(row.get("Market") or "").strip().upper()!="NASDAQ":
                continue
            started=_parse_nasdaq_et(row.get("HaltDate"),row.get("HaltTime"))
            if started is None or started>asof_open:
                continue
            rd=str(row.get("ResumptionDate") or "").strip()
            rt=str(row.get("ResumptionTradeTime") or "").strip()
            resumed=_parse_nasdaq_et(rd,rt) if rd else None
            if resumed is not None and resumed<=asof_close:
                continue
            return {
              "reason":"OFFICIAL_NASDAQ_FULL_SESSION_HALT_NO_ASOF_BAR",
              "proof":"NASDAQ_TRADER_FULL_SESSION_HALT",
              "source":"NASDAQ_TRADER_OFFICIAL_HALT_RSS",
              "source_url":str(th.get("url") or ""),
              "halt_date":str(row.get("HaltDate") or ""),
              "halt_time_et":str(row.get("HaltTime") or ""),
              "reason_code":str(row.get("ReasonCode") or ""),
              "resumption_date":rd,
              "resumption_trade_time_et":rt,
              "market":"NASDAQ",
              "asof_et":str(asof),
              "no_synthetic_bar":True,
              "decision_direction":"FAIL_ONLY_NEVER_PASS",
            }
        return None
    except Exception:
        return None


def apply_official_full_session_halt_fail_only(results,guard,asof):
    """Terminalize only unresolved full-session halts; never overwrite PASS/FAIL."""
    changed=[]
    if not isinstance(guard,dict):
        return changed
    for sym,row in sorted(results.items()):
        if row.get("status") not in {"BLOCK_CURRENT_RUN","UNKNOWN"}:
            continue
        ev=official_full_session_halt_terminal(guard,sym,asof)
        if not ev:
            continue
        results[sym]={
          "status":"FAIL_PRICE_NO_ASOF_BAR",
          "info":ev,
          "provenance":"OFFICIAL_NASDAQ_FULL_SESSION_HALT_FAIL_ONLY",
        }
        changed.append(sym)
    return changed


def load_official_listing_registry():
    try:
        obj=json.loads(OFFICIAL_LISTING_REGISTRY.read_text())
        if not (
          obj.get("schema")=="XRAY_PRICE_OFFICIAL_LISTING_REGISTRY_V1"
          and obj.get("authority")=="OFFICIAL_LISTING_DATE_FAIL_ONLY"
          and obj.get("execution")=="NONE" and obj.get("real_money")=="NO-GO"
          and obj.get("unknown_never_pass") is True
          and isinstance(obj.get("records"),dict)
        ):
            return None,{"status":"INVALID","reason":"REGISTRY_SCHEMA_OR_SAFETY_INVALID"}
        return obj,{
          "status":"PASS",
          "path":str(OFFICIAL_LISTING_REGISTRY),
          "content_sha256":hashlib.sha256(OFFICIAL_LISTING_REGISTRY.read_bytes()).hexdigest(),
          "record_count":len(obj.get("records") or {}),
        }
    except Exception as e:
        return None,{"status":"UNKNOWN","reason":type(e).__name__+":"+str(e)[:160]}


def official_recent_listing_terminal(registry,sym,asof,exp30):
    """Fail-only proof that exact-30 DV30 cannot exist for a newly listed security.

    This function can never create PASS. It requires an official first-trade date
    strictly after the first session in the exact 30-session window and no later
    than ASOF. That proves fewer than 30 completed trading sessions can exist.
    """
    try:
        if not isinstance(registry,dict):
            return None
        rec=(registry.get("records") or {}).get(str(sym).upper())
        if not isinstance(rec,dict):
            return None
        authority=str(rec.get("authority") or "")
        if authority not in {
          "ISSUER_IR_PRIMARY","SEC_PRIMARY","NASDAQ_PRIMARY_PUBLISHER",
          "NASDAQ_TRADER_PRIMARY",
        }:
            return None
        source_url=str(rec.get("source_url") or "")
        first=str(rec.get("first_trade_date") or "")[:10]
        if not source_url or len(first)!=10 or not exp30:
            return None
        if first>str(asof) or first<=str(exp30[0]):
            return None
        possible_sessions=sum(1 for d in exp30 if d>=first)
        if possible_sessions>=30:
            return None
        return {
          "reason":"OFFICIAL_RECENT_LISTING_LT_30_COMPLETED_SESSIONS",
          "proof":"OFFICIAL_FIRST_TRADE_DATE_AFTER_EXACT30_WINDOW_START",
          "source":authority,
          "source_url":source_url,
          "evidence_kind":str(rec.get("evidence_kind") or ""),
          "first_trade_date":first,
          "asof_et":str(asof),
          "exact30_window_start":str(exp30[0]),
          "max_possible_completed_sessions_in_exact30_window":possible_sessions,
          "no_synthetic_bar":True,
          "decision_direction":"FAIL_ONLY_NEVER_PASS",
        }
    except Exception:
        return None


def apply_official_recent_listing_fail_only(results,registry,asof,exp30):
    """Terminalize only unresolved recent listings; never overwrite PASS/FAIL."""
    changed=[]
    if not isinstance(registry,dict):
        return changed
    for sym,row in sorted(results.items()):
        if row.get("status") not in {"BLOCK_CURRENT_RUN","UNKNOWN"}:
            continue
        ev=official_recent_listing_terminal(registry,sym,asof,exp30)
        if not ev:
            continue
        results[sym]={
          "status":"FAIL_DV30_INSUFFICIENT_SESSIONS",
          "info":ev,
          "provenance":"OFFICIAL_RECENT_LISTING_FAIL_ONLY",
        }
        changed.append(sym)
    return changed


def load_official_halt_guard():
    try:
        guard=json.loads(OFFICIAL_GUARD.read_text())
        return guard,{
          "status":"PASS",
          "path":str(OFFICIAL_GUARD),
          "content_sha256":hashlib.sha256(OFFICIAL_GUARD.read_bytes()).hexdigest(),
          "source_status":((guard.get("sources") or {}).get("trade_halts") or {}).get("status"),
        }
    except Exception as e:
        return None,{"status":"UNKNOWN","reason":type(e).__name__+":"+str(e)[:160]}


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
    # Validate the frozen primary as an immutable authority artifact, but do
    # not require it to cover newly admitted identity survivors that never
    # belonged to the frozen PRICE resolver scope. Uncovered names stay
    # fail-closed under the live zero-dollar chain and can never gain PASS via
    # the primary materializer.
    rallies_primary,rallies_primary_meta=load_c417_rallies_primary(asof)
    rallies_primary_pass=set((rallies_primary or {}).get("pass_price_dv30",{}).keys())
    for sym in queue:
        r=old[sym];st=r.get("status");info=r.get("info")
        if st in {"PASS","PASS_PRICE_DV30"} and rallies_primary is not None and sym not in rallies_primary_pass:
            redo.append(sym);policy_redo.add(sym);continue
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
    rallies_primary_materialized=apply_c417_rallies_primary_partition(
        results,rallies_primary,queue
    )

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

    rallies_primary_pass_vetoed=apply_c417_rallies_primary_pass_veto(
        results,rallies_primary
    )

    # Official Nasdaq full-session halts are terminal fail-only evidence for
    # the ASOF price gate. They resolve provider-coverage ambiguity without
    # manufacturing a bar or changing the PRICE/DV30 thresholds.
    official_guard,official_halt_guard_meta=load_official_halt_guard()
    official_halt_terminalized=apply_official_full_session_halt_fail_only(
        results,official_guard,asof
    )

    # Official first-trade/listing dates can terminalize recent listings when
    # the exact 30-session DV30 history cannot mathematically exist by ASOF.
    # This is fail-only and never manufactures a bar, price, volume, or PASS.
    official_listing_registry,official_listing_registry_meta=load_official_listing_registry()
    official_listing_terminalized=apply_official_recent_listing_fail_only(
        results,official_listing_registry,asof,exp30
    )

    # Resolver BLOCK_CURRENT_RUN is fail-closed, but it must not silently
    # disappear from completeness. Re-evaluate non-halt blocks through the
    # remaining zero-dollar local chain (Sina -> Yahoo fail-only). Nasdaq web
    # automation is disabled; authenticated resolver evidence remains separate.
    # Only terminal PASS/FAIL may replace the authenticated block.
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

    rallies_primary_post_recovery_vetoed=apply_c417_rallies_primary_pass_veto(
        results,rallies_primary
    )

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
      "c417_rallies_primary_meta":rallies_primary_meta,
      "c417_rallies_primary_materialized_count":len(rallies_primary_materialized),
      "c417_rallies_primary_materialized_symbols":sorted(rallies_primary_materialized),
      "c417_rallies_primary_current_queue_uncovered_symbols":sorted(
          set(queue)-(
              set((rallies_primary or {}).get("fail_price",{}))
              | set((rallies_primary or {}).get("fail_dv30",{}))
              | set((rallies_primary or {}).get("pass_price_dv30",{}))
              | set((rallies_primary or {}).get("block_current_run",{}))
          )
      ),
      "c417_rallies_primary_pass_veto_count":len(rallies_primary_pass_vetoed),
      "c417_rallies_primary_pass_veto_symbols":sorted(rallies_primary_pass_vetoed),
      "c417_rallies_primary_post_recovery_veto_count":len(rallies_primary_post_recovery_vetoed),
      "c417_rallies_primary_post_recovery_veto_symbols":sorted(rallies_primary_post_recovery_vetoed),
      "counts":dict(sorted(counts.items())),"unknown_count":len(unknown),"unknown_symbols":unknown,
      "blocked_count":len(blocked),"blocked_symbols":blocked,
      "block_recovery_attempted":True,
      "block_recovery_input_count":len(blocked_before),
      "block_recovery_resolved_count":len(recovered_blocks),
      "block_recovery_resolved_symbols":sorted(recovered_blocks),
      "official_halt_guard_meta":official_halt_guard_meta,
      "official_halt_terminalized_count":len(official_halt_terminalized),
      "official_halt_terminalized_symbols":sorted(official_halt_terminalized),
      "official_listing_registry_meta":official_listing_registry_meta,
      "official_listing_terminalized_count":len(official_listing_terminalized),
      "official_listing_terminalized_symbols":sorted(official_listing_terminalized),
      "pass_count":len(passes),"pass_symbols":passes,
      "pass_hash":hashlib.sha256("\n".join(passes).encode()).hexdigest(),
      "results":dict(sorted(results.items()))
    }
    byte_stable_preserved=False
    if baseline_source=="CURRENT_PRICE_ARTIFACT" and price_decision_semantic_view(prior)==price_decision_semantic_view(obj):
        obj=prior
        byte_stable_preserved=True
    else:
        OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"reused":obj["reused_terminal_count"],"reevaluated":obj["reevaluated_count"],"policy_replay":FORCE_POLICY_REPLAY,"policy_replay_input_count":len(policy_redo),"counts":obj["counts"],"unknown_count":obj["unknown_count"],"blocked_count":obj["blocked_count"],"block_recovery_input":obj["block_recovery_input_count"],"block_recovery_resolved":obj["block_recovery_resolved_count"],"official_halt_terminalized":obj.get("official_halt_terminalized_count",0),"official_listing_terminalized":obj.get("official_listing_terminalized_count",0),"c417_rallies_primary_pass_veto_count":obj.get("c417_rallies_primary_pass_veto_count",0),"pass_count":obj["pass_count"],"pass_hash":obj["pass_hash"],"byte_stable_preserved":byte_stable_preserved},sort_keys=True))
if __name__=="__main__":main()
