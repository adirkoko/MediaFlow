# backend/app/main.py
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_auth import router as auth_router
from app.api.routes_health import router as health_router
from app.api.routes_jobs import router as jobs_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.infrastructure.db import ensure_db_initialized
from app.services.job_manager import JobManager
from app.services.worker import Worker
from app.api.routes_usage import router as usage_router
from app.services.cleanup import OutputsCleaner

setup_logging()

app = FastAPI(title=settings.app_name)

# CORS for frontend dev (configurable via env)
allowed_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(usage_router)

# Singletons attached to app.state
app.state.manager = JobManager()
app.state.worker_task = None


def get_manager() -> JobManager:
    return app.state.manager


@app.on_event("startup")
async def on_startup() -> None:
    ensure_db_initialized()
    # Ensure outputs dir exists
    import os

    os.makedirs(settings.outputs_dir, exist_ok=True)

    worker = Worker(app.state.manager)
    app.state.worker_task = asyncio.create_task(worker.run_forever())

    cleaner = OutputsCleaner()
    app.state.cleanup_task = asyncio.create_task(cleaner.run_forever())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    # Safely cancel worker task if it exists
    worker_task = getattr(app.state, "worker_task", None)
    if worker_task:
        worker_task.cancel()

    # Safely cancel cleanup task if it exists
    cleanup_task = getattr(app.state, "cleanup_task", None)
    if cleanup_task:
        cleanup_task.cancel()
