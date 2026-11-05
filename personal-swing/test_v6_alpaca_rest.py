import os
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch
import engine

SYMBOL='CVLT'
def raw_row(day='2026-10-22'):
    return {'t':day+'T04:00:00Z','o':111.2,'h':113.2,'l':110.6,'c':112.5,'v':111222,'n':480,'vw':111.7}

class RestAdapterTests(unittest.TestCase):
    def call(self, fn, symbols=('CVLT',)):
        with patch.dict(os.environ,{'XRAY_ALPACA_DATA_KEY_ID':'unit-test-key','XRAY_ALPACA_DATA_SECRET_KEY':'unit-test-secret'},clear=True):
            with patch.object(engine,'get_json',side_effect=fn):
                return engine.live_read(list(symbols),'2026-10-22')

    def test_raw_rest_fields_become_internal_complete_schema(self):
        data=self.call(lambda *args,**kw:{'bars':{'CVLT':[raw_row()]},'next_page_token':None})
        self.assertEqual(data['CVLT'][0]['close'],112.5)
        self.assertEqual(data['CVLT'][0]['volume'],111222)
        self.assertTrue(data['CVLT'][0]['timestamp'].startswith('2026-10-22'))
        self.assertEqual(set(data['CVLT'][0]),{'timestamp','open','high','low','close','volume'})

    def test_exact_request_is_iex_raw_readonly(self):
        urls=[]
        def fetch(url, headers):
            urls.append((url,headers));return {'bars':{'CVLT':[raw_row()]}}
        self.call(fetch)
        self.assertEqual(len(urls),1)
        url,heads=urls[0]
        self.assertEqual(urlparse(url).hostname,'data.alpaca.markets')
        self.assertEqual(urlparse(url).path,'/v2/stocks/bars')
        q=parse_qs(urlparse(url).query)
        self.assertEqual(q['feed'],['iex'])
        self.assertEqual(q['adjustment'],['raw'])
        self.assertEqual(q['symbols'],['CVLT'])
        self.assertIn('APCA-API-KEY-ID',heads)
        self.assertIn('APCA-API-SECRET-KEY',heads)

    def test_pagination_accumulates_both_pages(self):
        calls=[]
        def fetch(url, headers):
            token=parse_qs(urlparse(url).query).get('page_token')
            calls.append(token)
            return {'bars':{'CVLT':[raw_row('2026-10-21' if token is None else '2026-10-22')]},
                    'next_page_token':'P2' if token is None else None}
        out=self.call(fetch)
        self.assertEqual(len(out['CVLT']),2)
        self.assertEqual(calls,[None,['P2']])

    def test_repeated_page_token_rejected(self):
        with self.assertRaisesRegex(ValueError,'REPEATED'):
            self.call(lambda *a,**k:{'bars':{},'next_page_token':'same'})

    def test_bad_ohlc_rejected(self):
        row=raw_row();row['h']=109
        with self.assertRaisesRegex(ValueError,'BAD_RANGE'):
            self.call(lambda *a,**k:{'bars':{'CVLT':[row]}})

    def test_missing_price_fails_closed(self):
        row=raw_row();row.pop('c')
        with self.assertRaisesRegex(ValueError,'MISSING_close'):
            self.call(lambda *a,**k:{'bars':{'CVLT':[row]}})

    def test_unknown_symbol_return_rejected(self):
        with self.assertRaisesRegex(ValueError,'UNREQUESTED'):
            self.call(lambda *a,**k:{'bars':{'AAPL':[raw_row()]}})

    def test_non_dict_response_rejected(self):
        with self.assertRaisesRegex(ValueError,'INVALID_RESPONSE_SCHEMA'):
            self.call(lambda *a,**k:[])

    def test_creds_missing_fail_closed(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(PermissionError,'MISSING_PERSONAL_DATA_ONLY_API_KEYS'):
                engine.live_read(['CVLT'],'2026-10-22')

    def test_duplicate_scope_fails(self):
        with patch.dict(os.environ,{'XRAY_ALPACA_DATA_KEY_ID':'x','XRAY_ALPACA_DATA_SECRET_KEY':'y'},clear=True):
            with self.assertRaisesRegex(ValueError,'INVALID_EXACT_SYMBOL_SET'):
                engine.live_read(['CVLT','CVLT'],'2026-10-22')

    def test_missing_second_requested_symbol_is_empty_not_elected(self):
        d=self.call(lambda *a,**k:{'bars':{'CVLT':[raw_row()]}},('CVLT','AAPL'))
        self.assertEqual(d['AAPL'],[])

    def test_point_in_time_symbol_rename_pins_alpaca_asof(self):
        # Nasdaq ECA2026-742 / DTN2026-25: INDV -> new SUPN 2026-11-03.
        # Without asof, a replay of 2026-11-02 INDV on 2026-11-06
        # resolves against today's symbol identity and returns no rows.
        for symbol,day in (('INDV','2026-11-02'),('SUPN','2026-11-05')):
            with self.subTest(symbol=symbol,asof=day):
                urls=[]
                def fetch(url,headers):
                    urls.append(url)
                    return {'bars':{symbol:[raw_row(day)]}}
                with patch.dict(os.environ,{'XRAY_ALPACA_DATA_KEY_ID':'test',
                                            'XRAY_ALPACA_DATA_SECRET_KEY':'test'},clear=True):
                    with patch.object(engine,'get_json',side_effect=fetch):
                        data=engine.live_read([symbol],day)
                self.assertEqual(len(data[symbol]),1)
                self.assertEqual(len(urls),1)
                qs=parse_qs(urlparse(urls[0]).query)
                self.assertEqual(qs['asof'],[day])
                self.assertEqual(qs['feed'],['iex'])
                self.assertEqual(qs['adjustment'],['raw'])

    def test_asof_is_on_every_page_not_just_initial_request(self):
        urls=[]
        def fetch(url,headers):
            qs=parse_qs(urlparse(url).query)
            urls.append(qs)
            return {'bars':{'SUPN':[raw_row('2026-11-05')]},
                    'next_page_token':'NEXT' if len(urls)==1 else None}
        with patch.dict(os.environ,{'XRAY_ALPACA_DATA_KEY_ID':'test',
                                    'XRAY_ALPACA_DATA_SECRET_KEY':'test'},clear=True):
            with patch.object(engine,'get_json',side_effect=fetch):
                engine.live_read(['SUPN'],'2026-11-05')
        self.assertEqual([q['asof'] for q in urls],[['2026-11-05'],['2026-11-05']])
        self.assertEqual(urls[1]['page_token'],['NEXT'])

if __name__=='__main__':unittest.main()
