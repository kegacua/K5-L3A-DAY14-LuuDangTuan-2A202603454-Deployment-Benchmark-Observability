"""
Production AI Agent — Part 6 Final Project
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import sys
import time
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r as redis_client, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Định dạng mỗi dòng log thành 1 JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> logging.Logger:
    app_logger = logging.getLogger("production_agent")
    app_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    app_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    app_logger.addHandler(handler)
    app_logger.propagate = False
    return app_logger


logger = _configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & graceful shutdown (SIGTERM được uvicorn xử lý và drain request)."""
    logger.info(
        "agent_startup",
        extra={
            "extra_fields": {
                "event": "startup",
                "environment": settings.environment,
                "port": settings.port,
            }
        },
    )
    yield
    logger.info("agent_shutdown", extra={"extra_fields": {"event": "shutdown"}})
    if redis_client is not None:
        try:
            redis_client.close()
        except Exception:
            pass


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.error(
            "unhandled_error",
            extra={
                "extra_fields": {
                    "event": "error",
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "ms": elapsed_ms,
                }
            },
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "http_request",
        extra={
            "extra_fields": {
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": elapsed_ms,
            }
        },
    )
    return response


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = Field(default=None, max_length=128)


@app.get("/health")
def health():
    """Liveness probe: luôn trả 200 khi process còn chạy, kể cả khi Redis mất kết nối."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready():
    """Readiness probe: 200 khi Redis sẵn sàng, 503 khi Redis không kết nối được."""
    if redis_healthy():
        return {"status": "ready", "redis": "ok"}
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "redis": "unavailable"},
    )


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)
    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    cost_usd = record_cost(input_tokens, output_tokens)

    logger.info(
        "ask_completed",
        extra={
            "extra_fields": {
                "event": "ask",
                "user_id": body.user_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(cost_usd, 6),
            }
        },
    )
    return {
        "question": body.question,
        "answer": answer,
        "cost_usd": round(cost_usd, 6),
    }
