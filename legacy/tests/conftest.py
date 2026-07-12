"""
pytest 設定：確保從專案根目錄執行測試時能 import 模組
"""
import sys
import os

# 加入專案根目錄到 path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
