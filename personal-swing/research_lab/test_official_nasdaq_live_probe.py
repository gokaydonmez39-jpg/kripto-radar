"""Tests for read-only one-shot source probe. No external calls."""
import io
import json
import unittest
from unittest.mock import patch

import official_nasdaq_live_probe as p

NOW = '2026-10-31T12:00:00+00:00'

class FakeResponse:
    def __init__(self, raw, mime, url, status=200):
        self.raw = io.BytesIO(raw)
        self.headers = {'Content-Type': mime}
        self.url = url
        self.status = status
        self.read_calls = 0
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        self.raw.close()
    def read(self, n):
        self.read_calls += 1
        return self.raw.read(n)
    def geturl(self):
        return self.url
    def getcode(self):
        return self.status

class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.calls = 0
        self.last_request = None
    def open(self, req, timeout):
        self.calls += 1
        self.last_request = req
        return self.response

def rss():
    return (b'<rss><channel><item><Symbol>AAPL</Symbol>'
        b'<HaltDate>10/30/2026</HaltDate><HaltTime>12:00:00</HaltTime>'
        b'<ReasonCode>T1</ReasonCode></item></channel></rss>')

def directory():
    return (b'Symbol|Security Name|Market Category|Test Issue|Financial Status|'
        b'Round Lot Size|ETF|NextShares\n'
        b'AAPL|Apple|Q|N|N|100|N|N\n'
        b'File Creation Time: 103020261200|||||||\n')

