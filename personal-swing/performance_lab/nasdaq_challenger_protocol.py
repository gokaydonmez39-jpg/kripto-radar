"""XRAY A13 deterministic experiment admission: immutable pre-registration and
day-cluster negative-control statistics. No promotion, trading, model calls or IO.
"""
from __future__ import annotations
from collections import defaultdict
import hashlib
import json
import math
import random
import re

import exchange_calendars as ec
from nasdaq_performance_guard import EvidenceBlocked, iso, need

SHA=re.compile(r'^[0-9a-f]{64}$')
HID=re.compile(r'^XRAY-H-[0-9]{4}$')
ALLOWED={'RSI_BAND_RESEARCH','RVOL_RESEARCH','ATR_RISK_RESEARCH',
         'LIQUIDITY_RESEARCH','ENTRY_TIME_RESEARCH'}


def preregister(plan):
    """A human-approved proposal contract, NOT an approval event."""
    need(type(plan) is dict and
         set(plan)=={'registered_asof','holdout_start','holdout_end',
                     'baseline_sha','policy_sha','hypotheses'},'PREREG_SCHEMA')
    start=iso(plan['registered_asof'])
    hs=iso(plan['holdout_start'])
    he=iso(plan['holdout_end'])
    cal=ec.get_calendar('XNAS')
    need(all(cal.is_session(d.isoformat()) for d in (start,hs,he)) and
         start < hs <= he,'PREREG_HOLDOUT_LEAKAGE_OR_NONSESSION')
    need(all(type(plan[k]) is str and SHA.fullmatch(plan[k])
             for k in ('baseline_sha','policy_sha')),'PREREG_NO_FROZEN_BASELINE')
    hs_list=plan['hypotheses']
    need(type(hs_list) is list and 1 <= len(hs_list) <= 12,
         'PREREG_HYPOTHESES_LIMIT')
    ids=set()
    for h in hs_list:
        need(type(h) is dict and
             set(h)=={'id','lever','falsifier'},'PREREG_HYPOTHESIS_SCHEMA')
        need(type(h['id']) is str and HID.fullmatch(h['id']) and
             h['id'] not in ids, 'PREREG_HYPOTHESIS_ID_DUPLICATE')
        ids.add(h['id'])
        need(h['lever'] in ALLOWED, 'PREREG_LEVER_NOT_ALLOWED')
        need(type(h['falsifier']) is str and 20 <= len(h['falsifier']) <= 400,
             'PREREG_FALSIFIER_REQUIRED')
    digest=hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'digest':digest,'plan':plan,'state':'FROZEN_PROPOSAL_ONLY',
            'automatic_code_change':False,'trade_execution':False}


def signflip_day_pvalue(paired, *,trials=4095,seed=20261028):
    """Exploratory two-sided randomization by signal DAY, not independent signals."""
    need(type(paired) is list and len(paired)>0,'PAIRS_EMPTY')
    need(type(trials) is int and 999<=trials<=9999,'PERMUTATION_BUDGET')
    byday=defaultdict(list)
    for item in paired:
        need(type(item) is dict and set(item)=={'asof','delta_pct'},
             'PAIR_SCHEMA')
        iso(item['asof'])
        value=item['delta_pct']
        need(type(value) in (int,float) and math.isfinite(value),
             'PAIR_FINITE_DELTA')
        byday[item['asof']].append(value)
    keys=sorted(byday)
    group_sums=[sum(byday[k]) for k in keys]
    total=len(paired)
    obs=sum(group_sums)/total
    rng=random.Random(seed)
    exceed=0
    for _ in range(trials):
        sample=sum(v*(1 if rng.getrandbits(1) else -1) for v in group_sums)/total
        exceed+=abs(sample)>=abs(obs)-1e-12
    return {'mean_delta_pct':round(obs,6),
            'exploratory_two_sided_p':round((exceed+1)/(trials+1),6),
            'completed_episodes':total,
            'distinct_signal_days':len(keys),
            'uncertainty':'DAY_CLUSTER_SIGN_FLIP_REQUIRES_SYMMETRY_AND_EXCHANGEABILITY',
            'release':'NO_GO'}


