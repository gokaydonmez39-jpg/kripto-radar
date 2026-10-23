#!/usr/bin/env python3
"""Offline deterministic positive/negative regression for XRAY v36."""
from copy import deepcopy
import unittest
from xray_v36_trade_correction_lineage import EvidenceBlocked, replay

S='AAPL'; Z='2026-10-22T19:30:00Z'

def trade(i=10,**kw):
    o={'T':'t','S':S,'z':'C','x':'Q','t':Z,'i':i,
       'p':100.05,'s':100,'c':['@']}
    o.update(kw);return o

def corr(**kw):
    o={'T':'c','S':S,'z':'C','x':'Q','t':'2026-10-22T19:30:01Z',
       'oi':10,'op':100.05,'os':100,'oc':['@'],
       'ci':11,'cp':100.07,'cs':105,'cc':['@']}
    o.update(kw);return o

def cancel(**kw):
    o={'T':'x','S':S,'z':'C','x':'Q','t':'2026-10-22T19:30:02Z',
       'i':11,'p':100.07,'s':105,'a':'C'}
    o.update(kw);return o

class ReplayTests(unittest.TestCase):
    def good(self, events=None, **kw):
        return replay([trade(),corr(),cancel()] if events is None else events,S,**kw)

    def test_positive_correct_then_cancel(self):
        o=self.good()
        self.assertEqual((o['original_trades_seen'],o['corrections_seen'],o['cancels_errors_seen']), (1,1,1))
        self.assertEqual(o['active_trade_count_research_only'],0)
        self.assertFalse(o['historic_30_session_correction_lineage_verified'])
        self.assertFalse(o['canonical_price_pass'])
        self.assertEqual(o['registered_r92_count'],0)

    def test_positive_simple(self):
        self.assertEqual(self.good([trade()])['active_trade_count_research_only'],1)

    def test_caller_claim_is_not_authority(self):
        o=self.good(source_complete=True,provider_rights_attested=True)
        self.assertEqual(o['status'],'RESEARCH_SAMPLE_ONLY')
        self.assertFalse(o['market_data_usage_rights_independently_verified'])
        self.assertFalse(o['independently_attested_full_stream'])

    def test_no_prices_ids_sizes_persisted(self):
        o=self.good()
        self.assertNotIn('trades',o)
        self.assertNotIn('prices',o)
        self.assertNotIn('volume',o)
        self.assertNotIn('trade_ids',o)
        self.assertEqual(o['real_money'],'NO-GO')

    def test_correction_preserves_original_execution_date(self):
        # After-close correction is allowed as a MESSAGE; it does not change
        # the economic time from the original execution.
        ev=[trade(),corr(t='2026-10-23T11:00:00Z')]
        self.assertEqual(self.good(ev)['active_trade_count_research_only'],1)

    def test_reject_matching_invalid_symbol(self):
        # Matching symbol does not make an invalid ticker safe to process.
        ev = trade(S='A/PL')
        with self.assertRaises(EvidenceBlocked):
            replay([ev], 'A/PL')

    def test_reject_backwards_nanos(self):
        a = trade(t='2026-10-22T19:30:00.123456789Z')
        b = trade(i=12, t='2026-10-22T19:30:00.123456100Z')
        with self.assertRaises(EvidenceBlocked):
            self.good([a, b])

    def test_allow_forward_nanos(self):
        a = trade(t='2026-10-22T19:30:00.123456100Z')
        b = trade(i=12, t='2026-10-22T19:30:00.123456789Z')
        self.assertEqual(self.good([a,b])['active_trade_count_research_only'], 2)

    def test_reject_unrepresentable_precision(self):
        a = trade(t='2026-10-22T19:30:00.1234567891Z')
        with self.assertRaises(EvidenceBlocked):
            self.good([a])

    def test_negative_mutations(self):
        cases = [
            ([trade(),trade()], 'duplicate original'),
            ([corr()], 'orphan correction'),
            ([cancel()], 'orphan cancel'),
            ([trade(),cancel(i=10,p=100.05,s=100),cancel(i=10,p=100.05,s=100,t='2026-10-22T19:30:03Z')], 'double cancel'),
            ([trade(),corr(oi=55)], 'wrong original id'),
            ([trade(),corr(op=101.05)], 'old price mismatch'),
            ([trade(),corr(os=99)], 'old size mismatch'),
            ([trade(),corr(oc=['I'])], 'old condition mismatch'),
            ([trade(),corr(ci=10)], 'reused corrected id'),
            ([trade(),corr(cs=0)], 'zero new size'),
            ([trade(),corr(cp=float('nan'))], 'NaN price'),
            ([trade(),corr(cc=['@','@'])], 'duplicate condition'),
            ([trade(),corr(),cancel(p=999)], 'cancel different price'),
            ([trade(),corr(),cancel(s=999)], 'cancel different size'),
            ([trade(),corr(),cancel(a='Z')], 'cancel action unknown'),
            ([trade(),corr(),cancel(x='D')], 'wrong cancel venue'),
            ([trade(),corr(),corr(oi=10,t='2026-10-22T19:30:02Z')], 'repeat correction'),
            ([trade(t='2026-10-22T19:30:00'),corr()], 'naive timestamp'),
            ([trade(t='2026-10-22T19:30:04Z'),corr()], 'backwards sequence'),
            ([trade(z='A')], 'wrong tape'),
            ([trade(S='MSFT')], 'wrong ticker'),
            ([trade(u='incorrect')], 'REST u cannot masquerade as streaming link'),
            ([trade(i=True)], 'boolean id'),
            ([trade(s=1.5)], 'fractional invalid size'),
            ([trade(p=-3)], 'negative price'),
            ([trade(c=[])], 'missing sale condition'),
            ([trade(T='z')], 'unknown event type'),
            ([trade(x='')], 'no venue'),
        ]
        for events,name in cases:
            with self.subTest(name=name), self.assertRaises(EvidenceBlocked):
                self.good(deepcopy(events))

    def test_immutable_sample(self):
        events=[trade(),corr()];snap=deepcopy(events)
        self.good(events)
        self.assertEqual(events,snap)

    def test_invalid_scope(self):
        for sym in ('','abc','ABCDEFGHI','A/PL','aapl'):
            with self.subTest(sym=sym),self.assertRaises(EvidenceBlocked):
                replay([trade()],sym)

    def test_empty_and_wrong_flags(self):
        for ev in ([],{},[None]):
            with self.subTest(ev=ev),self.assertRaises(EvidenceBlocked):
                replay(ev,S)
        with self.assertRaises(EvidenceBlocked):
            self.good([trade()],source_complete='true')

if __name__=='__main__':
    unittest.main()