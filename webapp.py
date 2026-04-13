from __future__ import annotations

"""Debug API entrypoint for local backend testing and frontend integration."""

import asyncio
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_ROOT = CURRENT_DIR.parent
if str(PARENT_ROOT) not in sys.path:
    sys.path.insert(0, str(PARENT_ROOT))

from config.frontend_settings import (  # noqa: E402
    DEBUG_RUN_DEFAULTS,
    DEBUG_RUN_LIMITS,
    frontend_options_payload,
)
from run_backend_input import run_from_payload_async  # noqa: E402
from services.debug_io import (  # noqa: E402
    VIEWER_HTML,
    build_debug_payload,
    ensure_default_input,
    latest_output_path,
    load_json,
    snapshot_debug_meta,
    write_default_input,
    write_default_output,
)

RUN_JOBS: dict[str, dict[str, object]] = {}
RUN_JOBS_LOCK = threading.Lock()


class DebugRunRequest(BaseModel):
    """Frontend request model for a debug simulation run."""

    num_agents: int = Field(DEBUG_RUN_DEFAULTS.num_agents, ge=DEBUG_RUN_LIMITS.min_agents, le=DEBUG_RUN_LIMITS.max_agents)
    rounds: int = Field(DEBUG_RUN_DEFAULTS.rounds, ge=DEBUG_RUN_LIMITS.min_rounds, le=DEBUG_RUN_LIMITS.max_rounds)
    seed_posts: int = Field(DEBUG_RUN_DEFAULTS.seed_posts, ge=DEBUG_RUN_LIMITS.min_seed_posts, le=DEBUG_RUN_LIMITS.max_seed_posts)
    seed: int = Field(DEBUG_RUN_DEFAULTS.seed, ge=DEBUG_RUN_LIMITS.min_seed, le=DEBUG_RUN_LIMITS.max_seed)
    feed_limit: int = Field(DEBUG_RUN_DEFAULTS.feed_limit, ge=DEBUG_RUN_LIMITS.min_feed_limit, le=DEBUG_RUN_LIMITS.max_feed_limit)
    mode: Literal["fallback", "moe"] = DEBUG_RUN_DEFAULTS.mode
    llm_provider: Literal["ollama", "deepseek"] = DEBUG_RUN_DEFAULTS.llm_provider
    enable_fallback: bool = DEBUG_RUN_DEFAULTS.enable_fallback


app = FastAPI(
    title="Psychology Backend Debug API",
    description="Debug and visualize the social simulation backend.",
    version="1.1.0",
)


def _run_job_payload(job_id: str, request: DebugRunRequest) -> None:
    """Run a single simulation job in a background thread."""

    def update_job(**updates: object) -> None:
        with RUN_JOBS_LOCK:
            job = RUN_JOBS.get(job_id)
            if job is None:
                return
            job.update(updates)
            job["updated_at"] = time.time()

    async def progress_callback(payload: dict[str, object]) -> None:
        update_job(
            status="running" if payload.get("stage") != "completed" else "completed",
            progress=float(payload.get("progress", 0.0)),
            stage=str(payload.get("stage", "running")),
            message=str(payload.get("message", "")),
            completed_rounds=payload.get("completed_rounds"),
            total_rounds=payload.get("total_rounds"),
        )

    try:
        payload = build_debug_payload(request)
        write_default_input(payload)
        update_job(status="running", progress=0.01, stage="queued", message="Run job accepted")
        snapshot = asyncio.run(run_from_payload_async(payload, progress_callback=progress_callback))
        snapshot["_debug"] = snapshot_debug_meta(snapshot, request)
        write_default_output(snapshot)
        update_job(
            status="completed",
            progress=1.0,
            stage="completed",
            message="Simulation completed",
            snapshot=snapshot,
        )
    except Exception as exc:
        update_job(
            status="failed",
            stage="failed",
            message=str(exc),
            error=str(exc),
        )


