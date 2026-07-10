"""
範圍型參數編輯器（Optuna 模式用）

每個參數 = 1 行：
  [名稱 input] [型態 select] [低/選項 input] [高 input] [log checkbox] [刪除]

支援 4 種型態：
  - int:        整數範圍
  - float:      浮點數線性範圍
  - float_log:  浮點數對數範圍（適合跨數量級）
  - categorical:類別選項（low 欄位填入逗號分隔的選項）

輸出格式（Optuna 相容）：
  [
      {"name": "fast_period", "type": "int", "low": 5, "high": 50},
      {"name": "risk_pct", "type": "float_log", "low": 0.005, "high": 0.03},
      {"name": "ma_type", "type": "categorical", "choices": ["sma", "ema"]},
      {"name": "threshold", "type": "float", "low": 0.1, "high": 1.0},
  ]
"""
from __future__ import annotations

from typing import Dict, List, Any, Optional
import streamlit as st


# === 預設建議值（給 placeholder 提示用）===
PARAM_SUGGESTIONS_OPTUNA = {
    "fast_period": {"type": "int", "low": 5, "high": 50},
    "slow_period": {"type": "int", "low": 30, "high": 200},
    "ma_period": {"type": "int", "low": 10, "high": 100},
    "rsi_period": {"type": "int", "low": 7, "high": 28},
    "rsi_overbought": {"type": "int", "low": 65, "high": 85},
    "rsi_oversold": {"type": "int", "low": 15, "high": 35},
    "bb_period": {"type": "int", "low": 10, "high": 50},
    "num_std": {"type": "float", "low": 1.0, "high": 3.0},
    "fast": {"type": "int", "low": 5, "high": 20},
    "slow": {"type": "int", "low": 15, "high": 50},
    "signal": {"type": "int", "low": 5, "high": 20},
    "stop_loss": {"type": "float", "low": 0.005, "high": 0.1},
    "take_profit": {"type": "float", "low": 0.01, "high": 0.2},
    "commission": {"type": "float_log", "low": 0.0001, "high": 0.01},
    "slippage": {"type": "float_log", "low": 0.0001, "high": 0.005},
    "risk_pct": {"type": "float_log", "low": 0.005, "high": 0.03},
    "n": {"type": "int", "low": 5, "high": 30},
    "m1": {"type": "int", "low": 2, "high": 10},
    "m2": {"type": "int", "low": 2, "high": 10},
    "period": {"type": "int", "low": 10, "high": 100},
    "threshold": {"type": "float", "low": 0.1, "high": 1.0},
}


def _parse_choices(s: str) -> List[Any]:
    """解析 categorical 選項字串（如 'sma, ema, wma' → ['sma', 'ema', 'wma']）"""
    s = s.strip()
    if not s:
        return []
    parts = [p.strip() for p in s.split(",") if p.strip()]
    # 嘗試解析為數字
    result = []
    for p in parts:
        try:
            result.append(int(p))
            continue
        except ValueError:
            pass
        try:
            result.append(float(p))
            continue
        except ValueError:
            pass
        result.append(p)
    return result


def _parse_number(s: str) -> Optional[float]:
    """解析數字（支援 int / float）"""
    s = str(s).strip()
    if not s:
        return None
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


