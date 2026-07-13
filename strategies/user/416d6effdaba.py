from strategies.base import StrategyBase,Bar,Signal
class MyMA(StrategyBase):
 name="myma"
 def init(self,p): super().init(p)
 def next(self,b): return None
 def get_params_space(self):
  return {"n":{"type":"range","min":5,"max":50,"step":1}}
