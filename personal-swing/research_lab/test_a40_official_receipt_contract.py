"""A40: offline official 477 shadow receipt validation adversarial regressions.

No external data, secret, network, broker, order, Sheets or runtime feed.
This test deliberately fails on the original A39 main code for malformed EOD
dates and non-symbol punctuation in a correctly SHA-bound 477-row fixture.
"""
import unittest
from official_eod_shadow_receipt import ReceiptRefused, digest, verify
from test_official_eod_shadow_receipt import fixture


def change_date(snapshot, receipt, new_date):
    snapshot["asof_et"] = new_date
    receipt["asof_et"] = new_date
    receipt["private_eod_snapshot_sha256"] = digest(snapshot)


def change_symbol(snapshot, receipt, symbol):
    snapshot["rows"][0]["symbol"] = symbol
    receipt["rows"][0]["symbol"] = symbol
    receipt["private_eod_snapshot_sha256"] = digest(snapshot)


class A40OfficialSourceAdmission(unittest.TestCase):
    def test_invalid_calendar_day_must_be_rejected_even_when_hashes_match(self):
        for invalid in ("2026-02-30", "2026-13-01", "NOT_A_DATE"):
            with self.subTest(date=invalid):
                s, r, g = fixture()
                change_date(s, r, invalid)
                with self.assertRaisesRegex(ReceiptRefused, "SHADOW_EOD_DATE_INVALID"):
                    verify(s, r, g)

    def test_noncanonical_date_must_be_rejected(self):
        for invalid in ("2026-10-30T00:00:00Z", "2026-W44-5", ""):
            with self.subTest(date=invalid):
                s, r, g = fixture()
                change_date(s, r, invalid)
                with self.assertRaisesRegex(ReceiptRefused, "SHADOW_EOD_DATE_INVALID"):
                    verify(s, r, g)

    def test_symbol_punctuation_never_pretends_to_be_a_valid_ticker(self):
        for invalid in ("SYM000!", "SYM000/", "SYM000 ", "SYM000\n", "SYM000@"):
            with self.subTest(symbol=repr(invalid)):
                s, r, g = fixture()
                change_symbol(s, r, invalid)
                with self.assertRaisesRegex(ReceiptRefused, "SHADOW_SYMBOL_ORDER_OR_SCOPE_DRIFT"):
                    verify(s, r, g)

    def test_valid_dotted_symbol_remains_accepted(self):
        s, r, g = fixture()
        change_symbol(s, r, "BRK.B")
        self.assertEqual(verify(s, r, g),
                         "RESEARCH_LEDGER_READBACK_PASS_NO_MARKET_CLEARANCE")

    def test_date_mismatch_remains_rejected(self):
        s, r, g = fixture()
        r["asof_et"] = "2026-10-29"
        with self.assertRaisesRegex(ReceiptRefused, "SHADOW_EOD_DATE_MISMATCH"):
            verify(s, r, g)

    def test_never_elevate_source_authority(self):
        s, r, g = fixture()
        self.assertEqual(verify(s, r, g),
                         "RESEARCH_LEDGER_READBACK_PASS_NO_MARKET_CLEARANCE")
        r["may_place_order"] = True
        with self.assertRaisesRegex(ReceiptRefused, "UNAUTHORIZED_SHADOW_AUTHORITY"):
            verify(s, r, g)


if __name__ == "__main__":
    unittest.main()
