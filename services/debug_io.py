from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.backend_settings import BACKEND_IO
from config.frontend_settings import DEBUG_RUN_DEFAULTS
from generate_backend_input import build_payload
from oasis_adapter import write_mapping_csv


ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT / BACKEND_IO.outputs_dir_name
EXAMPLES_DIR = ROOT / BACKEND_IO.examples_dir_name
VIEWER_HTML = ROOT / BACKEND_IO.viewer_html_name
DEFAULT_INPUT = EXAMPLES_DIR / BACKEND_IO.default_input_name
DEFAULT_OUTPUT = OUTPUTS_DIR / BACKEND_IO.default_output_name


def ensure_default_input() -> Path:
    """Ensure the default sample backend input exists on disk."""

    write_mapping_csv()
    if DEFAULT_INPUT.exists():
        return DEFAULT_INPUT
    payload = build_payload(
        num_agents=DEBUG_RUN_DEFAULTS.num_agents,
        rounds=DEBUG_RUN_DEFAULTS.rounds,
        seed_posts=DEBUG_RUN_DEFAULTS.seed_posts,
        seed=DEBUG_RUN_DEFAULTS.seed,
    )
    write_default_input(payload)
    return DEFAULT_INPUT


def write_default_input(payload: dict[str, object]) -> Path:
    """Persist the default sample backend input file."""

    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    write_mapping_csv()
    DEFAULT_INPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return DEFAULT_INPUT


def write_default_output(snapshot: dict[str, object]) -> Path:
    """Persist the default sample backend output file."""

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return DEFAULT_OUTPUT


def latest_output_path() -> Path | None:
    """Return the latest exported snapshot path in outputs/."""

    candidates = sorted(OUTPUTS_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def load_json(path: Path) -> Any:
    """Load a JSON file from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


def build_debug_payload(request: Any) -> dict[str, object]:
    """Build a backend payload from the frontend debug request."""

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
            "appraisal_llm_ratio": runtime.get("appraisal_llm_ratio", 0.1),
        }
    )
    payload["runtime"] = runtime
    meta = dict(payload.get("meta", {}))
    meta["debugRunConfig"] = request.model_dump()
    payload["meta"] = meta
    return payload


def snapshot_debug_meta(snapshot: dict[str, object], request: Any | None = None) -> dict[str, object]:
    """Build the extra debug metadata attached to snapshots."""

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
