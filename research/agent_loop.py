"""
agent_loop.py — 自動策略演化循環 (用戶指定 5 步流程)
1. 策略生成: LLM 讀因子庫 → 輸出 JSON 交易邏輯假設
2. 程式碼轉譯: Parser 讀 JSON → 生成 Python 回測腳本 (StrategyBase 子類)
3. 回測執行: 命令列呼叫 optimize_local.py
4. 條件過濾: IS Sharpe>1.5 且 MaxDD<20% 且 OOS Sharpe>0 → 未達標回傳 LLM 修正
5. 儲存與叠代: 合格寫入 backtest_history + 觸發下一輪變異 (mutate params)
單輪 <10min。終端機執行: python3 research/agent_loop.py [--rounds N] [--symbol BTC_USDT] [--tf 1h] [--llm qwen|novita]

LLM providers:
- novita: meta-llama/llama-3.3-70b-instruct (key: NOVITA_API_KEY in /root/.hermes/.env)
- qwen: qwen3.7-max (key: 用戶提供, token-plan.ap-southeast-1.maas.aliyuncs.com)
"""
from __future__ import annotations
import os, sys, json, time, argparse, subprocess, textwrap, datetime, re
import urllib.request
import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# LLM providers
NOVITA_BASE = "https://api.novita.ai/openai"
NOVITA_MODEL = "meta-llama/llama-3.3-70b-instruct"
NOVITA_KEY_FILES = ["/root/.hermes/.env", "/root/.env"]

QWEN_BASE = "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
QWEN_KEY = "sk-sp-H.PDLP.Cang.MEUCIQD0Q-9KggKz03ksH3o9oylj_8XG_NKEH4pK2LoYuZwn5wIgB-GEaQIf-3wEKWKVB5w2C5sTicmPqCpl5UBTLuVRxQ4"

# Qwen token endpoint 可用文字模型 (2026-07-21 驗證)
QWEN_MODELS = [
    "qwen3.6-plus", "qwen3.6-flash", "qwen3.7-max", "qwen3.7-plus",
    "deepseek-v3.2", "deepseek-v4-flash", "deepseek-v4-pro",
    "glm-5", "glm-5.1", "glm-5.2",
    "kimi-k2.5", "kimi-k2.6", "kimi-k2.7-code", "MiniMax-M2.5",
]

THRESH_SHARPE = 1.5
THRESH_MAXDD = 20.0
SYMBOL_DEF = "BTC_USDT"
TF_DEF = "1h"

LLM_PROVIDER = "novita"  # runtime default; cron uses qwen


def _load_novita_key() -> str:
    import re
    for f in NOVITA_KEY_FILES:
        try:
            for line in open(f, encoding="utf-8", errors="ignore"):
                m = re.match(r"^NOVITA_API_KEY\s*=\s*['\"]?([A-Za-z0-9_\-]+)", line.strip())
                if m:
                    return m.group(1)
        except Exception:
            continue
    return os.environ.get("NOVITA_API_KEY", "")


def llm_chat(system: str, user: str, max_tokens: int = 1500, provider: str = None) -> str:
    """provider: 'novita' | 'qwen' | 具體模型名 (qwen3.7-max, deepseek-v4-pro, glm-5 ...)
    若傳具體模型名且屬於 QWEN_MODELS，自動走 Qwen endpoint。"""
    provider = provider or LLM_PROVIDER
    if provider in QWEN_MODELS:
        base, model, key = QWEN_BASE, provider, QWEN_KEY
    elif provider == "qwen":
        base, model, key = QWEN_BASE, "qwen3.7-max", QWEN_KEY
    elif provider in ("novita", "meta-llama/llama-3.3-70b-instruct"):
        base, model, key = NOVITA_BASE, NOVITA_MODEL, _load_novita_key()
    else:
        # 未知但嘗試當 novita (容錯)
        base, model, key = NOVITA_BASE, provider, _load_novita_key()
    if not key:
        raise RuntimeError(f"{provider} API key 未找到")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.8,
    }
    resp = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def step1_generate(round_n: int, feedback: str | None, factor_cols: list[str], provider: str = "novita") -> dict:
    """LLM 讀因子清單 + 統計摘要 → JSON 交易邏輯假設 (指定具體因子)"""
    factor_hint = (
        f"可用因子 (pandas_ta 單標的時間序列, 274 總數, 穩定子集 {len(factor_cols)} 個):\n"
        f"{', '.join(factor_cols[:40])}\n"
        "策略必須選用上述因子名 (如 'rsi','atr','MACD_12_26_9','BBANDS' 等), "
        "並指定 entry/exit 的數值閾值。"
    )
    system = (
        "你是一個量化策略設計師。輸出嚴格 JSON (不要 markdown 代碼塊), 包含:\n"
        "{\"name\": str, \"logic\": str, \"factor\": str (選一個因子名), "
        "\"entry_rule\": str (如 'rsi < 30'), \"exit_rule\": str (如 'rsi > 70'), "
        "\"params\": {\"n\": 14}, \"rationale\": str}\n"
        "factor 必須是給定清單中的一個。只輸出 JSON。"
    )
    user = f"第 {round_n} 輪策略生成。{factor_hint}\n"
    if feedback:
        user += f"\n上一輪失敗日誌 (請修正):\n{feedback}\n"
    user += "\n請生成一個新的交易邏輯假設 (JSON)，指定一個具體因子與閾值。"
    raw = llm_chat(system, user, provider=provider)
    try:
        j = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
    except Exception:
        j = {"name": f"llm_round{round_n}", "logic": raw[:200], "factor": "rsi",
             "entry_rule": "rsi<30", "exit_rule": "rsi>70", "params": {"n": 14}, "rationale": "fallback"}
    # 確保 factor 在清單內, 否則 fallback rsi
    if j.get("factor") not in factor_cols:
        j["factor"] = "rsi"
    return j


