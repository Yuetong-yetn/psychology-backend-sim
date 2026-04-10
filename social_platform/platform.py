"""In-memory platform used by the social simulation backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from Backend.social_platform.emotion_detector import (
    BaseEmotionDetector,
    CompositeEmotionDetector,
    LATENT_DIM,
)
from Backend.services.llm_provider import LLMProvider


@dataclass
class Platform:
    """Minimal platform state and interaction log."""

    feed_limit: int = 5
    current_round: int = 0
    scenario_prompt: str = ""
    agents: Dict[int, str] = field(default_factory=dict)
    posts: List[dict] = field(default_factory=list)
    replies: List[dict] = field(default_factory=list)
    likes: List[dict] = field(default_factory=list)
    shares: List[dict] = field(default_factory=list)
    influence_events: List[dict] = field(default_factory=list)
    traces: List[dict] = field(default_factory=list)
    mode: str = "moe"
    llm_provider: str = "ollama"
    enable_fallback: bool = True
    emotion_detector: BaseEmotionDetector = field(default_factory=CompositeEmotionDetector)
    _post_id_seq: int = 1
    _reply_id_seq: int = 1
    _like_id_seq: int = 1
    _share_id_seq: int = 1

    def __post_init__(self) -> None:
        self.cognitive_provider = LLMProvider(
            llm_provider=self.llm_provider,
            mode=self.mode,
            enable_fallback=self.enable_fallback,
        )

    def reset(self, scenario_prompt: str) -> None:
        self.current_round = 0
        self.scenario_prompt = scenario_prompt
        self.agents.clear()
        self.posts.clear()
        self.replies.clear()
        self.likes.clear()
        self.shares.clear()
        self.influence_events.clear()
        self.traces.clear()
        self._post_id_seq = 1
        self._reply_id_seq = 1
        self._like_id_seq = 1
        self._share_id_seq = 1

    def register_agent(self, agent) -> None:
        self.agents[agent.agent_id] = agent.profile.name
        self.traces.append(
            {
                "round_index": self.current_round,
                "type": "register_agent",
                "agent_id": agent.agent_id,
                "agent_name": agent.profile.name,
            }
        )

    def create_post(
        self,
        author_id: int,
        content: str,
        emotion: str,
        intensity: float,
        sentiment: float,
        emotion_analysis: Optional[dict] = None,
    ) -> dict:
        emotion_payload = self._resolve_emotion_payload(
            content=content,
            emotion=emotion,
            intensity=intensity,
            sentiment=sentiment,
            emotion_analysis=emotion_analysis,
        )
        post = {
            "post_id": self._post_id_seq,
            "author_id": author_id,
            "content": content,
            "emotion": emotion_payload["emotion"],
            "dominant_emotion": emotion_payload["dominant_emotion"],
            "intensity": emotion_payload["intensity"],
            "sentiment": emotion_payload["sentiment"],
            "emotion_probs": emotion_payload["emotion_probs"],
            "pad": emotion_payload["pad"],
            "emotion_latent": emotion_payload["emotion_latent"],
            "like_count": 0,
            "share_count": 0,
            "shared_post_id": None,
            "round_index": self.current_round,
        }
        self._post_id_seq += 1
        self.posts.append(post)
        self.traces.append({"round_index": self.current_round, "type": "create_post", **post})
        return post

    def reply_post(
        self,
        author_id: int,
        post_id: int,
        content: str,
        emotion: str,
        intensity: float,
        sentiment: float,
        emotion_analysis: Optional[dict] = None,
    ) -> dict:
        emotion_payload = self._resolve_emotion_payload(
            content=content,
            emotion=emotion,
            intensity=intensity,
            sentiment=sentiment,
            emotion_analysis=emotion_analysis,
        )
        reply = {
            "reply_id": self._reply_id_seq,
            "post_id": post_id,
            "author_id": author_id,
            "content": content,
            "emotion": emotion_payload["emotion"],
            "dominant_emotion": emotion_payload["dominant_emotion"],
            "intensity": emotion_payload["intensity"],
            "sentiment": emotion_payload["sentiment"],
            "emotion_probs": emotion_payload["emotion_probs"],
            "pad": emotion_payload["pad"],
            "emotion_latent": emotion_payload["emotion_latent"],
            "round_index": self.current_round,
        }
        self._reply_id_seq += 1
        self.replies.append(reply)
        self.traces.append({"round_index": self.current_round, "type": "reply_post", **reply})
        return reply

    def like_post(self, agent_id: int, post_id: int) -> dict:
        existing = next(
            (
                item
                for item in self.likes
                if item["agent_id"] == agent_id and item["post_id"] == post_id
            ),
            None,
        )
        if existing is not None:
            return existing

        like = {
            "like_id": self._like_id_seq,
            "post_id": post_id,
            "agent_id": agent_id,
            "round_index": self.current_round,
        }
        self._like_id_seq += 1
        self.likes.append(like)

        post = self._find_post(post_id)
        if post is not None:
            post["like_count"] += 1

        self.traces.append({"round_index": self.current_round, "type": "like_post", **like})
        return like

    def share_post(
        self,
        agent_id: int,
        post_id: int,
        emotion: str,
        intensity: float,
        sentiment: float,
        content: str | None = None,
        emotion_analysis: Optional[dict] = None,
    ) -> dict:
        original_post = self._find_post(post_id)
        if original_post is None:
            raise ValueError(f"Post {post_id} not found for sharing.")

        share = {
            "share_id": self._share_id_seq,
            "post_id": post_id,
            "agent_id": agent_id,
            "round_index": self.current_round,
        }
        self._share_id_seq += 1
        self.shares.append(share)
        original_post["share_count"] += 1
        share_content = content or f"Shared post #{post_id}: {original_post['content']}"
        emotion_payload = self._resolve_emotion_payload(
            content=share_content,
            emotion=emotion,
            intensity=intensity,
            sentiment=sentiment,
            emotion_analysis=emotion_analysis,
        )

        shared_post = {
            "post_id": self._post_id_seq,
            "author_id": agent_id,
            "content": share_content,
            "emotion": emotion_payload["emotion"],
            "dominant_emotion": emotion_payload["dominant_emotion"],
            "intensity": emotion_payload["intensity"],
            "sentiment": emotion_payload["sentiment"],
            "emotion_probs": emotion_payload["emotion_probs"],
            "pad": emotion_payload["pad"],
            "emotion_latent": emotion_payload["emotion_latent"],
            "like_count": 0,
            "share_count": 0,
            "shared_post_id": post_id,
            "round_index": self.current_round,
        }
        self._post_id_seq += 1
        self.posts.append(shared_post)
        self.traces.append({"round_index": self.current_round, "type": "share_post", **share})
        self.traces.append(
            {"round_index": self.current_round, "type": "create_post", **shared_post}
        )
        return shared_post

    def apply_influence(
        self,
        source_agent_id: int,
        target_agent_id: int,
        delta: float,
        reason: str,
    ) -> dict:
        event = {
            "round_index": self.current_round,
            "source_agent_id": source_agent_id,
            "target_agent_id": target_agent_id,
            "delta": delta,
            "reason": reason,
        }
        self.influence_events.append(event)
        self.traces.append({"type": "apply_influence", **event})
        return event

    def record_idle(self, agent_id: int, reason: str) -> None:
        self.traces.append(
            {
                "round_index": self.current_round,
                "type": "do_nothing",
                "agent_id": agent_id,
                "reason": reason,
            }
        )

    def get_feed_for_agent(self, agent_id: int) -> List[dict]:
        scored_items = []
        for item in self.posts:
            exposure = self._score_exposure(item, agent_id)
            feed_item = dict(item)
            feed_item["exposure_score"] = exposure["score"]
            feed_item["exposure_features"] = exposure["features"]
            scored_items.append(feed_item)

        ordered = sorted(
            scored_items,
            key=lambda item: (
                item.get("exposure_score", 0.0),
                item["round_index"],
                item.get("intensity", 0.0),
                abs(item.get("sentiment", 0.0)),
                item["post_id"],
            ),
            reverse=True,
        )
        return ordered[: self.feed_limit]

    def commit_round(self, round_index: int, round_results: Dict[int, object]) -> None:
        self.traces.append(
            {
                "round_index": round_index,
                "type": "commit_round",
                "agent_ids": sorted(round_results.keys()),
                "post_count": len(self.posts),
                "reply_count": len(self.replies),
                "like_count": len(self.likes),
                "share_count": len(self.shares),
                "influence_count": len(self.influence_events),
            }
        )
        self.current_round = round_index + 1

    def snapshot(self) -> dict:
        return {
            "current_round": self.current_round,
            "scenario_prompt": self.scenario_prompt,
            "agent_count": len(self.agents),
            "agents": self.agents,
            "posts": self.posts,
            "replies": self.replies,
            "likes": self.likes,
            "shares": self.shares,
            "influence_events": self.influence_events,
            "traces": self.traces,
            "trace_size": len(self.traces),
        }

    def _find_post(self, post_id: int) -> dict | None:
        return next((post for post in self.posts if post["post_id"] == post_id), None)

    def _resolve_emotion_payload(
        self,
        content: str,
        emotion: str,
        intensity: float,
        sentiment: float,
        emotion_analysis: Optional[dict] = None,
    ) -> dict:
        internal_signal = self._build_internal_signal(
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

    def _build_internal_signal(
        self,
        emotion: str,
        intensity: float,
        sentiment: float,
        emotion_analysis: Optional[dict],
    ) -> dict:
        payload = {
            "emotion": emotion,
            "dominant_emotion": emotion,
            "intensity": float(intensity),
            "sentiment": float(sentiment),
            "emotion_probs": {},
            "pad": [float(sentiment), float(max(0.0, min(1.0, intensity))), 0.0],
            "emotion_latent": [0.0] * LATENT_DIM,
        }
        if isinstance(emotion_analysis, dict):
            payload.update(dict(emotion_analysis))
        return payload

    def _score_exposure(self, item: dict, agent_id: int) -> dict:
        round_gap = max(0, self.current_round - item.get("round_index", 0))
        recency = self._clamp(1.0 - round_gap * 0.18)
        emotion_salience = self._clamp(
            item.get("intensity", 0.0) * 0.55 + abs(item.get("sentiment", 0.0)) * 0.45
        )
        engagement = self._clamp(
            item.get("like_count", 0) * 0.08 + item.get("share_count", 0) * 0.14
        )
        share_boost = self._clamp(0.2 if item.get("shared_post_id") is not None else 0.0)
        novelty_hint = self._clamp(
            0.3 + abs(item.get("sentiment", 0.0)) * 0.3 + engagement * 0.2
        )
        self_author_penalty = self._clamp(
            0.18 if item.get("author_id") == agent_id else 0.0
        )
        exposure_score = self._clamp(
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
    def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
        return max(minimum, min(maximum, float(value)))
