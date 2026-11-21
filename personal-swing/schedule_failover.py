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
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

WORKFLOW='xray-personal-477-eod.yml'
NY=ZoneInfo('America/New_York')
# An EOD workflow-file push runs ONLY offline tests and never writes private
# source/Sheet data. It must not suppress detection of a missing natural EOD.
VALID_EVENTS=frozenset(('schedule','workflow_dispatch'))
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
    # Existence suppresses duplicate dispatch; only a successful natural
    # schedule may count as an observed EOD scheduler success.
    matched=[]
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
            if item.get('status') not in VALID_STATUSES:
                return 'BLOCKED_RUN_STATUS_UNKNOWN',candidate_date
            matched.append(item)
    natural=[item for item in matched if item['event']=='schedule']
    if any(item['status']=='completed' and item.get('conclusion')=='success'
           for item in natural):
        return 'NOOP_CURRENT_EPOCH_RUN_EXISTS',candidate_date
    if natural:
        if any(item['status']=='completed' for item in natural):
            return 'BLOCKED_CURRENT_EPOCH_NATURAL_EOD_NOT_SUCCESS',candidate_date
        return 'BLOCKED_CURRENT_EPOCH_NATURAL_EOD_INCOMPLETE',candidate_date
    if matched:
        return 'BLOCKED_CURRENT_EPOCH_NON_NATURAL_SOURCE',candidate_date
    return 'DISPATCH_ONE_MISSING_SCHEDULE',candidate_date



def windowed_runs_url(workflow_base, now):
    """Limit run search to the entire possible 10h fallback epoch.

    GitHub supports the 'created' query for workflow-specific run listing.
    The five-minute cushion is outside the full MAX_FALLBACK_AGE window;
    even a run right at the eligible cutoff is included. No pagination
    is silently trusted: the caller rejects total_count != returned rows.
    """
    if now.tzinfo is None:
        raise ValueError('AWARE_UTC_NOW_REQUIRED')
    oldest=(now.astimezone(timezone.utc)-MAX_FALLBACK_AGE-
            timedelta(minutes=5)).replace(microsecond=0)
    created='>='+oldest.strftime('%Y-%m-%dT%H:%M:%SZ')
    return workflow_base+'/runs?'+urlencode({'per_page':100,'created':created})


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