def _build_factor_expr(factor: str) -> tuple[str, str]:
    """把因子名映射到 pandas_ta 呼叫 + 取最後值的方式。
    回傳 (init計算代碼片段, next取值代碼片段)"""
    f = factor.lower()
    # 特殊處理常見因子 (pandas_ta 調用方式)
    if f == "rsi":
        init = (
            "delta = self._df['close'].diff()\n"
            "gain = delta.clip(lower=0).rolling(self.n).mean()\n"
            "loss = (-delta.clip(upper=0)).rolling(self.n).mean()\n"
            "rs = gain / (loss + 1e-9)\n"
            "self._f = 100 - 100 / (1 + rs)"
        )
        get = "val = self._f.iloc[self._i - 1] if self._i - 1 < len(self._f) else None"
    elif f in ("atr", "natr"):
        init = "self._f = self._df.ta.atr(length=self.n)"
        get = "val = self._f.iloc[self._i - 1] if self._i - 1 < len(self._f) else None"
    elif f.startswith("macd"):
        init = "self._f = self._df.ta.macd(length=self.n).iloc[:, 0]"
        get = "val = self._f.iloc[self._i - 1] if self._i - 1 < len(self._f) else None"
    elif f.startswith("bbands") or f == "bbands":
        init = "self._f = self._df.ta.bbands(length=self.n).iloc[:, 0]"
        get = "val = self._f.iloc[self._i - 1] if self._i - 1 < len(self._f) else None"
    elif f in ("adx", "adxr_14_2", "adxr"):
        init = "self._f = self._df.ta.adx(length=self.n).iloc[:, 0]"
        get = "val = self._f.iloc[self._i - 1] if self._i - 1 < len(self._f) else None"
    elif f == "cci":
        init = "self._f = self._df.ta.cci(length=self.n)"
        get = "val = self._f.iloc[self._i - 1] if self._i - 1 < len(self._f) else None"
    elif f == "willr":
        init = "self._f = self._df.ta.willr(length=self.n)"
        get = "val = self._f.iloc[self._i - 1] if self._i - 1 < len(self._f) else None"
    elif f == "roc" or f.startswith("roc"):
        init = "self._f = self._df.ta.roc(length=self.n)"
        get = "val = self._f.iloc[self._i - 1] if self._i - 1 < len(self._f) else None"
    elif f == "mom" or f.startswith("mom"):
        init = "self._f = self._df['close'].diff(self.n)"
        get = "val = self._f.iloc[self._i - 1] if self._i - 1 < len(self._f) else None"
    elif f == "obv" or f == "obv_min_2" or f == "obv_max_2":
        init = "self._f = self._df.ta.obv()"
        get = "val = self._f.iloc[self._i - 1] if self._i - 1 < len(self._f) else None"
    else:
        # 通用 fallback: 嘗試 df.ta.<factor>(); 若無則用 close rolling
        init = (
            "try:\n"
            "    self._f = self._df.ta." + f + "(length=self.n) if hasattr(self._df.ta, '" + f + "') else self._df['close'].rolling(self.n).mean()\n"
            "except Exception:\n"
            "    self._f = self._df['close'].rolling(self.n).mean()"
        )
        get = "val = self._f.iloc[self._i] if hasattr(self, '_f') and self._i < len(self._f) else None"
    return init, get


