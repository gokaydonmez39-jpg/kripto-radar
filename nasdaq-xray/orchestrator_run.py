#!/usr/bin/env python3
"""NASDAQ SWING X-RAY external autonomous orchestrator.
Deterministic research data plane only.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
Does not mutate ChatGPT canonical Durable State and never places orders.
"""
from __future__ import annotations
import hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATE=ROOT/"orchestrator_state.json"
TASK_ID="6a825366222081918997094d76e6ae46"

ENGINE_FILES=[
 "sina_stage.py",
 "mc_zero_key.py",
 "production_core_build.py",
 "alpha_semantics.py",
 "stage1_shadow.py",
 "regime_breadth_shadow.py",
 "deep_pre_r1_shadow.py",
 "history_official_identity_evidence.json",
 "requirements-runtime.txt",
]

def readj(path):
    p=ROOT/path
    return json.loads(p.read_text()) if p.exists() else {}

def sha_file(path):
    p=ROOT/path
    if not p.exists(): return "MISSING"
    return hashlib.sha256(p.read_bytes()).hexdigest()

def hash_lines(items):
    return hashlib.sha256("\n".join(items).encode()).hexdigest()

def frozen_identity_partition_ok(ss):
    """Validate frozen PASS+UNKNOWN identity partitions without promoting UNKNOWN.

    V2 used discovery_queue_total as the post-partition raw total.
    V3 explicitly removes official blank-type rows before the PASS/UNKNOWN
    partition, so discovery_queue_total is the pre-blank-exclusion total and
    must equal raw_identity_total + official_blank_checks_excluded_count.
    """
    try:
        q=list(ss.get("queue") or [])
        dm=ss.get("discovery_meta") or {}
        unknown=sorted(set(ss.get("identity_unknown_symbols") or []))
        detail=ss.get("identity_unknown_detail") or {}
        raw=int(ss.get("raw_identity_total",-1))
        policy=str(ss.get("identity_partition_policy") or "")
        dm_policy=str(dm.get("identity_partition_policy") or "")
        if policy!=dm_policy:
            return False
        if policy=="MASTER_SPAC_UNKNOWN_PARTITION_V2_FROZEN_GUARD":
            discovery_total_ok=(int(dm.get("discovery_queue_total",-1))==raw)
        elif policy in {
            "MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V3_FROZEN_GUARD",
            "MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD",
        }:
            blank_count=int(dm.get("official_blank_checks_excluded_count",-1))
            blank_hash=str(dm.get("official_blank_checks_excluded_hash") or "")
            discovery_total_ok=bool(
                blank_count>=0
                and blank_hash==hash_lines(sorted(set(dm.get("official_blank_checks_excluded_symbols") or [])))
                if dm.get("official_blank_checks_excluded_symbols") is not None
                else bool(blank_hash)
            )
            discovery_total_ok=bool(
                discovery_total_ok
                and int(dm.get("discovery_queue_total",-1))==raw+blank_count
            )
            if policy=="MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD":
                discovery_total_ok=bool(discovery_total_ok and exact_asof_v4_identity_proofs_ok(ss))
        else:
            return False
        return bool(
          int(ss.get("queue_total",-1))==len(q)==len(set(q))
          and ss.get("queue_hash")==hash_lines(q)
          and set(detail)==set(unknown)
          and not (set(q)&set(unknown))
          and int(dm.get("identity_unknown_count",-1))==len(unknown)
          and dm.get("identity_unknown_hash")==hash_lines(unknown)
          and raw==len(q)+len(unknown)
          and int(dm.get("raw_identity_total",-1))==raw
          and discovery_total_ok
          and all((detail.get(x) or {}).get("unknown_never_pass") is True for x in unknown)
        )
    except Exception:
        return False

def git_blob_sha(path):
    p=Path(path)
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def _repo_rel_to_root(rel):
    rel=str(rel or "")
    if not rel.startswith("nasdaq-xray/") or ".." in Path(rel).parts:
        return None
    return ROOT/Path(rel).name


