"""场景数据结构。
相关的场景定义：
- 社会议题
- 环境背景
- 可被 agent 感知的上下文
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List


@dataclass
class SimulatedScenario:
    """研究场景定义。

    一个 scenario 主要描述：
    - 基础社会情境
    - 可供 agent 感知的环境上下文
    """

    scenario_id: str
    title: str
    description: str
    environment_context: List[str] = field(default_factory=list)

    def to_prompt(self) -> str:
        """把结构化场景信息压缩成一段 agent 可直接读取的文本提示。"""
        context = " ".join(self.environment_context).strip()
        if context:
            return f"{self.title}. {self.description} Context: {context}"
        return f"{self.title}. {self.description}"

    def to_dict(self) -> dict:
        """导出为普通字典，便于序列化存储或前端展示。"""
        return asdict(self)