def step2_translate(spec: dict) -> str:
    """Parser 讀 JSON → 生成 StrategyBase 子類 (真因子預計算 + 逐根取用)"""
    name = spec.get("name", "agent_strat")
    safe = f"r{int(time.time()) % 100000}_{abs(hash(name)) % 100000:05d}"
    factor = spec.get("factor", "rsi")
    entry = spec.get("entry_rule", "val < 30")
    exit_ = spec.get("exit_rule", "val > 70")
    init_code, get_code = _build_factor_expr(factor)
    cls = '''# AUTO-GENERATED by agent_loop.py round __TS__
from __future__ import annotations
from typing import Any, Optional
import numpy as np
import pandas as pd
from strategies.base import Bar, Signal, StrategyBase

def _rsi_series(x: pd.Series) -> float:
    delta = x.diff()
    gain = delta.clip(lower=0).sum()
    loss = (-delta.clip(upper=0)).sum()
    rs = gain / (loss + 1e-9)
    return 100 - 100 / (1 + rs)

class __SAFE__(StrategyBase):
    name = "agent___SAFE__"
    description = "__DESC__"
    category = "agent"

    def init(self, params: dict[str, Any]) -> None:
        super().__init__()
        self.n = int(params.get("n", 14))
        self._pos = 0
        self._i = 0
        self._bars: list[Bar] = []
        self._df = pd.DataFrame()
        self._f = None

    def next(self, bar: Bar) -> Optional[Signal]:
        self._bars.append(bar)
        self._i += 1
        if len(self._bars) < self.n + 2:
            return None
        # 每根用累積歷史重算因子 (向量化, 只用歷史無泄漏)
        self._df = pd.DataFrame({
            "close": [b.close for b in self._bars],
            "high": [b.high for b in self._bars],
            "low": [b.low for b in self._bars],
            "volume": [b.volume for b in self._bars],
        })
        try:
__INIT_CODE__
__GET_CODE__
            __FACTOR_VAR__ = val
        except Exception:
            return None
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        # entry: __ENTRY__
        # exit: __EXIT__
        try:
            if (__ENTRY__) and self._pos == 0:
                self._pos = 1
                return Signal(action="buy", price=bar.close)
            if (__EXIT__) and self._pos == 1:
                self._pos = 0
                return Signal(action="close")
        except Exception:
            return None
        return None

    def get_params_space(self) -> dict[str, Any]:
        return {"n": {"type": "range", "min": 5, "max": 50, "step": 1}}

    def warmup_period(self) -> int:
        return self.n + 2
'''
    # init_code/get_code 是頂格代碼塊 (在 try: 下需 12 空格縮排)
    init_indented = "\n".join("            " + ln if ln.strip() else ln for ln in init_code.split("\n"))
    get_indented = "\n".join("            " + ln if ln.strip() else ln for ln in get_code.split("\n"))
    # entry/exit 裡的因子名映射成 val (LLM 用 factor 名, 代碼用 val)
    factor_var = factor.lower()
    cls = (cls
           .replace("__TS__", datetime.datetime.now().isoformat())
           .replace("__SAFE__", safe)
           .replace("__DESC__", spec.get("rationale", "auto")[:80])
           .replace("__INIT_CODE__", init_indented)
           .replace("__GET_CODE__", get_indented)
           .replace("__FACTOR_VAR__", factor_var)
           .replace("__ENTRY__", entry)
           .replace("__EXIT__", exit_))
    path = os.path.join(ROOT, "strategies", "technical", f"agent_{safe}.py")
    with open(path, "w") as f:
        f.write(cls)
    return path


def step3_backtest(py_path: str, symbol: str, tf: str) -> dict:
    """呼叫 optimize_local.py 回測"""
    csv = os.path.join(ROOT, "data", "csv", f"{symbol}_{tf}.csv")
    if not os.path.exists(csv):
        return {"error": f"CSV missing {csv}"}
    env = dict(os.environ, NO_PUSH="1")
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, "research/optimize_local.py", py_path, csv, "3", "300"],
        cwd=ROOT, capture_output=True, text=True, env=env, timeout=600,
    )
    elapsed = time.time() - t0
    # 讀最新 opt json
    import glob
    # 必須按「修改時間」取最新，而非檔名字典序——否則會讀到歷史舊檔
    # （曾導致每輪都讀到同一份陳舊 opt json，誤判全部未達標）。
    files = sorted(
        glob.glob(os.path.join(ROOT, "backtest_history", "opt_*.json")),
        key=os.path.getmtime,
    )
    res = {}
    if files:
        try:
            res = json.load(open(files[-1]))
        except Exception:
            pass
    res["_elapsed"] = round(elapsed, 1)
    res["_returncode"] = r.returncode
    if r.returncode != 0:
        res["_stderr"] = r.stderr[-1500:]
    return res


