"""平台层。

这一层负责承载平台状态、帖子流、互动记录和导出能力。
"""

from Backend.social_platform.platform import Platform
from Backend.social_platform.storage import SimulationStorage
from Backend.social_platform.typing import ActionType
from Backend.social_platform.emotion_detector import (
    BaseEmotionDetector,
    CompositeEmotionDetector,
    EmotionAnalysis,
    HeuristicContextEmotionDetector,
    RuleBasedEmotionDetector,
)

# 对外暴露平台层的核心组件。
__all__ = [
    "Platform",
    "SimulationStorage",
    "ActionType",
    "BaseEmotionDetector",
    "CompositeEmotionDetector",
    "EmotionAnalysis",
    "HeuristicContextEmotionDetector",
    "RuleBasedEmotionDetector",
]
