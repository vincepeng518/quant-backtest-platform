#!/usr/bin/env python3
"""把 s1-s4 的 JSON 彙整成固定格式報告（Markdown）。"""
import json
import os

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"


def load(name):
    p = os.path.join(OUT, name)
    return json.load(open(p)) if os.path.exists(p) else None


def main() -> None:
    print("# 5m 突破 × Jev × 蒙地卡羅 — 結果（目標：月化 20%、複利、加槓桿後回撤上限 30%）\n")
    print("> 樣本：BTC 2025-06-25~2026-07-30（115,202 根）、APT/SUI 2025-10-04~2026-08-10、"
          "FIL 2026-01-31~2026-07-30、BCH 2026-01-31~2026-06-05。成本：taker 0.05% + 滑價 0.02%/邊。\n")
    s1 = load("s1_edge.json")
    if s1:
        print("## 1. 原始 edge（零成本 vs 含成本）\n")
        print("| 標的 | lookback | 零費平均% | 95% CI | 顯著 | 含費平均% | 樣本 | 勝率 | PF |")
        print("|---|---|---|---|---|---|---|---|---|")
        for tag, rows in s1.items():
            for r in rows:
                print(f"| {tag} | {r['lookback']} | {r['zero_fee_avg_pct']:+.4f} | "
                      f"[{r['ci_lo_pct']:+.4f}, {r['ci_hi_pct']:+.4f}] | "
                      f"{'✓' if r['significant'] else '✗'} | {r['fee_avg_pct']:+.4f} | "
                      f"{r['n_trades']} | {r['win_rate']:.1%} | {r['pf']:.2f} |")
        n_sig = sum(1 for rows in s1.values() for r in rows if r["significant"])
        n_neg = sum(1 for rows in s1.values() for r in rows if r["ci_hi_pct"] < 0)
        print(f"\n合計 {sum(len(v) for v in s1.values())} 個（標的 × lookback）配置："
              f"**顯著為正 {n_sig} 個、顯著為負 {n_neg} 個**。\n")

    s2 = load("s2_walkforward.json")
    if s2:
        print("## 2. 錨定式 Walk-Forward（含隨機參數對照）\n")
        print("| 標的 | 折 | IS Sharpe | OOS Sharpe | OOS 報酬% | 樣本 | control P90 | 勝過 control |")
        print("|---|---|---|---|---|---|---|---|")
        for tag, folds in s2.items():
            for f in folds:
                print(f"| {tag} | {f['fold']} | {f['is_sharpe']:+.3f} | {f['oos_sharpe']:+.3f} | "
                      f"{f['oos_ret_pct']:+.1f} | {f['oos_n']} | {f['ctrl_p90_sharpe']:+.3f} | "
                      f"{'✓' if f['beats_control'] else '✗'} |")
            oos = [f["oos_sharpe"] for f in folds]
            if oos:
                print(f"| {tag} | **平均** | （不適用） | **{sum(oos) / len(oos):+.3f}** | "
                      f"（不適用） | {sum(f['oos_n'] for f in folds)} | （不適用） | "
                      f"**{sum(1 for f in folds if f['beats_control'])}/{len(folds)}** |")
        print()

    s3 = load("s3_monte_carlo.json")
    if s3:
        print("## 3. 蒙地卡羅（10,000 次，含槓桿與爆倉）\n")
        print("槓桿採事後線性套用（ret×L + 爆倉歸零），不含追繳減倉動態路徑。\n")
        print("| 標的 | lookback | 槓桿 | 中位最終 | P5 | 破產機率% | 中位月化% | MaxDD P95% | 達月化20%機率% | 30%DD內可用 |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for tag, d in s3.items():
            for lev, s in d["leverage"].items():
                print(f"| {tag} | {d['lookback']} | {lev} | {s['median']:.3f} | {s['p5']:.3f} | "
                      f"{s['bankruptcy_prob_pct']:.1f} | {s['median_monthly_pct']:+.2f} | "
                      f"{s['maxdd_p95_pct']:.1f} | {s['prob_hit_20pct_monthly']:.1f} | "
                      f"{'✓' if s['feasible_within_30dd'] else '✗'} |")
        print()
        for tag, d in s3.items():
            need = d["required_trades_for_20pct"]
            need_s = "∞" if need == float("inf") else f"{need:,.0f}"
            print(f"- {tag}：達月化 20% 所需樣本（保守估計）**{need_s} 筆**，實測只有 "
                  f"{d['base']['n']} 筆（{d['base']['avg_pct']:+.4f}%/筆）")
        print()

    s4 = load("s4_jev_gate.json")
    if s4:
        print("## 4. Jev 過濾器（嚴格 OOS：train 50% → val 25% → test 25%）\n")
        print("> ⚠️ **本節結論已作廢**（2026-09-20）：實驗設計有缺陷 —— 問的是價格路徑預測、")
        print("> criteria 無 HOLD 選項（導致 1431/1431 全部硬選同一個答案）、state 只有摘要無證據、")
        print("> 無正當對照組、版本未鎖。詳見 `README.md` 的「Jev 實驗設計缺陷」段落。")
        print("> 反證：加上 HOLD 三選項後，同一份 state 立刻回 `HOLD 0.99 / BUY 0.01`。\n")
        print("| 標的 | train n | Jev 準確率 | 多數類基準線 | 有技能 | val 門檻 | test 無Jev 平均% | test 有Jev 平均% | 增益% |")
        print("|---|---|---|---|---|---|---|---|---|")
        for tag, d in s4.items():
            mb, mg = d["test_no_jev"], d["test_with_jev"]
            acc = d.get("jev_accuracy")
            br = d.get("majority_base_rate")
            acc_s = f"{acc:.1%}" if acc is not None else "—"
            br_s = f"{max(br, 1 - br):.1%}" if br is not None else "—"
            print(f"| {tag} | {d.get('train_n', '—')} | {acc_s} | {br_s} | "
                  f"{'✓' if d.get('has_skill') else '✗'} | {d['best_thr']:.2f} | "
                  f"{mb['avg_pct']:+.4f} | {mg['avg_pct']:+.4f} | {d['gain_avg_pct']:+.4f} |")
        n_skill = sum(1 for d in s4.values() if d.get("has_skill"))
        print(f"\n**{n_skill}/{len(s4)} 個標的顯示 Jev 有技能** —— 準確率恰等於多數類基準線的，"
              f"代表它只是複述基礎機率（說「會繼續」的比例 ≈ 實際發生率），沒有擇時資訊。\n")

    print("## 5. 結論\n")
    print(_verdict(s1, s2, s3, s4))


def _verdict(s1, s2, s3, s4) -> str:
    sig = bool(s1) and any(r["significant"] for rows in s1.values() for r in rows)
    oos_pos = bool(s2) and any(f["oos_sharpe"] > 0 for folds in s2.values() for f in folds)
    oos_mean_pos = bool(s2) and all(
        (sum(f["oos_sharpe"] for f in folds) / len(folds)) > 0
        for folds in s2.values() if folds)
    ctrl = bool(s2) and any(f["beats_control"] and f["oos_n"] >= 20
                            for folds in s2.values() for f in folds)
    ctrl_weak_n = sum(1 for folds in (s2 or {}).values() for f in folds if f["beats_control"])
    p20 = max((s["prob_hit_20pct_monthly"] for d in (s3 or {}).values()
               for s in d["leverage"].values()), default=0.0)
    any_feasible = bool(s3) and any(s["feasible_within_30dd"] for d in s3.values()
                                    for s in d["leverage"].values())
    n_neg = sum(1 for rows in (s1 or {}).values() for r in rows if r["ci_hi_pct"] < 0)
    lines = [
        f"- 原始 edge 顯著為正（零成本 CI 下界 > 0）：{'是' if sig else '否'}"
        + (f"（另有 {n_neg} 個配置**顯著為負** —— 突破是反指標）" if n_neg else ""),
        f"- Walk-Forward：所有標的 OOS 平均為正：{'是' if oos_mean_pos else '否'}",
        f"- Walk-Forward：任一折「勝過隨機參數 P90 **且樣本 >= 20 筆**」：{'是' if ctrl else '否'}"
        + (f"（另有 {ctrl_weak_n} 折帳面上勝出，但樣本數 < 20，統計上無效）"
           if ctrl_weak_n and not ctrl else ""),
        f"- MC 達到月化 20% 的最高機率：{p20:.1f}%",
        f"- 存在「MaxDD P95 < 30% 且破產 < 5%」的槓桿配置：{'是' if any_feasible else '否'}",
    ]
    if sig and oos_mean_pos and ctrl and p20 > 20 and any_feasible:
        lines.append("\n**判定：有可開發的 edge。**下一步做參數穩健性細部掃描與 paper trading。")
    else:
        lines.append(
            "\n**判定：不存在可支撐月化 20% 的 edge。**\n"
            "- 零成本下每筆約 −0.02%~+0.18%（多數為負），扣 0.14% 來回成本後幾乎全部為負。\n"
            "- 加槓桿只是等比放大：1x 就已達 53%~82% 回撤（遠超你設的 30%），"
            "3x 以上破產機率 100%。\n"
            "- Jev 過濾器（Stage 4）：**結論作廢** —— 實驗設計有缺陷（問價格路徑預測、criteria 無 HOLD、"
            "state 只有摘要無證據、無對照組、版本未鎖）。加上 HOLD 三選項後同一 state 立刻回 "
            "`HOLD 0.99 / BUY 0.01`，證明前一輪的 100% 偏答是問題設計造成的。\n"
            "- **建議**：放棄 5m Donchian 突破。若要繼續，換時間框架（1h 的 ATR% 約 0.5%，"
            "成本佔比低一個數量級、競爭密度低）—— 但那是另一個題目，且不保證可行。")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
