#!/usr/bin/env python3
"""Oct 7->8->9 root-cause regression; synthetic identity/control fixtures ONLY.
Never generates, replaces or certifies market bars; no vendor network access.
"""
from __future__ import annotations
import copy
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sina_identity_epoch import frozen_identity_fingerprint
from sina_late_asof_recheck import choose,choose_canary_probe,MAX_RECHECK_ROUNDS,MAX_PER_RUN
import orchestrator_run as orchestrator

def sha_lines(rows):
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()

def identity_fixture():
    return {
      "queue":["AAPL","GRAL","NVDA"],
      "queue_hash":sha_lines(["AAPL","GRAL","NVDA"]),
      "security_names":{"AAPL":"Apple Inc.","GRAL":"Grail Inc.","NVDA":"NVIDIA Corp"},
      "discovery":{k:{"industry":"Technology","screener_price":None}
                   for k in ("AAPL","GRAL","NVDA")},
      "identity_unknown_symbols":[],
      "identity_unknown_detail":{},
      "official_footer":"File Creation Time: 1009202618:01",
      "identity_authority":"OFFICIAL_NASDAQ",
      "explicit_excluded_count":0,
      "explicit_excluded_hash":sha_lines([]),
      "explicit_excluded_reason_counts":{},
      "source_state_hash":"3d497e5a046c5d36c1aa24b0fb8c4d8d97a93f9afba3f8f20c258bf54468ec7b"
    }

def test_epoch():
    a=identity_fixture()
    b=copy.deepcopy(a)
    # Actual GitHub 09-Oct same 3184-ticker scope changed frozen state hash.
    b["source_state_hash"]="f0f7acbf05ed808fe924c5a28074004322cc70332e7e70a2b89d5d797af1f9bc"
    # RED reproduction of the historic bug: the old implementation keyed
    # identity from *mutable* frozen state_hash even though official symbol
    # identity and current PRICE Git blob were unchanged in real Oct-9 readback.
    def legacy_frozen_key(x):
        return "CANONICAL_FROZEN:"+x["source_state_hash"]
    assert legacy_frozen_key(a)!=legacy_frozen_key(b), "LEGACY_RESET_BUG_NOT_REPRODUCED"
    assert frozen_identity_fingerprint(a)==frozen_identity_fingerprint(b), "SAME_IDENTITY_MUST_NOT_RESET_3184"
    for mutation in (
       lambda c:c["queue"].append("ZS"),
       lambda c:c["security_names"].update(AAPL="Changed issuer"),
       lambda c:c["discovery"]["GRAL"].update(industry="Blank Checks"),
       lambda c:c.update(official_footer="File Creation Time: 1008202618:01"),
       lambda c:c.update(explicit_excluded_hash="0"*64),
       lambda c:c["identity_unknown_detail"].update(SPAC={"reason":"UNRESOLVED"}),
    ):
        c=copy.deepcopy(a)
        mutation(c)
        try:changed=frozen_identity_fingerprint(c)
        except ValueError:continue  # exact hash/set inconsistency itself fails closed
        assert frozen_identity_fingerprint(a)!=changed,"IDENTITY_DRIFT_UNDETECTED"
    c=copy.deepcopy(a)
    c["queue_hash"]="0"*64
    try:frozen_identity_fingerprint(c)
    except ValueError:pass
    else:raise AssertionError("FORGED_QUEUE_HASH_ACCEPTED")

def last_30_weekdays():
    d=dt.date(2026,10,9)
    days=[]
    while len(days)<30:
        if d.weekday()<5 and d!=dt.date(2026,9,7):
            days.append(d.isoformat())
        d-=dt.timedelta(days=1)
    return sorted(days)

def state_fixture():
    syms=["AAPL","GRAL","NVDA","OLD","FAIL","DONE"]
    def row(status,reason,rounds=0,stamp="2026-10-09T22:30:00Z"):
        return {"status":status,"info":{"reason":reason},"attempts":1,
                "updated_at_utc":stamp,"late_asof_recheck_round":rounds}
    state={
      "asof_et":"2026-10-09","expected30":last_30_weekdays(),
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "status":"HISTORY_PARTIAL","queue":syms,"queue_total":6,
      "queue_hash":sha_lines(syms),"cursor":6,
      "results":{
        "AAPL":row("UNKNOWN_STATIC","ASOF_MISSING_REQUIRES_RESOLUTION"),
        "GRAL":row("UNKNOWN_STATIC","EXACT30_INCOMPLETE_NEVER_PASS"),
        "NVDA":row("UNKNOWN_STATIC","ASOF_MISSING_REQUIRES_RESOLUTION",MAX_RECHECK_ROUNDS),
        "OLD":row("UNKNOWN_STATIC","SINA_DAILY_LT260_REQUIRES_INDEPENDENT_CONFIRMATION"),
        "FAIL":row("FAIL_PRICE","ASOF_CLOSE"),
        "DONE":row("PASS","EXACT30_MEDIAN"),
       }
    }
    state["results"]["DONE"]["info"]["proof"]="EXACT30_MEDIAN"
    return state

