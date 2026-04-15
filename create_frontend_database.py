#!/usr/bin/env python3
"""Build a frontend handoff SQLite database from existing backend JSON artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from social_platform.database import build_database as build_snapshot_database


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "examples" / "backend_sample_input.json"
DEFAULT_OUTPUT_CANDIDATES = [
    ROOT / "outputs" / "backend_sample_output.json",
    ROOT / "outputs" / "simulation_snapshot.json",
    ROOT / "outputs" / "test_snapshot.json",
]
DEFAULT_DB = ROOT / "psychology_backend_frontend.db"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_snapshot_path() -> Path:
    for candidate in DEFAULT_OUTPUT_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No backend snapshot JSON file was found in outputs/.")


def build_database(
    input_path: Path = DEFAULT_INPUT,
    snapshot_path: Path | None = None,
    db_path: Path = DEFAULT_DB,
) -> Path:
    snapshot_path = snapshot_path or _resolve_snapshot_path()
    payload = _load_json(input_path)
    snapshot = _load_json(snapshot_path)
    return build_snapshot_database(payload=payload, snapshot=snapshot, db_path=db_path)


if __name__ == "__main__":
    db_path = build_database()
    print(db_path)
