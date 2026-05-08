"""
Ponto de entrada do servidor FastAPI.
Responsabilidades: CORS, rate limiting, registro de routers, lifespan (DB + Redis + scheduler).
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from db.database import init_db
from limiter import limiter
from routers import auth, history, invoices
from services.session_service import session_service

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
APP_ENV = os.getenv("APP_ENV", "development")
TEMP_BASE = Path(os.getenv("TEMP_STORAGE_PATH", tempfile.gettempdir())) / "invoice_sessions"

# ── Scheduler de limpeza ──────────────────────────────────────────────────────

_scheduler = AsyncIOScheduler()


def _cleanup_old_session_dirs() -> None:
    """Remove diretórios de sessão com mais de 24 horas do disco."""
    if not TEMP_BASE.exists():
        return
    cutoff = datetime.now() - timedelta(hours=24)
    removed = 0
    for d in TEMP_BASE.iterdir():
        if d.is_dir():
            try:
                mtime = datetime.fromtimestamp(d.stat().st_mtime)
                if mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
                    removed += 1
            except Exception:
                pass
    if removed:
        logger.info("Cleanup: %d diretório(s) de sessão antigos removidos", removed)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await session_service.init()

    _scheduler.add_job(_cleanup_old_session_dirs, "interval", hours=1, id="cleanup_sessions")
    _scheduler.start()
    logger.info("APScheduler iniciado — limpeza de sessões a cada hora")

    yield

    _scheduler.shutdown(wait=False)
    await session_service.close()


# ── App ───────────────────────────────────────────────────────────────────────

_docs_url = None if APP_ENV == "production" else "/docs"
_redoc_url = None if APP_ENV == "production" else "/redoc"

app = FastAPI(
    title="Invoice Processing API",
    description="API para automação de processamento de invoices internacionais — Pecege.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
)

# Rate limiter integrado ao app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
_cors_origins = [FRONTEND_URL, "http://localhost:3000"]
_cors_regex = r"http://localhost(:\d+)?" if APP_ENV == "development" else None

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_regex,
    allow_credentials=True,    # obrigatório para cookies httpOnly funcionarem
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(invoices.router, prefix="/api/invoices", tags=["Invoices"])
app.include_router(history.router, prefix="/api/history", tags=["History"])


# ── Info / Health ─────────────────────────────────────────────────────────────

@app.get("/api", tags=["Info"])
def api_info():
    return {
        "name": "Invoice Processing API",
        "version": "2.0.0",
        "auth": "JWT via httpOnly cookies",
        "endpoints": {
            "auth": {
                "register": "POST /api/auth/register",
                "login": "POST /api/auth/login",
                "refresh": "POST /api/auth/refresh",
                "logout": "POST /api/auth/logout",
                "me": "GET /api/auth/me",
            },
            "invoices": {
                "upload": "POST /api/invoices/upload",
                "confirm": "POST /api/invoices/confirm",
                "download": "GET /api/invoices/download/{job_id}",
            },
            "history": {
                "list": "GET /api/history/",
                "delete_all": "DELETE /api/history/all",
                "delete_one": "DELETE /api/history/{entry_id}",
            },
        },
    }


@app.get("/health", tags=["Info"])
def health():
    return {"status": "ok", "env": APP_ENV}
