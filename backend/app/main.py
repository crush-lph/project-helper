"""FastAPI 应用入口 —— 中间件、静态文件、路由注册。"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import Database
from .routers import analysis, auth, chat, projects, source

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


# ---- Rate Limiting ----

class _RateLimiter:
    """Simple sliding-window rate limiter per IP."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window
        timestamps = self._requests.setdefault(key, [])
        self._requests[key] = [t for t in timestamps if t > cutoff]
        if len(self._requests[key]) >= self.max_requests:
            return False
        self._requests[key].append(now)
        return True

    def purge_stale(self) -> None:
        """Remove IPs that haven't been seen in 2x the window."""
        cutoff = time.monotonic() - self.window * 2
        stale = [k for k, v in self._requests.items() if not v or v[-1] < cutoff]
        for k in stale:
            del self._requests[k]


_rate_limiter = _RateLimiter(max_requests=30, window_seconds=60)
_PURGE_INTERVAL = 300  # seconds
_last_purge = time.monotonic()


# ---- Lifespan ----

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _last_purge
    settings = get_settings()

    os.environ.pop("SSL_CERT_FILE", None)
    if settings.ssl_cert_file:
        os.environ["SSL_CERT_FILE"] = settings.ssl_cert_file

    app.state.settings = settings
    app.state.db = Database(settings.db_path)
    _last_purge = time.monotonic()
    yield


# ---- App ----

app = FastAPI(title="project-helper API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    global _last_purge
    path = request.url.path
    if path.startswith("/api/projects/") and (path.endswith("/chat/stream") or path.endswith("/analyze/stream")):
        client_ip = request.client.host if request.client else "unknown"
        if not _rate_limiter.is_allowed(client_ip):
            return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后重试。"})
        # Periodic purge of stale IPs
        now = time.monotonic()
        if now - _last_purge > _PURGE_INTERVAL:
            _rate_limiter.purge_stale()
            _last_purge = now
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ---- Routes ----

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(source.router)
app.include_router(chat.router)
app.include_router(analysis.router)


@app.get("/api/health")
def health():
    settings = app.state.settings
    return {"ok": True, "model": settings.deepseek_model, "llm_configured": bool(settings.deepseek_api_key)}


@app.get("/api/metrics")
def metrics():
    from .llm.observability import get_metrics
    return get_metrics().snapshot()


# ---- Static file serving (production) ----

if STATIC_DIR.is_dir():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("assets/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        index = STATIC_DIR / "index.html"
        if not index.exists():
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        return FileResponse(str(index))
