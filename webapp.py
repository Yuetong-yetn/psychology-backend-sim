from __future__ import annotations

"""调试 API 入口。

提供调试页、样例运行、任务进度查询和快照读取接口，
用于驱动本地后端调试和前端联调。
"""

import asyncio
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_ROOT = CURRENT_DIR.parent
# 允许直接执行当前文件时正常导入 `Backend` 包。
if str(PARENT_ROOT) not in sys.path:
    sys.path.insert(0, str(PARENT_ROOT))

from Backend.config.backend_settings import BACKEND_IO
from Backend.config.frontend_settings import (
    ALLOWED_MODES,
    ALLOWED_PROVIDERS,
    DEBUG_RUN_DEFAULTS,
    DEBUG_RUN_LIMITS,
    frontend_options_payload,
)
from Backend.generate_backend_input import build_payload
from Backend.run_backend_input import run_from_payload_async

ROOT = CURRENT_DIR
OUTPUTS_DIR = ROOT / BACKEND_IO.outputs_dir_name
EXAMPLES_DIR = ROOT / BACKEND_IO.examples_dir_name
VIEWER_HTML = ROOT / BACKEND_IO.viewer_html_name
DEFAULT_INPUT = EXAMPLES_DIR / BACKEND_IO.default_input_name
DEFAULT_OUTPUT = OUTPUTS_DIR / BACKEND_IO.default_output_name
RUN_JOBS: dict[str, dict[str, object]] = {}
RUN_JOBS_LOCK = threading.Lock()


class DebugRunRequest(BaseModel):
    """调试运行请求体。"""

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


def _ensure_default_input() -> Path:
    """确保默认示例输入文件存在。"""

    if DEFAULT_INPUT.exists():
        return DEFAULT_INPUT
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload(
        num_agents=DEBUG_RUN_DEFAULTS.num_agents,
        rounds=DEBUG_RUN_DEFAULTS.rounds,
        seed_posts=DEBUG_RUN_DEFAULTS.seed_posts,
        seed=DEBUG_RUN_DEFAULTS.seed,
    )
    DEFAULT_INPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return DEFAULT_INPUT


