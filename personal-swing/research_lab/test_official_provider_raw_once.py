"""No-network adversarial contract tests for protected manual SEC/Alpaca REST audit."""
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import official_provider_raw_once as m

START, END = '2026-10-01', '2026-10-31'
ID1 = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
ID2 = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'

class Response:
    def __init__(self, data, *, code=200, url=None, mime='application/json',
                 extra_headers=None):
        self.raw = io.BytesIO(data if isinstance(data,bytes) else
                              json.dumps(data).encode('utf-8'))
        self.code = code
        self.url = url
        self.headers = {'Content-Type': mime, **(extra_headers or {})}
    def __enter__(self):
        return self
    def __exit__(self,*args):
        self.raw.close()
    def getcode(self):
        return self.code
    def geturl(self):
        return self.url
    def read(self, n):
        return self.raw.read(n)

class Opener:
    def __init__(self, *pages):
        self.pages=list(pages)
        self.requests=[]
    def open(self, req, timeout):
        self.requests.append(req)
        if not self.pages:
            raise RuntimeError('Unexpected extra request')
        page=self.pages.pop(0)
        if isinstance(page, Exception):
            raise page
        page.url = page.url or req.full_url
        return page

def item(uid=ID1, day='2026-10-15'):
    return {'id':uid,'process_date':day,'symbol':'GILD'}

def pages(*data):
    # Adapt legacy synthetic row fixtures to the provider's documented RAW
    # corporate_actions envelope, not the connected-app flattened output.
    result = []
    for d in data:
        if 'corporate_actions' in d:
            envelope = d
        else:
            envelope = {'corporate_actions': {
                k: v for k, v in d.items() if k != 'next_page_token'}}
            if 'next_page_token' in d:
                envelope['next_page_token'] = d['next_page_token']
        result.append(Response(envelope))
    return Opener(*result)

def audit(op, *, max_pages=8, limit=100):
    return m.alpaca_raw_audit(key='synthetic-id',secret='synthetic-secret',
                              start=START,end=END,opener=op,
                              max_pages=max_pages,limit=limit)

def sec_fixture():
    return {'cik':'0001718227','tickers':['ROAD'],
            'filings':{'recent':{
                'accessionNumber':['0001718227-26-000001'],
                'form':['8-K'], 'filingDate':['2026-10-30'],
                'acceptanceDateTime':['2026-10-30T20:00:00Z']}}}

