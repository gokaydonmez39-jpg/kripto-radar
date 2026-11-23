"""Adversarial second-writer test: Kronos research requires native epoch CAS.

No credentials, provider POST, Git refs, real Sheets or user notifications.
"""
import copy
import io
import json
import unittest
from unittest.mock import patch

import kronos_research_transport as t
import kronos_v2 as v
import private_sheet_writer as w
from test_kronos_research_transport import (
    ASOF, SID, SCOPE, POLICY, rows, fixture, meta, fake_response,
)

WINNER=890124
LOSER=890125


def api(run):
    a=fixture()
    a._research_run_id=run
    return a


def live_metadata(owner=None):
    out=meta()
    out["namedRanges"]=[t.research_epoch_marker(ASOF,SID,owner)] if owner else []
    return out


class KronosAtomicChildCasTest(unittest.TestCase):
    def test_deterministic_marker_id_and_distinct_child_owner(self):
        a=t.research_epoch_marker(ASOF,SID,WINNER)
        b=t.research_epoch_marker(ASOF,SID,LOSER)
        self.assertEqual(a["namedRangeId"],b["namedRangeId"])
        self.assertNotEqual(a["name"],b["name"])
        self.assertEqual(a["range"]["sheetId"],SID)
        self.assertNotIn("Bearer",str(a))
        for invalid in ("2026-02-31","2026-11-2","2026-11-23;"):
            with self.subTest(asof=invalid):
                with self.assertRaises(w.HandoffBlocked):
                    t.research_epoch_marker(invalid,SID,WINNER)

    def test_production_first_chunk_always_reserves_marker_atomically(self):
        a=api(WINNER)
        body=v.build_research_chunk_body(a,ASOF,SID,rows(),0)
        req=body["requests"]
        self.assertEqual(len(req),2)
        self.assertEqual(req[0],{"addNamedRange":{"namedRange":
            t.research_epoch_marker(ASOF,SID,WINNER)}})
        self.assertEqual(req[1],w.as_cells(rows(),SID))
        continuation=v.build_research_chunk_body(a,ASOF,SID,rows(),3)
        self.assertEqual(continuation,{"requests":[w.as_cells(rows(),SID)]})

    def test_winner_first_batch_allowed_only_with_missing_marker(self):
        a=api(WINNER)
        body={"requests":[
            {"addNamedRange":{"namedRange":t.research_epoch_marker(
                ASOF,SID,WINNER)}},
            w.as_cells(rows(),SID),
        ]}
        with (patch.object(a,"_last_mile",return_value=a._research_scope),
              patch.object(w,"urlopen",
                 return_value=fake_response(live_metadata())) as get,
              patch.object(t,"urlopen",
                 return_value=fake_response({"replies":[{},{}]})) as post):
            self.assertEqual(a.request(":batchUpdate",method="POST",body=body),
                             {"replies":[{},{}]})
            self.assertEqual(post.call_count,1)
            self.assertEqual(get.call_count,1)

    def test_losing_child_cannot_append_under_winner_claim(self):
        a=api(LOSER)
        body={"requests":[w.as_cells(rows(),SID)]}
        with (patch.object(a,"_last_mile",return_value=a._research_scope),
              patch.object(w,"urlopen",
                   return_value=fake_response(live_metadata(WINNER))),
              patch.object(t,"urlopen",
                   side_effect=AssertionError("LOSER_MUST_NOT_POST")) as post):
            with self.assertRaisesRegex(w.HandoffBlocked,
                                        "KRONOS2_RESEARCH"):
                a.request(":batchUpdate",method="POST",body=body)
            post.assert_not_called()

    def test_winning_child_can_resume_only_under_own_claim(self):
        a=api(WINNER)
        body={"requests":[w.as_cells(rows(),SID)]}
        with (patch.object(a,"_last_mile",return_value=a._research_scope),
              patch.object(w,"urlopen",
                   return_value=fake_response(live_metadata(WINNER))),
              patch.object(t,"urlopen",
                   return_value=fake_response({"replies":[{}]})) as post):
            a.request(":batchUpdate",method="POST",body=body)
            self.assertEqual(post.call_count,1)


if __name__=="__main__":
    unittest.main()