def _create_run_job(request: DebugRunRequest) -> dict[str, object]:
    """Create and start a background simulation job."""

    job_id = f"run-{uuid.uuid4().hex[:12]}"
    created_at = time.time()
    job = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0.0,
        "stage": "queued",
        "message": "Waiting to start",
        "created_at": created_at,
        "updated_at": created_at,
        "request": request.model_dump(),
        "snapshot": None,
        "error": None,
        "completed_rounds": 0,
        "total_rounds": request.rounds,
    }
    with RUN_JOBS_LOCK:
        RUN_JOBS[job_id] = job
    worker = threading.Thread(
        target=_run_job_payload,
        args=(job_id, request),
        daemon=True,
        name=f"debug-run-{job_id}",
    )
    worker.start()
    return job


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    """Return a small landing page for the backend service."""

    return """
    <html>
      <head>
        <meta charset="utf-8" />
        <title>Psychology Backend</title>
        <style>
          body{font-family:Consolas,monospace;background:#0f1115;color:#f5f7fa;padding:32px}
          a{color:#93c5fd}
          .box{max-width:920px;background:#171a21;border:1px solid #2b3240;border-radius:16px;padding:24px}
        </style>
      </head>
      <body>
        <div class="box">
          <h1>Psychology Backend</h1>
          <p>Visit:</p>
          <ul>
            <li>API docs: <a href="/docs">http://localhost:8000/docs</a></li>
            <li>Debug viewer: <a href="/debug/viewer">http://localhost:8000/debug/viewer</a></li>
          </ul>
        </div>
      </body>
    </html>
    """


@app.get("/debug/viewer")
def debug_viewer() -> FileResponse:
    """Return the optional local debug viewer HTML file."""

    if not VIEWER_HTML.exists():
        raise HTTPException(status_code=404, detail="viewer.html not found")
    return FileResponse(VIEWER_HTML)


@app.get("/api/debug/options")
def debug_options() -> JSONResponse:
    """Return frontend-visible defaults and limits."""

    return JSONResponse(frontend_options_payload())


@app.get("/api/debug/status")
def debug_status() -> JSONResponse:
    """Return current debug status and useful local paths."""

    latest = latest_output_path()
    return JSONResponse(
        {
            "docs_url": "http://localhost:8000/docs",
            "viewer_url": "http://localhost:8000/debug/viewer",
            "default_input_path": str(ensure_default_input()),
            "latest_output_path": str(latest) if latest else None,
            "has_snapshot": latest is not None,
            "auto_run_sample_on_snapshot": False,
            "why_results_can_exist_without_api_key": (
                "Existing snapshots may already be stored in outputs/, and local fallback mode can generate "
                "fresh results without external API credentials."
            ),
        }
    )


@app.post("/api/debug/run-sample")
def debug_run_sample(request: DebugRunRequest | None = None) -> JSONResponse:
    """Run a sample simulation synchronously and return the snapshot."""

    resolved_request = request or DebugRunRequest()
    payload = build_debug_payload(resolved_request)
    write_default_input(payload)
    snapshot = asyncio.run(run_from_payload_async(payload))
    snapshot["_debug"] = snapshot_debug_meta(snapshot, resolved_request)
    write_default_output(snapshot)
    return JSONResponse(snapshot)


@app.post("/api/debug/run-sample/start")
def debug_run_sample_start(request: DebugRunRequest | None = None) -> JSONResponse:
    """Start an asynchronous sample simulation job."""

    resolved_request = request or DebugRunRequest()
    return JSONResponse(_create_run_job(resolved_request))


@app.get("/api/debug/run-sample/{job_id}")
def debug_run_sample_progress(job_id: str) -> JSONResponse:
    """Return the current background job state."""

    with RUN_JOBS_LOCK:
        job = RUN_JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Run job {job_id!r} not found")
        return JSONResponse(job)


@app.get("/api/debug/snapshot")
def debug_snapshot() -> JSONResponse:
    """Return the latest stored snapshot."""

    latest = latest_output_path()
    if latest is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No snapshot is available yet. Call POST /api/debug/run-sample first, "
                "or use the debug viewer to start a run."
            ),
        )
    snapshot = load_json(latest)
    if "_debug" not in snapshot:
        snapshot["_debug"] = snapshot_debug_meta(snapshot)
    return JSONResponse(snapshot)
