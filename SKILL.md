---
name: Crypto-Backtesting-Lab
description: Use when working in the Crypto-Backtesting-Lab repo — a quant backtesting SaaS with BingX TradFi symbols, tick-replay engine, multi-exchange execution, factor strategies, and a predict.fun monitoring daemon. Covers how to run backtests, add symbols, register strategies, and operate the monitoring service.
---

# Crypto-Backtesting-Lab

Solo quant backtesting SaaS (FastAPI backend + Next.js frontend). Lets you backtest
strategies on crypto + BingX TradFi symbols (gold, fx, stocks), with tick-replay
precision, multi-exchange execution simulation, factor-driven strategies, and a
live predict.fun shadow-trading monitor.

## When to use

- Running or extending backtests / strategies in this repo
- Adding BingX TradFi symbols or probing their live status
- Wiring a new strategy into `strategy_service`
- Operating the predict.fun monitoring daemon (start/stop/debug crashes)
- Frontend work on the arbitrage page, symbol picker, or backtest UI

## Architecture

| Layer | Path | Notes |
|-------|------|-------|
| Backend | `app/` (FastAPI) | `services/`, `api/routes/`, `models/` |
| Replay engine | `engine/replay.py` | Tick-synth from OHLCV, limit queue fill |
| Multi-exchange | `engine/exchanges/` | registry (fees) + executor (paper/live) |
| Factor strategy | `strategies/factor/` | factors.py + FactorStrategy |
| TradFi data | `data/providers/bingx_tradfi.py` | `BINGX_TRADFI_SYMBOLS` registry + `probe_symbols()` |
| Monitoring | `monitoring/` | `run.py --live` daemon → predict.fun + Railway push |
| Frontend | `frontend/src/` | Next.js app router |

## Key facts

- **BingX TradFi** uses OpenAPI klines (`openApi/swap/v3/quote/klines?symbol={S}-USDT`),
  NOT ccxt. Symbol prefixes: `NCCO`(metal/energy) `NCFX`(fx) `NCSI`(index) `NCSK`(stock).
- Active count ~26 of 60 symbols; FX all `paused`, energy/silver `offline`. Inactive
  symbols are selectable=false in the picker. Re-run `probe_symbols()` to refresh status.
- **BacktestConfig.source** defaults to `"binance"` and OVERWRITES auto-routing — `run()`
  force-routes NCCO/NCFX/NCSI/NCSK → `bingx_tradfi`. Do not "fix" that default.
- Factor strategy `factor_driven` is registered; weights are hardcoded in `FactorStrategy`
  (momentum 0.3, mean_reversion 0.25, volatility -0.2, rsi 0.15, roc 0.1).
- Monitoring daemon is a **systemd user service** (`predict-monitor.service`), NOT a
  manual nohup. Restart with `systemctl --user restart predict-monitor.service`.

## Common commands

```bash
# Backend venv
source venv/bin/activate

# Run a backtest (TestClient)
python3 - <<'PY'
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
r = c.post("/api/backtest/run", json={...})
PY

# Factor strategy end-to-end
python3 -c "from app.services.strategy_service import get_strategy; print(get_strategy('factor_driven'))"

# Probe BingX TradFi symbol status
python3 -c "from data.providers.bingx_tradfi import BingXTradFiProvider; print(BingXTradFiProvider().probe_symbols())"

# Monitoring daemon
systemctl --user status predict-monitor.service
systemctl --user restart predict-monitor.service   # after editing monitoring/run.py
journalctl --user -u predict-monitor.service

# Frontend
cd frontend && npm run build

# GLM model (separate skill: glm-tokenrouter)
python3 ~/.hermes/skills/glm-tokenrouter/scripts/glm_chat.py "prompt"
```

## Gotchas

- `monitoring/run.py` has self-heal reconnect (while-True + backoff). If it still dies,
  check `monitor.log` + `systemctl --user status` — systemd Restart=always catches hard crashes.
- Arbitrage page has two modes: `basis` (flatten when |spread|<=exit_threshold) and
  `locked` (hold until |spread|>=unlock_threshold or sign reverses).
- Don't start monitoring manually (nohup/background) — systemd owns it; two instances clash.
- `openai` pip package needed for GLM skill (installed in venv).
