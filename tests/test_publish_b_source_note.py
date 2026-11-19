import copy
import pathlib
import sys
import unittest
from urllib.parse import parse_qs

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "personal-swing"))
import publish_b_source_note as writer

ASOF = "2026-01-06"
SOURCE = {"schema": writer.SCHEMA, "asof": ASOF, "run": 101, "head": "a"*40,
          "proof": [{"jobId": j} for j in range(1, 5)]}


class FakeApi:
    def __init__(self):
        self.header = [f"COL_{i}" for i in range(35)]
        for i, name in writer.HEADER_COLUMNS.items():
            self.header[i] = name
        self.row = [""]*35
        self.row[0], self.row[1], self.row[4] = ASOF+"|SUMMARY", ASOF, "SUMMARY"
        self.row[26:30] = [writer.RUN_PREFIX+"101", writer.READY, "", "b"*64]
        self.rows = [self.header, self.row]
        self.note = ""
        self.posts = []
        self.ack = True
        self.preflight_drift = False
        self.readback_drift = False
        self.reads = 0
        self.checked = False

    def check_metadata(self):
        self.checked = True

    def read(self, tab, last_column):
        assert self.checked and (tab, last_column) == (writer.TAB, "AI")
        self.reads += 1
        out = copy.deepcopy(self.rows)
        if self.preflight_drift and self.reads == 2:
            out[1][29] = "c"*64
        return out

    def request(self, path, method="GET", body=None):
        if method == "POST":
            assert path == ":batchUpdate" and len(body["requests"]) == 1
            self.posts.append(copy.deepcopy(body))
            change = body["requests"][0]["updateCells"]
            assert change["range"] == {"sheetId": 7, "startRowIndex": 1, "endRowIndex": 2,
                                       "startColumnIndex": 26, "endColumnIndex": 27}
            assert change["fields"] == "note" and set(change["rows"][0]["values"][0]) == {"note"}
            self.note = change["rows"][0]["values"][0]["note"]
            return {"replies": [{}]} if self.ack else {}
        assert method == "GET" and body is None
        q = parse_qs(path[1:])
        assert q["ranges"] == ["'SWING_SKOR_GUNLUK'!AA2:AC2"]
        assert q["fields"] == [
            "properties(timeZone),sheets(properties(sheetId,title),data(startRow,startColumn,rowData(values(formattedValue,note))))"]
        note = "changed" if self.readback_drift and self.posts else self.note
        return {"properties": {"timeZone": "Europe/Istanbul"},
                "sheets": [{"properties": {"title": writer.TAB, "sheetId": 7},
                            "data": [{"startRow": 1, "startColumn": 26, "rowData": [
                                {"values": [{"formattedValue": self.row[26], "note": note},
                                            {"formattedValue": self.row[27]}]}]}]}]}


class NotePublisherTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()

    def deny(self, reason, count=0):
        with self.assertRaisesRegex(writer.EvidenceError, "^"+reason+"$"):
            writer.synchronize_note(self.api, SOURCE)
        self.assertEqual(len(self.api.posts), count)

    def test_writes_aa_note_only_once_and_verifies(self):
        rows = copy.deepcopy(self.api.rows)
        self.assertEqual(writer.synchronize_note(self.api, SOURCE), "ATTACHED_AND_VERIFIED")
        self.assertEqual(len(self.api.posts), 1)
        self.assertEqual(self.api.rows, rows)
        self.assertEqual(self.api.note, writer.note_text(SOURCE))
        self.assertEqual(writer.synchronize_note(self.api, SOURCE), "ALREADY_VERIFIED")
        self.assertEqual(len(self.api.posts), 1)

    def test_old_summary_cannot_be_modified(self):
        row = self.api.row.copy()
        row[0], row[1] = "2026-01-07|SUMMARY", "2026-01-07"
        self.api.rows.append(row)
        self.deny("SCORE_NEWER_OR_MISSING_ASOF")

    def test_duplicate_summary_cannot_be_modified(self):
        self.api.rows.append(self.api.row.copy())
        self.deny("SCORE_SUMMARY_NOT_UNIQUE")

    def test_different_run_cannot_be_modified(self):
        self.api.row[26] = writer.RUN_PREFIX+"102"
        self.deny("SCORE_SUMMARY_BINDING_UNVERIFIED")

    def test_already_reserved_summary_cannot_be_modified(self):
        self.api.row[27] = "REQUESTED_NOT_DEVICE_ACK"
        self.deny("SCORE_SUMMARY_BINDING_UNVERIFIED")

    def test_foreign_note_cannot_be_overwritten(self):
        self.api.note = "already present"
        self.deny("SCORE_NOTE_CONFLICT")

    def test_summary_change_before_post_stops_write(self):
        self.api.preflight_drift = True
        self.deny("SCORE_NOTE_PREWRITE_DRIFT")

    def test_ambiguous_ack_never_reposts(self):
        self.api.ack = False
        self.deny("SCORE_NOTE_ACK_UNVERIFIED", 1)

    def test_drift_after_post_never_reposts(self):
        self.api.readback_drift = True
        self.deny("SCORE_NOTE_READBACK_UNVERIFIED", 1)

    def test_bad_header_never_posts(self):
        self.api.header[26] = "UNKNOWN"
        self.deny("SCORE_HEADER_DRIFT")




