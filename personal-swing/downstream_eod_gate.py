"""Natural NASDAQ EOD downstream admission. GET only; no private data.
Uses the existing exact six-job/step/DAG validator, not workflow success alone.
"""
import json, os, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO='gokaydonmez39-jpg/kripto-radar'
PATH='.github/workflows/xray-personal-477-eod.yml'
BASE='https://api.github.com/repos/'+REPO+'/actions/'
JOBS=frozenset(('offline-guard','private-sheets-auth-preflight','daily-private-scan','private-episode-followups','guardian-acceptance','daily-private-score-acceptance'))
class Hold(ValueError): pass

def require(ok, reason):
    if not ok: raise Hold(reason)

def stamp(raw):
    require(type(raw) is str and raw.endswith('Z'),'TIMESTAMP_INVALID')
    try: d=datetime.fromisoformat(raw[:-1]+'+00:00')
    except ValueError: raise Hold('TIMESTAMP_INVALID') from None
    require(d.isoformat().replace('+00:00','Z')==raw,'TIMESTAMP_INVALID')
    return d

def current_epoch(now, calendar=None):
    require(isinstance(now,datetime) and now.tzinfo is not None and now.utcoffset() is not None,'CLOCK_INVALID')
    now=now.astimezone(timezone.utc)
    if calendar is None:
        import exchange_calendars as ec
        calendar=ec.get_calendar('XNAS')
    sessions=calendar.sessions_in_range((now-timedelta(days=15)).date().isoformat(),now.date().isoformat())
    completed=[]
    for session in sessions:
        cutoff=calendar.session_close(session).to_pydatetime().astimezone(timezone.utc)+timedelta(minutes=45)
        if cutoff<=now: completed.append((session.date().isoformat(),cutoff))
    require(bool(completed),'NO_COMPLETED_SESSION')
    asof,cutoff=completed[-1]
    require(now<=cutoff+timedelta(hours=10),'NO_CURRENT_EOD_WINDOW')
    return asof,cutoff,cutoff+timedelta(hours=10)

def identity(row):
    return (isinstance(row,dict) and type(row.get('id')) is int and row['id']>0
            and type(row.get('run_attempt')) is int and row['run_attempt']==1
            and row.get('event')=='schedule' and row.get('path')==PATH
            and row.get('head_branch')=='main' and row.get('status')=='completed'
            and row.get('conclusion')=='success' and isinstance(row.get('repository'),dict)
            and row['repository'].get('full_name')==REPO
            and isinstance(row.get('head_sha'),str) and re.fullmatch(r'[0-9a-f]{40}',row['head_sha']) is not None)

def same(a,b):
    return identity(a) and identity(b) and all(a.get(k)==b.get(k) for k in ('id','head_sha','created_at','updated_at'))

def admit(event, now, get, validate, *, calendar=None):
    require(isinstance(event,dict) and event.get('action')=='completed' and isinstance(event.get('repository'),dict) and event['repository'].get('full_name')==REPO,'EVENT_INVALID')
    parent=event.get('workflow_run');require(identity(parent),'PARENT_INVALID')
    asof,start,end=current_epoch(now,calendar)
    require(start<=stamp(parent.get('created_at'))<=end and stamp(parent.get('created_at'))<=stamp(parent.get('updated_at'))<=now,'PARENT_EPOCH_INVALID')
    rid=parent['id'];url=BASE+'runs/'+str(rid)
    detail=get(url);require(same(parent,detail),'PARENT_DETAIL_DRIFT')
    utc=lambda x:x.strftime('%Y-%m-%dT%H:%M:%SZ')
    collection=get(BASE+'workflows/'+PATH.rsplit('/',1)[1]+'/runs?event=schedule&per_page=100&created='+utc(start)+'..'+utc(end))
    require(isinstance(collection,dict) and type(collection.get('total_count')) is int and collection['total_count']==1 and isinstance(collection.get('workflow_runs'),list) and len(collection['workflow_runs'])==1,'PARENT_EPOCH_NOT_UNIQUE')
    require(same(collection['workflow_runs'][0],detail),'PARENT_LIST_DRIFT')
    jobs=get(url+'/jobs?per_page=100')
    require(isinstance(jobs,dict) and type(jobs.get('total_count')) is int and jobs['total_count']==6 and type(jobs.get('jobs')) is list and len(jobs['jobs'])==6,'SIX_JOB_COUNT_INVALID')
    entries=jobs['jobs']
    require(all(isinstance(j,dict) and type(j.get('id')) is int and j['id']>0 and type(j.get('run_id')) is int and j['run_id']==rid and j.get('status')=='completed' and j.get('conclusion')=='success' for j in entries) and len({j['id'] for j in entries})==6 and {j.get('name') for j in entries}==JOBS,'SIX_JOB_STATUS_INVALID')
    result=validate(detail,jobs,asof,now)
    require(isinstance(result,dict) and result.get('status')=='PRIMARY_EOD_SIX_JOB_PROVEN_GH_ONLY' and result.get('asof_et')==asof and type(result.get('run_id')) is int and result['run_id']==rid and result.get('source_event')=='schedule' and result.get('private_sheet_verified') is False and result.get('ab_release_authorized') is False and result.get('orders') is False and result.get('device_ack')=='UNKNOWN','SIX_JOB_PROOF_INVALID')
    return {'status':'DOWNSTREAM_NATURAL_EOD_ADMITTED_GITHUB_ONLY','asof_et':asof,'run_id':rid,'writes':0,'orders':False,'device_ack':'UNKNOWN'}

def main():
    try:
        require(os.environ.get('GITHUB_EVENT_NAME')=='workflow_run' and os.environ.get('GITHUB_REPOSITORY')==REPO and os.environ.get('GITHUB_REF')=='refs/heads/main' and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','RUNTIME_INVALID')
        token=os.environ.get('GITHUB_TOKEN','');require(bool(token),'TOKEN_MISSING')
        from fallback_job_receipt import github_get,validate
        event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
        result=admit(event,datetime.now(timezone.utc),lambda url:github_get(url,token),validate)
        print(json.dumps(result,sort_keys=True));return 0
    except Exception:
        # No raw GitHub response, exception, token, or private rows in logs.
        print('DOWNSTREAM_NATURAL_EOD_HOLD');return 3
if __name__=='__main__': raise SystemExit(main())
