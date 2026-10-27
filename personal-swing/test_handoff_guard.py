"""Negative contract for private Github EOD handoff. No vendor calls."""
import copy
import hashlib
import unittest
import handoff_guard as h

SYMS=[f'S{i:03d}' for i in range(477)]
SCOPE=hashlib.sha256(('\n'.join(SYMS)+'\n').encode()).hexdigest()
POLICY='f'*64


def sample():
    rows=[{'symbol':symbol,'decision':'ELE','asof_et':'2026-10-26'}
          for symbol in SYMS]
    rows[0].update(decision='AL',close=100.,atr14=2.5,
                   indicative_stop=95.,indicative_target_2r=110.,
                   relative_iex_volume=1.5,rsi14=55.,
                   sma20=98.,sma50=96.,prior_high20=99.,atr_risk_pct=5.)
    return {'scope_sha256':SCOPE,'analysis_fingerprint_sha256':POLICY,
        'requested_symbols':477,'processed_symbols':477,'valid_data_symbols':477,
        'insufficient_data_symbols':0,'remaining_symbols':0,
        'coverage_complete':True,'valid_data_coverage_complete':True,
        'new_signal_publishable':True,'not_broker':True,'orders_sent':0,
        'auto_trading':False,'failed_groups':[],'asof_et':'2026-10-26',
        'counts':{'START':477,'TEKNIK_AL_ADAYI':1,'YAKIN_IZLE':0,
                  'ELE':476,'VERI_YETERSIZ':0},'rows':rows}


def check(snap,syms=SYMS,scope=SCOPE,policy=POLICY):
    return h.validate_snapshot(snap,syms,scope_sha=scope,policy_sha=policy)


class FailClosedEodHandoff(unittest.TestCase):
    def test_valid_477_and_one_al(self):
        r=check(sample())
        self.assertEqual(r['new_signal_count'],1)
        self.assertTrue(r['safe_to_use_privately'])
        self.assertFalse(r['device_ack'])

    def test_wrong_universe_count(self):
        with self.assertRaises(h.HandoffInvalid):
            check(sample(),SYMS[:-1])

    def test_wrong_exact_scope_sha(self):
        with self.assertRaises(h.HandoffInvalid):
            check(sample(),scope='a'*64)

    def test_wrong_algorithm_fingerprint(self):
        with self.assertRaises(h.HandoffInvalid):
            check(sample(),policy='a'*64)

    def test_invalid_al_stop_target_rejected(self):
        for price in [100.,110.,-1.]:
            snap=sample();snap['rows'][0]['indicative_stop']=price
            with self.subTest(price=price),self.assertRaises(h.HandoffInvalid):
                check(snap)

    def test_non_2r_or_nan_rejected(self):
        for target in [120.,float('nan')]:
            snap=sample();snap['rows'][0]['indicative_target_2r']=target
            with self.subTest(target=target),self.assertRaises(h.HandoffInvalid):
                check(snap)

    def test_missing_or_duplicate_row_rejected(self):
        for action in ('missing','duplicate'):
            snap=sample()
            if action=='missing':snap['rows'].pop()
            else:snap['rows'][-1]=dict(snap['rows'][0])
            with self.subTest(action=action),self.assertRaises(h.HandoffInvalid):
                check(snap)

    def test_mixed_asof_rejected(self):
        snap=sample();snap['rows'][30]['asof_et']='2026-10-23'
        with self.assertRaises(h.HandoffInvalid):check(snap)

    def test_partial_vendor_coverage_fail_closed(self):
        snap=sample();snap['valid_data_symbols']=476
        with self.assertRaises(h.HandoffInvalid):check(snap)

    def test_false_status_never_treated_as_true(self):
        snap=sample();snap['new_signal_publishable']=1
        with self.assertRaises(h.HandoffInvalid):check(snap)

    def test_false_count_fail_closed(self):
        snap=sample();snap['counts']['TEKNIK_AL_ADAYI']=2
        with self.assertRaises(h.HandoffInvalid):check(snap)

    def test_execution_and_failed_groups_block(self):
        for key,val in [('not_broker',False),('orders_sent',1),
                        ('auto_trading',True),('failed_groups',[{'error':'MISSING'}])]:
            snap=sample();snap[key]=val
            with self.subTest(key=key),self.assertRaises(h.HandoffInvalid):
                check(snap)

    def test_invalid_asof_rejected(self):
        for day in ('2026-02-31','26-10-2026',None):
            snap=sample();snap['asof_et']=day
            with self.subTest(day=day),self.assertRaises(h.HandoffInvalid):
                check(snap)

    def test_corrupt_al_policy_fields_rejected(self):
        """A tampered checkpoint must never smuggle an AL past handoff."""
        bad=[
            ('close',4.99), ('relative_iex_volume',1.299),
            ('rsi14',44.99), ('rsi14',75.01),
            ('sma20',101.), ('sma50',99.),
            ('prior_high20',101.), ('atr_risk_pct',8.01),
            ('atr14',0.), ('atr14',float('nan'))
        ]
        for field,value in bad:
            with self.subTest(field=field,value=value):
                snap=sample()
                snap['rows'][0][field]=value
                with self.assertRaises(h.HandoffInvalid):
                    check(snap)

    def test_al_boundary_values_not_falsely_rejected(self):
        snap=sample()
        row=snap['rows'][0]
        row['relative_iex_volume']=1.3
        row['rsi14']=45.
        row['atr14']=4.
        row['indicative_stop']=92.
        row['indicative_target_2r']=116.
        row['atr_risk_pct']=8.
        self.assertEqual(check(snap)['new_signal_count'],1)
        row['rsi14']=75.
        self.assertEqual(check(snap)['new_signal_count'],1)

    def test_optimizer_mode_no_assert_dependency(self):
        self.assertNotIn('assert ',open(h.__file__,encoding='utf-8').read())


if __name__=='__main__':
    unittest.main()
