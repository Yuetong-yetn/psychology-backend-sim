"""仿真场景的数据结构。

场景主要描述三类信息：
- 社会议题本身
- 当前环境背景
- agent 在决策时可感知的上下文
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List


@dataclass
class SimulatedScenario:
    """结构化场景对象。"""

    scenario_id: str
    title: str
    description: str
    environment_context: List[str] = field(default_factory=list)

    def to_prompt(self) -> str:
        """将结构化场景压缩成 agent 可直接阅读的提示文本。"""

        context = " ".join(self.environment_context).strip()
        if context:
            return f"{self.title}. {self.description} Context: {context}"
        return f"{self.title}. {self.description}"

    def to_dict(self) -> dict:
        """导出为普通字典，便于存储和前端展示。"""

        return asdict(self)
