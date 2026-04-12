"""Agent 侧的平台动作封装。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, List

from social_platform.channel import Channel

if TYPE_CHECKING:
    from .agent import AgentDecision, EmotionState, SimulatedAgent


@dataclass
class PlatformActionRequest:
    """由 agent 决策派生出的结构化平台动作请求。"""

    action: str
    payload: dict[str, Any] = field(default_factory=dict)


class SocialAction:
    """面向平台的动作代理，负责发请求并接收结果。"""

    def __init__(
        self,
        agent_id: int,
        owner: SimulatedAgent | None = None,
        channel: Channel | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.owner = owner
        self.channel = channel

    def bind(
        self,
        *,
        owner: SimulatedAgent | None = None,
        channel: Channel | None = None,
    ) -> None:
        if owner is not None:
            self.owner = owner
        if channel is not None:
            self.channel = channel

    async def perform_action(self, payload: Any, action_name: str) -> dict:
        """通过通道发送动作，并等待平台返回结果。"""

        if self.channel is None:
            raise RuntimeError("SocialAction requires a bound channel.")
        message_id = await self.channel.write_to_receive_queue(
            (self.agent_id, payload, action_name)
        )
        _message_id, _agent_id, result = await self.channel.read_from_send_queue(message_id)
        return dict(result)

    async def register_agent(self, agent_name: str) -> dict:
        return await self.perform_action(
            {"agent_id": self.agent_id, "agent_name": agent_name},
            "register_agent",
        )

    async def browse_feed(self) -> dict:
        return await self.perform_action({}, "browse_feed")

    def build_action_requests(self, decision: AgentDecision) -> List[PlatformActionRequest]:
        """把高层决策拆成一个或多个平台动作。"""

        owner = self._require_owner()
        emotion_label = owner.state.dominant_emotion_label
        emotion_state = owner.state.emotion_state or owner.build_emotion_state_projection()
        emotion_intensity = max(owner.emotion_intensity(), emotion_state.intensity)
        emotion_payload = owner.platform_emotion_payload()
        requests: List[PlatformActionRequest] = []

        if decision.action == "create_post":
            requests.append(
                PlatformActionRequest(
                    action="create_post",
                    payload={
                        "content": decision.content,
                        "emotion": emotion_label,
                        "intensity": emotion_intensity,
                        "sentiment": owner.state.emotion,
                        "emotion_analysis": emotion_payload,
                    },
                )
            )
            return requests

        if decision.action == "reply_post" and decision.target_post_id is not None:
            # 回复动作可能顺带触发一次对目标 agent 的社会影响。
            requests.append(
                PlatformActionRequest(
                    action="reply_post",
                    payload={
                        "post_id": decision.target_post_id,
                        "content": decision.content,
                        "emotion": emotion_label,
                        "intensity": emotion_intensity,
                        "sentiment": owner.state.emotion,
                        "emotion_analysis": emotion_payload,
                    },
                )
            )
            if decision.target_agent_id is not None:
                requests.append(
                    PlatformActionRequest(
                        action="apply_influence",
                        payload={
                            "source_agent_id": self.agent_id,
                            "target_agent_id": decision.target_agent_id,
                            "delta": decision.influence_delta,
                            "reason": decision.reason,
                        },
                    )
                )
            return requests

        if decision.action == "like_post" and decision.target_post_id is not None:
            requests.append(
                PlatformActionRequest(
                    action="like_post",
                    payload={"post_id": decision.target_post_id},
                )
            )
            if decision.target_agent_id is not None and decision.target_agent_id != self.agent_id:
                requests.append(
                    PlatformActionRequest(
                        action="apply_influence",
                        payload={
                            "source_agent_id": self.agent_id,
                            "target_agent_id": decision.target_agent_id,
                            "delta": decision.influence_delta,
                            "reason": decision.reason,
                        },
                    )
                )
            return requests

        if decision.action == "share_post" and decision.target_post_id is not None:
            requests.append(
                PlatformActionRequest(
                    action="share_post",
                    payload={
                        "post_id": decision.target_post_id,
                        "content": decision.content,
                        "emotion": emotion_label,
                        "intensity": emotion_intensity,
                        "sentiment": owner.state.emotion,
                        "emotion_analysis": emotion_payload,
                    },
                )
            )
            if decision.target_agent_id is not None and decision.target_agent_id != self.agent_id:
                requests.append(
                    PlatformActionRequest(
                        action="apply_influence",
                        payload={
                            "source_agent_id": self.agent_id,
                            "target_agent_id": decision.target_agent_id,
                            "delta": decision.influence_delta,
                            "reason": decision.reason,
                        },
                    )
                )
            return requests

        if decision.action == "browse_feed":
            if decision.target_agent_id is not None and decision.target_agent_id != self.agent_id:
                requests.append(
                    PlatformActionRequest(
                        action="apply_influence",
                        payload={
                            "source_agent_id": decision.target_agent_id,
                            "target_agent_id": self.agent_id,
                            "delta": decision.influence_delta,
                            "reason": "Browsing socially salient content slightly shifts cognition.",
                        },
                    )
                )
            return requests

        requests.append(
            PlatformActionRequest(
                action="do_nothing",
                payload={"reason": decision.reason},
            )
        )
        return requests

    async def apply_decision(self, decision: AgentDecision, round_index: int) -> List[dict]:
        """执行决策对应的平台动作，并回写结果。"""

        requests = self.build_action_requests(decision)
        dispatch_results: List[dict] = []
        for request in requests:
            dispatch_results.append(await self.perform_action(request.payload, request.action))
        self.finalize_action_effects(decision, round_index, dispatch_results)
        return dispatch_results

    def finalize_action_effects(
        self,
        decision: AgentDecision,
        round_index: int,
        dispatch_results: List[dict],
    ) -> None:
        """根据平台执行结果补充 agent 自身状态。"""

        owner = self._require_owner()
        if decision.action == "create_post":
            owner.state.influence_score = owner.clamp(owner.state.influence_score + 0.05)
            created = dispatch_results[0].get("post", {}) if dispatch_results else {}
            owner.remember(
                round_index=round_index,
                source="self_post",
                content=str(created.get("content", decision.content)),
                valence=owner.state.emotion,
            )
            return

        if decision.action == "like_post":
            owner.state.influence_score = owner.clamp(owner.state.influence_score + 0.01)
            return

        if decision.action == "share_post":
            owner.state.influence_score = owner.clamp(owner.state.influence_score + 0.04)
            created = dispatch_results[0].get("post", {}) if dispatch_results else {}
            owner.remember(
                round_index=round_index,
                source="self_share",
                content=str(created.get("content", decision.content)),
                valence=owner.state.emotion,
            )

    def _require_owner(self) -> SimulatedAgent:
        if self.owner is None:
            raise RuntimeError("SocialAction requires a bound agent owner.")
        return self.owner
