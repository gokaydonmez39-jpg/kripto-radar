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


def reviewed_gild_forward_fixture():
    """All fixtures synthetic except reviewed public dates, price levels and status.

    20 Nov natural FINAL is intentionally absent. 23 Nov is a NEW natural
    forward day; this fixture never inserts/replays or retroactively attests
    a 20 Nov schedule, and it creates no notification or device ACK.
    """
    owner='2026-10-29|GILD'
    first='2026-10-29'
    final='2026-11-23'
    def scan(day,sha,new):
        return [day,'GitHub schedule VERIFIED IEX EOD',
                '477','477','477','0','TRUE',str(new),
                'https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/999001',
                'scopeSHA='+sha[0]+';algorithmSHA='+sha[1]+
                ';source_event=schedule;NO_ORDERS; SHEETS_READBACK_REQUIRED; NOT_DEVICE_ACK']
    c=[list(g.CANDIDATE_HEADER),
       [owner,first,'GILD','TEKNİK AL ADAYI',
        '165,58','157,447','181,846',
        'KAPALI • TIME_EXIT_AT_CLOSE • 15/15 SEANS',
        '2026-11-19','TIME_EXIT_AT_CLOSE','0,607',
        'KAYDEDİLDİ_BİLDİRİM_AYRI','NON_EXECUTABLE_PUBLIC_RESEARCH']]
    s=[list(g.SCAN_HEADER),
       scan(first,g.PIT_PRE_CUTOVER_SHA,1),
       scan('2026-11-19',g.PIT_ROKU_REPLACEMENT_SHA,0),
       scan(final,g.PIT_IEX_UTC_CODE_SHA,0)]
    def event(day,code,status,close,rank):
        return [
            owner+'|'+day+'|'+code+'|1',owner,first,'GILD',day,
            code,rank,close,'157.447','181.846',
            '', '', '', '', '', '0/15','',status,'',''
        ]
    initial=event(first,'AL_NEW_EPISODE',
                  'ALERT_REQUESTED_NOT_DEVICE_ACK','165.58','YENİ AL')
    quarantined=event('2026-10-30','NEW_52_SESSION_HIGH',
                      'DATA_DISPUTE_REVIEW_REQUIRED','170.95','ÖNEMLİ')
    quarantined[18]='2026-10-31 00:00:11 TRT'
    quarantined[19]=(
        '30 Ekim Alpaca IEX raw O/H/L/C 169.82/175.55/169.06/170.95; '
        'kapanış 170.95 > önceki52 tepe 165.62; '
        'hacim 691827 >= önceki20 ortalama 258653.95; 52/52 XNAS, teorik takip. '
        '| 31 Ekim denetim düzeltmesi: '
        '29 Ekim AL barında GILD close 165.58 > önceki52 tepe 160.83; '
        '30 Ekim de eşik üzerinde devam ediyor. '
        'İlk eşik geçişi değil; NEW_52_SESSION_HIGH kullanıcı alarmı FAIL_CLOSED, '
        'DATA_DISPUTE_REVIEW_REQUIRED. Mesaj oluşturulmadı.'
    )
    terminal=event('2026-11-19','TIME_EXIT_AT_CLOSE',
                   'ALERT_REQUESTED_NOT_DEVICE_ACK','166.585','SURE_SONU')
    e=[list(g.ALERT_HEADER),initial,quarantined,terminal]
    panel=[['Son doğrulanmış tarama seansı',final]]
    return [c,s,e,panel]


