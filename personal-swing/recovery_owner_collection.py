"""Read-only continuation evidence for an already verified immutable EOD owner.

No claim, write, dispatch, delivery, or new scheduler authority. The caller
must independently verify the protected ref/tag and direct run GET first.
The initial acquisition continues to require a unique natural run.
"""
from datetime import datetime, timedelta, timezone
import re

REPO = 'gokaydonmez39-jpg/kripto-radar'
WORKFLOW = '.github/workflows/xray-personal-477-eod.yml'
SHA = re.compile(r'[0-9a-f]{40}\Z')
ACTIVE = frozenset(('queued', 'in_progress', 'waiting', 'pending', 'requested'))
TERMINAL = frozenset(('success', 'failure', 'cancelled', 'timed_out',
                      'action_required', 'startup_failure', 'stale', 'neutral', 'skipped'))

class OwnerCollectionHold(ValueError):
    pass

def need(ok, reason):
    if not ok:
        raise OwnerCollectionHold(reason)

def utc(value):
    need(type(value) is str and value.endswith('Z'), 'UTC_INVALID')
    try:
        d = datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError:
        raise OwnerCollectionHold('UTC_INVALID') from None
    need(d.isoformat().replace('+00:00', 'Z') == value, 'UTC_INVALID')
    return d

def identity(row, start, end, now):
    need(type(row) is dict, 'RUN_INVALID')
    repo = row.get('repository')
    need(type(row.get('id')) is int and row['id'] > 0 and
         type(row.get('run_attempt')) is int and row['run_attempt'] == 1 and
         row.get('event') == 'schedule' and row.get('path') == WORKFLOW and
         row.get('head_branch') == 'main' and type(row.get('head_sha')) is str and
         SHA.fullmatch(row['head_sha']) is not None and type(repo) is dict and
         repo.get('full_name') == REPO, 'RUN_IDENTITY_INVALID')
    created, updated = utc(row.get('created_at')), utc(row.get('updated_at'))
    need(start <= created <= updated <= min(end, now + timedelta(seconds=5)),
         'RUN_CLOCK_INVALID')
    status, conclusion = row.get('status'), row.get('conclusion')
    need(type(status) is str and ((status in ACTIVE and conclusion is None) or
         (status == 'completed' and type(conclusion) is str and conclusion in TERMINAL)),
         'RUN_STATE_INVALID')
    return created

def verify_owned_collection(owner, actual, page, *, cutoff, now):
    """Return only normalized read evidence, never a write-authorization token.

    cutoff must be independently derived from the exact official XNAS calendar.
    owner must be the manifest read from the already verified immutable tag.
    Two rows are the maximum in the proposed two-slot topology. An earlier
    competitor or incomplete listing remains HOLD; a later contender is not
    allowed to borrow the existing owner. Initial claims use the old unique gate.
    """
    need(isinstance(cutoff, datetime) and isinstance(now, datetime) and
         cutoff.tzinfo is not None and now.tzinfo is not None and
         cutoff.utcoffset() is not None and now.utcoffset() is not None,
         'CLOCK_INVALID')
    cutoff, now = cutoff.astimezone(timezone.utc), now.astimezone(timezone.utc)
    end = cutoff + timedelta(hours=10)
    need(cutoff <= now <= end, 'EPOCH_EXPIRED')
    need(type(owner) is dict and owner.get('schema') == 'XRAY_PERSONAL_477_EPOCH_LEASE_V1' and
         owner.get('asof_et') == cutoff.date().isoformat() and
         owner.get('source_event') == 'schedule' and owner.get('workflow') == WORKFLOW and
         type(owner.get('run_attempt')) is int and owner['run_attempt'] == 1 and
         type(owner.get('run_id')) is int and owner['run_id'] > 0 and
         type(owner.get('source_sha')) is str and SHA.fullmatch(owner['source_sha']) is not None,
         'OWNER_INVALID')
    attested = utc(owner.get('observed_at'))
    actual_created = identity(actual, cutoff, end, now)
    need(actual['id'] == owner['run_id'] and actual['head_sha'] == owner['source_sha'] and
         actual['status'] == 'in_progress' and actual_created <= attested <= now,
         'OWNER_RUN_MISMATCH')
    need(type(page) is dict and type(page.get('total_count')) is int and
         type(page.get('workflow_runs')) is list and
         1 <= page['total_count'] == len(page['workflow_runs']) <= 2,
         'COLLECTION_INCOMPLETE_OR_EXCESS')
    seen, matched = set(), False
    for row in page['workflow_runs']:
        created = identity(row, cutoff, end, now)
        need(row['id'] not in seen, 'DUPLICATE_ID')
        seen.add(row['id'])
        if row['id'] == owner['run_id']:
            need(row['head_sha'] == actual['head_sha'] and
                 row['created_at'] == actual['created_at'] and row['status'] == 'in_progress',
                 'OWNER_LIST_DRIFT')
            matched = True
        else:
            need(created >= attested, 'EARLIER_COMPETITOR')
    need(matched, 'OWNER_NOT_LISTED')
    return {'state': 'IMMUTABLE_OWNER_COLLECTION_READ_ONLY',
            'run_id': owner['run_id'], 'asof_et': owner['asof_et'],
            'later_competitors': len(seen) - 1, 'writes': 0,
            'write_authority': False, 'ab_release_authorized': False,
            'device_ack': 'UNKNOWN'}
