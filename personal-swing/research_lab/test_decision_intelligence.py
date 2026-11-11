import unittest
from decision_intelligence import assess, digest

DAY="2026-11-10"; SHA="a"*64
def core():
    return {"system":"XRAY_NASDAQ_PERSONAL","asof":DAY,"episode_id":DAY+"|DEMO","symbol":"DEMO","source_run":"123","scope_sha":SHA,"algorithm_sha":SHA,"reference":"100","stop":"95","target":"110","current_close":"100","technical_score":83}
def record(name,c,p,status="READY"):
    r={"source":name,"asof":c["asof"],"episode_id":c["episode_id"] if name=="KRONOS" else None,"scope_sha":c["scope_sha"],"algorithm_sha":c["algorithm_sha"],"source_run":c["source_run"],"status":status,"payload":p}
    r["sha256"]=digest(r)
    return r
def sample():
    c=core()
    return c,[record("KRONOS",c,{"model_quality":"RESEARCH_ONLY","reference":"100","closes":{"1":"101","5":"102","12":"103"}}),record("COVE",c,{"scope":"COHORT","oos":"HOLD_UNVERIFIED_PIT_OOS"}),record("SEC",c,{},"HOLD"),record("CONFIDENCE",c,{},"HOLD")]
class DecisionTests(unittest.TestCase):
    def test_support_is_not_al(self):
        c,s=sample();r=assess(c,s)
        self.assertEqual(r["kronos_context"],"UPWARD_FORECAST")
        self.assertEqual(r["research_state"],"PARTIAL_RESEARCH")
        self.assertFalse(r["may_modify_al"]);self.assertFalse(r["may_notify"])
        self.assertIsNone(r["success_probability"]);self.assertIsNone(r["net_expected_r"])
    def test_down_and_mixed(self):
        for closes,expected in [({"1":"99","5":"98","12":"97"},"DOWNWARD_FORECAST"),({"1":"101","5":"99","12":"100"},"MIXED_FORECAST")]:
            c,s=sample();p=dict(s[0]["payload"],closes=closes);s[0]=record("KRONOS",c,p)
            self.assertEqual(assess(c,s)["kronos_context"],expected)
    def test_close_only_and_hold(self):
        c,s=sample();s[0]=record("KRONOS",c,dict(s[0]["payload"],model_quality="RESEARCH_CLOSE_ONLY"))
        self.assertEqual(assess(c,s)["kronos_quality"],"RESEARCH_CLOSE_ONLY")
        s[0]=record("KRONOS",c,{},"HOLD");self.assertEqual(assess(c,s)["kronos_context"],"UNAVAILABLE")
    def test_missing_and_duplicate(self):
        c,s=sample();self.assertEqual(assess(c,[])["research_state"],"NO_RESEARCH")
        with self.assertRaises(ValueError):assess(c,s+[s[0]])
    def test_stale_wrong_scope_wrong_run(self):
        for k,v in [("asof","2026-11-09"),("scope_sha","b"*64),("source_run","124"),("episode_id","2026-11-10|OTHER")]:
            c,s=sample();s[0][k]=v;s[0]["sha256"]=digest({k:v for k,v in s[0].items() if k!="sha256"})
            with self.subTest(k=k),self.assertRaises(ValueError):assess(c,s)
    def test_tamper_and_bad_payload(self):
        c,s=sample();s[0]["payload"]["closes"]["1"]="999"
        with self.assertRaises(ValueError):assess(c,s)
        for p in [{"model_quality":"RESEARCH_ONLY","reference":"100","closes":{"1":"101","5":"102"}},{"model_quality":"RESEARCH_ONLY","reference":"99","closes":{"1":"101","5":"102","12":"103"}}]:
            c,s=sample();s[0]=record("KRONOS",c,p)
            with self.assertRaises(ValueError):assess(c,s)
    def test_no_unsupported_per_symbol_risk_or_probability(self):
        c,s=sample()
        for name,p in [("COVE",{"scope":"COHORT","oos":"HOLD_UNVERIFIED_PIT_OOS","risk":"LOW"}),("CONFIDENCE",{"probability":.83}),("SEC",{"recommendation":"BUY"})]:
            with self.subTest(name=name),self.assertRaises(ValueError):assess(c,[record(name,c,p)])
    def test_deterministic_and_identity_bound(self):
        c,s=sample();a=assess(c,s);b=assess(c,list(reversed(s)))
        self.assertEqual(a["research_sha256"],b["research_sha256"])
        c["technical_score"]=82;self.assertNotEqual(a["research_sha256"],assess(c,s)["research_sha256"])
    def test_invalid_core(self):
        for k,v in [("technical_score",True),("target","111"),("system","XRAY_CRYPTO"),("episode_id","2026-11-11|DEMO")]:
            c,s=sample();c[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):assess(c,[])
    def test_actual_decimal_score_preserved(self):
        c,s=sample();c["technical_score"]=71.8
        self.assertEqual(assess(c,s)["technical_score"],71.8)
        for invalid in (71.81,float("nan"),float("inf"),True,-1,100.1):
            c,s=sample();c["technical_score"]=invalid
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):assess(c,s)
if __name__=="__main__":unittest.main()