def render_param_space_editor(
    label: str = "參數空間",
    current_specs: Optional[List[Dict[str, Any]]] = None,
    key_prefix: str = "param_space",
    caption: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    渲染範圍型參數空間編輯器

    Args:
        label: 區塊標題
        current_specs: 預設 param_specs list
        key_prefix: session_state key 前綴
        caption: 說明文字

    Returns:
        List[Dict]: param_specs 列表
    """
    if current_specs is None:
        current_specs = []

    if caption:
        st.caption(caption)

    storage_key = f"{key_prefix}_storage"

    # 初始化
    if storage_key not in st.session_state:
        st.session_state[storage_key] = [s.copy() for s in current_specs]

    # 處理「新增」
    if st.session_state.pop(f"{key_prefix}_add_clicked", False):
        st.session_state[storage_key].append({
            "name": f"param_{len(st.session_state[storage_key]) + 1}",
            "type": "int",
            "low": 1,
            "high": 100,
        })
        st.rerun()

    # 渲染每一列
    specs = list(st.session_state[storage_key])
    indices_to_remove = []

    for i, spec in enumerate(specs):
        # 5 欄：名稱 / 型態 / 低 / 高 / 操作
        c1, c2, c3, c4, c5, c6 = st.columns([2, 1.5, 1.2, 1.2, 0.6, 0.6])

        with c1:
            placeholder = "參數名稱"
            if spec["name"] in PARAM_SUGGESTIONS_OPTUNA:
                placeholder = f"例: {spec['name']}（{PARAM_SUGGESTIONS_OPTUNA[spec['name']]['type']}）"
            new_name = st.text_input(
                "名稱",
                value=spec["name"],
                key=f"{key_prefix}_n_{i}",
                label_visibility="collapsed",
                placeholder=placeholder,
            )

        with c2:
            type_options = ["int", "float", "float_log", "categorical"]
            type_labels = {
                "int": "整數 (int)",
                "float": "浮點 (float)",
                "float_log": "浮點 對數 (log)",
                "categorical": "類別 (cat)",
            }
            cur_type = spec.get("type", "int")
            if cur_type not in type_options:
                cur_type = "int"
            new_type = st.selectbox(
                "型態",
                type_options,
                index=type_options.index(cur_type),
                key=f"{key_prefix}_t_{i}",
                label_visibility="collapsed",
                format_func=lambda t: type_labels.get(t, t),
            )

        with c3:
            if new_type == "categorical":
                # categorical：用逗號分隔的選項
                cur_choices = spec.get("choices", [])
                cur_str = ", ".join(str(c) for c in cur_choices)
                new_low = st.text_input(
                    "選項（逗號分隔）",
                    value=cur_str,
                    key=f"{key_prefix}_l_{i}",
                    label_visibility="collapsed",
                    placeholder="sma, ema, wma",
                )
            else:
                placeholder = "low"
                if spec["name"] in PARAM_SUGGESTIONS_OPTUNA:
                    placeholder = str(PARAM_SUGGESTIONS_OPTUNA[spec["name"]].get("low", "low"))
                cur_low = spec.get("low", 1)
                new_low_str = st.text_input(
                    "low",
                    value=str(cur_low),
                    key=f"{key_prefix}_l_{i}",
                    label_visibility="collapsed",
                    placeholder=placeholder,
                )
                new_low = _parse_number(new_low_str)

        with c4:
            if new_type == "categorical":
                st.caption("—")
            else:
                placeholder = "high"
                if spec["name"] in PARAM_SUGGESTIONS_OPTUNA:
                    placeholder = str(PARAM_SUGGESTIONS_OPTUNA[spec["name"]].get("high", "high"))
                cur_high = spec.get("high", 100)
                new_high_str = st.text_input(
                    "high",
                    value=str(cur_high),
                    key=f"{key_prefix}_h_{i}",
                    label_visibility="collapsed",
                    placeholder=placeholder,
                )
                new_high = _parse_number(new_high_str)

        with c5:
            if new_type == "float_log":
                st.caption("📈 log")
            elif new_type == "float":
                st.caption("📏 lin")
            elif new_type == "int":
                st.caption("🔢 int")
            elif new_type == "categorical":
                st.caption("🏷️ cat")

        with c6:
            if st.button("✕", key=f"{key_prefix}_del_{i}", help=f"刪除 {spec['name']}"):
                indices_to_remove.append(i)

        # 即時更新到 storage
        updated_spec = spec.copy()
        if new_name.strip():
            updated_spec["name"] = new_name.strip()
        else:
            updated_spec["name"] = f"param_{i+1}"

        updated_spec["type"] = new_type

        if new_type == "categorical":
            if isinstance(new_low, str):
                updated_spec["choices"] = _parse_choices(new_low)
                updated_spec.pop("low", None)
                updated_spec.pop("high", None)
        else:
            if new_low is not None:
                updated_spec["low"] = new_low
            if new_high is not None:
                updated_spec["high"] = new_high
            updated_spec.pop("choices", None)

        st.session_state[storage_key][i] = updated_spec

    # 刪除
    if indices_to_remove:
        for idx in sorted(indices_to_remove, reverse=True):
            if idx < len(st.session_state[storage_key]):
                st.session_state[storage_key].pop(idx)
        st.rerun()

    # 新增按鈕
    if st.button("➕ 新增參數", key=f"{key_prefix}_add"):
        st.session_state[f"{key_prefix}_add_clicked"] = True
        st.rerun()

    return [s for s in st.session_state[storage_key] if s.get("name")]


def specs_to_param_space_dict(specs: List[Dict[str, Any]]) -> Dict[str, List]:
    """
    把 param_specs 轉成舊版 param_space（給 Grid Search 用）

    範例：
        [{"name": "fast", "type": "int", "low": 5, "high": 30}]
        → {"fast": [5, 8, 11, 14, 17, 20, 23, 26, 30]}
    """
    result = {}
    for spec in specs:
        name = spec["name"]
        ptype = spec.get("type", "int")
        if ptype == "int":
            low, high = int(spec["low"]), int(spec["high"])
            step = max(1, (high - low) // 10) if high > low else 1
            result[name] = list(range(low, high + 1, step))
        elif ptype in ("float", "float_log", "loguniform"):
            low, high = float(spec["low"]), float(spec["high"])
            n = 10
            if ptype in ("float_log", "loguniform"):
                result[name] = list(np_logspace(low, high, n))
            else:
                result[name] = list(np_linspace(low, high, n))
        elif ptype == "categorical":
            result[name] = list(spec.get("choices", []))
    return result


def np_linspace(start, stop, num):
    import numpy as np
    return np.linspace(start, stop, num).tolist()


def np_logspace(start, stop, num):
    import numpy as np
    if start <= 0 or stop <= 0:
        return np_linspace(start, stop, num)
    return np.logspace(np.log10(start), np.log10(stop), num).tolist()


def get_default_specs_for_strategy(strategy_name: str) -> List[Dict[str, Any]]:
    """根據策略名稱取得預設 param_specs"""
    from strategies.strategy_runner import get_param_space
    grid_space = get_param_space(strategy_name)
    specs = []
    for name, values in grid_space.items():
        if not values:
            continue
        # 判斷型態
        if all(isinstance(v, int) for v in values):
            spec = {"name": name, "type": "int", "low": min(values), "high": max(values)}
        elif all(isinstance(v, float) for v in values):
            spec = {"name": name, "type": "float", "low": min(values), "high": max(values)}
        else:
            spec = {"name": name, "type": "categorical", "choices": list(values)}
        specs.append(spec)
    return specs


__all__ = [
    "render_param_space_editor",
    "specs_to_param_space_dict",
    "get_default_specs_for_strategy",
    "PARAM_SUGGESTIONS_OPTUNA",
]
