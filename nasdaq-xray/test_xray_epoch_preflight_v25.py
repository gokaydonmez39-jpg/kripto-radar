#!/usr/bin/env python3
"""Deterministic property/mutation test suite; no market IO or broker IO."""
import copy
import hashlib
import importlib.util
import json
import random
from pathlib import Path

path=Path(__file__).with_name('xray_epoch_preflight_v25.py')
spec=importlib.util.spec_from_file_location('xray_epoch_preflight_v25',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def build(i=0):
    session=f'2026-10-{(i % 21)+1:02d}'
    base=dict(asof_et=session,execution='NONE',real_money='NO-GO',unknown_never_pass=True)
    master=dict(base,pass_symbols=['AAPL','NVDA'],pass_count=2,queue_hash='a'*64)
    price=dict(base,source_master_queue_hash='a'*64,source_master_count=2)
    watch=dict(base,watchlist=[],watchlist_count=0)
    tech=dict(base,candidate_count=0)
    root=dict(base,watch_radar=watch,candidate_technical_funnel=tech)
    blobs={k:hashlib.sha1((k+str(i)).encode()).hexdigest() for k in m.DOCS}
    return root,master,price,blobs

def accepted(docs):
    a,b,c,s=docs
    return m.check_source(a,b,c,s,s,'f'*40)

def rejected(docs,label):
    try:accepted(docs)
    except m.GateFailure:return label
    raise AssertionError('SHOULD_REJECT_'+label)

if __name__=='__main__':
    positives=0;negatives=0
    for i in range(80):
        x=build(i)
        r=accepted(x)
        assert r['alert_authority'] is False and r['canonical_C417_pass'] is False
        positives+=1
    mutations=[
        ('root-date',lambda x:x[0].update(asof_et='2026-09-01')),
        ('watch-date',lambda x:x[0]['watch_radar'].update(asof_et='2026-09-01')),
        ('tech-date',lambda x:x[0]['candidate_technical_funnel'].update(asof_et='2026-09-01')),
        ('master-date',lambda x:x[1].update(asof_et='2026-09-01')),
        ('price-date',lambda x:x[2].update(asof_et='2026-09-01')),
        ('root-exec',lambda x:x[0].update(execution='LIVE')),
        ('watch-money',lambda x:x[0]['watch_radar'].update(real_money='YES')),
        ('tech-unknown',lambda x:x[0]['candidate_technical_funnel'].update(unknown_never_pass=False)),
        ('master-unknown',lambda x:x[1].update(unknown_never_pass=False)),
        ('price-unknown',lambda x:x[2].update(unknown_never_pass=False)),
        ('price-queue',lambda x:x[2].update(source_master_queue_hash='b'*64)),
        ('price-count',lambda x:x[2].update(source_master_count=1)),
        ('master-members',lambda x:x[1].update(pass_symbols=['NVDA','AAPL'])),
        ('master-count',lambda x:x[1].update(pass_count=3)),
        ('master-duplicate',lambda x:x[1].update(pass_symbols=['AAPL','AAPL'])),
        ('master-invalid-symbol',lambda x:x[1].update(pass_symbols=['AAPL','aapl'])),
        ('master-queue',lambda x:x[1].update(queue_hash='no-sha')),
        ('bad-date',lambda x:x[0].update(asof_et='2026-13-99')),
        ('missing-watch',lambda x:x[0].pop('watch_radar')),
        ('missing-tech',lambda x:x[0].pop('candidate_technical_funnel')),
    ]
    for i in range(20):
        for label,mutate in mutations:
            x=build(i)
            mutate(x)
            rejected(x,f'{label}_{i}')
            negatives+=1
    # Immutable blob pin mismatch: this is the only state that should flip
    # when a source file changes after the manifest was created.
    for i in range(80):
        root,master,price,blobs=build(i)
        pinned=dict(blobs);pinned['price']='0'*40
        try:m.check_source(root,master,price,blobs,pinned,'f'*40)
        except m.GateFailure:negatives+=1
        else:raise AssertionError('BAD_BLOB_ACCEPTED')
    # Stale consumer outputs must block publication, even after source ASOF passes.
    for i in range(60):
        x=accepted(build(i))
        good={'asof_et':x['asof_et'],'execution':'NONE','real_money':'NO-GO',
              'automated_alert_authority':False,'certified_C417_AL_signal_count':0,
              'iphone_receipt_attested':False}
        ov={'asof_et':x['asof_et'],'alpha_authority':False,'execution':'NONE','real_money':'NO-GO'}
        assert m.check_consumer_date(x,good,ov)['alert_authority'] is False
        positives+=1
        d=copy.deepcopy(good);d['asof_et']='2026-09-01'
        try:m.check_consumer_date(x,d,ov)
        except m.GateFailure:negatives+=1
        else:raise AssertionError('STALE_DIGEST_ACCEPTED')
        o=copy.deepcopy(ov);o['asof_et']='2026-09-01'
        try:m.check_consumer_date(x,good,o)
        except m.GateFailure:negatives+=1
        else:raise AssertionError('STALE_OVERLAY_ACCEPTED')
    # Reproduce independently observed live date discrepancy (read-only GitHub).
    x=build(0);x[0]['asof_et']='2026-10-22';x[0]['watch_radar']['asof_et']='2026-10-22';x[0]['candidate_technical_funnel']['asof_et']='2026-10-22';x[1]['asof_et']='2026-10-21';x[2]['asof_et']='2026-10-22'
    rejected(x,'FAILED_GITHUB_COMMIT_C44C_ASOF_SPLIT');negatives+=1
    assert positives==140 and negatives==601,(positives,negatives)
    print(json.dumps({'test_suite':'XRAY_V25_EPOCH_PREFLIGHT','positive':positives,
        'expected_negative':negatives,'total':positives+negatives,
        'result':'PASS','vendor_io':False,'r92_registered':0,
        'github_production_changed':False},indent=2))