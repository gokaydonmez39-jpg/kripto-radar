import unittest
from confidence_ledger_readiness import *
DAYS=["2026-11-03","2026-11-04","2026-11-05","2026-11-06","2026-11-09","2026-11-10"]
def fixture():
    c=[list(CANDIDATE_HEADER),["2026-11-04|DEMO","2026-11-04","DEMO","TEKNİK AL ADAYI","100","95","110","KAPALI • STOP_TOUCHED • 1/15 SEANS","2026-11-05","STOP_TOUCHED","-5","X",""]]
    e=[""]*20;e[:10]=["2026-11-04|DEMO|2026-11-05|STOP_TOUCHED|1","2026-11-04|DEMO","2026-11-04","DEMO","2026-11-05","STOP_TOUCHED","KRITIK","94","95","110"];e[15:17]=["1",RUN_PREFIX+"123"]
    return c,[list(EVENT_HEADER),e]
def run(f,ids=frozenset({"123"})):
    return audit(*f,expected_asof=DAYS[-1],xnas_sessions=DAYS,verified_source_run_ids=ids)
class GateTest(unittest.TestCase):
    def test_linkage_not_performance(self):
        r=run(fixture());self.assertEqual(r["counts"],{"LINKAGE_CANDIDATE_NEEDS_RAW_PATH_AND_FORECAST":1});self.assertEqual(r["performance_labels_admitted"],0);self.assertFalse(r["may_fit"])
    def test_missing_event(self):
        f=fixture();f[1].pop();self.assertEqual(run(f)["counts"],{"HOLD_TERMINAL_EVENT_MISSING":1})
    def test_missing_and_unverified_run(self):
        self.assertEqual(run(fixture(),frozenset())["counts"],{"HOLD_SOURCE_RUN_UNVERIFIED":1})
        f=fixture();f[1][1][16]="";self.assertEqual(run(f)["counts"],{"HOLD_SOURCE_RUN_URL_MISSING":1})
    def test_mismatch(self):
        f=fixture();f[1][1][8]="94";self.assertEqual(run(f)["counts"],{"HOLD_TERMINAL_EVENT_MISMATCH":1})
    def test_open(self):
        f=fixture();f[0][1][7:11]=["AÇIK • 1/15 SEANS","","",""];f[1].pop();self.assertEqual(run(f)["counts"],{"HOLD_OPEN_NOT_MATURE":1})
    def test_ambiguous(self):
        f=fixture();c=f[0][1];e=f[1][1];o="BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS";c[7]="KAPALI • "+o+" • 1/15 SEANS";c[9]=o;e[5]=o;e[0]="2026-11-04|DEMO|2026-11-05|"+o+"|1";self.assertEqual(run(f)["counts"],{"CENSORED_RESEARCH_ONLY":1})
    def test_duplicate(self):
        f=fixture();f[1].append(f[1][1][:])
        with self.assertRaises(ValueError):run(f)
    def test_wrong_horizon_and_future(self):
        f=fixture();f[0][1][7]="KAPALI • STOP_TOUCHED • 2/15 SEANS"
        with self.assertRaises(ValueError):run(f)
        f=fixture();f[1][1][4]="2026-11-11"
        with self.assertRaises(ValueError):run(f)
if __name__=="__main__":unittest.main()
