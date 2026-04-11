"""环境层动作描述对象。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from Backend.social_platform.typing import ActionType


@dataclass
class ManualAction:
    """人工指定的动作及其参数。"""

    action_type: ActionType | str  # 动作类型，如 browse_feed / create_post
    action_args: Dict[str, Any] = field(default_factory=dict)  # 动作携带的参数


@dataclass
class LLMAction:
    """占位型动作对象，表示该步仍由模型自行决策。"""

    action_args: Dict[str, Any] = field(default_factory=dict)  # 预留给扩展推理控制参数
