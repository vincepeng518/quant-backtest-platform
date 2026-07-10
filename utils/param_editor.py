"""
參數編輯器 - 簡潔 Row layout（Notion 風格）

每行：[名稱 input] [值 input]
底部：[➕ 新增參數]
支援型別自動推斷（int / float / string / list / bool）
"""
from __future__ import annotations

from typing import Dict, Any, Optional
import streamlit as st


# 預設建議值（讓用戶知道可用什麼值）
PARAM_SUGGESTIONS = {
    # 移動平均
    "fast_period": "[5, 10, 15, 20, 25, 30]",
    "slow_period": "[30, 40, 50, 60, 80, 100]",
    "ma_period": "[10, 20, 30, 50, 100]",
    # RSI
    "rsi_period": "[7, 14, 21, 28]",
    "rsi_overbought": "70",
    "rsi_oversold": "30",
    "entry_level": "30",
    "exit_level": "70",
    # 布林通道
    "bb_period": "[15, 20, 25, 30]",
    "num_std": "2.0",
    "std_multiplier": "1.5",
    # MACD
    "fast": "12",
    "slow": "26",
    "signal": "9",
    # 風控
    "stop_loss": "0.02",
    "take_profit": "0.04",
    "commission": "0.001",
    "slippage": "0.0005",
    # KDJ
    "n": "9",
    "m1": "3",
    "m2": "3",
    # 一般
    "period": "[10, 20, 30, 50, 100]",
    "threshold": "0.5",
}


def render_param_editor(
    label: str = "參數",
    current_params: Optional[Dict[str, Any]] = None,
    key_prefix: str = "params",
    caption: Optional[str] = None,
) -> Dict[str, Any]:
    """
    渲染簡潔 Row layout 參數編輯器

    Args:
        label: 區塊標題
        current_params: 預設參數
        key_prefix: session_state key 前綴
        caption: 說明文字

    Returns:
        更新後的 params dict
    """
    if current_params is None:
        current_params = {}

    if caption:
        st.caption(caption)

    storage_key = f"{key_prefix}_storage"

    # 初始化
    if storage_key not in st.session_state:
        st.session_state[storage_key] = current_params.copy()

    # 處理「新增」
    if st.session_state.pop(f"{key_prefix}_add_clicked", False):
        new_name = "param_1"
        counter = 1
        while new_name in st.session_state[storage_key]:
            counter += 1
            new_name = f"param_{counter}"
        st.session_state[storage_key][new_name] = 0
        st.rerun()

    # 渲染每一列（無刪除按鈕）
    params = dict(st.session_state[storage_key])
    keys_to_remove = []

    for i, key in enumerate(list(params.keys())):
        col1, col2 = st.columns([2, 3])
        with col1:
            new_key = st.text_input(
                "名稱",
                value=key,
                key=f"{key_prefix}_n_{key}",
                label_visibility="collapsed",
                placeholder="參數名稱",
            )
        with col2:
            # 預設值提示
            placeholder = PARAM_SUGGESTIONS.get(key, "支援 int / float / string / list")
            value_str = st.text_input(
                "值",
                value=str(params[key]),
                key=f"{key_prefix}_v_{key}",
                label_visibility="collapsed",
                placeholder=placeholder,
            )
        # 即時更新
        new_key_clean = new_key.strip()
        if new_key_clean:
            if new_key_clean != key:
                # key 改名
                if key in st.session_state[storage_key]:
                    old_value = st.session_state[storage_key].pop(key)
                st.session_state[storage_key][new_key_clean] = _parse_value(value_str)
            else:
                st.session_state[storage_key][new_key_clean] = _parse_value(value_str)
        else:
            # 空 key → 標記刪除
            if key in st.session_state[storage_key]:
                keys_to_remove.append(key)

    # 清理空 key
    for k in keys_to_remove:
        if k in st.session_state[storage_key]:
            del st.session_state[storage_key][k]

    # 「➕ 新增參數」按鈕
    if st.button("➕ 新增參數", key=f"{key_prefix}_add"):
        st.session_state[f"{key_prefix}_add_clicked"] = True
        st.rerun()

    return st.session_state[storage_key]


def _parse_value(value: Any) -> Any:
    """解析輸入值（支援 int / float / string / list / dict / bool）"""
    if value is None or value == "":
        return ""
    s = str(value).strip()
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
        try:
            import ast
            return ast.literal_eval(s)
        except (ValueError, SyntaxError):
            return s
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)  # 支援小數（0.001, 0.05, 1.5, 2.0 等）
    except ValueError:
        pass
    return s
