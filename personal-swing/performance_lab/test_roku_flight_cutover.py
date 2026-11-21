"""Synthetic flight audit of reviewed forward ROKU replacement; no device claims."""
import copy
import unittest

import private_flight_recorder as flight
from test_private_flight_recorder import data

OLD=(
    "420025dd5b83b59fedd3d9af4332471fee731aedfaacb616ce80ca473bef6745",
    "d7d119c2125d75981f86850c2283973b2a70b5a2aa6aa638600a60f5039969c8",
)
INDV=(
    "4045849b129e74a600982db512f2e5ad5343a960544476721ca552544f328a20",
    "c8fc8877aa0a9e55a8e1b9707886c17210e3859fc91f896af90a26b4a98c134e",
)
RAW=(
    "4045849b129e74a600982db512f2e5ad5343a960544476721ca552544f328a20",
    "c13c5a7ad14c1753d044f2392f37c6fdf7cd5e11f6c2edd3954902aa0716056b",
)
NEW=(
    "3d1d226e2ef511570b2abd57e59c74d2c2156e6eed9baf4a08b8d3df82223060",
    "0c137ecbdaf0eb68dbab3a642cfd501e4af61641b52367607fe616713af32523",
)

def fp(t):
    return "scopeSHA="+t[0]+";algorithmSHA="+t[1]

def fixture():
    b=data()
    b[1][1][9]=fp(OLD)
    for day, sha in (("2026-11-03",INDV),("2026-11-06",RAW),
                     ("2026-11-10",NEW)):
        b[1].append([
            day,"GitHub schedule VERIFIED IEX EOD",
            "477","477","477","0","TRUE","0","private",fp(sha)
        ])
    return b


