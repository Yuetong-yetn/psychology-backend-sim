"""平台层的辅助函数集合。"""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Callable, Optional

from .emotion_detector import BaseEmotionDetector, LATENT_DIM

if TYPE_CHECKING:
    from services.llm_provider import LLMProvider


ProfileHook = Callable[[str, float], None]
CountHook = Callable[[str, int], None]


class PlatformUtils:
    """平台层共用工具，负责情绪解析和曝光打分等逻辑。"""

    def __init__(
        self,
        *,
        emotion_detector: BaseEmotionDetector,
        cognitive_provider: LLMProvider,
        profile_hook: ProfileHook | None = None,
        count_hook: CountHook | None = None,
        emotion_cache_size: int = 512,
    ) -> None:
        self.emotion_detector = emotion_detector
        self.cognitive_provider = cognitive_provider
        self.profile_hook = profile_hook
        self.count_hook = count_hook
        self.emotion_cache_size = max(1, int(emotion_cache_size))
        self._emotion_payload_cache: OrderedDict[str, dict] = OrderedDict()

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
        cache_key = self._emotion_cache_key(
            content=content,
            emotion=emotion,
            intensity=intensity,
            sentiment=sentiment,
            emotion_analysis=emotion_analysis,
        )
        cached = self._emotion_payload_cache.get(cache_key)
        if cached is not None:
            self._emotion_payload_cache.move_to_end(cache_key)
            self._count("emotion_payload_cache_hit")
            return dict(cached)

        internal_signal = self.build_internal_signal(
            emotion=emotion,
            intensity=intensity,
            sentiment=sentiment,
            emotion_analysis=emotion_analysis,
        )
        analysis = self._normalize_analysis_payload(
            internal_signal=internal_signal,
            content=content,
            emotion=emotion,
            intensity=intensity,
            sentiment=sentiment,
            emotion_analysis=emotion_analysis,
        )

        resolved = {
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
        self._emotion_payload_cache[cache_key] = dict(resolved)
        self._emotion_payload_cache.move_to_end(cache_key)
        while len(self._emotion_payload_cache) > self.emotion_cache_size:
            self._emotion_payload_cache.popitem(last=False)
        self._count("emotion_payload_cache_miss")
        return resolved

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

    def _normalize_analysis_payload(
        self,
        *,
        internal_signal: dict,
        content: str,
        emotion: str,
        intensity: float,
        sentiment: float,
        emotion_analysis: Optional[dict],
    ) -> dict:
        if self._has_complete_emotion_analysis(emotion_analysis):
            self._count("emotion_analysis_reused")
            return dict(emotion_analysis)

        self._count("emotion_analysis_fallback")
        start = time.perf_counter()
        try:
            return self.cognitive_provider.analyze_emotion(
                {
                    "text": content,
                    "internal_signal": internal_signal,
                },
                fallback_fn=lambda payload: self.emotion_detector.analyze_text(
                    str(payload.get("text", "")),
                    overrides={"internal_signal": payload.get("internal_signal")},
                ).to_dict(),
            )
        finally:
            self._profile("analyze_emotion", time.perf_counter() - start)

    @staticmethod
    def _has_complete_emotion_analysis(emotion_analysis: Optional[dict]) -> bool:
        if not isinstance(emotion_analysis, dict):
            return False
        required = {"dominant_emotion", "intensity", "sentiment", "emotion_probs", "pad", "emotion_latent"}
        if not required.issubset(emotion_analysis):
            return False
        pad = emotion_analysis.get("pad")
        latent = emotion_analysis.get("emotion_latent")
        return isinstance(pad, list) and len(pad) == 3 and isinstance(latent, list) and len(latent) == LATENT_DIM

    def _emotion_cache_key(
        self,
        *,
        content: str,
        emotion: str,
        intensity: float,
        sentiment: float,
        emotion_analysis: Optional[dict],
    ) -> str:
        payload = {
            "content": content,
            "emotion": emotion,
            "intensity": round(float(intensity), 6),
            "sentiment": round(float(sentiment), 6),
            "emotion_analysis": emotion_analysis if isinstance(emotion_analysis, dict) else None,
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    def _profile(self, metric: str, duration: float) -> None:
        if self.profile_hook is not None:
            self.profile_hook(metric, duration)

    def _count(self, metric: str, value: int = 1) -> None:
        if self.count_hook is not None:
            self.count_hook(metric, value)

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
