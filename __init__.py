"""最小社交仿真后端包。

这个文件是 Backend 的顶层导出入口。
外部如果只想快速使用后端能力，可以直接从这里导入最常用的对象：

- ``make``: 创建环境
- ``Platform``: 创建平台
- ``SimulatedAgent`` / ``AgentProfile``: 创建 agent
"""

from Backend.environment.make import make
from Backend.social_agent.agent import AgentProfile, SimulatedAgent
from Backend.social_platform.platform import Platform

# 统一对外暴露的最小 API 集合。
__all__ = ["make", "Platform", "SimulatedAgent", "AgentProfile"]
