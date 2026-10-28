"""XRAY A21 flight-recorder deterministic adversarial fixtures; zero external I/O."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import private_flight_recorder as g

DAY='2026-10-27'
KEY=DAY+'|FAKE'
EVENT=KEY+'|'+DAY+'|AL_NEW_EPISODE|1'

def data():
    c=[[ *g.CANDIDATE_HEADER ],
       [KEY, DAY, 'FAKE','TEKNİK AL ADAYI',
        '100','95','110','AÇIK • 0/15 SEANS','','','',
        'ALERT_REQUESTED_NOT_DEVICE_ACK','fake']]
    s=[[ *g.SCAN_HEADER ],
       [DAY,'fake','477','477','477','0','TRUE','1','private','not real']]
    e=[[ *g.ALERT_HEADER ],
       [EVENT,KEY,DAY,'FAKE',DAY,'AL_NEW_EPISODE','YENİ AL',
        '100','95','110','','','','','','0/15','','ALERT_REQUESTED_NOT_DEVICE_ACK','','fake']]
    p=[['Son doğrulanmış tarama seansı',DAY]]
    return [c,s,e,p]

class FlightNegativeTests(unittest.TestCase):
    def test_valid_pending_never_device_proven(self):
        x=g.inspect(*data())
        self.assertEqual(x['state'],'PASS_PENDING_DEVICE_ACK')
        self.assertEqual(x['pending_device_ack'],1)
        self.assertEqual(x['device_receipts_verified'],0)
        self.assertFalse(x['writes'])
        self.assertFalse(x['panel_non_authoritative_stale'])

    def test_panel_stale_is_detected_not_confused_with_scan(self):
        b=data()
        b[3][0][1]='2026-10-26'
        x=g.inspect(*b)
        self.assertTrue(x['panel_non_authoritative_stale'])
        self.assertEqual(x['latest_verified_scan_asof'],DAY)

    def test_missing_event_is_not_false_delivery(self):
        b=data()
        b[2]=[b[2][0]]
        x=g.inspect(*b)
        self.assertEqual(x['event_count'],0)
        self.assertEqual(x['device_receipts_verified'],0)

    def test_event_confirmation_pending_is_not_ack(self):
        b=data()
        b[2][1][17]=g.EVENT_PENDING
        self.assertEqual(g.inspect(*b)['pending_device_ack'],1)

    def test_duplicate_event_blocks(self):
        b=data()
        b[2].append(list(b[2][1]))
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'DUPLICATE_EVENT'):
            g.inspect(*b)

    def test_orphan_event_blocks(self):
        b=data()
        b[2][1][1]='2026-10-27|OTHER'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'ORPHAN_EVENT'):
            g.inspect(*b)

    def test_wrong_event_key_blocks(self):
        b=data()
        b[2][1][0]=EVENT+'-extra'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'DEDUP_KEY_INVALID'):
            g.inspect(*b)

    def test_original_stop_tamper_blocks(self):
        b=data()
        b[2][1][8]='94'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'ORIGINAL_LEVELS_CHANGED'):
            g.inspect(*b)

    def test_conflicting_device_delivery_text_blocks(self):
        b=data()
        b[2][1][17]='DELIVERED'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'UNATTESTED_DELIVERY_STATE'):
            g.inspect(*b)

    def test_invalid_source_coverage_blocks(self):
        b=data()
        b[1][1][3]='476'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'SCAN_NOT_FULL_FINAL'):
            g.inspect(*b)

    def test_duplicate_scan_blocks(self):
        b=data()
        b[1].append(list(b[1][1]))
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'SCAN_DATE_ORDER_OR_DUPLICATE'):
            g.inspect(*b)

    def test_missing_header_blocks(self):
        b=data()
        b[2][0][17]='BAD'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'HEADER_DRIFT'):
            g.inspect(*b)

    def test_unknown_candidate_blocks(self):
        b=data()
        b[0][1][7]='WIN_CONFIRMED'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'UNKNOWN_EPISODE_STATUS'):
            g.inspect(*b)

    def test_no_secrets_no_bars_and_output_aggregated(self):
        b=data()
        x=g.inspect(*b)
        self.assertNotIn('FAKE',str(x))
        self.assertNotIn('95',str(x))
        self.assertNotIn('AL_NEW_EPISODE',str(x))
        self.assertNotIn('iphone_delivered',str(x).lower())

    def test_bounded_row_contract(self):
        b=data()
        b[0]=[b[0][0]]+b[0][1:]*1000
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'TOO_LARGE'):
            g.inspect(*b)

if __name__=='__main__':
    unittest.main()
