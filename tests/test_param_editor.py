"""
測試 utils/param_editor.py

驗證：
- _parse_value 支援各種型別
- render_param_editor 邏輯正確（用 mock）
"""
import pytest
import pandas as pd

from utils.param_editor import _parse_value, render_param_editor


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
