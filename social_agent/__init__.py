"""agent 层。

这一层负责定义用户画像、动态状态、记忆和行为决策。
"""

from Backend.social_agent.agent import (
    AppraisalRecord,
    AgentDecision,
    EmotionState,
    AgentProfile,
    AgentRoundResult,
    AgentState,
    MemoryItem,
    SimulatedAgent,
)
from Backend.social_agent.appraisal_moe import AppraisalMoEConfig, AppraisalRouter
from Backend.social_agent.emotion_representation import (
    EmotionRepresentationConfig,
    EmotionRepresentationModule,
)

# 对外暴露 agent 层中最常用的数据结构和核心类。
__all__ = [
    "AppraisalRecord",
    "AgentDecision",
    "EmotionState",
    "AgentProfile",
    "AgentRoundResult",
    "AgentState",
    "MemoryItem",
    "SimulatedAgent",
    "AppraisalMoEConfig",
    "AppraisalRouter",
    "EmotionRepresentationConfig",
    "EmotionRepresentationModule",
]
