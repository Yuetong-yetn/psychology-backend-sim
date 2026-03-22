"""社会心理 agent。

这个文件实现了一个最小可运行的认知-情绪耦合 agent，核心流程是：

环境输入 -> appraisal -> emotion 更新 -> schema 更新 -> equilibrium -> 行为决策

同时保留情绪反馈、情绪传播与图式更新之间的闭环。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from Backend.social_agent.appraisal_moe import AppraisalMoEConfig, AppraisalRouter
from Backend.social_agent.emotion_representation import (
    LATENT_DIM,
    EmotionRepresentationConfig,
    EmotionRepresentationModule,
)


EMOTION_SENTIMENT = {
    "anger": -0.8,
    "frustration": -0.5,
    "anxiety": -0.45,
    "fear": -0.65,
    "guilt": -0.35,
    "shame": -0.45,
    "hope": 0.4,
    "confidence": 0.7,
    "relief": 0.35,
    "calm": 0.0,
}

class EmotionLatentEncoder:
    """Pure local mixed-feature encoder for higher-dimensional emotion latent."""

    @staticmethod
    def encode(
        emotion_probs: Dict[str, float],
        pad: List[float],
        sentiment: float,
        intensity: float,
        appraisal_summary: Optional[Dict[str, float]] = None,
        contagion_summary: Optional[Dict[str, float]] = None,
        schema_summary: Optional[Dict[str, float]] = None,
        text_context: Optional[Dict[str, object]] = None,
    ) -> List[float]:
        # 兼容旧调用点：静态编码器继续可用，但内部转发到新的可插拔表示模块。
        module = EmotionRepresentationModule(EmotionRepresentationConfig(mode="fallback"))
        return module.encode(
            emotion_probs=emotion_probs,
            pad=pad,
            sentiment=sentiment,
            intensity=intensity,
            appraisal_summary=appraisal_summary,
            contagion_summary=contagion_summary,
            schema_summary=schema_summary,
            text_context=text_context,
        )


@dataclass
class MemoryItem:
    """agent 的最小记忆单元。"""

    round_index: int
    source: str
    content: str
    valence: float = 0.0


@dataclass
class EmotionState:
    """多维情绪状态。"""

    emotion_probs: Dict[str, float] = field(default_factory=dict)
    pad: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    latent: List[float] = field(default_factory=lambda: [0.0] * LATENT_DIM)
    dominant_label: str = "calm"
    intensity: float = 0.0
    signed_valence: float = 0.0

    @classmethod
    def from_projection(
        cls,
        signed_valence: float = 0.0,
        intensity: float = 0.0,
        dominant_label: str = "calm",
        pad: Optional[List[float]] = None,
        latent: Optional[List[float]] = None,
        emotion_probs: Optional[Dict[str, float]] = None,
        appraisal_summary: Optional[Dict[str, float]] = None,
        contagion_summary: Optional[Dict[str, float]] = None,
        schema_summary: Optional[Dict[str, float]] = None,
    ) -> "EmotionState":
        probs = emotion_probs or _build_emotion_probs(dominant_label, signed_valence, intensity)
        resolved_pad = pad or [
            _clamp_signed(signed_valence),
            _clamp(intensity),
            _clamp_signed((intensity * 0.5) if signed_valence >= 0 else -(intensity * 0.35)),
        ]
        resolved_latent = latent or EmotionLatentEncoder.encode(
            emotion_probs=probs,
            pad=resolved_pad,
            sentiment=signed_valence,
            intensity=intensity,
            appraisal_summary=appraisal_summary,
            contagion_summary=contagion_summary,
            schema_summary=schema_summary,
        )
        return cls(
            emotion_probs=probs,
            pad=[float(item) for item in resolved_pad],
            latent=[float(item) for item in resolved_latent],
            dominant_label=dominant_label,
            intensity=_clamp(float(intensity)),
            signed_valence=_clamp_signed(float(signed_valence)),
        )


@dataclass
class AppraisalRecord:
    """一轮 appraisal 的结构化输出。"""

    relevance: float
    valence: float
    goal_congruence: float
    controllability: float
    agency: str
    certainty: float
    novelty: float
    coping_potential: float
    dominant_emotion: str
    emotion_intensity: float
    cognitive_mode: str


@dataclass
class AgentProfile:
    """agent 的静态画像。"""

    agent_id: int
    name: str
    role: str
    ideology: str
    communication_style: str = "balanced"


@dataclass
class AgentState:
    """agent 的动态心理状态。"""

    emotion: float = 0.0
    emotion_state: Optional[EmotionState] = None
    stress: float = 0.0
    expectation: float = 0.5
    influence_score: float = 0.5
    schemas: Dict[str, float] = field(
        default_factory=lambda: {
            "support_tendency": 0.5,
            "threat_sensitivity": 0.5,
            "self_efficacy": 0.5,
        }
    )
    schema_flexibility: float = 0.5
    equilibrium: float = 0.7
    last_cognitive_mode: str = "equilibrium"
    dominant_emotion_label: str = "calm"
    last_appraisal: Optional[AppraisalRecord] = None
    appraisal_history: List[AppraisalRecord] = field(default_factory=list)
    last_contagion_pad: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    last_contagion_vector: List[float] = field(default_factory=lambda: [0.0] * LATENT_DIM)
    appraisal_runtime: Dict[str, object] = field(default_factory=dict)
    latent_runtime: Dict[str, object] = field(default_factory=dict)
    memory: List[MemoryItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.emotion_state is None:
            inferred_label = self.dominant_emotion_label or _infer_label_from_valence(self.emotion)
            self.emotion_state = EmotionState.from_projection(
                signed_valence=self.emotion,
                intensity=abs(self.emotion),
                dominant_label=inferred_label,
            )
        else:
            self.emotion = _clamp_signed(self.emotion_state.signed_valence)
            self.dominant_emotion_label = self.emotion_state.dominant_label


@dataclass
class AgentDecision:
    """单轮行为决策结果。"""

    action: str
    content: str
    target_post_id: Optional[int] = None
    target_agent_id: Optional[int] = None
    metadata: Dict[str, object] = field(default_factory=dict)
    influence_delta: float = 0.0
    reason: str = ""


@dataclass
class AgentRoundResult:
    """单轮执行结果，供 environment 记录和导出。"""

    profile: AgentProfile
    state: AgentState
    decision: AgentDecision

    def to_dict(self) -> dict:
        return {
            "profile": asdict(self.profile),
            "state": {
                "emotion": self.state.emotion,
                "emotion_state": asdict(self.state.emotion_state),
                "stress": self.state.stress,
                "expectation": self.state.expectation,
                "influence_score": self.state.influence_score,
                "schemas": self.state.schemas,
                "schema_flexibility": self.state.schema_flexibility,
                "equilibrium": self.state.equilibrium,
                "last_cognitive_mode": self.state.last_cognitive_mode,
                "dominant_emotion_label": self.state.dominant_emotion_label,
                "last_appraisal": (
                    asdict(self.state.last_appraisal)
                    if self.state.last_appraisal is not None
                    else None
                ),
                "appraisal_history": [
                    asdict(item) for item in self.state.appraisal_history[-5:]
                ],
                "last_contagion_pad": self.state.last_contagion_pad,
                "last_contagion_vector": self.state.last_contagion_vector,
                "appraisal_runtime": dict(self.state.appraisal_runtime),
                "latent_runtime": dict(self.state.latent_runtime),
                "memory": [asdict(item) for item in self.state.memory],
            },
            "decision": asdict(self.decision),
        }


class SimulatedAgent:
    """带认知-情绪耦合的最小 social agent。"""

    contagion_weight: float = 0.18
    base_schema_rate: float = 0.16
    emotion_valence_bias: float = 0.28
    emotion_uncertainty_bias: float = 0.22
    emotion_control_bias: float = 0.18
    contagion_threat_gain: float = 0.08
    contagion_efficacy_loss: float = 0.06

    def __init__(
        self,
        profile: AgentProfile,
        state: AgentState | None = None,
        mode: str = "moe",
        llm_provider: str = "volcengine",
        enable_fallback: bool = True,
        checkpoint_dir: Optional[str] = None,
    ):
        self.agent_id = profile.agent_id
        self.profile = profile
        self.state = state or AgentState()
        public_mode = "fallback" if mode == "fallback" else "moe"

        self.appraisal_router = AppraisalRouter(
            AppraisalMoEConfig(
                mode=public_mode,
                checkpoint_dir=checkpoint_dir,
                llm_provider_name=llm_provider,
                enable_fallback=enable_fallback,
            )
        )
        self.emotion_representation = EmotionRepresentationModule(
            EmotionRepresentationConfig(
                mode=public_mode,
                checkpoint_dir=checkpoint_dir,
                llm_provider_name=llm_provider,
                enable_fallback=enable_fallback,
            )
        )
        self.state.appraisal_runtime = {
            "mode": public_mode,
            "provider": None,
            "model": None,
            "source": "local",
            "fallback_used": public_mode == "fallback",
            "fallback_reason": "mode_forced_fallback" if public_mode == "fallback" else None,
        }
        self.state.latent_runtime = {
            "mode": public_mode,
            "provider": None,
            "model": None,
            "source": "local",
            "fallback_used": public_mode == "fallback",
            "fallback_reason": "mode_forced_fallback" if public_mode == "fallback" else None,
        }

    def receive_information(
        self,
        round_index: int,
        scenario_prompt: str,
        feed: List[dict],
    ) -> None:
        """接收外部信息、写入记忆，并执行情绪传播。"""
        signal = self._extract_environment_signal(feed, scenario_prompt)
        self._apply_emotion_contagion(feed)
        self.state.memory.append(
            MemoryItem(
                round_index=round_index,
                source="scenario",
                content=scenario_prompt,
                valence=signal["direction"],
            )
        )
        for item in feed[:3]:
            self.state.memory.append(
                MemoryItem(
                    round_index=round_index,
                    source="feed",
                    content=item["content"],
                    valence=item.get("sentiment", 0.0),
                )
            )
        self.state.memory = self.state.memory[-12:]

    def update_state(self, feed: List[dict], scenario_prompt: str) -> None:
        """按固定顺序更新内部状态。"""
        event = self._extract_environment_signal(feed, scenario_prompt)
        appraisal = self._build_appraisal(event, feed)
        self._update_emotion(appraisal)
        self._update_schema(appraisal)
        self._rebalance(appraisal)
        self.state.last_appraisal = appraisal
        self.state.appraisal_history.append(appraisal)
        self.state.appraisal_history = self.state.appraisal_history[-8:]
        self.state.dominant_emotion_label = appraisal.dominant_emotion

    def decide_action(self, feed: List[dict]) -> AgentDecision:
        """根据 appraisal 和情绪调节后的 action score 选择行为。"""
        appraisal = self.state.last_appraisal
        if appraisal is None:
            appraisal = AppraisalRecord(
                relevance=0.0,
                valence=0.0,
                goal_congruence=0.5,
                controllability=0.5,
                agency="external",
                certainty=0.5,
                novelty=0.0,
                coping_potential=0.5,
                dominant_emotion="calm",
                emotion_intensity=0.0,
                cognitive_mode=self.state.last_cognitive_mode,
            )

        emotion_state = self.state.emotion_state or EmotionState.from_projection(
            signed_valence=self.state.emotion,
            intensity=self._emotion_intensity(),
            dominant_label=self.state.dominant_emotion_label,
        )
        emotion_intensity = max(self._emotion_intensity(), emotion_state.intensity)
        pleasure, arousal, dominance = emotion_state.pad
        latent = emotion_state.latent
        if not feed:
            return AgentDecision(
                action="create_post",
                content=self._build_post_content(opening=True),
                influence_delta=0.03 + emotion_intensity * 0.04,
                reason="No visible posts, so the agent opens the discussion.",
            )

        hottest = feed[0]
        target_agent_id = hottest["author_id"]

        browse_score = self._clamp(
            (1 - self.state.equilibrium) * 0.35
            + (1 - appraisal.certainty) * 0.25
            + self.state.stress * 0.2
            + arousal * 0.08
            + (0.15 if appraisal.dominant_emotion in {"anxiety", "fear", "guilt", "shame"} else 0.0)
        )
        create_score = self._clamp(
            appraisal.goal_congruence * 0.32
            + appraisal.controllability * 0.22
            + self.state.expectation * 0.16
            + self.state.equilibrium * 0.12
            + max(0.0, pleasure) * 0.14
            + max(0.0, dominance) * 0.04
            + max(0.0, latent[8]) * 0.04
        )
        reply_score = self._clamp(
            appraisal.relevance * 0.18
            + (1 - appraisal.goal_congruence) * 0.18
            + self.state.stress * 0.22
            + emotion_intensity * 0.16
            + max(0.0, arousal - 0.2) * 0.06
            + max(0.0, latent[11]) * 0.04
            + (0.2 if appraisal.dominant_emotion in {"anger", "frustration"} else 0.0)
        )
        like_score = self._clamp(
            appraisal.goal_congruence * 0.28
            + appraisal.certainty * 0.18
            + max(0.0, pleasure) * 0.18
            + max(0.0, latent[5] - latent[6]) * 0.06
            + (0.12 if appraisal.dominant_emotion in {"confidence", "relief", "hope"} else 0.0)
        )
        share_score = self._clamp(
            appraisal.relevance * 0.2
            + appraisal.goal_congruence * 0.24
            + self.state.influence_score * 0.14
            + emotion_intensity * 0.12
            + hottest.get("intensity", 0.0) * 0.14
            + max(0.0, arousal - 0.2) * 0.08
            + max(0.0, latent[12]) * 0.04
        )

        best_score = max(browse_score, create_score, reply_score, like_score, share_score)

        if browse_score >= best_score:
            return AgentDecision(
                action="browse_feed",
                content="Continue observing the feed before taking stronger action.",
                target_post_id=hottest["post_id"],
                target_agent_id=target_agent_id,
                influence_delta=0.01 + emotion_intensity * 0.02,
                reason="Low certainty or low equilibrium favors observation.",
            )

        if reply_score >= best_score:
            reply_delta = -0.02 if pleasure < 0 else 0.03
            reply_delta *= 1 + emotion_intensity
            return AgentDecision(
                action="reply_post",
                content=f"{self.profile.name} responds directly to the current discussion.",
                target_post_id=hottest["post_id"],
                target_agent_id=target_agent_id,
                influence_delta=reply_delta,
                reason="High emotional activation and relevance favor direct response.",
            )

        if share_score >= best_score:
            return AgentDecision(
                action="share_post",
                content=f"{self.profile.name} amplifies a post aligned with the current view.",
                target_post_id=hottest["post_id"],
                target_agent_id=target_agent_id,
                influence_delta=0.04 + emotion_intensity * 0.04,
                metadata={"shared_post_id": hottest["post_id"]},
                reason="High relevance plus congruence favors amplification through sharing.",
            )

        if like_score >= best_score:
            return AgentDecision(
                action="like_post",
                content="Signal agreement through a lightweight endorsement.",
                target_post_id=hottest["post_id"],
                target_agent_id=target_agent_id,
                influence_delta=0.02 + emotion_intensity * 0.02,
                reason="Congruent appraisal with low action cost favors liking.",
            )

        return AgentDecision(
            action="create_post",
            content=self._build_post_content(opening=False),
            influence_delta=0.03 + emotion_intensity * 0.03,
            reason="Congruent appraisal with enough control favors posting.",
        )

    def act(self, decision: AgentDecision, platform) -> None:
        """把内部决策落到平台动作上。"""
        emotion_label = self.state.dominant_emotion_label
        emotion_state = self.state.emotion_state or EmotionState.from_projection(
            signed_valence=self.state.emotion,
            intensity=self._emotion_intensity(),
            dominant_label=self.state.dominant_emotion_label,
        )
        emotion_intensity = max(self._emotion_intensity(), emotion_state.intensity)

        if decision.action == "create_post":
            post = platform.create_post(
                author_id=self.agent_id,
                content=decision.content,
                emotion=emotion_label,
                intensity=emotion_intensity,
                sentiment=self.state.emotion,
                emotion_analysis=self._emotion_state_to_platform_payload(),
            )
            self.state.influence_score = self._clamp(self.state.influence_score + 0.05)
            self.state.memory.append(
                MemoryItem(
                    round_index=platform.current_round,
                    source="self_post",
                    content=post["content"],
                    valence=self.state.emotion,
                )
            )
            return

        if decision.action == "reply_post" and decision.target_post_id is not None:
            platform.reply_post(
                author_id=self.agent_id,
                post_id=decision.target_post_id,
                content=decision.content,
                emotion=emotion_label,
                intensity=emotion_intensity,
                sentiment=self.state.emotion,
                emotion_analysis=self._emotion_state_to_platform_payload(),
            )
            if decision.target_agent_id is not None:
                platform.apply_influence(
                    source_agent_id=self.agent_id,
                    target_agent_id=decision.target_agent_id,
                    delta=decision.influence_delta,
                    reason=decision.reason,
                )
            return

        if decision.action == "like_post" and decision.target_post_id is not None:
            platform.like_post(agent_id=self.agent_id, post_id=decision.target_post_id)
            if decision.target_agent_id is not None and decision.target_agent_id != self.agent_id:
                platform.apply_influence(
                    source_agent_id=self.agent_id,
                    target_agent_id=decision.target_agent_id,
                    delta=decision.influence_delta,
                    reason=decision.reason,
                )
            self.state.influence_score = self._clamp(self.state.influence_score + 0.01)
            return

        if decision.action == "share_post" and decision.target_post_id is not None:
            shared_post = platform.share_post(
                agent_id=self.agent_id,
                post_id=decision.target_post_id,
                content=decision.content,
                emotion=emotion_label,
                intensity=emotion_intensity,
                sentiment=self.state.emotion,
                emotion_analysis=self._emotion_state_to_platform_payload(),
            )
            if decision.target_agent_id is not None and decision.target_agent_id != self.agent_id:
                platform.apply_influence(
                    source_agent_id=self.agent_id,
                    target_agent_id=decision.target_agent_id,
                    delta=decision.influence_delta,
                    reason=decision.reason,
                )
            self.state.influence_score = self._clamp(self.state.influence_score + 0.04)
            self.state.memory.append(
                MemoryItem(
                    round_index=platform.current_round,
                    source="self_share",
                    content=shared_post["content"],
                    valence=self.state.emotion,
                )
            )
            return

        if decision.action == "browse_feed":
            if decision.target_agent_id is not None and decision.target_agent_id != self.agent_id:
                platform.apply_influence(
                    source_agent_id=decision.target_agent_id,
                    target_agent_id=self.agent_id,
                    delta=decision.influence_delta,
                    reason="Browsing socially salient content slightly shifts cognition.",
                )
            return

        platform.record_idle(self.agent_id, reason=decision.reason)

    def run_round(
        self,
        round_index: int,
        scenario_prompt: str,
        feed: List[dict],
        platform,
    ) -> AgentRoundResult:
        """把接收信息、状态更新、决策和行动串成单轮循环。"""
        self.receive_information(round_index, scenario_prompt, feed)
        self.update_state(feed, scenario_prompt)
        decision = self.decide_action(feed)
        self.act(decision, platform)
        return AgentRoundResult(
            profile=self.profile,
            state=self.state,
            decision=decision,
        )

    def snapshot(self) -> dict:
        """返回适合导出/调试的最小 agent 快照。"""
        return {
            "profile": asdict(self.profile),
            "state": {
                "emotion": self.state.emotion,
                "emotion_state": asdict(self.state.emotion_state),
                "stress": self.state.stress,
                "expectation": self.state.expectation,
                "influence_score": self.state.influence_score,
                "schemas": self.state.schemas,
                "schema_flexibility": self.state.schema_flexibility,
                "equilibrium": self.state.equilibrium,
                "last_cognitive_mode": self.state.last_cognitive_mode,
                "dominant_emotion_label": self.state.dominant_emotion_label,
                "last_appraisal": (
                    asdict(self.state.last_appraisal)
                    if self.state.last_appraisal is not None
                    else None
                ),
                "last_contagion_pad": self.state.last_contagion_pad,
                "last_contagion_vector": self.state.last_contagion_vector,
                "appraisal_runtime": dict(self.state.appraisal_runtime),
                "latent_runtime": dict(self.state.latent_runtime),
                "memory_size": len(self.state.memory),
                "appraisal_count": len(self.state.appraisal_history),
            },
        }

    def _build_post_content(self, opening: bool) -> str:
        """根据当前主导情绪生成最小发帖文案。"""
        if opening:
            return f"{self.profile.name} starts discussing the current social issue."

        emotion_label = self.state.dominant_emotion_label
        if emotion_label in {"anger", "frustration"}:
            tone = "critical"
        elif emotion_label in {"anxiety", "fear"}:
            tone = "uncertain"
        elif emotion_label in {"hope", "confidence", "relief"}:
            tone = "supportive"
        else:
            tone = "measured"

        return (
            f"{self.profile.name} shares a {tone} take on the scenario "
            f"from the {self.profile.role} perspective."
        )

    def _extract_environment_signal(
        self,
        feed: List[dict],
        scenario_prompt: str,
    ) -> Dict[str, float]:
        """把外部输入压缩成一个最小 event 表示。"""
        feed_window = feed[:3]
        risk = sum(abs(item.get("sentiment", 0.0)) for item in feed_window)
        direction = sum(item.get("sentiment", 0.0) for item in feed_window)
        direction = self._clamp_signed(direction)

        controversy = 0.15 if "divided" in scenario_prompt.lower() else 0.0
        uncertainty_bonus = 0.1 if "uncertain" in scenario_prompt.lower() else 0.0
        risk = self._clamp(risk * 0.5 + controversy + uncertainty_bonus)

        schema_direction = self.state.schemas["support_tendency"] * 2 - 1
        novelty = self._clamp(
            abs(direction - schema_direction) * 0.45
            + abs(risk - self.state.schemas["threat_sensitivity"]) * 0.35
            + (0.2 if len(feed_window) == 0 else 0.0)
        )
        consistency = 1.0
        if len(feed_window) >= 2:
            sentiments = [item.get("sentiment", 0.0) for item in feed_window]
            spread = max(sentiments) - min(sentiments)
            consistency = self._clamp(1.0 - spread)

        return {
            "direction": direction,
            "risk": risk,
            "novelty": novelty,
            "consistency": consistency,
        }

    def _build_appraisal(
        self,
        event: Dict[str, float],
        feed: List[dict],
    ) -> AppraisalRecord:
        """构建带 schema 条件和情绪偏置的 appraisal。"""
        schemas = self.state.schemas
        schema_direction = schemas["support_tendency"] * 2 - 1
        threat_bias = schemas["threat_sensitivity"]
        efficacy = schemas["self_efficacy"]
        emotion_state = self.state.emotion_state or EmotionState.from_projection(
            signed_valence=self.state.emotion,
            intensity=abs(self.state.emotion),
            dominant_label=self.state.dominant_emotion_label,
        )
        emotion_bias = emotion_state.signed_valence
        emotion_magnitude = max(abs(emotion_bias), emotion_state.intensity)
        arousal = emotion_state.pad[1]
        dominance = emotion_state.pad[2]

        prior_relevance = self._clamp(
            event["risk"] * 0.45
            + event["novelty"] * 0.25
            + abs(event["direction"]) * 0.15
            + emotion_magnitude * 0.1
            + arousal * 0.05
        )
        prior_valence = self._clamp_signed(
            event["direction"] * (0.55 + schemas["support_tendency"] * 0.45)
            - event["risk"] * threat_bias * 0.6
        )
        prior_valence = self._clamp_signed(
            prior_valence * (1 + self.emotion_valence_bias * emotion_bias)
        )
        prior_goal_congruence = self._clamp(
            1.0 - abs(event["direction"] - schema_direction) / 2.0
        )
        prior_controllability = self._clamp(
            efficacy * 0.45
            + self.state.equilibrium * 0.2
            + (1 - event["risk"]) * 0.15
            + (1 - self.state.stress) * 0.1
            + prior_goal_congruence * 0.1
            + max(0.0, dominance) * 0.05
        )
        prior_controllability = self._clamp(
            prior_controllability * (1 - self.emotion_control_bias * emotion_magnitude)
        )
        prior_certainty = self._clamp(
            event["consistency"] * 0.5
            + (1 - event["novelty"]) * 0.25
            + prior_goal_congruence * 0.15
            + (1 - self.state.stress) * 0.1
            - arousal * 0.05
        )
        prior_certainty = self._clamp(
            prior_certainty * (1 - self.emotion_uncertainty_bias * emotion_magnitude)
        )
        prior_coping_potential = self._clamp(
            efficacy * 0.4
            + prior_controllability * 0.25
            + prior_certainty * 0.15
            + (1 - self.state.stress) * 0.1
            + (1 - event["risk"]) * 0.1
            + max(0.0, dominance) * 0.05
        )
        prior = {
            "relevance": prior_relevance,
            "valence": prior_valence,
            "goal_congruence": prior_goal_congruence,
            "controllability": prior_controllability,
            "certainty": prior_certainty,
            "coping_potential": prior_coping_potential,
        }
        feed_features = self._summarize_feed_for_appraisal(feed)
        contagion_features = self._summarize_contagion_features()
        memory_summary = self._summarize_memory()

        fused = self.appraisal_router.evaluate(
            event=event,
            schemas=schemas,
            emotion_state=emotion_state,
            stress=self.state.stress,
            equilibrium=self.state.equilibrium,
            feed_features=feed_features,
            contagion_features=contagion_features,
            memory_summary=memory_summary,
            prior=prior,
            llm_context={
                "profile": asdict(self.profile),
                "memory_excerpt": [item.content for item in self.state.memory[-4:]],
                "top_feed": [
                    {
                        "content": item.get("content", ""),
                        "sentiment": item.get("sentiment", 0.0),
                        "exposure_score": item.get("exposure_score", 0.0),
                    }
                    for item in feed[:3]
                ],
            },
        )
        self.state.appraisal_runtime = dict(self.appraisal_router.last_run_metadata)
        relevance = fused["relevance"]
        valence = fused["valence"]
        goal_congruence = fused["goal_congruence"]
        controllability = fused["controllability"]
        certainty = fused["certainty"]
        coping_potential = fused["coping_potential"]

        agency = self._infer_agency(feed, valence)
        dominant_emotion = self._map_emotion(
            valence=valence,
            goal_congruence=goal_congruence,
            agency=agency,
            controllability=controllability,
            certainty=certainty,
            coping_potential=coping_potential,
        )
        emotion_intensity = self._clamp(
            relevance * 0.35
            + abs(valence) * 0.25
            + event["risk"] * 0.15
            + event["novelty"] * 0.15
            + (1 - certainty) * 0.1
            + arousal * 0.05
        )

        return AppraisalRecord(
            relevance=relevance,
            valence=valence,
            goal_congruence=goal_congruence,
            controllability=controllability,
            agency=agency,
            certainty=certainty,
            novelty=event["novelty"],
            coping_potential=coping_potential,
            dominant_emotion=dominant_emotion,
            emotion_intensity=emotion_intensity,
            cognitive_mode=self.state.last_cognitive_mode,
        )

    def _update_emotion(self, appraisal: AppraisalRecord) -> None:
        """把 appraisal 投影为兼容旧字段的多维情绪状态。"""
        target_emotion = self._emotion_target(
            appraisal.dominant_emotion,
            appraisal.valence,
        )
        self.state.emotion = self._clamp_signed(
            self.state.emotion * 0.45
            + target_emotion * appraisal.emotion_intensity * 0.55
        )
        self.state.stress = self._clamp(
            self.state.stress * 0.55
            + appraisal.relevance * 0.15
            + appraisal.novelty * 0.12
            + (1 - appraisal.controllability) * 0.1
            + max(0.0, -appraisal.valence) * 0.08
        )
        self.state.expectation = self._clamp(
            self.state.expectation * 0.68
            + appraisal.goal_congruence * 0.12
            + appraisal.coping_potential * 0.12
            + max(0.0, appraisal.valence) * 0.08
        )
        dominance = _clamp_signed(
            appraisal.controllability + appraisal.coping_potential - 1.0
        )
        appraisal_summary = {
            "valence": appraisal.valence,
            "control": appraisal.controllability,
            "certainty": appraisal.certainty,
        }
        pad = [
            _clamp_signed(self.state.emotion),
            self._clamp(appraisal.emotion_intensity),
            dominance,
        ]
        self.state.emotion_state = EmotionState.from_projection(
            signed_valence=self.state.emotion,
            intensity=appraisal.emotion_intensity,
            dominant_label=appraisal.dominant_emotion,
            pad=pad,
            latent=self._encode_emotion_latent(
                emotion_probs=_build_emotion_probs(
                    appraisal.dominant_emotion,
                    self.state.emotion,
                    appraisal.emotion_intensity,
                ),
                pad=pad,
                sentiment=self.state.emotion,
                intensity=appraisal.emotion_intensity,
                appraisal_summary=appraisal_summary,
                contagion_summary=self._summarize_contagion_features(),
                schema_summary=self._summarize_schema_summary(),
            ),
        )
        self.state.latent_runtime = dict(self.emotion_representation.last_run_metadata)
        self.state.emotion = self.state.emotion_state.signed_valence

    def _update_schema(self, appraisal: AppraisalRecord) -> None:
        """接收 appraisal、PAD、latent 与 contagion 向量后更新三维 schema。"""
        emotion_state = self.state.emotion_state or EmotionState.from_projection(
            signed_valence=self.state.emotion,
            intensity=self._emotion_intensity(),
            dominant_label=self.state.dominant_emotion_label,
        )
        appraisal_vector = self._appraisal_vector(appraisal)
        emotion_pad = emotion_state.pad
        emotion_latent = emotion_state.latent
        contagion_vector = self.state.last_contagion_vector
        contagion_pad = self.state.last_contagion_pad
        emotion_intensity = max(
            0.15,
            self._emotion_intensity(),
            emotion_state.intensity,
        )
        update_rate = self.base_schema_rate * (1 + self.state.stress) * emotion_intensity
        update_rate = self._clamp(
            update_rate
            + max(0.0, emotion_pad[1]) * 0.04
            + max(0.0, contagion_pad[1]) * 0.02
        )
        accommodation_strength = self._clamp(
            appraisal.novelty
            * (1 - appraisal.goal_congruence)
            * (1 - appraisal.certainty)
            * (0.6 + self.state.schema_flexibility * 0.8)
            * (0.75 + emotion_intensity * 0.5)
        )
        assimilation_strength = self._clamp(update_rate * (1 - accommodation_strength))
        accommodation_rate = self._clamp(update_rate * accommodation_strength)

        direction = self._clamp_signed(appraisal.goal_congruence * 2 - 1)
        support_shift = (
            direction * update_rate
            + emotion_pad[0] * 0.06
            + appraisal_vector[1] * 0.04
            + contagion_pad[0] * 0.03
            + emotion_latent[3] * 0.02
            + emotion_latent[8] * 0.03
            + emotion_latent[13] * 0.02
        )
        if appraisal.dominant_emotion == "confidence":
            support_shift += 0.45 * update_rate
        elif appraisal.dominant_emotion in {"fear", "anxiety", "guilt", "shame"}:
            support_shift -= 0.2 * update_rate

        threat_shift = self._clamp_signed(
            (1 - appraisal.controllability) - appraisal.coping_potential
        )
        threat_shift *= update_rate
        threat_shift += (
            max(0.0, -emotion_pad[0]) * 0.06
            + max(0.0, contagion_pad[1]) * 0.03
            + max(0.0, -contagion_pad[0]) * 0.05
            + emotion_latent[6] * 0.03
            + emotion_latent[11] * 0.03
            + emotion_latent[14] * 0.03
        )
        if appraisal.dominant_emotion == "fear":
            threat_shift += 0.7 * update_rate
        elif appraisal.dominant_emotion == "anger":
            threat_shift += 0.45 * update_rate
        elif appraisal.dominant_emotion == "confidence":
            threat_shift -= 0.25 * update_rate

        efficacy_shift = self._clamp_signed(
            appraisal.coping_potential - (1 - appraisal.controllability)
        )
        efficacy_shift *= update_rate
        efficacy_shift += (
            emotion_pad[2] * 0.06
            - max(0.0, emotion_pad[1] - 0.5) * 0.04
            - max(0.0, contagion_pad[1] - 0.4) * 0.03
            + emotion_latent[5] * 0.02
            - contagion_vector[6] * 0.02
            + emotion_latent[9] * 0.03
            + emotion_latent[15] * 0.03
        )
        if appraisal.dominant_emotion == "anxiety":
            efficacy_shift -= 0.75 * update_rate
        elif appraisal.dominant_emotion == "fear":
            efficacy_shift -= 0.45 * update_rate
        elif appraisal.dominant_emotion == "confidence":
            efficacy_shift += 0.45 * update_rate

        support_rate = assimilation_strength + accommodation_rate
        self.state.schemas["support_tendency"] = self._clamp(
            self.state.schemas["support_tendency"] + support_shift * support_rate
        )
        self.state.schemas["threat_sensitivity"] = self._clamp(
            self.state.schemas["threat_sensitivity"] + threat_shift
        )
        self.state.schemas["self_efficacy"] = self._clamp(
            self.state.schemas["self_efficacy"] + efficacy_shift
        )

        if accommodation_rate > assimilation_strength:
            self.state.last_cognitive_mode = "accommodation"
        else:
            self.state.last_cognitive_mode = "assimilation"

    def _rebalance(self, appraisal: AppraisalRecord) -> None:
        """在 schema 更新后计算新的 equilibrium。"""
        emotion_state = self.state.emotion_state or EmotionState.from_projection(
            signed_valence=self.state.emotion,
            intensity=self._emotion_intensity(),
            dominant_label=self.state.dominant_emotion_label,
        )
        emotion_penalty = self._emotion_intensity() * (
            0.08 if self.state.emotion < 0 else 0.04
        )
        stability_source = (
            appraisal.controllability * 0.24
            + appraisal.coping_potential * 0.22
            + appraisal.certainty * 0.18
            + appraisal.goal_congruence * 0.16
            + (1 - self.state.stress) * 0.12
            + self.state.schemas["self_efficacy"] * 0.08
            + max(0.0, emotion_state.pad[2]) * 0.03
        )
        self.state.equilibrium = self._clamp(
            self.state.equilibrium * 0.38
            + stability_source * 0.62
            - appraisal.novelty * 0.08
            - emotion_penalty
        )
        self.state.expectation = self._clamp(
            self.state.expectation * 0.8
            + self.state.equilibrium * 0.1
            + appraisal.coping_potential * 0.1
        )
        if self.state.equilibrium > 0.72 and self._emotion_intensity() < 0.35:
            self.state.last_cognitive_mode = "equilibrium"

    def _apply_emotion_contagion(self, feed: List[dict]) -> None:
        """按 exposure_score 加权聚合 feed 中的情绪 PAD/latent。"""
        neighbor_emotions = [
            self._extract_post_emotion_features(item)
            for item in feed[:3]
            if item.get("author_id") != self.agent_id
        ]
        if not neighbor_emotions:
            return

        total_weight = sum(item["weight"] for item in neighbor_emotions)
        if total_weight <= 1e-6:
            total_weight = float(len(neighbor_emotions))

        avg_neighbor_sentiment = sum(
            item["sentiment"] * item["weight"] for item in neighbor_emotions
        ) / total_weight
        avg_pad = [
            sum(
                item["pad"][index] * item["weight"]
                for item in neighbor_emotions
            )
            / total_weight
            for index in range(3)
        ]
        avg_latent = [
            sum(
                item["latent"][index] * item["weight"]
                for item in neighbor_emotions
            )
            / total_weight
            for index in range(LATENT_DIM)
        ]
        self.state.last_contagion_pad = [float(item) for item in avg_pad]
        self.state.last_contagion_vector = [float(item) for item in avg_latent]

        projected_valence = self._clamp_signed(
            self.state.emotion + self.contagion_weight * avg_neighbor_sentiment
        )
        contagion_intensity = self._clamp(
            abs(avg_pad[0]) * 0.35
            + avg_pad[1] * 0.4
            + abs(avg_neighbor_sentiment) * 0.25
        )
        contagion_label = _infer_label_from_valence(projected_valence)
        self.state.emotion_state = EmotionState.from_projection(
            signed_valence=projected_valence,
            intensity=max(
                contagion_intensity,
                self.state.emotion_state.intensity if self.state.emotion_state else 0.0,
            ),
            dominant_label=contagion_label,
            pad=[
                self._clamp_signed(projected_valence),
                self._clamp(avg_pad[1]),
                self._clamp_signed(avg_pad[2]),
            ],
            latent=self._encode_emotion_latent(
                emotion_probs=_build_emotion_probs(
                    contagion_label,
                    projected_valence,
                    max(
                        contagion_intensity,
                        self.state.emotion_state.intensity if self.state.emotion_state else 0.0,
                    ),
                ),
                pad=[
                    self._clamp_signed(projected_valence),
                    self._clamp(avg_pad[1]),
                    self._clamp_signed(avg_pad[2]),
                ],
                sentiment=projected_valence,
                intensity=max(
                    contagion_intensity,
                    self.state.emotion_state.intensity if self.state.emotion_state else 0.0,
                ),
                contagion_summary={
                    "sentiment": avg_pad[0],
                    "arousal": avg_pad[1],
                    "amplification": avg_latent[12] if len(avg_latent) > 12 else avg_pad[1],
                },
                schema_summary=self._summarize_schema_summary(),
                text_context={"feed_excerpt": [item.get("content", "") for item in feed[:3]]},
            ),
            contagion_summary={
                "sentiment": avg_pad[0],
                "arousal": avg_pad[1],
                "amplification": avg_latent[12] if len(avg_latent) > 12 else avg_pad[1],
            },
            schema_summary=self._summarize_schema_summary(),
        )
        self.state.latent_runtime = dict(self.emotion_representation.last_run_metadata)
        self.state.emotion = self.state.emotion_state.signed_valence
        self.state.schemas["threat_sensitivity"] = self._clamp(
            self.state.schemas["threat_sensitivity"]
            + self.contagion_threat_gain * max(0.0, -avg_pad[0])
            + avg_pad[1] * 0.02
        )
        self.state.schemas["self_efficacy"] = self._clamp(
            self.state.schemas["self_efficacy"]
            - self.contagion_efficacy_loss * max(abs(avg_pad[0]), avg_pad[1])
            + max(0.0, avg_pad[2]) * 0.01
        )
        self.state.dominant_emotion_label = self.state.emotion_state.dominant_label

    def _infer_agency(self, feed: List[dict], valence: float) -> str:
        """基于 feed 指向与效价粗略推断责任归因。"""
        if not feed:
            return "external"
        if valence < -0.15:
            return "other"
        if valence > 0.25 and self.state.schemas["self_efficacy"] > 0.55:
            return "self"
        return "external"

    def _map_emotion(
        self,
        valence: float,
        goal_congruence: float,
        agency: str,
        controllability: float,
        certainty: float,
        coping_potential: float,
    ) -> str:
        """把融合后的 appraisal 映射为离散主导情绪标签。"""
        if valence < -0.45 and agency == "other" and certainty > 0.45:
            return "anger"
        if valence < -0.35 and controllability < 0.45:
            return "fear"
        if valence < -0.2 and certainty < 0.45:
            return "anxiety"
        if valence < -0.15 and agency == "self":
            return "guilt"
        if valence > 0.35 and coping_potential > 0.55 and controllability > 0.5:
            return "confidence"
        if valence > 0.15 and goal_congruence > 0.55:
            return "hope"
        if abs(valence) < 0.12 and certainty > 0.55:
            return "calm"
        return "frustration" if valence < 0 else "relief"

    def _emotion_target(self, dominant_emotion: str, valence: float) -> float:
        """把离散情绪标签映射为旧标量 emotion 的目标方向。"""
        if dominant_emotion in EMOTION_SENTIMENT:
            return EMOTION_SENTIMENT[dominant_emotion]
        return self._clamp_signed(valence)

    def _emotion_intensity(self) -> float:
        """融合旧标量和新多维状态，得到兼容的情绪强度。"""
        state_intensity = self.state.emotion_state.intensity if self.state.emotion_state else 0.0
        return self._clamp(
            abs(self.state.emotion) * 0.55
            + self.state.stress * 0.25
            + state_intensity * 0.2
        )

    def _appraisal_vector(self, appraisal: AppraisalRecord) -> List[float]:
        """把 appraisal 压成轻量向量，供 schema 更新使用。"""
        return [
            appraisal.relevance,
            appraisal.valence,
            appraisal.goal_congruence,
            appraisal.controllability,
            appraisal.certainty,
            appraisal.coping_potential,
        ]

    def _extract_post_emotion_features(self, item: dict) -> Dict[str, List[float] | float]:
        """从帖子中读取扩展情绪字段，缺失时回退到旧 sentiment。"""
        sentiment = float(item.get("sentiment", 0.0))
        pad = item.get("pad") or [
            sentiment,
            min(1.0, abs(sentiment)),
            sentiment * 0.5,
        ]
        latent = item.get("emotion_latent") or _project_emotion_latent(
            item.get("emotion_probs", {}),
            pad,
            item.get("intensity", abs(sentiment)),
        )
        return {
            "sentiment": sentiment,
            "pad": [float(value) for value in pad[:3]],
            "latent": [float(value) for value in latent[:LATENT_DIM]],
            "weight": float(max(0.05, item.get("exposure_score", 1.0))),
        }

    def _summarize_feed_for_appraisal(self, feed: List[dict]) -> Dict[str, float]:
        """把当前 feed 压缩成供 router/expert 使用的社会场景摘要。"""
        visible = feed[: min(4, len(feed))]
        if not visible:
            return {
                "direction": 0.0,
                "exposure_pressure": 0.0,
                "exposure_polarity": 0.0,
                "consensus": 0.0,
                "dispersion": 0.0,
                "engagement": 0.0,
            }

        total_exposure = sum(float(item.get("exposure_score", 1.0)) for item in visible)
        total_exposure = max(total_exposure, 1e-6)
        weighted_direction = sum(
            float(item.get("sentiment", 0.0)) * float(item.get("exposure_score", 1.0))
            for item in visible
        ) / total_exposure
        avg_exposure = total_exposure / len(visible)
        avg_engagement = sum(
            float(item.get("like_count", 0) + item.get("share_count", 0))
            for item in visible
        ) / len(visible)
        sentiments = [float(item.get("sentiment", 0.0)) for item in visible]
        dispersion = max(sentiments) - min(sentiments) if len(sentiments) >= 2 else 0.0
        consensus = self._clamp(1.0 - dispersion)
        exposure_polarity = sum(
            float(item.get("sentiment", 0.0)) * float(item.get("exposure_score", 1.0))
            for item in visible
        ) / total_exposure
        return {
            "direction": self._clamp_signed(weighted_direction),
            "exposure_pressure": self._clamp(avg_exposure),
            "exposure_polarity": self._clamp_signed(exposure_polarity),
            "consensus": consensus,
            "dispersion": self._clamp(dispersion),
            "engagement": self._clamp(avg_engagement * 0.12),
        }

    def _summarize_contagion_features(self) -> Dict[str, float]:
        """把上一轮 contagion 缓存投影成 router 可直接读取的摘要。"""
        pad = self.state.last_contagion_pad or [0.0, 0.0, 0.0]
        vector = self.state.last_contagion_vector or [0.0] * LATENT_DIM
        return {
            "sentiment": self._clamp_signed(pad[0] if len(pad) > 0 else 0.0),
            "arousal": self._clamp(pad[1] if len(pad) > 1 else 0.0),
            "dominance": self._clamp_signed(pad[2] if len(pad) > 2 else 0.0),
            "dispersion": self._clamp(abs(vector[4] - vector[3]) if len(vector) > 4 else 0.0),
            "negative_mass": self._clamp(vector[4] if len(vector) > 4 else 0.0),
            "amplification": self._clamp(vector[12] if len(vector) > 12 else (vector[7] if len(vector) > 7 else 0.0)),
        }

    def _summarize_schema_summary(self) -> Dict[str, float]:
        """把当前 schema 压成 latent 编码器可直接读取的摘要。"""
        return {
            "support_bias": self._clamp_signed(self.state.schemas["support_tendency"] * 2 - 1),
            "threat_bias": self._clamp(self.state.schemas["threat_sensitivity"]),
            "efficacy_bias": self._clamp(self.state.schemas["self_efficacy"]),
        }

    def _summarize_memory(self) -> Dict[str, float]:
        """从最近记忆中提取一个轻量 summary，供 appraisal router 使用。"""
        memory_window = self.state.memory[-8:]
        if not memory_window:
            return {
                "valence_bias": 0.0,
                "coherence": 0.5,
                "feed_ratio": 0.0,
                "self_generated_ratio": 0.0,
                "salience": 0.0,
            }

        valences = [float(item.valence) for item in memory_window]
        avg_valence = sum(valences) / len(valences)
        spread = max(valences) - min(valences) if len(valences) >= 2 else 0.0
        feed_count = sum(1 for item in memory_window if item.source == "feed")
        self_count = sum(1 for item in memory_window if item.source.startswith("self"))
        salience = sum(abs(value) for value in valences) / len(valences)
        return {
            "valence_bias": self._clamp_signed(avg_valence),
            "coherence": self._clamp(1.0 - spread * 0.5),
            "feed_ratio": self._clamp(feed_count / len(memory_window)),
            "self_generated_ratio": self._clamp(self_count / len(memory_window)),
            "salience": self._clamp(salience),
        }

    def _encode_emotion_latent(
        self,
        emotion_probs: Dict[str, float],
        pad: List[float],
        sentiment: float,
        intensity: float,
        appraisal_summary: Optional[Dict[str, float]] = None,
        contagion_summary: Optional[Dict[str, float]] = None,
        schema_summary: Optional[Dict[str, float]] = None,
        text_context: Optional[Dict[str, object]] = None,
    ) -> List[float]:
        """通过表示模块生成可学习/可回退的情绪 latent。"""
        latent = self.emotion_representation.encode(
            emotion_probs=emotion_probs,
            pad=pad,
            sentiment=sentiment,
            intensity=intensity,
            appraisal_summary=appraisal_summary,
            contagion_summary=contagion_summary,
            schema_summary=schema_summary,
            text_context=text_context,
        )
        self.state.latent_runtime = dict(self.emotion_representation.last_run_metadata)
        return [float(item) for item in latent[:LATENT_DIM]]

    def _emotion_state_to_platform_payload(self) -> dict:
        """把 EmotionState 投影为平台可直接写入的序列化字段。"""
        state = self.state.emotion_state or EmotionState.from_projection(
            signed_valence=self.state.emotion,
            intensity=self._emotion_intensity(),
            dominant_label=self.state.dominant_emotion_label,
        )
        return {
            "emotion_probs": dict(state.emotion_probs),
            "dominant_emotion": state.dominant_label,
            "intensity": float(state.intensity),
            "sentiment": float(state.signed_valence),
            "pad": [float(item) for item in state.pad],
            "emotion_latent": [float(item) for item in state.latent],
        }

    @staticmethod
    def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
        return max(minimum, min(maximum, float(value)))

    @staticmethod
    def _clamp_signed(value: float, limit: float = 1.0) -> float:
        return max(-limit, min(limit, float(value)))


def _build_emotion_probs(
    dominant_label: str,
    signed_valence: float,
    intensity: float,
) -> Dict[str, float]:
    """根据主导情绪和标量投影构造一个可导出的 baseline 概率分布。"""
    labels = list(EMOTION_SENTIMENT.keys())
    probs = {label: 0.01 for label in labels}
    if dominant_label not in probs:
        dominant_label = _infer_label_from_valence(signed_valence)
    probs[dominant_label] = 0.55 + 0.3 * _clamp(intensity)
    if signed_valence >= 0:
        probs["confidence"] += 0.08 * _clamp(intensity)
        probs["hope"] += 0.06 * _clamp(intensity)
        probs["relief"] += 0.04
    else:
        probs["fear"] += 0.08 * _clamp(intensity)
        probs["anxiety"] += 0.06 * _clamp(intensity)
        probs["anger"] += 0.04 * max(0.0, -signed_valence)
    total = sum(probs.values()) or 1.0
    return {key: float(value / total) for key, value in probs.items()}


def _project_emotion_latent(
    emotion_probs: Dict[str, float],
    pad: List[float],
    intensity: float,
) -> List[float]:
    """兼容旧调用点的 latent 构造入口，内部转发到统一编码器。"""
    sentiment = _clamp_signed(pad[0] if len(pad) > 0 else 0.0)
    return EmotionLatentEncoder.encode(
        emotion_probs=emotion_probs,
        pad=pad,
        sentiment=sentiment,
        intensity=intensity,
    )


def _infer_label_from_valence(signed_valence: float) -> str:
    """从带符号效价做最粗粒度的离散标签回退。"""
    if signed_valence > 0.35:
        return "confidence"
    if signed_valence > 0.1:
        return "hope"
    if signed_valence < -0.5:
        return "fear"
    if signed_valence < -0.2:
        return "anxiety"
    return "calm"


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _clamp_signed(value: float, limit: float = 1.0) -> float:
    return max(-limit, min(limit, float(value)))
