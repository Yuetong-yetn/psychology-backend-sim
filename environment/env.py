"""异步环境编排层。

该模块负责统一组织仿真的生命周期，包括环境重置、轮次推进、
平台动作派发、结果提交、快照导出以及运行进度回调。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List

from config.backend_settings import ENVIRONMENT_DEFAULTS
from environment.env_action import LLMAction, ManualAction
from environment.scenario import SimulatedScenario
from social_agent.agent import AgentRoundResult, SimulatedAgent
from social_agent.agent_graph import AgentGraph
from social_agent.agents_generator import generate_custom_agents
from social_platform.platform import Platform
from social_platform.storage import SimulationStorage

ProgressCallback = Callable[[dict[str, object]], Awaitable[None] | None]


@dataclass
class SimulationEnv:
    """后端仿真环境。

    该类通过异步生命周期方法管理整场仿真，并协调智能体、
    平台、场景和存储之间的交互。
    """

    agents: List[SimulatedAgent] | None = None
    platform: Platform = field(default_factory=Platform)
    scenario_prompt: str = ""
    scenario: SimulatedScenario | None = None
    storage: SimulationStorage | None = None
    round_index: int = 0
    history: List[dict] = field(default_factory=list)
    agent_graph: AgentGraph | None = None
    semaphore: int = ENVIRONMENT_DEFAULTS.llm_semaphore

    def __post_init__(self) -> None:
        """补全环境初始化后的派生状态。"""
        if self.agent_graph is None:
            self.agent_graph = AgentGraph()
            for agent in self.agents or []:
                self.agent_graph.add_agent(agent)
        elif self.agents is None:
            self.agents = [agent for _, agent in self.agent_graph.get_agents()]
        else:
            existing_ids = {agent_id for agent_id, _ in self.agent_graph.get_agents()}
            for agent in self.agents:
                if agent.agent_id not in existing_ids:
                    self.agent_graph.add_agent(agent)
        self.agents = self.agents or [agent for _, agent in self.agent_graph.get_agents()]
        # 用信号量限制并发推理数量，避免一次性把所有 agent 都压到线程池里。
        self._llm_semaphore = asyncio.Semaphore(self.semaphore)
        self._platform_task: asyncio.Task | None = None

    async def areset(self) -> None:
        """异步重置环境状态。

        该方法会重置平台、绑定智能体运行时依赖，并准备新一轮仿真。
        """
        self.round_index = 0
        self.history.clear()
        prompt = self._get_scenario_prompt()
        self.platform.reset(scenario_prompt=prompt)
        if self._platform_task is None or self._platform_task.done():
            # 平台侧使用一个常驻异步任务，循环处理来自 agent 的动作请求。
            self._platform_task = asyncio.create_task(self.platform.running())
        self.agent_graph = await generate_custom_agents(
            channel=self.platform.channel,
            agent_graph=self.agent_graph,
        )
        self.agents = [agent for _, agent in self.agent_graph.get_agents()]
        for _, agent in self.agent_graph.get_agents():
            agent.bind_runtime(
                channel=self.platform.channel,
                agent_graph=self.agent_graph,
                platform=self.platform,
            )
            # 每个 agent 在正式开跑前先向平台注册，确保 feed 和 trace 中能识别身份。
            await agent.action.register_agent(agent.profile.name)

    def _run_single_agent_round(
        self,
        agent: SimulatedAgent,
        round_index: int,
        feed: List[dict],
    ) -> AgentRoundResult:
        """执行单个智能体的一轮本地决策。

        Args:
            agent: 当前待执行的智能体。
            round_index: 当前轮次编号。
            feed: 当前智能体可见的信息流。

        Returns:
            智能体该轮的结构化结果。
        """
        return agent.run_round(
            round_index=round_index,
            scenario_prompt=self._get_scenario_prompt(),
            feed=feed,
        )

    async def _dispatch_platform_action(
        self,
        agent_id: int,
        action_name: str,
        payload: dict | None = None,
    ) -> dict:
        """向平台发送一个动作请求并等待结果。"""
        message_id = await self.platform.channel.write_to_receive_queue(
            (agent_id, payload or {}, action_name)
        )
        _message_id, _agent_id, result = await self.platform.channel.read_from_send_queue(message_id)
        return dict(result)

    async def _dispatch_agent_result(
        self,
        result: AgentRoundResult,
        round_index: int,
    ) -> None:
        """将智能体轮次结果回写到平台侧动作层。"""
        agent = self.agent_graph.get_agent(result.profile.agent_id)
        await agent.action.apply_decision(result.decision, round_index)

    def _finalize_round(
        self,
        round_results: Dict[int, AgentRoundResult],
        round_index: int,
    ) -> Dict[int, AgentRoundResult]:
        """提交轮次结果并更新环境历史。"""
        self.platform.commit_round(
            round_index=round_index,
            round_results=round_results,
        )
        self.history.append(
            {
                "round_index": round_index,
                "results": {
                    agent_id: result.to_dict()
                    for agent_id, result in round_results.items()
                },
            }
        )
        self.round_index = round_index + 1
        return round_results

    async def _perform_llm_action(
        self,
        agent: SimulatedAgent,
        round_index: int,
        feed: List[dict],
    ) -> AgentRoundResult:
        """在并发信号量控制下执行单个智能体轮次。"""
        async with self._llm_semaphore:
            return await asyncio.to_thread(self._run_single_agent_round, agent, round_index, feed)

    async def astep(
        self,
        actions: dict[SimulatedAgent, ManualAction | LLMAction | List[ManualAction | LLMAction]] | None = None,
    ) -> Dict[int, AgentRoundResult]:
        """推进一轮仿真。

        Args:
            actions: 可选的人工动作集合。

        Returns:
            当前轮次所有智能体的结果映射。
        """
        round_index = self.round_index
        if actions:
            await self._perform_manual_actions(actions)

        # 先收集所有 agent 的观察，再并行推进各自轮次，避免先后顺序影响可见 feed。
        feeds = await asyncio.gather(
            *(agent.environment.get_feed() for _, agent in self.agent_graph.get_agents())
        )
        agent_entries = list(self.agent_graph.get_agents())
        tasks = [
            self._perform_llm_action(agent, round_index, feed)
            for (_, agent), feed in zip(agent_entries, feeds)
        ]
        results = await asyncio.gather(*tasks)
        # 决策完成后，再统一把动作提交给平台。
        await asyncio.gather(
            *(self._dispatch_agent_result(result, round_index) for result in results)
        )
        round_results = {result.profile.agent_id: result for result in results}
        return self._finalize_round(round_results, round_index)

    async def arun(
        self,
        rounds: int,
        progress_callback: ProgressCallback | None = None,
    ) -> List[Dict[int, AgentRoundResult]]:
        """连续运行多轮仿真。

        Args:
            rounds: 需要执行的轮次数。
            progress_callback: 可选的进度回调函数。

        Returns:
            每轮结果组成的列表。
        """
        outputs: List[Dict[int, AgentRoundResult]] = []
        for index in range(rounds):
            outputs.append(await self.astep())
            if progress_callback is not None:
                payload = {
                    "stage": "running_rounds",
                    "completed_rounds": index + 1,
                    "total_rounds": rounds,
                    "progress": 0.15 + ((index + 1) / max(1, rounds)) * 0.75,
                    "message": f"Completed round {index + 1}/{rounds}",
                }
                maybe_awaitable = progress_callback(payload)
                if maybe_awaitable is not None:
                    await maybe_awaitable
        return outputs

    async def _perform_manual_actions(
        self,
        actions: dict[SimulatedAgent, ManualAction | LLMAction | List[ManualAction | LLMAction]],
    ) -> None:
        """执行用户显式传入的人工动作。"""
        for agent, action in actions.items():
            entries = action if isinstance(action, list) else [action]
            for item in entries:
                if isinstance(item, LLMAction):
                    # `LLMAction` 只是占位符，不会在这里直接派发平台动作。
                    continue
                action_type = (
                    item.action_type.value
                    if hasattr(item.action_type, "value")
                    else str(item.action_type)
                )
                message_id = await self.platform.channel.write_to_receive_queue(
                    (agent.agent_id, dict(item.action_args), action_type)
                )
                await self.platform.channel.read_from_send_queue(message_id)

    async def aclose(self) -> None:
        """异步关闭环境及其后台平台任务。"""
        if self._platform_task is None:
            return
        # 通过特殊退出消息让平台任务优雅结束，而不是直接取消协程。
        message_id = await self.platform.channel.write_to_receive_queue((None, None, "__exit__"))
        await self.platform.channel.read_from_send_queue(message_id)
        await self._platform_task
        self._platform_task = None

    def export(self, filename: str = "simulation_snapshot.json") -> str | None:
        """导出当前快照到存储层。

        Args:
            filename: 导出文件名。

        Returns:
            导出文件路径；若未配置存储则返回 `None`。
        """
        if self.storage is None:
            return None
        return self.storage.save_json(filename, self.snapshot())

    def snapshot(self) -> dict:
        """生成当前环境的完整快照。"""
        return {
            "round_index": self.round_index,
            "scenario_prompt": self._get_scenario_prompt(),
            "scenario": self.scenario.to_dict() if self.scenario else None,
            "platform": self.platform.snapshot(),
            "agent_graph": {
                "num_nodes": self.agent_graph.get_num_nodes(),
                "num_edges": self.agent_graph.get_num_edges(),
                "edges": self.agent_graph.get_edges(),
            },
            "agents": [agent.snapshot() for _, agent in self.agent_graph.get_agents()],
            "history": self.history,
        }

    def _get_scenario_prompt(self) -> str:
        """获取当前场景提示文本。"""
        if self.scenario is not None:
            return self.scenario.to_prompt()
        return self.scenario_prompt
