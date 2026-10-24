"""Synthetic admission tests; ZERO observed US equity prices."""
from datetime import date, datetime, timedelta, timezone
import unittest
from causal_offline_gate import admission_check, REQUIRED_EVIDENCE, SCHEMA, UPSTREAM_COMMIT

def fixture():
    # Deliberately artificial consecutive dates, NOT an XNAS calendar.
    # Calendar attestation is a mocked input, never established by this test.
    days = [(date(2024,1,1) + timedelta(days=i)).isoformat() for i in range(600)]
    manifest = dict(
        schema=SCHEMA, upstream_sha=UPSTREAM_COMMIT,
        mode="ISOLATED_OFFLINE_NO_EXECUTION", data_sha256="a"*64,
        official_xnas_sessions=days, test_start=days[540], embargo_sessions=15,
        registered_features=["x1","x2"], network_enabled=False,
        broker_enabled=False, write_private_sheet=False,
        may_emit_alert=False, may_promote_al=False
    )
    manifest.update({k:True for k in REQUIRED_EVIDENCE})
    rows=[]
    for i,day in enumerate(days):
        cutoff=(datetime.combine(date.fromisoformat(day),datetime.min.time(),timezone.utc)
                +timedelta(hours=21)).isoformat().replace("+00:00","Z")
        outcome=days[i+15] if i+15<len(days) else None
        known=((datetime.combine(date.fromisoformat(outcome),datetime.min.time(),timezone.utc)
               +timedelta(hours=21)).isoformat().replace("+00:00","Z")) if outcome else None
        rows.append(dict(session=day, decision_cutoff_utc=cutoff,
            features={"x1":{"value":1.0,"known_at_utc":cutoff},
                      "x2":{"value":2.0,"known_at_utc":cutoff}},
            outcome_session=outcome, label=0.1 if outcome else None,
            label_known_at_utc=known))
    return manifest, rows

class SyntheticAdmissionTests(unittest.TestCase):
    def check_bad(self,mutate,reason):
        m,r=fixture();mutate(m,r)
        with self.assertRaisesRegex(ValueError,reason):admission_check(m,r)
    def test_synthetic_ok_but_never_live(self):
        m,r=fixture();out=admission_check(m,r)
        self.assertEqual(out["decision"],"OFFLINE_EXPERIMENT_INPUT_ELIGIBLE_ONLY")
        self.assertGreaterEqual(out["train"],100)
        self.assertGreaterEqual(out["holdout"],30)
        self.assertFalse(out["alpha_proven"])
        self.assertFalse(out["production_enabled"])
    def test_future_feature_leak(self):
        self.check_bad(lambda m,r:r[10]["features"]["x1"].__setitem__("known_at_utc",r[11]["decision_cutoff_utc"]),"FUTURE_FEATURE_LEAK")
    def test_false_source_attestation(self):
        self.check_bad(lambda m,r:m.__setitem__("data_entitlement_attested",False),"MISSING_EXTERNAL_ATTESTATION")
    def test_production_side_effect(self):
        self.check_bad(lambda m,r:m.__setitem__("may_emit_alert",True),"FORBIDDEN_SIDE_EFFECT")
    def test_missing_calendar_row(self):
        self.check_bad(lambda m,r:r.pop(7),"MISSING_OR_EXTRA_SESSION_ROW")
    def test_label_time_lookahead(self):
        self.check_bad(lambda m,r:r[7].__setitem__("label_known_at_utc",r[7]["decision_cutoff_utc"]),"OUTCOME_LABEL_LOOKAHEAD")
    def test_label_wrong_window(self):
        self.check_bad(lambda m,r:r[7].__setitem__("outcome_session",m["official_xnas_sessions"][100]),"INVALID_FUTURE_OUTCOME_SESSION")
    def test_short_embargo(self):
        self.check_bad(lambda m,r:m.__setitem__("embargo_sessions",2),"INSUFFICIENT_15_SESSION_EMBARGO")
    def test_unknown_upstream_version(self):
        self.check_bad(lambda m,r:m.__setitem__("upstream_sha","0"*40),"UNREVIEWED_UPSTREAM_REVISION")
    def test_missing_future_label(self):
        self.check_bad(lambda m,r:r[-1].__setitem__("label",1.0),"UNVERIFIED_OUTCOME_LABEL")

if __name__=="__main__":
    unittest.main()
