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
    return Opener(*(Response(d) for d in data))

def audit(op, *, max_pages=8, limit=100):
    return m.alpaca_raw_audit(key='synthetic-id',secret='synthetic-secret',
                              start=START,end=END,opener=op,
                              max_pages=max_pages,limit=limit)

def sec_fixture():
    return {'cik':1718227,'tickers':['ROAD'],
            'filings':{'recent':{
                'accessionNumber':['0001718227-26-000001'],
                'form':['8-K'], 'filingDate':['2026-10-30'],
                'acceptanceDateTime':['2026-10-30T20:00:00Z']}}}

class ManualRawProviderTests(unittest.TestCase):
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

    def test_alpaca_noncanonical_event_date_rejected(self):
        op=pages({'cash_dividends':[item(day='2026-11-01')], 'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'ALPACA_PROCESS_DATE_INVALID'):
            audit(op)

    def test_alpaca_no_credentials_no_request(self):
        op=pages({'next_page_token':None})
        with self.assertRaisesRegex(m.Refused,'ALPACA_KEYS_MISSING'):
            m.alpaca_raw_audit(key='',secret='x',start=START,end=END,opener=op)
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

if __name__=='__main__':
    unittest.main()
