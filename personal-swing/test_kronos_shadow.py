"""Pure deterministic regression and fail-closed tests for Kronos shadow sidecar."""
from datetime import date, datetime, timedelta, timezone
import sys
import types
import unittest
from unittest.mock import patch

import kronos_shadow as k

ASOF = '2026-11-06'
SHA1 = 'a' * 64
SHA2 = 'b' * 64


def make_bars(n=52, asof=ASOF):
    days = [date.fromisoformat(asof) - timedelta(days=x) for x in range(n-1, -1, -1)]
    return [dict(timestamp=d.isoformat(), open=100.0, high=104.0,
                 low=99.0, close=102.0, volume=10000.0) for d in days]


class FakePredFrame:
    def __init__(self, rows):
        self.rows = rows
    def __len__(self):
        return len(self.rows)
    def iterrows(self):
        return enumerate(self.rows)


class FakeApi:
    def __init__(self):
        self.header = [list(k.HEADERS)]
        self.rows = []
        self.post_count = 0
        self.bad_readback = False
    def read(self, tab, column):
        if tab == k.TAB:
            return self.header + [list(r) for r in self.rows]
        raise AssertionError('private sheet side effect not expected')
    def request(self, path, *, method='GET', body=None):
        if method == 'GET':
            return {'properties':{'timeZone':'Europe/Istanbul'},
                    'sheets':[{'properties':{'title':k.TAB,'sheetId':99}}]}
        self.post_count += 1
        batch = body['requests'][0]['appendCells']['rows']
        parsed = [[v['userEnteredValue']['stringValue'] for v in r['values']] for r in batch]
        self.rows += parsed
        if self.bad_readback:
            self.rows[-1][-1] = 'CORRUPT'
        return {}


