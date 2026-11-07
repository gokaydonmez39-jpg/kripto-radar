"""No-network budget math and synthetic OHLC smoke contract."""
import unittest
import kronos_capacity_probe as p

class TestKronosCapacity(unittest.TestCase):
    def test_477_requires_every_series(self):
        x=p.capacity_contract(477,500,300)
        self.assertEqual(x['status'],'KRONOS_477_SYNTHETIC_CPU_BUDGET_PASS')
        self.assertEqual(x['real_iex_symbols_tested'],0)
        self.assertEqual(x['live_477_coverage'],'NOT_PROVEN')
        self.assertEqual(x['financial_alpha'],'NOT_PROVEN')
        self.assertFalse(x['orders'])
    def test_timeout_rss_or_476_fail_closed(self):
        for n,t,m in ((476,500,100),(477,1500,100),(477,500,9000)):
            self.assertEqual(p.capacity_contract(n,t,m)['status'],
                             'KRONOS_477_SYNTHETIC_CPU_BUDGET_HOLD')
    def test_synthetic_bars_are_valid_and_no_negative_or_future_price(self):
        dates=['2026-10-%02d' % i for i in range(1,41)]
        for i in (0,236,476):
            bars=p.synthetic_history(i,dates)
            self.assertEqual(len(bars),40)
            self.assertTrue(all(0<bar['low']<=min(bar['open'],bar['close'])<=
                                max(bar['open'],bar['close'])<=bar['high']
                                and bar['volume']>=0 for bar in bars))
if __name__=='__main__':
    unittest.main()