class ReviewedClosedGildHistoricalQuarantineRegression(unittest.TestCase):
    def test_verified_historical_non_emitting_event_does_not_block_future_day(self):
        b=reviewed_gild_forward_fixture()
        report=g.inspect(*b,expected_asof='2026-11-23')
        self.assertEqual(report['state'],'PASS_PENDING_DEVICE_ACK')
        self.assertEqual(report['quarantined_events'],1)
        self.assertEqual(report['reviewed_historical_non_emitting_events'],1)
        self.assertEqual(report['unresolved_quarantined_events'],0)
        self.assertEqual(report['device_receipts_verified'],0)
        self.assertFalse(report['writes'])
        self.assertFalse(report['orders'])
        self.assertNotIn('GILD',str(report))
        self.assertNotIn('157.447',str(report))

    def test_20_nov_missing_natural_final_is_never_retrospectively_invented(self):
        b=reviewed_gild_forward_fixture()
        self.assertNotIn('2026-11-20',[row[0] for row in b[1][1:]])
        with self.assertRaisesRegex(
                g.FlightRecorderBlocked,'FLIGHT_EXPECTED_COMPLETED_EOD_MISSING'):
            g.inspect(*b,expected_asof='2026-11-20')

    def test_tampered_historical_review_or_missing_terminal_remains_hold(self):
        for changed in ('wrong_note','missing_note','wrong_time',
                        'unclosed_episode','different_stop','different_status'):
            with self.subTest(change=changed):
                b=reviewed_gild_forward_fixture()
                if changed=='wrong_note':
                    b[2][2][19]=b[2][2][19].replace(
                        'İlk eşik geçişi değil','YENİ İLK EŞİK')
                elif changed=='missing_note':
                    b[2][2][19]=''
                elif changed=='wrong_time':
                    b[2][2][18]='2026-11-01 00:00:11 TRT'
                elif changed=='unclosed_episode':
                    b[0][1][7]='AÇIK • 0/15 SEANS'
                    b[0][1][8:10]=['','']
                    b[2]=b[2][:3]
                elif changed=='different_stop':
                    b[2][2][8]='157.448'
                elif changed=='different_status':
                    b[2][2][17]='ALERT_REQUESTED_NOT_DEVICE_ACK'
                try:
                    report=g.inspect(*b,expected_asof='2026-11-23')
                except g.FlightRecorderBlocked:
                    continue
                self.assertNotEqual(report['state'],'PASS_PENDING_DEVICE_ACK')
                self.assertNotEqual(report.get('unresolved_quarantined_events'),0)

    def test_second_unrelated_quarantine_is_not_waived(self):
        b=reviewed_gild_forward_fixture()
        second=list(b[2][2])
        second[0]='2026-10-29|GILD|2026-11-01|NEW_52_SESSION_HIGH|1'
        second[4]='2026-11-01'
        second[18]=''
        second[19]='UNREVIEWED'
        b[2].append(second)
        report=g.inspect(*b,expected_asof='2026-11-23')
        self.assertEqual(report['state'],'HOLD_DISPUTED_EVENT_NON_EMITTING')
        self.assertEqual(report['quarantined_events'],2)
        self.assertEqual(report['unresolved_quarantined_events'],1)
        self.assertEqual(report['reviewed_historical_non_emitting_events'],1)


