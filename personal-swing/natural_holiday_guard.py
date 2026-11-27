"""No-network-by-default holiday classifier. Never admits a write or EOD PASS.
Only called when the production completed-session resolver returned None.
"""
from datetime import datetime, timedelta, timezone
import re

REPO = 'gokaydonmez39-jpg/kripto-radar'
WORKFLOW = '.github/workflows/xray-personal-477-eod.yml'
HOLIDAY = 'NATURAL_HOLIDAY_NO_DATA_USED'
VERIFIED = 'NATURAL_RUN_GITHUB_READ_ONLY_VERIFIED'
class HolidayHold(ValueError):
    pass

def need(condition, code):
    if not condition:
        raise HolidayHold(code)

def utc(value):
    need(type(value) is str and value.endswith('Z'), 'HOLIDAY_TIMESTAMP_INVALID')
    try:
        d=datetime.fromisoformat(value[:-1]+'+00:00')
        need(d.isoformat().replace('+00:00','Z')==value,'HOLIDAY_TIMESTAMP_INVALID')
        return d
    except (TypeError,ValueError):
        raise HolidayHold('HOLIDAY_TIMESTAMP_INVALID') from None

def prior_path(start,end):
    stamp=lambda x:x.strftime('%Y-%m-%dT%H:%M:%SZ')
    return ('/actions/workflows/'+WORKFLOW.rsplit('/',1)[-1]+'/runs?event=schedule&per_page=100&created='+stamp(start)+'..'+stamp(end))

def identity(row):
    return (isinstance(row,dict) and type(row.get('id')) is int and row['id']>0
            and row.get('event')=='schedule' and row.get('path')==WORKFLOW
            and row.get('head_branch')=='main' and type(row.get('run_attempt')) is int
            and row['run_attempt']==1 and isinstance(row.get('repository'),dict)
            and row['repository'].get('full_name')==REPO
            and type(row.get('head_sha')) is str and re.fullmatch(r'[0-9a-f]{40}',row['head_sha']) is not None)

def classify_holiday_noop(runtime,transport,now,*,calendar=None):
    """Conservative no-op only: exact current natural receipt, recent weekday
    holiday cron and unique already-completed previous EOD receipt. A failed
    previous EOD stays failed. No synthetic successful six-job receipt.
    """
    need(isinstance(now,datetime) and now.tzinfo is not None and now.utcoffset() is not None,'HOLIDAY_CLOCK_INVALID')
    now=now.astimezone(timezone.utc)
    need(isinstance(runtime,dict) and callable(transport),'HOLIDAY_INPUT_INVALID')
    rid=runtime.get('GITHUB_RUN_ID'); sha=runtime.get('GITHUB_SHA')
    need(runtime.get('GITHUB_REPOSITORY')==REPO and runtime.get('GITHUB_REF')=='refs/heads/main'
         and runtime.get('GITHUB_WORKFLOW_REF')==REPO+'/'+WORKFLOW+'@refs/heads/main'
         and runtime.get('GITHUB_EVENT_NAME')=='schedule' and runtime.get('GITHUB_RUN_ATTEMPT')=='1'
         and type(rid) is str and re.fullmatch(r'[1-9][0-9]*',rid) is not None
         and type(sha) is str and re.fullmatch(r'[0-9a-f]{40}',sha) is not None,'HOLIDAY_RUNTIME_INVALID')
    if calendar is None:
        import exchange_calendars as ec
        calendar=ec.get_calendar('XNAS')
    # Nominal UTC cron: 23:16 Monday-Friday. Never infer a weekend catch-up.
    slot=now.replace(hour=23,minute=16,second=0,microsecond=0)
    if slot>now:
        slot-=timedelta(days=1)
    need(slot.weekday()<5 and slot<=now<=slot+timedelta(hours=10),'HOLIDAY_SLOT_UNPROVEN')
    holiday=slot.date().isoformat()
    need(not calendar.is_session(holiday),'HOLIDAY_NOT_CLOSED_WEEKDAY')
    sessions=calendar.sessions_in_range((slot-timedelta(days=15)).date().isoformat(),holiday)
    need(len(sessions)>0,'HOLIDAY_PRIOR_SESSION_UNKNOWN')
    prior=sessions[-1].date().isoformat()
    cutoff=calendar.session_close(prior).to_pydatetime().astimezone(timezone.utc)+timedelta(minutes=45)
    end=cutoff+timedelta(hours=10)
    need(now>end and slot>end,'HOLIDAY_PRIOR_WINDOW_STILL_OPEN')
    receipt=transport('GET','/actions/runs/'+rid)
    need(identity(receipt) and receipt['id']==int(rid) and receipt['head_sha']==sha
         and receipt.get('status')=='in_progress' and receipt.get('conclusion') is None,'HOLIDAY_CURRENT_RECEIPT_UNVERIFIED')
    created=utc(receipt.get('created_at')); updated=utc(receipt.get('updated_at'))
    need(slot<=created<=now and created<=updated<=now+timedelta(seconds=5),'HOLIDAY_CURRENT_RECEIPT_CLOCK_DRIFT')
    page=transport('GET',prior_path(cutoff,end))
    need(isinstance(page,dict) and type(page.get('total_count')) is int and page['total_count']==1
         and type(page.get('workflow_runs')) is list and len(page['workflow_runs'])==1,'HOLIDAY_PRIOR_EOD_NOT_UNIQUE')
    old=page['workflow_runs'][0]
    need(identity(old) and old['id']!=int(rid) and old.get('status')=='completed'
         and old.get('conclusion') in ('success','failure','cancelled','timed_out','action_required','startup_failure','stale','neutral','skipped')
         and cutoff<=utc(old.get('created_at'))<=end,'HOLIDAY_PRIOR_EOD_UNVERIFIED')
    return {'status':HOLIDAY,'holiday_date':holiday,'prior_asof_et':prior,'prior_eod_conclusion':old['conclusion'],
            'prior_run_id':old['id'],'run_id':int(rid),'source_event':'schedule','writes':0,'orders':False,
            'lease_issued':False,'ab_release_authorized':False,'device_ack':'UNKNOWN'}

def private_jobs_eligible(result):
    """Only the existing exact natural EOD verified result can admit the jobs."""
    need(isinstance(result,dict) and result.get('status') in (VERIFIED,HOLIDAY)
         and type(result.get('writes')) is int and result['writes']==0
         and result.get('orders') is False and result.get('lease_issued') is False
         and result.get('ab_release_authorized') is False and result.get('device_ack')=='UNKNOWN', 'NATURAL_GATE_RESULT_INVALID')
    need(result.get('source_event')=='schedule' and type(result.get('run_id')) is int and result['run_id']>0,'NATURAL_GATE_IDENTITY_INVALID')
    if result['status']==VERIFIED:
        need(type(result.get('asof_et')) is str and re.fullmatch(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}',result['asof_et']) is not None
             and type(result.get('source_get_attempts')) is int and 1<=result['source_get_attempts']<=3
             and not any(key in result for key in ('holiday_date','prior_asof_et','prior_eod_conclusion','prior_run_id')),'NATURAL_GATE_EOD_INVALID')
        return True
    need(type(result.get('holiday_date')) is str and type(result.get('prior_asof_et')) is str
         and type(result.get('prior_run_id')) is int and result['prior_run_id']>0
         and result['prior_run_id']!=result['run_id'] and 'asof_et' not in result,'NATURAL_GATE_HOLIDAY_INVALID')
    return False
