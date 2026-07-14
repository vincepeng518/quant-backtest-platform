# ============================================================================
# 实盘参考脚本（NOT wired into backtester）
# ----------------------------------------------------------------------------
# 这是用户提供的 OKX 实盘交易脚本的原始版本，保留作参考。
# ⚠️ 不接入回测引擎、不自动运行。要实盘请自行在隔离环境执行，并填入真实 API 金鑰。
# ⚠️ 本 Agent 依 SOUL.md 规则不持有任何私钥 / 不代发真实下单指令。
# ============================================================================
import ccxt
import time
import pandas as pd
import pandas_ta as ta

# 交易所初始化设定 (填写实际 API 金鑰)
exchange = ccxt.okx({
    'apiKey': 'YOUR_API_KEY',
    'secret': 'YOUR_SECRET_KEY',
    'password': 'YOUR_API_PASSWORD',
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

# 交易参数设定
SYMBOL = 'BTC-USDT-SWAP'
TIMEFRAME = '30m'
ORDER_SIZE = 0.01
ADX_THRESHOLD = 20.0
KL_PRICE_LONG = 70000.0  # 预期上方的压力位
KL_PRICE_SHORT = 60000.0 # 预期下方的支撑位

# 全域持仓状态追踪
in_position = False
position_side = None
entry_price = 0.0
stop_loss_price = 0.0
take_profit_price = 0.0

def fetch_data():
    bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=250)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculate_indicators(df):
    df.ta.ema(length=200, append=True)
    df.ta.adx(length=14, append=True)
    df.ta.atr(length=14, append=True)
    df.fillna(0, inplace=True)
    return df

def check_entry_signals(df):
    current_bar = df.iloc[-1]
    prev_bar = df.iloc[-2]
    close_price = current_bar['close']
    ema200 = current_bar['EMA_200']
    ema200_prev = df.iloc[-5]['EMA_200']
    adx = current_bar['ADX_14']
    atr = current_bar['ATRr_14']
    if atr == 0:
        return None
    ema_slope_up = ema200 > ema200_prev
    price_above_ema = close_price > ema200
    trend_strong = adx >= ADX_THRESHOLD
    kl_dist_long = abs(KL_PRICE_LONG - close_price)
    kl_enough_long = (kl_dist_long / atr) >= 3.0
    bull_trend = price_above_ema and ema_slope_up
    kl_dist_short = abs(close_price - KL_PRICE_SHORT)
    kl_enough_short = (kl_dist_short / atr) >= 3.0
    bear_trend = (not price_above_ema) and (not ema_slope_up)
    cross_over = (prev_bar['close'] <= prev_bar['EMA_200']) and (close_price > ema200)
    cross_under = (prev_bar['close'] >= prev_bar['EMA_200']) and (close_price < ema200)
    if bull_trend and trend_strong and kl_enough_long and cross_over:
        return 'LONG', close_price, atr
    if bear_trend and trend_strong and kl_enough_short and cross_under:
        return 'SHORT', close_price, atr
    return None

def execute_trade(side, price, atr):
    global in_position, position_side, entry_price, stop_loss_price, take_profit_price
    print(f"触发 {side} 信号，准备市价进场。当前价格: {price}")
    order_side = 'buy' if side == 'LONG' else 'sell'
    exchange.create_market_order(SYMBOL, order_side, ORDER_SIZE)
    in_position = True
    position_side = side
    entry_price = price
    if side == 'LONG':
        stop_loss_price = entry_price - (atr * 1.0)
        take_profit_price = entry_price + (atr * 1.5)
    else:
        stop_loss_price = entry_price + (atr * 1.0)
        take_profit_price = entry_price - (atr * 1.5)
    print(f"进场成功。停损设定: {stop_loss_price:.2f}，停利设定: {take_profit_price:.2f}")

def check_exit(current_price):
    global in_position, position_side, entry_price, stop_loss_price, take_profit_price
    exit_triggered = False
    order_side = 'sell' if position_side == 'LONG' else 'buy'
    if position_side == 'LONG':
        if current_price <= stop_loss_price:
            print(f"价格 {current_price} 触及停损 {stop_loss_price}，执行平仓。")
            exit_triggered = True
        elif current_price >= take_loss_price:
            pass
        elif current_price >= take_profit_price:
            print(f"价格 {current_price} 触及停利 {take_profit_price}，执行平仓。")
            exit_triggered = True
    elif position_side == 'SHORT':
        if current_price >= stop_loss_price:
            print(f"价格 {current_price} 触及停损 {stop_loss_price}，执行平仓。")
            exit_triggered = True
        elif current_price <= take_profit_price:
            print(f"价格 {current_price} 触及停利 {take_profit_price}，执行平仓。")
            exit_triggered = True
    if exit_triggered:
        exchange.create_market_order(SYMBOL, order_side, ORDER_SIZE)
        in_position = False
        position_side = None

print("启动自动化交易系统...")
while True:
    try:
        df_data = fetch_data()
        df_analyzed = calculate_indicators(df_data)
        current_close = df_analyzed.iloc[-1]['close']
        if not in_position:
            signal_result = check_entry_signals(df_analyzed)
            if signal_result:
                sig_side, sig_price, sig_atr = signal_result
                execute_trade(sig_side, sig_price, sig_atr)
        else:
            check_exit(current_close)
        time.sleep(10)
    except Exception as e:
        print(f"发生错误: {e}")
        time.sleep(10)
