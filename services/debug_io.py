from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.backend_settings import BACKEND_IO
from config.frontend_settings import DEBUG_RUN_DEFAULTS
from data.oasis_reddit.oasis_adapter import build_payload, write_mapping_csv


ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT / BACKEND_IO.outputs_dir_name
EXAMPLES_DIR = ROOT / BACKEND_IO.examples_dir_name
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


def _agent_runtime_summary(snapshot: dict[str, object]) -> dict[str, object]:
    """Build a compact per-agent runtime summary for frontend debug views."""

    summary: dict[str, object] = {}
    for row in snapshot.get("agents", []):
        if not isinstance(row, dict):
            continue
        profile = dict(row.get("profile", {}))
        state = dict(row.get("state", {}))
        debug_state = dict(state.get("_debug", {}))
        appraisal = dict(debug_state.get("appraisal_runtime", {}))
        latent = dict(debug_state.get("latent_runtime", {}))
        fallback_reason = appraisal.get("fallback_reason")
        fallback_triggered = bool(appraisal.get("fallback_used") or fallback_reason)
        agent_id = str(profile.get("agent_id", ""))
        if not agent_id:
            continue
        summary[agent_id] = {
            "name": profile.get("name"),
            "appraisal": {
                "mode": appraisal.get("mode"),
                "provider": appraisal.get("provider"),
                "model": appraisal.get("model"),
                "source": appraisal.get("source"),
                "fallback_reason": fallback_reason,
            },
            "latent": {
                "mode": latent.get("mode"),
                "provider": latent.get("provider"),
                "model": latent.get("model"),
                "source": latent.get("source"),
                "fallback_reason": latent.get("fallback_reason"),
            },
            "action_timing": debug_state.get("action_runtime", {}),
            "fallback_triggered": fallback_triggered,
        }
    return summary


def _request_value(request: Any | None, key: str, default: Any = None) -> Any:
    if request is None:
        return default
    if isinstance(request, dict):
        runtime = dict(request.get("runtime", {}))
        meta = dict(request.get("meta", {}))
        if key in runtime:
            return runtime.get(key)
        return meta.get(key, default)
    return getattr(request, key, default)


def snapshot_debug_meta(snapshot: dict[str, object], request: Any | None = None) -> dict[str, object]:
    """Build the extra debug metadata attached to snapshots."""

    simulation_config = {
        "num_agents": _request_value(request, "num_agents"),
        "rounds": _request_value(request, "rounds"),
        "seed_posts": _request_value(request, "seed_posts"),
        "seed": _request_value(request, "seed"),
        "feed_limit": _request_value(request, "feed_limit"),
        "mode": _request_value(request, "mode"),
        "llm_provider": _request_value(request, "llm_provider"),
        "enable_fallback": _request_value(request, "enable_fallback"),
        "appraisal_llm_ratio": _request_value(request, "appraisal_llm_ratio"),
    }
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
            "mode": simulation_config.get("mode"),
            "llm_provider": simulation_config.get("llm_provider"),
            "enable_fallback": simulation_config.get("enable_fallback"),
        },
        "simulation_config": simulation_config,
        "whyResultsAppearWithoutApiKey": (
            "The backend can run in local fallback mode. If mode=fallback, or the selected provider is unavailable "
            "while enable_fallback=true, the simulation still produces results without external API credentials."
        ),
        "autoRunOnSnapshot": False,
        "historyRounds": len(list(snapshot.get("history", []))),
        "agent_runtime_summary": _agent_runtime_summary(snapshot),
    }