def exact_asof_v4_identity_proofs_ok(ss):
    """Validate V4 exact-ASOF identity witnesses without making market decisions."""
    try:
        dm=ss.get("discovery_meta") or {}
        asof=str(ss.get("asof_et") or "")
        stamp=asof.replace("-","")
        if not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}",asof):
            return False

        snap_rel=str(dm.get("membership_snapshot_path") or "")
        sec_rel=str(dm.get("sec_spac_proof_path") or "")
        ident_rel=str(dm.get("asof_identity_proof_path") or "")
        if snap_rel!=f"nasdaq-xray/master_nasdaq_directory_snapshot_{stamp}.json":
            return False
        if sec_rel!=f"nasdaq-xray/master_sec_spac_proof_{stamp}.json":
            return False
        if ident_rel!=f"nasdaq-xray/master_asof_identity_proof_{stamp}.json":
            return False

        snap_p=_repo_rel_to_root(snap_rel)
        sec_p=_repo_rel_to_root(sec_rel)
        ident_p=_repo_rel_to_root(ident_rel)
        if not all(p is not None and p.exists() for p in (snap_p,sec_p,ident_p)):
            return False
        if git_blob_sha(snap_p)!=str(dm.get("membership_snapshot_blob_sha") or ""):
            return False
        if git_blob_sha(sec_p)!=str(dm.get("sec_spac_proof_blob_sha") or ""):
            return False
        if git_blob_sha(ident_p)!=str(dm.get("asof_identity_proof_blob_sha") or ""):
            return False

        snap=json.loads(snap_p.read_text(encoding="utf-8"))
        sec=json.loads(sec_p.read_text(encoding="utf-8"))
        ident=json.loads(ident_p.read_text(encoding="utf-8"))
        if not (
            snap.get("schema")=="XRAY_NASDAQ_DIRECTORY_SNAPSHOT_V1"
            and snap.get("asof_et")==asof
            and snap.get("authority")=="IMMUTABLE_EXACT_ASOF_NASDAQ_DIRECTORY_MEMBERSHIP_SNAPSHOT"
            and snap.get("applicability")=="EXACT_ASOF_MEMBERSHIP_ONLY_NO_FORWARD_CARRY"
            and snap.get("execution")=="NONE" and snap.get("real_money")=="NO-GO"
            and snap.get("unknown_never_pass") is True
            and snap.get("membership_only") is True
            and snap.get("identity_decisions_reused") is False
            and snap.get("source_queue_classification_ignored") is True
            and snap.get("source_directory_date")==asof
        ):
            return False
        names=snap.get("security_names") or {}
        industries=snap.get("industries") or {}
        if int(snap.get("membership_count",-1))!=len(names) or int(snap.get("industry_count",-1))!=len(industries):
            return False
        if not set(industries)<=set(names) or not names:
            return False

        proofs=sec.get("proofs") or {}
        if not (
            sec.get("schema")=="XRAY_MASTER_SEC_SPAC_PROOF_V1"
            and sec.get("asof_et")==asof
            and sec.get("authority")=="SEC_EDGAR_SIC_6770_EXACT_ASOF"
            and sec.get("applicability")=="EXACT_ASOF_ONLY_NO_FORWARD_CARRY"
            and sec.get("execution")=="NONE" and sec.get("real_money")=="NO-GO"
            and sec.get("unknown_never_pass") is True
            and int(dm.get("sec_spac_proof_count",-1))==len(proofs)
            and dm.get("sec_spac_proof_hash")==hash_lines(sorted(proofs))
        ):
            return False

        groups={
            "restore_to_asof":ident.get("restore_to_asof") or {},
            "remove_from_asof":ident.get("remove_from_asof") or {},
            "operating_overrides":ident.get("operating_overrides") or {},
        }
        if not (
            ident.get("schema")=="XRAY_MASTER_ASOF_IDENTITY_PROOF_V1"
            and ident.get("asof_et")==asof
            and ident.get("authority")=="NASDAQTRADER_SEC_EXACT_ASOF_IDENTITY_RECONCILIATION"
            and ident.get("applicability")=="EXACT_ASOF_ONLY_NO_FORWARD_CARRY"
            and ident.get("execution")=="NONE" and ident.get("real_money")=="NO-GO"
            and ident.get("unknown_never_pass") is True
            and all(isinstance(v,dict) for v in groups.values())
            and (dm.get("asof_identity_proof_counts") or {})=={k:len(v) for k,v in groups.items()}
        ):
            return False
        sets=[set(v) for v in groups.values()]
        if any(sets[a]&sets[b] for a in range(len(sets)) for b in range(a+1,len(sets))):
            return False
        return True
    except Exception:
        return False


