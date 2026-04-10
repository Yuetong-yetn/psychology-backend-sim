from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from Backend.generate_backend_input import build_payload
from Backend.run_backend_input import run_from_payload


ROOT = Path(__file__).resolve().parent
OUTPUTS_DIR = ROOT / "outputs"
EXAMPLES_DIR = ROOT / "examples"
VIEWER_HTML = ROOT / "viewer.html"
DEFAULT_INPUT = EXAMPLES_DIR / "backend_sample_input.json"
DEFAULT_OUTPUT = OUTPUTS_DIR / "backend_sample_output.json"

app = FastAPI(
    title="Psychology Backend Debug API",
    description="Debug and visualize the social simulation backend.",
    version="1.0.0",
)


def _ensure_default_input() -> Path:
    if DEFAULT_INPUT.exists():
        return DEFAULT_INPUT
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload(num_agents=8, rounds=4, seed_posts=6, seed=42)
    DEFAULT_INPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return DEFAULT_INPUT


def _latest_output_path() -> Path | None:
    candidates = sorted(OUTPUTS_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/", response_class=HTMLResponse)
def home() -> str:
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
            <li>调试页：<a href="/debug/viewer">http://localhost:8000/debug/viewer</a></li>
          </ul>
        </div>
      </body>
    </html>
    """


@app.get("/debug/viewer")
def debug_viewer() -> FileResponse:
    if not VIEWER_HTML.exists():
        raise HTTPException(status_code=404, detail="viewer.html not found")
    return FileResponse(VIEWER_HTML)


@app.get("/api/debug/status")
def debug_status() -> JSONResponse:
    latest = _latest_output_path()
    return JSONResponse(
        {
            "docs_url": "http://localhost:8000/docs",
            "viewer_url": "http://localhost:8000/debug/viewer",
            "default_input_path": str(_ensure_default_input()),
            "latest_output_path": str(latest) if latest else None,
        }
    )


@app.post("/api/debug/run-sample")
def debug_run_sample() -> JSONResponse:
    input_path = _ensure_default_input()
    payload = _load_json(input_path)
    snapshot = run_from_payload(payload)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return JSONResponse(snapshot)


@app.get("/api/debug/snapshot")
def debug_snapshot() -> JSONResponse:
    latest = _latest_output_path()
    if latest is None:
        input_path = _ensure_default_input()
        payload = _load_json(input_path)
        snapshot = run_from_payload(payload)
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        latest = DEFAULT_OUTPUT
    return JSONResponse(_load_json(latest))
