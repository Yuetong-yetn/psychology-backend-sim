#!/usr/bin/env python3
"""从后端原生输入运行一次完整仿真。

负责把 JSON payload 组装成环境、平台和智能体对象，
并执行完整的异步仿真流程；必要时还会汇报阶段性进度。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Awaitable, Callable

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_ROOT = CURRENT_DIR.parent
if str(PARENT_ROOT) not in sys.path:
    sys.path.insert(0, str(PARENT_ROOT))

from config.backend_settings import BACKEND_IO
from environment.make import make
from environment.scenario import SimulatedScenario
from social_agent.agent import AgentProfile, AgentState, SimulatedAgent
from social_agent.agent_graph import AgentGraph
from social_platform.platform import Platform
from social_platform.storage import SimulationStorage

ProgressCallback = Callable[[dict[str, object]], Awaitable[None] | None]


def _build_agent(row: dict[str, object], runtime: dict[str, object]) -> SimulatedAgent:
    """根据输入协议中的一行智能体数据构造运行时对象。"""

    profile = AgentProfile(
        agent_id=int(row["agent_id"]),
        name=str(row["name"]),
        role=str(row["role"]),
        ideology=str(row["ideology"]),
        communication_style=str(row.get("communication_style", "balanced")),
    )
    state = AgentState(**dict(row.get("initial_state", {})))
    return SimulatedAgent(
        profile=profile,
        state=state,
        mode=str(runtime.get("mode", "fallback")),
        llm_provider=str(runtime.get("llm_provider", "ollama")),
        enable_fallback=bool(runtime.get("enable_fallback", True)),
    )


async def _seed_platform_posts(env, seed_posts: list[dict[str, object]]) -> None:
    """把种子帖子注入平台。"""

    for row in seed_posts:
        await env._dispatch_platform_action(
            agent_id=int(row["author_id"]),
            action_name="create_post",
            payload={
                "content": str(row["content"]),
                "emotion": str(row.get("emotion", "calm")),
                "intensity": float(row.get("intensity", 0.2)),
                "sentiment": float(row.get("sentiment", 0.0)),
            },
        )


async def _emit_progress(
    progress_callback: ProgressCallback | None,
    payload: dict[str, object],
) -> None:
    """向外部回调当前仿真进度。"""

    if progress_callback is None:
        return
    maybe_awaitable = progress_callback(payload)
    if maybe_awaitable is not None:
        await maybe_awaitable


async def run_from_payload_async(
    payload: dict[str, object],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, object]:
    """根据 payload 异步执行一次仿真。"""

    runtime = dict(payload.get("runtime", {}))
    await _emit_progress(
        progress_callback,
        {
            "stage": "preparing",
            "progress": 0.05,
            "message": "Preparing scenario, agents, and platform",
        },
    )

    scenario_row = dict(payload["scenario"])
    scenario = SimulatedScenario(
        scenario_id=str(scenario_row["scenario_id"]),
        title=str(scenario_row["title"]),
        description=str(scenario_row["description"]),
        environment_context=list(scenario_row.get("environment_context", [])),
    )
    agents = [_build_agent(row, runtime) for row in list(payload.get("agents", []))]

    agent_graph = AgentGraph()
    for agent in agents:
        agent_graph.add_agent(agent)
    for edge in list(payload.get("relationships", [])):
        agent_graph.add_edge(
            int(edge.get("source_agent_id")),
            int(edge.get("target_agent_id")),
        )

    platform = Platform(
        feed_limit=int(runtime.get("feed_limit", 5)),
        mode=str(runtime.get("mode", "fallback")),
        llm_provider=str(runtime.get("llm_provider", "ollama")),
        enable_fallback=bool(runtime.get("enable_fallback", True)),
    )
    storage = SimulationStorage(output_dir=os.path.join(str(CURRENT_DIR), BACKEND_IO.outputs_dir_name))
    env = make(
        agents=agents,
        agent_graph=agent_graph,
        platform=platform,
        scenario=scenario,
        storage=storage,
    )

    await env.areset()
    await _emit_progress(
        progress_callback,
        {
            "stage": "seeding_posts",
            "progress": 0.1,
            "message": "Seeding initial platform posts",
        },
    )
    await _seed_platform_posts(env, list(payload.get("seed_posts", [])))

    rounds = int(dict(payload.get("meta", {})).get("rounds", 3))
    await _emit_progress(
        progress_callback,
        {
            "stage": "running_rounds",
            "completed_rounds": 0,
            "total_rounds": rounds,
            "progress": 0.15,
            "message": f"Starting simulation rounds (0/{rounds})",
        },
    )

    await env.arun(rounds=rounds, progress_callback=progress_callback)
    await _emit_progress(
        progress_callback,
        {
            "stage": "exporting",
            "progress": 0.95,
            "message": "Exporting simulation snapshot",
        },
    )
    export_path = env.export(filename=BACKEND_IO.exported_snapshot_name)
    snapshot = env.snapshot()
    snapshot["export_path"] = export_path
    await env.aclose()

    await _emit_progress(
        progress_callback,
        {
            "stage": "completed",
            "progress": 1.0,
            "message": "Simulation completed",
        },
    )
    return snapshot


def main() -> None:
    """命令行入口。"""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=CURRENT_DIR / "examples" / "backend_sample_input.json",
    )
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    snapshot = asyncio.run(run_from_payload_async(payload))
    if args.output is not None:
        args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