class TestKronosShadow(unittest.TestCase):
    def test_model_and_schema_pins(self):
        self.assertEqual(len(k.HEADERS), 20)
        self.assertEqual(k.HORIZONS, (1, 5, 12))
        self.assertEqual(len(k.MODEL_REV), 40)
        self.assertEqual(len(k.KRONOS_CODE_REV), 40)

    def test_exact_no_future_for_asof(self):
        candles = k.validate_candles(make_bars(), ASOF)
        self.assertEqual(len(candles), 52)
        self.assertEqual(candles[-1]['timestamp'], ASOF)
        with self.assertRaisesRegex(k.ShadowHold, 'KRONOS_SOURCE_ASOF_DRIFT'):
            k.validate_candles(make_bars(asof='2026-11-05'), ASOF)

    def test_duplicate_session_blocked(self):
        bars = make_bars()
        bars[-2]['timestamp'] = bars[-1]['timestamp']
        with self.assertRaisesRegex(k.ShadowHold, 'KRONOS_DUPLICATE'):
            k.validate_candles(bars, ASOF)

    def test_invalid_ohlc_source_blocked(self):
        bars = make_bars()
        bars[-1]['high'] = 101
        with self.assertRaisesRegex(k.ShadowHold, 'KRONOS_INVALID_SOURCE'):
            k.validate_candles(bars, ASOF)

    def test_prediction_invalid_candle_or_negative_volume_rejected(self):
        rows = [dict(open=100, high=105, low=99, close=102, volume=100)] * 12
        self.assertEqual(k.validate_prediction(FakePredFrame(rows), 102), [102]*12)
        rows = [dict(open=100, high=100, low=99, close=104, volume=100)] * 12
        with self.assertRaisesRegex(k.ShadowHold,'KRONOS_INVALID_FORECAST'):
            k.validate_prediction(FakePredFrame(rows), 102)
        rows = [dict(open=100, high=105, low=99, close=104, volume=-3)] * 12
        with self.assertRaisesRegex(k.ShadowHold,'KRONOS_INVALID_FORECAST'):
            k.validate_prediction(FakePredFrame(rows), 102)

    def test_build_row_hash_and_separation(self):
        b = make_bars()
        rows = k.build_rows('AAPL', ASOF, SHA1, SHA2, ASOF,
                            b, [105.12345678] * 12)
        self.assertEqual([r[3] for r in rows], ['1', '5', '12'])
        self.assertEqual(rows[0][17], 'RESEARCH_ONLY')
        self.assertEqual(rows[0][19], k.canonical_sha(rows[0][:19]))
        self.assertEqual(rows[0][6], f'{(105.12345678/102-1)*100:.6f}')
        self.assertEqual(rows[0][14], rows[2][14])
        self.assertEqual(len({r[0] for r in rows}), 3)

    def test_existing_idempotent_and_drift_fails(self):
        rows = k.build_rows('AAPL', ASOF, SHA1, SHA2, ASOF,
                            make_bars(), [103.0] * 12)
        self.assertTrue(k.assert_existing(rows, ASOF, ['AAPL'], SHA1, SHA2))
        with self.assertRaisesRegex(k.ShadowHold,'KRONOS_EXISTING_MODEL_OR_SOURCE_DRIFT'):
            k.assert_existing(rows, ASOF, ['AAPL'], SHA2, SHA1)
        with self.assertRaisesRegex(k.ShadowHold, 'KRONOS_EXISTING_ASOF_PARTIAL'):
            k.assert_existing(rows[:2], ASOF, ['AAPL'], SHA1, SHA2)
        rows[0][6] = '99.0'
        with self.assertRaisesRegex(k.ShadowHold,'KRONOS_EXISTING_ROW_TAMPERED'):
            k.assert_existing(rows, ASOF, ['AAPL'], SHA1, SHA2)

    def test_header_drift_and_dupe(self):
        with self.assertRaisesRegex(k.ShadowHold, 'KRONOS_HEADER_DRIFT'):
            k.normalize_existing([['BAD']])
        row = k.build_rows('AAPL', ASOF, SHA1, SHA2, ASOF,
                           make_bars(), [101] * 12)[0]
        with self.assertRaisesRegex(k.ShadowHold, 'KRONOS_DUPLICATE_ID'):
            k.normalize_existing([list(k.HEADERS), row, row])

    def test_end_to_end_append_and_idempotent_without_model_reexecution(self):
        api = FakeApi()
        fake_writer = types.ModuleType('private_sheet_writer')
        fake_writer.as_cells = lambda rows, sheet_id: {
            'appendCells':{'sheetId':sheet_id,
                           'rows':[{'values':[{'userEnteredValue':{'stringValue':v}}
                                                for v in row]} for row in rows],
                           'fields':'userEnteredValue'}}
        fake_engine = types.ModuleType('engine')
        fake_engine.analyze = lambda symbol, bars, asof: {'sessions':52,'decision':'IZLE'}
        with patch.dict(sys.modules, {'private_sheet_writer':fake_writer, 'engine':fake_engine}), \
             patch.object(k, 'current_authority', return_value=(['AAPL'], SHA1,SHA2,ASOF)), \
             patch.object(k, 'future_xnas_days', return_value=['2026-11-%02d' % d for d in range(7,19)]), \
             patch.object(k, 'predict_one', return_value=[103]*12) as pred:
            result = k.synchronize(api, ASOF, lambda symbols, asof:{'AAPL':make_bars()},
                                   predictor_factory=lambda:object())
            self.assertEqual(result['status'], 'KRONOS_SHADOW_PRIVATE_READBACK_PASS')
            self.assertEqual(api.post_count, 1)
            self.assertEqual(len(api.rows), 3)
            again = k.synchronize(api, ASOF,
                                  lambda *a: self.fail('Must not re-fetch market data'),
                                  predictor_factory=lambda: self.fail('Must not reload model'))
            self.assertEqual(again['status'], 'KRONOS_SHADOW_IDEMPOTENT_READBACK_PASS')
            self.assertEqual(api.post_count, 1)
            self.assertEqual(pred.call_count, 1)

    def test_bad_readback_rejected(self):
        api = FakeApi()
        api.bad_readback = True
        fake_writer = types.ModuleType('private_sheet_writer')
        fake_writer.as_cells = lambda rows, sheet_id: {
            'appendCells':{'sheetId':sheet_id,
                           'rows':[{'values':[{'userEnteredValue':{'stringValue':v}}
                                                for v in row]} for row in rows],
                           'fields':'userEnteredValue'}}
        fake_engine = types.ModuleType('engine')
        fake_engine.analyze = lambda symbol, bars, asof: {'sessions':52,'decision':'IZLE'}
        with patch.dict(sys.modules, {'private_sheet_writer':fake_writer,'engine':fake_engine}), \
             patch.object(k, 'current_authority', return_value=(['AAPL'],SHA1,SHA2,ASOF)), \
             patch.object(k, 'future_xnas_days', return_value=['2026-11-%02d' % d for d in range(7,19)]), \
             patch.object(k, 'predict_one', return_value=[103]*12):
            with self.assertRaisesRegex(k.ShadowHold,'KRONOS_READBACK_MISMATCH'):
                k.synchronize(api, ASOF,lambda *a:{'AAPL':make_bars()}, lambda:object())


    def test_qc_cause_is_distinct_and_immutable_hold_row_has_no_price(self):
        rows = [dict(open=100, high=105, low=99, close=104, volume=-3)] * 12
        with self.assertRaisesRegex(k.ShadowHold,'KRONOS_INVALID_FORECAST_VOLUME'):
            k.validate_prediction(FakePredFrame(rows), 102)
        rows = [dict(open=100, high=100, low=99, close=104, volume=3)] * 12
        with self.assertRaisesRegex(k.ShadowHold,'KRONOS_INVALID_FORECAST_GEOMETRY'):
            k.validate_prediction(FakePredFrame(rows), 102)
        holds = k.build_qc_hold_rows('AAPL', ASOF, SHA1, SHA2, ASOF,
                                      make_bars(), 'KRONOS_INVALID_FORECAST_VOLUME')
        self.assertEqual(len(holds), 3)
        self.assertEqual([r[3] for r in holds], ['1', '5', '12'])
        self.assertEqual({r[17] for r in holds}, {'HOLD_QC_VOLUME'})
        self.assertTrue(all(r[5] == r[6] == r[15] == '' for r in holds))
        self.assertTrue(k.assert_existing(holds, ASOF, ['AAPL'], SHA1, SHA2))

    def test_qc_isolated_cohort_and_fails_open_forecast_promotion(self):
        api = FakeApi()
        fake_writer = types.ModuleType('private_sheet_writer')
        fake_writer.as_cells = lambda rows, sheet_id: {
            'appendCells':{'sheetId':sheet_id,
                           'rows':[{'values':[{'userEnteredValue':{'stringValue':v}}
                                                for v in row]} for row in rows],
                           'fields':'userEnteredValue'}}
        fake_engine = types.ModuleType('engine')
        fake_engine.analyze = lambda symbol, bars, asof: {'sessions':52,'decision':'IZLE'}
        predictions = iter(([103.0]*12, k.ShadowHold('KRONOS_INVALID_FORECAST_VOLUME')))
        def predict(*_):
            result = next(predictions)
            if isinstance(result, Exception):
                raise result
            return result
        with patch.dict(sys.modules, {'private_sheet_writer':fake_writer,'engine':fake_engine}), \
             patch.object(k, 'current_authority', return_value=(['AAPL','MSFT'], SHA1,SHA2,ASOF)), \
             patch.object(k, 'future_xnas_days', return_value=['2026-11-%02d' % d for d in range(7,19)]), \
             patch.object(k, 'predict_one', side_effect=predict):
            result = k.synchronize(api, ASOF,
                                   lambda symbols, asof:{'AAPL':make_bars(),
                                                         'MSFT':make_bars()},
                                   predictor_factory=lambda:object())
            self.assertEqual(result['status'], 'KRONOS_SHADOW_QC_HOLD_READBACK')
            self.assertEqual(result['qc_hold_symbols'], 1)
            self.assertEqual(result['qc_categories'],
                             {'KRONOS_INVALID_FORECAST_VOLUME':1})
            self.assertEqual(len(api.rows), 6)
            self.assertEqual(api.post_count, 1)
            self.assertEqual(sum(r[17]=='RESEARCH_ONLY' for r in api.rows), 3)
            self.assertEqual(sum(r[17]=='HOLD_QC_VOLUME' for r in api.rows), 3)
            again = k.synchronize(api, ASOF,
                                  lambda *a: self.fail('Must not repeat provider call'),
                                  predictor_factory=lambda: self.fail('Must not reload AI'))
            self.assertEqual(again['status'], 'KRONOS_SHADOW_IDEMPOTENT_QC_HOLD')
            self.assertEqual(api.post_count, 1)


    def test_research_completed_friday_accepted_saturday_but_not_before_close_or_stale(self):
        fake_engine = types.ModuleType('engine')
        fake_engine.trading_asof = lambda instant: date(2026, 11, 6)
        class Stamp:
            def to_pydatetime(self):
                return datetime(2026, 11, 6, 21, 0, tzinfo=timezone.utc)
        class Cal:
            def session_close(self, session):
                self_session = str(session)
                if self_session != '2026-11-06':
                    raise AssertionError('unexpected XNAS session')
                return Stamp()
        fake_ec = types.ModuleType('exchange_calendars')
        fake_ec.get_calendar = lambda name: Cal() if name == 'XNAS' else None
        with patch.dict(sys.modules, {'engine':fake_engine, 'exchange_calendars':fake_ec}):
            self.assertEqual(k.eligible_shadow_asof(
                datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc)),
                '2026-11-06')
            self.assertIsNone(k.eligible_shadow_asof(
                datetime(2026, 11, 6, 20, 50, tzinfo=timezone.utc)))
            self.assertIsNone(k.eligible_shadow_asof(
                datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc)))
            with self.assertRaisesRegex(k.ShadowHold, 'KRONOS_UNAWARE_NOW'):
                k.eligible_shadow_asof(datetime(2026, 11, 7, 10, 0))


    def test_legacy_v1_archived_on_first_new_v2_asof_without_private_write(self):
        import contextlib
        import io
        fake_writer=types.ModuleType("private_sheet_writer")
        fake_writer.SheetApi=lambda *_: self.fail("V1 must not initialize private writer")
        fake_engine=types.ModuleType("engine")
        with patch.dict(sys.modules,{"private_sheet_writer":fake_writer,
                                    "engine":fake_engine}), \
             patch.object(k,"eligible_shadow_asof",
                          return_value="2026-11-09"):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                result=k.main(["--asof","2026-11-09"])
        self.assertEqual(result,0)
        self.assertIn("KRONOS_SHADOW_V1_ARCHIVED_NO_NEW_WRITES",
                      output.getvalue())


if __name__ == '__main__':
    unittest.main()