class ROKUFlightPITTests(unittest.TestCase):
    def test_three_reviewed_historical_eras_and_forward_fourth_accepted(self):
        b=fixture()
        out=flight.inspect(*b,expected_asof="2026-11-10")
        self.assertEqual(out["source_verified_issuance_days"],4)
        self.assertEqual(out["device_receipts_verified"],0)
        self.assertEqual(out["latest_verified_scan_asof"],"2026-11-10")

    def test_nov10_cannot_use_nov6_fingerprint(self):
        b=fixture()
        b[1][-1][9]=fp(RAW)
        with self.assertRaisesRegex(flight.FlightRecorderBlocked,
                "FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT"):
            flight.inspect(*b,expected_asof="2026-11-10")

    def test_nov10_cannot_use_unreviewed_uniform_fingerprint(self):
        b=fixture()
        for row in b[1][1:]:
            row[9]=fp(("a"*64,"b"*64))
        with self.assertRaisesRegex(flight.FlightRecorderBlocked,
                "FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT"):
            flight.inspect(*b,expected_asof="2026-11-10")

    def test_nov9_failed_epoch_cannot_be_promoted(self):
        b=fixture()
        b[1].insert(-1,["2026-11-09","GitHub schedule VERIFIED IEX EOD",
                        "477","477","477","0","TRUE","0","private",fp(RAW)])
        with self.assertRaisesRegex(flight.FlightRecorderBlocked,
                "FLIGHT_FAILED_EPOCH_REPLAY"):
            flight.inspect(*b,expected_asof="2026-11-10")

    def test_unknown_cutover_policy_sha_rejected(self):
        b=fixture()
        b[1][-1][9]=fp((NEW[0],"f"*64))
        with self.assertRaisesRegex(flight.FlightRecorderBlocked,
                "FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT"):
            flight.inspect(*b,expected_asof="2026-11-10")

    def test_historical_nov6_hash_must_not_be_rewritten(self):
        b=fixture()
        b[1][-2][9]=fp(NEW)
        with self.assertRaisesRegex(flight.FlightRecorderBlocked,
                "FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT"):
            flight.inspect(*b,expected_asof="2026-11-10")

    def test_historical_era_does_not_autorelabel_roku_to_gntx(self):
        b=fixture()
        b[0][1][0]= "2026-10-27|ROKU"
        b[0][1][2]="ROKU"
        b[2][1][0]= "2026-10-27|ROKU|2026-10-27|AL_NEW_EPISODE|1"
        b[2][1][1]= "2026-10-27|ROKU"
        b[2][1][3]="ROKU"
        out=flight.inspect(*b,expected_asof="2026-11-10")
        self.assertEqual(out["matched_new_al_outbox"],1)

    def corporate_fixture(self):
        b=fixture()
        episode="2026-10-27|ROKU"
        b[0][1][0]=episode
        b[0][1][2]="ROKU"
        b[0][1][7]="KAPALI • CORPORATE_ACTION_REVIEW • 8/15 SEANS"
        b[0][1][8]="2026-11-09"
        b[0][1][9]="CORPORATE_ACTION_REVIEW"
        b[0][1][10]=""
        b[2][1][0]=episode+"|2026-10-27|AL_NEW_EPISODE|1"
        b[2][1][1]=episode
        b[2][1][3]="ROKU"
        terminal=list(b[2][1])
        terminal[0]=episode+"|2026-11-09|CORPORATE_ACTION_REVIEW|1"
        terminal[4]="2026-11-09"
        terminal[5]="CORPORATE_ACTION_REVIEW"
        terminal[6]="KURUMSAL_ISLEM"
        terminal[7]=""
        terminal[17]="EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST"
        terminal[19]="Official Nasdaq https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2026-806"
        b[2].append(terminal)
        return b

    def test_fabricated_corporate_price_rejected(self):
        b=self.corporate_fixture()
        b[2][-1][7]="101"
        with self.assertRaisesRegex(flight.FlightRecorderBlocked,"FLIGHT_CORPORATE_ACTION_EVENT_INVALID"):
            flight.inspect(*b,expected_asof="2026-11-10")

    def test_corporate_outcome_fake_pnl_rejected(self):
        b=self.corporate_fixture()
        b[0][1][10]="2.5"
        with self.assertRaisesRegex(flight.FlightRecorderBlocked,"FLIGHT_CORPORATE_ACTION_EPISODE_INVALID"):
            flight.inspect(*b,expected_asof="2026-11-10")

    def test_wrong_corporate_issuer_rejected(self):
        b=self.corporate_fixture()
        for row in (b[0][1], b[2][1], b[2][-1]):
            for i,v in enumerate(row):
                if isinstance(v,str):
                    row[i]=v.replace("ROKU","AAA")
        with self.assertRaisesRegex(flight.FlightRecorderBlocked,"FLIGHT_CORPORATE_ACTION_EPISODE_INVALID"):
            flight.inspect(*b,expected_asof="2026-11-10")

    def test_missing_official_notice_rejected(self):
        b=self.corporate_fixture()
        b[2][-1][19]="unreviewed"
        with self.assertRaisesRegex(flight.FlightRecorderBlocked,"FLIGHT_CORPORATE_ACTION_EVENT_INVALID"):
            flight.inspect(*b,expected_asof="2026-11-10")

    def test_corporate_terminal_never_becomes_price_fill_or_device_ack(self):
        b=fixture()
        episode="2026-10-27|ROKU"
        b[0][1][0]=episode
        b[0][1][2]="ROKU"
        b[0][1][7]="KAPALI • CORPORATE_ACTION_REVIEW • 8/15 SEANS"
        b[0][1][8]="2026-11-09"
        b[0][1][9]="CORPORATE_ACTION_REVIEW"
        b[0][1][10]=""
        b[2][1][0]=episode+"|2026-10-27|AL_NEW_EPISODE|1"
        b[2][1][1]=episode
        b[2][1][3]="ROKU"
        terminal=list(b[2][1])
        terminal[0]=episode+"|2026-11-09|CORPORATE_ACTION_REVIEW|1"
        terminal[4]="2026-11-09"
        terminal[5]="CORPORATE_ACTION_REVIEW"
        terminal[7]=""
        terminal[17]="EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST"
        terminal[6]="KURUMSAL_ISLEM"
        terminal[19]="Official Nasdaq https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2026-806"
        b[2].append(terminal)
        out=flight.inspect(*b,expected_asof="2026-11-10")
        self.assertEqual(out["matched_terminal_outbox"],1)
        self.assertEqual(out["closed_count"],1)
        self.assertFalse(out["orders"])
        self.assertEqual(out["device_receipts_verified"],0)


