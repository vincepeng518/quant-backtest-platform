-- 影子交易與監聽覆盤系統 schema
-- Phase 3: 模擬紀錄系統 / Phase 4: 結算與自動覆盤

CREATE TABLE IF NOT EXISTS shadow_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id TEXT NOT NULL,            -- 輪次標識 (market + round_ts)
    market TEXT NOT NULL,              -- 市場 (e.g. BTC-5m-Up-Down)
    signal_ts TEXT NOT NULL,           -- 進場判定時間 (ISO)
    seconds_to_close INTEGER,          -- 下單時距收盤秒數
    side TEXT NOT NULL,                -- UP / DOWN
    entry_type TEXT NOT NULL,          -- SHADOW / LIVE
    sim_buy_cost REAL,                 -- 模擬買入成本 (USDC per share)
    book_depth REAL,                   -- 當下流動性 (目標價位掛單量)
    liquidity_ok INTEGER,              -- 1=足夠 0=不足
    anomaly_flag INTEGER DEFAULT 0,    -- 1=異常行情轉影子
    settle_price REAL,                 -- 輪次結算價 (or 現價)
    pnl REAL,                          -- 模擬盈虧 (USDC)
    win INTEGER,                       -- 1=贏 0=輸 NULL=未結算
    note TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS round_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id TEXT NOT NULL UNIQUE,
    market TEXT NOT NULL,
    round_open_ts TEXT,                -- 輪次開始
    round_close_ts TEXT,               -- 輪次收盤
    open_price REAL,                   -- 輪次開盤現價
    close_price REAL,                  -- 輪次收盤現價
    target_price REAL,                 -- 預測目標價 (if any)
    deviation_entry REAL,              -- 進場時偏離值 (現價-目標)
    btc_window_drop_pct REAL,          -- 輪內從開盤跌幅%
    rsi REAL,
    resolved INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tail_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id TEXT NOT NULL,
    snap_ts TEXT NOT NULL,             -- 快照時間
    secs_to_close INTEGER,             -- 距收盤秒數
    price REAL,                        -- 現價
    bid REAL,                          -- best bid (訂單簿)
    ask REAL,                          -- best ask
    spread REAL,
    vol_1m REAL,                       -- 近1m成交量
    note TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_shadow_round ON shadow_trades(round_id);
CREATE INDEX IF NOT EXISTS idx_roundlog_market ON round_logs(market, round_close_ts);
CREATE INDEX IF NOT EXISTS idx_tail_round ON tail_snapshots(round_id, secs_to_close);