class ASourceSupplementTests(unittest.TestCase):
    def application_inputs(self):
        import datetime as dt
        import json
        import emit_b_source_envelope as producer

        y = "2026-11-18T21:05:00Z"
        z = "2026-11-18T21:06:00Z"
        jobs = {n: {"id": i + 1, "started_at": y, "completed_at": z}
                for i, n in enumerate(producer.NAMES)}
        jobs[producer.CARRIER]["completed_at"] = None
        txt = lambda row: y + " " + json.dumps(row, separators=(",", ":"))
        here = {"asof_et": ASOF}
        logs = {
            producer.NAMES[0]: "\n".join([
                y + " " + producer.SCAN_MARK,
                txt(dict(here, status="PRIVATE_SHEET_READBACK_PASS", candidates=2)),
                txt(dict(here, no_execution=True, final_ready=True, universe=477, processed=477, valid=477,
                         invalid_or_missing=0, remaining=0, new_entries=2, scope_sha256=producer.A_SCOPE,
                         analysis_fingerprint_sha256=producer.A_ALGO)),
                txt(dict(here, status="AL_OUTBOX_PENDING_READBACK_PASS", technical_al=2, messages_sent=0,
                         device_ack=False, new_pending=2, new_suppressed=0, not_allowlisted="fixture-private")),
            ]),
            producer.NAMES[1]: "\n".join([
                txt(dict(here, status="SWING_SCORE_PRIVATE_READBACK_PASS", execution="NONE",
                         active_episodes=24, scoreable=24)),
                txt(dict(here, status="PANEL_READBACK_PASS", device_ack=False)),
                txt(dict(here, status="LIFECYCLE_READBACK_PASS", device_ack=False,
                         notification_delivery="NOT_ATTEMPTED_BY_GITHUB", terminal_updates=1)),
            ]),
            producer.NAMES[2]: txt(dict(schema="XRAY_PERSONAL_PRIVATE_EVIDENCE_AUDIT_V1", status="READ_ONLY_EVIDENCE_AUDIT",
                                  execution="NONE", sheet_writes=0, messages_sent=0, last_verified_scan_asof=ASOF,
                                  last_asof_score="SUMMARY_PRESENT", score_count=24, score_hold_count=0,
                                  scored_active_episodes=24)),
        }
        now = dt.datetime.fromisoformat(z.replace("Z", "+00:00"))
        return producer, jobs, logs, now

    def test_complete_witness_keeps_b_proof_and_note_only_write(self):
        p, jobs, logs, now = self.application_inputs()
        old_paths = {**logs, p.NAMES[1]: logs[p.NAMES[1]].splitlines()[0]}
        b = p.envelope(jobs, old_paths, 101, "a" * 40, ASOF, now)
        both = p.envelope(jobs, logs, 101, "a" * 40, ASOF, now)
        self.assertEqual({k: v for k, v in both.items() if k != "a"}, b)
        self.assertEqual(both["a"]["schema"], p.A_SCHEMA)
        self.assertEqual(both["a"]["outbox"][1:], [2, 0])
        self.assertEqual(both["a"]["life"][1], 1)
        self.assertNotIn("fixture-private", writer.note_text(both))
        api = FakeApi()
        self.assertEqual(writer.synchronize_note(api, both), "ATTACHED_AND_VERIFIED")
        self.assertEqual(len(api.posts), 1)
        self.assertEqual(api.posts[0]["requests"][0]["updateCells"]["fields"], "note")

    def test_wrong_policy_or_duplicate_receipt_does_not_attach_a(self):
        p, jobs, logs, now = self.application_inputs()
        k = p.NAMES[0]
        broken = [
            logs[k].replace(p.A_SCOPE, "b" * 64),
            logs[k] + "\n" + logs[k].splitlines()[-1],
            logs[k].replace('"new_pending":2', '"new_pending":3'),
            logs[k].replace('"messages_sent":0', '"messages_sent":1'),
        ]
        b = p.envelope(jobs, {**logs, k: broken[0]}, 101, "a"*40, ASOF, now)
        for text in broken:
            with self.subTest(length=len(text)):
                got = p.envelope(jobs, {**logs, k: text}, 101, "a"*40, ASOF, now)
                self.assertEqual(got, b)
                self.assertNotIn("a", got)

    def test_late_or_noncurrent_panel_is_not_witnessed(self):
        p, jobs, logs, now = self.application_inputs()
        key = p.NAMES[1]
        panel = logs[key].splitlines()[1]
        for change in (panel.replace("T21:05:00Z", "T21:25:00Z"), panel.replace(ASOF, "2026-01-05")):
            next_logs = {**logs, key: logs[key].replace(panel, change)}
            got = p.envelope(jobs, next_logs, 101, "a"*40, ASOF, now)
            self.assertNotIn("a", got)

if __name__ == "__main__":
    unittest.main()