# Forward-only UTC source policy from the independently recalculated
# engine.py + runner.py + requirements.txt + raw IEX feed contract.
UTC_20261123=(
    "3d1d226e2ef511570b2abd57e59c74d2c2156e6eed9baf4a08b8d3df82223060",
    "cac4dd7b729e23cd4f6e4c181f569ef286858c1473217e46358202f595f7723c",
)

class ForwardUtcPolicy20261123Tests(unittest.TestCase):
    """Old issue receipts immutable; only new natural XNAS sessions use the new SHA."""

    def scenario(self):
        table=fixture()
        table[1].append([
            "2026-11-19","GitHub schedule VERIFIED IEX EOD",
            "477","477","477","0","TRUE","0","private",fp(NEW)])
        table[1].append([
            "2026-11-23","GitHub schedule VERIFIED IEX EOD",
            "477","477","477","0","TRUE","0","private",fp(UTC_20261123)])
        table[3][0][1]="2026-11-23"
        return table

    def test_forward_23_nov_accepts_exact_reviewed_utc_sha_without_backfill(self):
        table=self.scenario()
        original=copy.deepcopy(table)
        result=flight.inspect(*table,expected_asof="2026-11-23")
        self.assertEqual(result["latest_verified_scan_asof"],"2026-11-23")
        self.assertEqual(result["source_verified_issuance_days"],6)
        self.assertEqual(result["unreserved_prior_eod_al"],0)
        self.assertEqual(result["device_receipts_verified"],0)
        self.assertFalse(result["writes"])
        self.assertFalse(result["orders"])
        self.assertNotIn("2026-11-20", [r[0] for r in table[1][1:]])
        self.assertEqual(table,original)

    def test_old_19_nov_current_policy_remains_valid(self):
        table=self.scenario()
        table[1].pop()
        table[3][0][1]="2026-11-19"
        out=flight.inspect(*table,expected_asof="2026-11-19")
        self.assertEqual(out["latest_verified_scan_asof"],"2026-11-19")

    def test_new_utc_sha_may_not_be_backdated_to_19_nov(self):
        table=self.scenario()
        table[1][-2][9]=fp(UTC_20261123)
        with self.assertRaisesRegex(flight.FlightRecorderBlocked,
                                    "FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT"):
            flight.inspect(*table,expected_asof="2026-11-23")

    def test_23_nov_must_not_reuse_19_nov_source_policy(self):
        table=self.scenario()
        table[1][-1][9]=fp(NEW)
        with self.assertRaisesRegex(flight.FlightRecorderBlocked,
                                    "FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT"):
            flight.inspect(*table,expected_asof="2026-11-23")

    def test_23_nov_rejects_arbitrary_policy_hash(self):
        table=self.scenario()
        table[1][-1][9]=fp((UTC_20261123[0],"f"*64))
        with self.assertRaisesRegex(flight.FlightRecorderBlocked,
                                    "FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT"):
            flight.inspect(*table,expected_asof="2026-11-23")

    def test_pre_10_nov_historical_sha_alteration_remains_rejected(self):
        table=self.scenario()
        table[1][1][9]=fp(UTC_20261123)
        with self.assertRaisesRegex(flight.FlightRecorderBlocked,
                                    "FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT"):
            flight.inspect(*table,expected_asof="2026-11-23")


if __name__=="__main__":
    unittest.main()
