"""Deterministic connector tests; ALL EVENT FIXTURES ARE SYNTHETIC."""
import unittest
from alpaca_connector_shadow_bridge import audit_connector_sample, reconcile_date_partitions, SampleRejected

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

def monthly_fixtures():
    original=fixture()
    all_events=original['announcements']['cash_dividends']
    result=[]
    for s,e in [('2026-08-01','2026-08-31'),
                ('2026-09-01','2026-09-30'),
                ('2026-10-01','2026-10-31')]:
        p=fixture()
        p['request']['start']=s
        p['request']['end']=e
        p['announcements']['cash_dividends']=[
            dict(row) for row in all_events if s<=row['process_date']<=e]
        result.append(p)
    return result

class ConnectedSampleTests(unittest.TestCase):
    def run_check(self, payload=None, **overrides):
        opts=dict(symbols=SYMBOLS,start=START,end=END,observed_at_utc=OBS)
        opts.update(overrides)
        return audit_connector_sample(fixture() if payload is None else payload, **opts)

    def reconcile(self, full=None, parts=None):
        return reconcile_date_partitions(
            fixture() if full is None else full,
            monthly_fixtures() if parts is None else parts,
            symbols=SYMBOLS,start=START,end=END,observed_at_utc=OBS)

    def test_partition_sets_match_without_completeness_promotion(self):
        r=self.reconcile()
        self.assertEqual(r['full_sample_count'],2)
        self.assertEqual(r['partition_sample_count'],2)
        self.assertEqual(r['partition_count'],3)
        self.assertTrue(r['full_sort_disputed'])
        self.assertFalse(r['pagination_completeness_proven'])
        self.assertFalse(r['unpublished_event_absence_proven'])
        self.assertFalse(r['may_notify'])

    def test_partition_gap_rejected(self):
        parts=monthly_fixtures()
        with self.assertRaisesRegex(SampleRejected,
                                    'PARTITION_GAP_OVERLAP_OR_ORDER'):
            self.reconcile(parts=[parts[0],parts[2]])

    def test_partition_missing_last_month_rejected(self):
        parts=monthly_fixtures()
        with self.assertRaisesRegex(SampleRejected,'PARTITION_NOT_EXHAUSTIVE'):
            self.reconcile(parts=parts[:2])

    def test_partition_duplicate_event_rejected(self):
        parts=monthly_fixtures()
        parts[1]['announcements']['cash_dividends'][0]['id']=(
            parts[0]['announcements']['cash_dividends'][0]['id'])
        with self.assertRaisesRegex(SampleRejected,
                                    'PARTITION_DUPLICATE_EVENT'):
            self.reconcile(parts=parts)

    def test_partition_missing_event_rejected(self):
        parts=monthly_fixtures()
        parts[1]['announcements']['cash_dividends'].clear()
        with self.assertRaisesRegex(SampleRejected,
                                    'PARTITION_EVENT_SET_OR_FIELD_MISMATCH'):
            self.reconcile(parts=parts)

    def test_partition_field_mutation_rejected(self):
        parts=monthly_fixtures()
        parts[1]['announcements']['cash_dividends'][0]['rate']=999
        with self.assertRaisesRegex(SampleRejected,
                                    'PARTITION_EVENT_SET_OR_FIELD_MISMATCH'):
            self.reconcile(parts=parts)

    def test_full_limit_blocks_reconciliation(self):
        full=fixture()
        full['request']['limit']=2
        with self.assertRaisesRegex(SampleRejected,
                                    'FULL_REQUEST_LIMIT_REACHED'):
            self.reconcile(full=full)

    def test_partition_limit_blocks_reconciliation(self):
        parts=monthly_fixtures()
        parts[0]['request']['limit']=1
        with self.assertRaisesRegex(SampleRejected,
                                    'PARTITION_REQUEST_LIMIT_REACHED'):
            self.reconcile(parts=parts)

    def test_positive_is_review_only(self):
        r=self.run_check()
        self.assertEqual(r['event_count'],2)
        self.assertEqual(r['status'],'CONNECTOR_ORDER_DISPUTE_REVIEW_REQUIRED')
        self.assertFalse(r['pagination_complete_proven'])
        self.assertFalse(r['market_event_absence_proven'])
        self.assertFalse(r['may_generate_al'])

    def test_sorted_process_dates_can_be_research_sample(self):
        p=fixture()
        p['announcements']['cash_dividends'].reverse()
        r=self.run_check(p)
        self.assertTrue(r['process_date_order_matches_requested_sort'])
        self.assertEqual(r['status'],'SAMPLE_FOR_REVIEW')
        self.assertFalse(r['pagination_complete_proven'])
        self.assertFalse(r['may_generate_al'])

    def test_provider_order_dispute_never_clears_risk(self):
        r=self.run_check()
        self.assertEqual(r['status'],'CONNECTOR_ORDER_DISPUTE_REVIEW_REQUIRED')
        self.assertFalse(r['process_date_order_matches_requested_sort'])
        self.assertFalse(r['market_event_absence_proven'])
        self.assertFalse(r['may_modify_stop_target'])

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

    def test_connector_pagination_token_blocks_processing(self):
        p=fixture();p['next_page_token']='more-results'
        with self.assertRaisesRegex(SampleRejected,'PAGINATION_INCOMPLETE'):
            self.run_check(p)

    def test_broken_pagination_token_rejected(self):
        p=fixture();p['next_page_token']=42
        with self.assertRaisesRegex(SampleRejected,'PAGINATION_TOKEN_INVALID'):
            self.run_check(p)

    def test_missing_pagination_metadata_never_proves_complete(self):
        r=self.run_check()
        self.assertFalse(r['connector_exposed_next_page_token'])
        self.assertFalse(r['pagination_complete_proven'])
        self.assertFalse(r['all_early_provider_events_proven'])
        self.assertTrue(r['default_complete_can_exclude_early_incomplete_events'])

    def test_data_quality_unknown_refused(self):
        p=fixture();p['request']['data_quality']='premium_magic'
        with self.assertRaisesRegex(SampleRejected,'DATA_QUALITY_INVALID'):
            self.run_check(p)

    def test_sort_not_by_process_date_never_claims_order(self):
        r=self.run_check()
        self.assertFalse(r['process_date_order_matches_requested_sort'])
        self.assertFalse(r['process_date_order_semantics_verified'])
        self.assertFalse(r['may_generate_al'])

    def test_explicit_null_token_does_not_prove_full_vendor_coverage(self):
        p=fixture();p['next_page_token']=None
        r=self.run_check(p)
        self.assertTrue(r['connector_exposed_next_page_token'])
        self.assertFalse(r['pagination_complete_proven'])

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
