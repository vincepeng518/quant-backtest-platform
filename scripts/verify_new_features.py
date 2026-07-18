import asyncio, sys, json
sys.path.insert(0, "/root/Crypto-Backtesting-Lab")

from data.providers.bingx_tradfi import BingXTradFiProvider, active_symbols
from engine.replay import ReplayBacktester, synthesize_ticks
from strategies.technical.moving_average import MovingAverageCrossStrategy
from engine.exchanges.executor import ExchangeExecutor
from engine.exchanges.registry import list_exchanges


async def main():
    prov = BingXTradFiProvider()
    sym = "NCCOGOLD2USD-USDT"
    print("== 1. Fetch GOLD 1h (BingX TradFi) ==")
    df = await prov.fetch_ohlcv(sym, "1h", start_date="2026-06-01", end_date="2026-07-01", limit=500)
    if df is None or len(df) == 0:
        print("  FAIL: no data"); return
    print(f"  OK rows={len(df)} cols={list(df.columns)} first={df.iloc[0]['timestamp']} last={df.iloc[-1]['timestamp']}")

    print("== 2. ReplayBacktester (tick-level) ==")
    bt = ReplayBacktester(initial_capital=100_000, commission=0.0005, slippage=0.0004, ticks_per_bar=20, tick_seed=42)
    bt.set_data(df)
    strat = MovingAverageCrossStrategy()
    strat.init({"fast": 10, "slow": 30})
    bt.set_strategy(strat)
    res = bt.run()
    print(f"  trades={res.total_trades} win_rate={res.win_rate:.1f}% "
          f"return_pct={res.total_return_pct:.2f} max_dd_pct={res.max_drawdown_pct:.2f} "
          f"sharpe={res.sharpe_ratio:.2f}")

    # correctness: replay must produce >= legacy close-fill trade count divergence sanity
    print("  tick synth sample (bar0):", [(round(t.price,2), round(t.t,2)) for t in synthesize_ticks(df.iloc[0], n_ticks=5)])

    print("== 3. Multi-exchange fee compare (GOLD, qty=1) ==")
    ex = ExchangeExecutor(exchanges=["bingx", "binance", "okx"], mode="paper")
    cmp = await ex.compare_fees(sym, 1.0, "buy")
    for c in cmp:
        print(f"  {c['exchange']:8} fill={c['fill_price']:.2f} fee_rate={c['fee_rate']} "
              f"fee_cost={c['fee_cost']:.4f} latency={c['latency_ms']}ms")
    if not cmp:
        print("  FAIL: no exchange comparison")

    print("== 4. Registry listing ==")
    for e in list_exchanges():
        print(f"  {e['id']:8} maker={e['maker_fee']} taker={e['taker_fee']}")

    print("\nALL CHECKS DONE")


asyncio.run(main())
