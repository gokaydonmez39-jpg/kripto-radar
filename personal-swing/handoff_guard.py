"""Deterministic fail-closed private EOD handoff validator.

All values stay in an ephemeral GitHub runner. Do NOT log raw IEX bars,
per-symbol decisions, private journal contents or candidate identities.
Invariant failures raise exceptions under BOTH normal and optimized Python.
"""
from collections import Counter
from datetime import date
import math
import re

ALLOWED=frozenset(('AL','IZLE','ELE'))
HEX64=re.compile(r'^[0-9a-f]{64}$')


class HandoffInvalid(ValueError):
    pass


def require(ok,code):
    if not ok:
        raise HandoffInvalid('HANDOFF_'+code)


def validate_snapshot(snap,symbols,*,scope_sha,policy_sha):
    require(isinstance(snap,dict),'SNAPSHOT_NOT_OBJECT')
    require(isinstance(symbols,list) and len(symbols)==len(set(symbols))==477,
            'UNIVERSE_NOT_EXACT_477')
    require(all(isinstance(s,str) and s and s.isascii() and s.upper()==s
                for s in symbols),'INVALID_SCOPE_SYMBOL')
    for name,want in (('scope_sha256',scope_sha),
                      ('analysis_fingerprint_sha256',policy_sha)):
        require(isinstance(want,str) and HEX64.fullmatch(want) is not None,
                'INVALID_EXPECTED_'+name)
        require(snap.get(name)==want,'MISMATCH_'+name)
    for name in ('requested_symbols','processed_symbols','valid_data_symbols'):
        require(type(snap.get(name)) is int and snap[name]==477,'NOT_477_'+name)
    for name in ('remaining_symbols','insufficient_data_symbols'):
        require(type(snap.get(name)) is int and snap[name]==0,'NONZERO_'+name)
    for name in ('coverage_complete','valid_data_coverage_complete',
                 'new_signal_publishable'):
        require(snap.get(name) is True,'NOT_TRUE_'+name)
    for name,want in (('not_broker',True),('orders_sent',0),
                      ('auto_trading',False)):
        require(snap.get(name)==want,'BROKER_SAFETY_'+name)
    require(snap.get('failed_groups')==[],'FAILED_BATCHES_PRESENT')
    day=snap.get('asof_et')
    try:
        require(isinstance(day,str),'ASOF_NOT_STRING')
        require(date.fromisoformat(day).isoformat()==day,'ASOF_NON_ISO')
    except (ValueError,TypeError) as exc:
        raise HandoffInvalid('HANDOFF_BAD_ASOF') from exc
    rows=snap.get('rows')
    require(isinstance(rows,list) and len(rows)==477,'ROWS_NOT_EXACT_477')
    require(all(isinstance(x,dict) for x in rows),'NONOBJECT_ROW')
    identities=[x.get('symbol') for x in rows]
    require(len(set(identities))==477 and set(identities)==set(symbols),
            'ROW_SCOPE_OR_DUPLICATE')
    require(all(x.get('asof_et')==day for x in rows),'MIXED_SESSION')
    decisions=[x.get('decision') for x in rows]
    require(all(x in ALLOWED for x in decisions),'UNSAFE_DECISION')
    counts=snap.get('counts')
    require(isinstance(counts,dict),'COUNTS_NOT_OBJECT')
    expected={'START':477,'TEKNIK_AL_ADAYI':decisions.count('AL'),
              'YAKIN_IZLE':decisions.count('IZLE'),
              'ELE':decisions.count('ELE'),'VERI_YETERSIZ':0}
    for k,v in expected.items():
        require(type(counts.get(k)) is int and counts[k]==v,
                'COUNT_MISMATCH_'+k)
    for x in rows:
        if x['decision']!='AL':
            continue
        fields=('close','atr14','indicative_stop','indicative_target_2r',
                'relative_iex_volume','rsi14')
        require(all(type(x.get(k)) in (int,float) and math.isfinite(x[k])
                    for k in fields),'AL_NONFINITE_FIELD')
        close,stop,target=x['close'],x['indicative_stop'],x['indicative_target_2r']
        require(0<stop<close<target,'AL_LEVEL_ORDER')
        require(abs(target-(close+2*(close-stop)))<=0.005,'AL_NOT_2R')
    return {'asof_et':day,'universe_valid':477,'new_signal_count':expected['TEKNIK_AL_ADAYI'],
            'policy_sha256':policy_sha,'scope_sha256':scope_sha,
            'safe_to_use_privately':True,'device_ack':False}