def test_recheck():
    close=dt.datetime(2026,10,9,20,tzinfo=dt.timezone.utc)
    later=dt.datetime(2026,10,10,1,tzinfo=dt.timezone.utc)
    s=state_fixture()
    assert choose(s,close,later)==["AAPL","GRAL"]
    # Source publication does NOT require a positive trading candidate.
    fail_observed=copy.deepcopy(s)
    fail_observed["results"]["DONE"]["status"]="FAIL_PRICE"
    fail_observed["results"]["DONE"]["info"]={"proof":"ASOF_CLOSE","price":4.0}
    assert choose(fail_observed,close,later)==["AAPL","GRAL"]
    fake_overlay=copy.deepcopy(fail_observed)
    fake_overlay["results"]["DONE"]["resolution_overlay"]=True
    assert choose(fake_overlay,close,later)==[]
    fake_overlay["results"]["DONE"]["resolution_overlay"]=False
    fake_overlay["results"]["DONE"]["attempts"]=0
    assert choose(fake_overlay,close,later)==[]

    assert choose_canary_probe(s,close,later)==[]
    not_ready=copy.deepcopy(s)
    not_ready["results"]["DONE"]={"status":"UNKNOWN_STATIC",
        "info":{"reason":"ASOF_MISSING_REQUIRES_RESOLUTION"},
        "updated_at_utc":"2026-10-09T22:30:00Z"}
    assert choose(not_ready,close,later)==[], "PREMATURE_MASS_PROVIDER_RETRY"
    assert choose_canary_probe(not_ready,close,later)==["AAPL"]
    assert choose_canary_probe(not_ready,close,close+dt.timedelta(minutes=89))==[]
    # Repeated hourly EOD canaries must not spin forever when the vendor
    # never publishes its ASOF bar: max eight per same-ASOF epoch, 16h horizon.
    recent=copy.deepcopy(not_ready)
    recent["results"]["AAPL"]["late_asof_canary_probe_round"]=1
    recent["results"]["AAPL"]["updated_at_utc"]="2026-10-10T00:30:00Z"
    assert choose_canary_probe(recent,close,later)==[]
    assert choose_canary_probe(recent,close,later+dt.timedelta(minutes=31))==["AAPL"]
    exhausted=copy.deepcopy(not_ready)
    exhausted["results"]["AAPL"]["late_asof_canary_probe_round"]=8
    assert choose_canary_probe(exhausted,close,later)==[]
    assert choose_canary_probe(not_ready,close,close+dt.timedelta(hours=17))==[]
    malformed=copy.deepcopy(not_ready)
    malformed["results"]["AAPL"]["late_asof_canary_probe_round"]=-1
    assert choose_canary_probe(malformed,close,later)==[]
    fake_counter=copy.deepcopy(not_ready)
    fake_counter["results"]["AAPL"]["late_asof_canary_probe_round"]=True
    assert choose_canary_probe(fake_counter,close,later)==[]
    assert orchestrator.history_retry_plan({
        "status":"HISTORY_PARTIAL","queue_total":6,"cursor":6,
        "pending_retry":0,"pending_late_asof_recheck":2
    })==(True,"REAL_SOURCE_LATE_ASOF_RECHECK_PENDING")
    assert orchestrator.history_retry_plan({
        "status":"HISTORY_PARTIAL","queue_total":6,"cursor":6,
        "pending_retry":0,"pending_late_asof_recheck":0
    })==(False,"NO_RETRYABLE_HISTORY_WORK_REMAINS")
    assert choose(s,close,later,limit=1)==["AAPL"]
    assert choose(s,close,close+dt.timedelta(minutes=89))==[]
    assert choose(s,close,dt.datetime(2026,10,9,22,45,tzinfo=dt.timezone.utc))==[]
    for alter in (
      lambda c:c.update(execution="ORDER"),
      lambda c:c.update(real_money="GO"),
      lambda c:c.update(asof_et="2026-10-08"),
      lambda c:c.update(queue_hash="f"*64),
      lambda c:c["queue"].append("AAPL"),
      lambda c:c.update(status="HISTORY_COMPLETE"),
      lambda c:c["results"]["AAPL"].update(status="PASS"),
      lambda c:c["results"]["AAPL"].update(updated_at_utc="invalid"),
    ):
      c=copy.deepcopy(s);alter(c)
      try:out=choose(c,close,later)
      except ValueError:continue
      assert "AAPL" not in out,(alter,out)
    assert MAX_PER_RUN<=250
    assert MAX_RECHECK_ROUNDS<=2

if __name__=="__main__":
    test_epoch()
    test_recheck()
    print("XRAY_SINA_OCT7_9_EPOCH_AND_LATE_BAR_REGRESSION=PASS_6_IDENTITY_NEGATIVE_8_RECHECK_NEGATIVE_NO_PRIMARY")
