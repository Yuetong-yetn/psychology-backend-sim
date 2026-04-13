"""社会心理 agent。

这个文件实现了一个最小可运行的认知-情绪耦合 agent，核心流程是：

环境输入 -> appraisal -> emotion 更新 -> schema 更新 -> equilibrium -> 行为决策

同时保留情绪反馈、情绪传播与图式更新之间的闭环。
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from config.backend_settings import AGENT_DYNAMICS
from .agent_action import SocialAction
from .agent_environment import SocialEnvironment
from .appraisal_moe import AppraisalMoEConfig, AppraisalRouter
from .cam_memory import CAMMemoryGraph
from .emotion_representation import (
    LATENT_DIM,
    EmotionRepresentationConfig,
    EmotionRepresentationModule,
)
from social_platform.channel import Channel

# 这些情绪标签与平台层保持一致，便于共享概率分布和 PAD 投影。

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

E_CAM_T_EMBED_DIM = 16

_OASIS_ACTION_SUMMARY = {
    "refresh": "Refresh the feed and continue observing socially salient content.",
    "create_post": "Publish a new public post aligned with the current topic.",
    "create_comment": "Write a direct public reply under a visible post.",
    "repost": "Repost a visible post to amplify its reach.",
    "quote_post": "Share a visible post with added commentary.",
    "like_post": "Endorse a visible post through a lightweight action.",
    "follow": "Increase engagement with the source account or topic.",
    "search_posts": "Search for additional context before acting strongly.",
    "unfollow": "Reduce engagement with a stressful source.",
    "mute": "Suppress a stressful topic or account from attention.",
    "do_nothing": "Avoid public interaction for this step.",
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
        """将多源情绪线索编码为统一潜在向量。

        Args:
            emotion_probs: 离散情绪概率分布。
            pad: PAD 三维情绪投影。
            sentiment: 带符号情感极性。
            intensity: 情绪强度。
            appraisal_summary: 可选 appraisal 摘要。
            contagion_summary: 可选情绪感染摘要。
            schema_summary: 可选 schema 摘要。
            text_context: 可选文本上下文特征。

        Returns:
            List[float]: 归一化后的潜在向量。
        """
        # 兼容旧调用点：静态编码器继续可用，但内部转发到新的可插拔表示模块。
        # 兼容旧调用点：静态编码器继续可用，但内部转发到新的表示模块。
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
        """根据情绪投影信息构造标准化情绪状态。

        Args:
            signed_valence: 带符号情感极性。
            intensity: 情绪强度。
            dominant_label: 主导情绪标签。
            pad: 可选 PAD 三维向量。
            latent: 可选潜在情绪向量。
            emotion_probs: 可选离散情绪分布。
            appraisal_summary: appraisal 摘要。
            contagion_summary: 感染摘要。
            schema_summary: schema 摘要。

        Returns:
            EmotionState: 构造完成的情绪状态对象。
        """
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
    goal_conduciveness: float
    controllability: float
    agency: str
    certainty: float
    novelty: float
    coping_potential: float
    unpredictability: float
    goal_relevance_signal: float
    performance: float
    confirmation: float
    dominant_emotion: str
    emotion_intensity: float
    cognitive_mode: str

    @property
    def goal_congruence(self) -> float:
        """返回与旧字段兼容的目标一致性值。"""
        return self.goal_conduciveness

    @property
    def epsilon_t(self) -> float:
        """返回与旧字段兼容的 epsilon 值。"""
        return self.unpredictability

    @property
    def zeta_t(self) -> float:
        """返回与旧字段兼容的 zeta 值。"""
        return self.goal_relevance_signal

    @property
    def P_t(self) -> float:
        """返回与旧字段兼容的表现代理值。"""
        return self.coping_potential


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
    # 核心字段速记：
    # `emotion` 是标量情绪方向，`emotion_state` 是完整多维情绪表征。
    # `schemas` 保存支持倾向 / 威胁敏感度 / 自我效能这三个核心图式参数。
    # `equilibrium` / `equilibrium_index` 表示内部平衡程度。
    # `epsilon` 表示不可预测性，`zeta` 表示目标相关显著性。
    # `last_contagion_pad` / `last_contagion_vector` 记录最近一次情绪感染结果。
    # `appraisal_runtime` / `latent_runtime` 记录 provider 或 fallback 的运行元信息。
    """agent 的动态心理状态。"""

    emotion: float = 0.0  # 标量情绪值。
    emotion_state: Optional[EmotionState] = None  # 多维情绪状态。
    stress: float = 0.0  # 当前压力。
    expectation: float = 0.5  # 当前预期。
    satisfaction: float = 0.0  # 当前满意度。
    dopamine_level: float = 0.5  # 当前多巴胺。
    performance_prediction: float = 0.5  # 表现预测值。
    influence_score: float = 0.5  # 当前影响力。
    schemas: Dict[str, float] = field(
        default_factory=lambda: {
            "support_tendency": 0.5,
            "threat_sensitivity": 0.5,
            "self_efficacy": 0.5,
        }
    )  # 当前图式。
    schema_flexibility: float = 0.5  # 图式可塑性。
    equilibrium: float = 0.7  # 当前稳态。
    equilibrium_index: float = 0.7  # 快速稳态指标。
    last_cognitive_mode: str = "equilibrium"  # 最近认知模式。
    empathy_level: float = 0.55  # 共情水平。
    empathized_negative_emotion: float = 0.0  # 共情到的负面情绪。
    dopamine_prediction_error: float = 0.0  # 多巴胺预测误差。
    moral_reward: float = 0.5  # 道德奖励。
    social_influence_reward: float = 0.0  # 社会影响奖励。
    semantic_similarity: float = 0.0  # 语义相似度。
    explicit_tom_triggered: bool = False  # 是否触发显式 ToM。
    beliefs: Dict[str, float] = field(default_factory=dict)  # 当前信念。
    desires: Dict[str, float] = field(default_factory=dict)  # 稳定动机。
    intentions: Dict[str, float] = field(default_factory=dict)  # 当前意图。
    knowledge: Dict[str, object] = field(default_factory=dict)  # 当前知识摘要。
    epsilon: float = 0.0  # 不可预测性。
    zeta: float = 0.0  # 目标相关信号。
    last_appraisal: Optional[AppraisalRecord] = None  # 最近 appraisal。
    appraisal_history: List[AppraisalRecord] = field(default_factory=list)  # appraisal 历史。
    last_contagion_pad: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])  # 最近传染 PAD。
    last_contagion_vector: List[float] = field(default_factory=lambda: [0.0] * LATENT_DIM)  # 最近传染 latent。
    appraisal_runtime: Dict[str, object] = field(default_factory=dict)  # appraisal 运行信息。
    latent_runtime: Dict[str, object] = field(default_factory=dict)  # latent 运行信息。
    memory: List[MemoryItem] = field(default_factory=list)  # 最近记忆。
    schemata_graph: CAMMemoryGraph = field(default_factory=CAMMemoryGraph)  # CAM 记忆图。

    def __post_init__(self) -> None:
        """补齐状态缺省项，并对关键变量做初始化规范化。"""
        if self.emotion_state is None:
            inferred_label = _infer_label_from_valence(self.emotion)
            self.emotion_state = EmotionState.from_projection(
                signed_valence=self.emotion,
                intensity=abs(self.emotion),
                dominant_label=inferred_label,
            )
        else:
            self.emotion = _clamp_signed(self.emotion_state.signed_valence)
        self.equilibrium_index = _clamp(self.equilibrium_index if self.equilibrium_index else self.equilibrium)
        if not self.desires:
            self.desires = {
                "affiliation": 0.55,
                "self_expression": 0.55,
                "stability": 0.5,
                "information_gain": 0.5,
            }
        if not self.beliefs:
            self.beliefs = {
                "environment_valence": 0.0,
                "social_pressure": 0.0,
                "goal_alignment": 0.5,
                "self_efficacy": self.schemas.get("self_efficacy", 0.5),
            }
        if not self.intentions:
            self.intentions = {
                "observe": 0.5,
                "participate": 0.5,
                "amplify": 0.5,
                "withdraw": 0.0,
                "support_others": 0.5,
            }
        if not self.knowledge:
            self.knowledge = {
                "topic_consensus": 0.5,
                "topic_polarization": 0.0,
                "salient_author_id": None,
                "salient_cluster_summaries": [],
            }

    @property
    def dominant_emotion_label(self) -> str:
        """返回当前主导情绪标签。"""
        if self.emotion_state is not None:
            return self.emotion_state.dominant_label
        return _infer_label_from_valence(self.emotion)

    @property
    def coping_potential(self) -> float:
        """返回当前轮 appraisal 的应对潜力。"""
        if self.last_appraisal is not None:
            return _clamp(self.last_appraisal.coping_potential)
        return 0.5

    @property
    def performance(self) -> float:
        """返回当前轮 appraisal 的表现估计。"""
        if self.last_appraisal is not None:
            return _clamp(self.last_appraisal.performance)
        return 0.5

    @property
    def confirmation(self) -> float:
        """返回当前轮 confirmation 信号。"""
        if self.last_appraisal is not None:
            return _clamp_signed(self.last_appraisal.confirmation)
        return 0.0

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
    suggested_action: str = "refresh"
    suggested_actions: List[str] = field(default_factory=list)


@dataclass
class AgentRoundResult:
    """单轮执行结果，供 environment 记录和导出。"""

    profile: AgentProfile
    state: AgentState
    decision: AgentDecision
    behavior_output: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """将单轮结果转换为可序列化字典。"""
        return {
            "profile": asdict(self.profile),
            "state": {
                "emotion": self.state.emotion,
                "emotion_state": asdict(self.state.emotion_state),
                "stress": self.state.stress,
                "expectation": self.state.expectation,
                "satisfaction": self.state.satisfaction,
                "dopamine_level": self.state.dopamine_level,
                "performance_prediction": self.state.performance_prediction,
                "influence_score": self.state.influence_score,
                "schemas": self.state.schemas,
                "schema_flexibility": self.state.schema_flexibility,
                "equilibrium_index": self.state.equilibrium_index,
                "last_cognitive_mode": self.state.last_cognitive_mode,
                "dominant_emotion_label": self.state.dominant_emotion_label,
                "empathy_level": self.state.empathy_level,
                "empathized_negative_emotion": self.state.empathized_negative_emotion,
                "dopamine_prediction_error": self.state.dopamine_prediction_error,
                "moral_reward": self.state.moral_reward,
                "social_influence_reward": self.state.social_influence_reward,
                "semantic_similarity": self.state.semantic_similarity,
                "explicit_tom_triggered": self.state.explicit_tom_triggered,
                "beliefs": self.state.beliefs,
                "desires": self.state.desires,
                "intentions": self.state.intentions,
                "knowledge": self.state.knowledge,
                "epsilon": self.state.epsilon,
                "zeta": self.state.zeta,
                "coping_potential": self.state.coping_potential,
                "performance": self.state.performance,
                "confirmation": self.state.confirmation,
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
            "behavior_output": dict(self.behavior_output),
        }


class SimulatedAgent:
    """带认知-情绪耦合的最小 social agent。"""

    contagion_weight: float = AGENT_DYNAMICS.contagion_weight
    beta_m: float = AGENT_DYNAMICS.beta_m
    emotion_valence_bias: float = AGENT_DYNAMICS.emotion_valence_bias
    emotion_uncertainty_bias: float = AGENT_DYNAMICS.emotion_uncertainty_bias
    emotion_control_bias: float = AGENT_DYNAMICS.emotion_control_bias
    contagion_threat_gain: float = AGENT_DYNAMICS.contagion_threat_gain
    contagion_efficacy_loss: float = AGENT_DYNAMICS.contagion_efficacy_loss
    eta: float = AGENT_DYNAMICS.eta
    alpha_E: float = AGENT_DYNAMICS.alpha_E
    gamma_DA: float = AGENT_DYNAMICS.gamma_DA
    lambda_pred: float = AGENT_DYNAMICS.lambda_pred
    kappa_zeta: float = AGENT_DYNAMICS.kappa_zeta
    tau_epsilon: float = AGENT_DYNAMICS.tau_epsilon
    kappa_eq: float = AGENT_DYNAMICS.kappa_eq
    eq_recovery: float = AGENT_DYNAMICS.eq_recovery
    lambda_S: float = AGENT_DYNAMICS.lambda_S

    def __init__(
        self,
        profile: AgentProfile,
        state: AgentState | None = None,
        mode: str = "moe",
        llm_provider: str = "ollama",
        enable_fallback: bool = True,
        appraisal_use_llm: bool = True,
        checkpoint_dir: Optional[str] = None,
        channel: Channel | None = None,
        agent_graph: object | None = None,
    ):
        """初始化智能体实例及其认知模块。"""
        self.agent_id = profile.agent_id
        self.profile = profile
        self.state = state or AgentState()
        self.channel = channel
        self.agent_graph = agent_graph
        self.runtime_platform = None
        self.action = SocialAction(agent_id=self.agent_id, owner=self, channel=channel)
        self.environment = SocialEnvironment(agent_id=self.agent_id, action=self.action)
        self.state.desires = self._initialize_desires(self.state.desires)
        self.state.empathy_level = self._initialize_empathy_level(self.state.empathy_level)
        public_mode = "fallback" if mode == "fallback" else "moe"
        appraisal_mode = public_mode if appraisal_use_llm else "fallback"
        appraisal_fallback_reason = None
        if public_mode == "fallback":
            appraisal_fallback_reason = "mode_forced_fallback"
        elif not appraisal_use_llm:
            appraisal_fallback_reason = "ratio_routed_to_local"

        self.appraisal_router = AppraisalRouter(
            AppraisalMoEConfig(
                mode=appraisal_mode,
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
            "mode": appraisal_mode,
            "provider": None,
            "model": None,
            "source": "local",
            "fallback_used": appraisal_mode == "fallback",
            "fallback_reason": appraisal_fallback_reason,
        }
        self.state.latent_runtime = {
            "mode": public_mode,
            "provider": None,
            "model": None,
            "source": "local",
            "fallback_used": public_mode == "fallback",
            "fallback_reason": "mode_forced_fallback" if public_mode == "fallback" else None,
        }

    def bind_runtime(
        self,
        *,
        channel: Channel | None = None,
        agent_graph: object | None = None,
        platform: object | None = None,
    ) -> None:
        """在运行期绑定平台、通道和关系图对象。"""
        if channel is not None:
            self.channel = channel
            self.action.bind(channel=channel)
        if agent_graph is not None:
            self.agent_graph = agent_graph
        if platform is not None:
            self.runtime_platform = platform
        # `action` 和 `environment` 都依赖当前 agent 实例本身，因此最后统一回绑。
        self.action.bind(owner=self)
        self.environment.bind(action=self.action)

    def remember(
        self,
        *,
        round_index: int,
        source: str,
        content: str,
        valence: float,
    ) -> None:
        """写入一条短期记忆，并截断记忆窗口长度。"""
        self.state.memory.append(
            MemoryItem(
                round_index=round_index,
                source=source,
                content=content,
                valence=valence,
            )
        )
        self.state.memory = self.state.memory[-12:]

    def build_emotion_state_projection(self) -> EmotionState:
        """返回当前状态对应的标准化情绪投影。"""
        return self.state.emotion_state or EmotionState.from_projection(
            signed_valence=self.state.emotion,
            intensity=self._emotion_intensity(),
            dominant_label=self.state.dominant_emotion_label,
        )

    def emotion_intensity(self) -> float:
        """返回当前情绪强度。"""
        return self._emotion_intensity()

    def platform_emotion_payload(self) -> dict:
        """导出供平台层消费的简化情绪载荷。"""
        return self._emotion_state_to_platform_payload()

    def clamp(self, value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
        """提供实例级数值裁剪便捷入口。"""
        return self._clamp(value, minimum=minimum, maximum=maximum)

    def receive_information(
        self,
        round_index: int,
        scenario_prompt: str,
        feed: List[dict],
    ) -> None:
        """接收外部信息、写入记忆，并执行情绪传播。"""
        # 先抽取环境信号，再把场景和高曝光 feed 写入短期记忆。
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
        # 这里是 agent 的核心状态流水线，顺序基本对应心理加工阶段。
        event = self._extract_environment_signal(feed, scenario_prompt)
        appraisal = self._build_appraisal(event, feed)
        self._update_cam_memory(event)
        self._update_ecam_t_state(appraisal, event, feed)
        self._update_emotion(appraisal)
        self._update_schema(appraisal)
        self._rebalance(appraisal)
        self._update_beliefs_and_intentions(appraisal, feed)
        self.state.last_appraisal = appraisal
        self.state.appraisal_history.append(appraisal)
        self.state.appraisal_history = self.state.appraisal_history[-8:]

    def decide_action(self, feed: List[dict]) -> AgentDecision:
        """根据 appraisal 和情绪调节后的 action score 选择行为。"""
        appraisal = self.state.last_appraisal
        if appraisal is None:
            appraisal = AppraisalRecord(
                relevance=0.0,
                valence=0.0,
                goal_conduciveness=0.5,
                controllability=0.5,
                agency="external",
                certainty=0.5,
                novelty=0.0,
                coping_potential=0.5,
                unpredictability=0.0,
                goal_relevance_signal=0.0,
                performance=0.5,
                confirmation=0.0,
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
        altruistic_drive = self._clamp(
            self.state.empathized_negative_emotion * self.state.empathy_level
        )
        social_influence_reward = self._clamp(self.state.social_influence_reward)
        tom_observation_bias = 0.12 if self.state.explicit_tom_triggered else 0.0
        suggested_action, suggested_actions = self._suggest_oasis_actions(
            self.state.epsilon,
            self.state.zeta,
            self.state.coping_potential,
            self.state.satisfaction,
        )
        if not feed:
            return AgentDecision(
                action="create_post",
                content=self._build_post_content(opening=True),
                influence_delta=0.03 + emotion_intensity * 0.04,
                reason="No visible posts, so the agent opens the discussion.",
                suggested_action=suggested_action,
                suggested_actions=suggested_actions,
            )

        hottest = feed[0]
        target_agent_id = hottest["author_id"]

        # 不同行为分值由 appraisal、PAD、latent 和社会奖励共同决定。
        browse_score = self._clamp(
            (1 - self.state.equilibrium) * 0.35
            + (1 - appraisal.certainty) * 0.25
            + self.state.stress * 0.2
            + arousal * 0.08
            + tom_observation_bias
            + (0.15 if appraisal.dominant_emotion in {"anxiety", "fear", "guilt", "shame"} else 0.0)
        )
        create_score = self._clamp(
            appraisal.goal_conduciveness * 0.32
            + appraisal.controllability * 0.22
            + self.state.expectation * 0.16
            + self.state.equilibrium * 0.12
            + max(0.0, pleasure) * 0.14
            + max(0.0, dominance) * 0.04
            + max(0.0, latent[8]) * 0.04
            + social_influence_reward * 0.18
            + altruistic_drive * 0.08
        )
        reply_score = self._clamp(
            appraisal.relevance * 0.18
            + (1 - appraisal.goal_conduciveness) * 0.18
            + self.state.stress * 0.22
            + emotion_intensity * 0.16
            + max(0.0, arousal - 0.2) * 0.06
            + max(0.0, latent[11]) * 0.04
            + altruistic_drive * 0.28
            + (0.2 if appraisal.dominant_emotion in {"anger", "frustration"} else 0.0)
        )
        like_score = self._clamp(
            appraisal.goal_conduciveness * 0.28
            + appraisal.certainty * 0.18
            + max(0.0, pleasure) * 0.18
            + max(0.0, latent[5] - latent[6]) * 0.06
            + (0.12 if appraisal.dominant_emotion in {"confidence", "relief", "hope"} else 0.0)
        )
        share_score = self._clamp(
            appraisal.relevance * 0.2
            + appraisal.goal_conduciveness * 0.24
            + self.state.influence_score * 0.14
            + emotion_intensity * 0.12
            + hottest.get("intensity", 0.0) * 0.14
            + max(0.0, arousal - 0.2) * 0.08
            + max(0.0, latent[12]) * 0.04
            + social_influence_reward * 0.22
        )
        # 显式 ToM 与外部建议会对行为分值再做一轮偏置修正。
        if self.state.explicit_tom_triggered and altruistic_drive < 0.25:
            create_score = self._clamp(create_score - 0.06)
            reply_score = self._clamp(reply_score - 0.03)
        if suggested_action in {"unfollow", "mute", "do_nothing"}:
            browse_score = self._clamp(browse_score + 0.18)
            create_score = self._clamp(create_score - 0.12)
            reply_score = self._clamp(reply_score - 0.08)
            share_score = self._clamp(share_score - 0.1)
        elif suggested_action in {"create_post", "create_comment", "quote_post", "repost"}:
            create_score = self._clamp(create_score + 0.15)
            reply_score = self._clamp(reply_score + 0.08)
            share_score = self._clamp(share_score + 0.08)
        elif suggested_action in {"refresh", "search_posts"}:
            browse_score = self._clamp(browse_score + 0.1)

        self.state.intentions = {
            "observe": self._clamp(browse_score),
            "participate": self._clamp(max(create_score, reply_score, like_score)),
            "amplify": self._clamp(share_score),
            "withdraw": self._clamp(
                max(
                    0.0,
                    -self.state.satisfaction,
                    self.state.epsilon - self.state.coping_potential,
                )
            ),
            "support_others": self._clamp(altruistic_drive),
        }

        best_score = max(browse_score, create_score, reply_score, like_score, share_score)

        if browse_score >= best_score:
            return AgentDecision(
                action="browse_feed",
                content="Continue observing the feed before taking stronger action.",
                target_post_id=hottest["post_id"],
                target_agent_id=target_agent_id,
                influence_delta=0.01 + emotion_intensity * 0.02,
                reason="Low certainty or explicit ToM observation favors gathering more context.",
                suggested_action=suggested_action,
                suggested_actions=suggested_actions,
                metadata={
                    "moral_reward": self.state.moral_reward,
                    "social_influence_reward": self.state.social_influence_reward,
                    "explicit_tom_triggered": self.state.explicit_tom_triggered,
                },
            )

        if reply_score >= best_score:
            reply_delta = -0.02 if pleasure < 0 else 0.03
            reply_delta *= 1 + emotion_intensity
            return AgentDecision(
                action="reply_post",
                content=self._build_reply_content(feed, altruistic_drive),
                target_post_id=hottest["post_id"],
                target_agent_id=target_agent_id,
                influence_delta=reply_delta,
                reason="Empathic tension or strong relevance favors a direct social response.",
                suggested_action=suggested_action,
                suggested_actions=suggested_actions,
                metadata={
                    "moral_reward": self.state.moral_reward,
                    "social_influence_reward": self.state.social_influence_reward,
                    "explicit_tom_triggered": self.state.explicit_tom_triggered,
                },
            )

        if share_score >= best_score:
            return AgentDecision(
                action="share_post",
                content=self._build_share_content(feed),
                target_post_id=hottest["post_id"],
                target_agent_id=target_agent_id,
                influence_delta=0.04 + emotion_intensity * 0.04,
                metadata={"shared_post_id": hottest["post_id"]},
                reason="Predicted social influence reward favors amplification through sharing.",
                suggested_action=suggested_action,
                suggested_actions=suggested_actions,
            )

        if like_score >= best_score:
            return AgentDecision(
                action="like_post",
                content="Signal agreement through a lightweight endorsement.",
                target_post_id=hottest["post_id"],
                target_agent_id=target_agent_id,
                influence_delta=0.02 + emotion_intensity * 0.02,
                reason="Congruent appraisal with low action cost favors liking.",
                suggested_action=suggested_action,
                suggested_actions=suggested_actions,
            )

        return AgentDecision(
            action="create_post",
            content=self._build_post_content(opening=False, altruistic=altruistic_drive > 0.28),
            influence_delta=0.03 + emotion_intensity * 0.03,
            reason="Goal-conducive appraisal and expected social influence favor posting.",
            suggested_action=suggested_action,
            suggested_actions=suggested_actions,
            metadata={
                "moral_reward": self.state.moral_reward,
                "social_influence_reward": self.state.social_influence_reward,
                "explicit_tom_triggered": self.state.explicit_tom_triggered,
            },
        )

    def build_platform_actions(self, decision: AgentDecision) -> List[dict]:
        """Project a decision into platform action requests."""
        return [
            {"action": item.action, "payload": dict(item.payload)}
            for item in self.action.build_action_requests(decision)
        ]

    def finalize_platform_actions(
        self,
        decision: AgentDecision,
        round_index: int,
        dispatch_results: List[dict],
    ) -> None:
        """Update local state after dispatched platform actions complete."""
        self.action.finalize_action_effects(decision, round_index, dispatch_results)

    def run_round(
        self,
        round_index: int,
        scenario_prompt: str,
        feed: List[dict],
    ) -> AgentRoundResult:
        """Run one round of cognition and decision-making."""
        self.receive_information(round_index, scenario_prompt, feed)
        self.update_state(feed, scenario_prompt)
        decision = self.decide_action(feed)
        behavior_output = self._build_behavior_output(
            decision,
            feed=feed,
            scenario_prompt=scenario_prompt,
            round_index=round_index,
        )
        return AgentRoundResult(
            profile=self.profile,
            state=self.state,
            decision=decision,
            behavior_output=behavior_output,
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
                "satisfaction": self.state.satisfaction,
                "dopamine_level": self.state.dopamine_level,
                "performance_prediction": self.state.performance_prediction,
                "influence_score": self.state.influence_score,
                "schemas": self.state.schemas,
                "schema_flexibility": self.state.schema_flexibility,
                "equilibrium_index": self.state.equilibrium_index,
                "last_cognitive_mode": self.state.last_cognitive_mode,
                "dominant_emotion_label": self.state.dominant_emotion_label,
                "empathy_level": self.state.empathy_level,
                "empathized_negative_emotion": self.state.empathized_negative_emotion,
                "dopamine_prediction_error": self.state.dopamine_prediction_error,
                "moral_reward": self.state.moral_reward,
                "social_influence_reward": self.state.social_influence_reward,
                "semantic_similarity": self.state.semantic_similarity,
                "explicit_tom_triggered": self.state.explicit_tom_triggered,
                "beliefs": self.state.beliefs,
                "desires": self.state.desires,
                "intentions": self.state.intentions,
                "knowledge": self.state.knowledge,
                "epsilon": self.state.epsilon,
                "zeta": self.state.zeta,
                "coping_potential": self.state.coping_potential,
                "performance": self.state.performance,
                "confirmation": self.state.confirmation,
                "last_appraisal": (
                    asdict(self.state.last_appraisal)
                    if self.state.last_appraisal is not None
                    else None
                ),
                "last_contagion_pad": self.state.last_contagion_pad,
                "last_contagion_vector": self.state.last_contagion_vector,
                "appraisal_runtime": dict(self.state.appraisal_runtime),
                "latent_runtime": dict(self.state.latent_runtime),
                "action_runtime": self.action.snapshot_runtime_profile(),
                "memory_size": len(self.state.memory),
                "appraisal_count": len(self.state.appraisal_history),
            },
        }

    def _build_post_content(self, opening: bool, altruistic: bool = False) -> str:
        """根据当前主导情绪生成最小发帖文案。"""
        if opening:
            return f"{self.profile.name} starts discussing the current social issue."

        emotion_label = self.state.dominant_emotion_label
        if altruistic:
            tone = "supportive"
        elif emotion_label in {"anger", "frustration"}:
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

    def _build_reply_content(self, feed: List[dict], altruistic_drive: float) -> str:
        """根据当前共情水平与上下文生成回复文案。"""
        if altruistic_drive > 0.28:
            return (
                f"{self.profile.name} responds with reassurance, attempting to reduce tension "
                "and support the people affected by the discussion."
            )
        if self.state.explicit_tom_triggered:
            return (
                f"{self.profile.name} asks a clarifying follow-up that tests what others "
                "currently believe before escalating the conversation."
            )
        return f"{self.profile.name} responds directly to the current discussion."

    def _build_share_content(self, feed: List[dict]) -> str:
        """根据当前社会影响奖励生成转发文案。"""
        if self.state.social_influence_reward > 0.22:
            return (
                f"{self.profile.name} amplifies the post because it is likely to shift "
                "other agents' beliefs in a meaningful way."
            )
        return f"{self.profile.name} amplifies a post aligned with the current view."

    def _extract_environment_signal(
        self,
        feed: List[dict],
        scenario_prompt: str,
    ) -> Dict[str, object]:
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

        observation_text = self._compose_observation_text(feed, scenario_prompt)
        event_embedding = self._text_to_embedding_hash(observation_text)
        observed_round_index = self.state.memory[-1].round_index if self.state.memory else 0
        graph_match = self.state.schemata_graph.best_match(event_embedding, observed_round_index)
        semantic_similarity = self._clamp(float(graph_match.get("best_similarity", 0.0)))
        if self.state.schemata_graph.nodes:
            epsilon = self._clamp(1.0 - semantic_similarity)
        else:
            belief_embedding = self._belief_embedding()
            if belief_embedding:
                epsilon = self._clamp(
                    1.0 - self._cosine_sim(event_embedding, belief_embedding)
                )
            else:
                epsilon = novelty
        empathized_negative_emotion = self._estimate_empathized_negative_emotion(feed_window)

        return {
            "direction": direction,
            "risk": risk,
            "novelty": novelty,
            "consistency": consistency,
            "observation_text": observation_text,
            "event_embedding": event_embedding,
            "unpredictability": epsilon,
            "semantic_similarity": semantic_similarity,
            "neighbor_candidates": list(graph_match.get("candidates", [])),
            "observed_round_index": observed_round_index,
            "empathized_negative_emotion": empathized_negative_emotion,
            "observed_agent_ids": [
                int(item["author_id"]) for item in feed_window if item.get("author_id") is not None
            ],
        }

    def _build_appraisal(
        self,
        event: Dict[str, object],
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
            "goal_conduciveness": prior_goal_congruence,
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
        )
        self.state.appraisal_runtime = dict(self.appraisal_router.last_run_metadata)
        relevance = fused["relevance"]
        valence = fused["valence"]
        goal_conduciveness = fused["goal_conduciveness"]
        controllability = fused["controllability"]
        certainty = fused["certainty"]
        coping_potential = fused["coping_potential"]
        unpredictability = self._clamp(float(event.get("unpredictability", event["novelty"])))
        goal_relevance_signal = self._clamp_signed(goal_conduciveness * 2 - 1)
        performance = self._estimate_performance(
            valence=valence,
            goal_conduciveness=goal_conduciveness,
            certainty=certainty,
            coping_potential=coping_potential,
            feed=feed,
        )
        confirmation = performance - self.state.expectation

        agency = self._infer_agency(feed, valence)
        dominant_emotion = self._map_emotion(
            valence=valence,
            goal_conduciveness=goal_conduciveness,
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
            goal_conduciveness=goal_conduciveness,
            controllability=controllability,
            agency=agency,
            certainty=certainty,
            novelty=event["novelty"],
            coping_potential=coping_potential,
            unpredictability=unpredictability,
            goal_relevance_signal=goal_relevance_signal,
            performance=performance,
            confirmation=confirmation,
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
        update_rate = self.beta_m * (1 + self.state.stress) * emotion_intensity
        update_rate = self._clamp(
            update_rate
            + max(0.0, emotion_pad[1]) * 0.04
            + max(0.0, contagion_pad[1]) * 0.02
        )
        accommodation_strength = self._clamp(
            appraisal.novelty
            * (1 - appraisal.goal_conduciveness)
            * (1 - appraisal.certainty)
            * (0.6 + self.state.schema_flexibility * 0.8)
            * (0.75 + emotion_intensity * 0.5)
        )
        assimilation_strength = self._clamp(update_rate * (1 - accommodation_strength))
        accommodation_rate = self._clamp(update_rate * accommodation_strength)

        direction = self._clamp_signed(appraisal.goal_conduciveness * 2 - 1)
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
            + appraisal.goal_conduciveness * 0.16
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
        self.state.equilibrium = self._clamp(
            self.state.equilibrium * 0.7 + self.state.equilibrium_index * 0.3
        )
        self.state.equilibrium_index = self._clamp(
            self.state.equilibrium_index * 0.7 + self.state.equilibrium * 0.3
        )
        if self.state.equilibrium > 0.72 and self._emotion_intensity() < 0.35:
            self.state.last_cognitive_mode = "equilibrium"

    def _update_cam_memory(self, event: Dict[str, object]) -> None:
        """将当前观察事件写入 CAM 记忆图，并同步更新摘要信息。"""
        round_index = int(event.get("observed_round_index", 0))
        update = self.state.schemata_graph.add_event(
            round_index=round_index,
            source="observation",
            content=str(event.get("observation_text", "")),
            embedding=list(event.get("event_embedding", [])),
            valence=float(event.get("direction", 0.0)),
            conflict_penalty=self.kappa_eq,
        )
        self.state.semantic_similarity = self._clamp(
            float(update.get("semantic_similarity", event.get("semantic_similarity", 0.0)))
        )
        self.state.equilibrium_index = self._clamp(
            self.state.equilibrium_index + float(update.get("conflict_delta", 0.0))
        )
        salient_node_id = int(update.get("node_id", 0) or 0)
        self.state.knowledge["salient_cluster_summaries"] = (
            self.state.schemata_graph.cluster_summary_for_node(salient_node_id)
        )
        self.state.knowledge["cam_candidates"] = list(update.get("candidate_ids", []))
        self.state.knowledge["cam_replicated_nodes"] = list(update.get("replicated_ids", []))

    def _update_ecam_t_state(
        self,
        appraisal: AppraisalRecord,
        event: Dict[str, object],
        feed: List[dict],
    ) -> None:
        """根据 appraisal 与反馈信号更新 ECAM-T 核心状态。"""
        epsilon = self._clamp(float(event.get("unpredictability", appraisal.novelty)))
        zeta = self._clamp_signed(appraisal.goal_relevance_signal)
        performance = self._clamp(appraisal.performance)
        confirmation = performance - self.state.expectation
        empathized_negative_emotion = self._clamp(
            float(event.get("empathized_negative_emotion", 0.0))
        )
        # firing_rate 用来近似本轮“主观表现”对内部奖励系统的驱动强度。
        firing_rate = self._clamp(
            performance
            - empathized_negative_emotion * self.state.empathy_level * 0.35
            + max(0.0, zeta) * 0.12
        )

        expectation_old = self.state.expectation
        # 先更新期望与满意度，再据此推动多巴胺预测误差修正。
        self.state.expectation = self._clamp(
            (1 - self.alpha_E) * expectation_old + self.alpha_E * performance
        )
        self.state.satisfaction = self._clamp_signed(
            self.state.satisfaction + self.eta * confirmation
        )

        delta_da = firing_rate - self.state.performance_prediction
        self.state.performance_prediction = self._clamp(
            self.state.performance_prediction + self.lambda_pred * delta_da
        )
        self.state.dopamine_level = self._clamp(
            self.state.dopamine_level
            + self.gamma_DA * delta_da
            + self.kappa_zeta * zeta
        )
        altruistic_drive = self._clamp(
            empathized_negative_emotion * self.state.empathy_level * (1.2 - self.state.dopamine_level)
        )
        self.state.moral_reward = self._clamp(
            performance + self.state.empathy_level * altruistic_drive
        )

        if epsilon > self.tau_epsilon:
            self.state.equilibrium_index = self._clamp(
                self.state.equilibrium_index - self.kappa_eq
            )
        else:
            self.state.equilibrium_index = self._clamp(
                self.state.equilibrium_index + self.eq_recovery
            )

        self.state.epsilon = epsilon
        self.state.zeta = zeta
        self.state.empathized_negative_emotion = empathized_negative_emotion
        self.state.dopamine_prediction_error = delta_da
        self.state.semantic_similarity = self._clamp(
            float(event.get("semantic_similarity", self.state.semantic_similarity))
        )

    def _update_beliefs_and_intentions(
        self,
        appraisal: AppraisalRecord,
        feed: List[dict],
    ) -> None:
        """从当前信息流中重建信念、知识摘要与行为意图。"""
        feed_summary = self._summarize_feed_for_appraisal(feed)
        social_influence_reward = self._estimate_social_influence_reward(feed)
        self.state.social_influence_reward = social_influence_reward
        explicit_tom_triggered = self.state.epsilon > self.tau_epsilon
        if not explicit_tom_triggered:
            explicit_tom_triggered = feed_summary.get("dispersion", 0.0) > 0.55
        self.state.explicit_tom_triggered = bool(explicit_tom_triggered)
        support_signal = self._clamp(
            self.state.empathized_negative_emotion * self.state.empathy_level
        )
        self.state.beliefs = {
            "environment_valence": self._clamp_signed(appraisal.valence),
            "social_pressure": self._clamp(feed_summary.get("exposure_pressure", 0.0)),
            "goal_alignment": self._clamp(appraisal.goal_conduciveness),
            "self_efficacy": self._clamp(self.state.schemas.get("self_efficacy", 0.5)),
            "others_need_support": support_signal,
            "social_influence_reward": social_influence_reward,
            "semantic_similarity": self.state.semantic_similarity,
        }
        self.state.knowledge = {
            **self.state.knowledge,
            "topic_consensus": self._clamp(feed_summary.get("consensus", 0.0)),
            "topic_polarization": self._clamp(feed_summary.get("dispersion", 0.0)),
            "salient_author_id": feed[0].get("author_id") if feed else None,
            "explicit_tom_target_ids": [
                int(item["author_id"])
                for item in feed[:3]
                if item.get("author_id") is not None and item.get("author_id") != self.agent_id
            ],
        }
        self.state.intentions = {
            "observe": self._clamp(
                0.45 + (0.22 if explicit_tom_triggered else 0.0) + (1 - appraisal.certainty) * 0.15
            ),
            "participate": self._clamp(
                0.35 + self.state.moral_reward * 0.18 + max(0.0, self.state.zeta) * 0.12
            ),
            "amplify": self._clamp(0.22 + social_influence_reward * 0.4),
            "withdraw": self._clamp(max(0.0, -self.state.satisfaction, self.state.epsilon - appraisal.coping_potential)),
            "support_others": self._clamp(0.25 + support_signal * 0.55),
        }

    def _initialize_desires(self, current: Dict[str, float]) -> Dict[str, float]:
        """按角色与表达风格补齐默认欲望配置。"""
        desires = dict(current)
        style = self.profile.communication_style.lower()
        role = self.profile.role.lower()
        desires.setdefault("affiliation", 0.6 if "balanced" in style else 0.5)
        desires.setdefault("self_expression", 0.72 if style in {"expressive", "direct"} else 0.55)
        desires.setdefault("stability", 0.66 if self.profile.ideology.lower() == "moderate" else 0.52)
        desires.setdefault("information_gain", 0.7 if role in {"journalist", "programmer"} else 0.55)
        return {key: self._clamp(value) for key, value in desires.items()}

    def _initialize_empathy_level(self, current: float) -> float:
        """根据角色与表达风格初始化共情水平。"""
        style = self.profile.communication_style.lower()
        role = self.profile.role.lower()
        baseline = current if current > 0 else 0.55
        if style in {"balanced", "expressive"}:
            baseline += 0.08
        if role in {"artist", "journalist", "teacher", "caregiver"}:
            baseline += 0.06
        return self._clamp(baseline)

    def _estimate_performance(
        self,
        *,
        valence: float,
        goal_conduciveness: float,
        certainty: float,
        coping_potential: float,
        feed: List[dict],
    ) -> float:
        """估计当前 appraisal 条件下的主观表现值。"""
        top_intensity = max((float(item.get("intensity", 0.0)) for item in feed[:3]), default=0.0)
        return self._clamp(
            0.35
            + goal_conduciveness * 0.25
            + certainty * 0.2
            + coping_potential * 0.12
            + max(0.0, valence) * 0.08
            + top_intensity * 0.04
        )

    def _suggest_oasis_actions(
        self,
        epsilon: float,
        zeta: float,
        coping_potential: float,
        satisfaction: float,
    ) -> tuple[str, List[str]]:
        """根据当前心理状态给出平台动作建议集合。"""
        if satisfaction < self.lambda_S and epsilon > self.tau_epsilon:
            actions = [
                "unfollow",
                "mute",
                "do_nothing",
                "dislike_post",
                "report_post",
                "exit",
                "unlike_post",
                "undo_dislike_post",
            ]
            return actions[0], actions
        if zeta > 0.25 and coping_potential > 0.45:
            actions = [
                "create_post",
                "create_comment",
                "repost",
                "quote_post",
                "like_post",
                "like_comment",
                "follow",
                "search_posts",
            ]
            return actions[0], actions
        if epsilon > 0.85:
            actions = [
                "do_nothing",
                "refresh",
                "search_posts",
                "search_user",
                "trend",
                "listen_from_group",
            ]
            return actions[0], actions
        actions = [
            "refresh",
            "like_post",
            "create_comment",
            "search_posts",
            "trend",
            "follow",
            "do_nothing",
            "search_user",
            "join_group",
            "listen_from_group",
            "repost",
            "quote_post",
        ]
        return actions[0], actions

    def _build_behavior_output(
        self,
        decision: AgentDecision,
        *,
        feed: List[dict],
        scenario_prompt: str,
        round_index: int,
    ) -> Dict[str, object]:
        """组装给调试页和导出逻辑使用的行为摘要。"""
        stimulus = feed[0]["content"] if feed else scenario_prompt
        if len(stimulus) > 120:
            stimulus = stimulus[:120] + "..."
        summary = _OASIS_ACTION_SUMMARY.get(
            decision.suggested_action,
            f"Execute platform action {decision.suggested_action}.",
        )
        simulated_public_content = None
        if decision.action in {"create_post", "reply_post", "share_post"}:
            simulated_public_content = decision.content
        return {
            "primary_action": decision.suggested_action,
            "stimulus_excerpt": stimulus,
            "public_behavior_summary": summary,
            "simulated_public_content": simulated_public_content,
            "state_hint": {
                "satisfaction": round(self.state.satisfaction, 4),
                "zeta": round(self.state.zeta, 4),
                "epsilon": round(self.state.epsilon, 4),
                "dopamine_level": round(self.state.dopamine_level, 4),
                "moral_reward": round(self.state.moral_reward, 4),
                "social_influence_reward": round(self.state.social_influence_reward, 4),
            },
            "cam_summary": list(self.state.knowledge.get("salient_cluster_summaries", [])),
            "explicit_tom_triggered": self.state.explicit_tom_triggered,
            "backend_action": decision.action,
            "round_index": round_index,
        }

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
        self.state.dopamine_level = self._clamp(
            self.state.dopamine_level
            - max(0.0, -avg_neighbor_sentiment) * 0.06
            + max(0.0, avg_neighbor_sentiment) * 0.03
        )

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
        goal_conduciveness: float,
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
        if valence > 0.15 and goal_conduciveness > 0.55:
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
            appraisal.goal_conduciveness,
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

    def _estimate_empathized_negative_emotion(self, feed_window: List[dict]) -> float:
        """估计信息流中负面内容引发的共情强度。"""
        signals = []
        for item in feed_window:
            if item.get("author_id") == self.agent_id:
                continue
            negative_valence = max(0.0, -float(item.get("sentiment", 0.0)))
            intensity = float(item.get("intensity", abs(item.get("sentiment", 0.0))))
            exposure = float(item.get("exposure_score", 1.0))
            signals.append(negative_valence * (0.6 + intensity * 0.25) * min(1.0, exposure))
        if not signals:
            return 0.0
        return self._clamp(sum(signals) / len(signals))

    def _estimate_social_influence_reward(self, feed: List[dict]) -> float:
        """估计当前信息流对社会影响收益的贡献。"""
        belief_embedding = self._belief_embedding()
        if not feed or not belief_embedding:
            return 0.0
        reward = 0.0
        for item in feed[:3]:
            if item.get("author_id") == self.agent_id:
                continue
            baseline = self._text_to_embedding_hash(str(item.get("content", "")))
            shift_weight = self._clamp(
                0.22
                + max(0.0, self.state.zeta) * 0.18
                + self.state.coping_potential * 0.12
                + self.state.empathy_level * 0.08
            )
            predicted_after = self._normalize_vector(
                [
                    (1 - shift_weight) * base + shift_weight * belief
                    for base, belief in zip(baseline, belief_embedding)
                ]
            )
            reward += 1.0 - self._cosine_sim(predicted_after, baseline)
        return self._clamp(reward)

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

    def _compose_observation_text(self, feed: List[dict], scenario_prompt: str) -> str:
        """把场景提示与信息流整理为 appraisal 输入文本。"""
        return self.environment.to_text_prompt(feed, scenario_prompt)

    def _belief_embedding(self) -> List[float]:
        """从 CAM 记忆图读取当前信念的全局向量表示。"""
        graph_embedding = self.state.schemata_graph.global_embedding()
        if graph_embedding:
            return [float(value) for value in graph_embedding[:E_CAM_T_EMBED_DIM]]
        return []

    def _text_to_embedding_hash(self, text: str) -> List[float]:
        """用稳定哈希为文本生成轻量近似向量。"""
        values: List[float] = []
        for index in range(E_CAM_T_EMBED_DIM):
            digest = hashlib.sha256(f"{text}:{index}".encode("utf-8")).digest()
            values.append(int.from_bytes(digest[:8], "big") / float(2**64))
        return self._normalize_vector(values)

    def _normalize_vector(self, values: List[float]) -> List[float]:
        """对向量做 L2 归一化。"""
        norm = math.sqrt(sum(value * value for value in values))
        if norm <= 1e-12:
            return [0.0 for _ in values]
        return [float(value / norm) for value in values]

    def _cosine_sim(self, left: List[float], right: List[float]) -> float:
        """计算两个向量的余弦相似度。"""
        if not left or not right:
            return 0.0
        size = min(len(left), len(right))
        numerator = sum(left[i] * right[i] for i in range(size))
        left_norm = math.sqrt(sum(left[i] * left[i] for i in range(size)))
        right_norm = math.sqrt(sum(right[i] * right[i] for i in range(size)))
        if left_norm <= 1e-12 or right_norm <= 1e-12:
            return 0.0
        return float(numerator / (left_norm * right_norm))

    @staticmethod
    def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
        """把数值限制到指定闭区间。"""
        return _clamp(value, minimum=minimum, maximum=maximum)

    @staticmethod
    def _clamp_signed(value: float, limit: float = 1.0) -> float:
        """把带符号数值限制到对称区间。"""
        return _clamp_signed(value, limit=limit)


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