def _latest_output_path() -> Path | None:
    """返回最新导出的快照文件路径。"""

    candidates = sorted(OUTPUTS_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _load_json(path: Path) -> Any:
    """读取并解析 JSON 文件。"""

    return json.loads(path.read_text(encoding="utf-8"))


def _build_debug_payload(request: DebugRunRequest) -> dict[str, object]:
    """根据前端请求构造调试用 payload。"""

    payload = build_payload(
        num_agents=request.num_agents,
        rounds=request.rounds,
        seed_posts=request.seed_posts,
        seed=request.seed,
    )
    runtime = dict(payload.get("runtime", {}))
    runtime.update(
        {
            "mode": request.mode,
            "llm_provider": request.llm_provider,
            "enable_fallback": request.enable_fallback,
            "feed_limit": request.feed_limit,
        }
    )
    payload["runtime"] = runtime
    meta = dict(payload.get("meta", {}))
    meta["debugRunConfig"] = request.model_dump()
    payload["meta"] = meta
    return payload


def _snapshot_debug_meta(snapshot: dict[str, object], request: DebugRunRequest | None = None) -> dict[str, object]:
    """生成调试相关的附加元信息。"""

    return {
        "exposedFrontendParams": [
            "num_agents",
            "rounds",
            "seed_posts",
            "seed",
            "feed_limit",
            "mode",
            "llm_provider",
            "enable_fallback",
        ],
        "providerBehavior": {
            "mode": request.mode if request else None,
            "llm_provider": request.llm_provider if request else None,
            "enable_fallback": request.enable_fallback if request else None,
        },
        "whyResultsAppearWithoutApiKey": (
            "The backend can run in local fallback mode. If mode=fallback, or the selected provider is unavailable "
            "while enable_fallback=true, the simulation still produces results without external API credentials."
        ),
        "autoRunOnSnapshot": False,
        "historyRounds": len(list(snapshot.get("history", []))),
    }


def _run_job_payload(job_id: str, request: DebugRunRequest) -> None:
    """在线程中执行一次后台仿真任务。"""

    def update_job(**updates: object) -> None:
        """线程安全地更新任务状态。"""

        with RUN_JOBS_LOCK:
            job = RUN_JOBS.get(job_id)
            if job is None:
                return
            job.update(updates)
            job["updated_at"] = time.time()

    async def progress_callback(payload: dict[str, object]) -> None:
        """接收仿真阶段进度并同步到任务表。"""

        update_job(
            status="running" if payload.get("stage") != "completed" else "completed",
            progress=float(payload.get("progress", 0.0)),
            stage=str(payload.get("stage", "running")),
            message=str(payload.get("message", "")),
            completed_rounds=payload.get("completed_rounds"),
            total_rounds=payload.get("total_rounds"),
        )

    try:
        payload = _build_debug_payload(request)
        EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_INPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        update_job(status="running", progress=0.01, stage="queued", message="Run job accepted")
        snapshot = asyncio.run(run_from_payload_async(payload, progress_callback=progress_callback))
        snapshot["_debug"] = _snapshot_debug_meta(snapshot, request)
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
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
    """创建并启动一个后台仿真任务。"""

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
    """返回首页 HTML。"""

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
          <p>访问：</p>
          <ul>
            <li>API 文档：<a href="/docs">http://localhost:8000/docs</a></li>
            <li>调试页面：<a href="/debug/viewer">http://localhost:8000/debug/viewer</a></li>
          </ul>
        </div>
      </body>
    </html>
    """


@app.get("/debug/viewer")
def debug_viewer() -> FileResponse:
    """返回调试页面文件。"""

    if not VIEWER_HTML.exists():
        raise HTTPException(status_code=404, detail="viewer.html not found")
    return FileResponse(VIEWER_HTML)


@app.get("/api/debug/options")
def debug_options() -> JSONResponse:
    """返回前端可选参数配置。"""

    return JSONResponse(frontend_options_payload())


@app.get("/api/debug/status")
def debug_status() -> JSONResponse:
    """返回当前调试状态与路径信息。"""

    latest = _latest_output_path()
    return JSONResponse(
        {
            "docs_url": "http://localhost:8000/docs",
            "viewer_url": "http://localhost:8000/debug/viewer",
            "default_input_path": str(_ensure_default_input()),
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
    """同步执行一次调试样例。"""

    resolved_request = request or DebugRunRequest()
    payload = _build_debug_payload(resolved_request)
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_INPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    snapshot = asyncio.run(run_from_payload_async(payload))
    snapshot["_debug"] = _snapshot_debug_meta(snapshot, resolved_request)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return JSONResponse(snapshot)


@app.post("/api/debug/run-sample/start")
def debug_run_sample_start(request: DebugRunRequest | None = None) -> JSONResponse:
    """异步启动一个调试样例任务。"""

    resolved_request = request or DebugRunRequest()
    return JSONResponse(_create_run_job(resolved_request))


@app.get("/api/debug/run-sample/{job_id}")
def debug_run_sample_progress(job_id: str) -> JSONResponse:
    """查询后台调试任务进度。"""

    with RUN_JOBS_LOCK:
        job = RUN_JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Run job {job_id!r} not found")
        return JSONResponse(job)


@app.get("/api/debug/snapshot")
def debug_snapshot() -> JSONResponse:
    """读取最新快照结果。"""

    latest = _latest_output_path()
    if latest is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No snapshot is available yet. Call POST /api/debug/run-sample first, "
                "or use the debug viewer to start a run."
            ),
        )
    snapshot = _load_json(latest)
    if "_debug" not in snapshot:
        snapshot["_debug"] = _snapshot_debug_meta(snapshot)
    return JSONResponse(snapshot)
