#!/usr/bin/env python3
"""Adversarial offline synthetic-only tests, no provider/broker/HTTP calls."""
import copy
import json
from pathlib import Path
import unittest

from xray_v46_offline_pagination_proof import audit, PaginationBlocked, time_ns

PATH = Path(__file__).with_name('xray_v46_a2_synthetic_pages.json')


def fixture():
    return json.loads(PATH.read_text(encoding='utf-8'))


class PaginationAuditTest(unittest.TestCase):
    def reject(self, mutate):
        value = fixture()
        mutate(value)
        with self.assertRaises(PaginationBlocked):
            audit(value)

    def test_three_page_2_symbols_sorted_and_all_noncertifying(self):
        result = audit(fixture())
        self.assertEqual((result['fixture_page_count'], result['fixture_synthetic_rows_count']), (3, 4))
        self.assertEqual(result['fixture_symbol_counts'], {'AAPL': 3, 'MSFT': 1})
        self.assertTrue(result['synthetic_page_tokens_exhausted'])
        for k in ('actual_provider_request_performed', 'actual_sip_pages_attested',
                  'provider_entitlements_attested', 'real_session_volume_reconciled',
                  'a0_release_ready', 'a2_release_ready', 'canonical_price_pass',
                  'issuer_mc_pass', 'g9_pass', 'c417_pass', 'iphone_receipt_attested'):
            with self.subTest(k=k): self.assertFalse(result[k])
        self.assertEqual((result['registered_r92_count'], result['execution'],
                          result['real_money']), (0, 'NONE', 'NO-GO'))

    def test_first_page_one_symbol_not_all_symbols_exhausted(self):
        self.reject(lambda d: d['pages'].__setitem__(0, {**d['pages'][0], 'next_page_token': None}))

    def test_truncated_chain(self):
        self.reject(lambda d: d['pages'].pop())

    def test_missing_second_page(self):
        self.reject(lambda d: d['pages'].pop(1))

    def test_repeated_token_cycle(self):
        self.reject(lambda d: d['pages'][1].__setitem__('next_page_token', 'tok_a'))

    def test_forged_next_token(self):
        self.reject(lambda d: d['pages'][0].__setitem__('next_page_token', '!!'))

    def test_orphan_request_token(self):
        self.reject(lambda d: d['pages'][1].__setitem__('requested_page_token', 'random'))

    def test_nonterminal_empty_page(self):
        self.reject(lambda d: d['pages'][1].__setitem__('synthetic_rows', []))

    def test_terminal_early_extra_pages(self):
        self.reject(lambda d: d['pages'][1].__setitem__('next_page_token', None))

    def test_total_limit_not_per_symbol(self):
        self.reject(lambda d: d['pages'][0]['synthetic_rows'].append(
            {'S':'MSFT','t':'2026-10-22T14:00:00.000000300Z','synthetic_key':'syn_bad'}))

    def test_symbol_first_sorting(self):
        self.reject(lambda d: d['pages'][0]['synthetic_rows'][1].__setitem__('S', 'MSFT'))

    def test_nanosecond_backwards_even_within_same_microsecond(self):
        self.reject(lambda d: d['pages'][0]['synthetic_rows'][1].__setitem__(
            't','2026-10-22T14:00:00.000000001Z'))

    def test_same_nanosecond_distinct_keys_allowed(self):
        d = fixture()
        d['pages'][0]['synthetic_rows'][1]['t'] = d['pages'][0]['synthetic_rows'][0]['t']
        self.assertEqual(audit(d)['fixture_synthetic_rows_count'], 4)

    def test_duplicate_synthetic_replay_id(self):
        self.reject(lambda d: d['pages'][1]['synthetic_rows'][0].__setitem__(
            'synthetic_key', 'syn_a1'))

    def test_wrong_feed_iex_not_sip(self):
        self.reject(lambda d: d['query'].__setitem__('feed','iex'))

    def test_wrong_sort_direction(self):
        self.reject(lambda d: d['query'].__setitem__('sort','desc'))

    def test_asof_drift_across_pages(self):
        self.reject(lambda d: d['pages'][1]['query'].__setitem__('asof','2026-10-21'))

    def test_time_bounds_drift(self):
        self.reject(lambda d: d['pages'][2]['query'].__setitem__('end','2026-10-22T21:00:00Z'))

    def test_row_outside_query_range(self):
        self.reject(lambda d: d['pages'][0]['synthetic_rows'][0].__setitem__(
            't','2026-10-22T12:00:00Z'))

    def test_reject_unrepresentable_subnanosecond(self):
        self.reject(lambda d: d['pages'][0]['synthetic_rows'][0].__setitem__(
            't','2026-10-22T14:00:00.0000000001Z'))

    def test_allow_equivalent_offset_timestamps(self):
        d=fixture()
        d['pages'][2]['synthetic_rows'][0]['t']='2026-10-22T10:30:00-04:00'
        self.assertEqual(audit(d)['fixture_synthetic_rows_count'], 4)

    def test_invalid_symbols_and_types(self):
        for value in (['aapl','MSFT'],['AAPL','AAPL'],['MSFT','AAPL'],[None],[],['A/PL']):
            with self.subTest(value=value):
                self.reject(lambda d: d['query'].__setitem__('symbols',value))

    def test_duplicate_page_or_unknown_symbol(self):
        self.reject(lambda d: d['pages'][2]['synthetic_rows'][0].__setitem__('S','TSLA'))

    def test_no_vendor_price_or_keys_permitted_in_row(self):
        self.reject(lambda d: d['pages'][0]['synthetic_rows'][0].__setitem__('p',100.0))

    def test_false_vendor_authority_rejected(self):
        self.reject(lambda d: d.__setitem__('source_complete',True))

    def test_fake_source_label_rejected(self):
        self.reject(lambda d: d.__setitem__('sample_type','PROVIDER_LIVE_SIP'))

    def test_invalid_page_limit_boolean(self):
        self.reject(lambda d: d['query'].__setitem__('limit',True))

    def test_bad_asof(self):
        self.reject(lambda d: d['query'].__setitem__('asof','2026-02-30'))

    def test_bad_timestamp_and_epoch(self):
        for txt in ('2026-10-22T14:00:00','2026-10-22T24:00:00Z','2026-10-22T14:00Z'):
            with self.subTest(txt=txt), self.assertRaises(PaginationBlocked):
                time_ns(txt)

    def test_input_immutable(self):
        inp=fixture();before=copy.deepcopy(inp)
        audit(inp)
        self.assertEqual(inp,before)


if __name__ == '__main__':
    unittest.main()