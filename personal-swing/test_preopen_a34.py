"""A34 pure offline negative tests. Never requires secrets, network or broker."""
import copy
import unittest
import preopen_a34 as w

ASOF = '2026-10-28'
SCOPE = '1'*64
POLICY = '2'*64
SYMBOLS = ['S%03d' % i for i in range(477)]
SCAN = [['ASOF ET','KANAL','ISTENEN','ISLENEN','GECERLI','EKSIK',
         'FINAL READY','YENI KAYIT','RUN','NOTE'],
        [ASOF,'GitHub','477','477','477','0','TRUE','2','https://example.invalid',
         'scopeSHA='+SCOPE+';algorithmSHA='+POLICY+';NO_ORDERS']]
ROWS = {s:{'symbol':s,'asof_et':ASOF,'sessions':52,
           'decision':'AL' if i < 2 else 'ELE'} for i,s in enumerate(SYMBOLS)}

class A34ContractTest(unittest.TestCase):
    def test_success_477_and_immutable_count(self):
        self.assertEqual(w.validate_scope_and_scan(SYMBOLS,SCAN,ASOF,SCOPE,POLICY),2)
        out=w.validate_iex_result(SYMBOLS,ASOF,2,ROWS)
        self.assertEqual(out['covered'],477)
        self.assertFalse(out['device_ack'])
        self.assertFalse(out['writes'])
        self.assertFalse(out['orders'])

    def test_bad_scope_count(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'EXACT_477'):
            w.validate_scope_and_scan(SYMBOLS[:-1],SCAN,ASOF,SCOPE,POLICY)

    def test_bad_scope_duplicate(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'EXACT_477'):
            w.validate_scope_and_scan(SYMBOLS[:-1]+[SYMBOLS[0]],SCAN,ASOF,SCOPE,POLICY)

    def test_bad_scope_lowercase(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'EXACT_477'):
            w.validate_scope_and_scan(SYMBOLS[:-1]+['bad'],SCAN,ASOF,SCOPE,POLICY)

    def test_missing_scan(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'SCANS_MISSING'):
            w.validate_scope_and_scan(SYMBOLS,[],ASOF,SCOPE,POLICY)

    def test_stale_scan(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'LATEST_COMPLETED_SCAN'):
            w.validate_scope_and_scan(SYMBOLS,SCAN,'2026-10-27',SCOPE,POLICY)

    def test_duplicate_scan(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'SCAN_DUPLICATE'):
            w.validate_scope_and_scan(SYMBOLS,SCAN+[SCAN[-1]],ASOF,SCOPE,POLICY)

    def test_bad_counts(self):
        arr=copy.deepcopy(SCAN);arr[-1][4]='476'
        with self.assertRaisesRegex(w.PreopenBlocked,'SCAN_NOT_FINAL'):
            w.validate_scope_and_scan(SYMBOLS,arr,ASOF,SCOPE,POLICY)

    def test_missing_sha(self):
        arr=copy.deepcopy(SCAN);arr[-1][9]='scopeSHA='+SCOPE
        with self.assertRaisesRegex(w.PreopenBlocked,'SOURCE_PROOF_MISSING'):
            w.validate_scope_and_scan(SYMBOLS,arr,ASOF,SCOPE,POLICY)

    def test_duplicate_sha(self):
        arr=copy.deepcopy(SCAN);arr[-1][9]+=';scopeSHA='+SCOPE
        with self.assertRaisesRegex(w.PreopenBlocked,'SOURCE_PROOF_MISSING'):
            w.validate_scope_and_scan(SYMBOLS,arr,ASOF,SCOPE,POLICY)

    def test_malformed_sha(self):
        arr=copy.deepcopy(SCAN);arr[-1][9]=arr[-1][9].replace(SCOPE,'x'*64)
        with self.assertRaisesRegex(w.PreopenBlocked,'SOURCE_PROOF_MISSING'):
            w.validate_scope_and_scan(SYMBOLS,arr,ASOF,SCOPE,POLICY)

    def test_scope_sha_drift(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'CURRENT_SOURCE'):
            w.validate_scope_and_scan(SYMBOLS,SCAN,ASOF,'3'*64,POLICY)

    def test_algorithm_sha_drift(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'CURRENT_SOURCE'):
            w.validate_scope_and_scan(SYMBOLS,SCAN,ASOF,SCOPE,'4'*64)

    def test_candidate_provider_missing_one_symbol(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'IEX_PROVIDER_SCOPE'):
            w.validate_iex_result(SYMBOLS,ASOF,2,{k:v for k,v in ROWS.items() if k!=SYMBOLS[0]})

    def test_invalid_provider_decision(self):
        arr=copy.deepcopy(ROWS);arr[SYMBOLS[0]]['decision']='VERI_YETERSIZ'
        with self.assertRaisesRegex(w.PreopenBlocked,'IEX_INCOMPLETE'):
            w.validate_iex_result(SYMBOLS,ASOF,2,arr)

    def test_stale_provider_session(self):
        arr=copy.deepcopy(ROWS);arr[SYMBOLS[0]]['asof_et']='2026-10-27'
        with self.assertRaisesRegex(w.PreopenBlocked,'IEX_INCOMPLETE'):
            w.validate_iex_result(SYMBOLS,ASOF,2,arr)

    def test_under_52_bars(self):
        arr=copy.deepcopy(ROWS);arr[SYMBOLS[0]]['sessions']=51
        with self.assertRaisesRegex(w.PreopenBlocked,'IEX_INCOMPLETE'):
            w.validate_iex_result(SYMBOLS,ASOF,2,arr)

    def test_false_al_count(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'IEX_LIVE_AL_COUNT'):
            w.validate_iex_result(SYMBOLS,ASOF,1,ROWS)

    def test_unrecognized_numeric_scan(self):
        arr=copy.deepcopy(SCAN);arr[-1][7]='2.0'
        with self.assertRaisesRegex(w.PreopenBlocked,'SCAN_NEW_AL_COUNT'):
            w.validate_scope_and_scan(SYMBOLS,arr,ASOF,SCOPE,POLICY)

if __name__=='__main__':unittest.main()
