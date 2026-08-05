# AGENTS.md — Quant Backtest Platform

回測網站（量化回測平台）。後端 FastAPI + Next.js 前端。本檔規範所有 agent（Claude Code / Cursor / Hermes）在操作此 repo 時的行為。

## 工程原則（不變鐵律）

1. **不維持向下相容**：直接移除廢棄路徑，不新增相容層、退路或轉移機制。
2. **最簡實現**：滿足當前需求即可，避免過度推測的抽象、設定與間接引用。
3. **分層擴充**：從最小可執行版本開始，在可運作產品上疊加新功能，絕不拿現成可用產品換未完成的複雜度。
4. **模組化與職責分離**：組件保持模組化，清晰劃分關注點。
5. **優先成熟函式庫**：能降低總體複雜度或提升可靠性時優先採用，無明確理由不重造輪子。
6. **優先既有依賴**：自行撰寫或新增套件前，先使用專案已有依賴，查文件與型別前不假設函式庫缺功能。
7. **長遠架構**：拒絕僅適用當下、日後必被替換的權宜之計。

## 部署（最常見坑）

- **此 repo 不會從 GitHub 自動部署**。`git push` 後必須手動：
  ```bash
  railway link -p quant-backend -e production
  railway up --detach
  ```
  後端 service = `affectionate-alignment`（production）。記憶的 URL：`affectionate-alignment-production-6d7e.up.railway.app`。
- **「push 了但行為沒變」= 忘了 `railway up`**，不是代碼問題。
- railway up 後用 `railway status` 確認 deployment ID 更新、狀態不再「Building/Queued」。

## 測試

- 後端測試在 `tests_backend/`，跑 `python3 -m pytest tests_backend/`。
- 改動引擎/API 必須先跑相關測試再部署，確認無 regression。
- 服務器記憶：完整套件約 60s，128+ passed。

## 架構重點

- `engine/backtester.py`：核心回測引擎。`run()` 有主循環；`_close_position` 是唯一平倉入口（signal/OCO + 兩條爆倉路徑收斂）；`_fee_for/_slippage_for/_size_for` 是實例方法。
- `app/models/schemas.py`：所有 API 參數 schema。**數值欄位一律要有 Field 邊界（gt/ge/le）與 finite 防護** —— critical 歷史漏洞（1e308 crash、負 leverage、150% commission）。
- `app/core/sandbox.py`：custom_code AST 沙箱。`backtest/run` 收到 custom_code 必須過 `check_strategy_code`。
- Pydantic response_model 改欄位時，**必須同步改 schema**，否則欄位被靜默丟棄（看起來像「部署沒生效」）。

## 已知鐵律（踩過的坑）

- commission 是**比例費率**（0.001 = 0.1%），不是絕對值。`notional * commission`。
- perp 爆倉走 generic `self.funding.accrued()`，不要用 `_last_funding`（死碼，已移除）。
- `_calculate_metrics` 的 PF 計算分母為 0 時用 999.0 sentinel（PF infinity 慣例）。
- 前端 Vercel 部署另有 skill reference，勿混淆 Railway 後端與 Vercel 前端。

## 工作目錄注意

- 頂層大量 `*.json` 是回測任務產出（backtests），勿誤當設定檔；這些是 untracked/運行時資料。
- `backtests/`、`app/data/experiments/` 是運行時副產物，不提交。
