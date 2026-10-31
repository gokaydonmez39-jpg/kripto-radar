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
       [DAY,'fake','477','477','477','0','TRUE','1','private','scopeSHA='+'a'*64+';algorithmSHA='+'b'*64]]
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
        self.assertEqual(x['state'],'PENDING_CURRENT_EOD_OUTBOX_RESERVATION')
        self.assertEqual(x['unreserved_current_eod_al'],1)

    def test_confirmed_verified_AL_outbox_is_complete(self):
        x=g.inspect(*data(),expected_asof=DAY)
        self.assertEqual(x['matched_new_al_outbox'],1)
        self.assertEqual(x['unreserved_prior_eod_al'],0)
        self.assertEqual(x['source_verified_issuance_days'],1)

    def test_expected_completed_eod_must_exist(self):
        b=data()
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'EXPECTED_COMPLETED_EOD_MISSING'):
            g.inspect(*b,expected_asof='2026-10-28')

    def test_verified_scan_new_count_drift_blocks(self):
        b=data()
        b[1][1][7]='2'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'SCAN_AL_CANDIDATE_COUNT_MISMATCH'):
            g.inspect(*b)

    def test_current_scan_missing_SHA_blocks(self):
        b=data()
        b[1][1][9]='unsigned source'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'CURRENT_SCAN_SHA_MISSING'):
            g.inspect(*b)

    def test_partial_SHA_does_not_convert_to_legacy(self):
        b=data()
        b[1][1][9]='scopeSHA='+'a'*64
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'CURRENT_SCAN_SHA_MISSING'):
            g.inspect(*b)

    def test_prior_verified_AL_without_event_blocks_silently_missing_alert(self):
        b=data()
        old='2026-10-26'
        older=[old,'fake','477','477','477','0','TRUE','1','private',b[1][1][9]]
        b[1].insert(1,older)
        new_row=list(b[0][1])
        new_row[0]=old+'|FAKE';new_row[1]=old;new_row[7]='AÇIK • 1/15 SEANS'
        b[0].append(new_row)
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'SILENT_MISSING_PRIOR_AL_EVENT'):
            g.inspect(*b)

    def test_prior_unproven_legacy_episode_may_lack_AL_event(self):
        b=data()
        old='2026-10-26'
        b[1].insert(1,[old,'manual','477','477','477','0','TRUE','1','private','no original hashes'])
        older=list(b[0][1])
        older[0]=old+'|FAKE';older[1]=old;older[7]='AÇIK • 1/15 SEANS'
        b[0].append(older)
        x=g.inspect(*b)
        self.assertEqual(x['source_unproven_issuance_days'],1)
        self.assertEqual(x['matched_new_al_outbox'],1)

    def test_historical_policy_hash_mismatch_fails(self):
        b=data()
        old='2026-10-26'
        bad='scopeSHA='+'a'*64+';algorithmSHA='+'c'*64
        b[1].insert(1,[old,'auto','477','477','477','0','TRUE','0','private',bad])
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'HISTORICAL_ISSUANCE_SHA_DRIFT'):
            g.inspect(*b)

    def test_closed_episode_without_terminal_event_blocks(self):
        b=data()
        b[0][1][7]='KAPALI • STOP_TOUCHED • 1/15 SEANS'
        b[0][1][8]=DAY
        b[0][1][9]='STOP_TOUCHED'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'MISSING_TERMINAL_EVENT'):
            g.inspect(*b)

    def test_closed_episode_with_matching_terminal_event_passes(self):
        b=data()
        b[0][1][7]='KAPALI • STOP_TOUCHED • 1/15 SEANS'
        b[0][1][8]=DAY;b[0][1][9]='STOP_TOUCHED'
        row=list(b[2][1])
        row[0]=KEY+'|'+DAY+'|STOP_TOUCHED|1'
        row[5]='STOP_TOUCHED'
        b[2].append(row)
        x=g.inspect(*b)
        self.assertEqual(x['matched_terminal_outbox'],1)
        self.assertEqual(x['closed_count'],1)

    def test_event_confirmation_pending_is_not_ack(self):
        b=data()
        b[2][1][17]=g.EVENT_PENDING
        self.assertEqual(g.inspect(*b)['pending_device_ack'],1)

    def test_user_attested_sheet_status_not_equivalent_to_system_device_ack(self):
        b=data()
        b[2][1][17]='DEVICE_ACK_USER_ATTESTED'
        status=g.inspect(*b)
        self.assertEqual(status['user_attested_status_rows'],1)
        self.assertEqual(status['pending_device_ack'],1)
        self.assertEqual(status['device_receipts_verified'],0)
        self.assertEqual(status['state'],'PASS_PENDING_DEVICE_ACK')

    def test_explicit_unknown_delivery_state_is_valid_but_not_delivered(self):
        b=data()
        b[2][1][17]='DELIVERY_UNKNOWN_REVIEW_REQUIRED'
        status=g.inspect(*b)
        self.assertEqual(status['explicit_unknown_status_rows'],1)
        self.assertEqual(status['pending_device_ack'],1)
        self.assertEqual(status['device_receipts_verified'],0)
        self.assertEqual(status['state'],'PASS_PENDING_DEVICE_ACK')

    def test_unverified_delivered_claim_fails_closed(self):
        b=data()
        b[2][1][17]='PHONE_DELIVERED'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'UNATTESTED_DELIVERY_STATE'):
            g.inspect(*b)

    def test_gap_annotation_must_be_paired_with_exact_stop_event(self):
        b=data()
        b[0][1][7]='KAPALI • STOP_TOUCHED • 1/15 SEANS'
        b[0][1][8]=DAY
        b[0][1][9]='STOP_TOUCHED'
        original=b[2][1]
        original[0]=KEY+'|'+DAY+'|STOP_TOUCHED|1'
        original[5]='STOP_TOUCHED'
        gap=list(original)
        gap[0]=KEY+'|'+DAY+'|GAP_BELOW_STOP|1'
        gap[5]='GAP_BELOW_STOP'
        b[2].append(gap)
        status=g.inspect(*b)
        self.assertEqual(status['matched_terminal_outbox'],1)
        self.assertEqual(status['paired_gap_below_stop_annotations'],1)
        self.assertEqual(status['device_receipts_verified'],0)

    def test_unpaired_gap_annotation_is_blocked(self):
        b=data()
        b[2][1][0]=KEY+'|'+DAY+'|GAP_BELOW_STOP|1'
        b[2][1][5]='GAP_BELOW_STOP'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'UNPAIRED_GAP_STOP_EVENT'):
            g.inspect(*b)

    def test_gap_different_day_cannot_borrow_other_stop(self):
        b=data()
        # Stop touch on signal day cannot justify a gap on following day.
        gap=list(b[2][1])
        gap[0]=KEY+'|2026-10-28|GAP_BELOW_STOP|1'
        gap[4]='2026-10-28'
        gap[5]='GAP_BELOW_STOP'
        b[2].append(gap)
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'EVENT_WRONG_EPISODE_OR_DAY'):
            g.inspect(*b)

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

    def test_new_52_session_high_event_recognized(self):
        b = data()
        row = list(b[2][1])
        row[0] = KEY+'|'+DAY+'|NEW_52_SESSION_HIGH|1'
        row[5] = 'NEW_52_SESSION_HIGH'
        b[2].append(row)
        self.assertEqual(g.inspect(*b)['event_count'], 2)

    def test_near_stop_one_atr_event_recognized(self):
        b = data()
        row = list(b[2][1])
        row[0] = KEY+'|'+DAY+'|NEAR_STOP_1ATR|1'
        row[5] = 'NEAR_STOP_1ATR'
        b[2].append(row)
        self.assertEqual(g.inspect(*b)['event_count'], 2)

    def test_disputed_event_is_quarantined_not_delivered(self):
        import alert_ledger_contract as contract
        b = data()
        row = list(b[2][1])
        row[0] = KEY+'|'+DAY+'|NEW_52_SESSION_HIGH|1'
        row[5] = 'NEW_52_SESSION_HIGH'
        row[17] = contract.QUARANTINED
        b[2].append(row)
        report = g.inspect(*b)
        self.assertEqual(report['state'], 'HOLD_DISPUTED_EVENT_NON_EMITTING')
        self.assertEqual(report['quarantined_events'], 1)
        self.assertEqual(report['device_receipts_verified'], 0)
        self.assertEqual(contract.delivery_status(b[2], row[0]),
                         'DATA_DISPUTE_QUARANTINED_NO_DELIVERY')
        with self.assertRaisesRegex(contract.LedgerRefused, 'EVENT_ALREADY_RECORDED_NO_RESEND'):
            contract.verify_first_reservation(b[2], b[2], [row[0]])

    def test_missing_al_reservation_remains_higher_priority_than_review_hold(self):
        import alert_ledger_contract as contract
        b = data()
        b[2] = [b[2][0]]
        row = [EVENT.replace('AL_NEW_EPISODE', 'NEW_52_SESSION_HIGH'), KEY, DAY,
               'FAKE', DAY, 'NEW_52_SESSION_HIGH', 'REVIEW', '100', '95', '110',
               '', '', '', '', '', '', '', contract.QUARANTINED, '', '']
        b[2].append(row)
        report = g.inspect(*b)
        self.assertEqual(report['state'], 'PENDING_CURRENT_EOD_OUTBOX_RESERVATION')
        self.assertEqual(report['unreserved_current_eod_al'], 1)
        self.assertEqual(report['quarantined_events'], 1)

    def test_fake_quarantine_on_buy_is_rejected(self):
        import alert_ledger_contract as contract
        b = data()
        b[2][1][17] = contract.QUARANTINED
        with self.assertRaisesRegex(g.FlightRecorderBlocked, 'UNATTESTED_DELIVERY_STATE'):
            g.inspect(*b)
        with self.assertRaisesRegex(contract.LedgerRefused, 'QUARANTINE_WRONG_EVENT_TYPE'):
            contract.parse_ledger(b[2])

    def test_non_terminal_warning_cannot_close_position(self):
        b = data()
        b[0][1][7] = 'KAPALI • NEAR_STOP_1ATR • 1/15 SEANS'
        b[0][1][8] = DAY
        b[0][1][9] = 'NEAR_STOP_1ATR'
        with self.assertRaisesRegex(g.FlightRecorderBlocked, 'TERMINAL_EVENT_INVALID'):
            g.inspect(*b)

    def test_unknown_event_type_still_blocks(self):
        b = data()
        b[2][1][0] = KEY+'|'+DAY+'|INVENTED_EVENT|1'
        b[2][1][5] = 'INVENTED_EVENT'
        with self.assertRaisesRegex(g.FlightRecorderBlocked, 'EVENT_WRONG_EPISODE_OR_DAY'):
            g.inspect(*b)

    def _overlap_fixture(self, with_prior=True):
        import alert_ledger_contract as contract
        b = data()
        day2 = '2026-10-28'
        new_key = day2+'|FAKE'
        b[1].append([day2,'fixture','477','477','477','0',
                     'TRUE','1','private',b[1][1][9]])
        previous = b[0][1]
        previous[7] = 'AÇIK • 1/15 SEANS' if with_prior else 'KAPALI • STOP_TOUCHED • 1/15 SEANS'
        if not with_prior:
            previous[8] = DAY
            previous[9] = 'STOP_TOUCHED'
            closed = list(b[2][1])
            closed[0] = KEY+'|'+DAY+'|STOP_TOUCHED|1'
            closed[5] = 'STOP_TOUCHED'
            b[2].append(closed)
        successor = list(previous)
        successor[0], successor[1], successor[7] = new_key, day2, 'AÇIK • 0/15 SEANS'
        successor[8], successor[9], successor[10] = '', '', ''
        b[0].append(successor)
        ev = list(b[2][1])
        ev[0], ev[1], ev[2], ev[4], ev[17] = (
            new_key+'|'+day2+'|AL_NEW_EPISODE|1',new_key,day2,day2,contract.SUPPRESSED)
        b[2].append(ev)
        b[3][0][1] = day2
        return b, ev[0]

    def test_active_prior_suppression_is_logged_without_delivery(self):
        import alert_ledger_contract as contract
        b,key = self._overlap_fixture()
        result = g.inspect(*b)
        self.assertEqual(result['suppressed_active_al'],1)
        self.assertEqual(result['unreserved_current_eod_al'],0)
        self.assertEqual(result['matched_new_al_outbox'],2)
        self.assertEqual(contract.delivery_status(b[2],key),
                         'SUPPRESSED_ACTIVE_EPISODE_NO_DELIVERY')
        self.assertEqual(result['device_receipts_verified'],0)
        with self.assertRaisesRegex(contract.LedgerRefused,'EVENT_ALREADY_RECORDED_NO_RESEND'):
            contract.verify_first_reservation(b[2],b[2],[key])

    def test_suppression_without_prior_open_fails_closed(self):
        b,key = self._overlap_fixture(with_prior=False)
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    'SUPPRESSION_WITHOUT_PRIOR_ACTIVE_EPISODE'):
            g.inspect(*b)

    def test_suppressed_stop_is_not_a_valid_delivery_state(self):
        import alert_ledger_contract as contract
        b = data()
        b[2][1][0] = KEY+'|'+DAY+'|STOP_TOUCHED|1'
        b[2][1][5] = 'STOP_TOUCHED'
        b[2][1][17] = contract.SUPPRESSED
        with self.assertRaisesRegex(contract.LedgerRefused,
                                    'SUPPRESSION_ONLY_FOR_NEW_AL_EPISODE'):
            contract.parse_ledger(b[2])
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    'UNATTESTED_DELIVERY_STATE'):
            g.inspect(*b)

    def test_unreserved_no_prior_open_remains_fail_closed(self):
        b = data()
        b[2] = [b[2][0]]
        result = g.inspect(*b)
        self.assertEqual(result['unreserved_current_eod_al'],1)
        self.assertEqual(result['suppressed_active_al'],0)

    def test_suppressed_event_duplicate_key_is_rejected(self):
        import alert_ledger_contract as contract
        b,key = self._overlap_fixture()
        b[2].append(list(b[2][-1]))
        with self.assertRaisesRegex(contract.LedgerRefused,'DUPLICATE_EVENT_KEY'):
            contract.parse_ledger(b[2])
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'DUPLICATE_EVENT'):
            g.inspect(*b)

if __name__=='__main__':
    unittest.main()
