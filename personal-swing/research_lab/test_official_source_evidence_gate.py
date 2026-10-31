"""Offline negative tests: evidence gate must never grant live risk clearance."""
import base64
import hashlib
import json
import unittest

import official_source_evidence_gate as g

CUTOFF = '2026-10-31T12:00:00Z'
OBS = '2026-10-31T11:00:00Z'
CIK = '0000320193'

def sec_payload():
    return {'cik':320193,'tickers':['AAPL'],'filings':{'recent':{
        'accessionNumber':['0000320193-26-000001'],'form':['8-K'],
        'filingDate':['2026-10-30'],
        'acceptanceDateTime':['2026-10-30T20:00:00Z']}}}

def envelope(source,payload,observed_at=OBS):
    url=g.expected_url(source,CIK if source=='SEC_EDGAR' else None)
    raw=payload if type(payload) is bytes else payload.encode('utf-8')
    return {'source':source,'method':'GET','request_url':url,'final_url':url,
        'status_code':200,
        'content_type':{'SEC_EDGAR':'application/json',
            'NASDAQ_HALTS':'text/xml','NASDAQ_DIRECTORY':'text/plain'}[source],
        'content_encoding':'identity','body_base64':base64.b64encode(raw).decode('ascii'),
        'body_bytes':len(raw),'body_sha256':hashlib.sha256(raw).hexdigest(),
        'observed_at_utc':observed_at}

def sec_capture():
    return envelope('SEC_EDGAR',json.dumps(sec_payload()))

def rss_capture():
    return envelope('NASDAQ_HALTS',
        '<rss><channel><item><Symbol>AAPL</Symbol><HaltDate>10/30/2026</HaltDate>'
        '<HaltTime>14:30:00</HaltTime><ReasonCode>T1</ReasonCode></item></channel></rss>')

def directory_capture(token='103020261200'):
    return envelope('NASDAQ_DIRECTORY',
        'Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n'
        'AAPL|Apple|Q|N|N|100|N|N\n'
        f'File Creation Time: {token}|||||||\n')

