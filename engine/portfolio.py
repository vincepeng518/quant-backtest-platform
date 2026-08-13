"""
engine/portfolio.py — 多標的組合對沖回測 + 相關性矩陣驗證(組合計算模組)。

純新增模組,不碰單標的回測路徑(engine/backtester.py 等)。
輸入: 多標的 equity_curve(時間對齊)或日回報; 輸出: 組合權重建組合、相關性矩陣、對沖報告。

設計原則(AGENTS.md: 最簡實現 / 模組化 / 長遠架構):
- 組合的「可驗證數據」= 標的間回報的相關性矩陣(標的對沖價值)。
- 組合 PnL = 對齊後各標的 equity 依權重疊加 → 組合回報 → 風險指標。
- 「異常負值」防護: 組合 equity 有 NaN/inf/負權重 → 回報診斷。

核心時間配對:  各標的 equity 依 timestamp 對齊(inner join),確保組合在同一天跨標的。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import math


@dataclass
class PortfolioResult:
    """組合回測 + 相關性矩陣結果。"""
    symbols: List[str]
    correlation_matrix: Dict[str, Dict[str, float]]  # sym -> sym -> pearson 相關係數
    weights: Dict[str, float]
    portfolio_equity: List[float]          # 組合時間對齊後加權 equity
    portfolio_returns: List[float]         # 組合日回報
    timestamps: List[int]                  # 對齊後 index 的 ts(ms), 便於前端畫圖/驗證
    individual_metrics: Dict[str, dict] = field(default_factory=dict)  # 各單標的風險指標
    portfolio_metrics: dict = field(default_factory=dict)              # 組合風險指標
    hedge_report: dict = field(default_factory=dict)                   # 對沖價值報告
    errors: List[str] = field(default_factory=list)                    # 異常診斷(卡關回報用)


# ── 1. 回報計算 ──────────────────────────────────────────────
def compute_returns(equity: List[float]) -> List[float]:
    """equity 序列 → 起報酬率序列(len-1)。等長輸入防呆。"""
    if len(equity) < 2:
        return []
    out = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        if prev == 0 or not math.isfinite(prev) or not math.isfinite(equity[i]):
            out.append(0.0)  # 防 nan/0 除
        else:
            out.append(equity[i] / prev - 1.0)
    return out


# ── 2. Pearson 相關性矩陣 ────────────────────────────────────
def _pearson(a: List[float], b: List[float]) -> float:
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    a, b = a[:n], b[:n]
    ma = sum(a) / n
    mb = sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = math.sqrt(sum((x - ma) ** 2 for x in a))
    vb = math.sqrt(sum((y - mb) ** 2 for y in b))
    if va == 0 or vb == 0:
        return 0.0
    return cov / (va * vb)


def correlation_matrix(returns: Dict[str, List[float]]) -> Dict[str, Dict[str, float]]:
    """標的日回報 → {symA: {symB: pearson}}。對角=1。"""
    syms = list(returns.keys())
    m = {s: {t: (1.0 if s == t else round(_pearson(returns[s], returns[t]), 4)) for t in syms}
         for s in syms}
    return m


# ── 3. 權重歸一化 ────────────────────────────────────────────
def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """權重歸一化: 保留正負號(負=對沖空頭腿), 使 |權重| 總和=1。"""
    total = sum(abs(w) for w in weights.values())
    if total == 0:
        return {k: 1.0 / len(weights) for k in weights}
    return {k: w / total for k, w in weights.items()}


# ── 4. 風險指標(單標的 / 組合共用)────────────────────────────
def _metrics(returns: List[float], periods_per_year: int = 252) -> dict:
    n = len(returns)
    if n == 0:
        return {"sharpe": None, "volatility_annual": None, "total_return": 0.0, "max_drawdown": 0.0, "n": 0}
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1) if n > 1 else 0.0
    std = math.sqrt(var) if var > 0 else 0.0
    ann_vol = std * math.sqrt(periods_per_year)
    sharpe = (mean / std * math.sqrt(periods_per_year)) if std > 0 else (0.0 if mean else 0.0)
    # drawdown (從報酬模擬 equity)
    eq = 1.0
    peak = 1.0
    mdd = 0.0
    for r in returns:
        eq *= (1 + r)
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak)
    total_ret = 1.0
    for r in returns:
        total_ret *= (1 + r)
    return {
        "sharpe": round(sharpe, 3) if sharpe is not None else None,
        "volatility_annual": round(ann_vol, 4),
        "total_return": round(total_ret - 1.0, 4),
        "max_drawdown": round(mdd, 4),
        "n": n,
    }


# ── 5. 組合對沖主入口 ─────────────────────────────────────────
def run_portfolio(
    equity_by_symbol: Dict[str, List[float]],
    timestamps_by_symbol: Optional[Dict[str, List[Optional[int]]]] = None,
    weights: Optional[Dict[str, float]] = None,
) -> PortfolioResult:
    """
    equity_by_symbol: {sym: equity_curve}. 各標的 index i 對應同 timestamps(需先對齊)。
    timestamps_by_symbol: {sym: ts_ms[]}, 供對齊(若傳入則以此 intersection 對齊)。
    回傳 PortfolioResult,含相關性矩陣 + 組合指標 + 對沖報告。任何異常回報 errors 並保守返回。
    """
    symbols = list(equity_by_symbol.keys())
    if not symbols:
        return PortfolioResult(symbols=[], correlation_matrix={}, weights={},
                               portfolio_equity=[], portfolio_returns=[], timestamps=[],
                               errors=["no symbols"])

    # 時間對齊: 取各標的共有的 ts 子集(inner join)
    ts_index: Dict[str, Dict[int, int]] = {}  # sym -> {ts: idx}
    all_tss: List[int] = []
    if timestamps_by_symbol:
        for s in symbols:
            tss = timestamps_by_symbol.get(s, [])
            ts_index[s] = {int(t): i for i, t in enumerate(tss) if t is not None and t > 0}
        if ts_index:
            common = set.intersection(*[set(v.keys()) for v in ts_index.values()]) if len(ts_index) > 1 else set(next(iter(ts_index.values())).keys())
            all_tss = sorted(common)
        aligned: Dict[str, List[float]] = {}
        if all_tss:
            for s in symbols:
                aligned[s] = [equity_by_symbol[s][ts_index[s][t]] for t in all_tss]
        else:
            aligned = equity_by_symbol  # 無 timestamps → 假設已對齊
            all_tss = list(range(len(next(iter(equity_by_symbol.values())))))
    else:
        aligned = equity_by_symbol
        # 無 timestamps → 只支援等長; 不等長取最短
        minlen = min(len(v) for v in aligned.values())
        aligned = {s: v[:minlen] for s, v in aligned.items()}
        all_tss = list(range(minlen))

    # 異常防護: 任一標的 equity 含非有限值 → 回報卡關
    for s, eq in aligned.items():
        bad = [i for i, v in enumerate(eq) if not math.isfinite(v)]
        if bad:
            pf = PortfolioResult(symbols=symbols, correlation_matrix={}, weights=weights or {},
                                 portfolio_equity=[], portfolio_returns=[], timestamps=[],
                                 errors=[f"{s}: equity 含非有限值於 index {bad[:5]}"])
            return pf

    # ⚠️ 異常負值防護: 單標 equity 若 ≤0(標的爆倉/歸零), 截斷到 0(損失 100% 上緣),
    #   避免「負 equity」被帶入組合加權 → 組合被拉成異常負值/回撤>100%。
    #   記錄被 clip 的標的與點數到 warning(供「異常負值停下回報」)。
    warning_msgs: List[str] = []
    clip_warn = []
    for s, eq in aligned.items():
        le0 = [i for i, v in enumerate(eq) if v <= 0]
        if le0:
            clip_warn.append(f"{s}: 出現 ≤0 equity({len(le0)}/點) 已截斷為 0(爆倉防護)")
            aligned[s] = [v if v > 0 else 0.0 for v in eq]
    warning_msgs = warning_msgs + clip_warn

    # 權重(等權或給定), 負權重=對沖空頭腿, 記錄但不早退
    w = weights or {s: 1.0 / len(symbols) for s in symbols}
    for s in symbols:
        if s not in w:
            w[s] = 0.0
    norm_w = _normalize_weights(w)
    neg_w = {s: v for s, v in w.items() if v < 0}
    if neg_w:
        warning_msgs.append(f"權重含負值(對沖空頭): {neg_w} — 如非預期請回報")
    # 異常負值防護: 權重若造成組合 equity 任一非有限 → 直接卡關
    for s, eq in aligned.items():
        if any(not math.isfinite(norm_w.get(s, 0) * v) for v in eq):
            return PortfolioResult(symbols=symbols, correlation_matrix={}, weights=norm_w,
                                   portfolio_equity=[], portfolio_returns=[], timestamps=[],
                                   errors=warning_msgs + [f"{s}: 權重×equity 產生非有限值(權重{norm_w.get(s)})"])

    # 標的回報 + 相關性矩陣
    returns_by_sym = {s: compute_returns(aligned[s]) for s in symbols}
    corr = correlation_matrix(returns_by_sym)

    # ── 組合計算: 日回報空間加權(正確對沖)──
    # 各標的日回報 r_s, 組合日回報 = Σ w_s * r_s(每天), 再累乘成組合 equity。
    # 理由: 資產 equity 是乘性累積(×1+return), 組合加權必須在日回報空間做,
    #       否則「負相關資產同持」無法正確抵消(equity線性相加反而加倍暴露)。
    n_ret = min(len(returns_by_sym[s]) for s in symbols)  # 回報長度 = equity-1
    # norm_w 已在權重段(line 168)定義 = _normalize_weights(w)
    # 歸一化後權重和 Σ|w|=1; 但對沖要 Σ w = 1(總多頭基準)。用 Σw 歸一化皆可,
    # 此處用「權重和=1」做組合報酬基準(平多空類組合)。
    wsum = sum(norm_w.values())
    if wsum == 0:
        wsum = 1.0
    port_returns = [sum(norm_w[s] / wsum * returns_by_sym[s][i] for s in symbols) for i in range(n_ret)]
    # 組合 equity(從 100 起累乘)
    port_equity = [100.0]
    for r in port_returns:
        port_equity.append(port_equity[-1] * (1 + r))

    # 單標 + 組合指標
    ind_metrics = {s: _metrics(returns_by_sym[s]) for s in symbols}
    port_metrics = _metrics(port_returns)

    # 對沖報告: 組合 vs 最爛/最佳單標的波動比較 + 最大負相關對
    best_single_vol = min((m["volatility_annual"] for m in ind_metrics.values() if m["volatility_annual"] is not None), default=None)
    pair_corr = []
    syms = symbols
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            c = corr[syms[i]][syms[j]]
            pair_corr.append({"a": syms[i], "b": syms[j], "corr": c})
    neg_pairs = sorted([p for p in pair_corr if p["corr"] < 0], key=lambda x: x["corr"])
    vol_reduction = None
    if best_single_vol is not None and port_metrics["volatility_annual"] is not None:
        vol_reduction = round((best_single_vol - port_metrics["volatility_annual"]) / best_single_vol, 4) if best_single_vol else None

    pf = PortfolioResult(
        symbols=symbols,
        correlation_matrix=corr,
        weights=norm_w,
        portfolio_equity=port_equity,
        portfolio_returns=port_returns,
        timestamps=all_tss,
        individual_metrics=ind_metrics,
        portfolio_metrics=port_metrics,
        hedge_report={
            "best_single_volatility": best_single_vol,
            "portfolio_volatility": port_metrics["volatility_annual"],
            "portfolio_vol_reduction": vol_reduction,   # 組合相對最佳單標波動降幅(對沖價值)
            "negative_corr_pairs": neg_pairs,          # 負相關(對沖)標的對
            "avg_pair_corr": round(sum(p["corr"] for p in pair_corr) / len(pair_corr), 4) if pair_corr else None,
        },
        errors=warning_msgs,   # 含負權重警告(異常負值防護)
    )
    return pf
