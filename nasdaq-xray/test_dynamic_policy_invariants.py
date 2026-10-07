#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, pathlib, sys

ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

from price_dv30_phase import classify as price_classify
from price_dv30_recover_from_fullstate import apply_terminal_overrides
from resolve_unknowns_fallback import classify as resolver_classify
from deep_pre_r1_shadow import family_b
from build_current_terminal import mc_semantic_input_match, candidate_local_research_ready
from build_current_master_manifest import valid_full_identity_authority
import history_phase as history_mod
from history_phase import official_listing_upper_bound_fail, continuity_composite_pass
import pandas as pd

def load_sina():
    spec=importlib.util.spec_from_file_location("sina_stage_test",ROOT/"sina_stage.py")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def bars(dates, price=100.0, volume=1_000_000.0):
    return {d:(price,volume) for d in dates}

def main():
    exp=[f"2026-09-{d:02d}" for d in range(1,31)]
    # The functions only need a stable ordered set of expected dates for this invariant test.
    exact=bars(exp)
    incomplete=bars(exp[:-1])
    low=bars(exp,price=20.0,volume=1_000_000.0)  # $20m/session => terminal DV30 fail

    st,info=price_classify(exact,exp[-1],exp,"TEST")
    assert st=="PASS_PRICE_DV30",(st,info)
    assert info["known_session_count"]==30 and info["missing_sessions"]==[]
    at_floor=bars(exp,price=5.0,volume=20_000_000.0)
    st,info=price_classify(at_floor,exp[-1],exp,"TEST")
    assert st=="PASS_PRICE_DV30",(st,info)
    below_floor=bars(exp,price=4.99,volume=20_000_000.0)
    st,info=price_classify(below_floor,exp[-1],exp,"TEST")
    assert st=="FAIL_PRICE",(st,info)

    st,info=price_classify(incomplete,exp[-1],exp,"TEST")
    assert st=="UNKNOWN",(st,info)
    assert info["reason"]=="ASOF_MISSING"  # exact ASOF itself missing

    # Missing a middle expected session while ASOF exists must never PASS.
    mid=bars([d for d in exp if d!=exp[9]])
    st,info=price_classify(mid,exp[-1],exp,"TEST")
    assert st!="PASS_PRICE_DV30",(st,info)
    assert st in {"UNKNOWN","FAIL_DV30"}

    st,info=price_classify(low,exp[-1],exp,"TEST")
    assert st=="FAIL_DV30",(st,info)

    sina_window=load_sina()
    assert sina_window.official_blank_checks_exclusion_authorized("Blank Checks",False,None) is True
    assert sina_window.official_blank_checks_exclusion_authorized("Blank Checks",True,None) is False
    _snap={"path":"nasdaq-xray/master_nasdaq_directory_snapshot_20261006.json","blob_sha":"abc123"}
    assert sina_window.official_blank_checks_exclusion_authorized("Blank Checks",True,_snap) is True
    assert sina_window.official_blank_checks_exclusion_authorized("Technology",True,_snap) is False
    _,completed30=sina_window.completed_sessions()
    assert len(completed30)==30,len(completed30)
    assert valid_full_identity_authority({"full_identity":True,"authority":"FULL_IDENTITY_NO_PREFILTER"}) is True
    assert valid_full_identity_authority({"full_identity":True,"authority":"CANONICAL_FROZEN_FULL_IDENTITY_SAME_ASOF"}) is True
    assert valid_full_identity_authority({"full_identity":True,"authority":"DISCOVERY_PREFILTER_ONLY_NOT_CANONICAL_MC"}) is False

    # Operator resolver evidence may terminally resolve only an existing block,
    # never manufacture PASS or rewrite a non-blocked row.
    base={"NEW":{
      "decision":"BLOCK_CURRENT_RUN","reason":"INSUFFICIENT_30_USABLE_DV30_SESSIONS_CONFIRMED",
      "source":"RALLIES_CANDLESTICK_SCANNER_EXACT30_PRIMARY","proof":"FAIL_CLOSED_CURRENT_RUN_NONPASS"
    }}
    ov={"NEW":{
      "decision":"FAIL_DV30_INSUFFICIENT_SESSIONS","price":20.0,
      "known_session_count":3,"missing_sessions":exp[:-3],
      "no_synthetic_bar":True,"proof":"ALPACA_RALLIES_EXACT_MISSING_SET_MATCH"
    }}
    resolved=apply_terminal_overrides({k:dict(v) for k,v in base.items()},ov)
    assert resolved["NEW"]["decision"]=="FAIL_DV30_INSUFFICIENT_SESSIONS",resolved
    try:
        apply_terminal_overrides({"NEW":dict(base["NEW"])},{"NEW":{"decision":"PASS_PRICE_DV30"}})
        raise AssertionError("terminal override manufactured PASS")
    except ValueError:
        pass
    try:
        apply_terminal_overrides({"NEW":{"decision":"FAIL_PRICE","price":4.99,"source":"X","proof":"X"}},ov)
        raise AssertionError("terminal override rewrote non-blocked row")
    except ValueError:
        pass

    history_prefix={f"H{i:03d}":(100.0,1_000_000.0) for i in range(260)}
    rich_exact={**history_prefix,**exact}
    rich_mid={**history_prefix,**mid}
    st,info=resolver_classify(rich_exact,exp[-1],exp,"TEST")
    assert st=="PASS_HARD_GATES",(st,info)
    assert info["known_session_count"]==30 and info["missing_sessions"]==[]

    st,info=resolver_classify(rich_mid,exp[-1],exp,"TEST")
    assert st!="PASS_HARD_GATES",(st,info)

    sina=load_sina()
    bad_overlay={
      "decision":"PASS_HARD_GATES","price":100.0,"bars":300,
      "dv30_lower_bound":100_000_000.0,"dv30_upper_bound":100_000_000.0,
      "known_session_count":29,"missing_sessions":[exp[9]],
      "no_synthetic_bar":True,"source":"TEST","proof":"BOUND"
    }
    st,info=sina.resolution_result("ZZZZ",bad_overlay,exp)
    assert st=="UNKNOWN_STATIC",(st,info)

    good_overlay={
      "decision":"PASS_HARD_GATES","price":100.0,"bars":300,
      "dv30_lower_bound":100_000_000.0,"dv30_upper_bound":100_000_000.0,
      "known_session_count":30,"missing_sessions":[],
      "no_synthetic_bar":True,"source":"TEST","proof":"EXACT30_MEDIAN"
    }
    st,info=sina.resolution_result("ZZZZ",good_overlay,exp)
    assert st=="PASS",(st,info)
    assert info["known_session_count"]==30 and info["missing_sessions"]==[]

    from price_dv30_recover_from_fullstate import valid_bridge_price_resolution
    assert valid_bridge_price_resolution({
      "decision":"PASS_PRICE_DV30","price":100.0,"dv30":100_000_000.0,
      "known_session_count":30,"missing_sessions":[],"no_synthetic_bar":True,
      "source":"RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9","proof":"EXACT30_MEDIAN_GE_GATE"
    },"2026-10-05") is True
    assert valid_bridge_price_resolution({
      "decision":"PASS_PRICE_DV30","price":100.0,"dv30":100_000_000.0,
      "known_session_count":30,"missing_sessions":[],"no_synthetic_bar":True,
      "source":"ALPACA_HISTORICAL_SIP_DAILY_BATCH_NON_G9","proof":"EXACT30_MEDIAN_GE_GATE"
    },"2026-10-05") is False
    assert valid_bridge_price_resolution({
      "decision":"PASS_PRICE_DV30","price":100.0,"dv30":100_000_000.0,
      "known_session_count":20,"missing_sessions":[],"no_synthetic_bar":True,
      "source":"RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9","proof":"EXACT30_MEDIAN_GE_GATE"
    },"2026-10-05") is False
    assert valid_bridge_price_resolution({
      "decision":"FAIL_DV30_INSUFFICIENT_SESSIONS","price":20.0,
      "known_session_count":29,"missing_sessions":["2026-09-01"],
      "no_synthetic_bar":True,"source":"TEST","proof":"ALPACA_RALLIES_EXACT_MISSING_SET_MATCH"
    },"2026-10-05") is True

    # Setup-B regression: breakout pivot MUST come from the completed base and
    # exclude the current breakout bar. Including the current bar makes the
    # breakout inequality self-containing/unsatisfiable (a bug class observed
    # in an external Donchian implementation).
    rows=[]
    for i in range(60):
        if i < 39:
            o=100.0; h=102.0; l=98.0; close=100.0; vol=1_000_000.0
        elif i < 59:
            o=100.0; h=100.5; l=99.5; close=100.0; vol=1_000_000.0
        else:
            o=101.0; h=150.0; l=100.8; close=102.0; vol=3_000_000.0
        rows.append({"date":pd.Timestamp("2026-01-01")+pd.Timedelta(days=i),
                     "open":o,"high":h,"low":l,"close":close,"volume":vol})
    b=family_b(pd.DataFrame(rows))
    assert b and b["pool"] is True,b
    assert abs(float(b["P"])-100.5)<1e-9,b
    assert b["breakout_confirmed"] is True,b


    # MC semantic rebind regression: byte-level metadata drift may rebind only
    # when pass_hash, exact pass set, and pass_count all match. Count equality alone
    # must never substitute for set equality.
    price_sem={"pass_hash":"H","pass_count":2,"pass_symbols":["AAA","BBB"]}
    bridge_good={"input_pass_hash":"H","input_count":2,"results":{"AAA":{},"BBB":{}}}
    assert mc_semantic_input_match(price_sem,bridge_good) is True
    assert mc_semantic_input_match(price_sem,{"input_pass_hash":"H","input_count":2,"results":{"AAA":{},"CCC":{}}}) is False
    assert mc_semantic_input_match(price_sem,{"input_pass_hash":"X","input_count":2,"results":{"AAA":{},"BBB":{}}}) is False
    assert mc_semantic_input_match(price_sem,{"input_pass_hash":"H","input_count":1,"results":{"AAA":{},"BBB":{}}}) is False

    # Candidate-local research delivery must not depend on unrelated global
    # coverage completeness. It still fails closed on official safety and semantic
    # conformance, and cannot create a candidate from an empty PRE_G9 set.
    ft_ok={
      "policy_semantics_exact":True,
      "lifecycle_semantics_exact":True,
      "candidate_legal_guard_exact_binding":True,
      "results":{"AAA":{"candidate_legal_review_status":"PASS"}},
    }
    assert candidate_local_research_ready({"AAA"},{"status":"PASS"},ft_ok,True) is True
    assert candidate_local_research_ready(set(),{"status":"PASS"},ft_ok,True) is False
    assert candidate_local_research_ready({"AAA"},{"status":"UNKNOWN"},ft_ok,True) is False
    assert candidate_local_research_ready({"AAA"},{"status":"PASS"},{**ft_ok,"policy_semantics_exact":False},True) is False
    assert candidate_local_research_ready({"AAA"},{"status":"PASS"},ft_ok,False) is False
    assert candidate_local_research_ready({"AAA"},{"status":"PASS"},{**ft_ok,"lifecycle_semantics_exact":False},True) is False
    assert candidate_local_research_ready({"AAA"},{"status":"PASS"},{**ft_ok,"candidate_legal_guard_exact_binding":False},True) is False

    # PRICE BLOCK_CURRENT_RUN has not proven PASS or a policy-authorized
    # terminal FAIL. UNKNOWN!=PASS and full-E2E/no-signal claims require
    # complete hard-gate coverage, so unresolved blocks must stop FULL_E2E.
    terminal_src=(ROOT/"build_current_terminal.py").read_text()
    blocker_body=terminal_src.split("blockers={",1)[1].split("full=all",1)[0]
    assert '"price_blocked_current_run":price_blocked_count' in blocker_body,blocker_body
    assert '"price_blocked_requires_terminal_resolution":True' in terminal_src
    assert candidate_local_research_ready({"AAA"},{"status":"PASS"},{**ft_ok,"results":{"AAA":{"candidate_legal_review_status":"UNKNOWN"}}},True) is False

    # HISTORY evidence regression: official listing-date evidence can only
    # produce a terminal upper-bound FAIL; it must never manufacture PASS.
    hf=official_listing_upper_bound_fail("HONA","2026-10-02")
    assert hf and hf["proof"]=="OFFICIAL_LISTING_DATE_HISTORY_UPPER_BOUND",hf
    assert hf["max_possible_daily_bars"]<260 or hf["max_possible_completed_weeks"]<52,hf

    # Completed-week counting must use the official Nasdaq calendar. Thursday
    # 2026-10-01 is not a completed week; Friday 2026-10-02 is. The following
    # Monday must not increment the count again until that new week completes.
    cal=history_mod.mcal.get_calendar("NASDAQ")
    sched=cal.schedule(start_date="2025-08-01",end_date="2026-10-05")
    ds=[idx.date().isoformat() for idx,_ in sched.iterrows()]
    by={d:(100.0,1_000_000.0) for d in ds}
    w_thu=history_mod.week_count({d:v for d,v in by.items() if d<="2026-10-01"},"2026-10-01")
    w_fri=history_mod.week_count({d:v for d,v in by.items() if d<="2026-10-02"},"2026-10-02")
    w_mon=history_mod.week_count({d:v for d,v in by.items() if d<="2026-10-05"},"2026-10-05")
    assert w_fri==w_thu+1,(w_thu,w_fri,w_mon)
    assert w_mon==w_fri,(w_thu,w_fri,w_mon)

    # Ticker-continuity composite regression: same unchanged-CUSIP security
    # may use predecessor history only when a long-history source and exact-ASOF
    # source overlap closely on >=20 sessions.
    ydates=[d.strftime("%Y-%m-%d") for d in pd.bdate_range("2025-01-02","2026-10-01")]
    sdates=[d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-15","2026-10-02")]
    yb={d:(20.0,1_000_000.0) for d in ydates}
    sb={d:(20.0,1_000_000.0) for d in sdates}
    comp=continuity_composite_pass("DFTX","2026-10-02",sb,{},yb,{})
    assert comp and comp["proof"]=="UNCHANGED_CUSIP_PLUS_CROSS_SOURCE_OVERLAP",comp
    assert comp["daily_bars"]>=260 and comp["completed_week_count"]>=52,comp
    bad_sb=dict(sb)
    for d in list(bad_sb)[-30:]:
        bad_sb[d]=(30.0,1_000_000.0)
    assert continuity_composite_pass("DFTX","2026-10-02",bad_sb,{},yb,{}) is None

    # Legacy evidence bridge must never resurrect a ticker-lineage PASS if the
    # stricter live composite check fails.
    old_bridge=history_mod.HISTORY_BRIDGE
    try:
        history_mod.HISTORY_BRIDGE={"DFTX":{
          "mode":"TICKER_LINEAGE_HISTORY_PASS_V1","outcome":"PASS_HISTORY",
          "current_ticker":"DFTX","current_has_exact_asof_bar":True,
          "combined_unique_daily_bars":999,"combined_completed_week_count":200,
          "official_continuity_source":"https://www.nasdaq.com/example",
          "predecessor_ticker":"MNMD","ticker_change_effective_date":"2026-01-15"
        }}
        assert history_mod.bridge_resolution("DFTX","2026-10-02") is None
    finally:
        history_mod.HISTORY_BRIDGE=old_bridge

    # Canonical universe is operating common equity. C4.17 accepts official,
    # issuer, or SEC shell proof. Exact same-ASOF Nasdaq screener industry
    # "Blank Checks" is deterministic official exclusion evidence. A name-only
    # SPAC suspicion without official/issuer/SEC classification remains
    # UNKNOWN_IDENTITY and must never enter PRICE/DV30/MC.
    sina_src=(ROOT/"sina_stage.py").read_text()
    master_src=(ROOT/"build_current_master_manifest.py").read_text()
    resolver_src=(ROOT/"build_current_resolver_request.py").read_text()
    terminal_src=(ROOT/"build_current_terminal.py").read_text()
    pre_mc_src=(ROOT.parent/".github/workflows/xray-canonical-current-pre-mc.yml").read_text()
    assert 'IDENTITY_RULESET="V6_ASOF_IDENTITY_AND_SPAC_PROOF_AT_MASTER"' in sina_src,sina_src
    assert 'IDENTITY_PARTITION_POLICY="MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD"' in sina_src,sina_src
    identity_proof_src=(ROOT/"build_current_identity_proofs.py").read_text()
    assert 'IDENTITY_DISCOVERY_VERSION="SEC_CURRENT_SUSPECT_DISCOVERY_V3"' in identity_proof_src,identity_proof_src
    assert 'def sec_ticker_cik_map()' in identity_proof_src and 'def sec_current_classification(' in identity_proof_src,identity_proof_src
    assert 'SAME_RUN_SEC_CURRENT_NON_BLANK_CHECK_DISCOVERY' in identity_proof_src,identity_proof_src
    assert 'asof_discovery_version!="SEC_CURRENT_SUSPECT_DISCOVERY_V3"' in pre_mc_src,pre_mc_src
    assert '"reason":"SPAC_BLANK_CHECK"' in sina_src,sina_src
    assert '"NASDAQ_EXACT_ASOF_FROZEN_SCREENER_INDUSTRY"' in sina_src,sina_src
    assert 'official_blank_checks_exclusion_authorized(' in sina_src,sina_src
    assert '"reason":"SPAC_NAME_SUSPECT_OFFICIAL_CLASSIFICATION_UNRESOLVED"' in sina_src,sina_src
    assert '"official_blank_checks_excluded_count"' in sina_src and '"official_blank_checks_excluded_hash"' in sina_src,sina_src
    assert 'identity_unknown_symbols' in sina_src and 'unknown_never_pass' in sina_src,sina_src
    assert 'st.get("identity_partition_policy")!=IDENTITY_PARTITION_POLICY' in sina_src,sina_src
    assert 'mf_cp.get("identity_unknown_partition_exact") is not True' in sina_src,sina_src
    assert 'if sym in operating_overrides:' in sina_src and 'bool(SPAC_SUSPECT.search(security_name)) and sym not in sec_spac_proof' in sina_src,sina_src
    assert 'identity_unknown_partition_exact' in master_src and '"UNKNOWN_IDENTITY"' in master_src,master_src
    assert '"PARTIAL_UNKNOWN"' in master_src and '"raw_identity_total"' in master_src,master_src
    assert 'union=sorted(set(price_symbols)|set(blocked_symbols))' in resolver_src,resolver_src
    assert 'not (set(master_symbols)&set(s["queue"]))' in resolver_src,resolver_src
    assert 'm["status"] in {"HISTORY_COMPLETE","PARTIAL_UNKNOWN"}' in terminal_src,terminal_src
    assert '"master_unknown":int(m["unknown_count"])' in terminal_src,terminal_src
    assert 'master_complete":master_unknown_count==0' in terminal_src,terminal_src
    assert 'REPLAY_COMPLETED_EPOCH_UNDER_CURRENT_IDENTITY_POLICY_V6' in pre_mc_src,pre_mc_src
    assert 'sec_spac_proof_path(asof)' in sina_src and 'asof_identity_proof_path(asof)' in sina_src,sina_src
    assert 'ASOF_IDENTITY_PROOF=ROOT/"master_asof_identity_proof_20261005.json"' not in sina_src,sina_src
    assert '"POST_ASOF_LISTING"' in master_src,master_src
    assert 'asof_identity_proof_binding' in master_src and 'sec_spac_proof_binding' in master_src,master_src

    # Replay guard must be bound to the current C4.17 DV30 artifact and must
    # inspect the durable pointer's nested ASOF. A stale pointer can never be
    # hidden by a missing top-level asof_et field.
    replay_src=(ROOT/"deterministic_replay_guard.py").read_text()
    assert 'PRICE_FILE="canonical_current_price_dv30.json"' in replay_src,replay_src
    assert 'canonical_current_price_dv20.json' not in replay_src,replay_src
    assert 'if fn==POINTER_FILE:' in replay_src and 's.get("asof_et")' in replay_src,replay_src
    assert '"status":"PASS" if all_present and asof_consistent and policy_ok else "FAIL_CLOSED"' in replay_src,replay_src

    print({"status":"PASS","invariants":[
        "EXACT30_REQUIRED_FOR_PASS","INCOMPLETE_NEVER_PASS","BLOCKED_TERMINAL_OVERRIDE_FAIL_ONLY",
        "OVERLAY_EXACT30_REQUIRED","SETUP_B_PIVOT_EXCLUDES_CURRENT_BAR",
        "MC_SEMANTIC_REBIND_REQUIRES_HASH_SET_COUNT",
        "CANDIDATE_LOCAL_RESEARCH_INDEPENDENT_GLOBAL_COVERAGE_FAIL_CLOSED",
        "OFFICIAL_LISTING_HISTORY_FAIL_ONLY","CUSIP_CONTINUITY_REQUIRES_CROSS_SOURCE_OVERLAP",
        "LEGACY_LINEAGE_BRIDGE_CANNOT_BYPASS_COMPOSITE","REPLAY_GUARD_DV30_AND_NESTED_POINTER_ASOF_FAIL_CLOSED","SPAC_EXACT_SEC_EXCLUSION_OR_MASTER_UNKNOWN","SEC_SIC_6770_EXACT_ASOF_ONLY_EXCLUSION","MASTER_UNKNOWN_NEVER_ENTERS_PRICE","EXACT_ASOF_IDENTITY_ROLLBACK_AND_OPERATING_OVERRIDE"
    ]})

if __name__=="__main__":
    main()
