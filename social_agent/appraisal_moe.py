"""Appraisal 路由模块。

支持 MoE-first 的认知路径，也支持完全本地的启发式回退。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from Backend.services.llm_provider import CognitiveMoEProvider


APPRAISAL_KEYS = [
    "relevance",
    "valence",
    "goal_conduciveness",
    "controllability",
    "certainty",
    "coping_potential",
]


@dataclass
class ExpertOutput:
    """单个 appraisal 专家的输出结构。"""

    relevance: float = 0.0
    valence: float = 0.0
    goal_conduciveness: float = 0.5
    controllability: float = 0.5
    certainty: float = 0.5
    coping_potential: float = 0.5

    def to_dict(self) -> Dict[str, float]:
        return {
            "relevance": self.relevance,
            "valence": self.valence,
            "goal_conduciveness": self.goal_conduciveness,
            "controllability": self.controllability,
            "certainty": self.certainty,
            "coping_potential": self.coping_potential,
        }

    @property
    def goal_congruence(self) -> float:
        return self.goal_conduciveness


@dataclass
class AppraisalMoEConfig:
    """Appraisal 路由器的运行配置。"""

    mode: str = "moe"
    llm_provider_name: Optional[str] = "ollama"
    enable_fallback: bool = True
    checkpoint_dir: Optional[str] = None


class ThreatExpert:
    """偏重威胁、风险和负性社会线索的专家。"""

    def score(
        self,
        event: Dict[str, float],
        schemas: Dict[str, float],
        emotion_state: Any,
        stress: float,
        contagion_features: Dict[str, float],
    ) -> ExpertOutput:
        arousal = _pad_at(emotion_state, 1)
        risk = event["risk"]
        novelty = event["novelty"]
        threat_sensitivity = schemas["threat_sensitivity"]
        contagion_negativity = max(0.0, -contagion_features.get("sentiment", 0.0))
        social_arousal = contagion_features.get("arousal", 0.0)
        return ExpertOutput(
            relevance=_clamp(risk * 0.42 + novelty * 0.2 + arousal * 0.14 + contagion_negativity * 0.16 + social_arousal * 0.08),
            valence=_clamp_signed(-(risk * 0.48 + threat_sensitivity * 0.2 + contagion_negativity * 0.2 + stress * 0.12)),
            goal_conduciveness=_clamp(1.0 - (risk * 0.28 + novelty * 0.18 + contagion_negativity * 0.18)),
            controllability=_clamp(1.0 - (risk * 0.36 + arousal * 0.14 + social_arousal * 0.08 + stress * 0.08)),
            certainty=_clamp(1.0 - novelty * 0.45 - social_arousal * 0.08 - contagion_features.get("dispersion", 0.0) * 0.08),
            coping_potential=_clamp(1.0 - (risk * 0.28 + threat_sensitivity * 0.14 + contagion_negativity * 0.14 + stress * 0.1)),
        )


class SupportExpert:
    """偏重支持感、立场一致性和正向反馈的专家。"""

    def score(
        self,
        event: Dict[str, float],
        schemas: Dict[str, float],
        emotion_state: Any,
        feed_features: Dict[str, float],
        memory_summary: Dict[str, float],
    ) -> ExpertOutput:
        pleasure = _pad_at(emotion_state, 0)
        support = schemas["support_tendency"]
        schema_direction = support * 2 - 1
        feed_direction = feed_features.get("direction", event["direction"])
        memory_bias = memory_summary.get("valence_bias", 0.0)
        memory_coherence = memory_summary.get("coherence", 0.5)
        goal = _clamp(1.0 - abs(feed_direction - schema_direction) / 2.0 + memory_coherence * 0.08)
        return ExpertOutput(
            relevance=_clamp(abs(feed_direction) * 0.22 + support * 0.2 + abs(pleasure) * 0.16 + feed_features.get("exposure_pressure", 0.0) * 0.16 + memory_coherence * 0.12),
            valence=_clamp_signed(feed_direction * 0.42 + schema_direction * 0.2 + pleasure * 0.18 + memory_bias * 0.12),
            goal_conduciveness=goal,
            controllability=_clamp(0.42 + max(0.0, pleasure) * 0.12 + goal * 0.24 + memory_coherence * 0.08),
            certainty=_clamp(event["consistency"] * 0.44 + goal * 0.24 + memory_coherence * 0.16 + (1 - feed_features.get("dispersion", 0.0)) * 0.08),
            coping_potential=_clamp(0.42 + goal * 0.18 + max(0.0, pleasure) * 0.14 + memory_bias * 0.06),
        )


class CopingExpert:
    """偏重控制感、自我效能和恢复能力的专家。"""

    def score(
        self,
        event: Dict[str, float],
        schemas: Dict[str, float],
        emotion_state: Any,
        stress: float,
        equilibrium: float,
        memory_summary: Dict[str, float],
    ) -> ExpertOutput:
        dominance = _pad_at(emotion_state, 2)
        efficacy = schemas["self_efficacy"]
        recovered = memory_summary.get("self_generated_ratio", 0.0)
        return ExpertOutput(
            relevance=_clamp(event["risk"] * 0.12 + stress * 0.18 + abs(dominance) * 0.08 + memory_summary.get("salience", 0.0) * 0.1),
            valence=_clamp_signed(dominance * 0.28 - stress * 0.12 + recovered * 0.06),
            goal_conduciveness=_clamp(0.44 + efficacy * 0.18 - stress * 0.08 + recovered * 0.06),
            controllability=_clamp(efficacy * 0.34 + equilibrium * 0.24 + max(0.0, dominance) * 0.14 + recovered * 0.08),
            certainty=_clamp((1 - event["novelty"]) * 0.2 + equilibrium * 0.24 + (1 - stress) * 0.22 + memory_summary.get("coherence", 0.0) * 0.12),
            coping_potential=_clamp(efficacy * 0.4 + equilibrium * 0.18 + max(0.0, dominance) * 0.14 + (1 - stress) * 0.08 + recovered * 0.08),
        )


class SocialAmplificationExpert:
    """偏重信息流放大效应和社会扩散线索的专家。"""

    def score(
        self,
        event: Dict[str, float],
        schemas: Dict[str, float],
        emotion_state: Any,
        feed_features: Dict[str, float],
        contagion_features: Dict[str, float],
        memory_summary: Dict[str, float],
    ) -> ExpertOutput:
        pleasure = _pad_at(emotion_state, 0)
        exposure_pressure = feed_features.get("exposure_pressure", 0.0)
        exposure_polarity = feed_features.get("exposure_polarity", 0.0)
        social_sentiment = contagion_features.get("sentiment", 0.0)
        social_arousal = contagion_features.get("arousal", 0.0)
        memory_sociality = memory_summary.get("feed_ratio", 0.0)
        return ExpertOutput(
            relevance=_clamp(exposure_pressure * 0.28 + abs(exposure_polarity) * 0.14 + social_arousal * 0.18 + abs(social_sentiment) * 0.14 + memory_sociality * 0.1),
            valence=_clamp_signed(exposure_polarity * 0.3 + social_sentiment * 0.3 + pleasure * 0.08 - feed_features.get("dispersion", 0.0) * 0.08),
            goal_conduciveness=_clamp(0.5 + exposure_polarity * 0.14 + social_sentiment * 0.12 + (schemas["support_tendency"] * 2 - 1) * 0.08),
            controllability=_clamp(0.42 - social_arousal * 0.08 - exposure_pressure * 0.06 + max(0.0, _pad_at(emotion_state, 2)) * 0.08),
            certainty=_clamp(0.46 + feed_features.get("consensus", 0.0) * 0.18 - feed_features.get("dispersion", 0.0) * 0.14 - social_arousal * 0.06),
            coping_potential=_clamp(0.44 + max(0.0, _pad_at(emotion_state, 2)) * 0.08 - exposure_pressure * 0.06 - social_arousal * 0.06 + memory_summary.get("self_generated_ratio", 0.0) * 0.04),
        )


class AppraisalRouter:
    """Appraisal 总路由器。"""

    def __init__(self, config: Optional[AppraisalMoEConfig] = None) -> None:
        self.config = config or AppraisalMoEConfig()
        self.threat_expert = ThreatExpert()
        self.support_expert = SupportExpert()
        self.coping_expert = CopingExpert()
        self.social_expert = SocialAmplificationExpert()
        self.provider = CognitiveMoEProvider(
            llm_provider=self.config.llm_provider_name,
            checkpoint_dir=self.config.checkpoint_dir,
            mode=self.config.mode,
            enable_fallback=self.config.enable_fallback,
        )
        self.last_run_metadata: Dict[str, object] = {
            # 记录最近一次 appraisal 是外部生成还是本地回退得到的。
            "mode": self.config.mode,
            "provider": None,
            "model": None,
            "source": "local",
            "fallback_used": False,
            "fallback_reason": None,
        }

    def evaluate(
        self,
        event: Dict[str, float],
        schemas: Dict[str, float],
        emotion_state: Any,
        stress: float,
        equilibrium: float,
        feed_features: Dict[str, float],
        contagion_features: Dict[str, float],
        memory_summary: Dict[str, float],
        prior: Dict[str, float],
        llm_context: Optional[Dict[str, object]] = None,
    ) -> Dict[str, float]:
        """对当前事件进行 appraisal 评估。"""

        fallback_result = self._fallback_appraisal(
            event=event,
            schemas=schemas,
            emotion_state=emotion_state,
            stress=stress,
            equilibrium=equilibrium,
            feed_features=feed_features,
            contagion_features=contagion_features,
            memory_summary=memory_summary,
            prior=prior,
        )

        if self.config.mode == "fallback":
            self.last_run_metadata = {
                "mode": "fallback",
                "provider": "local",
                "model": None,
                "source": "local",
                "fallback_used": True,
                "fallback_reason": "mode_forced_fallback",
            }
            return fallback_result

        payload = {
            "event": event,
            "schemas": schemas,
            "emotion_state": {
                "signed_valence": float(getattr(emotion_state, "signed_valence", 0.0)),
                "pad": list(getattr(emotion_state, "pad", [0.0, 0.0, 0.0])),
                "intensity": float(getattr(emotion_state, "intensity", 0.0)),
            },
            "stress": stress,
            "equilibrium": equilibrium,
            "feed_features": feed_features,
            "contagion_features": contagion_features,
            "memory_summary": memory_summary,
            "prior": prior,
            "llm_context": llm_context or {},
        }
        result = self.provider.generate_appraisal(
            payload,
            fallback_fn=lambda _payload: fallback_result,
        )
        meta = result.get("_provider_meta", {})
        self.last_run_metadata = {
            "mode": str(meta.get("mode", "fallback")),
            "provider": None,
            "provider": meta.get("provider"),
            "model": meta.get("model"),
            "source": meta.get("source", "local"),
            "fallback_used": bool(meta.get("fallback_used", False)),
            "fallback_reason": meta.get("fallback_reason"),
        }
        if meta.get("fallback_used", False):
            return fallback_result

        return {
            "relevance": _clamp(result.get("relevance", fallback_result["relevance"])),
            "valence": _clamp_signed(result.get("valence", fallback_result["valence"])),
            "goal_conduciveness": _clamp(
                result.get(
                    "goal_conduciveness",
                    result.get("goal_congruence", fallback_result["goal_conduciveness"]),
                )
            ),
            "controllability": _clamp(result.get("controllability", fallback_result["controllability"])),
            "certainty": _clamp(result.get("certainty", fallback_result["certainty"])),
            "coping_potential": _clamp(result.get("coping_potential", fallback_result["coping_potential"])),
        }

    def _fallback_appraisal(
        self,
        event: Dict[str, float],
        schemas: Dict[str, float],
        emotion_state: Any,
        stress: float,
        equilibrium: float,
        feed_features: Dict[str, float],
        contagion_features: Dict[str, float],
        memory_summary: Dict[str, float],
        prior: Dict[str, float],
    ) -> Dict[str, float]:
        """本地启发式 appraisal 回退路径。"""

        weights = self._route(
            event=event,
            schemas=schemas,
            emotion_state=emotion_state,
            stress=stress,
            equilibrium=equilibrium,
            feed_features=feed_features,
            contagion_features=contagion_features,
            memory_summary=memory_summary,
        )
        outputs = {
            "threat": self.threat_expert.score(event, schemas, emotion_state, stress, contagion_features),
            "support": self.support_expert.score(event, schemas, emotion_state, feed_features, memory_summary),
            "coping": self.coping_expert.score(event, schemas, emotion_state, stress, equilibrium, memory_summary),
            "social": self.social_expert.score(event, schemas, emotion_state, feed_features, contagion_features, memory_summary),
        }
        fused: Dict[str, float] = {}
        for key in APPRAISAL_KEYS:
            expert_value = sum(weights[name] * getattr(outputs[name], key) for name in outputs)
            fused[key] = prior[key] * 0.3 + expert_value * 0.7
        fused["relevance"] = _clamp(fused["relevance"])
        fused["goal_conduciveness"] = _clamp(fused["goal_conduciveness"])
        fused["controllability"] = _clamp(fused["controllability"])
        fused["certainty"] = _clamp(fused["certainty"])
        fused["coping_potential"] = _clamp(fused["coping_potential"])
        fused["valence"] = _clamp_signed(fused["valence"])
        return fused

    def _route(
        self,
        event: Dict[str, float],
        schemas: Dict[str, float],
        emotion_state: Any,
        stress: float,
        equilibrium: float,
        feed_features: Dict[str, float],
        contagion_features: Dict[str, float],
        memory_summary: Dict[str, float],
    ) -> Dict[str, float]:
        """估计四个专家的路由权重。"""

        arousal = _pad_at(emotion_state, 1)
        pleasure = _pad_at(emotion_state, 0)
        threat_score = event["risk"] * 0.32 + event["novelty"] * 0.16 + arousal * 0.08 + max(0.0, -contagion_features.get("sentiment", 0.0)) * 0.16 + contagion_features.get("arousal", 0.0) * 0.08
        support_score = max(0.0, feed_features.get("direction", event["direction"])) * 0.18 + schemas["support_tendency"] * 0.16 + max(0.0, pleasure) * 0.1 + max(0.0, memory_summary.get("valence_bias", 0.0)) * 0.1
        coping_score = schemas["self_efficacy"] * 0.24 + equilibrium * 0.18 + (1 - stress) * 0.14 + memory_summary.get("self_generated_ratio", 0.0) * 0.08
        social_score = feed_features.get("exposure_pressure", 0.0) * 0.22 + abs(feed_features.get("exposure_polarity", 0.0)) * 0.12 + contagion_features.get("arousal", 0.0) * 0.1 + memory_summary.get("feed_ratio", 0.0) * 0.08
        total = max(1e-6, threat_score + support_score + coping_score + social_score)
        return {
            "threat": threat_score / total,
            "support": support_score / total,
            "coping": coping_score / total,
            "social": social_score / total,
        }


def _pad_at(emotion_state: Any, index: int) -> float:
    pad = getattr(emotion_state, "pad", [0.0, 0.0, 0.0])
    return float(pad[index]) if len(pad) > index else 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp_signed(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))
