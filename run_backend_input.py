#!/usr/bin/env python3
"""Run the backend from a backend-native input JSON payload."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_ROOT = CURRENT_DIR.parent
if str(PARENT_ROOT) not in sys.path:
    sys.path.insert(0, str(PARENT_ROOT))

from Backend.environment.make import make
from Backend.environment.scenario import SimulatedScenario
from Backend.social_agent.agent import AgentProfile, AgentState, SimulatedAgent
from Backend.social_platform.platform import Platform
from Backend.social_platform.storage import SimulationStorage


def _build_agent(row: dict[str, object], runtime: dict[str, object]) -> SimulatedAgent:
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


def _seed_platform_posts(platform: Platform, seed_posts: list[dict[str, object]]) -> None:
    for row in seed_posts:
        platform.create_post(
            author_id=int(row["author_id"]),
            content=str(row["content"]),
            emotion=str(row.get("emotion", "calm")),
            intensity=float(row.get("intensity", 0.2)),
            sentiment=float(row.get("sentiment", 0.0)),
        )


def run_from_payload(payload: dict[str, object]) -> dict[str, object]:
    runtime = dict(payload.get("runtime", {}))
    scenario_row = dict(payload["scenario"])
    scenario = SimulatedScenario(
        scenario_id=str(scenario_row["scenario_id"]),
        title=str(scenario_row["title"]),
        description=str(scenario_row["description"]),
        environment_context=list(scenario_row.get("environment_context", [])),
    )
    agents = [_build_agent(row, runtime) for row in list(payload.get("agents", []))]
    platform = Platform(
        feed_limit=int(runtime.get("feed_limit", 5)),
        mode=str(runtime.get("mode", "fallback")),
        llm_provider=str(runtime.get("llm_provider", "ollama")),
        enable_fallback=bool(runtime.get("enable_fallback", True)),
    )
    storage = SimulationStorage(output_dir=os.path.join(str(CURRENT_DIR), "outputs"))
    env = make(agents=agents, platform=platform, scenario=scenario, storage=storage)
    env.reset()
    _seed_platform_posts(platform, list(payload.get("seed_posts", [])))
    rounds = int(dict(payload.get("meta", {})).get("rounds", 3))
    env.run(rounds=rounds)
    export_path = env.export()
    snapshot = env.snapshot()
    snapshot["export_path"] = export_path
    return snapshot


def main() -> None:
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
    snapshot = run_from_payload(payload)
    if args.output is not None:
        args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
