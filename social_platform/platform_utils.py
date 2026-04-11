"""平台层的辅助函数集合。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from Backend.social_platform.emotion_detector import BaseEmotionDetector, LATENT_DIM

if TYPE_CHECKING:
    from Backend.services.llm_provider import LLMProvider


class PlatformUtils:
    """平台层共用工具，负责情绪解析和曝光打分等逻辑。"""

    def __init__(
        self,
        *,
        emotion_detector: BaseEmotionDetector,
        cognitive_provider: LLMProvider,
    ) -> None:
        self.emotion_detector = emotion_detector
        self.cognitive_provider = cognitive_provider

    def find_post(self, posts: list[dict], post_id: int) -> dict | None:
        """按 `post_id` 查找帖子。"""
        return next((post for post in posts if post["post_id"] == post_id), None)

    def resolve_emotion_payload(
        self,
        *,
        content: str,
        emotion: str,
        intensity: float,
        sentiment: float,
        emotion_analysis: Optional[dict] = None,
    ) -> dict:
        """把文本和 agent 自报情绪整合成平台侧统一情绪载荷。"""
        internal_signal = self.build_internal_signal(
            emotion=emotion,
            intensity=intensity,
            sentiment=sentiment,
            emotion_analysis=emotion_analysis,
        )
        analysis = self.cognitive_provider.analyze_emotion(
            {
                "text": content,
                "internal_signal": internal_signal,
            },
            fallback_fn=lambda payload: self.emotion_detector.analyze_text(
                str(payload.get("text", "")),
                overrides={"internal_signal": payload.get("internal_signal")},
            ).to_dict(),
        )

        return {
            "emotion": analysis.get("dominant_emotion", emotion),
            "dominant_emotion": analysis.get("dominant_emotion", emotion),
            "intensity": float(analysis.get("intensity", intensity)),
            "sentiment": float(analysis.get("sentiment", sentiment)),
            "emotion_probs": dict(analysis.get("emotion_probs", {})),
            "pad": [float(item) for item in analysis.get("pad", [0.0, 0.0, 0.0])],
            "emotion_latent": [
                float(item) for item in analysis.get("emotion_latent", [0.0] * LATENT_DIM)
            ],
        }

    def build_internal_signal(
        self,
        *,
        emotion: str,
        intensity: float,
        sentiment: float,
        emotion_analysis: Optional[dict],
    ) -> dict:
        """构造平台情绪分析器可消费的内部信号。"""
        payload = {
            "emotion": emotion,
            "dominant_emotion": emotion,
            "intensity": float(intensity),
            "sentiment": float(sentiment),
            "emotion_probs": {},
            "pad": [float(sentiment), float(self.clamp(intensity)), 0.0],
            "emotion_latent": [0.0] * LATENT_DIM,
        }
        if isinstance(emotion_analysis, dict):
            payload.update(dict(emotion_analysis))
        return payload

    def score_exposure(self, item: dict, agent_id: int, current_round: int) -> dict:
        """为帖子计算曝光分及其特征拆解。"""

        round_gap = max(0, current_round - item.get("round_index", 0))
        # 曝光分综合考虑时效性、情绪显著性、互动量和是否是转发内容。
        recency = self.clamp(1.0 - round_gap * 0.18)
        emotion_salience = self.clamp(
            item.get("intensity", 0.0) * 0.55 + abs(item.get("sentiment", 0.0)) * 0.45
        )
        engagement = self.clamp(
            item.get("like_count", 0) * 0.08 + item.get("share_count", 0) * 0.14
        )
        share_boost = self.clamp(0.2 if item.get("shared_post_id") is not None else 0.0)
        novelty_hint = self.clamp(
            0.3 + abs(item.get("sentiment", 0.0)) * 0.3 + engagement * 0.2
        )
        self_author_penalty = self.clamp(0.18 if item.get("author_id") == agent_id else 0.0)
        exposure_score = self.clamp(
            recency * 0.34
            + emotion_salience * 0.24
            + engagement * 0.18
            + share_boost * 0.1
            + novelty_hint * 0.14
            - self_author_penalty
        )
        return {
            "score": exposure_score,
            "features": {
                "recency": recency,
                "emotion_salience": emotion_salience,
                "engagement": engagement,
                "share_boost": share_boost,
                "novelty_hint": novelty_hint,
                "self_author_penalty": self_author_penalty,
            },
        }

    @staticmethod
    def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
        """把数值限制到指定区间。"""
        return max(minimum, min(maximum, float(value)))
