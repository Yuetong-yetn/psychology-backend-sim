"""为后端智能体图绑定运行时通道的辅助函数。"""

from __future__ import annotations

import math
from typing import Any

from .agent import AgentProfile, AgentState, SimulatedAgent
from .agent_graph import AgentGraph
from social_platform.channel import Channel


def connect_platform_channel(
    channel: Channel,
    agent_graph: AgentGraph | None = None,
) -> AgentGraph:
    """把已有 agent 图中的每个智能体都绑定到平台通道。"""

    agent_graph = agent_graph or AgentGraph()
    for _, agent in agent_graph.get_agents():
        if hasattr(agent, "bind_runtime"):
            agent.bind_runtime(channel=channel, agent_graph=agent_graph)
    return agent_graph


async def generate_custom_agents(
    channel: Channel,
    agent_graph: AgentGraph | None = None,
) -> AgentGraph:
    """兼容旧接口，内部仍复用 `connect_platform_channel`。"""

    return connect_platform_channel(channel=channel, agent_graph=agent_graph)


async def generate_backend_agent_graph(
    payload: dict[str, Any],
    runtime: dict[str, Any] | None = None,
) -> AgentGraph:
    """根据输入 payload 构造智能体图和关注关系。"""

    runtime = runtime or {}
    graph = AgentGraph()
    agent_rows = list(payload.get("agents", []))
    ratio = max(0.0, min(1.0, float(runtime.get("appraisal_llm_ratio", 0.1))))
    llm_agent_count = 0
    if str(runtime.get("mode", "fallback")) != "fallback" and agent_rows and ratio > 0.0:
        llm_agent_count = min(len(agent_rows), max(1, math.ceil(len(agent_rows) * ratio)))
    for index, row in enumerate(agent_rows):
        # 这里把 JSON 行记录恢复成可运行的 `SimulatedAgent` 对象。
        profile = AgentProfile(
            agent_id=int(row["agent_id"]),
            name=str(row["name"]),
            role=str(row["role"]),
            ideology=str(row["ideology"]),
            communication_style=str(row.get("communication_style", "balanced")),
        )
        state = AgentState(**dict(row.get("initial_state", {})))
        agent = SimulatedAgent(
            profile=profile,
            state=state,
            mode=str(runtime.get("mode", "fallback")),
            llm_provider=str(runtime.get("llm_provider", "ollama")),
            enable_fallback=bool(runtime.get("enable_fallback", True)),
            appraisal_use_llm=index < llm_agent_count,
        )
        graph.add_agent(agent)

    for edge in list(payload.get("relationships", [])):
        source_id = int(edge.get("source_agent_id"))
        target_id = int(edge.get("target_agent_id"))
        graph.add_edge(source_id, target_id)

    return graph
