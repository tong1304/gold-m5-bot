import unittest
import pandas as pd
from v11.strategies.btc import REGISTRY as BTC
from v11.strategies.gold import REGISTRY as GOLD

class V11StrategyTests(unittest.TestCase):
    def setUp(self):
        rows=[]
        for i in range(100):
            o=100+i*0.05; c=o+0.04; rows.append({"open":o,"high":c+0.08,"low":o-0.03,"close":c,"volume":1})
        self.df=pd.DataFrame(rows)
    def test_btc_registry(self):
        self.assertEqual(set(BTC),{"TREND_PULLBACK","BREAKOUT_RETEST","RANGE_BREAKOUT","MOMENTUM","VOLATILITY_BREAKOUT"})
    def test_gold_registry(self):
        self.assertEqual(set(GOLD),{"TREND_PULLBACK","BREAKOUT_RETEST","EMA_PULLBACK","LIQUIDITY_SWEEP","SR_REVERSAL","VOLATILITY_BREAKOUT"})
    def test_each_strategy_returns_structured_result(self):
        for registry in (BTC,GOLD):
            for name,fn in registry.items():
                result=fn(self.df,"BUY",{})
                self.assertIn(result.status,{"PASS","FAIL","NOT_APPLICABLE"},name)
                self.assertEqual(result.strategy,name)
                self.assertNotIn("CANDLE_CONFIRMATION", result.reasons)

if __name__=="__main__":unittest.main()
