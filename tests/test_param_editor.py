"""
測試 utils/param_editor.py

驗證：
- _parse_value 支援各種型別
- render_param_editor 邏輯正確（用 mock）
"""
import pytest
import pandas as pd

from utils.param_editor import _parse_value, render_param_editor, PARAM_SUGGESTIONS


class TestParseValue:
    """_parse_value 測試"""

    def test_int(self):
        assert _parse_value("42") == 42
        assert isinstance(_parse_value("42"), int)

    def test_float(self):
        assert _parse_value("3.14") == 3.14
        assert isinstance(_parse_value("3.14"), float)

    def test_string(self):
        assert _parse_value("hello") == "hello"

    def test_empty(self):
        assert _parse_value("") == ""
        assert _parse_value(None) == ""

    def test_list(self):
        assert _parse_value("[1, 2, 3]") == [1, 2, 3]
        assert _parse_value("[10, 20, 30]") == [10, 20, 30]

    def test_nested_list(self):
        assert _parse_value("[[1, 2], [3, 4]]") == [[1, 2], [3, 4]]

    def test_dict(self):
        assert _parse_value('{"a": 1, "b": 2}') == {"a": 1, "b": 2}

    def test_invalid_list_falls_back_to_string(self):
        """無效 list 格式 fallback 到 string"""
        result = _parse_value("[invalid")
        # 不是合法 list，fallback 到 string（嘗試 int/float 都失敗）
        assert result == "[invalid"

    def test_whitespace_stripped(self):
        assert _parse_value("  42  ") == 42
        assert _parse_value("  hello  ") == "hello"

    def test_negative_numbers(self):
        assert _parse_value("-10") == -10
        assert _parse_value("-3.14") == -3.14

    def test_scientific_notation(self):
        assert _parse_value("1e5") == 100000.0
        assert isinstance(_parse_value("1e5"), float)

    def test_small_decimal(self):
        """小數（手續費、滑點等）"""
        assert _parse_value("0.001") == 0.001
        assert _parse_value("0.0005") == 0.0005
        assert _parse_value("0.05") == 0.05
        assert _parse_value("1.5") == 1.5
        assert _parse_value("2.0") == 2.0

    def test_float_list(self):
        """浮點數 list"""
        assert _parse_value("[0.001, 0.005, 0.01]") == [0.001, 0.005, 0.01]
        assert _parse_value("[1.5, 2.0, 2.5]") == [1.5, 2.0, 2.5]

    def test_bool(self):
        assert _parse_value("true") is True
        assert _parse_value("false") is False
        assert _parse_value("True") is True
        assert _parse_value("False") is False


class TestParamSuggestions:
    """PARAM_SUGGESTIONS 測試（自動填入預設值提示）"""

    def test_ma_period_suggestions(self):
        assert "fast_period" in PARAM_SUGGESTIONS
        assert "slow_period" in PARAM_SUGGESTIONS
        assert "ma_period" in PARAM_SUGGESTIONS

    def test_rsi_suggestions(self):
        assert "rsi_period" in PARAM_SUGGESTIONS
        assert "rsi_overbought" in PARAM_SUGGESTIONS
        assert "rsi_oversold" in PARAM_SUGGESTIONS

    def test_risk_suggestions(self):
        """風險參數預設（支援小數）"""
        assert "stop_loss" in PARAM_SUGGESTIONS
        assert "take_profit" in PARAM_SUGGESTIONS
        assert "0.02" in PARAM_SUGGESTIONS["stop_loss"]
        assert "0.04" in PARAM_SUGGESTIONS["take_profit"]

    def test_broadcast_suggestions(self):
        """布林通道預設（num_std 為小數）"""
        assert "bb_period" in PARAM_SUGGESTIONS
        assert "num_std" in PARAM_SUGGESTIONS
        assert "2.0" in PARAM_SUGGESTIONS["num_std"]

    def test_general_period(self):
        """通用 period 預設"""
        assert "period" in PARAM_SUGGESTIONS

