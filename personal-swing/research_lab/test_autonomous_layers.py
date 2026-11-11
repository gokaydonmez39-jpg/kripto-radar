import unittest
from autonomous_layers import risk_bounds, validate_snapshot, watchdog
SHA="a"*64
def snapshot():
    symbols=[f"DEMO{i:03d}" for i in range(477)]
    return {"schema":"XRAY_PRIVATE_SNAPSHOT_V1","asof":"2026-11-10","scope_sha":SHA,"algorithm_sha":SHA,"source_run":"123","source_accepted":True,"symbols":symbols,
            "scan":[{"symbol":s,"status":"IZLE"} for s in symbols],
            "kronos":[{"symbol":s,"horizon":h,"asof":"2026-11-10","quality":"RESEARCH_CLOSE_ONLY","close":100.,"native":None} for s in symbols for h in (1,5,12)]}
def obs():
    return {"asof":"2026-11-10","expected_asof":"2026-11-10","source_run":"123","run_status":"success","scan_count":477,"sheet_asof":"2026-11-10","sheet_exact":True,"guardian":True,"score":True,"identity_verified":True}
class LayersTest(unittest.TestCase):
    def test_coverage(self):
        self.assertEqual(validate_snapshot(snapshot(),expected_asof="2026-11-10",expected_scope_sha=SHA,expected_algorithm_sha=SHA)["forecast_count"],1431)
    def test_stale_duplicate_missing(self):
        for change in ("stale","dup","missing","sha","quality"):
            s=snapshot()
            if change=="stale": s["asof"]="2026-11-09"
            elif change=="dup": s["scan"][1]=s["scan"][0]
            elif change=="missing": s["kronos"].pop()
            elif change=="sha": s["scope_sha"]="b"*64
            else: s["kronos"][0]["native"]={"open":100,"high":101,"low":99,"close":100}
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_snapshot(s,expected_asof="2026-11-10",expected_scope_sha=SHA,expected_algorithm_sha=SHA)
    def test_dual_touch(self):
        r=risk_bounds(100,95,110,100,111,94,102,.1)
        self.assertEqual(r["status"],"AMBIGUOUS_DUAL_TOUCH")
        self.assertAlmostEqual(r["net_r_min"],-1.1)
        self.assertAlmostEqual(r["net_r_max"],1.9)
    def test_gap_and_no_touch(self):
        self.assertAlmostEqual(risk_bounds(100,95,110,90,93,89,92,.1)["net_r_min"],-2.1)
        self.assertEqual(risk_bounds(100,95,110,100,105,97,101,.1)["status"],"OPEN_NO_TERMINAL")
    def test_invalid_bar(self):
        with self.assertRaises(ValueError):risk_bounds(100,95,110,100,99,94,102,.1)
    def test_watchdog_identity(self):
        r=watchdog(obs(),set())
        self.assertEqual(r["status"],"ACCEPTED")
        self.assertEqual(r["event_key"],"XRAY_NASDAQ_PERSONAL|EOD_ACCEPTED|2026-11-10")
        self.assertFalse(r["may_notify"])
        o=obs();o["source_run"]="456"
        self.assertEqual(watchdog(o,{r["event_key"]})["status"],"DUPLICATE")
    def test_watchdog_failed_stale_unknown(self):
        for key,val,expected in [("run_status","failure","HOLD"),("run_status","in_progress","WAIT"),("sheet_asof","2026-11-09","HOLD"),("scan_count",476,"HOLD"),("identity_verified",False,"HOLD"),("sheet_exact",None,"UNKNOWN")]:
            o=obs();o[key]=val
            with self.subTest(key=key):self.assertEqual(watchdog(o,set())["status"],expected)
    def test_no_execution(self):
        r=watchdog(obs(),set())
        self.assertFalse(r["may_dispatch"])
        self.assertFalse(r["may_trade"])
if __name__=="__main__": unittest.main()