class FlightNegativeTests(unittest.TestCase):
    def test_approved_2026_11_03_pit_provenance_switch(self):
        b=data()
        b[1][1][9]=('scopeSHA=420025dd5b83b59fedd3d9af4332471fee731aedfaacb616ce80ca473bef6745'
                   ';algorithmSHA=d7d119c2125d75981f86850c2283973b2a70b5a2aa6aa638600a60f5039969c8')
        b[1].append(['2026-11-03','GitHub','477','477','477','0',
                     'TRUE','0','private',
                     'scopeSHA=4045849b129e74a600982db512f2e5ad5343a960544476721ca552544f328a20'
                     ';algorithmSHA=c8fc8877aa0a9e55a8e1b9707886c17210e3859fc91f896af90a26b4a98c134e'])
        result=g.inspect(*b,expected_asof='2026-11-03')
        self.assertEqual(result['source_verified_issuance_days'],2)
        self.assertEqual(result['matched_new_al_outbox'],1)
        self.assertEqual(result['device_receipts_verified'],0)

    def test_pit_migration_wrong_legacy_fingerprint_is_rejected(self):
        b=data()
        b[1][1][9]=('scopeSHA=420025dd5b83b59fedd3d9af4332471fee731aedfaacb616ce80ca473bef6745'
                   ';algorithmSHA='+'f'*64)
        b[1].append(['2026-11-03','GitHub','477','477','477','0','TRUE','0',
                     'private',
                     'scopeSHA=4045849b129e74a600982db512f2e5ad5343a960544476721ca552544f328a20'
                     ';algorithmSHA=c8fc8877aa0a9e55a8e1b9707886c17210e3859fc91f896af90a26b4a98c134e'])
        with self.assertRaisesRegex(g.FlightRecorderBlocked,'HISTORICAL_ISSUANCE_SHA_DRIFT'):
            g.inspect(*b,expected_asof='2026-11-03')

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

    def _suppressed_successor_closes_after_prior_was_live_at_issuance(self):
        """Prior is closed *now* but was open on successor's AL day."""
        b,_ = self._overlap_fixture(with_prior=True)
        day3 = '2026-10-29'
        b[1].append([day3,'fixture','477','477','477','0',
                     'TRUE','0','private',b[1][1][9]])
        earlier=b[0][1]
        later=b[0][2]
        for candidate in (earlier,later):
            candidate[7]='KAPALI • STOP_TOUCHED • 2/15 SEANS'
            candidate[8]=day3
            candidate[9]='STOP_TOUCHED'
        terminal=list(b[2][1])
        terminal[0]=KEY+'|'+day3+'|STOP_TOUCHED|1'
        terminal[4]=day3
        terminal[5]='STOP_TOUCHED'
        terminal[17]=g.EVENT_PENDING
        b[2].append(terminal)
        b[3][0][1]=day3
        return b

    def test_suppressed_early_al_later_closed_never_demands_second_stop(self):
        b=self._suppressed_successor_closes_after_prior_was_live_at_issuance()
        result=g.inspect(*b,expected_asof='2026-10-29')
        self.assertEqual(result['matched_terminal_outbox'],1)
        self.assertEqual(result['suppressed_active_al'],1)
        self.assertEqual(result['suppressed_terminal_not_duplicated'],1)
        self.assertEqual(result['device_receipts_verified'],0)

    def test_suppressed_successor_without_prior_terminal_still_blocks(self):
        b=self._suppressed_successor_closes_after_prior_was_live_at_issuance()
        b[2].pop()
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    'MISSING_TERMINAL_EVENT'):
            g.inspect(*b,expected_asof='2026-10-29')

    def _same_session_close_fixture(self):
        b=self._suppressed_successor_closes_after_prior_was_live_at_issuance()
        b[0][1][7]='KAPALI • STOP_TOUCHED • 1/15 SEANS'
        b[0][1][8]='2026-10-28'
        b[2][-1][0]=KEY+'|2026-10-28|STOP_TOUCHED|1'
        b[2][-1][4]='2026-10-28'
        return b

    def test_prior_close_on_successor_day_exact_terminal_proves_overlap(self):
        b=self._same_session_close_fixture()
        result=g.inspect(*b,expected_asof='2026-10-29')
        self.assertEqual(result['suppressed_active_al'],1)
        self.assertEqual(result['device_receipts_verified'],0)

    def test_same_session_without_terminal_does_not_prove_overlap(self):
        b=self._same_session_close_fixture()
        b[2].pop()
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    'SUPPRESSION_WITHOUT_PRIOR_ACTIVE_EPISODE'):
            g.inspect(*b,expected_asof='2026-10-29')

    def test_same_session_zero_duration_does_not_prove_overlap(self):
        b=self._same_session_close_fixture()
        b[0][1][7]='KAPALI • STOP_TOUCHED • 0/15 SEANS'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    'SUPPRESSION_WITHOUT_PRIOR_ACTIVE_EPISODE'):
            g.inspect(*b,expected_asof='2026-10-29')

    def test_same_session_mismatched_terminal_state_does_not_prove_overlap(self):
        b=self._same_session_close_fixture()
        b[0][1][7]='KAPALI • TARGET_TOUCHED • 1/15 SEANS'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    'SUPPRESSION_WITHOUT_PRIOR_ACTIVE_EPISODE'):
            g.inspect(*b,expected_asof='2026-10-29')

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


