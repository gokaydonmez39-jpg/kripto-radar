"""Offline negative tests for raw single-exchange price discontinuity witness."""
import copy
import unittest
import raw_corporate_action_witness as w
from private_sheet_writer import CANDIDATE_HEADER, SCAN_HEADER

URL='https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/999001'
DAY='2026-10-28'
DATES=['2026-10-26','2026-10-27','2026-10-28']


def fixture():
    candidates=[list(CANDIDATE_HEADER),
                ['2026-10-26|AAA','2026-10-26','AAA','TEKNİK AL ADAYI',
                 '100','95','110','AÇIK • 2/15 SEANS','','','','','']]
    scans=[list(SCAN_HEADER),
           [DAY,'GitHub auto VERIFIED IEX EOD','477','477','477',
            '0','TRUE','0',URL,'scopeSHA='+'a'*64+';algorithmSHA='+'b'*64]]
    bars={'AAA':[{'timestamp':d+'T04:00:00+00:00',
                  'open':100.,'high':102.,'low':98.,'close':100.,
                  'volume':1000.} for d in DATES]}
    return candidates,scans,bars


class RawCaWitnessTests(unittest.TestCase):
    def test_healthy_input_does_not_claim_corporate_action_clearance(self):
        c,s,b=fixture()
        result=w.inspect(c,s,b,DAY)
        self.assertEqual(result['state'],
                         'NO_LARGE_RAW_DISCONTINUITY_CA_STATUS_UNVERIFIED')
        self.assertFalse(result['corporate_action_cleared'])
        self.assertFalse(result['independent_vendor_corporate_action_confirmed'])
        self.assertEqual(result['raw_session_bars_checked'],3)
        self.assertFalse(result['sheet_writes'])
        self.assertFalse(result['device_ack'])

    def test_split_like_half_price_is_review_not_execution(self):
        c,s,b=fixture()
        b['AAA'][1].update(open=50.,high=51.,low=49.,close=50.)
        b['AAA'][2].update(open=50.,high=52.,low=49.,close=50.)
        out=w.inspect(c,s,b,DAY)
        self.assertEqual(out['large_raw_open_gap_count'],1)
        self.assertEqual(out['state'],'REVIEW_REQUIRED')
        self.assertFalse(out['auto_strategy_change'])

    def test_reverse_split_double_price_is_review(self):
        c,s,b=fixture()
        b['AAA'][1].update(open=200.,high=201.,low=198.,close=200.)
        b['AAA'][2].update(open=200.,high=201.,low=199.,close=200.)
        self.assertEqual(w.inspect(c,s,b,DAY)['state'],'REVIEW_REQUIRED')

    def test_true_large_earnings_gap_also_needs_review_not_claim_split(self):
        c,s,b=fixture()
        b['AAA'][1].update(open=70.,high=73.,low=69.,close=72.)
        out=w.inspect(c,s,b,DAY)
        self.assertEqual(out['state'],'REVIEW_REQUIRED')
        self.assertFalse(out['corporate_action_cleared'])

    def test_changed_original_close_is_flagged_even_without_gap(self):
        c,s,b=fixture()
        b['AAA'][0]['close']=99.
        result=w.inspect(c,s,b,DAY)
        self.assertEqual(result['historical_issuance_close_mismatches'],1)
        self.assertEqual(result['state'],'REVIEW_REQUIRED')

    def test_one_cent_is_not_mere_rounding(self):
        c,s,b=fixture()
        b['AAA'][0]['close']=100.02
        self.assertEqual(w.inspect(c,s,b,DAY)['state'],'REVIEW_REQUIRED')

    def test_missing_raw_session_fails_closed(self):
        c,s,b=fixture()
        b['AAA'].pop(1)
        with self.assertRaisesRegex(w.ActionWitnessBlocked,'RAW_MISSING_XNAS_SESSION'):
            w.inspect(c,s,b,DAY)

    def test_duplicate_raw_session_fails_closed(self):
        c,s,b=fixture()
        b['AAA'].append(copy.deepcopy(b['AAA'][2]))
        with self.assertRaisesRegex(w.ActionWitnessBlocked,'DUPLICATE_RAW_BAR'):
            w.inspect(c,s,b,DAY)

    def test_invalid_ohlc_fails_closed(self):
        c,s,b=fixture()
        b['AAA'][2]['low']=110.
        with self.assertRaisesRegex(w.ActionWitnessBlocked,'INVALID_RAW_PRICE_RANGE'):
            w.inspect(c,s,b,DAY)

    def test_nan_fails_closed(self):
        c,s,b=fixture()
        b['AAA'][1]['close']=float('nan')
        with self.assertRaisesRegex(w.ActionWitnessBlocked,'INVALID_RAW_OHLCV'):
            w.inspect(c,s,b,DAY)

    def test_extra_symbol_provider_scope_fails_closed(self):
        c,s,b=fixture()
        b['EXTRA']=copy.deepcopy(b['AAA'])
        with self.assertRaisesRegex(w.ActionWitnessBlocked,'RAW_SYMBOL_SCOPE_DRIFT'):
            w.inspect(c,s,b,DAY)

    def test_asof_requires_full_final_477(self):
        c,s,b=fixture()
        s[1][4]='476'
        with self.assertRaisesRegex(w.ActionWitnessBlocked,'EOD_SCAN_NOT_FULL_FINAL'):
            w.inspect(c,s,b,DAY)

    def test_episode_duplicate_or_tamper_fails_closed(self):
        c,s,b=fixture()
        c.append(copy.deepcopy(c[1]))
        with self.assertRaisesRegex(w.ActionWitnessBlocked,'EPISODE_IDENTITY'):
            w.inspect(c,s,b,DAY)

    def test_absent_required_date_is_not_yesterdays_current(self):
        c,s,b=fixture()
        b['AAA']=b['AAA'][:-1]
        with self.assertRaisesRegex(w.ActionWitnessBlocked,'RAW_MISSING_XNAS_SESSION'):
            w.inspect(c,s,b,DAY)

    def test_non_session_asof_fails(self):
        c,s,b=fixture()
        with self.assertRaisesRegex(w.ActionWitnessBlocked,'BAD_ASOF'):
            w.inspect(c,s,b,'2026-10-25')

    def test_rounded_two_decimal_original_price_is_accepted(self):
        c,s,b=fixture()
        b['AAA'][0]['close']=100.004
        self.assertEqual(w.inspect(c,s,b,DAY)['state'],
                         'NO_LARGE_RAW_DISCONTINUITY_CA_STATUS_UNVERIFIED')

    def test_multiple_episodes_share_one_raw_price_request(self):
        c,s,b=fixture()
        c.append(['2026-10-27|AAA','2026-10-27','AAA','TEKNİK AL ADAYI',
                  '100','95','110','AÇIK • 1/15 SEANS','','','','',''])
        result=w.inspect(c,s,b,DAY)
        self.assertEqual(result['candidate_count'],2)
        self.assertEqual(result['unique_symbol_count'],1)
        self.assertEqual(result['raw_session_bars_checked'],3)


if __name__=='__main__':
    unittest.main()
