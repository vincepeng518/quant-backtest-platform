#!/usr/bin/env bash
# 重建交易紀錄頁讀的三個靜態檔（by-month / summary / latest_trades）並推上 GitHub。
# 前端 /trades 直接讀 raw.githubusercontent 的這三個檔；bot 只推快照，不重建它們。
set -euo pipefail
cd /root/quant-backtest-platform
exec 9>/tmp/refresh_trades_static.lock
flock -n 9 || { echo "already running"; exit 0; }

git fetch -q origin master
# 只動 trades 衍生檔；其他未提交改動保留在工作區不碰
git checkout -q origin/master -- trades/by-month trades/summary.json trades/latest_trades.json 2>/dev/null || true
git merge -q --ff-only origin/master 2>/dev/null || git rebase -q --autostash origin/master

python3 scripts/gen_monthly_trades.py >/dev/null
python3 scripts/gen_trades_summary.py >/dev/null
python3 scripts/gen_latest_trades.py >/dev/null

git add -f trades/by-month/ trades/summary.json trades/latest_trades.json
if git diff --cached --quiet; then
  exit 0   # 無變化 → 靜默
fi
git -c user.email=vincepeng518@users.noreply.github.com -c user.name=vincepeng518 \
  commit -q -m "chore(trades): refresh by-month/summary/latest ($(date -u +%Y-%m-%dT%H:%MZ))"
for i in 1 2 3; do
  git push -q origin HEAD:master && exit 0
  git pull -q --rebase origin master
done
echo "push failed"; exit 1
