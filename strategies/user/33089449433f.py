from strategies.base import StrategyBase,Bar,Signal
class T(StrategyBase):
 name="t"
 def init(self,p): super().init(p)
 def next(self,b): return None
