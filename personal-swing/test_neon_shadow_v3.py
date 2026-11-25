"""Offline-only synthetic tests; no Alpaca/GitHub/Sheets/ChatGPT access."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

import neon_shadow_v3 as n

ASOF = '2026-11-19'
WATCHLIST = Path(__file__).with_name('nasdaq_watchlist_477.json')
if WATCHLIST.exists():
    import runner
    MASTER = runner.get_scope(watchlist_file=str(WATCHLIST), asof=ASOF)
else:
    MASTER = json.loads((Path(__file__).parents[1] / 'neon_v3_isolated' /
                         'master_477_asof_2026-11-19.json').read_text(encoding='utf-8'))
NOW = datetime(2026,11,19,23,16,tzinfo=timezone.utc)
POLICY='a'*64


def fixture():
    dates=n.session_dates(ASOF,NOW)
    raw={}
    rows=[]
    for i,s in enumerate(MASTER):
        base=10 + i*.05
        b=[]
        for j,d in enumerate(dates):
            c=round(base + .045*j + .0002*i*j,6)
            b.append({'timestamp':d+'T21:00:00Z','open':c-.02,'high':c+.16,
                      'low':c-.16,'close':c,'volume':float(1000000+3*i+j*10)})
        raw[s]=b
        m=n.indicators(b)
        rows.append({'symbol':s,'asof_et':ASOF,'decision':'ELE',
                     'close':round(m['close'],3),'atr14':round(m['atr14'],3),
                     'sma20':round(m['sma20'],3),'sma50':round(m['sma50'],3),
                     'prior_high20':round(m['prior_high20'],3),
                     'rsi14':round(m['rsi14'],2),
                     'relative_iex_volume':round(m['rvol20'],3)})
    snap={'schema':'XRAY_PERSONAL_SWING_V3','feed':'ALPACA_IEX_DAILY_ONE_EXCHANGE',
          'asof_et':ASOF,'scope_sha256':n.scope_digest(MASTER),
          'analysis_fingerprint_sha256':POLICY,
          'requested_symbols':477,'processed_symbols':477,'valid_data_symbols':477,
          'remaining_symbols':0,'insufficient_data_symbols':0,
          'valid_data_coverage_complete':True,'new_signal_publishable':True,
          'not_broker':True,'auto_trading':False,'orders_sent':0,'failed_groups':[],
          'counts':{'START':477,'TEKNIK_AL_ADAYI':0,'YAKIN_IZLE':0,'ELE':477,'VERI_YETERSIZ':0},
          'rows':rows}
    return snap,raw


class NeonShadowV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot,cls.raw=fixture()
        cls.good=n.evaluate(cls.snapshot, MASTER, cls.raw,
                            expected_policy_sha=POLICY,now_utc=NOW,source_event='schedule')

    def result(self,snap=None,raw=None,master=None,now=None,event='schedule',policy=POLICY):
        return n.evaluate(self.snapshot if snap is None else snap,
                          MASTER if master is None else master,
                          self.raw if raw is None else raw,
                          expected_policy_sha=policy,
                          now_utc=NOW if now is None else now,source_event=event)

    def test_477_complete_ranks_and_no_delivery(self):
        r=self.good
        self.assertEqual(r['counts']['scored'],477)
        self.assertEqual(r['counts']['na'],0)
        self.assertEqual({a['rank'] for a in r['rows']},set(range(1,478)))
        self.assertEqual({a['symbol'] for a in r['rows']},set(MASTER))
        self.assertTrue(all(0<=float(a['score'])<=100 for a in r['rows']))
        self.assertFalse(r['notification_sent'])
        self.assertEqual(r['orders_sent'],0)
        self.assertFalse(r['chatgpt_card_written'])

    def test_high_score_cannot_create_al(self):
        # Even a malicious UI-level score change cannot change source signal.
        tampered=copy.deepcopy(self.good)
        tampered['rows'][0]['score']='99.99'
        self.assertEqual(tampered['rows'][0]['signal_status'],'NO_NEW_AL')
        self.assertTrue(all(x['signal_status']=='NO_NEW_AL' for x in self.good['rows']))
        self.assertTrue(all(x['decision_corridor']!='İNCELE' for x in self.good['rows']))

    def test_deterministic_no_future_mutation(self):
        self.assertEqual(self.result(),self.good)
        copyraw=copy.deepcopy(self.raw)
        copyraw[MASTER[0]].append({'timestamp':'2026-11-20T21:00:00Z','open':10.,
                    'high':11.,'low':9.,'close':10.,'volume':1000.})
        with self.assertRaisesRegex(n.NeonHold,'RAW_BAR_FROM_FUTURE'):
            self.result(raw=copyraw)

    def test_insufficient_symbol_is_hard_hold(self):
        raw=dict(self.raw);raw.pop(MASTER[0])
        with self.assertRaisesRegex(n.NeonHold,'RAW_BAR_UNIVERSE_INCOMPLETE'):
            self.result(raw=raw)

    def test_missing_bar_rejected(self):
        raw=dict(self.raw);raw[MASTER[0]]=self.raw[MASTER[0]][:-1]
        with self.assertRaisesRegex(n.NeonHold,'RAW_BARS_INCOMPLETE'):
            self.result(raw=raw)

    def test_missing_internal_session_rejected(self):
        raw=dict(self.raw)
        raw[MASTER[0]]=self.raw[MASTER[0]][:20]+self.raw[MASTER[0]][21:]
        with self.assertRaisesRegex(n.NeonHold,'RAW_BARS_INCOMPLETE'):
            self.result(raw=raw)

    def test_duplicate_session_rejected(self):
        raw=dict(self.raw);raw[MASTER[0]]=self.raw[MASTER[0]]+[self.raw[MASTER[0]][-1]]
        with self.assertRaisesRegex(n.NeonHold,'DUPLICATE_RAW_BAR_SESSION'):
            self.result(raw=raw)

    def test_utc_shifted_local_asof_bar_cannot_be_scored(self):
        # A local date prefix is insufficient: Nov 19 23:30 -04:00 is
        # Nov 20 03:30 UTC, i.e. not the requested Nov 19 XNAS bar.
        raw=copy.deepcopy(self.raw)
        raw[MASTER[0]][-1]['timestamp']='2026-11-19T23:30:00-04:00'
        with self.assertRaisesRegex(n.NeonHold,
                                    'RAW_BAR_FROM_FUTURE'):
            self.result(raw=raw)

    def test_neon_indicators_match_independent_production_engine(self):
        # Production engine uses its own indicator implementation. Cross-check
        # all key factors with source-derived 52 XNAS bars, not the NEON
        # fixture-derived synthetic snapshot (which is otherwise self-referential).
        import engine
        for symbol in [MASTER[k] for k in (0, 119, 238, 357, 476)]:
            with self.subTest(symbol=symbol):
                bars=copy.deepcopy(self.raw[symbol])
                # Perturb the CURRENT close/high/volume to catch off-by-one
                # RSI, ATR, rolling-high and relative-volume regression.
                last=bars[-1]
                last['close']+=.23
                last['high']=max(last['high'],last['close']+.1)
                last['volume']*=1.17
                prod=engine.analyze(symbol,bars,ASOF)
                neon=n.indicators(bars)
                self.assertNotEqual(prod['decision'],'VERI_YETERSIZ')
                for source,metric,tolerance in (
                    ('close','close',.00051),
                    ('sma20','sma20',.00051),
                    ('sma50','sma50',.00051),
                    ('prior_high20','prior_high20',.00051),
                    ('relative_iex_volume','rvol20',.00051),
                    ('rsi14','rsi14',.0051),
                    ('atr14','atr14',.00051)):
                    self.assertLessEqual(abs(prod[source]-neon[metric]),
                                         tolerance,
                                         (symbol,source,prod[source],neon[metric]))

    def test_naive_timestamp_rejected(self):
        raw=dict(self.raw)
        bars=copy.deepcopy(self.raw[MASTER[0]])
        bars[-1]['timestamp']='2026-11-19T21:00:00'
        raw[MASTER[0]]=bars
        with self.assertRaisesRegex(n.NeonHold,'RAW_BAR_TIMESTAMP_NAIVE'):
            self.result(raw=raw)

    def test_bad_ohlc_rejected(self):
        raw=dict(self.raw)
        bars=copy.deepcopy(self.raw[MASTER[0]])
        bars[-1]['low']=bars[-1]['high']+1.
        raw[MASTER[0]]=bars
        with self.assertRaisesRegex(n.NeonHold,'RAW_BAR_OHLC_GEOMETRY'):
            self.result(raw=raw)

    def test_nan_input_rejected(self):
        raw=dict(self.raw)
        bars=copy.deepcopy(self.raw[MASTER[0]])
        bars[-1]['close']=float('nan')
        raw[MASTER[0]]=bars
        with self.assertRaisesRegex(n.NeonHold,'RAW_BAR_NONFINITE_OR_MISSING'):
            self.result(raw=raw)

    def test_indicator_drift_rejected(self):
        snapshot=copy.deepcopy(self.snapshot)
        snapshot['rows'][0]['close']+=.01
        with self.assertRaisesRegex(n.NeonHold,'SNAPSHOT_INDICATOR_DRIFT'):
            self.result(snap=snapshot)

    def test_wrong_policy_sha_rejected(self):
        with self.assertRaisesRegex(n.NeonHold,'SNAPSHOT_SCOPE_OR_POLICY_SHA_DRIFT'):
            self.result(policy='b'*64)

    def test_same_asof_old_capture_rejected(self):
        with self.assertRaisesRegex(n.NeonHold,'OUTSIDE_NATURAL_SOURCE_WINDOW'):
            self.result(now=NOW+timedelta(days=2))

    def test_pre_close_gate_rejected(self):
        with self.assertRaisesRegex(n.NeonHold,'OUTSIDE_NATURAL_SOURCE_WINDOW'):
            self.result(now=datetime(2026,11,19,21,20,tzinfo=timezone.utc))

    def test_non_xnas_asof_rejected(self):
        snapshot=copy.deepcopy(self.snapshot);snapshot['asof_et']='2026-11-21'
        for row in snapshot['rows']:row['asof_et']='2026-11-21'
        with self.assertRaisesRegex(n.NeonHold,'NOT_XNAS_SESSION'):
            self.result(snap=snapshot)

    def test_event_push_rejected(self):
        with self.assertRaisesRegex(n.NeonHold,'SHADOW_SOURCE_EVENT_UNTRUSTED'):
            self.result(event='push')

    def test_duplicate_symbol_master_rejected(self):
        master=MASTER[:];master[1]=master[0]
        with self.assertRaisesRegex(n.NeonHold,'MASTER_NOT_EXACT_477'):
            self.result(master=master)

    def test_reordered_master_rejected(self):
        master=MASTER[:];master[0],master[1]=master[1],master[0]
        with self.assertRaisesRegex(n.NeonHold,'SNAPSHOT_SCOPE_OR_POLICY_SHA_DRIFT'):
            self.result(master=master)

    def test_snapshot_missing_account_rejected(self):
        snapshot=copy.deepcopy(self.snapshot)
        snapshot['counts']['ELE']=476
        with self.assertRaisesRegex(n.NeonHold,'SNAPSHOT_COUNTS_DRIFT'):
            self.result(snap=snapshot)

    def test_source_event_manual_research_only(self):
        result=self.result(event='workflow_dispatch')
        self.assertEqual(result['source_event'],'workflow_dispatch')
        self.assertFalse(result['notification_sent'])

    def test_capture_preserves_original_477_master_and_single_read(self):
        count=[]
        def provider(group,asof):
            count.append((group,asof))
            return {s:self.raw[s][:] for s in group}
        capture=n.Capture(provider,MASTER,ASOF)
        for i in range(0,477,10):
            group=MASTER[i:i+10]
            self.assertEqual(capture.read(group,ASOF),{s:self.raw[s] for s in group})
        with tempfile.TemporaryDirectory() as d:
            r=capture.finish(self.snapshot,expected_policy_sha=POLICY,
                             now_utc=NOW,source_event='schedule',
                             output_file=str(Path(d)/'neon.json'))
            data=json.loads((Path(d)/'neon.json').read_text())
            self.assertEqual(data['counts']['scored'],477)
            self.assertEqual(r['scored'],477)
            self.assertEqual(len(count),48)
            self.assertEqual(data['scope_sha256'],n.scope_digest(MASTER))
            self.assertFalse(data['notification_sent'])

    def test_natural_risk_sidecar_counts_and_exact_coverage(self):
        from statistics import stdev
        from decimal import Decimal
        import math
        summary=n.risk_cohort_counts(MASTER,self.raw,asof=ASOF,now_utc=NOW)
        dates=n.session_dates(ASOF,NOW)
        expected=[0,0,0]
        for s in MASTER:
            b=n.validated_bars(s,self.raw[s],dates)
            ret=[b[i]["close"]/b[i-1]["close"]-1. for i in range(len(b)-20,len(b))]
            v=stdev(ret)*math.sqrt(252)
            # Independent decimal oracle; no binary subtraction at boundary.
            g=any(Decimal(str(b[i]["open"]))*10 <=
                  Decimal(str(b[i-1]["close"]))*9 for i in range(1,len(b)))
            expected[0]+=v>=.60
            expected[1]+=v<=.10
            expected[2]+=g
        self.assertEqual(summary["symbols"],477)
        self.assertEqual(summary["sessions"],52)
        self.assertEqual([summary["high_vol20_count"],summary["low_vol20_count"],
                          summary["negative_open_close_discontinuity_10_count"]],expected)
        self.assertFalse(summary["production_decision_authority"])
        self.assertEqual(summary["extra_market_requests"],0)
        self.assertEqual(summary["corporate_action_clearance"],"UNKNOWN")
        self.assertNotIn("rows",summary)
        self.assertNotIn("bars",summary)
        missing=dict(self.raw);del missing[MASTER[0]]
        with self.assertRaisesRegex(n.NeonHold,"RISK_CAPTURE_SCOPE"):
            n.risk_cohort_counts(MASTER,missing,asof=ASOF,now_utc=NOW)

    def test_risk_discontinuity_exact_boundary_and_477_oracle(self):
        from decimal import Decimal
        prices=[89.99,90,90.01,80,100,90.00000000000001,89.99999999999999]*68+[90]
        self.assertEqual(len(prices),477)
        dates=n.session_dates(ASOF,NOW)
        raw={}
        for symbol,price in zip(MASTER,prices):
            bars=[dict(timestamp=d+"T21:00:00Z",open=100.,high=110.,
                       low=80.,close=100.,volume=10000) for d in dates]
            bars[1]["open"]=price
            raw[symbol]=bars
        expected=sum(Decimal(str(p))*10<=Decimal(100)*9 for p in prices)
        self.assertEqual(expected,273)
        r=n.risk_cohort_counts(MASTER,raw,asof=ASOF,now_utc=NOW)
        self.assertEqual(r["negative_open_close_discontinuity_10_count"],expected)
        self.assertEqual(r["low_vol20_count"],477)
        self.assertFalse(r["production_decision_authority"])
        # Check a second occurrence counts once and a non-integer price scale.
        symbol=MASTER[1]
        raw[symbol][2]["open"]=89.99
        self.assertEqual(n.risk_cohort_counts(MASTER,raw,asof=ASOF,now_utc=NOW)
                         ["negative_open_close_discontinuity_10_count"],expected)
        symbol=MASTER[2] # prior 90.01 did not qualify
        raw[symbol][0].update(close=.30,low=.20)
        raw[symbol][1].update(open=.27,low=.20)
        self.assertEqual(n.risk_cohort_counts(MASTER,raw,asof=ASOF,now_utc=NOW)
                         ["negative_open_close_discontinuity_10_count"],expected+1)

    def test_risk_sidecar_failure_preserves_neon_file_and_no_extra_read(self):
        from unittest.mock import patch
        count=[]
        def provider(group,asof):
            count.append((group,asof))
            return {s:self.raw[s][:] for s in group}
        capture=n.Capture(provider,MASTER,ASOF)
        for i in range(0,477,10):
            capture.read(MASTER[i:i+10],ASOF)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"neon.json"
            result=capture.finish(self.snapshot,expected_policy_sha=POLICY,
                                  now_utc=NOW,source_event="schedule",output_file=path)
            original=path.read_bytes()
            self.assertEqual(result["risk_shadow"]["status"],"COHORT_COUNTS_READY_RESEARCH_ONLY")
            self.assertEqual(len(count),48)
            with patch.object(n,"risk_cohort_counts",side_effect=RuntimeError("PRIVATE_EXAMPLE")):
                failed=capture.finish(self.snapshot,expected_policy_sha=POLICY,
                                      now_utc=NOW,source_event="schedule",output_file=path)
                self.assertEqual(failed["risk_shadow"]["status"],"HOLD_RISK_SHADOW")
                self.assertEqual(failed["status"],result["status"])
                self.assertEqual(path.read_bytes(),original)
            with patch.object(n,"risk_cohort_counts",side_effect=AssertionError("MUST_NOT_RUN")) as f:
                manual=capture.finish(self.snapshot,expected_policy_sha=POLICY,
                                      now_utc=NOW,source_event="workflow_dispatch",output_file=path)
                self.assertEqual(manual["risk_shadow"]["status"],"SKIPPED_NON_NATURAL")
                f.assert_not_called()
            self.assertEqual(len(count),48)

    def test_shadow_capture_fault_does_not_block_original_provider(self):
        class FailingSlice(list):
            def __getitem__(self, key):
                if isinstance(key, slice):
                    raise ValueError('SIMULATED_SHADOW_COPY_FAILURE')
                return super().__getitem__(key)
        returned={MASTER[0]:FailingSlice(self.raw[MASTER[0]])}
        capture=n.Capture(lambda group,asof:returned,MASTER,ASOF)
        self.assertIs(capture.read([MASTER[0]],ASOF),returned)
        self.assertTrue(capture.capture_failed)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(n.NeonHold,'RAW_CAPTURE_FAILED'):
                capture.finish(self.snapshot,expected_policy_sha=POLICY,
                               now_utc=NOW,source_event='schedule',
                               output_file=str(Path(d)/'neon.json'))
            self.assertFalse((Path(d)/'neon.json').exists())

    def test_al_math_rejects_wrong_stop(self):
        row={'decision':'AL','close':100.,'atr14':2.,'indicative_stop':95.9,
             'indicative_target_2r':108.,'sma20':95.,'sma50':90.,
             'prior_high20':99.,'rsi14':60.,'relative_iex_volume':1.5}
        measured={'iex_dollar_volume20':1e6,'close':100.,'atr14':2.,
                  'sma20':95.,'sma50':90.,'prior_high20':99.,'rsi14':60.,'rvol20':1.5}
        with self.assertRaisesRegex(n.NeonHold,'SOURCE_AL_STOP_2R_DRIFT'):
            n.compare_snapshot(row,measured)

    def test_al_math_accepts_exact(self):
        row={'decision':'AL','close':100.,'atr14':2.,'indicative_stop':96.,
             'indicative_target_2r':108.,'sma20':95.,'sma50':90.,
             'prior_high20':99.,'rsi14':60.,'relative_iex_volume':1.5}
        measured={'iex_dollar_volume20':1e6,'close':100.,'atr14':2.,'sma20':95.,
                  'sma50':90.,'prior_high20':99.,'rsi14':60.,'rvol20':1.5}
        n.compare_snapshot(row,measured)

    def test_rsi_zero_is_valid_observation_not_missing(self):
        row={'decision':'ELE','close':100.,'atr14':2.,'sma20':105.,
             'sma50':110.,'prior_high20':108.,'rsi14':0.,
             'relative_iex_volume':1.0}
        measured={'close':100.,'atr14':2.,'sma20':105.,'sma50':110.,
                  'prior_high20':108.,'rsi14':0.,'rvol20':1.0}
        n.compare_snapshot(row, measured)

    def test_score_with_reference_weight_contract(self):
        from decimal import Decimal, ROUND_HALF_UP
        for row in self.good['rows'][::61]:
            want=sum(Decimal(str(row['factors'][k])) * Decimal(weight)
                     for k,weight in n.WEIGHTS.items()).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            self.assertEqual(row['score'],str(want))

    def test_independent_live_master_sha(self):
        self.assertEqual(n.scope_digest(MASTER),
                         '3d1d226e2ef511570b2abd57e59c74d2c2156e6eed9baf4a08b8d3df82223060')


if __name__=='__main__':
    unittest.main()
