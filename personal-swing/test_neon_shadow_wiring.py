"""Offline workflow regression: NEON shadow must never change primary EOD."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import daily_job
import runner
import neon_shadow_v3

ASOF='2026-11-19'
MASTER=runner.get_scope(
    watchlist_file=str(Path(__file__).with_name('nasdaq_watchlist_477.json')),
    asof=ASOF)

def accepted():
    return {'asof_et':ASOF,'processed_symbols':477,'valid_data_symbols':477,
            'insufficient_data_symbols':0,'remaining_symbols':0,
            'valid_data_coverage_complete':True,
            'scope_sha256':'a'*64,'analysis_fingerprint_sha256':'b'*64}

def journal_ok(*args,**kw):
    return {'new_signals':[],'followup_errors':[],'closed_signals':[]}


class NeonWiringTests(unittest.TestCase):
    def exercise(self, *, shadow, scan=None, provider=None):
        calls=[]
        if provider is None:
            def provider(symbols,asof):
                calls.append(tuple(symbols))
                return {s:[] for s in symbols}
        def scanner(asof, symbols, directory, *, batch_size, max_batches, read_batch):
            if read_batch is not None:
                read_batch(symbols[:2],asof)
            if isinstance(scan,Exception):
                raise scan
            return accepted() if scan is None else scan
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(daily_job.engine,'validate_asof',return_value=None),\
                 patch.object(daily_job.runner,'scan',side_effect=scanner),\
                 patch.object(daily_job.tracker,'process_snapshot',side_effect=journal_ok):
                result=daily_job.run_once(asof=ASOF,symbols=MASTER,
                      directory=directory,read_batch=provider,neon_shadow=shadow)
            self.assertFalse((Path(directory)/('neon_shadow_v3_'+ASOF+'.json')).exists())
        return result,calls

    def test_legacy_no_flag_keeps_existing_behavior(self):
        r,calls=self.exercise(shadow=False)
        self.assertTrue(r['final_ready'])
        self.assertNotIn('neon_shadow',r)
        self.assertEqual(len(calls),1)
        self.assertEqual(r['new_entries'],0)

    def test_enabled_shadow_bad_raw_does_not_block_primary(self):
        r,calls=self.exercise(shadow=True)
        self.assertTrue(r['final_ready'])
        self.assertEqual(r['neon_shadow']['status'],'NEON_SHADOW_HOLD_NO_DELIVERY')
        self.assertFalse(r['neon_shadow']['notification_sent'])
        self.assertEqual(len(calls),1)

    def test_shadow_success_never_changes_primary_outcome(self):
        fake={'status':'NEON_SHADOW_477_READY_PRIVATE_NO_DELIVERY',
              'scored':477,'asof':ASOF,'orders_sent':0,'notification_sent':False}
        with patch.object(neon_shadow_v3.Capture,'finish',return_value=fake):
            r,calls=self.exercise(shadow=True)
        self.assertTrue(r['final_ready'])
        self.assertEqual(r['neon_shadow'],fake)
        self.assertEqual(len(calls),1)

    def test_shadow_constructor_failure_uses_original_reader(self):
        with patch.object(neon_shadow_v3,'Capture',side_effect=RuntimeError('synthetic')):
            r,calls=self.exercise(shadow=True)
        self.assertTrue(r['final_ready'])
        self.assertEqual(r['neon_shadow']['scored'],0)
        self.assertEqual(len(calls),1)

    def test_primary_scan_failure_is_never_concealed(self):
        with self.assertRaisesRegex(RuntimeError,'PRIMARY_FAILURE'):
            self.exercise(shadow=True,scan=RuntimeError('PRIMARY_FAILURE'))

    def test_incomplete_primary_scan_never_claims_neon_ready(self):
        snap=accepted();snap['valid_data_coverage_complete']=False
        snap['valid_data_symbols']=476;snap['insufficient_data_symbols']=1
        r,calls=self.exercise(shadow=True,scan=snap)
        self.assertFalse(r['final_ready'])
        self.assertEqual(r['neon_shadow']['status'],'NEON_SHADOW_HOLD_NO_DELIVERY')
        self.assertEqual(len(calls),1)

    def test_public_summary_never_includes_symbols_or_raw_prices(self):
        r,calls=self.exercise(shadow=True)
        body=json.dumps(r,sort_keys=True)
        self.assertNotIn('"rows"',body)
        self.assertNotIn('sample_close',body)
        self.assertNotIn('data.alpaca.markets',body)

    def test_primary_source_read_error_stays_an_error(self):
        def failing_source(*args):
            raise PermissionError('PRIMARY_SOURCE_FAILURE')
        with self.assertRaisesRegex(PermissionError,'PRIMARY_SOURCE_FAILURE'):
            self.exercise(shadow=True,provider=failing_source)


if __name__=='__main__':
    unittest.main()