def immutable_membership_partition_ok(ss):
    try:
        dm=ss.get("discovery_meta") or {}
        asof=str(ss.get("asof_et") or "")
        if dm.get("authority")!="IMMUTABLE_EXACT_ASOF_MEMBERSHIP_SNAPSHOT_NO_MARKET_DECISIONS": return False
        if dm.get("full_identity") is not True: return False
        if dm.get("identity_decisions_reused_from_snapshot") is not False: return False
        rel=str(dm.get("membership_snapshot_path") or "")
        expected=f"nasdaq-xray/master_nasdaq_directory_snapshot_{asof.replace('-','')}.json"
        if rel!=expected: return False
        p=ROOT/Path(rel).name
        if not p.exists() or git_blob_sha(p)!=str(dm.get("membership_snapshot_blob_sha") or ""): return False
        snap=json.loads(p.read_text(encoding="utf-8"))
        names={str(k).strip().upper():str(v).strip() for k,v in (snap.get("security_names") or {}).items() if str(k).strip() and str(v).strip()}
        industries={str(k).strip().upper():str(v).strip() for k,v in (snap.get("industries") or {}).items() if str(k).strip()}
        footer=str(snap.get("source_directory_footer") or "")
        if not footer.startswith("File Creation Time:"): return False
        digits="".join(ch for ch in footer[len("File Creation Time:"):] if ch.isdigit())
        if len(digits)<8: return False
        mm,dd,yyyy=digits[:2],digits[2:4],digits[4:8]
        if (snap.get("schema")!="XRAY_NASDAQ_DIRECTORY_SNAPSHOT_V1"
            or snap.get("asof_et")!=asof
            or snap.get("execution")!="NONE" or snap.get("real_money")!="NO-GO"
            or snap.get("unknown_never_pass") is not True
            or snap.get("authority")!="IMMUTABLE_EXACT_ASOF_NASDAQ_DIRECTORY_MEMBERSHIP_SNAPSHOT"
            or snap.get("applicability")!="EXACT_ASOF_MEMBERSHIP_ONLY_NO_FORWARD_CARRY"
            or snap.get("membership_only") is not True
            or snap.get("identity_decisions_reused") is not False
            or snap.get("source_queue_classification_ignored") is not True
            or snap.get("source_directory_date")!=asof
            or f"{yyyy}-{mm}-{dd}"!=asof
            or int(snap.get("membership_count",-1))!=len(names)
            or int(snap.get("industry_count",-1))!=len(industries)
            or not set(industries)<=set(names) or not names):
            return False
        return frozen_identity_partition_ok(ss)
    except Exception:
        return False

def direct_no_web_identity_ok(ss):
    """Accept live NasdaqTrader full identity only with exact-ASOF/no-web bindings."""
    try:
        dm=ss.get("discovery_meta") or {}
        asof=str(ss.get("asof_et") or "")
        footer=str(ss.get("official_footer") or "")
        if not (
          dm.get("authority")=="NASDAQTRADER_FULL_IDENTITY_NO_NASDAQ_WEB_MARKET_METADATA"
          and dm.get("full_identity") is True
          and dm.get("nasdaq_web_screener_used") is False
          and footer.startswith("File Creation Time:")
        ):
            return False
        digits="".join(ch for ch in footer[len("File Creation Time:"):] if ch.isdigit())
        if len(digits)<8:
            return False
        mm,dd,yyyy=digits[:2],digits[2:4],digits[4:8]
        if f"{yyyy}-{mm}-{dd}"!=asof:
            return False
        return frozen_identity_partition_ok(ss)
    except Exception:
        return False


def stable_engine_hash():
    h=hashlib.sha256()
    for name in ENGINE_FILES:
        p=ROOT/name
        h.update(name.encode()); h.update(b"\0"); h.update(p.read_bytes()); h.update(b"\0")
    return h.hexdigest()

def _write_state(name, obj):
    (ROOT/name).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")