class ExplicitSecondPolicyCutover20261106Tests(unittest.TestCase):
    """No historical rewrite: approve only the reviewed corporate-action asof pin."""
    NEW_ASOF_POLICY = (
        '4045849b129e74a600982db512f2e5ad5343a960544476721ca552544f328a20',
        'c13c5a7ad14c1753d044f2392f37c6fdf7cd5e11f6c2edd3954902aa0716056b',
    )

    @staticmethod
    def _scan(day, pair, count=0):
        return [day, 'GitHub verified private', '477','477','477','0',
                'TRUE',str(count),'private',
                'scopeSHA='+pair[0]+';algorithmSHA='+pair[1]]

    def fixture(self):
        b = data()
        b[1][1] = self._scan(DAY, g.PIT_PRE_CUTOVER_SHA, count=1)
        b[1].append(self._scan('2026-11-03',g.PIT_POST_CUTOVER_SHA))
        b[1].append(self._scan('2026-11-05',g.PIT_POST_CUTOVER_SHA))
        b[1].append(self._scan('2026-11-06',self.NEW_ASOF_POLICY))
        b[3][0][1] = '2026-11-06'
        b[0][1][7] = 'AÇIK • 8/15 SEANS'
        return b

    def test_approved_three_epoch_policy_corpus_passes_without_changing_rows(self):
        b = self.fixture()
        before=deepcopy(b)
        result=g.inspect(*b,expected_asof='2026-11-06')
        self.assertEqual(result['source_verified_issuance_days'],4)
        self.assertEqual(result['latest_verified_scan_asof'],'2026-11-06')
        self.assertEqual(result['unreserved_prior_eod_al'],0)
        self.assertEqual(result['device_receipts_verified'],0)
        self.assertFalse(result['writes'])
        self.assertEqual(b,before)

    def test_wrong_legacy_pre_cutover_fingerprint_blocks(self):
        b=self.fixture()
        b[1][1]=self._scan(DAY,(g.PIT_PRE_CUTOVER_SHA[0],'f'*64),count=1)
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    'FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT'):
            g.inspect(*b,expected_asof='2026-11-06')

    def test_wrong_middle_policy_fingerprint_blocks(self):
        b=self.fixture()
        b[1][3]=self._scan('2026-11-05',(g.PIT_POST_CUTOVER_SHA[0],'e'*64))
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    'FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT'):
            g.inspect(*b,expected_asof='2026-11-06')

    def test_new_asof_policy_may_not_be_backdated_to_5_nov(self):
        b=self.fixture()
        b[1].pop()
        b[1][-1]=self._scan('2026-11-05',self.NEW_ASOF_POLICY)
        b[3][0][1]='2026-11-05'
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    'FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT'):
            g.inspect(*b,expected_asof='2026-11-05')

    def test_unreviewed_latest_policy_sha_fails_closed(self):
        b=self.fixture()
        b[1][-1]=self._scan('2026-11-06',(self.NEW_ASOF_POLICY[0],'f'*64))
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    'FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT'):
            g.inspect(*b,expected_asof='2026-11-06')



