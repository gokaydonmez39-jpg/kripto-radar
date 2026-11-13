import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Lock

import alert_ledger_contract as ledger
import delivery_reservation as reservation

DAY = "2026-11-12"
STAMP = "2026-11-13 09:30 TRT"
EID = f"{DAY}|TEST|{DAY}|AL_NEW_EPISODE|1"
DID = f"{DAY}|SUMMARY"


def events():
    row = [""] * 20
    row[:6] = [EID, f"{DAY}|TEST", DAY, "TEST", DAY, "AL_NEW_EPISODE"]
    row[17] = ledger.CONFIRMED_PENDING
    return [list(ledger.EVENT_HEADER), row]


def scores():
    summary = [""] * 35
    summary[:9] = [DID, DAY, "", "", "SUMMARY", "0", "0", "0", "0"]
    summary[27] = reservation.DIGEST_READY
    summary[29] = "a" * 64
    return [list(reservation.DIGEST_HEADER), summary]


class Fixture:
    """Models atomic rejection on a duplicate named-range ID."""
    def __init__(self):
        self.tables = {17: events(), 33: scores()}
        self.markers = {}
        self.lock = Lock()
        self.accepted = 0

    def post(self, plan):
        with self.lock:
            tables = deepcopy(self.tables)
            markers = deepcopy(self.markers)
            replies = []
            for request in plan.requests():
                if "addNamedRange" in request:
                    marker = request["addNamedRange"]["namedRange"]
                    key = marker["namedRangeId"]
                    if key in markers:
                        raise ValueError("synthetic provider rejection")
                    markers[key] = marker
                    replies.append({"addNamedRange": {"namedRange": marker}})
                else:
                    req = request["updateCells"]
                    a = req["start"]
                    values = req["rows"][0]["values"]
                    col = a["columnIndex"]
                    tables[a["sheetId"]][a["rowIndex"]][col:col + 2] = [
                        v["userEnteredValue"]["stringValue"] for v in values
                    ]
                    replies.append({})
            self.tables, self.markers = tables, markers
            self.accepted += 1
            return {"spreadsheetId": "synthetic", "replies": replies}


class DeliveryReservationTests(unittest.TestCase):
    def plan(self, kind="event", stamp=STAMP):
        if kind == "event":
            return reservation.plan_events(17, events(), [EID], DAY, stamp)
        return reservation.plan_digest(33, scores(), DAY, "a" * 64, stamp)

    def test_same_batch_two_writers_one_verified_winner_even_same_minute(self):
        for kind in ("event", "digest"):
            with self.subTest(kind=kind):
                db = Fixture()
                barrier = Barrier(2)
                def writer():
                    plan = self.plan(kind)
                    barrier.wait(timeout=3)
                    try:
                        result = db.post(plan)
                    except ValueError:
                        return False
                    proof = reservation.verify_commit(
                        plan, result, deepcopy(db.tables[plan.sheet_id]), "synthetic")
                    self.assertEqual(proof["reserved"], 1)
                    self.assertFalse(proof["device_ack"])
                    self.assertFalse(proof["message_proven"])
                    return True
                with ThreadPoolExecutor(max_workers=2) as pool:
                    self.assertEqual(sorted(pool.map(lambda _: writer(), range(2))), [False, True])
                self.assertEqual(db.accepted, 1)

    def test_marker_does_not_depend_on_timestamp_or_row_position(self):
        p = self.plan()
        later = self.plan(stamp="2026-11-13 09:31 TRT")
        moved = reservation.plan_events(
            17, [list(ledger.EVENT_HEADER), [], events()[1]], [EID], DAY, STAMP)
        marker = lambda plan: plan.requests()[0]["addNamedRange"]["namedRange"]
        self.assertEqual(marker(p)["namedRangeId"], marker(later)["namedRangeId"])
        self.assertEqual(marker(p)["namedRangeId"], marker(moved)["namedRangeId"])
        self.assertNotEqual(marker(p)["range"], marker(moved)["range"])

    def test_ambiguous_post_never_becomes_proof_from_cells_alone(self):
        db = Fixture()
        p = self.plan()
        db.post(p)
        for bad in (None, {}, {"spreadsheetId": "synthetic", "replies": [{}, {}]}):
            with self.subTest(bad=bad), self.assertRaises(reservation.Refused):
                reservation.verify_commit(p, bad, db.tables[17], "synthetic")
        with self.assertRaises(ValueError):
            db.post(self.plan())
        self.assertEqual(db.accepted, 1)

    def test_readback_checks_binding_and_all_unchanged_fields(self):
        for kind in ("event", "digest"):
            db = Fixture()
            p = self.plan(kind)
            result = db.post(p)
            with self.assertRaises(reservation.Refused):
                reservation.verify_commit(p, result, db.tables[p.sheet_id], "other")
            after = deepcopy(db.tables[p.sheet_id])
            after[1][6] = "changed"
            with self.assertRaises(reservation.Refused):
                reservation.verify_commit(p, result, after, "synthetic")

    def test_historical_already_reserved_duplicate_and_wrong_hash_block(self):
        ev = events()
        ev[1][17] = ledger.REQUESTED
        with self.assertRaises(reservation.Refused):
            reservation.plan_events(17, ev, [EID], DAY, STAMP)
        with self.assertRaises(reservation.Refused):
            reservation.plan_events(17, events(), [EID, EID], DAY, STAMP)
        with self.assertRaises(reservation.Refused):
            reservation.plan_events(17, events(), [EID], "2026-11-13", STAMP)
        with self.assertRaises(reservation.Refused):
            reservation.plan_digest(33, scores(), DAY, "b" * 64, STAMP)

    def test_scope_status_stamp_and_sparse_rows_fail_closed(self):
        for sid, stamp in ((-1, STAMP), (True, STAMP), (17, "2026-11-13 99:30 TRT"),
                           (17, "2026-11-10 09:30 TRT")):
            with self.subTest(sid=sid, stamp=stamp), self.assertRaises(reservation.Refused):
                reservation.plan_events(sid, events(), [EID], DAY, stamp)
        a = scores()
        a[1][28] = STAMP
        with self.assertRaises(reservation.Refused):
            reservation.plan_digest(33, a, DAY, "a" * 64, STAMP)
        a = scores()
        a.append(deepcopy(a[1]))
        with self.assertRaises(reservation.Refused):
            reservation.plan_digest(33, a, DAY, "a" * 64, STAMP)


if __name__ == "__main__":
    unittest.main()
