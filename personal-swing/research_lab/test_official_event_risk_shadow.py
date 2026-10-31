"""Deterministic, adversarial, no-network XRAY source contract tests."""
from copy import deepcopy
import unittest
import official_event_risk_shadow as r

CUTOFF='2026-10-31T04:00:00Z'
OBS='2026-10-31T03:00:00Z'
CIK='0000320193'
ACC='0000320193-26-000001'

def sec():
    return {'cik':320193,'tickers':['AAPL'], 'filings':{'recent':{
        'accessionNumber':[ACC], 'form':['8-K'], 'filingDate':['2026-10-30'],
        'acceptanceDateTime':['2026-10-30T20:00:00Z']}}}

def halt():
    return '''<rss version="2.0" xmlns:n="https://nasdaqtrader.com/schema">
<channel><title>Nasdaq Trade Halts</title><item>
<n:Symbol>AAPL</n:Symbol><n:HaltDate>10/30/2026</n:HaltDate>
<n:HaltTime>14:30:00</n:HaltTime><n:ReasonCode>T1</n:ReasonCode>
</item></channel></rss>'''

def action():
    return {'corporate_actions':[{'id':'ca-1','symbol':'AAPL',
      'type':'reverse_split','process_date':'2026-10-30'}],
      'next_page_token':None}

def directory():
    return ('Symbol|Security Name|Market Category|Test Issue|Financial Status|ETF\n'
            'AAPL|Apple Inc|Q|N|N|N\n'
            'MSFT|Microsoft|Q|N|N|N\n'
            'File Creation Time: 103020261800||||||\n')

