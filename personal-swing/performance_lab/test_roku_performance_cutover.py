"""A14 synthetic former-ROKU cohort exclusion; never create fake fills."""
import copy
import unittest

import private_performance_adapter as a
from test_private_performance_adapter import scans,sheet,UNIVERSE,SRC,POL


def fixtures(kind="corporate"):
    ss=scans()
    ss[1][9]="scopeSHA="+"d"*64+";algorithmSHA="+"e"*64
    ss[-1][0]="2026-11-10"
    rr=sheet()
    r=["2026-10-22|ROKU","2026-10-22","ROKU","TEKNIK AL",
       "100","95","110","KAPALI • CORPORATE_ACTION_REVIEW • 1/15 SEANS",
       "2026-11-09","CORPORATE_ACTION_REVIEW","",
       "PRESERVE_NOTICE","PRESERVE_NOTE"]
    if kind=="open":r[7]="AÇIK • 1/15 SEANS";r[8:11]=["","",""]
    if kind=="wrongdate":r[8]="2026-11-10"
    if kind=="wrongcode":r[9]="STOP_TOUCHED"
    rr.append(r)
    return rr,ss


class FormerROKUPerformanceTests(unittest.TestCase):
    def test_verified_non_price_corporate_ep_excluded_from_current_cohort(self):
        candidates,scans_=fixtures()
        before=copy.deepcopy(candidates)
        plan=a.source_plan(candidates,scans_,"2026-11-10",UNIVERSE,SRC,POL)
        self.assertEqual(plan["total"],2)
        self.assertEqual(plan["excluded_unproven_issuance"],2)
        self.assertEqual(plan["verified"],[])
        self.assertEqual(candidates,before)

    def test_unclosed_out_of_scope_roku_must_fail(self):
        candidates,scans_=fixtures("open")
        with self.assertRaisesRegex(a.EvidenceBlocked,"CANDIDATE_IDENTITY_MISMATCH"):
            a.source_plan(candidates,scans_,"2026-11-10",UNIVERSE,SRC,POL)

    def test_unverified_corporate_date_cannot_pass_identity(self):
        candidates,scans_=fixtures("wrongdate")
        with self.assertRaisesRegex(a.EvidenceBlocked,"CANDIDATE_IDENTITY_MISMATCH"):
            a.source_plan(candidates,scans_,"2026-11-10",UNIVERSE,SRC,POL)

    def test_unverified_corporate_code_cannot_pass_identity(self):
        candidates,scans_=fixtures("wrongcode")
        with self.assertRaisesRegex(a.EvidenceBlocked,"CANDIDATE_IDENTITY_MISMATCH"):
            a.source_plan(candidates,scans_,"2026-11-10",UNIVERSE,SRC,POL)


if __name__=="__main__":
    unittest.main()
