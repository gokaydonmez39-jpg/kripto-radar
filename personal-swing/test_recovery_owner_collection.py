import copy
import unittest
from datetime import datetime, timezone, timedelta
from recovery_owner_collection import verify_owned_collection, OwnerCollectionHold, REPO, WORKFLOW

CUTOFF=datetime(2026,11,27,18,45,tzinfo=timezone.utc)
NOW=datetime(2026,11,28,0,40,tzinfo=timezone.utc)

def row(rid=100, created='2026-11-27T23:16:00Z', **kw):
    r=dict(id=rid,run_attempt=1,event='schedule',path=WORKFLOW,head_branch='main',head_sha='a'*40,
           repository={'full_name':REPO,'id':999,'private':False},created_at=created,
           updated_at='2026-11-28T00:39:00Z',status='in_progress',conclusion=None)
    r.update(kw)
    return r

def owner(**kw):
    r=dict(schema='XRAY_PERSONAL_477_EPOCH_LEASE_V1',asof_et='2026-11-27',source_event='schedule',
           workflow=WORKFLOW,run_attempt=1,run_id=100,source_sha='a'*40,observed_at='2026-11-27T23:18:00Z')
    r.update(kw)
    return r

def page(*rows):
    return {'total_count':len(rows),'workflow_runs':list(rows)}

class OwnedCollectionTests(unittest.TestCase):
    def check(self, p=None, o=None, a=None, now=NOW, cutoff=CUTOFF):
        return verify_owned_collection(owner() if o is None else o,row() if a is None else a,
               page(row()) if p is None else p,cutoff=cutoff,now=now)
    def test_single_real_shape(self):
        out=self.check();self.assertEqual(out['later_competitors'],0);self.assertFalse(out['write_authority'])
    def test_later_queued(self):
        out=self.check(page(row(),row(101,'2026-11-28T00:26:00Z',status='queued')))
        self.assertEqual(out['later_competitors'],1);self.assertEqual(out['writes'],0)
    def test_later_in_progress(self):
        self.assertEqual(self.check(page(row(),row(101,'2026-11-28T00:26:00Z')))['run_id'],100)
    def test_later_completed(self):
        self.assertEqual(self.check(page(row(),row(101,'2026-11-28T00:26:00Z',status='completed',conclusion='failure')))['later_competitors'],1)
    def test_order_independent(self):
        self.assertEqual(self.check(page(row(101,'2026-11-28T00:26:00Z'),row()))['run_id'],100)
    def test_earlier_competitor(self):
        with self.assertRaisesRegex(OwnerCollectionHold,'EARLIER_COMPETITOR'): self.check(page(row(),row(101,'2026-11-27T23:17:59Z')))
    def test_duplicate(self):
        with self.assertRaisesRegex(OwnerCollectionHold,'DUPLICATE_ID'): self.check(page(row(),row()))
    def test_missing_owner(self):
        with self.assertRaisesRegex(OwnerCollectionHold,'OWNER_NOT_LISTED'): self.check(page(row(101,'2026-11-28T00:26:00Z')))
    def test_partial_page(self):
        with self.assertRaises(OwnerCollectionHold): self.check({'total_count':2,'workflow_runs':[row()]})
    def test_too_many_rows(self):
        with self.assertRaises(OwnerCollectionHold): self.check(page(row(),row(101,'2026-11-28T00:26:00Z'),row(102,'2026-11-28T00:27:00Z')))
    def test_boolean_count(self):
        with self.assertRaises(OwnerCollectionHold): self.check({'total_count':True,'workflow_runs':[row()]})
    def test_manual_competitor(self):
        with self.assertRaises(OwnerCollectionHold): self.check(page(row(),row(101,'2026-11-28T00:26:00Z',event='workflow_dispatch')))
    def test_wrong_repo(self):
        with self.assertRaises(OwnerCollectionHold): self.check(page(row(),row(101,'2026-11-28T00:26:00Z',repository={'full_name':'other/repo'})))
    def test_wrong_attempt(self):
        with self.assertRaises(OwnerCollectionHold): self.check(page(row(),row(101,'2026-11-28T00:26:00Z',run_attempt=2)))
    def test_sha_drift(self):
        with self.assertRaisesRegex(OwnerCollectionHold,'OWNER_LIST_DRIFT'): self.check(page(row(head_sha='b'*40)))
    def test_time_drift(self):
        with self.assertRaisesRegex(OwnerCollectionHold,'OWNER_LIST_DRIFT'): self.check(page(row(created='2026-11-27T23:17:00Z')))
    def test_lease_theft(self):
        with self.assertRaisesRegex(OwnerCollectionHold,'OWNER_RUN_MISMATCH'): self.check(o=owner(run_id=101))
    def test_expiry(self):
        with self.assertRaisesRegex(OwnerCollectionHold,'EPOCH_EXPIRED'): self.check(now=CUTOFF+timedelta(hours=10,seconds=1))
    def test_wrong_date(self):
        with self.assertRaises(OwnerCollectionHold): self.check(o=owner(asof_et='2026-11-26'))
    def test_missing_timestamp(self):
        with self.assertRaises(OwnerCollectionHold): self.check(page(row(),row(101,'2026-11-28T00:26:00Z',updated_at=None)))
    def test_bad_terminal_conclusion(self):
        with self.assertRaises(OwnerCollectionHold): self.check(page(row(),row(101,'2026-11-28T00:26:00Z',status='completed')))
    def test_input_not_mutated(self):
        p=page(row(),row(101,'2026-11-28T00:26:00Z'));old=copy.deepcopy(p);self.check(p);self.assertEqual(p,old)
    def test_clock_boundary_exact(self):
        self.assertEqual(self.check(now=CUTOFF+timedelta(hours=10))['run_id'],100)
    def test_no_delivered_claim(self):
        out=self.check();self.assertFalse(out['ab_release_authorized']);self.assertEqual(out['device_ack'],'UNKNOWN')
