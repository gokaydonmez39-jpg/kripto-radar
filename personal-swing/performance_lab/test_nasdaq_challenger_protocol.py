"""A13 scientific challenger / anti-overfit safety regression. Synthetic only."""
from __future__ import annotations
from copy import deepcopy
import unittest

import exchange_calendars as ec

from nasdaq_performance_guard import EvidenceBlocked
from nasdaq_challenger_protocol import (preregister,signflip_day_pvalue,
                                        compare_registered_trials)

CAL=ec.get_calendar('XNAS')
ORIGIN='2026-10-22'


def d(i):
    return CAL.session_offset(CAL.date_to_session(ORIGIN),i).date().isoformat()


def plan():
    return {'registered_asof':d(0),'holdout_start':d(1),
            'holdout_end':d(42),'baseline_sha':'a'*64,'policy_sha':'b'*64,
            'hypotheses':[
                {'id':'XRAY-H-0001','lever':'RSI_BAND_RESEARCH',
                 'falsifier':'Reject RSI challenger if paired unseen net returns do not beat baseline.'},
                {'id':'XRAY-H-0002','lever':'RVOL_RESEARCH',
                 'falsifier':'Reject RVOL challenger if day-cluster randomization shows no stable edge.'}]}


def cohort(lever=1.0, n=80, day_count=40):
    out=[]
    for i in range(n):
        day=d(1+i%day_count)
        out.append({'episode_id':day+'|SIM%04d'%i,
                    'signal_asof':day,'outcome':'COMPLETE',
                    'challenger_net_pct':float(lever),
                    'baseline_net_pct':0.,
                    'baseline_policy_sha':'b'*64})
    return out


class ScientificTrialSafety(unittest.TestCase):
    def test_registration_fingerprint_stable_and_never_executes(self):
        x=preregister(plan())
        self.assertEqual(x['state'],'FROZEN_PROPOSAL_ONLY')
        self.assertEqual(preregister(deepcopy(plan()))['digest'],x['digest'])
        self.assertFalse(x['automatic_code_change'])
        self.assertFalse(x['trade_execution'])

    def test_temporal_leakage_rejected(self):
        p=plan()
        p['registered_asof']=p['holdout_start']
        with self.assertRaisesRegex(EvidenceBlocked,'PREREG_HOLDOUT_LEAKAGE'):
            preregister(p)

    def test_unapproved_lever_and_duplicate_hypothesis_rejected(self):
        p=plan()
        p['hypotheses'][0]['lever']='AUTOBUY'
        with self.assertRaisesRegex(EvidenceBlocked,'PREREG_LEVER_NOT_ALLOWED'):
            preregister(p)
        p=plan()
        p['hypotheses'][1]['id']=p['hypotheses'][0]['id']
        with self.assertRaisesRegex(EvidenceBlocked,'PREREG_HYPOTHESIS_ID_DUPLICATE'):
            preregister(p)

    def test_no_partial_hypothesis_family_allowed(self):
        with self.assertRaisesRegex(EvidenceBlocked,'TRIAL_FULL_FAMILY_REQUIRED'):
            compare_registered_trials(preregister(plan()),{'XRAY-H-0001':cohort()})

    def test_paired_zero_effect_is_not_discovered_alpha(self):
        z=[{'asof':d(i+1),'delta_pct':0.0} for i in range(35)]
        p=signflip_day_pvalue(z)
        self.assertEqual(p['exploratory_two_sided_p'],1.)
        self.assertEqual(p['release'],'NO_GO')

    def test_same_day_80_observations_are_not_80_independent_days(self):
        shared=cohort(n=80,day_count=1)
        fam={'XRAY-H-0001':shared,
             'XRAY-H-0002':deepcopy(shared)}
        r=compare_registered_trials(preregister(plan()),fam)
        self.assertTrue(all(h['underpowered'] for h in r['trials']))
        self.assertTrue(all(h['distinct_signal_days']==1 for h in r['trials']))
        self.assertTrue(r['human_review_required'])

    def test_positive_effect_still_never_autopromotes(self):
        p=preregister(plan())
        fam={'XRAY-H-0001':cohort(1.4),
             'XRAY-H-0002':cohort(0.)}
        r=compare_registered_trials(p,fam)
        self.assertEqual(r['registered_hypotheses'],2)
        self.assertEqual(r['status'],'HOLD_EXTERNAL_PROVENANCE_AND_POWER_REVIEW')
        self.assertFalse(r['rule_change'])
        self.assertFalse(r['orders'])
        self.assertEqual(r['external_source_attestation'],'NOT_VERIFIED')
        self.assertEqual(r['multiple_comparison_control'],'EXPLORATORY_HOLM')
        self.assertTrue(all(0<=x['holm_exploratory_p']<=1 for x in r['trials']))

    def test_mutated_registration_object_rejected(self):
        frozen=preregister(plan())
        frozen['plan']['baseline_sha']='c'*64
        with self.assertRaisesRegex(EvidenceBlocked,'PREREG_IMMUTABLE_CONFLICT'):
            compare_registered_trials(frozen,
                {'XRAY-H-0001':cohort(),'XRAY-H-0002':cohort()})

    def test_future_observation_rejected(self):
        fam={'XRAY-H-0001':cohort(),'XRAY-H-0002':cohort()}
        fam['XRAY-H-0001'][0]['signal_asof']=d(60)
        fam['XRAY-H-0001'][0]['episode_id']=d(60)+'|SIM0000'
        with self.assertRaisesRegex(EvidenceBlocked,'TRIAL_TIME_LEAKAGE'):
            compare_registered_trials(preregister(plan()),fam)

    def test_missing_baseline_policy_fails(self):
        fam={'XRAY-H-0001':cohort(),'XRAY-H-0002':cohort()}
        fam['XRAY-H-0002'][0]['baseline_policy_sha']='c'*64
        with self.assertRaisesRegex(EvidenceBlocked,'TRIAL_BASELINE_DRIFT'):
            compare_registered_trials(preregister(plan()),fam)

    def test_hypothesis_cohort_selection_bias_fails(self):
        fam={'XRAY-H-0001':cohort(),'XRAY-H-0002':cohort(n=79)}
        with self.assertRaisesRegex(EvidenceBlocked,'TRIAL_SURVIVORSHIP_OR_COHORT_MISMATCH'):
            compare_registered_trials(preregister(plan()),fam)

    def test_censored_episode_cannot_have_pnl(self):
        fam={'XRAY-H-0001':cohort(),'XRAY-H-0002':cohort()}
        fam['XRAY-H-0001'][0]['outcome']='CENSORED'
        with self.assertRaisesRegex(EvidenceBlocked,'TRIAL_CENSORED_OUTCOME_INFLATION'):
            compare_registered_trials(preregister(plan()),fam)

    def test_never_publish_real_fill_or_signal_delivery(self):
        r=compare_registered_trials(preregister(plan()),
            {'XRAY-H-0001':cohort(),'XRAY-H-0002':cohort()})
        self.assertFalse(r['notification_delivery'])
        self.assertTrue(all(x['release']=='NO_GO' for x in r['trials']))


if __name__=='__main__':
    unittest.main()
