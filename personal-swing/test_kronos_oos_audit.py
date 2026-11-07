"""Pure, no-network regression tests for Kronos OOS evidence and fail-closed maturity."""
from datetime import date, timedelta
import unittest
from unittest.mock import patch

import kronos_shadow as k
import kronos_oos_audit as o


def candles(asof='2026-11-06'):
    dates=[date.fromisoformat(asof)-timedelta(days=i) for i in range(51,-1,-1)]
    return [{'timestamp':d.isoformat(),'open':100.,'high':103.,
             'low':99.,'close':102.,'volume':10000.} for d in dates]


def forecast(symbol='AAPL',asof='2026-11-06'):
    return k.build_rows(symbol,asof,'a'*64,'b'*64,asof,
                        candles(asof),[104.]*12)


class TestOosAudit(unittest.TestCase):
    def test_pure_ledger_valid_three_horizons(self):
        rows=o.validate_ledger([list(k.HEADERS)]+forecast())
        self.assertEqual(len(rows),3)
        self.assertEqual(set(r[3] for r in rows),{'1','5','12'})

    def test_detect_tampering_and_missing_horizon(self):
        rows=forecast()
        rows[1][5]='1000.0'
        with self.assertRaisesRegex(k.ShadowHold,'ROW_TAMPERED'):
            o.validate_ledger([list(k.HEADERS)]+rows)
        with self.assertRaisesRegex(k.ShadowHold,'PARTIAL_PAIR'):
            o.validate_ledger([list(k.HEADERS)]+forecast()[:2])

    def test_detect_unverified_qc_forecast(self):
        rows=k.build_qc_hold_rows('AAPL','2026-11-06','a'*64,'b'*64,
                                  '2026-11-06',candles(),
                                  'KRONOS_INVALID_FORECAST_GEOMETRY')
        self.assertEqual(len(o.validate_ledger([list(k.HEADERS)]+rows)),3)
        rows[0][5]='1.0'; rows[0][19]=k.canonical_sha(rows[0][:19])
        with self.assertRaisesRegex(k.ShadowHold,'QC_HOLD_HAS_FORECAST'):
            o.validate_ledger([list(k.HEADERS)]+rows)

    def test_no_future_data_requested_saturday(self):
        future=['2026-11-09','2026-11-10','2026-11-11','2026-11-12',
                '2026-11-13','2026-11-16','2026-11-17','2026-11-18',
                '2026-11-19','2026-11-20','2026-11-23','2026-11-24']
        rows=forecast()
        with patch.object(k,'future_xnas_days',return_value=future):
            matured,pending,hold=o.select_matured(rows,'2026-11-07')
            self.assertEqual((len(matured),pending,hold),(0,3,0))
            out=o.score_matured(matured,'2026-11-07',
                               lambda *a: self.fail('future provider call forbidden'))
            self.assertEqual(out,{})
            matured,pending,hold=o.select_matured(rows,'2026-11-09')
            self.assertEqual((len(matured),pending,hold),(1,2,0))
            self.assertEqual(matured[0][0][3],'1')
            matured,pending,hold=o.select_matured(rows,'2026-11-24')
            self.assertEqual((len(matured),pending,hold),(3,0,0))

    def test_model_and_persistence_baseline_same_target(self):
        row=forecast()[0]
        pairs=[(row,'2026-11-09')]
        def reader(symbols,asof):
            self.assertEqual(symbols,['AAPL'])
            self.assertEqual(asof,'2026-11-09')
            return {'AAPL':[{'timestamp':'2026-11-09','close':103.0}]}
        evidence=o.score_matured(pairs,'2026-11-09',reader)
        outcome=o.summarize(evidence,2,0)
        self.assertEqual(outcome['horizons']['1']['model_mape_pct'],
                         round(100*1/103,5))
        self.assertEqual(outcome['horizons']['1']['persistence_mape_pct'],
                         round(100*1/103,5))
        self.assertEqual(outcome['horizons']['1']['direction_hit_rate'],1.0)
        self.assertFalse(outcome['sufficient_for_decision'])
        self.assertEqual(outcome['decision_influence'],'NO_GO')

    def test_missing_realized_price_is_not_zero_or_success(self):
        with self.assertRaisesRegex(k.ShadowHold,'MISSING_TARGET_CLOSE'):
            o.score_matured([(forecast()[0],'2026-11-09')],
                            '2026-11-09',lambda *a:{'AAPL':[]})

    def test_qc_holds_count_separately_no_model_accuracy_pollution(self):
        holds=k.build_qc_hold_rows('AAPL','2026-11-06','a'*64,'b'*64,
                                  '2026-11-06',candles(),
                                  'KRONOS_INVALID_FORECAST_GEOMETRY')
        matured,pending,hold=o.select_matured(holds,'2026-11-25')
        self.assertEqual((matured,pending,hold),([],0,3))

    def test_sample_gate_is_not_alpha_or_live_success(self):
        values={'asof':'2026-11-06','model_pct_error':0.6,
                'baseline_pct_error':1.0,'direction_correct':True}
        all_evidence={h:[dict(values,asof=f'2026-11-{d:02d}') for d in (2,3,4,5)
                       for _ in range(15)] for h in (1,5,12)}
        out=o.summarize(all_evidence,0,0)
        self.assertEqual(out['status'],'KRONOS_OOS_SAMPLE_REVIEW_REQUIRED')
        self.assertFalse(out['sufficient_for_decision'])
        self.assertEqual(out['decision_influence'],'NO_GO')

    def test_future_source_record_is_fail_closed(self):
        with self.assertRaisesRegex(k.ShadowHold,'FUTURE_SOURCE_ROW'):
            o.select_matured(forecast(),'2026-11-05')


    def test_v2_close_only_is_forecast_but_not_native_ohlc_pass(self):
        import kronos_v2 as v2
        rows=v2.build_v2_rows('MSFT','2026-11-06','a'*64,'b'*64,
                 '2026-11-06',candles(),[103.0]*12,
                 v2.MODEL_STATUS_CLOSE,
                 'RAW_CLOSE_ONLY__NATIVE_OHLC_GEOMETRY_INVALID')
        checked=o.validate_ledger([list(k.HEADERS)]+rows)
        self.assertEqual(len(checked),3)
        self.assertTrue(all(r[17]=='RESEARCH_CLOSE_ONLY' for r in checked))
        vals={'asof':'2026-11-06','forecast_status':'RESEARCH_CLOSE_ONLY',
              'model_pct_error':2.0,'baseline_pct_error':2.5,
              'direction_correct':True}
        output=o.summarize({1:[vals]},0,0)
        self.assertEqual(output['horizons']['1']['forecast_quality_counts']
                         ['RESEARCH_CLOSE_ONLY'],1)
        self.assertFalse(output['sufficient_for_decision'])

    def test_load_recent_month_partition_preserves_no_future_boundary(self):
        import kronos_v2 as v2
        legacy=forecast('AAPL','2026-11-06')
        source=v2.build_v2_rows('MSFT','2026-11-06','a'*64,'b'*64,
                 '2026-11-06',candles(),[103.0]*12,
                 v2.MODEL_STATUS_CLOSE,
                 'RAW_CLOSE_ONLY__NATIVE_OHLC_GEOMETRY_INVALID')
        class FakeApi:
            def read(self,name,col):
                return [list(k.HEADERS)]+legacy
            def request(self,path,*,method='GET',body=None):
                if path.startswith('?'):
                    return {'sheets':[{'properties':{
                        'title':'KRONOS2_2026_11'}}]}
                return {'values':[list(k.HEADERS)]+source}
        data=o.load_recent_ledgers(FakeApi(),'2026-11-07')
        result=o.validate_ledger(data)
        self.assertEqual(len(result),6)
        self.assertEqual({x[17] for x in result},
                         {'RESEARCH_ONLY','RESEARCH_CLOSE_ONLY'})


if __name__=='__main__':
    unittest.main()
