#!/usr/bin/env python3
"""XRAY personal swing START/FINAL V3: resumable IEX EOD scan; no brokerage.

Private, local output only. No raw provider OHLCV is stored in public GitHub.
Checkpoints are hash-scoped to the exact symbol universe and completed session.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import engine

SCHEMA = 'XRAY_PERSONAL_SWING_V3'
CHECKPOINT_SCHEMA = 'XRAY_PERSONAL_V3_CHECKPOINT'


def dump_atomic(path, obj):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n'
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(payload,encoding='utf-8')
    os.replace(temp,path)


def sha_symbols(symbols):
    return hashlib.sha256(('\n'.join(symbols)+'\n').encode()).hexdigest()


def get_scope(symbols=None, repo_watchlist=False, watchlist_file=None):
    if watchlist_file:
        j=json.loads(Path(watchlist_file).read_text(encoding='utf-8'))
        values=j if isinstance(j,list) else j.get('liquidity_watch_symbols',[])
    elif symbols:
        values=[s.strip() for s in symbols.split(',')]
    elif repo_watchlist:
        values=engine.read_watchlist(repo=True)
    else:
        values=engine.DEFAULT_SYMBOLS
    # Refuse silently converting case, duplicate securities or malformed identities.
    if (not isinstance(values,list) or not values or any(not isinstance(s,str) or not s or
          s!=s.upper() or not s.isascii() or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.' for c in s)
          for s in values) or len(values)!=len(set(values))):
        raise ValueError('INVALID_EXACT_CASE_SENSITIVE_SYMBOL_SCOPE')
    return values


def fresh_checkpoint(path, asof, symbols):
    h=sha_symbols(symbols)
    p=Path(path)
    if p.exists():
        data=json.loads(p.read_text(encoding='utf-8'))
        if data.get('schema')!=CHECKPOINT_SCHEMA:raise ValueError('INVALID_CHECKPOINT_SCHEMA')
        if data.get('asof_et')==asof and data.get('scope_sha256')==h and data.get('scope_count')==len(symbols):
            rows=data.get('rows')
            if not isinstance(rows,dict) or not set(rows).issubset(set(symbols)):
                raise ValueError('CHECKPOINT_SCOPE_CORRUPTION')
            return data
        # Do not overwrite the prior day's checkpoint without preserving it.
        archive=p.with_name(f'{p.stem}_{data.get("asof_et","unknown")}_{data.get("scope_sha256","")[:10]}.json')
        if archive.exists():raise RuntimeError('CHECKPOINT_ARCHIVE_COLLISION')
        p.replace(archive)
    return {'schema':CHECKPOINT_SCHEMA,'asof_et':asof,'scope_sha256':h,
            'scope_count':len(symbols),'symbols':symbols,'rows':{},'error_groups':[],
            'finished':False}


def scan(asof, symbols, output_dir, *, batch_size=10, max_batches=None,
         read_batch=None, pause=0):
    """Persist successful groups, resume only remaining. Provider failures never turn into ELE.

    read_batch(group,asof) returns {symbol:[bars]}. For testing this can be injected.
    """
    if not 1<=batch_size<=10:raise ValueError('BATCH_SIZE_1_TO_10')
    output_dir=Path(output_dir)
    checkpoint_path=output_dir/'checkpoint.json'
    cp=fresh_checkpoint(checkpoint_path,asof,symbols)
    if cp['symbols']!=symbols:raise ValueError('CHECKPOINT_SYMBOL_ORDER_DRIFT')
    finished=cp['rows']; errors=[]; attempted=0
    if read_batch is None:read_batch=lambda group,day:engine.live_read(group,day)
    for pos in range(0,len(symbols),batch_size):
        group=symbols[pos:pos+batch_size]
        if all(s in finished and finished[s].get('decision')!='VERI_YETERSIZ' for s in group):continue
        if max_batches is not None and attempted>=max_batches:break
        attempted+=1
        try:
            # Do not mix new provider returns with successful older checkpoint rows.
            missing=[s for s in group if s not in finished or finished[s].get('decision')=='VERI_YETERSIZ']
            bars=read_batch(missing,asof)
            if not isinstance(bars,dict):raise ValueError('NONDICT_VENDOR_RESPONSE')
            new={}
            for s in missing:
                if s not in bars:
                    new[s]={'symbol':s,'asof_et':asof,'decision':'VERI_YETERSIZ',
                            'reasons':['MISSING_PROVIDER_SYMBOL']}
                else:
                    try:new[s]=engine.analyze(s,bars[s],asof)
                    except (ValueError,KeyError,TypeError,ZeroDivisionError) as ex:
                        new[s]={'symbol':s,'asof_et':asof,'decision':'VERI_YETERSIZ',
                                'reasons':[f'INVALID_SYMBOL_DATA:{type(ex).__name__}']}
            finished.update(new)
            cp['rows']=finished
            cp['error_groups']=errors
            dump_atomic(checkpoint_path,cp)
        except Exception as ex:
            # Missing network access is not evidence for ELE, AL, or zero candidates.
            errors.append({'symbols':group,'kind':type(ex).__name__,'message':str(ex)[:180]})
            cp['error_groups']=errors
            dump_atomic(checkpoint_path,cp)
            # Quota or non-retryable auth failure: stop the run and retain cursor.
            if isinstance(ex,(PermissionError,RuntimeError)) or '401' in str(ex) or '403' in str(ex) or '429' in str(ex):
                break
        if pause:time.sleep(pause)
    cp['finished']=len(finished)==len(symbols)
    cp['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    cp['error_groups']=errors
    dump_atomic(checkpoint_path,cp)
    rows=[finished[s] for s in symbols if s in finished]
    snap=engine.assemble(rows,asof,f'personal IEX, processed {len(rows)}/{len(symbols)}')
    valid_rows=sum(r.get('decision') in ('AL','IZLE','ELE') for r in rows)
    missing_rows=len(rows)-valid_rows
    snap.update({'valid_data_symbols':valid_rows,'insufficient_data_symbols':missing_rows,
                 'valid_data_coverage_complete':cp['finished'] and missing_rows==0,
                 'schema':SCHEMA,'requested_symbols':len(symbols),
                 'processed_symbols':len(rows),'remaining_symbols':len(symbols)-len(rows),
                 'scope_sha256':cp['scope_sha256'],
                 'coverage_complete':cp['finished'],
                 'partial_scan':not cp['finished'],
                 'failed_groups':errors,
                 'new_signal_publishable':cp['finished'] and missing_rows==0,
                 'publisher':'PRIVATE_LOCAL_ONLY_NO_BROKER'})
    # Publish only an all-valid full-universe result. Partial progress is an
    # independent diagnostic file and must never replace the latest FINAL.
    if snap['valid_data_coverage_complete']:
        dump_atomic(output_dir/'latest.json',snap)
    else:
        dump_atomic(output_dir/'progress.json',snap)
    if snap['valid_data_coverage_complete']:
        dump_atomic(output_dir/'snapshots'/f'{asof}.json',snap)
    return snap


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--watchlist-file',help='Local JSON with liquidity_watch_symbols')
    p.add_argument('--repo-watchlist',action='store_true')
    p.add_argument('--symbols')
    p.add_argument('--asof')
    p.add_argument('--dir',default='private-data')
    p.add_argument('--batch-size',type=int,default=10)
    p.add_argument('--max-batches',type=int)
    p.add_argument('--pause',type=float,default=0)
    a=p.parse_args(argv)
    asof=a.asof or engine.trading_asof().isoformat()
    engine.validate_asof(asof)
    syms=get_scope(a.symbols,a.repo_watchlist,a.watchlist_file)
    result=scan(asof,syms,a.dir,batch_size=a.batch_size,max_batches=a.max_batches,pause=a.pause)
    print(json.dumps({'asof_et':asof,'requested':len(syms),
          'processed':result['processed_symbols'],'complete':result['coverage_complete'],
          'decisions':result['counts']},ensure_ascii=False))
    return 0 if result['coverage_complete'] else 2


if __name__=='__main__':sys.exit(main())
