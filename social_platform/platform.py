"""浠跨湡鍚庣浣跨敤鐨勫唴瀛樺钩鍙般€?"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .action_dispatcher import PlatformActionDispatcher
from .channel import Channel
from .emotion_detector import BaseEmotionDetector, CompositeEmotionDetector
from .platform_utils import PlatformUtils
from services.llm_provider import LLMProvider


@dataclass
class Platform:
    """缁存姢甯栧瓙銆佷簰鍔ㄥ拰 trace 鐨勫钩鍙扮姸鎬佸鍣ㄣ€?"""

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
    channel: Channel | None = None
    emotion_detector: BaseEmotionDetector = field(default_factory=CompositeEmotionDetector)
    _post_id_seq: int = 1
    _reply_id_seq: int = 1
    _like_id_seq: int = 1
    _share_id_seq: int = 1
    runtime_profile: Dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cognitive_provider = LLMProvider(
            llm_provider=self.llm_provider,
            mode=self.mode,
            enable_fallback=self.enable_fallback,
        )
        self.channel = self.channel or Channel()
        self.platform_utils = PlatformUtils(
            emotion_detector=self.emotion_detector,
            cognitive_provider=self.cognitive_provider,
            profile_hook=self._profile_timing,
            count_hook=self._profile_count,
        )
        self.action_dispatcher = PlatformActionDispatcher(self)
        self._action_lock = asyncio.Lock()

    def reset(self, scenario_prompt: str) -> None:
        """閲嶇疆骞冲彴鐘舵€侊紝涓烘柊涓€杞豢鐪熷仛鍑嗗銆?"""
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
        self.runtime_profile.clear()

    def register_agent(
        self,
        agent=None,
        agent_id: int | None = None,
        agent_name: str | None = None,
    ) -> dict:
        """鐧昏骞冲彴鍙鐨?agent 韬唤銆?"""
        if agent is not None:
            agent_id = int(agent.agent_id)
            agent_name = str(agent.profile.name)
        if agent_id is None:
            raise ValueError("agent_id is required when agent is not provided.")
        self.agents[int(agent_id)] = str(agent_name or f"agent_{agent_id}")
        self.traces.append(
            {
                "round_index": self.current_round,
                "type": "register_agent",
                "agent_id": int(agent_id),
                "agent_name": str(agent_name or f"agent_{agent_id}"),
            }
        )
        return {"success": True, "agent_id": int(agent_id), "agent_name": self.agents[int(agent_id)]}

    async def sign_up(
        self,
        agent_id: int,
        user_message: tuple[str, str] | tuple[str, str, str] | str,
    ) -> dict:
        """鍏煎鏃ф帴鍙ｇ殑娉ㄥ唽鍏ュ彛銆?"""
        if isinstance(user_message, str):
            return self.register_agent(agent_id=agent_id, agent_name=user_message)
        if isinstance(user_message, tuple):
            if len(user_message) >= 2:
                return self.register_agent(agent_id=agent_id, agent_name=str(user_message[1]))
            if len(user_message) == 1:
                return self.register_agent(agent_id=agent_id, agent_name=str(user_message[0]))
        return self.register_agent(agent_id=agent_id, agent_name=f"agent_{agent_id}")

    def browse_feed(self, agent_id: int) -> dict:
        """杩斿洖鏌愪釜 agent 褰撳墠鍙鐨勪俊鎭祦銆?"""
        return {"success": True, "feed": self.get_feed_for_agent(agent_id)}

    async def running(self) -> None:
        """鎸佺画娑堣垂閫氶亾涓殑骞冲彴鍔ㄤ綔璇锋眰銆?"""
        while True:
            message_id, data = await self.channel.receive_from()
            if not isinstance(data, tuple) or len(data) < 3:
                await self.channel.send_to((message_id, None, {"success": False, "error": "Invalid message"}))
                continue

            agent_id, message, action = data
            action_name = str(action)
            if action_name == "__exit__":
                await self.channel.send_to((message_id, agent_id, {"success": True}))
                break

            try:
                lock_wait_start = time.perf_counter()
                async with self._action_lock:
                    self._profile_timing("platform_lock_wait", time.perf_counter() - lock_wait_start)
                    dispatch_start = time.perf_counter()
                    result = await self.action_dispatcher.dispatch(
                        agent_id=int(agent_id) if agent_id is not None else -1,
                        action_name=action_name,
                        message=message,
                    )
                    self._profile_timing("platform_dispatch", time.perf_counter() - dispatch_start)
                    self._profile_count(f"platform_action:{action_name}")
            except Exception as exc:
                result = {"success": False, "error": str(exc)}
            await self.channel.send_to((message_id, agent_id, result))

    def create_post(
        self,
        author_id: int,
        content: str,
        emotion: str,
        intensity: float,
        sentiment: float,
        emotion_analysis: Optional[dict] = None,
    ) -> dict:
        """鍒涘缓涓€鏉℃柊甯栧瓙锛屽苟琛ラ綈骞冲彴渚ф儏缁垎鏋愬瓧娈点€?"""
        emotion_payload = self.platform_utils.resolve_emotion_payload(
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
        """鍦ㄦ寚瀹氬笘瀛愪笅鍒涘缓鍥炲銆?"""
        emotion_payload = self.platform_utils.resolve_emotion_payload(
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
        """璁板綍鐐硅禐锛涘悓涓€ agent 瀵瑰悓涓€甯栧瓙鍙繚鐣欎竴鏉¤褰曘€?"""
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

        post = self.platform_utils.find_post(self.posts, post_id)
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
        """杞彂鍘熷笘锛屽苟棰濆鐢熸垚涓€鏉℃柊鐨勫垎浜笘瀛愩€?"""
        original_post = self.platform_utils.find_post(self.posts, post_id)
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
        emotion_payload = self.platform_utils.resolve_emotion_payload(
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
        self.traces.append({"round_index": self.current_round, "type": "create_post", **shared_post})
        return shared_post

    def apply_influence(
        self,
        source_agent_id: int,
        target_agent_id: int,
        delta: float,
        reason: str,
    ) -> dict:
        """璁板綍涓€娆＄ぞ浼氬奖鍝嶄簨浠躲€?"""
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
        """璁板綍鏈疆鏈墽琛屽叕寮€鍔ㄤ綔銆?"""
        self.traces.append(
            {
                "round_index": self.current_round,
                "type": "do_nothing",
                "agent_id": agent_id,
                "reason": reason,
            }
        )

    def get_feed_for_agent(self, agent_id: int) -> List[dict]:
        """涓烘寚瀹?agent 璁＄畻甯︽洕鍏夊垎鐨勪俊鎭祦銆?"""
        scored_items = []
        for item in self.posts:
            exposure = self.platform_utils.score_exposure(item, agent_id, self.current_round)
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
        """鎻愪氦涓€杞粨鏉熷悗鐨勭粺璁′俊鎭紝骞舵帹杩涘钩鍙拌疆娆°€?"""
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
                "runtime_profile": self.snapshot_runtime_profile(),
            }
        )
        self.current_round = round_index + 1

    def snapshot(self) -> dict:
        """瀵煎嚭骞冲彴褰撳墠瀹屾暣蹇収銆?"""
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
            "runtime_profile": self.snapshot_runtime_profile(),
        }

    def snapshot_runtime_profile(self) -> dict:
        return {
            key: {
                "count": int(value.get("count", 0)),
                "total_ms": round(float(value.get("total", 0.0)) * 1000.0, 3),
                "avg_ms": round(
                    (
                        float(value.get("total", 0.0)) / max(1, int(value.get("count", 0)))
                    )
                    * 1000.0,
                    3,
                ),
            }
            for key, value in sorted(self.runtime_profile.items())
        }

    def _profile_timing(self, metric: str, duration: float) -> None:
        bucket = self.runtime_profile.setdefault(metric, {"count": 0, "total": 0.0})
        bucket["count"] += 1
        bucket["total"] += max(0.0, float(duration))

    def _profile_count(self, metric: str, value: int = 1) -> None:
        bucket = self.runtime_profile.setdefault(metric, {"count": 0, "total": 0.0})
        bucket["count"] += max(0, int(value))
