"""Offline exact A source epoch and GitHub delimiter redaction tests."""
import json
import unittest
import emit_b_source_envelope as e


def receipt(asof, algo):
    return dict(asof_et=asof, no_execution=True, final_ready=True,
                universe=477, processed=477, valid=477,
                invalid_or_missing=0, remaining=0, scope_sha256=e.A_SCOPE,
                analysis_fingerprint_sha256=algo,
                neon_shadow=dict(asof=asof, notification_sent=False,
                                 orders_sent=0, scored=477,
                                 status="NEON_SHADOW_477_READY_PRIVATE_NO_DELIVERY"),
                new_entries=1)


def masked(obj):
    return json.dumps(obj).replace("{", "***").replace("}", "***")


class TestASourceEnvelope(unittest.TestCase):
    def test_exact_redaction_roundtrip(self):
        obj = receipt("2026-11-23", e.A_ALGO_NEXT)
        self.assertEqual(e.a_receipt_object(masked(obj)), obj)
        self.assertEqual(e.a_receipt_object(json.dumps(obj)), obj)

    def test_unknown_masked_scalar_unsafe_wrong_day_rejected(self):
        raw = masked(receipt("2026-11-23", e.A_ALGO_NEXT))
        for bad in (raw.replace("neon_shadow", "unknown_shadow"),
                    raw.replace('"scored": 477', '"scored": ***'),
                    raw.replace('"orders_sent": 0', '"orders_sent": 1'),
                    raw.replace('"notification_sent": false', '"notification_sent": true'),
                    raw.replace('"asof": "2026-11-23"', '"asof": "2026-11-20"')):
            with self.subTest(case=bad[:50]):
                self.assertIsNone(e.a_receipt_object(bad))

    def witness(self, asof, algo, *, duplicate=False):
        names = e.NAMES[:3]
        job = {"started_at": "2026-11-24T06:00:00Z",
               "completed_at": "2026-11-24T07:00:00Z"}
        jobs = {n: job for n in names}
        t = "2026-11-24T06:01:00Z"
        line = lambda o: t+" "+masked(o)
        scan = [line(receipt(asof, algo)),
                line(dict(asof_et=asof,status="AL_OUTBOX_PENDING_READBACK_PASS",
                          technical_al=1,messages_sent=0,device_ack=False,
                          new_pending=1,new_suppressed=0))]
        if duplicate:
            scan.append(scan[0])
        follow = [line(dict(asof_et=asof,status="PANEL_READBACK_PASS",device_ack=False)),
                  line(dict(asof_et=asof,status="LIFECYCLE_READBACK_PASS",device_ack=False,
                            notification_delivery="NOT_ATTEMPTED_BY_GITHUB",terminal_updates=1))]
        guard = [line(dict(last_verified_scan_asof=asof,schema="XRAY_PERSONAL_PRIVATE_EVIDENCE_AUDIT_V1",
                           status="READ_ONLY_EVIDENCE_AUDIT",execution="NONE",messages_sent=0,sheet_writes=0))]
        logs = dict(zip(names,map("\n".join,(scan,follow,guard))))
        proof = [{"lines":[[t,e.SCAN_MARK],[t,json.dumps({"candidates":1})]]},
                 {"lines":[]},{"lines":[[t,"unused"]]}]
        return e.a_supplement(jobs,logs,asof,proof)

    def test_epoch_forward_only_and_realistic_a_supplement(self):
        self.assertEqual(e.a_source_algo("2026-11-20"),e.A_ALGO)
        self.assertEqual(e.a_source_algo("2026-11-23"),e.A_ALGO_NEXT)
        self.assertEqual(self.witness("2026-11-23",e.A_ALGO_NEXT)["schema"],e.A_SCHEMA)
        self.assertEqual(self.witness("2026-11-20",e.A_ALGO)["schema"],e.A_SCHEMA)
        for asof, wrong in (("2026-11-23",e.A_ALGO),("2026-11-20",e.A_ALGO_NEXT)):
            with self.assertRaisesRegex(e.EvidenceError,"A_SOURCE_SCAN"):
                self.witness(asof,wrong)
        with self.assertRaisesRegex(e.EvidenceError,"A_SOURCE_SCAN"):
            self.witness("2026-11-23",e.A_ALGO_NEXT,duplicate=True)


if __name__ == "__main__":
    unittest.main()