def invalidate_downstream_for_partial_history(ss):
    """Replace every downstream shadow artifact with an explicit fail-closed tombstone.

    Partial HISTORY must never leave a prior-ASOF MC/core/technical state looking
    current. These tombstones are support-plane diagnostics only and cannot
    authorize alpha.
    """
    asof=ss.get("asof_et")
    ts=datetime.now(timezone.utc).isoformat()
    upstream_marker={"__UPSTREAM_HISTORY__":{
        "reason":"WAITING_UPSTREAM_HISTORY",
        "fail_closed":True,
        "unknown_never_pass":True,
    }}
    empty_hash=hash_lines([])
    states={
      "mc_zero_key_state.json":{
        "schema":"XRAY_MC_ZERO_KEY_V3","status":"WAITING_UPSTREAM_HISTORY",
        "task_id":TASK_ID,"asof_et":asof,"execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"alpha_authority":False,"pit_safe_shadow":True,
        "direct_nasdaq_conservative_pass_count":0,"definitive_fail_count":0,
        "unresolved_count":1,"direct_nasdaq_conservative_pass":{},
        "definitive_fail":{},"unresolved":upstream_marker,
        "nasdaq_snapshot_binding":{"status":"NOT_EVALUATED_WAITING_UPSTREAM_HISTORY"},
        "nasdaq_current_diagnostic_count":0,"nasdaq_current_diagnostic":{},
        "current_core_zero_key":[],"fallback_watch_symbols":[],
        "overlay_meta":{"status":"NOT_EVALUATED_WAITING_UPSTREAM_HISTORY"},
        "updated_at_utc":ts,
        "policy_note":"FAIL_CLOSED_TOMBSTONE; upstream HISTORY incomplete; no MC decision authority."
      },
      "production_core_state.json":{
        "schema":"XRAY_EXTERNAL_ZERO_KEY_CORE_V1","status":"WAITING_UPSTREAM_HISTORY",
        "task_id":TASK_ID,"asof_et":asof,"execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"alpha_authority":False,
        "authority":"EXTERNAL_SHADOW_DATA_PLANE_NOT_CANONICAL_DURABLE_STATE",
        "current_core_mc_pass":[],"current_core_count":0,"current_core_hash":empty_hash,
        "state_caps":{},"fallback_watch_symbols":[],"r92_ineligible":[],
        "mc_unresolved":upstream_marker,"mc_unresolved_count":1,
        "mc_definitive_fail":{},"updated_at_utc":ts
      },
      "stage1_shadow.json":{
        "schema":"XRAY_STAGE1_SHADOW_V1","status":"WAITING_UPSTREAM_HISTORY",
        "task_id":TASK_ID,"asof_et":asof,"execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"alpha_authority":False,
        "weekly_pass_count":0,"unknown_count":1,"results":{},"updated_at_utc":ts
      },
      "regime_breadth_shadow.json":{
        "schema":"XRAY_REGIME_BREADTH_SHADOW_V1","status":"WAITING_UPSTREAM_HISTORY",
        "task_id":TASK_ID,"asof_et":asof,"execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"alpha_authority":False,
        "regime":"UNKNOWN","breadth_missing_count":1,"results":{},"updated_at_utc":ts
      },
      "deep_pre_r1_shadow.json":{
        "schema":"XRAY_DEEP_PRE_R1_SHADOW_V1","status":"WAITING_UPSTREAM_HISTORY",
        "task_id":TASK_ID,"asof_et":asof,"execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"alpha_authority":False,
        "authority":"SHADOW_DEEP_PREFILTER_ONLY_NO_SIGNAL",
        "a_geometry_count":0,"b_breakout_count":0,"b_armed_count":0,
        "d_geometry_rs_count":0,"unknown_history_count":1,"results":{},
        "updated_at_utc":ts
      },
    }
    for name,obj in states.items():
        _write_state(name,obj)
    return {name:{"schema":obj["schema"],"status":obj["status"],"asof_et":asof}
            for name,obj in states.items()}


def run(script, extra_env=None):
    env=os.environ.copy()
    if extra_env: env.update(extra_env)
    print(f"XRAY_RUN={script}", flush=True)
    cp=subprocess.run([sys.executable,str(ROOT/script)],cwd=ROOT.parent,env=env,text=True)
    if cp.returncode!=0:
        raise RuntimeError(f"{script}:EXIT_{cp.returncode}")

