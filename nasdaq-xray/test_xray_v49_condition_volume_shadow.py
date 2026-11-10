"""Synthetic-only provider-specific condition rules, adversarial regressions."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import unittest

from xray_v49_condition_volume_shadow import audit, eligibility, synth_bar, ConditionBlocked

FIXTURE=Path(__file__).with_name('xray_v49_condition_counterexamples_synthetic.json')

def load():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))

class ConditionTests(unittest.TestCase):
    def reject_mutation(self, mutate):
        d=load(); mutate(d)
        with self.assertRaises(ConditionBlocked):audit(d)

    def test_positive_is_still_blocked(self):
        r=audit(load())
        self.assertTrue(r['provider_specific_partial_table_only'])
        self.assertTrue(r['oddlot_only_bar_may_be_absent_despite_trades'])
        self.assertTrue(r['synthetic_bar_volume_and_vwap_denominator_can_differ'])
        self.assertTrue(r['corrected_close_can_move_daily_close_without_increasing_volume'])
        for k in ('complete_sale_condition_table_verified',
                  'actual_sip_trade_cancel_correction_replayed',
                  'official_settled_consolidated_volume_reconciled',
                  'closing_auction_volume_reconciled','rth_vs_extended_hours_partition_attested',
                  'a0_rights_attested','a1_venue_session_attested',
                  'a2_live_pages_attested','a3_release_ready',
                  'canonical_price_pass','issuer_mc_pass','g9_pass','c417_pass',
                  'iphone_receipt_attested'):
            with self.subTest(k=k):self.assertIs(r[k],False)
        self.assertEqual((r['registered_r92_count'],r['execution'],r['real_money']),(0,'NONE','NO-GO'))
        self.assertEqual(r['orders'],[])
        self.assertTrue(r['unknown_never_pass'])

    def test_regular_C_eligible_both(self):
        self.assertEqual(eligibility(['@'],'M'),(2,1,1))
        self.assertEqual(eligibility(['@'],'D'),(2,1,1))

    def test_odd_lot_volume_without_price(self):
        self.assertEqual(eligibility(['I'],'M'),(0,0,1))
        self.assertEqual(eligibility(['I'],'D'),(0,0,1))

    def test_oddlot_only_can_hide_bar(self):
        a=synth_bar([{'conditions':['I'],'synthetic_price':'10.00','synthetic_size':7}],'M')
        self.assertEqual(a['synthetic_bar_volume'],7)
        self.assertFalse(a['synthetic_bar_emitted'])
        self.assertIsNone(a['synthetic_vwap'])

    def test_multi_condition_strictest(self):
        self.assertEqual(eligibility(['@','4','I'],'D'),(0,0,1))
        self.assertEqual(eligibility(['@','4'],'D'),(1,1,1))
        self.assertEqual(eligibility(['@','4'],'M'),(0,0,1))

    def test_P_updates_daily_high_not_minute_high(self):
        self.assertEqual(eligibility(['P'],'M'),(0,0,1))
        self.assertEqual(eligibility(['P'],'D'),(1,1,1))

    def test_other_time_dependent_Z_and_T(self):
        self.assertEqual(eligibility(['Z'],'M'),(0,0,1))
        self.assertEqual(eligibility(['Z'],'D'),(1,1,1))
        self.assertEqual(eligibility(['T'],'M'),(2,1,1))
        self.assertEqual(eligibility(['T'],'D'),(0,0,1))

    def test_corrected_consolidated_close_zero_volume(self):
        self.assertEqual(eligibility(['9'],'M'),(0,0,0))
        self.assertEqual(eligibility(['9'],'D'),(2,1,0))

    def test_9_not_emitted_alone_due_to_zero_volume(self):
        a=synth_bar([{'conditions':['9'],'synthetic_price':'10.25','synthetic_size':0}],'D')
        self.assertEqual(a['synthetic_bar_volume'],0)
        self.assertFalse(a['synthetic_bar_emitted'])

    def test_corrected_close_moves_daily_only_not_volume(self):
        seq=load()['cases'][2]['synthetic_trades']
        m=synth_bar(seq,'M');d=synth_bar(seq,'D')
        self.assertEqual(m['synthetic_close'],Decimal('10.00'))
        self.assertEqual(d['synthetic_close'],Decimal('10.25'))
        self.assertEqual(m['synthetic_bar_volume'],d['synthetic_bar_volume'])
        self.assertEqual(d['synthetic_bar_volume'],100)

    def test_vwap_denominator_diff_from_bar_volume(self):
        seq=load()['cases'][1]['synthetic_trades']
        d=synth_bar(seq,'D')
        self.assertEqual(d['synthetic_bar_volume'],115)
        self.assertEqual(d['synthetic_vwap_basis'],100)
        self.assertEqual(d['synthetic_vwap'],Decimal('10'))

    def test_yellow_price_oc_only_if_not_set(self):
        a=synth_bar([
            {'conditions':['@'],'synthetic_price':'10','synthetic_size':100},
            {'conditions':['4'],'synthetic_price':'11','synthetic_size':10},
        ],'D')
        self.assertEqual(a['synthetic_close'],Decimal('10'))
        self.assertEqual(a['synthetic_high'],Decimal('11'))
        self.assertEqual(a['synthetic_bar_volume'],110)

    def test_yellow_can_seed_unset_ohlc(self):
        a=synth_bar([
            {'conditions':['4'],'synthetic_price':'11','synthetic_size':10},
            {'conditions':['@'],'synthetic_price':'10','synthetic_size':100},
        ],'D')
        self.assertEqual(a['synthetic_open'],Decimal('11'))
        self.assertEqual(a['synthetic_close'],Decimal('10'))

    def test_W_vwap_restricted(self):
        self.assertEqual(eligibility(['W'],'D'),(0,0,1))

    def test_M_Q_official_price_without_bar_contribution(self):
        self.assertEqual(eligibility(['M'],'D'),(0,0,0))
        self.assertEqual(eligibility(['Q'],'D'),(0,0,0))

    def test_empty_or_unknown_conditions_fail_closed(self):
        for cond in ([],['?'],[' '],['@','?'],['@','@'],None,['@']*5,['i']):
            with self.subTest(cond=cond), self.assertRaises(ConditionBlocked):
                eligibility(cond,'D')

    def test_wrong_bar_kind_fail_closed(self):
        for kind in ('W','D1','',None,1):
            with self.subTest(kind=kind),self.assertRaises(ConditionBlocked):
                eligibility(['@'],kind)

    def test_negative_schema_wrong_feed(self):
        self.reject_mutation(lambda d:d.__setitem__('tape','A'))

    def test_negative_false_market_authority(self):
        self.reject_mutation(lambda d:d.__setitem__('certified_AL',True))

    def test_negative_forged_source(self):
        self.reject_mutation(lambda d:d.__setitem__('reference','https://example.com/'))

    def test_negative_not_synthetic_source(self):
        self.reject_mutation(lambda d:d.__setitem__('sample_type','REAL_SIP_TRADES'))

    def test_negative_missing_case(self):
        self.reject_mutation(lambda d:d['cases'].pop())

    def test_negative_duplicated_case(self):
        self.reject_mutation(lambda d:d['cases'][1].__setitem__('name','ODDLOT_ONLY'))

    def test_negative_unknown_case(self):
        self.reject_mutation(lambda d:d['cases'][1].__setitem__('name','PROVIDER_GO'))

    def test_negative_bad_only_oddlot(self):
        self.reject_mutation(lambda d:d['cases'][0]['synthetic_trades'][0].__setitem__('conditions',['@']))

    def test_negative_zero_regular_trade(self):
        self.reject_mutation(lambda d:d['cases'][1]['synthetic_trades'][0].__setitem__('synthetic_size',0))

    def test_negative_zero_not_special(self):
        self.reject_mutation(lambda d:d['cases'][2]['synthetic_trades'][1].__setitem__('conditions',['I']))

    def test_negative_invalid_price_inf(self):
        self.reject_mutation(lambda d:d['cases'][1]['synthetic_trades'][0].__setitem__('synthetic_price','NaN'))

    def test_negative_invalid_price_type(self):
        self.reject_mutation(lambda d:d['cases'][1]['synthetic_trades'][0].__setitem__('synthetic_price',10.0))

    def test_negative_bool_size(self):
        self.reject_mutation(lambda d:d['cases'][1]['synthetic_trades'][0].__setitem__('synthetic_size',True))

    def test_negative_raw_vendor_field(self):
        self.reject_mutation(lambda d:d['cases'][1]['synthetic_trades'][0].__setitem__('trade_id',9823))

    def test_negative_vendor_correction_not_incomplete_input(self):
        self.reject_mutation(lambda d:d['cases'][2]['synthetic_trades'][0].__setitem__('correction_complete',True))

    def test_input_not_mutated(self):
        obj=load();old=deepcopy(obj);audit(obj);self.assertEqual(obj,old)

if __name__=='__main__':
    unittest.main()