def step4_filter(res: dict) -> tuple[bool, str]:
    """雙重過濾: IS Sharpe>1.5 且 MaxDD<20% 且 OOS Sharpe>0 (防過擬合)"""
    if res.get("error") or res.get("_returncode", 0) != 0:
        return False, f"回測失敗: {res.get('error') or res.get('_stderr','')[:800]}"
    fb = res.get("full_backtest", {})
    wf = res.get("walk_forward", {})
    sharpe = fb.get("sharpe", 0) or 0
    mdd = fb.get("max_drawdown_pct", 100) or 100
    oos = wf.get("avg_oos_sharpe", -999) or -999
    # IS 達標 + OOS 正 (樣本外不失效)
    if sharpe > THRESH_SHARPE and mdd < THRESH_MAXDD and oos > 0:
        return True, f"PASS IS_sharpe={sharpe:.2f} mdd={mdd:.1f}% OOS_sharpe={oos:.2f}"
    reasons = []
    if sharpe <= THRESH_SHARPE:
        reasons.append(f"IS_sharpe={sharpe:.2f}(需>{THRESH_SHARPE})")
    if mdd >= THRESH_MAXDD:
        reasons.append(f"mdd={mdd:.1f}%(需<{THRESH_MAXDD})")
    if oos <= 0:
        reasons.append(f"OOS_sharpe={oos:.2f}(需>0,過擬合)")
    return False, "未達標: " + " | ".join(reasons)


def step5_store(spec: dict, res: dict, passed: bool, symbol: str, tf: str):
    """合格寫入 db (標記 agent_pass)"""
    if not passed:
        return
    log = os.path.join(ROOT, "research", "agent_passed.jsonl")
    with open(log, "a") as f:
        f.write(json.dumps({
            "name": spec.get("name"),
            "symbol": symbol, "tf": tf,
            "sharpe": res.get("full_backtest", {}).get("sharpe"),
            "mdd": res.get("full_backtest", {}).get("max_drawdown_pct"),
            "oos_sharpe": res.get("walk_forward", {}).get("avg_oos_sharpe"),
            "ts": datetime.datetime.now().isoformat(),
        }, ensure_ascii=False) + "\n")
    print(f"  [stored] {spec.get('name')} → research/agent_passed.jsonl")


def mutate(spec: dict, feedback: str) -> dict:
    """下一輪變異: 把失敗日誌回傳 LLM 修正 params/logic"""
    return spec  # step1_generate 會吃 feedback 重新生成


def _load_factor_cols(symbol: str, tf: str) -> list[str]:
    """從 factor_lib parquet 抽穩定因子列名 (給 LLM 精確清單)"""
    import pandas as pd
    p = os.path.join(ROOT, "factor_lib", "pandas_ta_features", f"{symbol}_{tf}.parquet")
    if not os.path.exists(p):
        return ["rsi", "atr", "macd", "bbands", "cci", "willr", "adx", "roc", "mom", "obv"]
    try:
        df = pd.read_parquet(p)
        cols = [c for c in df.columns if c not in ("timestamp", "open", "high", "low", "close", "volume")]
        # 優先穩定子集
        stable = [c for c in cols if any(k in c.upper() for k in
                  ["RSI", "ATR", "BBANDS", "MACD", "SMA", "EMA", "ADX", "CCI", "ROC", "MOM",
                   "WILLR", "STOCH", "OBV", "VWAP", "ZSCORE", "LOG"])]
        return stable[:40] if stable else cols[:40]
    except Exception:
        return ["rsi", "atr", "macd", "bbands", "cci"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--symbol", default=SYMBOL_DEF)
    ap.add_argument("--tf", default=TF_DEF)
    ap.add_argument("--llm", default="novita",
                    help=f"novita | qwen | 具體模型名 (可用: {', '.join(QWEN_MODELS)})")
    args = ap.parse_args()

    factor_cols = _load_factor_cols(args.symbol, args.tf)
    print(f"=== agent_loop start: {args.rounds} rounds, {args.symbol} {args.tf}, llm={args.llm} ===")
    print(f"  factor pool: {len(factor_cols)} factors from factor_lib")
    feedback = None
    for i in range(1, args.rounds + 1):
        t0 = time.time()
        print(f"\n--- ROUND {i} ({time.time()-t0:.0f}s) ---")
        # 1. 生成
        spec = step1_generate(i, feedback, factor_cols, provider=args.llm)
        print(f"  [1] LLM spec: {spec.get('name')} | factor={spec.get('factor')} | {spec.get('rationale','')[:40]}")
        # 2. 轉譯
        py = step2_translate(spec)
        print(f"  [2] generated: {os.path.basename(py)}")
        # 3. 回測
        res = step3_backtest(py, args.symbol, args.tf)
        print(f"  [3] backtest: {res.get('_elapsed','?')}s rc={res.get('_returncode')}")
        # 4. 過濾
        passed, msg = step4_filter(res)
        print(f"  [4] filter: {msg}")
        # 5. 儲存
        step5_store(spec, res, passed, args.symbol, args.tf)
        feedback = msg if not passed else None
        print(f"  round {i} done in {time.time()-t0:.0f}s")
    print("=== agent_loop complete ===")


if __name__ == "__main__":
    main()
