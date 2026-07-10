"""
參數編輯器 - 簡潔 Row layout（Notion 風格）

每行：[名稱 input] [值 input] [🗑 刪除]
底部：[➕ 新增參數]

純 session_state 實作，無 data_editor 內建工具列
"""
from __future__ import annotations

from typing import Dict, Any, Optional
import streamlit as st


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

    # 處理「刪除」
    delete_key_to_remove = st.session_state.pop(f"{key_prefix}_to_delete", None)
    if delete_key_to_remove and delete_key_to_remove in st.session_state[storage_key]:
        del st.session_state[storage_key][delete_key_to_remove]
        st.rerun()

    # 渲染每一列
    params = dict(st.session_state[storage_key])
    keys_to_remove = []

    for i, key in enumerate(list(params.keys())):
        col1, col2, col3 = st.columns([2, 2, 0.3])
        with col1:
            new_key = st.text_input(
                "名稱",
                value=key,
                key=f"{key_prefix}_n_{key}",
                label_visibility="collapsed",
                placeholder="參數名稱",
            )
        with col2:
            value_str = st.text_input(
                "值",
                value=str(params[key]),
                key=f"{key_prefix}_v_{key}",
                label_visibility="collapsed",
                placeholder="參數值",
            )
        with col3:
            if st.button("🗑", key=f"{key_prefix}_del_{key}", help=f"刪除 {key}"):
                st.session_state[f"{key_prefix}_to_delete"] = key
                st.rerun()

        # 即時更新
        new_key_clean = new_key.strip()
        if new_key_clean:
            if new_key_clean != key:
                # key 改了，刪舊的
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
    """解析輸入值"""
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
        return float(s)
    except ValueError:
        pass
    return s