def main():
    now_et=datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
    # Keep an all-UTC schedule without accidentally treating UTC Saturday as ET Friday loss.
    if now_et.weekday()>=5:
        print("XRAY_ORCHESTRATOR=NOOP_ET_WEEKEND")
        return

    # 1) Progress/refresh official universe + PRICE/DV20/HISTORY.
    # Repeated local invocations are resumable and bounded; same epoch does zero new work once complete.
    max_loops=max(1,min(16,int(os.getenv("XRAY_ORCHESTRATOR_MAX_LOOPS","16"))))
    for i in range(max_loops):
        run("sina_stage.py",{"XRAY_FULL_IDENTITY":"1"})
        ss=readj("sina_state.json")
        dm=ss.get("discovery_meta") or {}
        authority=str(dm.get("authority") or "")
        allowed={"FULL_IDENTITY_NO_PREFILTER","CANONICAL_FROZEN_FULL_IDENTITY_SAME_ASOF","IMMUTABLE_EXACT_ASOF_MEMBERSHIP_SNAPSHOT_NO_MARKET_DECISIONS","NASDAQTRADER_FULL_IDENTITY_NO_NASDAQ_WEB_MARKET_METADATA"}
        if dm.get("full_identity") is not True or authority not in allowed:
            raise RuntimeError("FULL_UNIVERSE_IDENTITY_NOT_PROVEN")
        if authority=="CANONICAL_FROZEN_FULL_IDENTITY_SAME_ASOF":
            frozen_hash=str(dm.get("frozen_queue_hash") or "")
            if not frozen_hash or frozen_hash!=str(ss.get("queue_hash") or ""):
                raise RuntimeError("FROZEN_FULL_UNIVERSE_HASH_MISMATCH")
            if not frozen_identity_partition_ok(ss):
                raise RuntimeError("FROZEN_FULL_UNIVERSE_PARTITION_MISMATCH")
        elif authority=="IMMUTABLE_EXACT_ASOF_MEMBERSHIP_SNAPSHOT_NO_MARKET_DECISIONS":
            if not immutable_membership_partition_ok(ss):
                raise RuntimeError("IMMUTABLE_EXACT_ASOF_MEMBERSHIP_PARTITION_MISMATCH")
        elif authority=="NASDAQTRADER_FULL_IDENTITY_NO_NASDAQ_WEB_MARKET_METADATA":
            if not direct_no_web_identity_ok(ss):
                raise RuntimeError("NASDAQTRADER_DIRECT_NO_WEB_IDENTITY_PARTITION_MISMATCH")
        print("XRAY_HISTORY_STATUS="+str(ss.get("status"))+" CURSOR="+str(ss.get("cursor"))+"/"+str(ss.get("queue_total"))+" FULL_IDENTITY=1 AUTHORITY="+authority,flush=True)
        if ss.get("status")=="HISTORY_COMPLETE":
            break
    ss=readj("sina_state.json")
    if ss.get("status")!="HISTORY_COMPLETE":
        downstream_invalidation=invalidate_downstream_for_partial_history(ss)
        out={
          "schema":"XRAY_ORCHESTRATOR_V1","task_id":TASK_ID,
          "execution":"NONE","real_money":"NO-GO",
          "updated_at_utc":datetime.now(timezone.utc).isoformat(),
          "status":"PARTIAL_HISTORY","asof_et":ss.get("asof_et"),
          "cursor":ss.get("cursor"),"queue_total":ss.get("queue_total"),
          "full_universe_identity":True,"queue_hash":ss.get("queue_hash"),
          "g9_status":"BLOCKED","account_gate":"UNKNOWN_NOT_CONFIGURED",
          "downstream_invalidation":downstream_invalidation
        }
        STATE.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
        print("XRAY_ORCHESTRATOR=PARTIAL_HISTORY")
        return

    cand_hash=sha_file("sina_candidates.json")
    engine_hash=stable_engine_hash()
    old=readj("orchestrator_state.json")
    fingerprint=hashlib.sha256((cand_hash+"|"+engine_hash).encode()).hexdigest()

    # Root is a data-plane support layer, not canonical candidate authority.
    # It must never depend on stale/current Canonical Event, Legal, lifecycle or
    # finalist artifacts from a different ASOF.
    if old.get("fingerprint")==fingerprint and old.get("status")=="DATA_PLANE_PASS_CANONICAL_DOWNSTREAM_DEFERRED":
        print("XRAY_ORCHESTRATOR=NOOP_UNCHANGED_DATA_PLANE")
        return

    # 2) Fail-closed zero-key MC and autonomous support core.
    run("mc_zero_key.py")
    run("production_core_build.py")
    core=readj("production_core_state.json")

    # 3) Root-owned technical diagnostics only. Deep runs geometry-only so this
    # layer never consumes Canonical Event/Legal/Final evidence. All event,
    # detailed legal, R1/RR, lifecycle, official-safety and candidate authority
    # remains exclusively in the canonical Post-MC/Final chain.
    common_env={"XRAY_MC_STATE":str(ROOT/"production_core_state.json")}
    run("stage1_shadow.py",common_env)
    run("regime_breadth_shadow.py",common_env)
    run("deep_pre_r1_shadow.py",{
        "XRAY_DEEP_GEOMETRY_ONLY":"1",
        "XRAY_STAGE1_STATE":str(ROOT/"stage1_shadow.json"),
        "XRAY_DEEP_OUT":str(ROOT/"deep_pre_r1_shadow.json"),
    })

    st1=readj("stage1_shadow.json")
    rg=readj("regime_breadth_shadow.json")
    deep=readj("deep_pre_r1_shadow.json")
    mc=readj("mc_zero_key_state.json")

    coverage_faults=[]
    identity_unknown_count=len(set(ss.get("identity_unknown_symbols") or []))
    if identity_unknown_count>0: coverage_faults.append("MASTER_IDENTITY_UNKNOWN_REMAINS")
    if int(ss.get("unknown_count",0) or 0)>0: coverage_faults.append("HARD_GATE_UNKNOWN_REMAINS")
    if int(mc.get("unresolved_count",0) or 0)>0: coverage_faults.append("MC_UNRESOLVED_REMAINS")
    if int(st1.get("unknown_count",0) or 0)>0: coverage_faults.append("STAGE1_UNKNOWN_REMAINS")
    if int(rg.get("breadth_missing_count",0) or 0)>0: coverage_faults.append("BREADTH_MISSING_REMAINS")
    if int(deep.get("unknown_history_count",0) or 0)>0: coverage_faults.append("DEEP_HISTORY_UNKNOWN_REMAINS")

    blockers=list(coverage_faults)
    blockers.append("CANONICAL_EVENTS_LEGAL_R1_RR_LIFECYCLE_DEFERRED")
    blockers.append("G9_BLOCKED_NO_AUTHORIZED_ZERO_DOLLAR_RUNTIME_SOURCE")
    blockers.append("ACCOUNT_GATE_UNKNOWN")
    blockers.append("OBSERVED_IPHONE_SIGNAL_DELIVERY_UNPROVEN")

    status="DATA_PLANE_PARTIAL_UNKNOWN" if coverage_faults else "DATA_PLANE_PASS_CANONICAL_DOWNSTREAM_DEFERRED"
    out={
      "schema":"XRAY_ORCHESTRATOR_V1","task_id":TASK_ID,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "updated_at_utc":datetime.now(timezone.utc).isoformat(),
      "status":status,"asof_et":ss.get("asof_et"),
      "fingerprint":fingerprint,
      "candidate_hash":cand_hash,"engine_hash":engine_hash,
      "history":{"status":ss.get("status"),"queue_total":ss.get("queue_total"),"queue_hash":ss.get("queue_hash"),
                 "raw_identity_total":ss.get("raw_identity_total"),
                 "identity_unknown_count":len(set(ss.get("identity_unknown_symbols") or [])),
                 "identity_partition_policy":ss.get("identity_partition_policy"),
                 "full_universe_identity":True,"counts":ss.get("counts")},
      "mc":{"current_core_count":core.get("current_core_count"),"unresolved_count":mc.get("unresolved_count"),"definitive_fail_count":mc.get("definitive_fail_count")},
      "stage1":{"weekly_pass_count":st1.get("weekly_pass_count"),"unknown_count":st1.get("unknown_count")},
      "regime":{"regime":rg.get("regime"),"breadth_missing_count":rg.get("breadth_missing_count"),"breadth_above_sma50_pct":rg.get("breadth_above_sma50_pct"),"nh20":rg.get("nh20"),"nl20":rg.get("nl20")},
      "deep_geometry":{
        "a_geometry_count":deep.get("a_geometry_count"),
        "b_breakout_count":deep.get("b_breakout_count"),
        "b_armed_count":deep.get("b_armed_count"),
        "d_geometry_count":deep.get("d_geometry_rs_count"),
        "unknown_history_count":deep.get("unknown_history_count"),
        "event_and_regime_finalist_authority":"DEFERRED_TO_CANONICAL_CHAIN"
      },
      "final_tech":{"status":"DEFERRED_TO_CANONICAL_FINAL_FACTORY","pre_g9_tech_pass":[]},
      "coverage_faults":coverage_faults,
      "g9_status":"BLOCKED",
      "account_gate":"UNKNOWN_NOT_CONFIGURED",
      "full_go_blockers":blockers,
      "authority":"EXTERNAL_AUTONOMOUS_SUPPORT_DATA_PLANE_ONLY; CANONICAL_CANDIDATE_AUTHORITY_UNCHANGED"
    }
    STATE.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("XRAY_ORCHESTRATOR="+status)
    print(json.dumps({"asof":out["asof_et"],"core":core.get("current_core_count"),
                      "weekly":st1.get("weekly_pass_count"),"regime":rg.get("regime"),
                      "coverage_faults":coverage_faults},sort_keys=True))

if __name__=="__main__":
    main()
