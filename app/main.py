from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import data, strategy, backtest, optimize, analysis, arbitrage, monitoring, research, admin, experiments, validate
from app.config import settings
from app.core.exceptions import AppException
from app.core.middleware import TimingMiddleware

logger = logging.getLogger(__name__)
logging.basicConfig(level=settings.log_level.upper())

app = FastAPI(title="Quant Backtest Platform API", version="1.0.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TimingMiddleware)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/")
async def root():
    return {"service": "Quant Backtest Platform", "docs": "/docs"}


# Mount routes
app.include_router(data.router)
app.include_router(strategy.router)
app.include_router(backtest.router)
app.include_router(optimize.router)
app.include_router(analysis.router)
app.include_router(arbitrage.router)
app.include_router(monitoring.router)
app.include_router(research.router, prefix="/api")
app.include_router(admin.router)
app.include_router(experiments.router)
app.include_router(validate.router)
