#!/usr/bin/env python3
"""Read-only C4.17 / manual-research end-to-end production readiness witness.

Outputs *blocked states*, never prices, tickers, trade instructions or signals.
A green CI job running this script is NOT a production-ready claim.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
POLICY="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"

def read(name):
    p=ROOT/name
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError,OSError): return {}

def sha(name):
    try:
        b=(ROOT/name).read_bytes()
        return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
    except OSError:
        return None

def mc_exact(mc,price,price_sha):
    """Verify the exact MC partition, not merely deduplicated set counts."""
    if not isinstance(mc,dict) or not isinstance(price,dict):
        return False
    def exact_symbols(values):
        return (type(values) is list
                and all(type(sym) is str and sym and sym==sym.strip()
                        for sym in values)
                and len(values)==len(set(values)))
    price_raw=price.get("pass_symbols")
    input_raw=mc.get("input_pass_symbols")
    results=mc.get("results")
    if (not exact_symbols(price_raw) or not exact_symbols(input_raw)
            or not isinstance(results,dict)
            or any(not isinstance(v,dict) for v in results.values())):
        return False
    first=mc.get("fallback_fail_symbols",[])
    second=mc.get("fallback_two_source_fail_symbols",[])
    if not exact_symbols(first) or not exact_symbols(second):
        return False
    # Native bridges may include BOTH old/new fallback-fail aliases.
    # A contradictory copy cannot be ignored by selecting the first key.
    if ("fallback_fail_symbols" in mc
            and "fallback_two_source_fail_symbols" in mc
            and set(first)!=set(second)):
        return False
    fail_raw=first if "fallback_fail_symbols" in mc else second
    raw_groups={
       "MC_PASS_PRIMARY":mc.get("primary_pass_symbols",[]),
       "MC_FAIL_PRIMARY":mc.get("primary_fail_symbols",[]),
       "MC_PASS_FALLBACK_WATCH":mc.get("fallback_watch_symbols",[]),
       "MC_FAIL_FALLBACK_TWO_SOURCE":fail_raw,
       "MC_UNKNOWN":mc.get("unknown_symbols",[])}
    if any(not exact_symbols(raw) for raw in raw_groups.values()):
        return False
    symbols=set(price_raw)
    statuses={group:set(raw) for group,raw in raw_groups.items()}
    if not (mc.get("asof_et")==price.get("asof_et")
            and mc.get("input_blob_sha")==price_sha
            and mc.get("input_pass_hash")==price.get("pass_hash")
            and mc.get("policy_hash")==POLICY
            and mc.get("execution")=="NONE" and mc.get("real_money")=="NO-GO"
            and mc.get("unknown_never_pass") is True
            and set(input_raw)==symbols
            and len(input_raw)==len(symbols)
            and set(results)==symbols):
        return False
    seen=set()
    for group, group_symbols in statuses.items():
        if seen & group_symbols:return False
        seen |= group_symbols
        if any((results[s] or {}).get("status") != group for s in group_symbols):
            return False
    counts=mc.get("counts")
    if not isinstance(counts,dict):return False
    if any(type(counts.get(k)) is not int or counts[k]!=len(v)
           for k,v in raw_groups.items()):
        return False
    # TOTAL is optional in early source schemas, but must be an exact
    # integer equal to the authoritative PRICE PASS scope when present.
    if ("TOTAL" in counts
            and (type(counts["TOTAL"]) is not int or counts["TOTAL"]!=len(symbols))):
        return False
    # Independent row-level semantics: a primary label and exact symbol-set
    # equality cannot substitute for an XNAS issuer or C4.17 USD cap value.
    # The only currently defined primary MC row schema is BIGDATA exact XNAS;
    # a successor must have a separately reviewed primary contract, not WATCH.
    for sym in statuses["MC_PASS_PRIMARY"] | statuses["MC_FAIL_PRIMARY"]:
        row=mc["results"].get(sym) or {}
        amount=row.get("market_cap_usd")
        if (row.get("mode")!="BIGDATA_EXACT_XNAS_COMPANY_PUBLIC_USD"
                or row.get("listing")!="XNAS:"+sym
                or not isinstance(row.get("bigdata_entity_id"),str)
                or not row["bigdata_entity_id"].strip()
                or type(amount) not in (int,float)
                or not math.isfinite(amount)
                or amount<0):
            return False
        if (sym in statuses["MC_PASS_PRIMARY"]) != (amount>=2_000_000_000):
            return False
    # WATCH is an admissible observation class only with an EXPLICIT R92 veto.
    # The native historical MC_FAIL_PRIMARY / MC_FAIL_FALLBACK / MC_UNKNOWN
    # schemas, by contrast, express their veto by the negative status itself;
    # they have no per-row r92_eligible property. Never turn these into PASS.
    for sym in statuses["MC_PASS_FALLBACK_WATCH"]:
        if (mc["results"].get(sym) or {}).get("r92_eligible") is not False:
            return False
    for group in ("MC_FAIL_PRIMARY","MC_FAIL_FALLBACK_TWO_SOURCE","MC_UNKNOWN"):
        for sym in statuses[group]:
            row=mc["results"].get(sym) or {}
            # If supplied, the eligibility bit must explicitly be False:
            # True, strings, numbers, or null contradict native negative rows.
            if "r92_eligible" in row and row["r92_eligible"] is not False:
                return False
    return seen==symbols

def terminal_bound_mc_selection(valid_bridge_names,terminal,asof,blob_sha):
    """Select ONLY the exact terminal-attested Git blob from source-validated MC.

    Historical version files may coexist. No filename sorting, newest-wins
    selection, fabricated PRIMARY, or unbound fallback is allowed.
    A separate terminal_chain_exact() checks every other upstream source SHA.
    """
    if (not isinstance(valid_bridge_names,list)
            or not valid_bridge_names
            or not all(isinstance(x,str) for x in valid_bridge_names)
            or len(valid_bridge_names)!=len(set(valid_bridge_names))
            or not isinstance(terminal,dict)
            or not isinstance(asof,str)
            or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",asof)):
        return None
    evidence=terminal.get("evidence")
    if not isinstance(evidence,dict):return None
    binding=evidence.get("mc")
    if not isinstance(binding,dict):return None
    path=binding.get("path")
    blob=binding.get("blob_sha")
    if not isinstance(path,str) or not isinstance(blob,str):return None
    prefix="canonical_mc_bridge_"+asof.replace("-","")+"_c417_dv30_v"
    if not path.startswith("nasdaq-xray/"):return None
    name=path[len("nasdaq-xray/"):]
    if not (name.startswith(prefix)
            and name.endswith(".json")
            and re.fullmatch(r"[1-9][0-9]*",name[len(prefix):-5])
            and name in valid_bridge_names
            and re.fullmatch(r"[0-9a-f]{40}",blob)):
        return None
    # Git readback: the terminal must bind the precise bytes on disk.
    # A matching same-day filename without its SHA never creates authority.
    actual=blob_sha(name)
    return name if actual is not None and actual==blob else None

def terminal_research_seal(terminal):
    """Full-universe success OR independently attested candidate-local success.

    Candidate-local mode still requires every semantic, risk, legal, lifecycle
    and source-binding control; neither mode implies trade or phone receipt.
    """
    checks=terminal.get("checks") or {}
    local=(terminal.get("candidate_local_research_pass") is True
           and (terminal.get("candidate_delivery_safety") or {}).get("status")=="PASS"
           and all(checks.get(key) is True for key in REQUIRED_LOCAL_CHECKS))
    return terminal.get("full_end_to_end_research_pass") is True or local

def terminal_chain_exact(terminal, asof, source_shas, mc_name, mc_sha):
    """Full terminal is current ONLY with every upstream Git blob bound."""
    ev=terminal.get("evidence") or {}
    checks=terminal.get("checks") or {}
    names=("master","price","history","events","final")
    # Two distinct, equally strict provenance modes:
    # FULL_E2E requires complete universe; candidate-local may remain valid
    # with unrelated global UNKNOWN, but only after its exact C4.17, legal,
    # lifecycle, safety and AL semantics checks all PASS independently.
    full_or_local=terminal_research_seal(terminal)
    if not (
        terminal.get("asof_et")==asof
        and terminal.get("compiled_policy_hash")==POLICY
        and full_or_local
        and checks.get("exact_blob_provenance_chain") is True
        and checks.get("semantic_provenance_chain_exact") is True
        and isinstance(mc_name,str)
        and mc_name.startswith("canonical_mc_bridge_")
        and (ev.get("mc") or {}).get("path")=="nasdaq-xray/"+mc_name
        and (ev.get("mc") or {}).get("blob_sha")==mc_sha
        and all((ev.get(k) or {}).get("blob_sha")==source_shas.get(k)
                and source_shas.get(k) is not None for k in names)
    ):
        return False
    return True

def non_g9_price_pass_count(price):
    """Never let explicitly NON_G9 PRICE-pass sources imply release authority.

    No third-party license can be inferred from a missing tag or source name:
    this is a necessary exclusion only, not a sufficient entitlement proof.
    """
    if not isinstance(price,dict):
        return None
    rows=price.get("results")
    symbols=price.get("pass_symbols")
    if (not isinstance(rows,dict) or not isinstance(symbols,list)
        or not all(isinstance(sym,str) and sym for sym in symbols)
        or len(set(symbols))!=len(symbols)):
        return None
    total=0
    for sym in symbols:
        row=rows.get(sym)
        if not isinstance(row,dict) or row.get("status")!="PASS_PRICE_DV30":
            return None
        info=row.get("info")
        source=info.get("source") if isinstance(info,dict) else None
        if not isinstance(source,str) or not source:
            return None
        if "NON_G9" in source.upper():
            total+=1
    return total

def manual_delayed_eod_source_contract(price, manual_policy):
    """Historical non-G9 data may be *inspected* in manual-only research.

    Strict G9 remains BLOCKED. This helper grants NO registered candidate,
    delivery, live quote, market-cap measurement, or trade authority. The
    independent full MC/HISTORY/FINAL source chain is still mandatory.
    """
    if not isinstance(manual_policy,dict) or not isinstance(price,dict):
        return False
    g9=manual_policy.get("g9") or {}
    delivery=manual_policy.get("delivery") or {}
    h=manual_policy.get("hard_gates") or {}
    if not (
        manual_policy.get("schema")=="XRAY_MANUAL_DECISION_RESEARCH_MODE_V1"
        and manual_policy.get("mode")=="RESEARCH_ONLY_MANUAL_DECISION"
        and manual_policy.get("status")=="PARALLEL_SHADOW_UNTIL_VERIFIED"
        and manual_policy.get("parent_policy_version")=="C4.17"
        and manual_policy.get("execution")=="NONE"
        and manual_policy.get("real_money")=="NO-GO"
        and manual_policy.get("unknown_never_pass") is True
        and manual_policy.get("alpha_thresholds_unchanged") is True
        and manual_policy.get("broker_trade_access_allowed") is False
        and g9.get("mandatory_for_research_signal") is False
        and g9.get("never_claim_g9_pass_unless_existing_gate_pass") is True
        and delivery.get("enabled_in_this_shadow") is False
        and delivery.get("quotes_must_disclose_asof_and_data_delay") is True
        and h.get("price_min_usd")==5
        and h.get("dv30_min_usd")==50000000
        and h.get("mc_min_usd")==2000000000
        and h.get("history_min_daily_bars")==260
        and h.get("mc_fallback_watch_cannot_promote") is True
    ):
        return False
    symbols=price.get("pass_symbols")
    n=non_g9_price_pass_count(price)
    return bool(type(symbols) is list and symbols
                and type(n) is int and n==len(symbols)
                and price.get("execution")=="NONE"
                and price.get("real_money")=="NO-GO"
                and price.get("unknown_never_pass") is True
                and price.get("unknown_count")==0)

def scope_readiness(blockers,chain_exact):
    """Distinguish global universe completion from exact candidate-local lineage.

    This function never vets a particular setup or acknowledges an iPhone
    notification; neither can be inferred from symbol counts or workflow PASS.
    """
    local_hard={
        "SOURCE_EPOCH_NOT_LATEST_COMPLETED_SESSION",
        "POLICY_SAFETY_NOT_ALL_ATTESTED",
        "PRICE_PARTITION_NOT_EXACT_CURRENT",
        "PRICE_PASS_NON_G9_SOURCE_NOT_RELEASE_AUTHORITY",
        "SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT",
        "CURRENT_MC_AUTHORITY_MISSING",
        "CURRENT_TERMINAL_FROZEN_OR_INCOMPLETE",
        "TERMINAL_CURRENT_MC_CHAIN_NOT_PROVEN",
    }
    global_only={"IDENTITY_PARTITION_INCOMPLETE","PRICE_BLOCKED_30_SESSION_BARS","PRICE_UNKNOWN_CURRENT"}
    blocks=set(blockers)
    local=bool(chain_exact) and blocks.isdisjoint(local_hard)
    return {
        "candidate_local_source_chain_attested":local,
        "full_universe_source_coverage_attested":local and blocks.isdisjoint(global_only),
        "candidate_local_al_setup_attested":False,
        "actual_device_delivery_receipt_attested":False,
    }

TASK_ID="6a825366222081918997094d76e6ae46"
# Exact family-specific C4.17 source-of-truth values, matching the compiled
# policy, manual_decision_policy_v1.json and final_tech_shadow.py.
REGISTERED_RR_MIN_BY_FAMILY={
    "A":(1.5,1.1), "B":(2.0,1.5), "C":(2.0,1.5), "D":(2.0,1.5),
}
REQUIRED_REGISTERED_FIELDS=(
    "delivery_key","symbol","setup","asof_et","entry_low","entry_high",
    "chase_limit","stop","r1","rr_basic","rr_severe","dv30",
    "regime","event_status","mc_class","mc_source","liquidity","pass_reason",
    "g9_status","account_status","registered_at_utc","execution","real_money"
)
REQUIRED_LOCAL_CHECKS=(
    "candidate_local_research_pass","alpha_semantic_conformance_exact",
    "alpha_source_binding_exact","lifecycle_frozen_semantics_exact",
    "candidate_legal_guard_exact_binding","all_finalists_detailed_legal_review_exact",
    "mc_exact_price_pass_set","semantic_provenance_chain_exact"
)

def registered_research_candidate_exact(terminal,pointer,asof,terminal_sha):
    """A positive *preparation* witness; actual delivery requires delivery_prepare.

    No user notification/phone receipt/trading action is inferred from this.
    All candidate fields, exact pointer and terminal registration must agree.
    """
    if not (terminal.get("asof_et")==asof
            and terminal.get("candidate_local_research_pass") is True
            and (terminal.get("candidate_delivery_safety") or {}).get("status")=="PASS"
            and all((terminal.get("checks") or {}).get(x) is True for x in REQUIRED_LOCAL_CHECKS)
            and pointer.get("schema")=="XRAY_GITHUB_DURABLE_STATE_V3"
            and pointer.get("authority")=="GITHUB_CURRENT_POINTER"
            and pointer.get("execution")=="NONE" and pointer.get("real_money")=="NO-GO"):
        return False
    state=pointer.get("state_json")
    if isinstance(state,str):
        try: state=json.loads(state)
        except (ValueError,TypeError):return False
    if not isinstance(state,dict):
        return False
    if not (state.get("task_id")==TASK_ID
            and state.get("asof_et")==asof
            and (state.get("deep_final_evidence") or {}).get("terminal_path")
                =="nasdaq-xray/canonical_current_terminal.json"
            and (state.get("deep_final_evidence") or {}).get("terminal_blob_sha")==terminal_sha):
        return False
    keys=state.get("delivery_keys") or []
    rows=state.get("r92") or []
    terminal_keys=terminal.get("r92_candidates") or []
    pre_keys=(terminal.get("sets") or {}).get("pre_g9_tech_pass") or []
    if not (isinstance(keys,list) and isinstance(rows,list)
            and isinstance(terminal_keys,list) and isinstance(pre_keys,list)
            and 1<=len(rows)<=3 and len(set(keys))==len(keys)
            and set(terminal_keys)==set(pre_keys)
            and bool(terminal_keys)):
        return False
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or row.get("schema")!="XRAY_RESEARCH_CANDIDATE_R92_V1":
            return False
        if any(row.get(k) is None for k in REQUIRED_REGISTERED_FIELDS):
            return False
        nums=("entry_low","entry_high","chase_limit","stop",
              "r1","rr_basic","rr_severe","dv30")
        if any(isinstance(row.get(n),bool) or not isinstance(row.get(n),(int,float))
               or not math.isfinite(row[n]) for n in nums):
            return False
        # C4.17 has family-specific RR. Do not impose B/C/D on family A.
        family=str(row.get("setup") or "").upper()
        rr_min=REGISTERED_RR_MIN_BY_FAMILY.get(family)
        if rr_min is None:
            return False
        if not (0 < row["stop"] < row["entry_low"] <= row["entry_high"]
                <= row["chase_limit"] < row["r1"]
                and row["dv30"]>=50_000_000
                and row["rr_basic"]>=rr_min[0] and row["rr_severe"]>=rr_min[1]):
            return False
        # Independent necessary R92 bounds: final_tech uses entry_model =
        # entry_high, and both RR scenarios deduct nonnegative trading costs.
        # Neither reported RR can EXCEED its zero-cost price-geometry maximum.
        # This never asserts exact ATR/cost correctness or creates alpha.
        hi=row["entry_high"]
        stop=row["stop"]
        r1=row["r1"]
        no_cost_rr_upper=(r1-hi)/(hi-stop)
        if ((hi-stop)/hi>0.08
            or row["rr_basic"]>no_cost_rr_upper+1e-10
            or row["rr_severe"]>no_cost_rr_upper+1e-10
            or row["rr_severe"]>row["rr_basic"]+1e-10):
            return False
        key=str(row.get("symbol") or "").upper()+"|"+str(row.get("setup") or "").upper()
        dkey=row.get("delivery_key")
        if (key not in terminal_keys or dkey not in keys or dkey in seen
            or row.get("asof_et")!=asof
            or row.get("mc_class")!="MC_PASS_PRIMARY"
            or row.get("execution")!="NONE" or row.get("real_money")!="NO-GO"):
            return False
        seen.add(dkey)
    return True

def snapshot():
    master=read("canonical_current_master_manifest.json")
    price=read("canonical_current_price_dv30.json")
    req=read("canonical_current_resolver_request.json")
    terminal=read("canonical_current_terminal.json")
    ledger=read("delivery_ledger.json")
    blocks=[]
    def fail(code,ok):
        if not ok:blocks.append(code)
    asof=master.get("asof_et")
    safety=(all(x.get("execution")=="NONE" and x.get("real_money")=="NO-GO"
                and x.get("unknown_never_pass") is True for x in (master,price,req,terminal)))
    fail("POLICY_SAFETY_NOT_ALL_ATTESTED",safety)
    # A perfectly internally consistent but 1-2-session-old chain is NOT
    # current GO. Use the independently tested official XNAS close + 30m
    # finality buffer, never calendar date or workflow success.
    freshness={"freshness_ready":False,"latest_completed_nasdaq_session":None,
               "session_lag":{"MASTER":None,"PRICE":None,"TERMINAL":None}}
    try:
        import datetime as _dt
        from source_epoch_freshness_guard import audit as _session_audit
        freshness=_session_audit(price,master,terminal,_dt.datetime.now(_dt.timezone.utc))
    except (ImportError,ValueError,TypeError,AttributeError,KeyError,OverflowError):
        # Missing library, unreliable clock, illegal source ASOF or safety
        # drift must NEVER become an implied same-session PASS.
        pass
    fail("SOURCE_EPOCH_NOT_LATEST_COMPLETED_SESSION",
         freshness.get("freshness_ready") is True)
    master_set=set(master.get("pass_symbols") or [])
    fail("IDENTITY_PARTITION_INCOMPLETE",master.get("unknown_count")==0
         and int(master.get("queue_total") or -1)==len(master_set))
    price_set=set(price.get("pass_symbols") or [])
    fail("PRICE_PARTITION_NOT_EXACT_CURRENT",bool(asof)
         and price.get("asof_et")==asof
         and price.get("source_master_queue_hash")==master.get("queue_hash")
         and price.get("source_master_count")==master.get("queue_total")
         and len(price.get("results") or {})==len(master_set)
         and set(price.get("results") or {})==master_set
         and set(price.get("blocked_symbols") or []).isdisjoint(price_set)
         and int(price.get("pass_count") if price.get("pass_count") is not None else -1)==len(price_set))
    non_g9_count=non_g9_price_pass_count(price)
    manual_policy=read("manual_decision_policy_v1.json")
    delayed_manual_contract=manual_delayed_eod_source_contract(price,manual_policy)
    fail("PRICE_PASS_NON_G9_SOURCE_NOT_RELEASE_AUTHORITY",non_g9_count==0)
    fail("PRICE_UNKNOWN_CURRENT",price.get("unknown_count")==0)
    fail("PRICE_BLOCKED_30_SESSION_BARS",price.get("blocked_count")==0)
    price_sha=sha("canonical_current_price_dv30.json")
    fail("SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT",req.get("asof_et")==asof
         and req.get("source_master_blob_sha")==sha("canonical_current_master_manifest.json")
         and req.get("source_price_blob_sha")==price_sha
         and req.get("settlement_already_proven") is True
         and req.get("settlement_bridge_blob_sha")==sha(
             Path(str(req.get("settlement_bridge_path") or "")).name))
    mc_files=list(ROOT.glob("canonical_mc_bridge_*_c417_dv30_v*.json"))
    mc_authorities=[p for p in mc_files if p.name.startswith("canonical_mc_bridge_"+str(asof or "").replace("-","")+"_"+ "c417_dv30_v")]
    mcs=[]
    for p in mc_authorities:
        try:j=json.loads(p.read_text(encoding="utf-8"))
        except (OSError,ValueError):continue
        if mc_exact(j,price,price_sha):mcs.append(p.name)
    # Do not fail on a *second valid revision* of the same day: the terminal
    # selects exactly one cryptographically bound bridge. But valid upstream
    # source material alone does not attest the terminal research chain.
    fail("CURRENT_MC_AUTHORITY_MISSING",bool(mcs))
    terminal_mc=terminal_bound_mc_selection(mcs,terminal,asof,sha)
    exact_terminal=(terminal.get("asof_et")==asof
        and terminal_research_seal(terminal)
        and terminal.get("compiled_policy_hash")==POLICY)
    fail("CURRENT_TERMINAL_FROZEN_OR_INCOMPLETE",exact_terminal)
    source_shas={key:sha(name) for key,name in {
        "master":"canonical_current_master_manifest.json",
        "price":"canonical_current_price_dv30.json",
        "history":"canonical_current_history.json",
        "events":"canonical_current_event_state.json",
        "final":"canonical_current_final_tech.json"}.items()}
    current_chain=(terminal_mc is not None and terminal_chain_exact(
        terminal,asof,source_shas,terminal_mc,sha(terminal_mc)))
    fail("TERMINAL_CURRENT_MC_CHAIN_NOT_PROVEN",current_chain)
    pointer=read("chatgpt_canonical_state_v2.json")
    prepared=bool(non_g9_count==0 and current_chain
                  and freshness.get("freshness_ready") is True
                  and registered_research_candidate_exact(
        terminal,pointer,asof,sha("canonical_current_terminal.json")))
    manual_eod_candidate_prep=bool(delayed_manual_contract and current_chain
        and freshness.get("freshness_ready") is True
        and registered_research_candidate_exact(
            terminal,pointer,asof,sha("canonical_current_terminal.json")))
    # Unlike current/live G9, this is a separate historical manual-only
    # witness; it is NEVER a market-data entitlement, full GO or delivery.
    # Delivery is independent: a zero-signal scenario may be a legitimate
    # completed run, but a device receipt must never be inferred from a ledger.
    fail("NOTIFICATION_DEVICE_RECEIPT_NOT_PROVEN",False)
    scopes=scope_readiness(blocks,current_chain)
    return {
        "schema":"XRAY_E2E_PRODUCTION_READINESS_AUDIT_V1",
        "asof_et":asof,"research_mode":"RESEARCH_ONLY_MANUAL_DECISION",
        "execution":"NONE","real_money":"NO-GO","alpha_authority":False,
        "blockers":sorted(set(blocks)),
        "ready_for_current_research_signal":prepared,
        "historical_manual_non_g9_source_contract_ready":delayed_manual_contract,
        "historical_manual_research_candidate_prep_only":manual_eod_candidate_prep,
        "historical_manual_research_no_g9_pass_claim":True,
        "historical_manual_research_no_notification_claim":True,
        "candidate_preparation_witness_only":prepared,
        "actual_device_delivery_receipt_attested":False,
        "full_e2e_research_attested":current_chain
            and freshness.get("freshness_ready") is True
            and terminal.get("full_end_to_end_research_pass") is True
            and not any(k in blocks for k in (
                "PRICE_PARTITION_NOT_EXACT_CURRENT","PRICE_PASS_NON_G9_SOURCE_NOT_RELEASE_AUTHORITY",
                "POLICY_SAFETY_NOT_ALL_ATTESTED",
                "SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT",
                "IDENTITY_PARTITION_INCOMPLETE","PRICE_BLOCKED_30_SESSION_BARS",
                "PRICE_UNKNOWN_CURRENT")),
        "current_mc_authority_count":1 if terminal_mc else 0,
        "current_mc_valid_revision_count":len(mcs),
        "latest_completed_nasdaq_session":freshness.get("latest_completed_nasdaq_session"),
        "official_nasdaq_session_freshness_attested":freshness.get("freshness_ready") is True,
        "source_session_lags":freshness.get("session_lag"),
        **scopes,
        "price_pass_count":price.get("pass_count"),"price_blocked_count":price.get("blocked_count"),
        "price_pass_explicit_non_g9_count":non_g9_count,
        "master_unknown_count":master.get("unknown_count"),
        "terminal_asof_et":terminal.get("asof_et"),
        "ledger_entry_count":len(ledger.get("deliveries") or {}),
        "source_blob_shas":{
            "master":sha("canonical_current_master_manifest.json"),
            "price":price_sha,
            "resolver_request":sha("canonical_current_resolver_request.json"),
            "terminal":sha("canonical_current_terminal.json")},
        "no_trading_or_device_receipt_claim":True,
        "explanation":"An Actions SUCCESS for this audit only means the fail-closed blocker classification completed."
    }

def selftest():
    sample={
      "pass_symbols":["A","B"],
      "results":{
        "A":{"status":"PASS_PRICE_DV30","info":{"source":"RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9"}},
        "B":{"status":"PASS_PRICE_DV30","info":{"source":"AUTHORITY_TEST_FIXTURE_ONLY"}},
      }}
    assert non_g9_price_pass_count(sample)==1
    assert non_g9_price_pass_count({}) is None
    # The policy expressly permits historical manual research without strict
    # G9. Check the source-contract distinction, without publishing a signal.
    _policy=read("manual_decision_policy_v1.json")
    _price={"pass_symbols":["A"],"results":{
        "A":{"status":"PASS_PRICE_DV30","info":{"source":"RALLIES_EXACT30_NON_G9"}}},
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"unknown_count":0}
    assert manual_delayed_eod_source_contract(_price,_policy) is True
    from copy import deepcopy as _copy_manual
    for mutate in (
        lambda q,p:q.update(mode="FULL_GO"),
        lambda q,p:q.update(execution="TRADE"),
        lambda q,p:q.update(real_money="GO"),
        lambda q,p:q.update(unknown_never_pass=False),
        lambda q,p:q["g9"].update(mandatory_for_research_signal=True),
        lambda q,p:q["delivery"].update(enabled_in_this_shadow=True),
        lambda q,p:q["delivery"].update(quotes_must_disclose_asof_and_data_delay=False),
        lambda q,p:q["hard_gates"].update(price_min_usd=2),
        lambda q,p:q["hard_gates"].update(mc_min_usd=0),
        lambda q,p:q["hard_gates"].update(history_min_daily_bars=10),
        lambda q,p:p["results"]["A"]["info"].update(source="UNKNOWN"),
        lambda q,p:p["results"]["A"]["info"].pop("source"),
        lambda q,p:p.update(unknown_count=1),
        lambda q,p:p["pass_symbols"].append("A"),
    ):
        q,p=_copy_manual(_policy),_copy_manual(_price)
        mutate(q,p)
        assert manual_delayed_eod_source_contract(p,q) is False
    print("XRAY_MANUAL_EOD_NON_G9_SEPARATE_FROM_STRICT_G9=PASS_14_NEGATIVES_NO_RELEASE")
    from copy import deepcopy as _deepcopy
    invalid=_deepcopy(sample)
    invalid["results"]["B"]["info"].pop("source")
    assert non_g9_price_pass_count(invalid) is None
    invalid=_deepcopy(sample)
    invalid["pass_symbols"].append("A")
    assert non_g9_price_pass_count(invalid) is None
    invalid=_deepcopy(sample)
    invalid["results"]["A"]["status"]="UNKNOWN"
    assert non_g9_price_pass_count(invalid) is None
    assert scope_readiness(
        ["PRICE_PASS_NON_G9_SOURCE_NOT_RELEASE_AUTHORITY"],True
        )["candidate_local_source_chain_attested"] is False
    price={"asof_et":"2026-10-08","pass_symbols":["A","B"],"pass_hash":"X"}
    mc={"asof_et":"2026-10-08","input_blob_sha":"P","input_pass_hash":"X",
       "input_pass_symbols":["A","B"],"policy_hash":POLICY,"execution":"NONE",
       "real_money":"NO-GO","unknown_never_pass":True,
       "primary_pass_symbols":["A"],"primary_fail_symbols":[],
       "fallback_watch_symbols":["B"],"fallback_fail_symbols":[],"unknown_symbols":[],
       "counts":{"MC_PASS_PRIMARY":1,"MC_FAIL_PRIMARY":0,"MC_PASS_FALLBACK_WATCH":1,
                "MC_FAIL_FALLBACK_TWO_SOURCE":0,"MC_UNKNOWN":0},
       "results":{"A":{"status":"MC_PASS_PRIMARY",
                        "mode":"BIGDATA_EXACT_XNAS_COMPANY_PUBLIC_USD",
                        "listing":"XNAS:A","market_cap_usd":2100000000,
                        "bigdata_entity_id":"ISOLATED_TEST_NOT_A_LIVE_QUOTE"},
                  "B":{"status":"MC_PASS_FALLBACK_WATCH","r92_eligible":False}}}
    assert mc_exact(mc,price,"P")
    from copy import deepcopy
    # RED: set() deduplication and int() coercion cannot prove the exact
    # PRIMARY partition and counters. Native C4.17 bridges preserve lists and
    # exact integer counts; aliases must not disagree about FAIL membership.
    for label,edit in (
        ("DUPLICATE_PRIMARY_MEMBER",lambda x:x["primary_pass_symbols"].append("A")),
        ("PRIMARY_COUNT_STRING",lambda x:x["counts"].update(MC_PASS_PRIMARY="1")),
        ("PRIMARY_COUNT_FLOAT",lambda x:x["counts"].update(MC_PASS_PRIMARY=1.9)),
        ("PRIMARY_COUNT_BOOLEAN",lambda x:x["counts"].update(MC_PASS_PRIMARY=True)),
        ("TOTAL_WRONG",lambda x:x["counts"].update(TOTAL=99)),
        ("TOTAL_WRONG_TYPE",lambda x:x["counts"].update(TOTAL="2")),
        ("PRIMARY_GROUP_NOT_LIST",lambda x:x.update(primary_pass_symbols="A")),
    ):
        bad=deepcopy(mc)
        edit(bad)
        assert not mc_exact(bad,price,"P"),("UNTRUSTWORTHY_MC_PARTITION_ACCEPTED",label)
    bad_price=dict(price,pass_symbols=["A","A","B"])
    assert not mc_exact(mc,bad_price,"P"),"DUPLICATED_PRICE_PROOF_SCOPE_ACCEPTED"
    for change in (
       lambda x:x.update(input_blob_sha="OTHER"),
       lambda x:x.update(asof_et="2026-10-07"),
       lambda x:x["results"]["B"].update(status="MC_PASS_PRIMARY"),
       lambda x:x["unknown_symbols"].append("B"),
       lambda x:x["counts"].update(MC_PASS_PRIMARY=2),
       lambda x:x.update(input_pass_symbols=["A"]),
       lambda x:x.update(policy_hash="INVALID")):
        bad=deepcopy(mc);change(bad)
        assert not mc_exact(bad,price,"P"),bad
    # Adversarial RED: a mere MC_PASS_PRIMARY label and partition is never
    # proof of an exact XNAS issuer, finite USD cap or primary source.
    for edit in (
        lambda x:x["results"]["A"].pop("market_cap_usd"),
        lambda x:x["results"]["A"].update(market_cap_usd=1999999999),
        lambda x:x["results"]["A"].update(market_cap_usd=float("nan")),
        lambda x:x["results"]["A"].update(listing="XNYS:A"),
        lambda x:x["results"]["A"].update(mode="LONG BRIDGE SHADOW"),
        lambda x:x["results"]["A"].pop("bigdata_entity_id"),
        lambda x:x["results"]["B"].update(r92_eligible=True),
        lambda x:x["results"]["B"].pop("r92_eligible"),
    ):
        bad=deepcopy(mc);edit(bad)
        assert not mc_exact(bad,price,"P"),("UNPROVEN_PRIMARY_OR_WATCH_ESCAPED",bad)
    # Native C4.17 bridge schemas deliberately omit r92_eligible on
    # MC_FAIL_PRIMARY, MC_FAIL_FALLBACK_TWO_SOURCE and MC_UNKNOWN rows.
    # Their *negative status* is an R92 veto: missing eligibility is not
    # positive evidence, but it must not make an intact bridge unverifiable.
    # MC_PASS_FALLBACK_WATCH is different: require explicit False.
    native=deepcopy(mc)
    native["input_pass_symbols"]=["A","B","C","D","E"]
    native["results"]["C"]={"status":"MC_FAIL_FALLBACK_TWO_SOURCE"}
    native["results"]["D"]={"status":"MC_UNKNOWN","unknown_never_pass":True}
    native["results"]["E"]={
        "status":"MC_FAIL_PRIMARY",
        "mode":"BIGDATA_EXACT_XNAS_COMPANY_PUBLIC_USD",
        "listing":"XNAS:E",
        "market_cap_usd":1_500_000_000,
        "bigdata_entity_id":"ISOLATED_NEGATIVE_PRIMARY_TEST"}
    native["fallback_fail_symbols"]=["C"]
    native["unknown_symbols"]=["D"]
    native["primary_fail_symbols"]=["E"]
    native["counts"]["MC_FAIL_FALLBACK_TWO_SOURCE"]=1
    native["counts"]["MC_UNKNOWN"]=1
    native["counts"]["MC_FAIL_PRIMARY"]=1
    native_price=dict(price,pass_symbols=["A","B","C","D","E"])
    assert mc_exact(native,native_price,"P"),"NEGATIVE_NATIVE_SCHEMA_FALSE_REJECTION"
    conflicting=deepcopy(native)
    conflicting["fallback_two_source_fail_symbols"]=["A"]
    assert not mc_exact(conflicting,native_price,"P"),"CONFLICTING_FALLBACK_ALIAS_SILENTLY_ACCEPTED"
    duplicated=deepcopy(native)
    duplicated["fallback_fail_symbols"]=["C","C"]
    assert not mc_exact(duplicated,native_price,"P"),"DUPLICATE_NEGATIVE_GROUP_ACCEPTED"
    consistent=deepcopy(native)
    consistent["fallback_two_source_fail_symbols"]=["C"]
    assert mc_exact(consistent,native_price,"P"),"MATCHING_NATIVE_ALIAS_FALSE_REJECTED"

    for sym in ("C","D","E"):
        forged=deepcopy(native)
        forged["results"][sym]["r92_eligible"]=True
        assert not mc_exact(forged,native_price,"P"),("CONTRADICTORY_R92_FLAG_ACCEPTED",sym)
    for sym in ("C","D","E"):
        forged=deepcopy(native)
        forged["results"][sym]["r92_eligible"]="false"
        assert not mc_exact(forged,native_price,"P"),("NONBOOL_R92_FLAG_ACCEPTED",sym)
    # Read the immutable real October 5/7 bridges as schema fixtures. This
    # is a compatibility check only, NOT a new ASOF, quote, or MC authority.
    for file_name,expected_sha,expected_rows in (
        ("canonical_mc_bridge_20261005_c417_dv30_v4.json",
         "5dae47c183a7e2f4b631e3ce2fb7bd8021ca250b",504),
        ("canonical_mc_bridge_20261007_c417_dv30_v28.json",
         "7eedf06479502b59257788e268df92816f9a3163",510),
    ):
        assert sha(file_name)==expected_sha,"HISTORIC_FIXTURE_SHA_DRIFT"
        bridge=read(file_name)
        assert len(bridge["input_pass_symbols"])==expected_rows
        historical_scope={
            "asof_et":bridge["asof_et"],
            "pass_symbols":bridge["input_pass_symbols"],
            "pass_hash":bridge["input_pass_hash"]}
        assert mc_exact(bridge,historical_scope,bridge["input_blob_sha"]),(
            "HISTORIC_NATIVE_MC_SCHEMA_FALSE_REJECTION",file_name)
    # RED: multiple historically valid same-ASOF MC revision files must not
    # indefinitely deadlock current readiness when terminal pins EXACTLY ONE
    # Git blob. No terminal-selected proof => always blocked.
    v1="canonical_mc_bridge_20261009_c417_dv30_v1.json"
    v2="canonical_mc_bridge_20261009_c417_dv30_v2.json"
    mc_terminal={"evidence":{"mc":{"path":"nasdaq-xray/"+v2,
                                  "blob_sha":"b"*40}}}
    sha_lookup=lambda name: {"a":None,v1:"a"*40,v2:"b"*40}.get(name)
    assert terminal_bound_mc_selection([v1,v2],mc_terminal,
                 "2026-10-09",sha_lookup)==v2, "MULTIPLE_VALID_REVISIONS_FALSE_BLOCK"
    for altered in (
        {"path":"nasdaq-xray/"+v2,"blob_sha":"a"*40},
        {"path":"nasdaq-xray/"+v1,"blob_sha":"b"*40},
        {"path":"nasdaq-xray/../"+v2,"blob_sha":"b"*40},
        {"path":"nasdaq-xray/canonical_mc_bridge_20261008_c417_dv30_v2.json","blob_sha":"b"*40},
        {"path":"nasdaq-xray/"+v2,"blob_sha":"b"*39+"c"},
    ):
        poisoned={"evidence":{"mc":altered}}
        assert terminal_bound_mc_selection([v1,v2],poisoned,
                        "2026-10-09",sha_lookup) is None, "UNBOUND_MC_AUTHORITY_ACCEPTED"
    assert terminal_bound_mc_selection([v1,v2],{},
                   "2026-10-09",sha_lookup) is None
    assert terminal_bound_mc_selection([v2,v2],mc_terminal,
                   "2026-10-09",sha_lookup) is None
    assert terminal_bound_mc_selection([],mc_terminal,
                   "2026-10-09",sha_lookup) is None
    assert terminal_bound_mc_selection([v1,v2],{"evidence":[]},
                   "2026-10-09",sha_lookup) is None
    assert terminal_bound_mc_selection([v1,v2],{"evidence":{"mc":[]}},
                   "2026-10-09",sha_lookup) is None
    assert terminal_bound_mc_selection([v1,v2],{"evidence":{"mc":{}}},
                   "2026-10-09",sha_lookup) is None
    print("XRAY_MC_TERMINAL_BOUND_SELECTION=PASS_MULTI_REVISION_POSITIVE_11_NO_AUTHORITY_NEGATIVES")
    print("XRAY_MC_HISTORIC_REAL_BRIDGES=PASS_OCT05_504_OCT07_510_NO_CURRENT_PROMOTION")
    print("XRAY_MC_NATIVE_NEGATIVE_ROWS=PASS_3_MISSING_FLAG_POSITIVES_6_CONTRADICTORY_NEGATIVES")
    print("XRAY_MC_PRIMARY_ROW_EVIDENCE=PASS_8_ADVERSARIAL_NEGATIVES")
    base_shas={k:k+"_SHA" for k in ("master","price","history","events","final")}
    t={"asof_et":"2026-10-08","compiled_policy_hash":POLICY,
       "full_end_to_end_research_pass":True,
       "checks":{"exact_blob_provenance_chain":True,
                 "semantic_provenance_chain_exact":True},
       "evidence":{**{k:{"blob_sha":v} for k,v in base_shas.items()},
                   "mc":{"path":"nasdaq-xray/canonical_mc_bridge_20261008_c417_dv30_v1.json",
                         "blob_sha":"MC_SHA"}}}
    good="canonical_mc_bridge_20261008_c417_dv30_v1.json"
    assert terminal_chain_exact(t,"2026-10-08",base_shas,good,"MC_SHA")
    for changed in (
        lambda x:x["evidence"]["mc"].update(blob_sha="BAD"),
        lambda x:x["evidence"]["events"].update(blob_sha="STALE"),
        lambda x:x["checks"].update(exact_blob_provenance_chain=False),
        lambda x:x.update(full_end_to_end_research_pass=False),
        lambda x:x.update(asof_et="2026-10-07")):
        bad=deepcopy(t);changed(bad)
        assert not terminal_chain_exact(bad,"2026-10-08",base_shas,good,"MC_SHA")
    # A fully attested candidate-local chain must not be vetoed by
    # unrelated master/PRICE UNKNOWN, while every local legal or C4.17 defect
    # and every source blob mismatch still blocks the candidate.
    cand=deepcopy(t)
    cand["full_end_to_end_research_pass"]=False
    cand["candidate_local_research_pass"]=True
    cand["candidate_delivery_safety"]={"status":"PASS"}
    cand["checks"].update({key:True for key in REQUIRED_LOCAL_CHECKS})
    assert terminal_research_seal(cand) is True
    assert terminal_chain_exact(cand,"2026-10-08",base_shas,good,"MC_SHA")
    assert terminal_research_seal({"full_end_to_end_research_pass":False,
                                   "candidate_local_research_pass":True}) is False
    for edit in (
       lambda x:x.update(candidate_local_research_pass=False),
       lambda x:x["candidate_delivery_safety"].update(status="UNKNOWN"),
       lambda x:x["checks"].update(mc_exact_price_pass_set=False),
       lambda x:x["checks"].update(candidate_legal_guard_exact_binding=False),
       lambda x:x["checks"].update(semantic_provenance_chain_exact=False),
       lambda x:x["evidence"]["mc"].update(blob_sha="STALE"),
       lambda x:x["evidence"]["price"].update(blob_sha="STALE"),
    ):
       bad=deepcopy(cand)
       edit(bad)
       assert not terminal_chain_exact(bad,"2026-10-08",base_shas,good,"MC_SHA")
    print("XRAY_E2E_CANDIDATE_LOCAL_CHAIN_SELFTEST=PASS_POSITIVE_7_NEGATIVES_NO_GLOBAL_BYPASS")
    global_only=("IDENTITY_PARTITION_INCOMPLETE","PRICE_BLOCKED_30_SESSION_BARS")
    x=scope_readiness(global_only,True)
    assert x["candidate_local_source_chain_attested"] is True
    assert x["full_universe_source_coverage_attested"] is False
    assert x["candidate_local_al_setup_attested"] is False
    assert x["actual_device_delivery_receipt_attested"] is False
    assert scope_readiness([],True)["full_universe_source_coverage_attested"] is True
    assert scope_readiness([],False)["candidate_local_source_chain_attested"] is False
    for blocker in ("SOURCE_EPOCH_NOT_LATEST_COMPLETED_SESSION","CURRENT_MC_AUTHORITY_MISSING","TERMINAL_CURRENT_MC_CHAIN_NOT_PROVEN",
                    "SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT",
                    "POLICY_SAFETY_NOT_ALL_ATTESTED"):
        assert scope_readiness([blocker],True)["candidate_local_source_chain_attested"] is False
    # A negative-only readiness implementation is not a working state
    # machine. Prove real future exact candidate registration is reachable,
    # while tampered provenance, mismatched MC, or absent registration fail.
    from copy import deepcopy
    reg_t=deepcopy(t)
    reg_t["candidate_local_research_pass"]=True
    reg_t["candidate_delivery_safety"]={"status":"PASS"}
    reg_t["checks"].update({key:True for key in REQUIRED_LOCAL_CHECKS})
    reg_t["r92_candidates"]=["AAA|B"]
    reg_t["sets"]={"pre_g9_tech_pass":["AAA|B"]}
    reg_row={key:"present" for key in REQUIRED_REGISTERED_FIELDS}
    reg_row.update({
        "schema":"XRAY_RESEARCH_CANDIDATE_R92_V1",
        "delivery_key":"exact-key", "symbol":"AAA","setup":"B",
        "asof_et":"2026-10-08","mc_class":"MC_PASS_PRIMARY",
        "execution":"NONE","real_money":"NO-GO",
        "entry_low":20.0,"entry_high":21.0,"chase_limit":22.0,
        "stop":19.5,"r1":26.5,"rr_basic":2.5,"rr_severe":1.7,
        "dv30":100_000_000.0})
    ptr={"schema":"XRAY_GITHUB_DURABLE_STATE_V3",
         "authority":"GITHUB_CURRENT_POINTER","execution":"NONE",
         "real_money":"NO-GO",
         "state_json":{
           "task_id":TASK_ID,"asof_et":"2026-10-08",
           "deep_final_evidence":{
             "terminal_path":"nasdaq-xray/canonical_current_terminal.json",
             "terminal_blob_sha":"TERMINAL-SHA"},
           "delivery_keys":["exact-key"],"r92":[reg_row]}}
    assert registered_research_candidate_exact(reg_t,ptr,"2026-10-08","TERMINAL-SHA")
    # A setup obeying original C4.17 (1.5 / 1.1) must pass this *preparation*
    # check without bypassing terminal MC, legal, risk or real delivery gates.
    at,ap=deepcopy(reg_t),deepcopy(ptr)
    at["r92_candidates"]=["AAA|A"]
    at["sets"]["pre_g9_tech_pass"]=["AAA|A"]
    ap["state_json"]["r92"][0]["setup"]="A"
    ap["state_json"]["r92"][0]["rr_basic"]=1.6
    ap["state_json"]["r92"][0]["rr_severe"]=1.2
    assert registered_research_candidate_exact(at,ap,"2026-10-08","TERMINAL-SHA"),"A_FAMILY_FALSE_REJECTED"
    for field,bad_rr in (("rr_basic",1.49),("rr_severe",1.09)):
        ta,pa=deepcopy(at),deepcopy(ap)
        pa["state_json"]["r92"][0][field]=bad_rr
        assert not registered_research_candidate_exact(ta,pa,"2026-10-08","TERMINAL-SHA"),("A_BELOW_POLICY",field)
    bt,bp=deepcopy(reg_t),deepcopy(ptr)
    bp["state_json"]["r92"][0]["rr_basic"]=1.6
    bp["state_json"]["r92"][0]["rr_severe"]=1.2
    assert not registered_research_candidate_exact(bt,bp,"2026-10-08","TERMINAL-SHA"),"B_WRONGLY_RELAXED"
    qt,qp=deepcopy(at),deepcopy(ap)
    qt["r92_candidates"]=["AAA|Q"]
    qt["sets"]["pre_g9_tech_pass"]=["AAA|Q"]
    qp["state_json"]["r92"][0]["setup"]="Q"
    assert not registered_research_candidate_exact(qt,qp,"2026-10-08","TERMINAL-SHA"),"UNKNOWN_FAMILY_ACCEPTED"
    for edit in (
        lambda t,p:p["state_json"]["deep_final_evidence"].update(terminal_blob_sha="DRIFT"),
        lambda t,p:p["state_json"]["delivery_keys"].clear(),
        lambda t,p:p["state_json"]["r92"][0].update(mc_class="MC_PASS_FALLBACK_WATCH"),
        lambda t,p:p["state_json"]["r92"][0].update(execution="ORDER"),
        lambda t,p:p["state_json"]["r92"][0].update(asof_et="2026-10-07"),
        lambda t,p:p.update(authority="NOT_CANONICAL"),
        lambda t,p:t["candidate_delivery_safety"].update(status="UNKNOWN"),
        lambda t,p:t["checks"].update(candidate_legal_guard_exact_binding=False),
        lambda t,p:t["sets"].update(pre_g9_tech_pass=[]),
        lambda t,p:p["state_json"]["r92"].clear(),
        lambda t,p:p["state_json"]["r92"][0].update(rr_basic=1.9),
        lambda t,p:p["state_json"]["r92"][0].update(rr_severe=1.4),
        lambda t,p:p["state_json"]["r92"][0].update(dv30=49_999_999),
        lambda t,p:p["state_json"]["r92"][0].update(entry_low=float("nan")),
        lambda t,p:p["state_json"]["r92"][0].update(stop=21),
        # These were accepted before this regression: reported RR could be
        # mathematically impossible even with zero trading costs, or severe
        # cost scenario could claim a better RR than the basic scenario.
        lambda t,p:p["state_json"]["r92"][0].update(rr_basic=5.0),
        lambda t,p:p["state_json"]["r92"][0].update(rr_severe=5.0),
        lambda t,p:p["state_json"]["r92"][0].update(rr_severe=2.7),
        # Stop risk >8% is independent of reported winning probability.
        lambda t,p:p["state_json"]["r92"][0].update(stop=18.0),
    ):
        tbad,pbad=deepcopy(reg_t),deepcopy(ptr)
        edit(tbad,pbad)
        assert not registered_research_candidate_exact(tbad,pbad,"2026-10-08","TERMINAL-SHA")
    print("XRAY_E2E_REGISTERED_RESEARCH_PREP_SELFTEST=PASS_BCD_AND_A_C417_RR_POSITIVE_19_NEGATIVES_NO_DEVICE_CLAIM")
    print("XRAY_E2E_SCOPE_BOUNDARY_SELFTEST=PASS_INDEPENDENT_GLOBAL_AND_LOCAL_NO_AL")
    print("XRAY_E2E_NON_G9_PRICE_RELEASE_VETO=PASS_5_NEGATIVE_NO_LICENSE_INFERENCE")
    print("XRAY_E2E_READINESS_MC_SELFTEST=PASS_POSITIVE_7_NEGATIVES")
    print("XRAY_E2E_TERMINAL_SHA_BINDING_SELFTEST=PASS_POSITIVE_5_NEGATIVES")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--output")
    args=p.parse_args()
    if args.selftest:
        selftest()
    else:
        result=snapshot()
        if args.output:
            Path(args.output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print("XRAY_E2E_READINESS="+("ATTESTED_TECH_CHAIN_ONLY" if result["full_e2e_research_attested"] else "BLOCKED"))
        print("XRAY_E2E_BLOCKERS="+json.dumps(result["blockers"]))
        print("XRAY_E2E_SNAPSHOT="+json.dumps(result,sort_keys=True))
