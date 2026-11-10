"""Synthetic tamper tests of a public calendar fixture; NO provider I/O."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import unittest
from xray_v43_a1_calendar_scope import audit, ScopeBlocked, expected_days

FIXTURE = Path(__file__).with_name('xray_v43_a1_calendar_snapshot_20261022.json')


def snapshot():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


class CalendarWitness(unittest.TestCase):
    def test_positive_only_partial(self):
        result = audit(snapshot())
        self.assertEqual(result['last_30_trading_dates_count'], 30)
        self.assertEqual(result['last_30_trading_dates_first'], '2026-09-11')
        self.assertEqual(result['last_30_trading_dates_last'], '2026-10-22')
        self.assertEqual(result['calendar_rows_checked'], 37)
        self.assertTrue(result['a1_calendar_date_time_subscope_checked'])
        for k in ('a1_release_ready', 'a0_account_rights_attested',
                  'a2_pagination_complete', 'a3_sip_settled_volume_pass',
                  'canonical_price_pass', 'issuer_mc_pass', 'g9_pass',
                  'c417_pass', 'iphone_receipt_attested',
                  'historical_trade_or_quote_data_checked',
                  'official_symbol_venue_listing_scope_attested'):
            self.assertIs(result[k], False)
        self.assertEqual(result['registered_r92_count'], 0)
        self.assertEqual(result['orders'], [])
        self.assertEqual(result['execution'], 'NONE')
        self.assertEqual(result['real_money'], 'NO-GO')

    def bad(self, mutate):
        d = snapshot()
        mutate(d)
        with self.assertRaises(ScopeBlocked):
            audit(d)

    def test_missing_day(self):
        self.bad(lambda d: d['calendar'].pop(12))

    def test_duplicate_day(self):
        self.bad(lambda d: d['calendar'].__setitem__(4, copy.deepcopy(d['calendar'][3])))

    def test_swapped_days(self):
        self.bad(lambda d: d['calendar'].reverse())

    def test_forged_holiday_trading(self):
        def modify(d):
            d['calendar'][4] = {'date':'2026-09-07','open':'2026-09-07T09:30:00','close':'2026-09-07T16:00:00'}
        self.bad(modify)

    def test_weekend_insertion(self):
        def modify(d):
            d['calendar'][6] = {'date':'2026-09-12','open':'2026-09-12T09:30:00','close':'2026-09-12T16:00:00'}
        self.bad(modify)

    def test_forged_early_close(self):
        self.bad(lambda d: d['calendar'][-1].__setitem__('close', '2026-10-22T13:00:00'))

    def test_wrong_open_clock(self):
        self.bad(lambda d: d['calendar'][-1].__setitem__('open', '2026-10-22T09:00:00'))

    def test_stale_asof(self):
        self.bad(lambda d: d.__setitem__('asof_et', '2026-10-21'))

    def test_incorrect_source_claim(self):
        self.bad(lambda d: d.__setitem__('source_type', 'OFFICIAL_NASDAQ_SIGNED'))

    def test_incorrect_official_reference(self):
        self.bad(lambda d: d.__setitem__('official_holiday_reference','https://example.org/'))

    def test_timestamp_conflict(self):
        self.bad(lambda d: d['calendar'][0].__setitem__('open','2026-09-02T09:30:00'))

    def test_future_day(self):
        self.bad(lambda d: d['calendar'][-1].__setitem__('date', '2026-10-23'))

    def test_unexpected_extra_field(self):
        self.bad(lambda d: d['calendar'][0].__setitem__('provider_claimed_certified',True))

    def test_no_future_gap_in_expected(self):
        self.assertEqual(len(expected_days()),37)
        self.assertNotIn('2026-09-07',expected_days())
        self.assertIn('2026-10-15',expected_days())

    def test_does_not_mutate_snapshot(self):
        d=snapshot();old=copy.deepcopy(d)
        audit(d)
        self.assertEqual(d,old)


if __name__ == '__main__':
    unittest.main()