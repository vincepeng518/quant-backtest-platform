from strategies.base import Bar, Signal, StrategyBase
class PersistTest(StrategyBase):
    name = "persist_test"
    description = "persistence e2e"
    category = "test"
    def init(self, p):
        super().init(p)
    def next(self, bar):
        return None
