import asyncio
from fastapi import FastAPI

from app.api.routes_auth import router as auth_router
from app.api.routes_health import router as health_router
from app.api.routes_jobs import router as jobs_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.infrastructure.db import ensure_db_initialized
from app.services.job_manager import JobManager
from app.services.worker import Worker

setup_logging()

app = FastAPI(title=settings.app_name)

# Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(jobs_router)

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


@app.on_event("shutdown")
async def on_shutdown() -> None:
    task = app.state.worker_task
    if task:
        task.cancel()