def compare_registered_trials(frozen, cohorts):
    """Holm for the FULL fixed registered family, including bad/weak members.

    A missing or incomplete hypothesis blocks inference for the entire family.
    No caller-provided power, sourced benchmark, OOS or fill claim is trusted.
    """
    need(type(frozen) is dict and frozen.get('state')=='FROZEN_PROPOSAL_ONLY',
         'TRIAL_NOT_PREREGISTERED')
    plan=frozen['plan']
    need(preregister(plan)['digest']==frozen.get('digest'),
         'PREREG_IMMUTABLE_CONFLICT')
    need(type(cohorts) is dict and
         set(cohorts)=={h['id'] for h in plan['hypotheses']},
         'TRIAL_FULL_FAMILY_REQUIRED')
    results=[]
    all_episode_keys=None
    for h in plan['hypotheses']:
        hid=h['id']
        rows=cohorts[hid]
        need(type(rows) is list,'TRIAL_COHORT_NOT_LIST')
        seen=set()
        pairs=[]
        for row in rows:
            need(type(row) is dict and
                 set(row)=={'episode_id','signal_asof','outcome',
                            'challenger_net_pct','baseline_net_pct',
                            'baseline_policy_sha'},
                 'TRIAL_OBSERVATION_SCHEMA')
            k=row['episode_id']
            d=iso(row['signal_asof'])
            need(type(k) is str and k not in seen and
                 k.startswith(d.isoformat()+'|'),'TRIAL_DUPLICATE_EPISODE_OR_DAY')
            seen.add(k)
            need(plan['holdout_start'] <= d.isoformat() <= plan['holdout_end'],
                 'TRIAL_TIME_LEAKAGE')
            need(row['baseline_policy_sha']==plan['policy_sha'],
                 'TRIAL_BASELINE_DRIFT')
            need(row['outcome'] in {'COMPLETE','CENSORED','INVALIDATED'},
                 'TRIAL_UNKNOWN_OUTCOME')
            if row['outcome']=='COMPLETE':
                v=row['challenger_net_pct']
                b=row['baseline_net_pct']
                need(type(v) in (int,float) and type(b) in (int,float)
                     and math.isfinite(v) and math.isfinite(b),
                     'TRIAL_NONFINITE_NET_RETURN')
                pairs.append({'asof':d.isoformat(),'delta_pct':v-b})
            else:
                need(row['challenger_net_pct'] is None and
                     row['baseline_net_pct'] is None,
                     'TRIAL_CENSORED_OUTCOME_INFLATION')
        if all_episode_keys is None:
            all_episode_keys=seen
        need(seen==all_episode_keys,'TRIAL_SURVIVORSHIP_OR_COHORT_MISMATCH')
        if pairs:
            scored=signflip_day_pvalue(pairs)
        else:
            scored={'exploratory_two_sided_p':1.,'completed_episodes':0,
                    'distinct_signal_days':0,'mean_delta_pct':None,
                    'release':'NO_GO'}
        scored['id']=hid
        scored['n_total']=len(rows)
        scored['underpowered']=(scored['completed_episodes']<60 or
                                scored['distinct_signal_days']<20)
        results.append(scored)
    # Fixed-family Holm step-down; adjusted P values never certify true alpha.
    ordered=sorted(range(len(results)),key=lambda i:results[i]['exploratory_two_sided_p'])
    running=0.
    for rank,idx in enumerate(ordered):
        raw=results[idx]['exploratory_two_sided_p']
        running=max(running,min(1.,raw*(len(results)-rank)))
        results[idx]['holm_exploratory_p']=round(running,6)
    return {'status':'HOLD_EXTERNAL_PROVENANCE_AND_POWER_REVIEW',
            'prereg_sha256':frozen['digest'],
            'registered_hypotheses':len(results),'trials':results,
            'external_source_attestation':'NOT_VERIFIED',
            'matched_benchmark_execution':'NOT_VERIFIED',
            'holdout_immutable_public_commit':'NOT_VERIFIED',
            'multiple_comparison_control':'EXPLORATORY_HOLM',
            'rule_change':False,'notification_delivery':False,
            'orders':False,'human_review_required':True}
