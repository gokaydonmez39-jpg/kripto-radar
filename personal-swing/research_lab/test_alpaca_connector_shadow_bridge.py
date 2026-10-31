"""Deterministic connector tests; ALL EVENT FIXTURES ARE SYNTHETIC."""
import unittest
from alpaca_connector_shadow_bridge import audit_connector_sample, SampleRejected

OBS = '2026-10-31T12:00:00Z'
START, END = '2026-08-01', '2026-10-31'
SYMBOLS = ['AAPL', 'MSFT']

def fixture():
    return {'request': {
        'ca_types': ['cash_dividend'], 'start': START, 'end': END,
        'symbols': SYMBOLS.copy(), 'cusips': None, 'ids': None,
        'limit': 15, 'sort': 'asc'},
        'announcements': {'cash_dividends': [
        {'id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
         'corporate_action_type':'cash_dividends','symbol':'AAPL',
         'rate':0.5,'process_date':'2026-09-29','ex_date':'2026-09-15',
         'record_date':'2026-09-15','payable_date':'2026-09-29'},
        {'id':'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
         'corporate_action_type':'cash_dividends','symbol':'MSFT',
         'rate':0.75,'process_date':'2026-08-17','ex_date':'2026-07-31',
         'record_date':'2026-07-31','payable_date':'2026-08-17'}
    ]}}

class ConnectedSampleTests(unittest.TestCase):
    def run_check(self, payload=None, **overrides):
        opts=dict(symbols=SYMBOLS,start=START,end=END,observed_at_utc=OBS)
        opts.update(overrides)
        return audit_connector_sample(fixture() if payload is None else payload, **opts)

    def test_positive_is_review_only(self):
        r=self.run_check()
        self.assertEqual(r['event_count'],2)
        self.assertEqual(r['status'],'SAMPLE_FOR_REVIEW')
        self.assertFalse(r['pagination_complete_proven'])
        self.assertFalse(r['market_event_absence_proven'])
        self.assertFalse(r['may_generate_al'])

    def test_empty_is_never_clearance(self):
        p=fixture();p['announcements']={}
        r=self.run_check(p)
        self.assertEqual(r['status'],'NO_EVENTS_SAMPLED_NOT_CLEAR')
        self.assertFalse(r['market_event_absence_proven'])

    def test_hitting_limit_is_unknown(self):
        p=fixture();p['request']['limit']=2
        r=self.run_check(p)
        self.assertEqual(r['status'],'CAP_REACHED_COVERAGE_UNKNOWN')
        self.assertFalse(r['pagination_complete_proven'])

    def test_exceeding_limit_is_error(self):
        p=fixture();p['request']['limit']=1
        with self.assertRaisesRegex(SampleRejected,'RESPONSE_EXCEEDS_REQUESTED_LIMIT'):
            self.run_check(p)

    def test_duplicate_event_refused(self):
        p=fixture();p['announcements']['cash_dividends'][1]['id']=p['announcements']['cash_dividends'][0]['id']
        with self.assertRaisesRegex(SampleRejected,'EVENT_ID_DUPLICATE'):
            self.run_check(p)

    def test_future_type_group_refused(self):
        p=fixture();p['announcements']['reverse_splits']=[]
        with self.assertRaisesRegex(SampleRejected,'UNSUPPORTED_CONNECTOR_CA_GROUP'):
            self.run_check(p)

    def test_wrong_event_group_refused(self):
        p=fixture();p['announcements']['cash_dividends'][0]['corporate_action_type']='forward_splits'
        with self.assertRaisesRegex(SampleRejected,'EVENT_KIND_MISMATCH'):
            self.run_check(p)

    def test_missing_rate_refused(self):
        p=fixture();p['announcements']['cash_dividends'][0]['rate']=None
        with self.assertRaisesRegex(SampleRejected,'DIVIDEND_RATE_INVALID'):
            self.run_check(p)

    def test_nan_rate_refused(self):
        p=fixture();p['announcements']['cash_dividends'][0]['rate']=float('nan')
        with self.assertRaisesRegex(SampleRejected,'DIVIDEND_RATE_INVALID'):
            self.run_check(p)

    def test_boolean_rate_refused(self):
        p=fixture();p['announcements']['cash_dividends'][0]['rate']=True
        with self.assertRaisesRegex(SampleRejected,'DIVIDEND_RATE_INVALID'):
            self.run_check(p)

    def test_outside_ticker_refused(self):
        p=fixture();p['announcements']['cash_dividends'][0]['symbol']='TSLA'
        with self.assertRaisesRegex(SampleRejected,'EVENT_SYMBOL_OUTSIDE_SCOPE'):
            self.run_check(p)

    def test_wrong_query_order_refused(self):
        p=fixture();p['request']['symbols']=['MSFT','AAPL']
        with self.assertRaisesRegex(SampleRejected,'REQUEST_SYMBOL_SCOPE_MISMATCH'):
            self.run_check(p)

    def test_wrong_date_refused(self):
        p=fixture();p['request']['end']='2026-10-30'
        with self.assertRaisesRegex(SampleRejected,'REQUEST_DATE_MISMATCH'):
            self.run_check(p)

    def test_future_event_refused(self):
        p=fixture();p['announcements']['cash_dividends'][0]['process_date']='2026-11-01'
        with self.assertRaisesRegex(SampleRejected,'EVENT_OUTSIDE_REQUEST_WINDOW'):
            self.run_check(p)

    def test_non_utc_refused(self):
        with self.assertRaisesRegex(SampleRejected,'OBSERVATION_TIME_NOT_UTC'):
            self.run_check(observed_at_utc='2026-10-31T15:00:00+03:00')

    def test_unreviewed_filter_refused(self):
        p=fixture();p['request']['ca_types']=['forward_split']
        with self.assertRaisesRegex(SampleRejected,'UNVERIFIED_CORPORATE_ACTION_FILTER'):
            self.run_check(p)

    def test_hidden_cusip_filter_refused(self):
        p=fixture();p['request']['cusips']=['000000000']
        with self.assertRaisesRegex(SampleRejected,'ADDITIONAL_QUERY_FILTER_NOT_REVIEWED'):
            self.run_check(p)

    def test_fake_id_refused(self):
        p=fixture();p['announcements']['cash_dividends'][0]['id']='not-a-uuid'
        with self.assertRaisesRegex(SampleRejected,'EVENT_ID_INVALID'):
            self.run_check(p)

    def test_every_side_effect_and_pit_claim_is_false(self):
        r=self.run_check()
        for flag in ('may_generate_al','may_modify_stop_target','may_notify',
                     'may_place_order','may_write_private_sheets','historical_pit_proven',
                     'source_data_rights_proven','provider_known_at_proven'):
            self.assertIs(r[flag],False)

if __name__ == '__main__':
    unittest.main()
