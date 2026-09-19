#!/usr/bin/env bash
# 5m 突破策略批次優化：BTC + FIL（研究中唯二正期望的標的）
# 用 optimize_local.py 單組合模式（batch_opt.py 不支援 5m / 此策略名）
set -uo pipefail
cd /root/Crypto-Backtesting-Lab

LOG=/root/Crypto-Backtesting-Lab/research/breakout_jev/batch_opt.log
mkdir -p "$(dirname "$LOG")"

run_one() {
  local strat="$1" csv="$2" tag="$3"
  echo "=== $tag 開始 $(date -Is) ==="
  ./venv/bin/python research/optimize_local.py "$strat" "$csv" 3 500 2>&1 | tail -30
  echo "=== $tag 結束 $(date -Is) rc=${PIPESTATUS[0]} ==="
}

{
  run_one strategies/technical/breakout_5m_long.py data/csv/FIL_USDT_5m.csv "FIL 5m"
} >> "$LOG" 2>&1

echo "log: $LOG"
