"""Synthetic-only deterministic A33 tests: no web, stocks, private prices or credentials."""
import copy
from datetime import timedelta
import unittest
import exchange_calendars as ec
import sip_shadow_a33 as a

CAL=ec.get_calendar('XNAS')
DAY='2026-10-28'
SESSIONS=CAL.sessions_window(CAL.date_to_session(DAY),-52)

def fixture():
    def series(vol_last=13000):
        rows=[]
        for i,t in enumerate(SESSIONS):
            close=100+i*.28 + (0.52 if i%2 else -0.52)
            rows.append({'session':str(t.date()),'open':close-.25,
                         'high':close+.5, 'low':close-.75,'close':close,
                         'volume':vol_last if i==51 else 10000})
        rows[-1]['close'] += 1.7
        rows[-1]['open'] = rows[-1]['close'] - .25
        rows[-1]['high'] = rows[-1]['close'] + .5
        rows[-1]['low'] = rows[-1]['close'] - .75
        return rows
    return {'schema':a.SCHEMA,'asof_et':DAY,
            'cutoff_utc':'2026-10-28T21:20:00Z',
            'symbols':['FAKE'],
            'iex':{'provider':'ALPACA','feed':'IEX','basis':'RAW',
                   'bars':{'FAKE':series(18000)}},
            'sip':{'provider':'ALPACA','feed':'SIP','basis':'RAW',
                   'bars':{'FAKE':series(11000)}}}

class TestSipShadow(unittest.TestCase):
    def rejects(self,change,reason):
        d=fixture();change(d)
        with self.assertRaisesRegex(a.ComparisonBlocked,reason):a.evaluate(d)

    def test_valid_shadow_disagreement_has_no_side_effects(self):
        x=a.evaluate(fixture())
        self.assertEqual(x['matched_symbols'],1)
        self.assertEqual(x['paired_bar_count'],104)
        self.assertEqual(x['decisions_disagree'],1)
        self.assertEqual(x['disagreement_reasons_aggregated'],{'RVOL_LT1_30':1})
        self.assertEqual(x['iex_shadow_al_count'],1)
        self.assertEqual(x['sip_shadow_al_count'],0)
        self.assertFalse(any(x[k] for k in ('may_issue_production_al','may_write_sheet',
                                            'may_send_alert','may_place_order','may_change_stops')))
        self.assertNotIn('FAKE',str(x))

    def test_source_agreement_no_production_pass(self):
        d=fixture();d['sip']['bars']['FAKE'][-1]['volume']=18000
        x=a.evaluate(d)
        self.assertEqual(x['decisions_disagree'],0)
        self.assertEqual(x['status'],'RESEARCH_AGREEMENT_ONLY')
        self.assertFalse(x['universe_full_477_attested'])

    def test_invalid_basis(self):
        self.rejects(lambda d:d['sip'].update(basis='SPLIT_ADJUSTED'),'PROVIDER_FEED_OR_BASIS')
    def test_swapped_feeds(self):
        self.rejects(lambda d:d['iex'].update(feed='SIP'),'PROVIDER_FEED_OR_BASIS')
    def test_duplicate_scope(self):
        self.rejects(lambda d:d['symbols'].append('FAKE'),'INVALID_SCOPE')
    def test_missing_provider_symbol(self):
        self.rejects(lambda d:d['sip']['bars'].clear(),'SYMBOL_SCOPE')
    def test_missing_asof_bar(self):
        self.rejects(lambda d:d['sip']['bars']['FAKE'].pop(),'INCOMPLETE_HISTORY|MISSING_OR_EXTRA_XNAS_SESSION')
    def test_duplicate_daily_bar(self):
        self.rejects(lambda d:d['sip']['bars']['FAKE'].append(copy.deepcopy(d['sip']['bars']['FAKE'][-1])),'DUPLICATE_PROVIDER_SESSION')
    def test_future_bar(self):
        self.rejects(lambda d:d['sip']['bars']['FAKE'][-1].update(session='2026-10-29'),'FUTURE_BAR_FORBIDDEN')
    def test_malformed_bar(self):
        self.rejects(lambda d:d['sip']['bars']['FAKE'][-1].update(high=1),'INVALID_OHLC_GEOMETRY')
    def test_nan(self):
        self.rejects(lambda d:d['sip']['bars']['FAKE'][-1].update(close=float('nan')),'INVALID_NUMERIC_BAR')
    def test_embargo(self):
        self.rejects(lambda d:d.update(cutoff_utc='2026-10-28T20:08:00Z'),'SIP_15_MINUTE_EMBARGO')
    def test_future_asof(self):
        self.rejects(lambda d:d.update(asof_et='2026-10-29'),'SIP_15_MINUTE_EMBARGO')
    def test_holiday(self):
        self.rejects(lambda d:d.update(asof_et='2026-10-25'),'ASOF_NOT_XNAS_SESSION')
    def test_identity_mixing(self):
        self.rejects(lambda d:d['sip']['bars'].update({'OTHER':d['sip']['bars'].pop('FAKE')}),'SYMBOL_SCOPE_COVERAGE')
    def test_old_unknown_not_no_signal(self):
        self.rejects(lambda d:d['iex']['bars']['FAKE'].clear(),'INCOMPLETE_HISTORY')
    def test_unsorted_history(self):
        self.rejects(lambda d:d['sip']['bars']['FAKE'].reverse(),'UNSORTED_PROVIDER_SESSIONS')
    def test_477_synthetic_coverage_and_privacy(self):
        d=fixture()
        d['symbols']=['FAKE%03d'%i for i in range(477)]
        left=d['iex']['bars'].pop('FAKE')
        right=d['sip']['bars'].pop('FAKE')
        d['iex']['bars']={sym:copy.deepcopy(left) for sym in d['symbols']}
        d['sip']['bars']={sym:copy.deepcopy(right) for sym in d['symbols']}
        x=a.evaluate(d)
        self.assertEqual(x['matched_symbols'],477)
        self.assertEqual(x['paired_bar_count'],52*477*2)
        self.assertEqual(x['decisions_disagree'],477)
        self.assertFalse(x['universe_full_477_attested'])
        self.assertNotIn('FAKE000',str(x))

    def test_477_synthetic_one_missing_blocks_not_no_signal(self):
        d=fixture()
        d['symbols']=['FAKE%03d'%i for i in range(477)]
        left=d['iex']['bars'].pop('FAKE')
        right=d['sip']['bars'].pop('FAKE')
        d['iex']['bars']={sym:left for sym in d['symbols']}
        d['sip']['bars']={sym:right for sym in d['symbols']}
        d['sip']['bars']['FAKE476']=right[:-1]
        with self.assertRaisesRegex(a.ComparisonBlocked,'INCOMPLETE_HISTORY'):
            a.evaluate(d)


if __name__=='__main__':unittest.main()
