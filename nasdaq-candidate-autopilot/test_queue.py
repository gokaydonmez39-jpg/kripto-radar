"""A46 deterministic ledger advancement, no skipped-session loss, retry safety."""
import copy
import datetime as dt
import json
from pathlib import Path
import unittest

from autopilot import GateError, evidence, parse_registry
from candidate_queue import QUEUE_SCHEMA, select_queue

RAW = (Path(__file__).parent / "registry.json").read_bytes()
REGISTRY = json.loads(RAW)
SHA = __import__("hashlib").sha256(RAW).hexdigest()


def history(states=None, episodes=None, asof=""):
    doc = {
        "schema":"XRAY_NASDAQ_A45_ROLLING_ARTIFACT_LEDGER_V1",
        "scope":"NASDAQ_RESEARCH_ONLY_NO_CRYPTO",
        "registry_sha256":SHA,
        "total_accepted_epochs":len(episodes or {}),
        "last_asof_et":asof,
        "candidate_states":states or {},
        "episodes":episodes or {},
    }
    return json.dumps(doc,sort_keys=True).encode()


class A46QueueTests(unittest.TestCase):
    def test_first_unseen_exact_p1(self):
        q=select_queue(RAW,asof=dt.date(2026,11,2),upstream_run_id=1)
        self.assertEqual(q["selected_ids"],[2,3,11,61,83,253,255])
        self.assertEqual(q["remaining_unseen_before"],249)
        self.assertFalse(q["automatic_promotion"])

    def test_actual_a42_uses_ledger_ids(self):
        q=select_queue(RAW,asof=dt.date(2026,11,2),upstream_run_id=1)
        e=evidence(RAW,dt.date(2026,11,2),queue=q)
        self.assertEqual([r["registry_id"] for r in e["findings"]],q["selected_ids"])
        self.assertTrue(all(r["integration_status"]=="NOT_INTEGRATED" for r in e["findings"]))
        self.assertEqual(e["selection"]["cohort_page"],"LEDGER_DRIVEN")

    def test_36_successful_epochs_exhaust_all_249_without_duplicate(self):
        seen=set()
        states={}
        epochs={}
        base=dt.date(2026,11,2)
        day=0
        for epoch in range(36):
            # Simulate skipped calendar dates and market holidays.
            while (base+dt.timedelta(days=day)).weekday()>=5:
                day+=1
            date=base+dt.timedelta(days=day)
            p=history(states,epochs,(date-dt.timedelta(days=1)).isoformat()
                      if epochs else "")
            q=select_queue(RAW,asof=date,previous_raw=p if epochs else None,
                           upstream_run_id=epoch+1)
            ids=q["selected_ids"]
            self.assertTrue(1<=len(ids)<=7)
            self.assertFalse(seen.intersection(ids))
            seen.update(ids)
            for i in ids:
                states[str(i)]={"production_integrated":False,
                                "latest_status":"PROVENANCE_RECORDED_TEST_REQUIRED",
                                "last_asof_et":date.isoformat(),
                                "observations":1}
            epochs[str(epoch+1)]={"sha256":"a"*64,"asof_et":date.isoformat()}
            day+=2 # Skip some weekdays; queue must not skip candidates.
        self.assertEqual(len(seen),249)
        self.assertEqual(len(states),249)

    def test_market_holiday_does_not_skip_entries(self):
        first=select_queue(RAW,asof=dt.date(2026,11,2),upstream_run_id=1)
        states={str(i):{"production_integrated":False,
                         "latest_status":"PROVENANCE_RECORDED_TEST_REQUIRED",
                         "last_asof_et":"2026-11-02","observations":1}
                for i in first["selected_ids"]}
        second=select_queue(RAW,asof=dt.date(2026,11,6),
                            previous_raw=history(states,{"1":{}},asof="2026-11-02"),
                            upstream_run_id=2)
        self.assertTrue(all(i not in states for i in map(str,second["selected_ids"])))
        self.assertEqual(second["remaining_unseen_before"],242)

    def test_holds_never_admitted(self):
        q=select_queue(RAW,asof=dt.date(2026,11,2),upstream_run_id=1)
        protected={r["registry_id"] for r in REGISTRY["entries"]
                   if r["recomputed_tier"] in ("HOLD","HOLD/SEPARATE")}
        self.assertEqual(len(protected),35)
        self.assertTrue(protected.isdisjoint(q["selected_ids"]))

    def test_unknown_candidate_retried_after_unseen(self):
        states={str(r["registry_id"]):{
                    "production_integrated":False,
                    "latest_status":"SOURCE_PROBE_UNKNOWN" if r["registry_id"]==2
                    else "PROVENANCE_RECORDED_TEST_REQUIRED",
                    "last_asof_et":"2026-11-02","observations":1}
                for r in REGISTRY["entries"]
                if r["recomputed_tier"] not in ("HOLD","HOLD/SEPARATE")}
        q=select_queue(RAW,asof=dt.date(2026,11,3),
                       previous_raw=history(states,{"1":{}},asof="2026-11-02"),
                       upstream_run_id=2)
        self.assertEqual(q["mode"],"RETRY_UNCERTAIN")
        self.assertIn(2,q["selected_ids"])

    def test_exhausted_retries_fall_back_to_periodic(self):
        states={str(r["registry_id"]):{
                    "production_integrated":False,
                    "latest_status":"SOURCE_PROBE_UNKNOWN",
                    "last_asof_et":"2026-11-02","observations":3}
                for r in REGISTRY["entries"]
                if r["recomputed_tier"] not in ("HOLD","HOLD/SEPARATE")}
        q=select_queue(RAW,asof=dt.date(2026,11,3),
                       previous_raw=history(states,{"1":{}},asof="2026-11-02"),
                       upstream_run_id=2)
        self.assertEqual(q["mode"],"PERIODIC_SOURCE_RECHECK")
        self.assertEqual(len(q["selected_ids"]),7)

    def test_same_source_epoch_replay_blocks(self):
        with self.assertRaises(GateError):
            select_queue(RAW,asof=dt.date(2026,11,3),
                         previous_raw=history({},{"2":{}},asof="2026-11-02"),
                         upstream_run_id=2)

    def test_stale_asof_blocked(self):
        with self.assertRaises(GateError):
            select_queue(RAW,asof=dt.date(2026,11,2),
                         previous_raw=history({},{"1":{}},asof="2026-11-03"),
                         upstream_run_id=2)

    def test_changed_registry_sha_blocks(self):
        v=json.loads(history())
        v["registry_sha256"]="f"*64
        with self.assertRaises(GateError):
            select_queue(RAW,asof=dt.date(2026,11,2),
                         previous_raw=json.dumps(v).encode(),upstream_run_id=1)

    def test_previous_claims_integration_blocks(self):
        states={"2":{"production_integrated":True,"latest_status":"OK",
                     "last_asof_et":"2026-11-02","observations":1}}
        with self.assertRaises(GateError):
            select_queue(RAW,asof=dt.date(2026,11,3),
                         previous_raw=history(states,{"1":{}},asof="2026-11-02"),
                         upstream_run_id=2)

    def test_wrong_queue_cannot_control_a42(self):
        q=select_queue(RAW,asof=dt.date(2026,11,2),upstream_run_id=1)
        q["registry_sha256"]="f"*64
        with self.assertRaises(GateError):
            evidence(RAW,dt.date(2026,11,2),queue=q)

    def test_hold_id_cannot_be_injected_into_a42(self):
        q=select_queue(RAW,asof=dt.date(2026,11,2),upstream_run_id=1)
        q["selected_ids"]=[218]
        with self.assertRaises(GateError):
            evidence(RAW,dt.date(2026,11,2),queue=q)

    def test_weekend_source_rejected(self):
        with self.assertRaises(GateError):
            select_queue(RAW,asof=dt.date(2026,11,1),upstream_run_id=1)


if __name__=="__main__":
    unittest.main()
