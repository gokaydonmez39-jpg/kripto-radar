#!/usr/bin/env python3
"""Bounded, personal-477-only GitHub Actions schedule fallback. No market IO.

Checks whether the production personal EOD workflow received ANY main-branch
run after the most recently eligible official XNAS close+45m. GitHub schedule
jobs can run after midnight in New York; never mistake the next calendar day
for the completed prior session. The fallback dispatches once only
when the primary GitHub scheduler appears absent. A failed producer is NOT
a scheduler gap and must be left fail-closed. This program never reads bars,
secrets, personal Sheets, broker APIs, or candidate identities.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

WORKFLOW='xray-personal-477-eod.yml'
NY=ZoneInfo('America/New_York')
VALID_EVENTS=frozenset(('schedule','workflow_dispatch','push'))
VALID_STATUSES=frozenset(('requested','waiting','queued','pending','in_progress','completed'))
# GitHub schedule delay can cross NY midnight. Limit backfill dispatch to
# a 10-hour window following that SESSION's close+45m, never an ancient day.
MAX_FALLBACK_AGE=timedelta(hours=10)


def decision(now, runs, *, calendar=None):
    """Pure function: return (status, official_session) without mutation."""
    import exchange_calendars as ec
    if now.tzinfo is None:
        raise ValueError('AWARE_UTC_NOW_REQUIRED')
    instant=now.astimezone(timezone.utc)
    local_date=instant.astimezone(NY).date().isoformat()
    cal=calendar or ec.get_calendar('XNAS')
    # The fallback is scheduled Tue-Sat in UTC, for the PREVIOUS
    # Mon-Fri NY close. A delayed GitHub job often crosses 00:00 NY.
    # Do not silently skip a valid closed session merely because local
    # calendar day switched to the next yet-unopened session.
    candidate=cal.date_to_session(local_date,direction='previous')
    candidate_date=candidate.date().isoformat()
    if cal.is_session(local_date):
        today_cutoff=cal.session_close(candidate).to_pydatetime()+timedelta(minutes=45)
        if instant<today_cutoff:
            candidate=cal.previous_session(candidate)
            candidate_date=candidate.date().isoformat()
    cutoff=cal.session_close(candidate).to_pydatetime()+timedelta(minutes=45)
    if instant<cutoff:
        return 'NOOP_SESSION_NOT_READY',candidate_date
    if instant-cutoff>MAX_FALLBACK_AGE:
        return 'NOOP_OUTSIDE_SAFE_FALLBACK_WINDOW',candidate_date
    if not isinstance(runs,list):
        return 'BLOCKED_RUN_COLLECTION_UNKNOWN',candidate_date
    for item in runs:
        if not isinstance(item,dict):
            return 'BLOCKED_MALFORMED_RUN',candidate_date
        if item.get('event') not in VALID_EVENTS or item.get('head_branch')!='main':
            continue
        try:
            created=datetime.fromisoformat(item['created_at'].replace('Z','+00:00'))
        except (KeyError,TypeError,ValueError):
            return 'BLOCKED_RUN_TIMESTAMP_UNKNOWN',candidate_date
        if created.tzinfo is None:
            return 'BLOCKED_RUN_TIMESTAMP_NAIVE',candidate_date
        if created>=cutoff:
            status=item.get('status')
            if status not in VALID_STATUSES:
                return 'BLOCKED_RUN_STATUS_UNKNOWN',candidate_date
            # ANY queued/completed run in the same fresh trading epoch
            # suppresses retry. Even failure can be a correct fail-closed gate.
            return 'NOOP_CURRENT_EPOCH_RUN_EXISTS',candidate_date
    return 'DISPATCH_ONE_MISSING_SCHEDULE',candidate_date


def api_json(url,token,method='GET',body=None):
    headers={'Accept':'application/vnd.github+json',
             'Authorization':'Bearer '+token,
             'X-GitHub-Api-Version':'2022-11-28',
             'User-Agent':'xray-personal-477-scheduler-fallback'}
    if body is not None:
        headers['Content-Type']='application/json'
    data=json.dumps(body).encode() if body is not None else None
    req=Request(url,data=data,headers=headers,method=method)
    with urlopen(req,timeout=20) as response:
        if method=='POST':
            if response.status!=204:
                raise RuntimeError('UNEXPECTED_DISPATCH_STATUS')
            return {'dispatch_accepted':True}
        return json.load(response)


def run(*,now=None,read_runs=None,request_dispatch=None):
    """Injectable vendor operations for offline, network-free negative tests."""
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError('AWARE_NOW_REQUIRED')
    # Calendar first: no GitHub API IO outside the actual completed-session
    # fallback window (including on weekends, holidays and delayed jobs).
    preliminary,_=decision(now,[],calendar=None)
    if preliminary!='DISPATCH_ONE_MISSING_SCHEDULE':
        return {'status':preliminary,'dispatch_requested':False}
    if read_runs is None or request_dispatch is None:
        return {'status':'BLOCKED_MISSING_EXPLICIT_GITHUB_IO','dispatch_requested':False}
    payload=read_runs()
    if not isinstance(payload,dict) or not isinstance(payload.get('workflow_runs'),list):
        return {'status':'BLOCKED_INVALID_GITHUB_RUN_RESPONSE','dispatch_requested':False}
    if payload.get('total_count',0)>len(payload['workflow_runs']) and len(payload['workflow_runs'])<50:
        # Pagination inconsistency, not proof that no matching run exists.
        return {'status':'BLOCKED_UNTRUSTED_RUN_PAGINATION','dispatch_requested':False}
    verdict,session=decision(now,payload['workflow_runs'])
    if verdict!='DISPATCH_ONE_MISSING_SCHEDULE':
        return {'status':verdict,'asof_et':session,'dispatch_requested':False}
    accepted=request_dispatch()
    if accepted is not True:
        return {'status':'BLOCKED_DISPATCH_NOT_CONFIRMED','asof_et':session,
                'dispatch_requested':False}
    return {'status':'DISPATCH_REQUEST_ACCEPTED_NOT_COMPLETED',
            'asof_et':session,'dispatch_requested':True,'no_execution':True}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args(argv)
    repo=os.environ.get('GITHUB_REPOSITORY','')
    token=os.environ.get('GITHUB_TOKEN','')
    if not repo or len(repo.split('/'))!=2 or not token:
        print(json.dumps({'status':'BLOCKED_MISSING_GITHUB_REPO_OR_TOKEN','no_execution':True}))
        return 2
    base='https://api.github.com/repos/'+repo+'/actions/workflows/'+WORKFLOW
    def get_runs():
        return api_json(base+'/runs?per_page=50',token)
    def dispatch():
        if args.dry_run:
            return True
        return api_json(base+'/dispatches',token,method='POST',body={'ref':'main'})['dispatch_accepted']
    try:
        result=run(read_runs=get_runs,request_dispatch=dispatch)
        if args.dry_run and result.get('dispatch_requested'):
            result['status']='DRY_RUN_WOULD_DISPATCH'
            result['dispatch_requested']=False
        result['workflow']=WORKFLOW
        result['execution']='NONE'
        result['real_money']='NO-GO'
        print(json.dumps(result,sort_keys=True))
        return 0
    except (HTTPError,URLError,RuntimeError,ValueError,TimeoutError) as exc:
        # The exception class is enough. Never leak tokens or vendor endpoints.
        print(json.dumps({'status':'BLOCKED_GITHUB_API_UNCERTAIN',
            'reason_type':type(exc).__name__,'execution':'NONE'}))
        return 2


if __name__=='__main__':
    sys.exit(main())
