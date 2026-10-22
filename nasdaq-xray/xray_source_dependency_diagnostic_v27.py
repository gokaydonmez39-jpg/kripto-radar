#!/usr/bin/env python3
"""XRAY source dependency *diagnostic* (non-authoritative, read-only).

Never emits market OHLCV, names, credentials, trading orders, fake signals, PASS authority.
Run against the existing checkout. No network. 100% research-only and fail-closed.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMA = 'XRAY_SOURCE_BLOCKER_DIAGNOSTIC_V1'
SHA = re.compile(r'^[0-9a-f]{40}$')


def blob(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def read(root: Path, name: str) -> dict:
    path = root / name
    if not path.is_file():
        raise ValueError('MISSING_' + name.upper().replace('.', '_'))
    obj = json.loads(path.read_text(encoding='utf-8'))
    if type(obj) is not dict:
        raise ValueError('NON_OBJECT_' + name.upper().replace('.', '_'))
    return obj


def integer(x):
    if type(x) is not int or x < 0:
        raise ValueError('NOT_NONNEGATIVE_INT')
    return x


def summarize_price_reason_census(master: dict, price: dict, identity: int, expected_unknown: int) -> dict:
    """Aggregate in-memory full-PRICE status/reason/provenance; never export symbols or bars.

    Canonical 22 Oct PRICE contains a 3,191-row result mapping. A subset count
    cannot be interpreted as the entire master without validating this mapping.
    """
    from collections import Counter
    results=price.get('results')
    if results is None:
        return {'validated':False,'reason':'SYNTHETIC_FIXTURE_WITHOUT_RESULTS'}
    if type(results) is not dict or len(results)!=identity:
        raise ValueError('PRICE_RESULT_SCOPE_NOT_MASTER_EXACT')
    member=master.get('pass_symbols')
    if isinstance(member,list) and (len(member)!=identity or set(member)!=set(results)):
        raise ValueError('PRICE_RESULT_SYMBOL_IDENTITY_DRIFT')
    status=Counter(); reasons=Counter(); provenance=Counter(); unknown_symbols=[]
    for symbol,row in results.items():
        if type(row) is not dict:
            raise ValueError('PRICE_RESULT_NOT_OBJECT')
        st=row.get('status')
        if type(st) is not str or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}',st):
            raise ValueError('PRICE_RESULT_STATUS_INVALID')
        status[st]+=1
        origin=row.get('provenance')
        if isinstance(origin,str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}',origin):
            provenance[origin]+=1
        if st=='UNKNOWN':
            unknown_symbols.append(symbol)
            info=row.get('info')
            if type(info) is not dict:
                raise ValueError('PRICE_UNKNOWN_INFO_MISSING')
            reason=info.get('reason')
            if type(reason) is not str or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,100}',reason):
                raise ValueError('PRICE_UNKNOWN_REASON_UNSAFE_OR_MISSING')
            reasons[reason]+=1
    if len(unknown_symbols)!=expected_unknown:
        raise ValueError('PRICE_UNKNOWN_RESULT_COUNT_DRIFT')
    declared=price.get('unknown_symbols')
    if declared is not None and (not isinstance(declared,list) or
                                 len(declared)!=expected_unknown or
                                 set(declared)!=set(unknown_symbols)):
        raise ValueError('PRICE_UNKNOWN_MEMBERSHIP_DRIFT')
    listed_pass=price.get('pass_symbols')
    if listed_pass is not None and (not isinstance(listed_pass,list) or
             len(listed_pass)!=integer(price.get('pass_count')) or
             any(sym not in results or not str(results[sym].get('status','')).startswith('PASS')
                 for sym in listed_pass)):
        raise ValueError('PRICE_PASS_MEMBERSHIP_DRIFT')
    primary=price.get('c417_rallies_primary_meta') or {}
    return {'validated':True,'result_count':len(results),
            'status_counts':dict(sorted(status.items())),
            'unknown_reason_counts':dict(sorted(reasons.items())),
            'provenance_counts':dict(sorted(provenance.items())),
            'resolver_required_unknown_count':reasons.get(
                'AUTHENTICATED_SIP_RESOLVER_BRIDGE_REQUIRED',0),
            'rallies_primary_materialized_count':integer(
                price.get('c417_rallies_primary_materialized_count',0)),
            'rallies_primary_meta_status':str(primary.get('status','UNKNOWN'))[:40],
            'rallies_primary_runner_file_missing':str(primary.get('reason','')).startswith(
                'FileNotFoundError:'),
            'market_data_access_proven':False,
            'rth_30_session_proven':False}


def analyze_data(root: dict, master: dict, price: dict, request: dict,
                 history: dict, terminal: dict, overlay: dict, g9: dict,
                 mc_bridges: list[dict]) -> dict:
    datasets=(root,master,price,request,history,terminal,overlay,g9)
    if any(o.get('execution') != 'NONE' or o.get('real_money') != 'NO-GO' for o in datasets):
        raise ValueError('POLICY_EXECUTION_REAL_MONEY')
    if any(o.get('unknown_never_pass') is not True for o in (master,price)):
        raise ValueError('UNKNOWN_NEVER_PASS_CHANGED')
    asof = root.get('asof_et')
    if not isinstance(asof,str) or not re.fullmatch(r'20\d\d-\d\d-\d\d',asof):
        raise ValueError('ROOT_ASOF_INVALID')
    if master.get('asof_et') != asof or price.get('asof_et') != asof or request.get('asof_et') != asof:
        raise ValueError('CURRENT_EPOCH_ASOF_MISMATCH')
    identity = integer(master.get('pass_count'))
    unknown = integer(price.get('unknown_count'))
    price_pass = integer(price.get('pass_count'))
    blocked=integer(price.get('blocked_count'))
    # The three canonical PRICE counters may refer to overlapping/residual scopes.
    # Never assert they sum to the MASTER identity universe without proof that
    # they form an exhaustive, disjoint partition. Validate only safe bounds.
    if any(n > identity for n in (price_pass, unknown, blocked)):
        raise ValueError('PRICE_COUNT_EXCEEDS_MASTER_IDENTITY')
    census=summarize_price_reason_census(master,price,identity,unknown)
    if integer(request.get('price_unknown_count')) != unknown:
        raise ValueError('REQUEST_UNKNOWN_MISMATCH')
    if request.get('source_price_blob_sha') is None or not SHA.fullmatch(str(request.get('source_price_blob_sha'))):
        raise ValueError('INVALID_PRICE_LINEAGE_SHA')
    current_mc = [m for m in mc_bridges
                  if m.get('schema')=='XRAY_MC_EPOCH_RESULT_V1'
                  and m.get('status')=='COMMITTED'
                  and m.get('asof_et')==asof
                  and m.get('input_blob_sha')==request.get('source_price_blob_sha')
                  and m.get('input_pass_hash')==price.get('pass_hash')
                  and m.get('input_count')==price_pass
                  and m.get('policy_version')=='C4.17']
    stale_history = history.get('asof_et') != asof
    stale_terminal = terminal.get('asof_et') != asof
    stale_overlay = overlay.get('asof_et') != asof
    # Never report positive authority; this module reports sources only.
    gates = {'PRICE_UNKNOWN': unknown > 0,
             'MC_BRIDGE_MISSING': len(current_mc) != 1,
             'HISTORY_STALE': stale_history,
             'TERMINAL_STALE': stale_terminal,
             'OVERLAY_STALE': stale_overlay,
             'G9_UNAUTHORIZED': g9.get('g9_pass') is not True}
    order = ['PRICE_UNKNOWN','MC_BRIDGE_MISSING','HISTORY_STALE','TERMINAL_STALE','OVERLAY_STALE','G9_UNAUTHORIZED']
    return {
        'schema':SCHEMA,'asof_et':asof,'release_authorized':False,
        'execution':'NONE','real_money':'NO-GO','unknown_never_pass':True,
        'registered_R92_generated':False,'iphone_receipt_attested':False,
        'status':'BLOCKED_OR_DIAGNOSTIC_ONLY',
        'first_blocker':next((s for s in order if gates[s]),'NO_MISSING_SOURCE_IN_THIS_LIMITED_DIAGNOSTIC'),
        'gates':gates,
        'price_reason_census':census,
        'source_counts':{'identity_pass':identity,'price_pass':price_pass,
                         'price_unknown':unknown,'price_blocked':blocked,
                         'price_counts_disjoint_and_exhaustive_proven':False,
                         'mc_exact_bridge_matches':len(current_mc)},
        'source_asof':{'root':asof,'price':price.get('asof_et'),
                       'history':history.get('asof_et'),
                       'terminal':terminal.get('asof_et'),
                       'overlay':overlay.get('asof_et')},
        'authority_disclaimer':'READ_ONLY_DIAGNOSTIC_NOT_C417_NOT_R92_NOT_MARKET_DATA_PASS'
    }


def inspect(root_path: Path) -> dict:
    names=['orchestrator_state.json','canonical_current_master_manifest.json',
           'canonical_current_price_dv30.json','canonical_current_resolver_request.json',
           'canonical_current_history.json','canonical_current_terminal.json',
           'canonical_current_final_gate_overlay.json','strict_g9_runtime_state.json']
    objs=[read(root_path,n) for n in names]
    # Check the resolver's actual source bytes as well as its declared hash.
    actual_price_blob=blob(root_path/names[2])
    if objs[3].get('source_price_blob_sha') != actual_price_blob:
        raise ValueError('RESOLVER_PRICE_SHA_DRIFT')
    bridges=[]
    for path in sorted(root_path.glob('canonical_mc_bridge_*.json')):
        try:
            bridges.append(read(root_path,path.name))
        except (OSError,ValueError,TypeError,json.JSONDecodeError):
            # A corrupt candidate is not a valid bridge and never makes a PASS.
            continue
    return analyze_data(*objs,bridges)


def fixture(*, unknown=3, has_mc=False, history_asof='2026-10-07',
            terminal_asof='2026-10-07', overlay_asof='2026-10-07'):
    common={'execution':'NONE','real_money':'NO-GO'}
    date='2026-10-22'; sha='a'*40
    root=dict(common,asof_et=date)
    master=dict(common,asof_et=date,pass_count=10,unknown_never_pass=True)
    price=dict(common,asof_et=date,unknown_never_pass=True,
               unknown_count=unknown,blocked_count=0,pass_count=10-unknown,pass_hash='b'*64)
    req=dict(common,asof_et=date,source_price_blob_sha=sha,price_unknown_count=unknown)
    hist=dict(common,asof_et=history_asof)
    terminal=dict(common,asof_et=terminal_asof)
    overlay=dict(common,asof_et=overlay_asof)
    g9=dict(common,g9_pass=False)
    mc=([dict(schema='XRAY_MC_EPOCH_RESULT_V1',status='COMMITTED',asof_et=date,
              input_blob_sha=sha,input_pass_hash='b'*64,input_count=10-unknown,
              policy_version='C4.17')] if has_mc else [])
    return [root,master,price,req,hist,terminal,overlay,g9,mc]


def selftest() -> dict:
    cases=0; fails=0
    for unknown in range(0,16):
        for has_mc in (False,True):
            for fresh in (False,True):
                v=fixture(unknown=min(unknown,10),has_mc=has_mc,
                          history_asof='2026-10-22' if fresh else '2026-10-07',
                          terminal_asof='2026-10-22' if fresh else '2026-10-07',
                          overlay_asof='2026-10-22' if fresh else '2026-10-07')
                z=analyze_data(*v)
                if z['release_authorized'] or z['registered_R92_generated'] or z['status']!='BLOCKED_OR_DIAGNOSTIC_ONLY':
                    raise AssertionError('FALSE_MARKET_RELEASE')
                if z['gates']['PRICE_UNKNOWN'] != (min(unknown,10)>0):
                    raise AssertionError('INCORRECT_SOURCE_GATE')
                cases+=1
    import copy
    invalid=[]
    funcs=[lambda v:v[0].update(execution='LIVE'),
           lambda v:v[1].update(real_money='YES'),
           lambda v:v[2].update(unknown_never_pass=False),
           lambda v:v[2].update(unknown_count=-1),
           lambda v:v[3].update(source_price_blob_sha='INVALID'),
           lambda v:v[3].update(price_unknown_count=5),
           lambda v:v[1].update(asof_et='2026-10-21'),
           lambda v:v[2].update(pass_count=11),
           lambda v:v[0].update(asof_et='INVALID')]
    for fn in funcs:
        v=copy.deepcopy(fixture());fn(v)
        try: analyze_data(*v)
        except ValueError: fails+=1
        else:raise AssertionError('FALSE_ACCEPT_OF_MUTATION')
    # The same census contract must cover a zero-UNKNOWN scope and a 3-UNKNOWN scope.
    for u in (0,3):
        v=fixture(unknown=u)
        symbols=[f'X{i:04d}' for i in range(10)]
        v[1]['pass_symbols']=symbols
        v[2]['results']={sym:(
            {'status':'UNKNOWN','provenance':'DYNAMIC_BRIDGE_DEFERRED',
             'info':{'reason':'AUTHENTICATED_SIP_RESOLVER_BRIDGE_REQUIRED'}}
            if i<u else {'status':'FAIL_PRICE','provenance':'CURRENT_PRICE_SAME_POLICY_REUSE',
                          'info':{'proof':'ASOF_CLOSE_LT_5'}})
                         for i,sym in enumerate(symbols)}
        v[2]['unknown_symbols']=symbols[:u]
        v[2]['pass_symbols']=[]
        v[2]['pass_count']=0
        c=analyze_data(*v)['price_reason_census']
        if c['unknown_reason_counts'].get('AUTHENTICATED_SIP_RESOLVER_BRIDGE_REQUIRED',0)!=u:
            raise AssertionError('CENSUS_WRONG_REASON_COUNT')
        if c['result_count']!=10 or c['market_data_access_proven']:
            raise AssertionError('CENSUS_FALSE_AUTHORITY')
        cases+=1
        if u==3:
            variants=[
                lambda x:x[2]['unknown_symbols'].append('GHOST'),
                lambda x:x[2]['results'].pop('X0000'),
                lambda x:x[2]['results']['X0000']['info'].update(reason='BAD PATH / SECRET'),
                lambda x:x[2]['results']['X0000'].update(status='FAIL_PRICE'),
                lambda x:x[1]['pass_symbols'].append('INVALID')
            ]
            for mutant in variants:
                bad=copy.deepcopy(v);mutant(bad)
                try:analyze_data(*bad)
                except ValueError:fails+=1
                else:raise AssertionError('CENSUS_MUTATION_FALSE_PASS')
    return {'schema':'XRAY_DEPENDENCY_DIAGNOSTIC_TESTS_V1','valid_shadow_cases':cases,
            'rejected_negative_mutations':fails,'total':cases+fails,'status':'PASS',
            'notes':'Synthetic only; never a proof of provider rights or real 30/30 RTH'}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--selftest',action='store_true')
    ap.add_argument('--out',type=Path)
    ap.add_argument('--root',type=Path,default=ROOT)
    ns=ap.parse_args()
    result=selftest() if ns.selftest else inspect(ns.root)
    if ns.out:
        ns.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__': main()