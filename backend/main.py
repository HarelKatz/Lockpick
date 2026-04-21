"""FastAPI application entry point."""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine
import models  # noqa: F401 — ensures models are registered before migrations

from routers import activity, connections, credentials, export_import, graph, hosts, operations, search, stats, upload, ws
from ws_manager import set_main_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run Alembic migrations on startup to ensure DB is up to date."""
    import subprocess
    import sys

    set_main_loop(asyncio.get_event_loop())

    os.makedirs(os.path.dirname(os.path.abspath(settings.db_path)), exist_ok=True)
    os.makedirs(settings.upload_path, exist_ok=True)

    # Run alembic upgrade head
    backend_dir = os.path.dirname(__file__)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Alembic migration warning: {result.stderr}", flush=True)

    yield


app = FastAPI(
    title="Lockpick",
    description="Red Team Operation Manager — track SSH credentials, hosts, and pivot paths",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: allow all origins — this is a trusted-network red team tool
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(operations.router, prefix="/api")
app.include_router(hosts.router, prefix="/api")
app.include_router(credentials.router, prefix="/api")
app.include_router(connections.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(activity.router, prefix="/api")
app.include_router(export_import.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(ws.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "lockpick"}
