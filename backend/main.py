from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from backend.services.database import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting RegAI backend")
    yield
    logger.info("Shutting down RegAI backend")
    await engine.dispose()


app = FastAPI(
    title="RegAI",
    description="AI regulatory compliance automation engine",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Rate limiting middleware for LLM-calling endpoints ───────────────────────

LLM_ENDPOINTS = {"/api/chat", "/api/internal/analyze-gap", "/api/internal/generate-report-section"}
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 30

_request_log: dict[str, list[float]] = defaultdict(list)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in LLM_ENDPOINTS:
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()
            window_start = now - RATE_LIMIT_WINDOW
            _request_log[client_ip] = [t for t in _request_log[client_ip] if t > window_start]

            if len(_request_log[client_ip]) >= RATE_LIMIT_MAX:
                return Response(
                    content='{"detail":"Rate limit exceeded. Try again later."}',
                    status_code=429,
                    media_type="application/json",
                )
            _request_log[client_ip].append(now)

        return await call_next(request)


app.add_middleware(RateLimitMiddleware)


# ── Request timing middleware ────────────────────────────────────────────────

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - t0) * 1000
        response.headers["X-Response-Time-Ms"] = f"{elapsed:.1f}"
        if elapsed > 5000:
            logger.warning("Slow request: %s %s took %.0fms", request.method, request.url.path, elapsed)
        return response


app.add_middleware(TimingMiddleware)


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ── Register routers ────────────────────────────────────────────────────────

from backend.api.chat import router as chat_router
from backend.api.frameworks import router as frameworks_router
from backend.api.gaps import router as gaps_router
from backend.api.internal import router as internal_router
from backend.api.policies import router as policies_router
from backend.api.usage import router as usage_router

app.include_router(chat_router)
app.include_router(frameworks_router)
app.include_router(gaps_router)
app.include_router(internal_router)
app.include_router(policies_router)
app.include_router(usage_router)