def run(*,now=None,read_runs=None,request_dispatch=None,trigger_event=None):
    """Injectable vendor operations for offline, network-free negative tests."""
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError('AWARE_NOW_REQUIRED')
    # Calendar first: no GitHub API IO outside the actual completed-session
    # fallback window (including on weekends, holidays and delayed jobs).
    preliminary,session=decision(now,[],calendar=None)
    if preliminary=='NOOP_OUTSIDE_SAFE_FALLBACK_WINDOW' and trigger_event=='schedule':
        import exchange_calendars as ec
        cutoff=(ec.get_calendar('XNAS').session_close(session).to_pydatetime()
                +timedelta(minutes=45))
        age=now.astimezone(timezone.utc)-cutoff
        # GitHub can create an existing scheduled fallback >10h late.
        # Failure must remain visible even though replay is prohibited.
        # More than 24h means it is no longer the prior daily EOD epoch.
        if MAX_FALLBACK_AGE < age <= timedelta(hours=24):
            return {'status':'BLOCKED_NATURAL_FALLBACK_EXPIRED',
                    'asof_et':session,'dispatch_requested':False}
    if preliminary!='DISPATCH_ONE_MISSING_SCHEDULE':
        return {'status':preliminary,'dispatch_requested':False}
    if read_runs is None or request_dispatch is None:
        return {'status':'BLOCKED_MISSING_EXPLICIT_GITHUB_IO','dispatch_requested':False}
    payload=read_runs()
    if not isinstance(payload,dict) or not isinstance(payload.get('workflow_runs'),list):
        return {'status':'BLOCKED_INVALID_GITHUB_RUN_RESPONSE','dispatch_requested':False}
    count=payload.get('total_count')
    if type(count) is not int or count<0 or count!=len(payload['workflow_runs']):
        # Exactly 50/100 results with MORE pages also means UNKNOWN.
        # Do not dispatch when the original EOD run may be hidden on page 2,
        # or when GitHub omits / falsifies the total count.
        return {'status':'BLOCKED_UNTRUSTED_RUN_PAGINATION','dispatch_requested':False}
    verdict,session=decision(now,payload['workflow_runs'])
    if verdict!='DISPATCH_ONE_MISSING_SCHEDULE':
        return {'status':verdict,'asof_et':session,'dispatch_requested':False}
    # Bind the fallback dispatch to the exact eligible XNAS date: the
    # downstream worker can start still later, across another midnight.
    # Recheck just before dispatch: a late natural schedule may have arrived.
    # Two GETs reduce but cannot eliminate the non-atomic GitHub dispatch race.
    confirm=read_runs()
    if not isinstance(confirm,dict) or not isinstance(confirm.get('workflow_runs'),list):
        return {'status':'BLOCKED_RECHECK_INVALID_GITHUB_RUN_RESPONSE',
                'asof_et':session,'dispatch_requested':False}
    n=confirm.get('total_count')
    if type(n) is not int or n<0 or n!=len(confirm['workflow_runs']):
        return {'status':'BLOCKED_RECHECK_UNTRUSTED_RUN_PAGINATION',
                'asof_et':session,'dispatch_requested':False}
    rechecked,rechecked_session=decision(now,confirm['workflow_runs'])
    if rechecked_session!=session:
        return {'status':'BLOCKED_RECHECK_ASOF_CHANGED',
                'asof_et':session,'dispatch_requested':False}
    if rechecked!='DISPATCH_ONE_MISSING_SCHEDULE':
        return {'status':('NOOP_RECHECK_CURRENT_EPOCH_RUN_EXISTS'
                          if rechecked=='NOOP_CURRENT_EPOCH_RUN_EXISTS'
                          else 'BLOCKED_RECHECK_UNCERTAIN_RUN_STATE'),
                'asof_et':session,'dispatch_requested':False}
    accepted=request_dispatch(session)
    if accepted is not True:
        return {'status':'BLOCKED_DISPATCH_NOT_CONFIRMED','asof_et':session,
                'dispatch_requested':False}
    return {'status':'DISPATCH_REQUEST_ACCEPTED_NOT_COMPLETED',
            'asof_et':session,'dispatch_requested':True,'no_execution':True}




def allow_dispatch_for_event(event):
    """Only an explicitly authorized manual recovery may dispatch today."""
    # Natural fallback is observational until schedule/dispatch provenance
    # and the private Sheet A/B gates support a complete parent-child proof.
    return event == 'workflow_dispatch'

def scheduler_parent_receipt(result, env):
    """Log-only immutable parent witness, never a new dispatch authority."""
    if not isinstance(result, dict) or not isinstance(env, dict):
        return None
    if (result.get('status') != 'DISPATCH_REQUEST_ACCEPTED_NOT_COMPLETED'
            or result.get('dispatch_requested') is not True
            or result.get('no_execution') is not True
            or env.get('GITHUB_EVENT_NAME') != 'schedule'):
        return None
    number = env.get('GITHUB_RUN_ID')
    sha = env.get('GITHUB_SHA')
    repo = env.get('GITHUB_REPOSITORY')
    ref = env.get('GITHUB_REF')
    day = result.get('asof_et')
    if (not isinstance(number, str) or not number.isascii() or
            not number.isdecimal() or int(number) < 1 or
            not isinstance(sha, str) or len(sha) != 40 or
            any(c not in '0123456789abcdef' for c in sha) or
            repo != 'gokaydonmez39-jpg/kripto-radar' or
            ref != 'refs/heads/main' or
            not isinstance(day, str) or len(day) != 10):
        return None
    try:
        if datetime.fromisoformat(day).date().isoformat() != day:
            return None
    except ValueError:
        return None
    return {'schema': 'XRAY_477_FALLBACK_PARENT_RECEIPT_V1',
            'parent_run_id': int(number),
            'parent_source_event': 'schedule',
            'parent_workflow': '.github/workflows/xray-personal-477-schedule-fallback.yml',
            'parent_head_sha': sha,
            'parent_ref': ref,
            'requested_asof_et': day,
            'dispatch_request_accepted': True,
            'eod_completion_proven': False,
            'ab_release_authorized': False,
            'writes': 0, 'orders': 0}