class FutureUtcPolicyEpochTests(unittest.TestCase):
    """Forward-only 23 Nov primary IEX UTC code-hash cutover; zero IO."""

    FUTURE_PAIR=(
        "3d1d226e2ef511570b2abd57e59c74d2c2156e6eed9baf4a08b8d3df82223060",
        "cac4dd7b729e23cd4f6e4c181f569ef286858c1473217e46358202f595f7723c",
    )

    @staticmethod
    def row(day,pair,count=0):
        return [day,"GitHub schedule verified research-only","477","477",
                "477","0","TRUE",str(count),"private",
                "scopeSHA="+pair[0]+";algorithmSHA="+pair[1]]

    def corpus(self,*,new_day=True):
        b=data()
        b[1][1]=self.row(DAY,g.PIT_PRE_CUTOVER_SHA,1)
        for day,pair in (
            ("2026-11-03",g.PIT_POST_CUTOVER_SHA),
            ("2026-11-06",g.PIT_ASOF_PIN_SHA),
            ("2026-11-10",g.PIT_ROKU_REPLACEMENT_SHA),
            ("2026-11-19",g.PIT_ROKU_REPLACEMENT_SHA),
        ):
            b[1].append(self.row(day,pair))
        if new_day:
            b[1].append(self.row("2026-11-23",self.FUTURE_PAIR))
        b[3][0][1]="2026-11-23" if new_day else "2026-11-19"
        return b

    def test_exact_new_engine_policy_digest_is_attested(self):
        import runner
        self.assertEqual(runner.analysis_fingerprint(),self.FUTURE_PAIR[1])
        self.assertEqual(g.PIT_IEX_UTC_CODE_SHA,self.FUTURE_PAIR)
        self.assertEqual(g.PIT_IEX_UTC_CODE_CUTOVER,"2026-11-23")

    def test_valid_23_nov_477_accepts_missing_20_without_replay(self):
        b=self.corpus()
        frozen=deepcopy(b)
        self.assertNotIn("2026-11-20",[r[0] for r in b[1][1:]])
        out=g.inspect(*b,expected_asof="2026-11-23")
        self.assertEqual(out["latest_verified_scan_asof"],"2026-11-23")
        self.assertEqual(out["source_verified_issuance_days"],6)
        self.assertEqual(out["unreserved_prior_eod_al"],0)
        self.assertEqual(out["device_receipts_verified"],0)
        self.assertEqual(b,frozen)

    def test_old_19_nov_receipt_still_accepted_unchanged(self):
        b=self.corpus(new_day=False)
        out=g.inspect(*b,expected_asof="2026-11-19")
        self.assertEqual(out["latest_verified_scan_asof"],"2026-11-19")
        self.assertEqual(out["source_verified_issuance_days"],5)

    def test_old_policy_is_not_valid_for_23_nov_eod(self):
        b=self.corpus()
        b[1][-1]=self.row("2026-11-23",g.PIT_ROKU_REPLACEMENT_SHA)
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    "FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT"):
            g.inspect(*b,expected_asof="2026-11-23")

    def test_new_code_policy_cannot_be_backdated_to_20_nov(self):
        b=self.corpus()
        b[1][-1]=self.row("2026-11-20",self.FUTURE_PAIR)
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    "FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT"):
            g.inspect(*b,expected_asof="2026-11-20")

    def test_original_19_nov_fingerprint_cannot_be_rewritten(self):
        b=self.corpus()
        b[1][-2]=self.row("2026-11-19",self.FUTURE_PAIR)
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    "FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT"):
            g.inspect(*b,expected_asof="2026-11-23")

    def test_unreviewed_future_sha_remains_blocked(self):
        b=self.corpus()
        b[1][-1]=self.row("2026-11-23",
                          (self.FUTURE_PAIR[0],"f"*64))
        with self.assertRaisesRegex(g.FlightRecorderBlocked,
                                    "FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT"):
            g.inspect(*b,expected_asof="2026-11-23")


class FlightRecorderMandatoryReleaseGateTests(unittest.TestCase):
    def test_mandatory_ci_includes_second_sha_cutover_tests_in_both_modes(self):
        from pathlib import Path
        ci = (Path(__file__).resolve().parents[2] /
              '.github/workflows/xray-nasdaq-477-pr-required-readonly.yml'
              ).read_text(encoding='utf-8')
        self.assertIn('python -m unittest -q test_private_flight_recorder',ci)
        self.assertIn('python -O -m unittest -q test_private_flight_recorder',ci)
        self.assertIn('  xray-477-required-ci:', ci)
        self.assertNotIn('continue-on-error: true',ci)


if __name__=='__main__':
    unittest.main()
