from __future__ import annotations

"""前端调试页可见参数的集中配置。"""

from dataclasses import asdict, dataclass


ALLOWED_MODES = ("fallback", "moe")
ALLOWED_PROVIDERS = ("ollama", "deepseek")


@dataclass(frozen=True)
class DebugRunDefaults:
    """调试运行时的默认表单值。"""

    num_agents: int = 20
    rounds: int = 4
    seed_posts: int = 6
    seed: int = 42
    feed_limit: int = 5
    mode: str = "moe"
    llm_provider: str = "ollama"
    enable_fallback: bool = True


@dataclass(frozen=True)
class DebugRunLimits:
    """调试表单每个字段允许的上下界。"""

    min_agents: int = 1
    max_agents: int = 200
    min_rounds: int = 1
    max_rounds: int = 50
    min_seed_posts: int = 0
    max_seed_posts: int = 200
    min_feed_limit: int = 1
    max_feed_limit: int = 20
    min_seed: int = 0
    max_seed: int = 2_147_483_647


DEBUG_RUN_DEFAULTS = DebugRunDefaults()
DEBUG_RUN_LIMITS = DebugRunLimits()


def frontend_options_payload() -> dict[str, object]:
    """导出前端渲染调试面板所需的参数说明。"""

    return {
        "debug_run_defaults": asdict(DEBUG_RUN_DEFAULTS),
        "debug_run_limits": asdict(DEBUG_RUN_LIMITS),
        "allowed_modes": list(ALLOWED_MODES),
        "allowed_providers": list(ALLOWED_PROVIDERS),
        "notes": {
            "mode": "Controls the cognition path: moe tries external providers first, fallback stays local.",
            "llm_provider": "Only used when mode=moe and the provider is available.",
            "enable_fallback": "Allows local fallback if the external provider is unavailable or fails.",
        },
    }
