"""环境调度层。

这个文件对应 OASIS 中的 environment/env.py。
它不直接实现平台业务，也不直接决定 agent 的行为，
而是负责把三层串起来，组织每轮仿真的执行顺序。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from Backend.environment.scenario import SimulatedScenario
from Backend.social_agent.agent import AgentRoundResult, SimulatedAgent
from Backend.social_platform.platform import Platform
from Backend.social_platform.storage import SimulationStorage


@dataclass
class SimulationEnv:
    """最小社交仿真环境。

    每轮执行顺序：
    1. agent 接收平台信息
    2. agent 更新内部状态
    3. agent 执行动作
    4. 环境记录本轮结果
    """

    agents: List[SimulatedAgent]
    platform: Platform
    scenario_prompt: str = ""
    scenario: SimulatedScenario | None = None
    storage: SimulationStorage | None = None
    round_index: int = 0
    history: List[dict] = field(default_factory=list)

    def reset(self) -> None:
        """初始化环境，把场景信息写入平台，并注册所有 agent。"""
        # reset 只负责准备工作，不推进任何轮次。
        self.round_index = 0
        self.history.clear()
        prompt = self._get_scenario_prompt()
        self.platform.reset(scenario_prompt=prompt)
        for agent in self.agents:
            self.platform.register_agent(agent)

    def step(self) -> Dict[int, AgentRoundResult]:
        """执行一轮完整仿真。"""
        round_results: Dict[int, AgentRoundResult] = {}

        # 逐个 agent 获取 feed，并完成“感知 -> 更新 -> 决策 -> 行动”。
        for agent in self.agents:
            feed = self.platform.get_feed_for_agent(agent.agent_id)
            result = agent.run_round(
                round_index=self.round_index,
                scenario_prompt=self._get_scenario_prompt(),
                feed=feed,
                platform=self.platform,
            )
            round_results[agent.agent_id] = result

        self.platform.commit_round(
            round_index=self.round_index,
            round_results=round_results,
        )
        self.history.append(
            {
                "round_index": self.round_index,
                "results": {
                    agent_id: result.to_dict()
                    for agent_id, result in round_results.items()
                },
            }
        )
        self.round_index += 1
        return round_results

    def run(self, rounds: int) -> List[Dict[int, AgentRoundResult]]:
        """连续运行多轮仿真。"""
        outputs: List[Dict[int, AgentRoundResult]] = []
        for _ in range(rounds):
            outputs.append(self.step())
        return outputs

    def export(self, filename: str = "simulation_snapshot.json") -> str | None:
        """导出完整快照到 JSON。"""
        if self.storage is None:
            return None
        return self.storage.save_json(filename, self.snapshot())

    def snapshot(self) -> dict:
        """返回当前环境的整体状态快照。"""
        # snapshot 适合作为调试输出，也适合作为后续前端/分析脚本的输入。
        return {
            "round_index": self.round_index,
            "scenario_prompt": self._get_scenario_prompt(),
            "scenario": self.scenario.to_dict() if self.scenario else None,
            "platform": self.platform.snapshot(),
            "agents": [agent.snapshot() for agent in self.agents],
            "history": self.history,
        }

    def _get_scenario_prompt(self) -> str:
        """统一获取场景提示词。

        优先使用结构化 scenario；如果没有，再退回到普通字符串 scenario_prompt。
        """
        if self.scenario is not None:
            return self.scenario.to_prompt()
        return self.scenario_prompt
