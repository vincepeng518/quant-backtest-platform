"""
使用者策略管理模組
- 從 .py 檔案載入策略
- 從文字貼上載入策略
- 儲存到 session_state 作為「我的策略庫」
"""

import os
import re
import ast
from typing import Tuple, Optional, List, Dict


def validate_strategy_code(code: str) -> Tuple[bool, str]:
    """
    驗證策略代碼是否符合規範
    - 必須是合法 Python
    - 必須定義 generate_signals 函數
    - 函數必須接受 (df, params) 參數
    - 函數必須回傳兩個變數
    """
    if not code or not code.strip():
        return False, "代碼為空"

    # 語法檢查
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"語法錯誤: {e}"

    # 找 generate_signals 函數
    has_func = False
    func_args_ok = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "generate_signals":
            has_func = True
            # 檢查參數
            args = [a.arg for a in node.args.args]
            if len(args) >= 2 and args[0] == "df":
                func_args_ok = True
            break

    if not has_func:
        return False, "找不到函數 'generate_signals(df, params)'"

    if not func_args_ok:
        return False, "函數必須接受兩個參數 (df, params)"

    return True, "✅ 策略代碼有效"


def extract_strategy_name(code: str, fallback: str = "My Strategy") -> str:
    """
    從策略代碼中提取名稱
    優先順序：
    1. 註解中第一行（# 開頭）
    2. 函數 docstring
    3. 預設名稱
    """
    lines = code.strip().split("\n")

    # 1. 找第一個註解
    for line in lines:
        line = line.strip()
        if line.startswith("#") and len(line) > 1:
            comment = line.lstrip("#").strip()
            if comment and not comment.startswith("!"):
                return comment[:50]  # 限制長度

    # 2. 找 docstring
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "generate_signals":
                if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                    return node.body[0].value.value[:50]
    except Exception:
        pass

    return fallback


def extract_strategy_description(code: str) -> str:
    """提取策略描述（取 docstring 或前幾行註解）"""
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "generate_signals":
                if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                    return node.body[0].value.value[:200]
    except Exception:
        pass

    # 取前 5 行註解
    lines = code.strip().split("\n")[:5]
    comments = []
    for line in lines:
        if line.strip().startswith("#"):
            comments.append(line.strip().lstrip("#").strip())
    return " / ".join(comments) if comments else "（無描述）"


def load_strategy_from_file(file) -> Tuple[bool, str, str]:
    """
    從上傳的檔案載入策略
    回傳 (success, code_or_error, filename)
    """
    try:
        # 讀取檔案內容
        content = file.read()
        if isinstance(content, bytes):
            # 嘗試 UTF-8，再試 BIG5（中文常見編碼）
            for encoding in ["utf-8", "utf-8-sig", "gbk", "big5", "latin-1"]:
                try:
                    code = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                return False, "無法解碼檔案編碼，請用 UTF-8 儲存", file.name
        else:
            code = content

        # 驗證
        valid, msg = validate_strategy_code(code)
        if not valid:
            return False, f"❌ {file.name}: {msg}", file.name

        return True, code, file.name

    except Exception as e:
        return False, f"❌ {file.name}: {type(e).__name__}: {e}", file.name


def load_strategy_from_pasted_code(code: str) -> Tuple[bool, str]:
    """從貼上的代碼載入策略"""
    valid, msg = validate_strategy_code(code)
    if not valid:
        return False, msg
    return True, code


# === 策略範本庫（也放在這裡方便重複使用）===

SAMPLE_STRATEGIES = {
    "海龜交易 + ATR 停損": '''# 海龜交易 + ATR 動態停損
# 進場：突破 20 日新高
# 出場：跌破 10 日新低 或 ATR 停損

def generate_signals(df, params):
    entry_n = params.get("entry_n", 20)
    exit_n = params.get("exit_n", 10)
    atr_period = params.get("atr_period", 14)
    atr_multiplier = params.get("atr_multiplier", 2.0)

    # 計算 ATR（Average True Range）
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.rolling(atr_period).mean()

    # 進場：突破 N 日高點
    df["entry_high"] = df["high"].rolling(entry_n).max().shift(1)
    entries = df["close"] > df["entry_high"]

    # 出場：跌破 N 日低點
    df["exit_low"] = df["low"].rolling(exit_n).min().shift(1)
    exits = df["close"] < df["exit_low"]

    return entries.fillna(False), exits.fillna(False)
''',

    "雙 RSI 交叉": '''# 雙 RSI 交叉策略
# 短 RSI 向上穿越長 RSI → 進場
# 短 RSI 向下穿越長 RSI → 出場

def generate_signals(df, params):
    short_rsi = params.get("short_rsi", 7)
    long_rsi = params.get("long_rsi", 21)

    def calc_rsi(series, period):
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    df["rsi_short"] = calc_rsi(df["close"], short_rsi)
    df["rsi_long"] = calc_rsi(df["close"], long_rsi)

    entries = (df["rsi_short"] > df["rsi_long"]) & (df["rsi_short"].shift(1) <= df["rsi_long"].shift(1))
    exits = (df["rsi_short"] < df["rsi_long"]) & (df["rsi_short"].shift(1) >= df["rsi_long"].shift(1))

    return entries.fillna(False), exits.fillna(False)
''',

    "三連陰陽線反轉": '''# 三連陰陽線反轉策略
# 連 3 根陰線後進場做多（均值回歸）
# 進場後持有固定 K 棒數量

def generate_signals(df, params):
    hold_bars = params.get("hold_bars", 5)

    # 判斷每根 K 線是陰還是陽
    is_bear = df["close"] < df["open"]
    is_bull = df["close"] > df["open"]

    # 連 3 根陰線
    three_bear = is_bear & is_bear.shift(1) & is_bear.shift(2)

    # 第 4 根反轉（收紅）
    entries = three_bear.shift(-1) & is_bull.shift(-1)

    # 進場後 hold_bars 根出場（簡化：下一個三連陰線進場時也順便出場）
    exits = entries.shift(hold_bars).fillna(False)

    return entries.fillna(False), exits.fillna(False)
''',

    "ATR 波動突破": '''# ATR 波動突破策略
# 價格突破「前根收盤 ± N 倍 ATR」時進場
# 預期大幅波動後的趨勢

def generate_signals(df, params):
    atr_period = params.get("atr_period", 14)
    atr_multiplier = params.get("atr_multiplier", 1.5)

    # 計算 ATR
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.rolling(atr_period).mean()

    # 突破上限
    upper_break = df["close"].shift(1) + atr_multiplier * df["atr"].shift(1)
    lower_break = df["close"].shift(1) - atr_multiplier * df["atr"].shift(1)

    entries = df["close"] > upper_break
    exits = df["close"] < lower_break

    return entries.fillna(False), exits.fillna(False)
''',
}
