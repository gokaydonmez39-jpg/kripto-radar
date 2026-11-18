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


if __name__ == "__main__":
    unittest.main()
