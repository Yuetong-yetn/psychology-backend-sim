"""最小异步示例。

这个脚本演示如何在代码里直接构造场景、智能体和环境，
并运行一轮最基础的社会心理仿真。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)
# 方便直接执行当前脚本时仍能找到项目根目录下的各个包。
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from environment.make import make
from environment.scenario import SimulatedScenario
from social_agent.agent import AgentProfile, AgentState, SimulatedAgent
from social_agent.agent_graph import AgentGraph
from social_platform.platform import Platform
from social_platform.storage import SimulationStorage


def build_agents() -> list[SimulatedAgent]:
    """构造示例智能体列表。"""

    return [
        SimulatedAgent(
            profile=AgentProfile(
                agent_id=0,
                name="Alex",
                role="journalist",
                ideology="moderate",
                communication_style="analytical",
            ),
            state=AgentState(emotion=0.1, stress=0.2, expectation=0.7),
        ),
        SimulatedAgent(
            profile=AgentProfile(
                agent_id=1,
                name="Bea",
                role="artist",
                ideology="progressive",
                communication_style="expressive",
            ),
            state=AgentState(emotion=-0.1, stress=0.5, expectation=0.45),
        ),
        SimulatedAgent(
            profile=AgentProfile(
                agent_id=2,
                name="Chen",
                role="programmer",
                ideology="conservative",
                communication_style="direct",
            ),
            state=AgentState(emotion=0.05, stress=0.35, expectation=0.55),
        ),
    ]


async def main() -> None:
    """初始化场景并运行一次示例仿真。"""

    scenario = SimulatedScenario(
        scenario_id="aid_policy_001",
        title="News topic: Overseas aid package",
        description=(
            "The government announces a new overseas aid package. "
            "Agents should react based on emotion, stress, expectation, "
            "and what they observe on the platform."
        ),
        environment_context=[
            "Public opinion is divided.",
            "Users can post, browse, reply, and influence each other.",
        ],
    )

    agents = build_agents()
    agent_graph = AgentGraph()
    for agent in agents:
        agent_graph.add_agent(agent)

    env = make(
        agents=agents,
        agent_graph=agent_graph,
        platform=Platform(feed_limit=4),
        scenario=scenario,
        storage=SimulationStorage(output_dir=os.path.join(PROJECT_ROOT, "outputs")),
    )

    await env.areset()
    await env.arun(rounds=3)
    export_path = env.export()
    payload = env.snapshot()
    payload["export_path"] = export_path
    await env.aclose()
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
