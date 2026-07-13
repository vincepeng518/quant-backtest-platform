# 使用者策略上傳 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** 讓用戶上傳自己的 Python 策略（繼承 StrategyBase），持久化進策略庫（git 推送），並在回測/優化中像內建策略一樣被使用。

**Architecture:** 使用者策略存 `strategies/user/{id}.py` + `manifest.json`，啟動時動態 import 註冊為 `user_{id}` 進現有 `_registry`。上傳時 `compile()` 擋語法錯、寫檔後 `git commit/push` 持久化。回測/優化零改動（走同一 `get_strategy()` 路徑）。前端新 `/strategies` 頁 + backtest/optimize 下拉含使用者策略 + 動態參數框。

**Tech Stack:** FastAPI, importlib, subprocess(git), Next.js 14 (React), Tailwind

## Global Constraints
- 安全：solo 平台，直接執行用戶代碼，不做隔離；檔名用 UUID 防 path traversal
- 持久化：上傳/編輯/刪除後必須 `git add/commit/push` 到 `vincepeng518/quant-backtest-platform` master
- 註冊 key 前綴：`user_{id}`，避免與內建策略撞名
- 軟上限 100 個策略；超過回 warning 但仍可存
- 每個 .py 只註冊一個 StrategyBase 子類（多個取第一個 + warning）
- `GET /api/strategy/templates` 回填 `params = cls().get_params_space()`（前端靠此渲染輸入框）
- POLLUTION GUARD: upload_strategy 會自動 push 到 GitHub。測試時若呼叫它會污染真實 repo。剩餘 task 的 subagent 驗證後必須清理測試策略（呼叫 delete_strategy 或透過 GitHub API 刪除），或直接測 load_user_strategies/registration 而不經 upload_strategy。

---

## Task 1: Git 持久化 helper (DONE)
Created app/services/strategy_git.py with git_persist(files, message) -> tuple[bool, str].

## Task 2: strategy_service 使用者策略 CRUD + 啟動載入 (DONE)
Appended to app/services/strategy_service.py: _read_manifest, _write_manifest, _load_one, load_user_strategies, _syntax_ok, upload_strategy, list_user_strategies, get_user_strategy, update_strategy, delete_strategy, _now. Added load_user_strategies() call at end of _ensure_registered().

## Task 3: Schemas 擴充
**Files:** Modify app/models/schemas.py
Add after StrategyTemplate:
```python
class UserStrategyUpload(BaseModel):
    name: str
    description: str = ""
    category: str = "custom"
    code: str

class UserStrategyMeta(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = "custom"
    filename: str = ""
    created_at: str = ""
    status: str = "registered"
    params_space: dict[str, Any] = {}
    error: str | None = None
```
Verify: `./venv/bin/python -c "from app.models.schemas import UserStrategyUpload, UserStrategyMeta; print('ok')"`
Commit: app/models/schemas.py

## Task 4: 路由 upload/user/list/get/put/delete
**Files:** Modify app/api/routes/strategy.py
Rewrite to add POST /upload, GET /user, GET /user/{sid}, PUT /user/{sid}, DELETE /user/{sid}, and backfill params in GET /templates.
Uses ss.upload_strategy, ss.list_user_strategies, ss.get_user_strategy, ss.update_strategy, ss.delete_strategy.
templates route: iterate ss._registry, build StrategyTemplate with params=[{"name":k,**v} for k,v in (cls().get_params_space() or {}).items()].
Verify locally with uvicorn + curl (use a temp strategy, then delete it to avoid pollution).
Commit: app/api/routes/strategy.py

## Task 5: 前端 api + types
**Files:** Modify frontend/src/lib/api.ts, frontend/src/types/api.ts
Add types: UserStrategy, StrategyTemplate (with params array).
Add api methods: uploadStrategy, listUserStrategies, getUserStrategy, updateStrategy, deleteStrategy, getTemplates.
Commit both files.

## Task 6: /strategies 頁（上傳/編輯/刪除）
**Files:** Create frontend/src/app/strategies/page.tsx
Impeccable style. Form (name/description/category/code textarea), library list with edit/delete.
Uses api from Task 5. On mount load list. Submit → upload or update. Edit → getUserStrategy → fill form. Delete → deleteStrategy → reload.
Commit: frontend/src/app/strategies/page.tsx

## Task 7: backtest/optimize 整合使用者策略 + 動態參數
**Files:** Modify frontend/src/app/backtest/page.tsx, frontend/src/stores/useBacktestStore.ts
backtest page: load getTemplates() + listUserStrategies(). Dropdown = builtin + user (value `user_{id}`, label `我的：{name}`). On select, render param inputs from templates.find(t=>t.id===sel).params (range→number input min/max/step; choice→select). Build config.strategy = {template_id: sel, params}.
store runBacktest already sends config.strategy.template_id — confirm it passes user_{id} through.
Verify: `cd frontend && npm run build` succeeds.
Commit both files.

## Task 8: 端到端驗證 + 部署
Local: start uvicorn, upload a TestMA strategy with get_params_space, confirm templates contains user_, run backtest with user_{id}, confirm status=completed. Then DELETE the test strategy (call delete_strategy + verify GitHub cleaned).
Frontend: `cd frontend && npm run build`.
Push: `git add -A && git commit -m "feat: user strategy upload (full pipeline)" && git push origin master`.
Verify live: `curl https://quant-backed.onrender.com/api/strategy/user` returns list (confirms git push + startup load cross-device survival).