class ProbeTests(unittest.TestCase):
    def test_rss_one_request_is_review_only(self):
        url=p.expected_url('NASDAQ_HALTS',None)
        fake=FakeOpener(FakeResponse(rss(),'text/xml',url))
        result=p.probe_once('NASDAQ_HALTS',fake)
        self.assertEqual(fake.calls,1)
        self.assertEqual(fake.response.read_calls,1)
        self.assertEqual(fake.last_request.get_method(),'GET')
        self.assertEqual(result['state'],'HTTP_AND_FORMAT_OBSERVED_NOT_LIVE_ACCEPTANCE')
        self.assertFalse(result['may_send_alert'])
        self.assertNotIn('AAPL',json.dumps(result))
        self.assertNotIn('reason_code',json.dumps(result))
        self.assertNotIn('HaltDate',json.dumps(result))

    def test_directory_one_request_is_review_only(self):
        url=p.expected_url('NASDAQ_DIRECTORY',None)
        fake=FakeOpener(FakeResponse(directory(),'text/plain',url))
        result=p.probe_once('NASDAQ_DIRECTORY',fake)
        self.assertEqual(fake.calls,1)
        self.assertFalse(result['may_change_al'] if 'may_change_al' in result else result['may_modify_al'])
        self.assertIn(result['state'],
                      ('HTTP_AND_FORMAT_OBSERVED_NOT_LIVE_ACCEPTANCE','READER_REJECTED'))

    def test_real_xml_bom_accepted_by_live_diagnostic(self):
        raw = b'\xef\xbb\xbf' + rss()
        result = p.evaluate_response(
            'NASDAQ_HALTS', raw=raw, status=200,
            response_url=p.expected_url('NASDAQ_HALTS', None),
            content_type='text/xml', observed_at_utc=NOW)
        self.assertEqual(result['state'],
                         'HTTP_AND_FORMAT_OBSERVED_NOT_LIVE_ACCEPTANCE')
        self.assertEqual(result['body_sha256'],
                         __import__('hashlib').sha256(raw).hexdigest())
        self.assertFalse(result['may_clear_risk'])

    def test_untrusted_redirect_fails(self):
        result=p.evaluate_response(
            'NASDAQ_HALTS', raw=rss(),status=200,
            response_url='https://other.invalid/rss', content_type='text/xml',
            observed_at_utc=NOW)
        self.assertEqual(result['state'],'READER_REJECTED')
        self.assertEqual(result['refusal_code'],'URL_OR_REDIRECT_MISMATCH')

    def test_http_429_fail_closed(self):
        result=p.evaluate_response(
            'NASDAQ_HALTS',raw=rss(),status=429,
            response_url=p.expected_url('NASDAQ_HALTS',None),
            content_type='text/xml',observed_at_utc=NOW)
        self.assertEqual(result['state'],'READER_REJECTED')
        self.assertEqual(result['refusal_code'],'HTTP_NOT_200')

    def test_oversize_never_parsed(self):
        result=p.evaluate_response(
            'NASDAQ_HALTS', raw=b'a'*(p.MAX_BYTES['NASDAQ_HALTS']+1),
            status=200, response_url=p.expected_url('NASDAQ_HALTS',None),
            content_type='text/xml', observed_at_utc=NOW)
        self.assertEqual(result['state'],'BODY_SIZE_REJECTED')

    def test_empty_feed_cannot_clear_risk(self):
        result=p.evaluate_response(
            'NASDAQ_HALTS',raw=b'<rss><channel/></rss>',status=200,
            response_url=p.expected_url('NASDAQ_HALTS',None),
            content_type='text/xml',observed_at_utc=NOW)
        self.assertEqual(result['state'],'HTTP_AND_FORMAT_OBSERVED_NOT_LIVE_ACCEPTANCE')
        self.assertEqual(result['parser_status'],'NASDAQ_NO_ITEM_NOT_CLEAR')
        self.assertFalse(result['may_clear_risk'])

    def test_malformed_xml_rejected(self):
        result=p.evaluate_response(
            'NASDAQ_HALTS', raw=b'<rss>',status=200,
            response_url=p.expected_url('NASDAQ_HALTS',None),
            content_type='text/xml',observed_at_utc=NOW)
        self.assertEqual(result['state'],'READER_REJECTED')
        self.assertEqual(result['refusal_code'],'RSS_READER_REFUSED')

    def test_477_scope_partition_current_only(self):
        symbols = [f'T{i:04d}' for i in range(477)]
        header = 'Symbol|Security Name|Market Category|Test Issue|Financial Status|ETF'
        rows = [f'{s}|Synthetic|Q|N|N|N' for s in symbols[:-2]]
        rows += [f'{symbols[-2]}|Synthetic|Q|N|D|N']
        body = (header + '\n' + '\n'.join(rows) +
                '\nFile Creation Time: 103020261200||||||\n').encode()
        result = p.compare_current_directory_scope(body, {
            'liquidity_watch_symbols': symbols, 'source_count': 477})
        self.assertEqual(result['scope_count'],477)
        self.assertEqual(result['directory_basic_flag_match'],475)
        self.assertEqual(result['directory_flagged'],1)
        self.assertEqual(result['directory_missing'],1)
        self.assertEqual(result['flagged_watchlist_index_zero_based'], 475)
        self.assertEqual(result['flagged_directory_fields'], {'Financial Status': 'D'})
        self.assertFalse(result['historical_membership_proven'])
        self.assertFalse(result['may_clear_risk'])
        self.assertNotIn(symbols[-1],json.dumps(result))

    def test_two_flagged_do_not_disclose_index(self):
        symbols = [f'T{i:04d}' for i in range(477)]
        header = 'Symbol|Security Name|Market Category|Test Issue|Financial Status|ETF'
        rows = [f'{s}|Synthetic|Q|N|N|N' for s in symbols]
        rows[4] = f'{symbols[4]}|Synthetic|Q|Y|N|N'
        rows[7] = f'{symbols[7]}|Synthetic|Q|N|E|N'
        body = (header + '\n' + '\n'.join(rows) +
                '\nFile Creation Time: 103020261200||||||\n').encode()
        result = p.compare_current_directory_scope(body, {
            'liquidity_watch_symbols': symbols, 'source_count': 477})
        self.assertEqual(result['directory_flagged'],2)
        self.assertIsNone(result['flagged_watchlist_index_zero_based'])
        self.assertIsNone(result['flagged_directory_fields'])
        self.assertFalse(result['may_clear_risk'])

    def test_bad_watchlist_size_refused(self):
        with self.assertRaisesRegex(ValueError,'SCOPE_477_COUNT_MISMATCH'):
            p.compare_current_directory_scope(directory(), {
                'liquidity_watch_symbols':['AAPL'],'source_count':477})

    def test_scope_duplicate_refused(self):
        with self.assertRaisesRegex(ValueError,'SCOPE_SYMBOL_INVALID_OR_DUPLICATE'):
            p.compare_current_directory_scope(directory(), {
                'liquidity_watch_symbols':['AAPL']*477,'source_count':477})

    def test_real_477_scope_file_exists_and_is_exact(self):
        data=p.local_watchlist()
        self.assertEqual(len(data['liquidity_watch_symbols']),477)
        self.assertEqual(len(set(data['liquidity_watch_symbols'])),477)
        self.assertEqual(data['source_count'],477)

    def test_outside_allowlist_no_request(self):
        fake=FakeOpener(None)
        with self.assertRaisesRegex(ValueError,'SOURCE_NOT_ALLOWED'):
            p.probe_once('SEC_EDGAR',fake)
        self.assertEqual(fake.calls,0)

    def test_safe_output_has_no_raw_payload(self):
        result=p.evaluate_response(
            'NASDAQ_HALTS', raw=rss(),status=200,
            response_url=p.expected_url('NASDAQ_HALTS',None),
            content_type='text/xml',observed_at_utc=NOW)
        output=json.dumps(result)
        self.assertNotIn('AAPL',output)
        self.assertNotIn('HaltDate',output)
        self.assertFalse(result['first_public_availability_proven'])

    def test_no_redirect_handler(self):
        self.assertIsNone(p.NoRedirect().redirect_request(
            None,None,302,'Found',{},'https://other.invalid/'))

if __name__ == '__main__':
    unittest.main()
