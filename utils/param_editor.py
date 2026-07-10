"""
參數編輯器元件

以 Row layout 顯示參數：
- 左：參數名稱
- 右：可編輯輸入框
- 支援新增/刪除參數
- 維持 session_state 同步

用 st.data_editor 實作（內建新增/刪除 row 功能）
"""
from __future__ import annotations

from typing import Dict, Any, List
import pandas as pd
import streamlit as st


def render_param_editor(
    label: str,
    current_params: Dict[str, Any],
    key_prefix: str,
    caption: str = "",
    value_types: List[str] = None,
) -> Dict[str, Any]:
    """
    渲染參數編輯器（Row layout）

    Args:
        label: 區塊標題
        current_params: 當前參數 dict
        key_prefix: session_state key 前綴
        caption: 說明文字
        value_types: 可選的 value 類型清單 ["int", "float", "string"]

    Returns:
        更新後的 params dict
    """
    if value_types is None:
        value_types = ["float", "int", "string"]

    if caption:
        st.caption(caption)

    # 初始化 session_state
    storage_key = f"{key_prefix}_params"
    if storage_key not in st.session_state:
        st.session_state[storage_key] = current_params.copy()

    # 同步 current_params → storage（保留用戶編輯）
    if current_params and not st.session_state[storage_key]:
        st.session_state[storage_key] = current_params.copy()

    params = st.session_state[storage_key]

    # 轉成 DataFrame 給 data_editor
    # 注意：data_editor 的整個 column 必須統一 type，所以值用 string 表示
    if params:
        df = pd.DataFrame([
            {"參數名稱": k, "參數值": str(v)} for k, v in params.items()
        ])
    else:
        df = pd.DataFrame(columns=["參數名稱", "參數值"])

    # 用 st.data_editor 編輯
    edited_df = st.data_editor(
        df,
        key=f"{key_prefix}_editor",
        num_rows="dynamic",  # 允許新增/刪除 row
        column_config={
            "參數名稱": st.column_config.TextColumn(
                "參數名稱",
                required=True,
                width="medium",
            ),
            "參數值": st.column_config.TextColumn(
                "參數值",
                required=True,
                width="medium",
                help="支援 int / float / string / list（如 [1, 2, 3]）",
            ),
        },
        use_container_width=True,
        hide_index=True,
    )

    # 把 DataFrame 轉回 dict
    if not edited_df.empty:
        result = {}
        for _, row in edited_df.iterrows():
            key = str(row["參數名稱"]).strip()
            if not key:
                continue
            value = _parse_value(row["參數值"])
            result[key] = value
        st.session_state[storage_key] = result
        return result
    else:
        st.session_state[storage_key] = {}
        return {}


def _parse_value(value: Any) -> Any:
    """
    解析輸入值（支援 int / float / string / list / dict）
    """
    if value is None or value == "":
        return ""

    s = str(value).strip()

    # 嘗試 eval（支援 list, dict）
    if s.startswith("[") and s.endswith("]"):
        try:
            import ast
            return ast.literal_eval(s)
        except (ValueError, SyntaxError):
            return s
    if s.startswith("{") and s.endswith("}"):
        try:
            import ast
            return ast.literal_eval(s)
        except (ValueError, SyntaxError):
            return s

    # 嘗試 int
    try:
        return int(s)
    except ValueError:
        pass

    # 嘗試 float
    try:
        return float(s)
    except ValueError:
        pass

    # 字串
    return s


def render_param_editor_advanced(
    label: str,
    current_params: Dict[str, Any],
    key_prefix: str,
    caption: str = "",
) -> Dict[str, Any]:
    """
    進階版：用 st.data_editor 直接編輯，支援型別自動推斷
    """
    if caption:
        st.caption(caption)

    # 初始化 session_state
    storage_key = f"{key_prefix}_params"
    if storage_key not in st.session_state:
        st.session_state[storage_key] = current_params.copy()

    params = st.session_state[storage_key]

    # 用 st.data_editor
    if params:
        rows = [{"參數名稱": k, "參數值": str(v), "說明": ""} for k, v in params.items()]
        df = pd.DataFrame(rows)
    else:
        df = pd.DataFrame(columns=["參數名稱", "參數值", "說明"])

    edited_df = st.data_editor(
        df,
        key=f"{key_prefix}_editor_v2",
        num_rows="dynamic",
        column_config={
            "參數名稱": st.column_config.TextColumn("參數名稱", required=True),
            "參數值": st.column_config.TextColumn("參數值", required=True),
            "說明": st.column_config.TextColumn("說明（選填）"),
        },
        use_container_width=True,
        hide_index=True,
    )

    if not edited_df.empty:
        result = {}
        for _, row in edited_df.iterrows():
            key = str(row["參數名稱"]).strip()
            if not key:
                continue
            value = _parse_value(row["參數值"])
            result[key] = value
        st.session_state[storage_key] = result
        return result
    else:
        st.session_state[storage_key] = {}
        return {}
