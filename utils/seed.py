"""
隨機種子管理模組

確保所有隨機行為可重現：numpy, random, optuna, strategy 內部隨機
"""
from __future__ import annotations

import os
import random
import numpy as np
from contextlib import contextmanager
from typing import Optional


# 全域當前種子
CURRENT_SEED = 42


def set_global_seed(seed: int = 42) -> int:
    """
    設定全域隨機種子，確保實驗可重現

    Returns:
        設定的種子值
    """
    global CURRENT_SEED
    CURRENT_SEED = int(seed)

    # Python 內建 random
    random.seed(CURRENT_SEED)

    # NumPy
    np.random.seed(CURRENT_SEED)

    # 嘗試設定其他常見的隨機源
    try:
        import torch
        torch.manual_seed(CURRENT_SEED)
    except ImportError:
        pass

    # PYTHONHASHSEED
    os.environ["PYTHONHASHSEED"] = str(CURRENT_SEED)

    return CURRENT_SEED


def get_seed() -> int:
    """取得當前全域種子"""
    return CURRENT_SEED


@contextmanager
def temporary_seed(seed: int):
    """
    臨時改變種子（with 區塊結束後自動還原）

    用法:
        with temporary_seed(123):
            result = do_random_thing()
    """
    global CURRENT_SEED
    old_seed = CURRENT_SEED
    set_global_seed(seed)
    try:
        yield seed
    finally:
        set_global_seed(old_seed)


def seed_for_trial(trial_number: int, base_seed: Optional[int] = None) -> int:
    """
    為特定 trial 產生獨立種子

    Args:
        trial_number: Optuna trial 編號
        base_seed: 基礎種子（None = 用全域）

    Returns:
        該 trial 的種子
    """
    if base_seed is None:
        base_seed = CURRENT_SEED
    return (base_seed * 1000003 + trial_number) % (2**31 - 1)


__all__ = [
    "set_global_seed",
    "get_seed",
    "temporary_seed",
    "seed_for_trial",
    "CURRENT_SEED",
]
