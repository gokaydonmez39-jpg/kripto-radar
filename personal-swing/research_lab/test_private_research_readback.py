import unittest
from private_research_readback import *
DAY="2026-11-10"; ALG="a"*64; RUN="123"; SYMS=[f"DEMO{i:03d}" for i in range(477)]
SCOPE=scope_sha(SYMS)
def fixture():
    scan=[list(SCAN_HEADER),[DAY,"GitHub schedule VERIFIED IEX EOD","477","477","477","0","TRUE","0",SOURCE_URL+RUN,f"scopeSHA={SCOPE};algorithmSHA={ALG};source_event=schedule"]]
    s=[""]*35;s[:9]=[DAY+"|SUMMARY",DAY,"","","SUMMARY","1","1","0","1"];s[26:33]=[SOURCE_URL+RUN,"REQUESTED_NOT_DEVICE_ACK","","b"*64,SCOPE,ALG,SCORE_VERSION]
    e=[""]*35;e[:7]=[DAY+"|2026-11-06|DEMO000",DAY,"2026-11-06|DEMO000","DEMO000","EPISODE","1","83"];e[14:18]=["100","100","95","110"];e[21]="2";e[26:33]=[SOURCE_URL+RUN,"","","b"*64,SCOPE,ALG,SCORE_VERSION]
    k=[list(KRONOS_HEADER)]
    for i,sym in enumerate(SYMS):
        for h in HORIZONS:
            status=["RESEARCH_ONLY","RESEARCH_CLOSE_ONLY","HOLD_QC_NONFINITE"][i%3]
            hold=status.startswith("HOLD")
            policy={"RESEARCH_ONLY":"IEX_RAW_AMOUNT_OHLC_MEAN_VOLUME_PROXY","RESEARCH_CLOSE_ONLY":"RAW_CLOSE_ONLY__NATIVE_OHLC_GEOMETRY_INVALID","HOLD_QC_NONFINITE":"MODEL_OUTPUT_UNUSABLE"}[status]
            r=[f"{DAY}|{sym}|H{h}",DAY,sym,h,"100.000000","" if hold else "101.000000","" if hold else "1.000000",*MODEL,SCOPE,ALG,DAY,"c"*64,"" if hold else "d"*64,VERSION,status,policy]
            k.append(r+[canonical_sha(r)])
    return scan,[list(SCORE_HEADER),s,e],k
def build(f,**kw):
    args=dict(expected_asof=DAY,expected_symbols=SYMS,expected_algorithm_sha=ALG,expected_run_id=RUN);args.update(kw)
    return build_readback(*f,**args)
def rehash(r):r[19]=canonical_sha(r[:19])
class ReadbackTest(unittest.TestCase):
    def test_full(self):
        r=build(fixture());self.assertEqual((r["scope_count"],r["score_count"],r["forecast_count"]),(477,1,1431));self.assertFalse(r["may_publish"]);self.assertFalse(r["native_forecast_ohlc_available"]);self.assertFalse(r["scan_classifications_available"]);self.assertEqual(r["episodes"][0]["technical_score"],83)
        self.assertEqual(r["forecasts"][0]["chart_kind"],"FORECAST_CLOSE_POINTS");self.assertEqual(r["forecasts"][3]["model_quality"],"RESEARCH_CLOSE_ONLY");self.assertEqual(r["forecasts"][6]["chart_kind"],"NONE");self.assertTrue(all(x["native_ohlc"] is None for x in r["forecasts"]))
    def test_stale_and_bad_source(self):
        for kw in (dict(expected_asof="2026-11-11"),dict(expected_run_id="456"),dict(expected_symbols=list(reversed(SYMS))),dict(expected_algorithm_sha="b"*64)):
            with self.subTest(kw=kw),self.assertRaises(ValueError):build(fixture(),**kw)
    def test_scan_mutations(self):
        for i,v in ((2,"476"),(6,"FALSE"),(1,"GitHub push VERIFIED IEX EOD"),(9,f"scopeSHA={SCOPE};scopeSHA={SCOPE};algorithmSHA={ALG}")):
            f=fixture();f[0][1][i]=v
            with self.subTest(i=i),self.assertRaises(ValueError):build(f)
    def test_score_mutations(self):
        for i,v in ((4,"UNKNOWN"),(6,"101"),(16,"100"),(26,SOURCE_URL+"999"),(29,"c"*64),(21,"16")):
            f=fixture();f[1][2][i]=v
            with self.subTest(i=i),self.assertRaises(ValueError):build(f)
    def test_score_count_and_zero(self):
        f=fixture();f[1].pop()
        with self.assertRaises(ValueError):build(f)
        f[1][1][5:9]=["0","0","0","0"];self.assertEqual(build(f)["score_count"],0)
    def test_hash_mutation(self):
        f=fixture();f[2][1][5]="999"
        with self.assertRaises(ValueError):build(f)
    def test_signed_invalid_rows(self):
        for i,v in ((3,"2"),(5,"0"),(6,"9"),(8,"e"*40),(11,"e"*64),(17,"HOLD_QC_NONFINITE"),(18,"WRONG")):
            f=fixture();r=f[2][1];r[i]=v
            if i==3:r[0]=f"{DAY}|DEMO000|H2"
            rehash(r)
            with self.subTest(i=i),self.assertRaises(ValueError):build(f)
    def test_missing_duplicate_and_group_drift(self):
        f=fixture();f[2].pop()
        with self.assertRaises(ValueError):build(f)
        f=fixture();f[2][2]=f[2][1][:]
        with self.assertRaises(ValueError):build(f)
        f=fixture();f[2][2][14]="e"*64;rehash(f[2][2])
        with self.assertRaises(ValueError):build(f)
    def test_hold_cannot_draw(self):
        f=fixture();r=f[2][7];r[5]="101.000000";rehash(r)
        with self.assertRaises(ValueError):build(f)
    def test_header_and_blank(self):
        f=fixture();f[2][0][0]="wrong"
        with self.assertRaises(ValueError):build(f)
        f=fixture();f[2].insert(2,[])
        with self.assertRaises(ValueError):build(f)
if __name__=="__main__": unittest.main()