class ManualRawProviderTests(unittest.TestCase):
    def test_flat_connected_app_response_is_rejected_as_nonraw(self):
        op=Opener(Response({
            'cash_dividends':[item()], 'next_page_token':None}))
        with self.assertRaisesRegex(m.Refused,
                                    'ALPACA_NESTED_GROUPS_MISSING'):
            audit(op)

    def test_real_nested_envelope_is_read(self):
        op=Opener(Response({
            'corporate_actions':{'cash_dividends':[item()]},
            'next_page_token':None}))
        result=audit(op)
        self.assertEqual(result['pages'],1)
        self.assertEqual(result['event_ids_observed'],1)
        self.assertFalse(result['may_clear_risk'])

    def test_raw_unexpected_root_metadata_refused(self):
        op=Opener(Response({
            'corporate_actions':{},'next_page_token':None,'success':True}))
        with self.assertRaisesRegex(m.Refused,'ALPACA_ROOT_SCHEMA_DRIFT'):
            audit(op)

    def test_raw_null_nested_groups_refused(self):
        op=Opener(Response({
            'corporate_actions':None,'next_page_token':None}))
        with self.assertRaisesRegex(m.Refused,
                                    'ALPACA_GROUP_CONTAINER_INVALID'):
            audit(op)

    def test_alpaca_one_page_complete_transport_only(self):
        op=pages({'cash_dividends':[item()], 'next_page_token':None})
        outcome=audit(op)
        self.assertEqual(outcome['pages'],1)
        self.assertEqual(outcome['event_ids_observed'],1)
        self.assertTrue(outcome['page_chain_exhausted'])
        self.assertFalse(outcome['all_corporate_events_proven'])
        self.assertFalse(outcome['may_modify_al'])
        self.assertEqual(len(op.requests),1)
        query=parse_qs(urlsplit(op.requests[0].full_url).query)
        self.assertEqual(query['data_quality'],['all'])
        self.assertEqual(query['region'],['us'])
        self.assertEqual(query['sort'],['asc'])

    def test_alpaca_real_pagination_token_exhausted(self):
        op=pages({'cash_dividends':[item()], 'next_page_token':'opaque-next'},
                 {'stock_dividends':[item(ID2)],'next_page_token':None})
        outcome=audit(op)
        self.assertEqual(outcome['pages'],2)
        self.assertEqual(outcome['event_ids_observed'],2)
        params=parse_qs(urlsplit(op.requests[1].full_url).query)
        self.assertEqual(params['page_token'],['opaque-next'])

    def test_alpaca_duplicate_event_across_pages_fails(self):
        op=pages({'cash_dividends':[item()], 'next_page_token':'opaque-next'},
                 {'cash_dividends':[item()], 'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'ALPACA_DUPLICATE_EVENT_ACROSS_PAGES'):
            audit(op)

    def test_alpaca_pagination_cycle_fails(self):
        op=pages({'cash_dividends':[], 'next_page_token':'cycle'},
                 {'cash_dividends':[], 'next_page_token':'cycle'})
        with self.assertRaisesRegex(m.Refused,'ALPACA_PAGE_TOKEN_CYCLE'):
            audit(op)

    def test_alpaca_page_budget_blocks_truncation(self):
        op=pages({'cash_dividends':[], 'next_page_token':'next'})
        with self.assertRaisesRegex(m.Refused,'ALPACA_PAGE_BUDGET_EXCEEDED'):
            audit(op,max_pages=1)

    def test_alpaca_new_group_never_silently_ignored(self):
        op=pages({'unknown_mergers':[item()], 'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'ALPACA_NEW_SCHEMA_REVIEW_REQUIRED'):
            audit(op)

    def test_missing_page_metadata_must_not_claim_exhaustive(self):
        op=pages({'cash_dividends':[item()]})
        with self.assertRaisesRegex(m.Refused,'ALPACA_PAGE_METADATA_MISSING'):
            audit(op)

    def test_exact_per_page_count_must_not_exceed_limit(self):
        op=pages({'cash_dividends':[item(), item(ID2)],
                  'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'ALPACA_PAGE_EXCEEDS_LIMIT'):
            audit(op,limit=1)

    def test_malformed_uuid_refused(self):
        op=pages({'cash_dividends':[item(uid='-'*36)],
                  'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'ALPACA_EVENT_ID_INVALID'):
            audit(op)

    def test_invalid_calendar_day_refused(self):
        op=pages({'cash_dividends':[item(day='2026-10-32')],
                  'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'ALPACA_PROCESS_DATE_INVALID'):
            audit(op)

    def test_realistic_merger_acquirer_in_scope_accepted(self):
        op=pages({'stock_and_cash_mergers':[{
            'id':ID1, 'process_date':'2026-10-07',
            'acquirer_symbol':'RGEN', 'acquiree_symbol':'BLFS'
        }], 'next_page_token':None})
        result=m.alpaca_raw_audit(key='synthetic',secret='synthetic',
            start=START,end=END,symbols=('RGEN',),
            opener=op)
        self.assertEqual(result['event_ids_observed'],1)
        self.assertFalse(result['may_clear_risk'])

    def test_merger_both_issuers_outside_scope_rejected(self):
        op=pages({'stock_and_cash_mergers':[{
            'id':ID1, 'process_date':'2026-10-07',
            'acquirer_symbol':'RGEN','acquiree_symbol':'BLFS'
        }], 'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,
                                    'ALPACA_EVENT_OUTSIDE_REQUEST_SCOPE'):
            m.alpaca_raw_audit(key='synthetic',secret='synthetic',
                start=START,end=END,symbols=('SWKS',),opener=op)

    def test_missing_merger_counterparty_fails(self):
        op=pages({'stock_and_cash_mergers':[{
            'id':ID1, 'process_date':'2026-10-07',
            'acquirer_symbol':'RGEN'
        }], 'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,
                                    'ALPACA_MERGER_IDENTITY_MISSING'):
            m.alpaca_raw_audit(key='synthetic',secret='synthetic',
                start=START,end=END,symbols=('RGEN',),opener=op)

    def test_cash_dividend_requires_its_own_in_scope_symbol(self):
        op=pages({'cash_dividends':[{
            'id':ID1,'process_date':'2026-10-15',
            'acquirer_symbol':'GILD','symbol':'OUT'
        }], 'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,
                                    'ALPACA_CASH_DIVIDEND_SYMBOL_REQUIRED'):
            audit(op)

    def test_event_without_any_supported_symbol_is_refused(self):
        op=pages({'cash_dividends':[{
            'id':ID1,'process_date':'2026-10-15'
        }], 'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'ALPACA_EVENT_SYMBOL_INVALID'):
            audit(op)

    def test_alpaca_noncanonical_event_date_rejected(self):
        op=pages({'cash_dividends':[item(day='2026-11-01')], 'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'ALPACA_PROCESS_DATE_INVALID'):
            audit(op)

    def test_alpaca_no_credentials_no_request(self):
        op=pages({'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'ALPACA_KEYS_MISSING'):
            m.alpaca_raw_audit(key='',secret='x',start=START,end=END,opener=op)
        self.assertEqual(len(op.requests),0)

    def test_invalid_input_calendar_date_refused_before_http(self):
        op=pages({'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'DATE_INVALID'):
            m.alpaca_raw_audit(key='synthetic-key',secret='synthetic-secret',
                start='2026-02-30',end='2026-10-31',opener=op)
        self.assertEqual(len(op.requests),0)

    def test_alpaca_invalid_date_refused_before_request(self):
        op=pages({'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'DATE_INVALID'):
            m.alpaca_raw_audit(key='key',secret='secret',
                start='2026-11-01',end='2026-10-01',opener=op)
        self.assertEqual(len(op.requests),0)

    def test_http_429_fail_closed(self):
        error=HTTPError(m.ALPACA_URL,429,'rate limited',{},None)
        op=Opener(error)
        with self.assertRaisesRegex(m.Refused,'HTTP_429'):
            audit(op)

    def test_redirect_refused(self):
        op=Opener(Response({'next_page_token':None},
                            url='https://other.invalid/api'))
        with self.assertRaisesRegex(m.Refused,'REDIRECT_REFUSED'):
            audit(op)

    def test_mime_not_json_refused(self):
        op=Opener(Response('<html>oops</html>',mime='text/html'))
        with self.assertRaisesRegex(m.Refused,'JSON_MIME_INVALID'):
            audit(op)

    def test_unknown_encoding_refused(self):
        op=Opener(Response('{"next_page_token":null}',
                            extra_headers={'Content-Encoding':'gzip'}))
        with self.assertRaisesRegex(m.Refused,'ENCODING_UNVERIFIED'):
            audit(op)

    def test_json_duplicate_key_refused(self):
        op=Opener(Response(b'{"next_page_token":null,"next_page_token":null}'))
        with self.assertRaisesRegex(m.Refused,'JSON_DUPLICATE_KEY'):
            audit(op)

    def test_json_nonfinite_refused(self):
        op=Opener(Response(b'{"next_page_token":NaN}'))
        with self.assertRaisesRegex(m.Refused,'JSON_NONFINITE'):
            audit(op)

    def test_json_bom_refused(self):
        op=Opener(Response(b'\xef\xbb\xbf{"next_page_token":null}'))
        with self.assertRaisesRegex(m.Refused,'JSON_BOM_REFUSED'):
            audit(op)

    def test_477_scoped_exact_20_batches_without_market_clearance(self):
        scope=tuple(f'T{i:04d}' for i in range(477))
        op=pages(*({'next_page_token':None} for _ in range(20)))
        paced=[]
        result=m.audit_all_477(key='synthetic-key',secret='synthetic-secret',
            start=START,end=END,scope=scope,opener=op,
            before_request=lambda: paced.append(1))
        self.assertEqual(result['requested_symbols'],477)
        self.assertEqual(result['batches'],20)
        self.assertEqual(result['http_pages'],20)
        self.assertEqual(len(op.requests),20)
        self.assertEqual(len(paced),20)
        self.assertEqual(len(parse_qs(urlsplit(op.requests[0].full_url).query)['symbols'][0].split(',')),25)
        self.assertEqual(len(parse_qs(urlsplit(op.requests[-1].full_url).query)['symbols'][0].split(',')),2)
        self.assertTrue(result['cross_batch_unique_events_proven'])
        self.assertEqual(result['unique_event_ids_observed'],0)
        self.assertEqual(result['cross_batch_duplicate_occurrences'],0)
        self.assertFalse(result['market_event_absence_proven'])
        self.assertFalse(result['historical_pit_proven'])
        self.assertFalse(result['may_modify_al'])
        self.assertFalse(result['may_place_order'])

    def test_wrong_477_scope_rejected_without_http(self):
        op=pages(*({'next_page_token':None} for _ in range(20)))
        with self.assertRaisesRegex(m.Refused,'WATCHLIST_NOT_477_UNIQUE'):
            m.audit_all_477(key='synthetic-key',secret='synthetic-secret',
                start=START,end=END,scope=['GILD']*477,opener=op,
                before_request=lambda:None)
        self.assertEqual(len(op.requests),0)

    def test_477_batch_failure_stops_all_remaining_requests(self):
        scope=tuple(f'T{i:04d}' for i in range(477))
        op=pages({'next_page_token':None}, {'cash_dividends':[dict(item(uid='bad'),symbol='T0025')],
                        'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'ALPACA_EVENT_ID_INVALID'):
            m.audit_all_477(key='synthetic-key',secret='synthetic-secret',
                start=START,end=END,scope=scope,opener=op,
                before_request=lambda:None)
        self.assertEqual(len(op.requests),2)

    def test_477_real_watchlist_shape_is_unchanged(self):
        scope=m.read_immutable_477_scope()
        self.assertEqual(len(scope),477)
        self.assertEqual(len(set(scope)),477)

    def test_all477_cross_batch_duplicate_is_one_unique_event(self):
        scope=tuple(f'T{i:04d}' for i in range(477))
        merger={'id':ID1,'process_date':'2026-10-07',
                'acquirer_symbol':scope[0],'acquiree_symbol':scope[25]}
        fixtures=[{'next_page_token':None} for _ in range(20)]
        for index in (0,1):
            fixtures[index]['stock_and_cash_mergers']=[dict(merger)]
        result=m.audit_all_477(key='synthetic-key',secret='synthetic-secret',
            start=START,end=END,scope=scope,opener=pages(*fixtures),
            before_request=lambda:None)
        self.assertEqual(result['observed_query_event_occurrences'],2)
        self.assertEqual(result['unique_event_ids_observed'],1)
        self.assertEqual(result['cross_batch_duplicate_occurrences'],1)
        self.assertTrue(result['cross_batch_unique_events_proven'])
        self.assertNotIn(ID1,json.dumps(result))
        self.assertFalse(result['may_clear_risk'])

    def test_cross_batch_same_id_different_record_is_refused(self):
        scope=tuple(f'T{i:04d}' for i in range(477))
        original={'id':ID1,'process_date':'2026-10-07',
                  'acquirer_symbol':scope[0],'acquiree_symbol':scope[25]}
        changed=dict(original,cash_rate=42.0)
        fixtures=[{'next_page_token':None} for _ in range(20)]
        fixtures[0]['stock_and_cash_mergers']=[original]
        fixtures[1]['stock_and_cash_mergers']=[changed]
        with self.assertRaisesRegex(m.Refused,
                                    'ALPACA_EVENT_CONFLICT_ACROSS_BATCHES'):
            m.audit_all_477(key='synthetic-key',secret='synthetic-secret',
                start=START,end=END,scope=scope,opener=pages(*fixtures),
                before_request=lambda:None)

    def test_raw_quality_requires_documented_enum_no_http(self):
        op=pages({'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'DATA_QUALITY_INVALID'):
            m.alpaca_raw_audit(key='synthetic-key',secret='synthetic-secret',
                start=START,end=END,opener=op,data_quality='initial')
        self.assertEqual(len(op.requests),0)

    def test_quality_all_only_one_event_proves_filter_delta_not_pit(self):
        scope=tuple(f'T{i:04d}' for i in range(477))
        first=[{'next_page_token':None} for _ in range(20)]
        first[0]['cash_dividends']=[dict(item(),symbol=scope[0])]
        second=[{'next_page_token':None} for _ in range(20)]
        op=pages(*(first+second))
        r=m.reconcile_all477_quality(key='synthetic-key',
            secret='synthetic-secret',start=START,end=END,scope=scope,
            opener=op,before_request=lambda:None)
        self.assertEqual(r['all_observed_unique_events'],1)
        self.assertEqual(r['complete_observed_unique_events'],0)
        self.assertEqual(r['all_only_event_ids_count'],1)
        self.assertEqual(r['all_only_event_group_counts'],{'cash_dividends':1})
        self.assertEqual(r['total_http_pages'],40)
        self.assertEqual(len(op.requests),40)
        query1=parse_qs(urlsplit(op.requests[0].full_url).query)
        query2=parse_qs(urlsplit(op.requests[20].full_url).query)
        self.assertEqual(query1['data_quality'],['all'])
        self.assertEqual(query2['data_quality'],['complete'])
        self.assertNotIn(ID1,json.dumps(r))
        self.assertFalse(r['connector_event_id_reconciled'])
        self.assertFalse(r['provider_snapshot_atomic'])
        self.assertFalse(r['may_clear_risk'])

    def test_quality_complete_not_subset_of_all_is_refused(self):
        scope=tuple(f'T{i:04d}' for i in range(477))
        first=[{'next_page_token':None} for _ in range(20)]
        second=[{'next_page_token':None} for _ in range(20)]
        second[0]['cash_dividends']=[dict(item(),symbol=scope[0])]
        with self.assertRaisesRegex(m.Refused,'QUALITY_COMPLETE_NOT_SUBSET_OF_ALL'):
            m.reconcile_all477_quality(key='synthetic-key',
                secret='synthetic-secret',start=START,end=END,scope=scope,
                opener=pages(*(first+second)),before_request=lambda:None)

    def test_quality_id_field_change_refused_not_false_match(self):
        scope=tuple(f'T{i:04d}' for i in range(477))
        first=[{'next_page_token':None} for _ in range(20)]
        second=[{'next_page_token':None} for _ in range(20)]
        first[0]['cash_dividends']=[dict(item(),symbol=scope[0])]
        second[0]['cash_dividends']=[dict(item(),symbol=scope[0],rate=0.9)]
        with self.assertRaisesRegex(m.Refused,'QUALITY_SAME_ID_ROW_DISAGREEMENT'):
            m.reconcile_all477_quality(key='synthetic-key',
                secret='synthetic-secret',start=START,end=END,scope=scope,
                opener=pages(*(first+second)),before_request=lambda:None)

    def test_quality_identical_batches_no_fake_extra_event(self):
        scope=tuple(f'T{i:04d}' for i in range(477))
        first=[{'next_page_token':None} for _ in range(20)]
        first[0]['cash_dividends']=[dict(item(),symbol=scope[0])]
        second=[dict(x) for x in first]
        r=m.reconcile_all477_quality(key='synthetic-key',
            secret='synthetic-secret',start=START,end=END,scope=scope,
            opener=pages(*(first+second)),before_request=lambda:None)
        self.assertEqual(r['all_only_event_ids_count'],0)
        self.assertEqual(r['all_observed_unique_events'],1)
        self.assertEqual(r['complete_observed_unique_events'],1)
        self.assertEqual(r['all_id_set_sha256'],r['complete_id_set_sha256'])

    def test_cli_reconcile_mode_status_excludes_event_ids(self):
        from contextlib import redirect_stdout
        result={'status':'OBSERVED_PROVIDER_QUALITY_DELTA_NOT_PIT_CLEARANCE',
                'all_only_event_ids_count':1,'may_clear_risk':False}
        out=io.StringIO()
        with patch.dict(os.environ,{
            'XRAY_SEC_DECLARED_USER_AGENT':'',
            'XRAY_ALPACA_DATA_KEY_ID':'synthetic-key',
            'XRAY_ALPACA_DATA_SECRET_KEY':'synthetic-secret',
            'XRAY_SOURCE_SCOPE':'reconcile477',
            'XRAY_RECONCILE_START':START,
            'XRAY_RECONCILE_END':END},clear=True):
            with patch.object(m,'reconcile_all477_quality',return_value=result) as spy:
                with redirect_stdout(out):
                    rc=m.main()
        self.assertEqual(rc,0)
        self.assertEqual(spy.call_args.kwargs['start'],START)
        self.assertEqual(spy.call_args.kwargs['end'],END)
        self.assertIn('OBSERVED_PROVIDER_QUALITY_DELTA_NOT_PIT_CLEARANCE',out.getvalue())
        self.assertNotIn(ID1,out.getvalue())

    def test_reconcile477_no_dates_refused_before_any_provider_call(self):
        with patch.dict(os.environ,{
            'XRAY_SOURCE_SCOPE':'reconcile477',
            'XRAY_RECONCILE_START':'',
            'XRAY_RECONCILE_END':'',
            'XRAY_ALPACA_DATA_KEY_ID':'synthetic',
            'XRAY_ALPACA_DATA_SECRET_KEY':'synthetic',
            'XRAY_SEC_DECLARED_USER_AGENT':''},clear=True):
            with patch.object(m,'reconcile_all477_quality',
                              side_effect=AssertionError('MUST_NOT_CALL')):
                with self.assertRaisesRegex(m.Refused,
                        'RECONCILIATION_DATES_REQUIRED'):
                    m.main()

    def test_reconcile477_invalid_calendar_dates_refused(self):
        for start,end in (('2026-02-30','2026-10-31'),
                          ('2026-11-01','2026-10-31'),
                          ('2026-10-01','2099-10-31')):
            with patch.dict(os.environ,{
                'XRAY_SOURCE_SCOPE':'reconcile477',
                'XRAY_RECONCILE_START':start,
                'XRAY_RECONCILE_END':end,
                'XRAY_ALPACA_DATA_KEY_ID':'synthetic',
                'XRAY_ALPACA_DATA_SECRET_KEY':'synthetic',
                'XRAY_SEC_DECLARED_USER_AGENT':''},clear=True):
                with patch.object(m,'reconcile_all477_quality',
                                  side_effect=AssertionError('MUST_NOT_CALL')):
                    with self.assertRaisesRegex(m.Refused,
                            'RECONCILIATION_DATES_INVALID'):
                        m.main()

    def test_sec_no_genuine_contact_refused_without_http(self):
        op=Opener(Response(sec_fixture()))
        with self.assertRaisesRegex(m.Refused,
              'SEC_DECLARED_CONTACT_MISSING_OR_INVALID'):
            m.sec_raw_audit(declared_agent='',opener=op)
        self.assertEqual(len(op.requests),0)

    def test_sec_user_agent_no_header_in_response(self):
        declared='Synthetic Research synthetic-contact@audit.invalid'
        op=Opener(Response(sec_fixture()))
        outcome=m.sec_raw_audit(declared_agent=declared,opener=op)
        self.assertEqual(outcome['status'],'SEC_RAW_FORMAT_OBSERVED_NOT_PIT_CLEARANCE')
        self.assertFalse(outcome['first_public_availability_proven'])
        self.assertFalse(outcome['may_write_sheet'])
        self.assertEqual(op.requests[0].headers['User-agent'],declared)
        self.assertNotIn(declared,json.dumps(outcome))
        self.assertEqual(len(op.requests),1)

    def test_sec_real_submissions_cik_string_passes_full_raw_gate(self):
        op=Opener(Response(sec_fixture()))
        result=m.sec_raw_audit(
            declared_agent='Synthetic Research synthetic-contact@audit.invalid',
            opener=op)
        self.assertEqual(result['status'],'SEC_RAW_FORMAT_OBSERVED_NOT_PIT_CLEARANCE')
        self.assertTrue(result['declared_contact_present'])
        self.assertFalse(result['first_public_availability_proven'])
        self.assertFalse(result['may_modify_al'])
        self.assertEqual(len(op.requests),1)

    def test_sec_mismatched_text_cik_fails_full_raw_gate(self):
        f=sec_fixture();f['cik']='0001718228'
        op=Opener(Response(f))
        with self.assertRaisesRegex(m.Refused,'SEC_FORMAT_REQUIRES_REVIEW'):
            m.sec_raw_audit(
                declared_agent='Synthetic Research synthetic-contact@audit.invalid',
                opener=op)

    def test_sec_wrong_cik_rejected(self):
        f=sec_fixture()
        f['cik']=123
        op=Opener(Response(f))
        with self.assertRaisesRegex(m.Refused,'SEC_FORMAT_REQUIRES_REVIEW'):
            m.sec_raw_audit(declared_agent=
                'Synthetic Research synthetic-contact@audit.invalid',
                            opener=op)

    def test_sec_redirect_refused(self):
        op=Opener(Response(sec_fixture(),url='https://not-sec.invalid/'))
        with self.assertRaisesRegex(m.Refused,'REDIRECT_REFUSED'):
            m.sec_raw_audit(declared_agent=
                'Synthetic Research synthetic-contact@audit.invalid',
                            opener=op)

    def test_cli_missing_alpaca_keys_is_red_not_false_green(self):
        from contextlib import redirect_stdout
        out=io.StringIO()
        with patch.dict(os.environ, {
            'XRAY_SEC_DECLARED_USER_AGENT':'',
            'XRAY_ALPACA_DATA_KEY_ID':'',
            'XRAY_ALPACA_DATA_SECRET_KEY':'',
            'XRAY_SOURCE_SCOPE':'pilot3'}, clear=True):
            with patch.object(m,'default_opener',
                              side_effect=AssertionError('UNAUTHORIZED_HTTP')):
                with redirect_stdout(out):
                    code=m.main()
        self.assertEqual(code,3)
        self.assertEqual(out.getvalue().count('SKIPPED_NO_AUTHORIZED_INPUT'),2)

    def test_cli_alpaca_refusal_is_red_without_secret_leak(self):
        from contextlib import redirect_stdout
        out=io.StringIO()
        with patch.dict(os.environ,{
            'XRAY_SEC_DECLARED_USER_AGENT':'',
            'XRAY_ALPACA_DATA_KEY_ID':'key-private-synthetic',
            'XRAY_ALPACA_DATA_SECRET_KEY':'secret-private-synthetic',
            'XRAY_SOURCE_SCOPE':'pilot3'},clear=True):
            with patch.object(m,'alpaca_raw_audit',
                              side_effect=m.Refused('HTTP_429')):
                with redirect_stdout(out):
                    code=m.main()
        self.assertEqual(code,4)
        self.assertIn('SOURCE_REFUSED',out.getvalue())
        self.assertIn('HTTP_429',out.getvalue())
        self.assertNotIn('private-synthetic',out.getvalue())

    def test_cli_valid_alpaca_and_unconfigured_sec_is_only_alpaca_pass(self):
        from contextlib import redirect_stdout
        out=io.StringIO()
        accepted={'status':'RAW_PAGE_CHAIN_EXHAUSTED_NOT_MARKET_CLEARANCE',
                  'may_clear_risk':False,'pages':1,'event_ids_observed':1}
        with patch.dict(os.environ,{
            'XRAY_SEC_DECLARED_USER_AGENT':'',
            'XRAY_ALPACA_DATA_KEY_ID':'synthetic-key',
            'XRAY_ALPACA_DATA_SECRET_KEY':'synthetic-secret',
            'XRAY_SOURCE_SCOPE':'pilot3'},clear=True):
            with patch.object(m,'alpaca_raw_audit',return_value=accepted):
                with redirect_stdout(out):
                    code=m.main()
        self.assertEqual(code,0)
        rows=[json.loads(x) for x in out.getvalue().splitlines()]
        self.assertEqual(rows[0]['status'],'SKIPPED_NO_AUTHORIZED_INPUT')
        self.assertEqual(rows[1]['status'],'RAW_PAGE_CHAIN_EXHAUSTED_NOT_MARKET_CLEARANCE')
        self.assertFalse(rows[1]['may_clear_risk'])

    def test_cli_configured_sec_refused_red_even_if_alpaca_passes(self):
        from contextlib import redirect_stdout
        out=io.StringIO()
        accepted={'status':'RAW_PAGE_CHAIN_EXHAUSTED_NOT_MARKET_CLEARANCE',
                  'may_clear_risk':False,'pages':1}
        with patch.dict(os.environ,{
            'XRAY_SEC_DECLARED_USER_AGENT':
                'Synthetic Research synthetic-contact@audit.invalid',
            'XRAY_ALPACA_DATA_KEY_ID':'synthetic-key',
            'XRAY_ALPACA_DATA_SECRET_KEY':'synthetic-secret',
            'XRAY_SOURCE_SCOPE':'pilot3'},clear=True):
            with patch.object(m,'sec_raw_audit',
                              side_effect=m.Refused('SEC_FORMAT_REQUIRES_REVIEW')):
                with patch.object(m,'alpaca_raw_audit',return_value=accepted):
                    with redirect_stdout(out):
                        code=m.main()
        self.assertEqual(code,4)
        self.assertIn('SEC_FORMAT_REQUIRES_REVIEW',out.getvalue())
        self.assertNotIn('synthetic-contact@audit.invalid',out.getvalue())

    def test_cli_incorrect_alpaca_status_never_success(self):
        from contextlib import redirect_stdout
        out=io.StringIO()
        with patch.dict(os.environ,{
            'XRAY_SEC_DECLARED_USER_AGENT':'',
            'XRAY_ALPACA_DATA_KEY_ID':'synthetic-key',
            'XRAY_ALPACA_DATA_SECRET_KEY':'synthetic-secret',
            'XRAY_SOURCE_SCOPE':'pilot3'},clear=True):
            with patch.object(m,'alpaca_raw_audit',
                              return_value={'status':'SAMPLE_FOR_REVIEW',
                                            'may_clear_risk':False}):
                with redirect_stdout(out):
                    code=m.main()
        self.assertEqual(code,4)
        self.assertIn('ALPACA_ACCEPTANCE_STATUS_INVALID',out.getvalue())

    def test_no_env_never_touches_network_or_secrets(self):
        with patch.dict(os.environ,{'XRAY_SEC_DECLARED_USER_AGENT':'',
            'XRAY_ALPACA_DATA_KEY_ID':'','XRAY_ALPACA_DATA_SECRET_KEY':''}):
            with patch.object(m,'default_opener',side_effect=AssertionError('HTTP')):
                from contextlib import redirect_stdout
                out=io.StringIO()
                with redirect_stdout(out):
                    m.main()
        self.assertEqual(out.getvalue().count('SKIPPED_NO_AUTHORIZED_INPUT'),2)
        self.assertNotIn('synthetic-secret',out.getvalue())

class InternalRoleEvidenceTests(unittest.TestCase):
    def test_default_audit_never_exposes_private_symbol_roles(self):
        out = m.alpaca_raw_audit(key='synthetic',secret='synthetic',
            start=START,end=END,symbols=('GILD',),
            opener=pages({'cash_dividends':[item()], 'next_page_token':None}))
        self.assertNotIn('_internal_symbol_roles',out)
        self.assertNotIn('_internal_id_index',out)

    def test_protected_internal_role_index_follows_uuid(self):
        out = m.alpaca_raw_audit(key='synthetic',secret='synthetic',
            start=START,end=END,symbols=('RGEN',),
            include_internal_ids=True,include_internal_roles=True,
            opener=pages({'stock_and_cash_mergers':[{
                'id':ID1,'process_date':'2026-10-07',
                'acquirer_symbol':'RGEN','acquiree_symbol':'BLFS'
            }], 'next_page_token':None}))
        self.assertEqual(out['_internal_symbol_roles'][ID1],('BLFS','RGEN'))
        self.assertEqual(out['_internal_id_index'][ID1][0],
                         'stock_and_cash_mergers')

    def test_role_request_requires_private_id_capture(self):
        with self.assertRaisesRegex(m.Refused,'INTERNAL_CAPTURE_FLAG_INVALID'):
            m.alpaca_raw_audit(key='synthetic',secret='synthetic',
                start=START,end=END,symbols=('GILD',),
                include_internal_roles=True,
                opener=pages({'cash_dividends':[],'next_page_token':None}))

    def test_all477_empty_batches_have_role_index_and_no_leak(self):
        symbols = m.read_immutable_477_scope()
        x = m.audit_all_477(
            key='synthetic',secret='synthetic',start=START,end=END,
            scope=symbols,
            include_internal_ids=True,include_internal_roles=True,
            before_request=lambda:None,
            opener=pages(*([
                {'cash_dividends':[],'next_page_token':None}
                for _ in range(20)])))
        self.assertEqual(x['batches'],20)
        self.assertEqual(x['_internal_symbol_roles'],{})
        self.assertEqual(x['_internal_id_index'],{})
        self.assertFalse(x['historical_pit_proven'])

    def test_public_all477_output_never_exposes_roles(self):
        symbols=m.read_immutable_477_scope()
        out=m.audit_all_477(key='synthetic',secret='synthetic',
            start=START,end=END,scope=symbols,
            before_request=lambda:None,
            opener=pages(*([{'cash_dividends':[],'next_page_token':None}
                            for _ in range(20)])))
        self.assertNotIn('_internal_symbol_roles',out)
        self.assertNotIn('_internal_id_index',out)

if __name__=='__main__':
    unittest.main()
