"""最小后端示例。

这个文件展示如何从零启动一次完整实验：

1. 创建 agent
2. 创建 scenario
3. 创建 environment
4. 运行多轮仿真
5. 导出结果

运行方式：
    python examples/start.py
"""

from __future__ import annotations

import json
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)
# 为了确保可以直接从 examples 目录运行脚本，这里手动补上导入路径。
if PARENT_ROOT not in sys.path:
    sys.path.insert(0, PARENT_ROOT)

from Backend.environment.make import make
from Backend.environment.scenario import SimulatedScenario
from Backend.social_agent.agent import AgentProfile, AgentState, SimulatedAgent
from Backend.social_platform.platform import Platform
from Backend.social_platform.storage import SimulationStorage


def build_agents() -> list[SimulatedAgent]:
    """创建一组最小示例 agent。"""
    # 这里手动构造三种不同画像，方便观察不同状态如何影响行为。
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


def main() -> None:
    # 定义一个最小研究场景：
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

    # 组装环境，并附带一个 JSON 导出器。
    env = make(
        agents=build_agents(),
        platform=Platform(feed_limit=4),
        scenario=scenario,
        storage=SimulationStorage(output_dir=os.path.join(PROJECT_ROOT, "outputs")),
    )

    # 先 reset，再推进轮次。
    env.reset()
    env.run(rounds=3)
    export_path = env.export()

    # 打印最终快照，方便直接在终端检查结果。
    payload = env.snapshot()
    payload["export_path"] = export_path
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
