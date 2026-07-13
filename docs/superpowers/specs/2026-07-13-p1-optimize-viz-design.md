# P1 — 優化頁完整化與結果視覺化設計

日期：2026-07-13
範圍：仅优化页（optimize）功能完整化 + 后端 optimize 返回完整 grid 以支持热力图。
backtest / analysis / strategies 页已功能完整，本批不改动。

## 背景与现状

- 前端 5 页（backtest, analysis, strategies, optimize, 首页）基础 UI 均存在。
- backtest 页：equity curve / drawdown / trade blotter / metrics 全接真 API，完整。
- analysis 页：walk-forward / monte-carlo UI + 指标全接真 API，完整。
- strategies 页：CRUD 全接真 API，完整。
- **optimize 页（stub）**：
  - 只支持单参数 + 硬 code `ma_cross`，无策略选择
  - 无市场数据选择（symbol/timeframe/source）
  - 无多参数网格搜索 UI
  - 结果只显示 best params + best score，无可视化
  - store 直接 fetch `/api/...`，未走统一 `api.ts` client
- 后端 optimize：`run` 接受 `param_space: list[ParamRange]`（支持多参数），但 `get_results` 只回 `trials[:10]`（前 10 组），无完整 2D grid matrix，无法画热力图。

## 目标

将 optimize 页从 stub 提升为完整功能页，与 backtest 页体验一致：
1. 多参数网格搜索（2+ 参数同时扫）
2. 策略选择（从 templates 拉，含用户策略）
3. 市场数据选择（symbol / timeframe / source，同 backtest 页）
4. 结果可视化：
   - 热力图（2D 参数空间 × sharpe）
   - 参数重要性条形图（每参数 score 分布）
   - 收敛曲线（best score over trial index）
5. 接统一 `api.ts` client（一致性）

## 后端改动（A 方案：改后端）

文件：`app/services/optimize_service.py` + `app/models/schemas.py`

### schemas.py — OptimizeResultOut 增加字段
```
class OptimizeResultOut(BaseModel):
    task_id: str
    status: str = "completed"
    best_params: dict[str, Any] = {}
    best_score: float = 0.0
    trials: list[dict] = []          # 保留：前 N 组（兼容）
    grid: dict | None = None         # 新增：完整 2D grid（仅当 2 参数时）
```

`grid` 结构（当 param_space 恰为 2 个 range 参数时填充）：
```
{
  "param_x": str,            # 第 1 个参数名
  "param_y": str,            # 第 2 个参数名
  "x_values": [..],          # x 轴取值序列
  "y_values": [..],          # y 轴取值序列
  "scores": [[s00, s01, ...], [s10, ...], ...]  # len(y) x len(x) 矩阵，None 表示未跑/报错
}
```

### optimize_service.py — `_execute` 改动
- `grid_search` 返回完整 `results`（已是所有组合，按 score 排序）
- 当 `param_space` 长度为 2 且均为 range 类型时，构建 `grid` matrix：
  - 从 param_space 推导 x_values / y_values（min..max step）
  - 将 results 映射到 matrix（key = (param_x, param_y)）
- `trials` 仍存前 10（兼容现有前端），但新增 `grid`
- `get_results` 原样返回（含新 grid 字段）

注意：仅 2 参数时生成 heatmap；1 参数或 >2 参数时 `grid=None`，前端降级显示条形图/收敛曲线。

## 前端改动

### 1. `frontend/src/lib/api.ts` 增加 optimize 方法
```ts
runOptimize: (config) => request<{task_id:string}>('/optimize/run', {method:'POST', body: JSON.stringify(config)}),
getOptimizeResults: (taskId) => request<any>(`/optimize/results/${taskId}`),
applyBestParams: () => request<{applied:boolean}>('/optimize/best-params', {method:'POST'}),
```

### 2. `frontend/src/stores/useOptimizeStore.ts` 重构
- 改用 `api.runOptimize` / `api.getOptimizeResults`
- state 增加：`grid`, `trials`, `paramSpace`（编辑中）, `strategyId`, `symbol`, `timeframe`, `source`
- `runOptimization(strategyId, paramSpace, market)` → 调用 api，polling 直到 done/error
- 增加 `setParamSpace` / `addParam` / `removeParam` actions

### 3. `frontend/src/app/optimize/page.tsx` 重构
布局（同 backtest 页 PageShell 风格）：
- **配置区**：Strategy Select（templates + 用户策略）、Symbol / Timeframe / Source（复用 useDataStore）、动态参数行（多参数增删，每行：name / min / max / step）
- **运行区**：进度条 + Run 按钮
- **结果区**（status==completed）：
  - 顶部 MetricsCard：Best Sharpe / Best Params 摘要
  - 若 `grid` 存在 → `<Heatmap>` 组件
  - `<ParamImportanceBar>` 组件（每参数 score 分布，从 trials 推导）
  - `<ConvergenceChart>` 组件（best score over trial index，用 lightweight-charts 或 SVG）
  - "Apply Best Params" 按钮（调用 applyBestParams，可复制到 backtest 页）

### 4. 新增图表组件（手寫 SVG，ponytail 原则，不引新库）
- `frontend/src/components/charts/Heatmap.tsx`
  - props: `{ paramX, paramY, xValues, yValues, scores }`
  - 渲染色阶矩阵（success→danger 渐变），hover 显示数值
  - 响应式 SVG，min/max score 归一化上色
- `frontend/src/components/charts/ParamImportanceBar.tsx`
  - props: `{ trials: {params, score}[] }`
  - 每参数一个条形图：该参数各取值的平均 score
- `frontend/src/components/charts/ConvergenceChart.tsx`
  - props: `{ trials: {score}[] }`
  - 用 lightweight-charts 画 line（trial index vs best-so-far score）

### 5. 类型 `frontend/src/types/api.ts` 增加
```ts
export interface OptimizeGrid {
  param_x: string; param_y: string;
  x_values: number[]; y_values: number[];
  scores: (number | null)[][];
}
export interface OptimizeResult {
  task_id: string; status: string;
  best_params: Record<string, any>; best_score: number;
  trials: { params: Record<string, any>; score: number }[];
  grid: OptimizeGrid | null;
}
```

## 错误处理 / 边界
- optimize 运行失败（status==error）：显示 error 信息，重置按钮
- grid 为 null（非 2 参数）：隐藏 Heatmap，显示条形图 + 收敛曲线
- 参数空间为空 / 单参数：正常跑，结果区降级
- 市场数据加载失败：同 backtest 页（show error）

## 测试与验证
1. 后端：本地跑 optimize（2 参数 ma_cross fast/slow）→ 确认返回 `grid` 含 matrix
2. Railway 重部署 → 验证 live `/optimize/run` + `/optimize/results/{id}` 含 grid
3. 前端：`npm run build` 通过（类型检查）
4. Vercel 重部署 → 浏览器验证 optimize 页：选 2 参数 → Run → 看到 Heatmap + 条形图 + 收敛曲线
5. 验证 1 参数 / 3 参数降级路径

## 不在本批范围
- P2（loading/error 边界统一、symbols 预览）
- P3（backtest 历史、CSV 导出）
- P4（首页 dashboard、多用戶）
- backtest / analysis / strategies 页改动

## 技術决策
- 热力图/条形图用手写 SVG（不引 recharts/d3），符合 premium minimal + ponytail
- 收敛曲线复用 lightweight-charts（已依赖）
- 后端仅增加 `grid` 字段，不破坏现有 `trials` 兼容
