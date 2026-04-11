"""Backend 包的顶层导出。

这里统一暴露环境、平台、智能体和图结构的常用入口，
方便外部脚本直接从 `Backend` 导入核心对象。
"""

from Backend.environment.make import make
from Backend.social_agent.agent import AgentProfile, SimulatedAgent
from Backend.social_agent.agent_graph import AgentGraph
from Backend.social_platform.channel import Channel
from Backend.social_platform.platform import Platform

__all__ = ["make", "Platform", "SimulatedAgent", "AgentProfile", "AgentGraph", "Channel"]