class OfficialSourceTests(unittest.TestCase):
    def _sec(self,d=None,**kw):
        return r.inspect_sec(sec() if d is None else d,CIK,'AAPL',asof_utc=CUTOFF,observed_at_utc=OBS,**kw)
    def _halt(self,v=None):
        return r.inspect_nasdaq_halts(halt() if v is None else v,'AAPL',asof_utc=CUTOFF,observed_at_utc=OBS)
    def _actions(self,d=None):
        return r.inspect_alpaca_actions(action() if d is None else d,'AAPL',asof_utc=CUTOFF,observed_at_utc=OBS)
    def _dir(self,v=None):
        return r.inspect_nasdaq_directory(directory() if v is None else v,'AAPL',asof_utc=CUTOFF,observed_at_utc=OBS)

    def test_sec_valid_is_review_not_trading_clearance(self):
        v=self._sec();self.assertEqual(v['event_count'],1)
        self.assertTrue(v['acceptance_not_publication_timestamp'])
        self.assertFalse(v['pit_available_proven'])
        self.assertFalse(v['may_issue_al'])
    def test_sec_wrong_cik_rejected(self):
        d=sec();d['cik']=123
        with self.assertRaisesRegex(r.SourceRefused,'CIK_MISMATCH'):self._sec(d)
    def test_sec_current_ticker_identity_guard(self):
        d=sec();d['tickers']=['MSFT']
        with self.assertRaisesRegex(r.SourceRefused,'TICKER_MISMATCH'):self._sec(d)
    def test_sec_naive_acceptance_rejected(self):
        d=sec();d['filings']['recent']['acceptanceDateTime']=['2026-10-30T20:00:00']
        with self.assertRaisesRegex(r.SourceRefused,'TIMESTAMP_NAIVE'):self._sec(d)
    def test_sec_duplicate_accession_rejected(self):
        d=sec()
        for col in d['filings']['recent'].values():col.append(col[0])
        with self.assertRaisesRegex(r.SourceRefused,'ACCESSION_DUPLICATE'):self._sec(d)
    def test_sec_1001_recent_rows_are_contract_valid_research_only(self):
        d=sec()
        recent=d['filings']['recent']
        for key in recent:
            recent[key]=[recent[key][0]]*1001
        recent['accessionNumber']=[
            '0000320193-26-%06d' % (i+1) for i in range(1001)]
        d['filings']['files']=[{'name':'CIK0000320193-submissions-001.json'}]
        v=self._sec(d)
        self.assertEqual(v['recent_filing_rows_observed'],1001)
        self.assertEqual(v['supplemental_history_files_declared'],1)
        self.assertFalse(v['filing_history_exhaustiveness_proven'])
        self.assertFalse(v['acceptance_utc_independently_crosschecked'])
        self.assertFalse(v['may_issue_al'])

    def test_sec_20001_rows_defensive_limit_rejected(self):
        d=sec()
        recent=d['filings']['recent']
        for key in recent:
            recent[key]=[recent[key][0]]*20001
        with self.assertRaisesRegex(r.SourceRefused,'SEC_COLUMN_LENGTH_DRIFT'):
            self._sec(d)

    def test_sec_corrupt_column_lengths_rejected(self):
        d=sec();d['filings']['recent']['form'].append('10-K')
        with self.assertRaisesRegex(r.SourceRefused,'COLUMN_LENGTH_DRIFT'):self._sec(d)
    def test_sec_future_filing_is_not_visible(self):
        d=sec();d['filings']['recent']['acceptanceDateTime']=['2026-11-02T20:00:00Z']
        v=self._sec(d)
        self.assertEqual(v['event_count'],0)
        self.assertEqual(v['timestamp_dispute_count'],1)
        self.assertEqual(v['status'],'SEC_TIMESTAMP_DISPUTE_REVIEW_REQUIRED')
        self.assertFalse(v['may_issue_al'])
    def test_sec_synthetic_four_hour_skew_is_quarantined_not_lost(self):
        d=sec()
        d['filings']['recent']['acceptanceDateTime']=['2026-10-31T05:00:00Z']
        v=self._sec(d)
        self.assertEqual(v['event_count'],0)
        self.assertEqual(v['timestamp_dispute_count'],1)
        self.assertEqual(v['timestamp_dispute_events'][0]['form'],'8-K')
        self.assertFalse(v['timestamp_dispute_may_prove_late_publication'])
        self.assertFalse(v['pit_available_proven'])
        self.assertFalse(v['may_send_alert'])

    def test_sec_nonrisk_future_filing_no_false_risk_claim(self):
        d=sec()
        d['filings']['recent']['form']=['SC 13G']
        d['filings']['recent']['acceptanceDateTime']=['2026-11-02T20:00:00Z']
        v=self._sec(d)
        self.assertEqual(v['timestamp_dispute_count'],0)
        self.assertEqual(v['status'],'SEC_NO_EVENT_NOT_CLEAR')
        self.assertFalse(v['history_complete_proven'])

    def test_sec_mixed_risk_events_keep_valid_and_disputed_separate(self):
        d=sec()
        recent=d['filings']['recent']
        for k in recent:
            recent[k].append(recent[k][0])
        recent['accessionNumber'][1]='0000320193-26-000002'
        recent['form'][1]='10-Q'
        recent['acceptanceDateTime'][1]='2026-10-31T06:00:00Z'
        v=self._sec(d)
        self.assertEqual(v['event_count'],1)
        self.assertEqual(v['timestamp_dispute_count'],1)
        self.assertEqual(v['status'],'SEC_TIMESTAMP_DISPUTE_REVIEW_REQUIRED')
        self.assertNotEqual(v['events'][0]['event_id'],
                            v['timestamp_dispute_events'][0]['event_id'])
        self.assertFalse(v['may_issue_al'])

    def test_sec_unrelated_form_is_not_8k(self):
        d=sec();d['filings']['recent']['form']=['SC 13G']
        self.assertEqual(self._sec(d)['event_count'],0)
    def test_sec_null_payload_fails(self):
        with self.assertRaisesRegex(r.SourceRefused,'CIK_MISMATCH'):self._sec({})

    def test_nasdaq_halt_true_event_review(self):
        v=self._halt();self.assertEqual(v['event_count'],1)
        self.assertEqual(v['events'][0]['reason_code'],'T1')
        self.assertFalse(v['may_send_alert'])
    def test_nasdaq_empty_feed_not_clear(self):
        v=self._halt('<rss><channel/></rss>')
        self.assertEqual(v['status'],'NASDAQ_NO_ITEM_NOT_CLEAR')
    def test_nasdaq_xml_doctype_forbidden(self):
        with self.assertRaisesRegex(r.SourceRefused,'DTD_ENTITY_FORBIDDEN'):
            self._halt('<!DOCTYPE foo [<!ENTITY x "danger">]>'+halt())
    def test_nasdaq_explicit_symbol_required(self):
        with self.assertRaisesRegex(r.SourceRefused,'MISSING_EXPLICIT_SYMBOL'):
            self._halt(halt().replace('<n:Symbol>AAPL</n:Symbol>',''))
    def test_nasdaq_invalid_halt_date_rejected(self):
        with self.assertRaisesRegex(r.SourceRefused,'DATE_INVALID'):
            self._halt(halt().replace('10/30/2026','13/30/2026'))
    def test_nasdaq_future_date_rejected(self):
        with self.assertRaisesRegex(r.SourceRefused,'FUTURE_HALT_DATE'):
            self._halt(halt().replace('10/30/2026','11/02/2026'))
    def test_nasdaq_duplicate_rss_event_fails(self):
        s=halt().replace('</item></channel>','</item><item><n:Symbol>AAPL</n:Symbol><n:HaltDate>10/30/2026</n:HaltDate><n:HaltTime>14:30:00</n:HaltTime><n:ReasonCode>T1</n:ReasonCode></item></channel>')
        with self.assertRaisesRegex(r.SourceRefused,'DUPLICATE_EVENT'):self._halt(s)
    def test_nasdaq_different_symbol_not_clear(self):
        v=self._halt(halt().replace('AAPL','MSFT'))
        self.assertEqual(v['status'],'NASDAQ_NO_ITEM_NOT_CLEAR')
    def test_nasdaq_missing_reason_code_rejected(self):
        with self.assertRaisesRegex(r.SourceRefused,'DETAILS_MISSING'):
            self._halt(halt().replace('<n:ReasonCode>T1</n:ReasonCode>',''))
    def test_nasdaq_malformed_xml_rejected(self):
        with self.assertRaisesRegex(r.SourceRefused,'RSS_MALFORMED'):self._halt('<rss>')

    def test_alpaca_reverse_split_remains_research(self):
        v=self._actions();self.assertEqual(v['event_count'],1)
        self.assertFalse(v['adjusted_price_or_volume_generated'])
    def test_alpaca_pagination_not_ignored(self):
        d=action();d['next_page_token']='next_page'
        with self.assertRaisesRegex(r.SourceRefused,'PAGINATION_INCOMPLETE'):self._actions(d)
    def test_alpaca_duplicate_ids_rejected(self):
        d=action();d['corporate_actions'].append(deepcopy(d['corporate_actions'][0]))
        with self.assertRaisesRegex(r.SourceRefused,'DUPLICATE_OR_MISSING_ID'):self._actions(d)
    def test_alpaca_invalid_type_rejected(self):
        d=action();d['corporate_actions'][0]['type']='magical_buy_signal'
        with self.assertRaisesRegex(r.SourceRefused,'UNKNOWN_KIND'):self._actions(d)
    def test_alpaca_future_process_not_issued_now(self):
        d=action();d['corporate_actions'][0]['process_date']='2026-11-02'
        self.assertEqual(self._actions(d)['event_count'],0)
    def test_alpaca_wrong_symbol_not_laundered(self):
        d=action();d['corporate_actions'][0]['symbol']='MSFT'
        self.assertEqual(self._actions(d)['event_count'],0)
    def test_alpaca_missing_payload_rejected(self):
        with self.assertRaisesRegex(r.SourceRefused,'RESPONSE_MISSING'):
            self._actions({})
    def test_alpaca_incomplete_empty_not_clear(self):
        d={'corporate_actions':[],'next_page_token':None}
        self.assertEqual(self._actions(d)['status'],'CA_NONE_NOT_CLEAR')

    def test_nasdaq_dir_current_match_only(self):
        v=self._dir();self.assertTrue(v['symbol_found'])
        self.assertTrue(v['historical_membership_not_proven'])
        self.assertFalse(v['pit_available_proven'])
    def test_nasdaq_dir_not_found_not_clear(self):
        v=self._dir(directory().replace('AAPL|Apple Inc|Q|N|N|N\n',''))
        self.assertEqual(v['status'],'DIRECTORY_SYMBOL_NOT_FOUND_REVIEW')
    def test_nasdaq_dir_test_issue_rejected_as_current_clear(self):
        v=self._dir(directory().replace('AAPL|Apple Inc|Q|N|N|N','AAPL|Apple Inc|Q|Y|N|N'))
        self.assertEqual(v['status'],'DIRECTORY_STATUS_REVIEW')
    def test_nasdaq_dir_financial_status_warning(self):
        v=self._dir(directory().replace('AAPL|Apple Inc|Q|N|N|N','AAPL|Apple Inc|Q|N|D|N'))
        self.assertEqual(v['status'],'DIRECTORY_STATUS_REVIEW')
    def test_nasdaq_dir_etf_is_not_stock(self):
        v=self._dir(directory().replace('AAPL|Apple Inc|Q|N|N|N','AAPL|Apple Inc|Q|N|N|Y'))
        self.assertEqual(v['status'],'DIRECTORY_STATUS_REVIEW')
    def test_nasdaq_dir_duplicate_symbol_fails(self):
        v=directory().replace('MSFT|Microsoft|Q|N|N|N\n','AAPL|Dup|Q|N|N|N\n')
        with self.assertRaisesRegex(r.SourceRefused,'DUPLICATE_TICKER'):self._dir(v)
    def test_nasdaq_dir_missing_timestamp_fails(self):
        with self.assertRaisesRegex(r.SourceRefused,'CREATION_TIMESTAMP_MISSING'):
            self._dir(directory().split('File Creation Time:')[0])
    def test_nasdaq_dir_timestamp_future_fails(self):
        with self.assertRaisesRegex(r.SourceRefused,'CREATED_AFTER_OBSERVATION'):
            self._dir(directory().replace('103020261800','110220261800'))
    def test_nasdaq_dir_bad_header_fails(self):
        with self.assertRaisesRegex(r.SourceRefused,'HEADER_DRIFT'):
            self._dir(directory().replace('Test Issue','Test Index'))

    def test_all_four_present_no_production_side_effects(self):
        v=r.offline_summary('AAPL',asof_utc=CUTOFF,observed_at_utc=OBS,
            cik=CIK,sec=sec(),halts=halt(),corporate_actions=action(),directory=directory())
        self.assertEqual(v['state'],'RESEARCH_REVIEW_ONLY_NO_CLEARANCE')
        self.assertEqual(len(v['sources']),4)
        self.assertFalse(v['may_modify_al'])
        self.assertFalse(v['may_emit_alert'])
        self.assertFalse(v['may_place_order'])
        self.assertFalse(v['may_write_sheet'])
        self.assertFalse(v['market_event_exhaustiveness_proven'])
    def test_absent_four_sources_cannot_be_success(self):
        v=r.offline_summary('AAPL',asof_utc=CUTOFF,observed_at_utc=OBS)
        self.assertEqual(set(s['status'] for s in v['sources'].values()),
                         {'NOT_PROVIDED_NOT_CLEAR'})
    def test_invalid_one_source_does_not_mask_other(self):
        d=sec();d['cik']=10
        v=r.offline_summary('AAPL',asof_utc=CUTOFF,observed_at_utc=OBS,
            cik=CIK,sec=d,halts=halt())
        self.assertEqual(v['sources']['SEC_EDGAR']['status'],'SOURCE_REFUSED')
        self.assertEqual(v['sources']['NASDAQ_HALTS']['status'],'NASDAQ_HALT_REVIEW')
    def test_utc_now_before_observation_fails(self):
        with self.assertRaisesRegex(r.SourceRefused,'OBSERVED_AFTER_CUTOFF'):
            r.inspect_sec(sec(),CIK,'AAPL',asof_utc=OBS,observed_at_utc=CUTOFF)
    def test_nan_or_empty_ticker_invalid(self):
        with self.assertRaisesRegex(r.SourceRefused,'SYMBOL_INVALID'):
            r.offline_summary('',asof_utc=CUTOFF,observed_at_utc=OBS)

if __name__=='__main__':
    unittest.main()