def exit_code_for_result(result, event):
    """A scheduled fallback with no proven primary EOD must never be green.

    A normal success means only that an eligible genuine EOD run was found,
    NOT that a ChatGPT card or a device notification was delivered. On a
    missing primary run the scheduler cannot auto-dispatch until an
    independently verified parent-child provenance contract is deployed.
    """
    if not isinstance(result, dict) or not isinstance(event, str):
        return 3
    status=result.get('status')
    accepted=('NOOP_CURRENT_EPOCH_RUN_EXISTS',
              'NOOP_RECHECK_CURRENT_EPOCH_RUN_EXISTS')
    # Official XNAS holidays/early no-session windows are legitimate safe
    # no-ops, not missing natural EODs. Never turn holidays into false alarms.
    safe_noop=('NOOP_SESSION_NOT_READY',
               'NOOP_OUTSIDE_SAFE_FALLBACK_WINDOW')
    if event == 'schedule':
        return 0 if status in accepted+safe_noop else 3
    if event == 'workflow_dispatch':
        # Explicit manual dry-run, no-session and manual accepted request
        # are diagnostics: they do not promote to an EOD delivery claim.
        return 0 if status in accepted+safe_noop+(
            'DRY_RUN_WOULD_DISPATCH',
            'DISPATCH_REQUEST_ACCEPTED_NOT_COMPLETED') else 3
    return 3


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
    captured_now=datetime.now(timezone.utc)
    def get_runs():
        return api_json(windowed_runs_url(base,captured_now),token)
    def dispatch(session):
        if args.dry_run:
            return True
        # FAIL CLOSED: automated fallback writes source_event=workflow_dispatch.
        # The canonical A/B gate only authorizes schedule; an early fallback
        # scan could lock this ASOF to unaccepted provenance forever.
        # Never dispatch from this scheduled fallback until an independently
        # tested parent-child/Sheet receipt authorization is deployed.
        if not allow_dispatch_for_event(os.environ.get('GITHUB_EVENT_NAME')):
            return False
        return api_json(base+'/dispatches',token,method='POST',
                        body={'ref':'main','inputs':{'asof_et':session}})['dispatch_accepted']
    try:
        result=run(now=captured_now,read_runs=get_runs,request_dispatch=dispatch,
                   trigger_event=os.environ.get('GITHUB_EVENT_NAME'))
        if args.dry_run and result.get('dispatch_requested'):
            result['status']='DRY_RUN_WOULD_DISPATCH'
            result['dispatch_requested']=False
        result['workflow']=WORKFLOW
        result['execution']='NONE'
        result['real_money']='NO-GO'
        receipt=scheduler_parent_receipt(result, os.environ)
        if receipt is not None:
            result['parent_receipt']=receipt
        print(json.dumps(result,sort_keys=True))
        return exit_code_for_result(result, os.environ.get('GITHUB_EVENT_NAME',''))
    except (HTTPError,URLError,RuntimeError,ValueError,TimeoutError) as exc:
        # The exception class is enough. Never leak tokens or vendor endpoints.
        print(json.dumps({'status':'BLOCKED_GITHUB_API_UNCERTAIN',
            'reason_type':type(exc).__name__,'execution':'NONE'}))
        return 2


if __name__=='__main__':
    sys.exit(main())
