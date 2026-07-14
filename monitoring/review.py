from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from typing import Optional


def review(db_path: str = "monitoring/shadow.db") -> dict:
    """Phase 4 自動覆盤報告。

    從 DB 讀取影子交易 + 尾盤快照, 量化:
      - 整體 win rate / pnl
      - 時間窗分布 (150-200s vs 其他)
      - 異常行情 vs 正常行情的勝率差
      - 尾盤特徵 (最後 10-20s 價格跳動幅度 vs 前面)
      - 「提前反轉是騙炮」假說驗證: 進場朝反轉方向, 結算是否真反轉
    """
    c = sqlite3.connect(db_path)

    rep: dict = {"shadow": {}, "by_window": {}, "anomaly": {}, "tail": {}, "hypothesis": {}}

    # DB 可能尚未初始化 (引擎未跑過) -> 回傳空報告
    try:
        c.execute("SELECT COUNT(*) FROM shadow_trades").fetchone()
    except sqlite3.OperationalError:
        rep["shadow"] = {"total": 0, "resolved": 0, "wins": 0, "win_rate": 0.0,
                         "avg_pnl": 0.0, "total_pnl": 0.0}
        c.close()
        return rep
    n = c.execute("SELECT COUNT(*) FROM shadow_trades").fetchone()[0]
    wins = c.execute("SELECT COUNT(*) FROM shadow_trades WHERE win=1").fetchone()[0]
    resolved = c.execute("SELECT COUNT(*) FROM shadow_trades WHERE win IS NOT NULL").fetchone()[0]
    pnls = [r[0] for r in c.execute("SELECT pnl FROM shadow_trades WHERE pnl IS NOT NULL")]
    rep["shadow"] = {
        "total": n, "resolved": resolved, "wins": wins,
        "win_rate": round(wins / resolved * 100, 1) if resolved else 0.0,
        "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
        "total_pnl": round(sum(pnls), 2),
    }

    # --- 時間窗分布 ---
    rows = c.execute(
        "SELECT seconds_to_close, win FROM shadow_trades WHERE win IS NOT NULL").fetchall()
    win_d = defaultdict(lambda: [0, 0])  # secs -> [wins, total]
    for secs, win in rows:
        win_d[secs][1] += 1
        if win:
            win_d[secs][0] += 1
    in_win = [v for s, v in win_d.items() if 150 <= s <= 200]
    out_win = [v for s, v in win_d.items() if not (150 <= s <= 200)]
    rep["by_window"] = {
        "in_150_200": _wr(in_win),
        "outside": _wr(out_win),
    }

    # --- 異常 vs 正常 ---
    anom = c.execute(
        "SELECT COUNT(*), SUM(win) FROM shadow_trades WHERE anomaly_flag=1 AND win IS NOT NULL").fetchone()
    norm = c.execute(
        "SELECT COUNT(*), SUM(win) FROM shadow_trades WHERE anomaly_flag=0 AND win IS NOT NULL").fetchone()
    rep["anomaly"] = {
        "anomaly": _wr2(anom),
        "normal": _wr2(norm),
    }

    # --- 尾盤特徵 ---
    # 每個 round 的尾盤快照: 最後 10-20s 的價格變動 vs 前面基準
    tails = c.execute(
        "SELECT round_id, secs_to_close, price FROM tail_snapshots ORDER BY round_id, secs_to_close DESC").fetchall()
    by_round: dict[str, list] = defaultdict(list)
    for rid, secs, price in tails:
        by_round[rid].append((secs, price))
    jump_last10 = []
    for rid, snaps in by_round.items():
        snaps.sort(key=lambda x: x[0], reverse=True)  # secs 大到小
        # 最後 10s 內的快照
        last10 = [p for s, p in snaps if s <= 10]
        prev = [p for s, p in snaps if 11 <= s <= 20]
        if len(last10) >= 2 and prev:
            j = abs(last10[0] - last10[-1]) / last10[-1] * 100
            base = abs(prev[0] - prev[-1]) / prev[-1] * 100 if len(prev) >= 2 else 0
            jump_last10.append((j, base))
    if jump_last10:
        rep["tail"] = {
            "rounds": len(jump_last10),
            "avg_jump_last10s_pct": round(sum(j for j, _ in jump_last10) / len(jump_last10), 3),
            "avg_jump_prev10s_pct": round(sum(b for _, b in jump_last10) / len(jump_last10), 3),
            "tail_accel": round(
                sum(j - b for j, b in jump_last10) / len(jump_last10), 3),
        }

    # --- 「提前反轉是騙炮」假說 ---
    # 進場 side + 結算方向: 若 side=UP 且 win=1 -> 真反轉; win=0 -> 騙炮
    bait = c.execute(
        "SELECT side, win FROM shadow_trades WHERE win IS NOT NULL").fetchall()
    if bait:
        up_total = sum(1 for s, _ in bait if s == "UP")
        up_win = sum(1 for s, w in bait if s == "UP" and w == 1)
        down_total = sum(1 for s, _ in bait if s == "DOWN")
        down_win = sum(1 for s, w in bait if s == "DOWN" and w == 1)
        rep["hypothesis"] = {
            "up_win_rate": round(up_win / up_total * 100, 1) if up_total else 0.0,
            "down_win_rate": round(down_win / down_total * 100, 1) if down_total else 0.0,
            "note": "win=1 表示進場方向與結算一致 (真反轉); win=0 表示騙炮",
        }

    c.close()
    return rep


def _wr(buckets: list[list]) -> dict:
    wins = sum(b[0] for b in buckets)
    total = sum(b[1] for b in buckets)
    return {"wins": wins, "total": total,
            "win_rate": round(wins / total * 100, 1) if total else 0.0}


def _wr2(row: tuple) -> dict:
    total, wins = row[0], row[1] or 0
    return {"wins": wins, "total": total,
            "win_rate": round(wins / total * 100, 1) if total else 0.0}


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "monitoring/shadow.db"
    r = review(db)
    import json
    print(json.dumps(r, indent=2, ensure_ascii=False))