class EvidenceGateTests(unittest.TestCase):
    def audit(self,capture,source='SEC_EDGAR'):
        return g.audit_capture(capture,source=source,ticker='AAPL',
            asof_utc=CUTOFF,cik=CIK if source=='SEC_EDGAR' else None)

    def reject(self,capture,reason,source='SEC_EDGAR'):
        with self.assertRaisesRegex(g.EvidenceRejected,reason):
            self.audit(capture,source)

    def test_sec_valid_but_never_live_origin(self):
        result=self.audit(sec_capture())
        self.assertEqual(result['event_count'],1)
        self.assertFalse(result['http_origin_independently_proven'])
        self.assertFalse(result['may_change_al'])
        self.assertFalse(result['may_place_order'])

    def test_xml_valid_but_never_send_alert(self):
        result=self.audit(rss_capture(),'NASDAQ_HALTS')
        self.assertEqual(result['event_count'],1)
        self.assertFalse(result['may_send_alert'])

    def test_directory_recent_format_not_history(self):
        result=self.audit(directory_capture(),'NASDAQ_DIRECTORY')
        self.assertEqual(result['status'],'FORMAT_REVIEW_ONLY_ORIGIN_NOT_ATTESTED')
        self.assertFalse(result['first_public_availability_proven'])

    def test_directory_stale_snapshot_not_accepted(self):
        result=self.audit(directory_capture('081020261211'),'NASDAQ_DIRECTORY')
        self.assertEqual(result['status'],'STALE_SNAPSHOT_NOT_ACCEPTED')

    def test_http_403_refused(self):
        c=sec_capture();c['status_code']=403;self.reject(c,'HTTP_NOT_200')

    def test_http_429_refused(self):
        c=sec_capture();c['status_code']=429;self.reject(c,'HTTP_NOT_200')

    def test_http_206_refused(self):
        c=sec_capture();c['status_code']=206;self.reject(c,'HTTP_NOT_200')

    def test_boolean_http_status_refused(self):
        c=sec_capture();c['status_code']=True;self.reject(c,'HTTP_NOT_200')

    def test_redirect_not_trusted(self):
        c=sec_capture();c['final_url']='https://evil.invalid/'
        self.reject(c,'URL_OR_REDIRECT_MISMATCH')

    def test_http_non_https_not_trusted(self):
        c=sec_capture();c['request_url']=c['request_url'].replace('https:','http:')
        self.reject(c,'URL_OR_REDIRECT_MISMATCH')

    def test_source_mismatch(self):
        c=sec_capture();c['source']='NASDAQ_HALTS';self.reject(c,'SOURCE_MISMATCH')

    def test_mime_mismatch(self):
        c=sec_capture();c['content_type']='text/html';self.reject(c,'MIME_INVALID')

    def test_compressed_unknown_transport_refused(self):
        c=sec_capture();c['content_encoding']='gzip'
        self.reject(c,'ENCODED_TRANSPORT_UNVERIFIED')

    def test_length_mismatch(self):
        c=sec_capture();c['body_bytes']+=1;self.reject(c,'BODY_LENGTH_MISMATCH')

    def test_hash_mismatch(self):
        c=sec_capture();c['body_sha256']='0'*64;self.reject(c,'HASH_MISMATCH')

    def test_base64_corruption(self):
        c=sec_capture();c['body_base64']='?!';self.reject(c,'BASE64_INVALID')

    def test_after_cutoff_refused(self):
        c=sec_capture();c['observed_at_utc']='2026-10-31T13:00:00Z'
        self.reject(c,'CAPTURE_AFTER_DECISION_CUTOFF')

    def test_timezone_naive_refused(self):
        c=sec_capture();c['observed_at_utc']='2026-10-31T11:00:00'
        self.reject(c,'TIME_NOT_UTC')

    def test_wrong_issuer_rejected(self):
        p=sec_payload();p['cik']=555
        self.reject(envelope('SEC_EDGAR',json.dumps(p)),'SEC_READER_REFUSED')

    def test_malformed_json(self):
        self.reject(envelope('SEC_EDGAR','{"cik":'),'JSON_INVALID')

    def test_json_duplicate_key(self):
        self.reject(envelope('SEC_EDGAR','{"cik":1,"cik":2}'),'JSON_DUPLICATE_KEY')

    def test_json_nonfinite_refused(self):
        self.reject(envelope('SEC_EDGAR','{"cik":NaN}'),'JSON_NONFINITE')

    def test_malformed_xml(self):
        self.reject(envelope('NASDAQ_HALTS','<rss>'),
            'RSS_READER_REFUSED','NASDAQ_HALTS')

    def test_nasdaq_xml_utf8_bom_keeps_original_sha(self):
        original = b'\xef\xbb\xbf' + (
            b'<rss><channel><item><Symbol>AAPL</Symbol>'
            b'<HaltDate>10/30/2026</HaltDate><HaltTime>14:30:00</HaltTime>'
            b'<ReasonCode>T1</ReasonCode></item></channel></rss>')
        c = envelope('NASDAQ_HALTS', original)
        result = self.audit(c, 'NASDAQ_HALTS')
        self.assertEqual(result['parser_status'], 'NASDAQ_HALT_REVIEW')
        self.assertEqual(result['content_sha256'], hashlib.sha256(original).hexdigest())
        self.assertFalse(result['may_send_alert'])

    def test_sec_json_bom_rejected(self):
        payload = b'\xef\xbb\xbf' + json.dumps(sec_payload()).encode('utf-8')
        self.reject(envelope('SEC_EDGAR', payload), 'UTF8_BOM_UNSUPPORTED')

    def test_directory_bom_rejected(self):
        token = b'\xef\xbb\xbf' + (
            b'Symbol|Security Name|Market Category|Test Issue|Financial Status|ETF\n'
            b'AAPL|Apple|Q|N|N|N\nFile Creation Time: 103020261200||||||\n')
        self.reject(envelope('NASDAQ_DIRECTORY', token),
                    'UTF8_BOM_UNSUPPORTED', 'NASDAQ_DIRECTORY')

    def test_xml_doctype_refused(self):
        self.reject(envelope('NASDAQ_HALTS','<!DOCTYPE foo><rss/>'),
            'RSS_READER_REFUSED','NASDAQ_HALTS')

    def test_directory_future_generation_refused(self):
        self.reject(directory_capture('110120261200'),
            'DIRECTORY_READER_REFUSED','NASDAQ_DIRECTORY')

    def test_empty_feed_not_clear(self):
        result=self.audit(envelope('NASDAQ_HALTS','<rss><channel/></rss>'),
                          'NASDAQ_HALTS')
        self.assertEqual(result['parser_status'],'NASDAQ_NO_ITEM_NOT_CLEAR')
        self.assertFalse(result['may_clear_risk'])

    def test_sec_no_event_not_clear(self):
        p=sec_payload();p['filings']['recent']['form']=['SC 13G']
        result=self.audit(envelope('SEC_EDGAR',json.dumps(p)))
        self.assertEqual(result['parser_status'],'SEC_NO_EVENT_NOT_CLEAR')
        self.assertFalse(result['may_clear_risk'])

if __name__=='__main__':
    unittest.main()
