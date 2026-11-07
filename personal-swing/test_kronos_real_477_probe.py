"""Offline deterministic no-secrets proof of real cohort QC isolation and budget gates."""
from datetime import date, timedelta
import json
import sys
import types
import unittest
from unittest.mock import patch

import kronos_shadow as k
import kronos_real_477_probe as p

ASOF='2026-11-06'
SYMBOLS=[f'SYM{i:03d}' for i in range(477)]

def fake_bars(symbols):
    dates=[(date.fromisoformat(ASOF)-timedelta(days=51-i)).isoformat()
           for i in range(52)]
    rows={}
    for j,s in enumerate(symbols):
        c=10.0+j*0.1
        rows[s]=[{'timestamp':d,'open':c,'high':c+1,
                  'low':c-1,'close':c,'volume':1000.0} for d in dates]
    return rows

class ProbeTests(unittest.TestCase):
    def _context(self, failing=()):
        engine=types.ModuleType('engine')
        engine.analyze=lambda symbol,bars,asof:{'sessions':52,'decision':'IZLE'}
        allrows=fake_bars(SYMBOLS)
        def predict(_,candles,future):
            symbol_id=round((candles[-1]['close']-10)/0.1)
            if symbol_id in failing:
                raise k.ShadowHold('KRONOS_INVALID_FORECAST_GEOMETRY')
            return [candles[-1]['close']]*12
        return engine,allrows,predict

    def test_real_477_qc_accounting_no_silent_promotion(self):
        engine,rows,predict=self._context(failing=range(6))
        with patch.dict(sys.modules,{'engine':engine}), \
             patch.object(k,'future_xnas_days',return_value=['2026-11-09']*12), \
             patch.object(k,'predict_one',side_effect=predict):
            output=p.evaluate_cohort(SYMBOLS,ASOF,
                                     lambda symbols,asof:rows,
                                     lambda:object(),
                                     clock=lambda:0.0,mem_mb=lambda:250.0)
        self.assertEqual(output['processed'],477)
        self.assertEqual(output['valid_forecast_symbols'],471)
        self.assertEqual(output['qc_hold_symbols'],6)
        self.assertEqual(output['status'],'KRONOS_REAL_477_QC_HOLD')
        self.assertEqual(output['sheet_rows_written'],0)
        self.assertEqual(output['financial_alpha'],'NOT_PROVEN')
        self.assertEqual(output['qc_categories'],
                         {'KRONOS_INVALID_FORECAST_GEOMETRY':6})
        text=json.dumps(output)
        self.assertNotIn('SYM000',text)

    def test_full_477_valid_still_not_financial_pass(self):
        engine,rows,predict=self._context()
        with patch.dict(sys.modules,{'engine':engine}), \
             patch.object(k,'future_xnas_days',return_value=['2026-11-09']*12), \
             patch.object(k,'predict_one',side_effect=predict):
            output=p.evaluate_cohort(SYMBOLS,ASOF,lambda *_:rows,
                                     lambda:object(),clock=lambda:0,
                                     mem_mb=lambda:250)
        self.assertEqual(output['status'],'KRONOS_REAL_477_QC_OBSERVATION_PASS')
        self.assertEqual(output['live_477_persistent_readback'],'NOT_TESTED')
        self.assertEqual(output['model_decision_influence'],'NO_GO')

    def test_partial_bars_scope_never_counted_pass(self):
        engine,rows,predict=self._context()
        rows.pop(SYMBOLS[0])
        with patch.dict(sys.modules,{'engine':engine}), \
             patch.object(k,'future_xnas_days',return_value=['2026-11-09']*12), \
             patch.object(k,'predict_one',side_effect=predict):
            with self.assertRaisesRegex(k.ShadowHold,'PROVIDER_SCOPE_DRIFT'):
                p.evaluate_cohort(SYMBOLS,ASOF,lambda *_:rows,
                                  lambda:object(),clock=lambda:0,mem_mb=lambda:250)

    def test_no_476_or_duplicate_scope(self):
        for symbols in (SYMBOLS[:-1],SYMBOLS[:-1]+[SYMBOLS[0]]):
            with self.assertRaisesRegex(k.ShadowHold,'INVALID_SCOPE'):
                p.evaluate_cohort(symbols,ASOF,lambda *_:None,
                                  lambda:object(),clock=lambda:0,mem_mb=lambda:250)

if __name__=='__main__':
    unittest.main()
