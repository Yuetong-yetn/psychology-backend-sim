"""轻量级本地情绪检测器。

这个模块让 Backend 在完全离线时也能运行，同时暴露可插拔的情绪分析接口：
- `RuleBasedEmotionDetector`：关键词规则基线
- `HeuristicContextEmotionDetector`：带上下文启发式的轻量分析器
- `CompositeEmotionDetector`：融合文本结果和内部信号
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


EMOTION_LABELS = [
    "anger",
    "frustration",
    "anxiety",
    "fear",
    "guilt",
    "shame",
    "hope",
    "confidence",
    "relief",
    "calm",
]

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

LATENT_DIM = 16

EMOTION_KEYWORDS = {
    "anger": ["angry", "rage", "furious", "outrage", "mad", "hate"],
    "frustration": ["frustrated", "annoyed", "stuck", "tired", "upset"],
    "anxiety": ["anxious", "worry", "uncertain", "nervous", "uneasy"],
    "fear": ["fear", "afraid", "threat", "danger", "risk", "unsafe"],
    "guilt": ["guilt", "sorry", "regret", "apologize"],
    "shame": ["shame", "embarrassed", "humiliated"],
    "hope": ["hope", "wish", "optimistic", "promising"],
    "confidence": ["confident", "certain", "sure", "strong", "clear"],
    "relief": ["relief", "finally", "safe", "better", "solved"],
}

# 启发式探测器会用到的语气词和风险词典。
NEGATION_WORDS = ["not", "never", "no", "hardly", "rarely", "without"]
INTENSIFIERS = ["very", "really", "extremely", "highly", "deeply", "so"]
UNCERTAINTY_WORDS = ["maybe", "perhaps", "unclear", "uncertain", "possibly", "seems"]
THREAT_WORDS = ["risk", "threat", "danger", "crisis", "harm", "conflict"]
SUPPORT_WORDS = ["support", "agree", "benefit", "help", "progress", "improve"]


@dataclass
class EmotionAnalysis:
    """可序列化的情绪分析结果。"""

    emotion_probs: Dict[str, float] = field(default_factory=dict)
    dominant_emotion: str = "calm"
    intensity: float = 0.0
    sentiment: float = 0.0
    pad: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    emotion_latent: List[float] = field(default_factory=lambda: [0.0] * LATENT_DIM)

    def to_dict(self) -> dict:
        return asdict(self)


class BaseEmotionDetector:
    """情绪检测器的统一接口。"""

    def analyze_text(
        self,
        text: str,
        overrides: Optional[Dict[str, object]] = None,
    ) -> EmotionAnalysis:
        raise NotImplementedError


class RuleBasedEmotionDetector(BaseEmotionDetector):
    """基于关键词的离线基线检测器。"""

    def analyze_text(
        self,
        text: str,
        overrides: Optional[Dict[str, object]] = None,
    ) -> EmotionAnalysis:
        overrides = overrides or {}
        lowered = (text or "").lower()
        # 先按关键词命中次数做一个最粗的情绪分布估计。
        counts = {label: 0.0 for label in EMOTION_LABELS}

        for label, keywords in EMOTION_KEYWORDS.items():
            counts[label] = float(sum(1 for keyword in keywords if keyword in lowered))

        total_hits = sum(counts.values())
        probs = self._counts_to_probs(counts, total_hits)
        dominant = self._resolve_dominant_emotion(probs)
        sentiment = self._resolve_sentiment(probs)
        intensity = self._resolve_intensity(total_hits, sentiment)
        pad = self._resolve_pad(probs, sentiment, intensity)
        latent = _project_latent(probs, pad, intensity)

        return _merge_with_overrides(
            EmotionAnalysis(
                emotion_probs=probs,
                dominant_emotion=dominant,
                intensity=intensity,
                sentiment=sentiment,
                pad=pad,
                emotion_latent=latent,
            ),
            overrides,
            trust_overrides=False,
        )

    def _counts_to_probs(self, counts: Dict[str, float], total_hits: float) -> Dict[str, float]:
        if total_hits <= 0:
            calm_prior = {label: 0.0 for label in EMOTION_LABELS}
            calm_prior["calm"] = 1.0
            return calm_prior

        raw_scores = {label: 0.05 + counts[label] for label in EMOTION_LABELS}
        raw_scores["calm"] = 0.05
        total = sum(raw_scores.values()) or 1.0
        return {label: float(raw_scores[label] / total) for label in EMOTION_LABELS}

    def _resolve_dominant_emotion(self, probs: Dict[str, float]) -> str:
        return max(probs, key=probs.get)

    def _resolve_sentiment(self, probs: Dict[str, float]) -> float:
        sentiment = sum(probs[label] * EMOTION_SENTIMENT[label] for label in EMOTION_LABELS)
        return _clamp_signed(sentiment * 1.6)

    def _resolve_intensity(self, total_hits: float, sentiment: float) -> float:
        return _clamp(0.15 * total_hits + abs(sentiment) * 0.65)

    def _resolve_pad(
        self,
        probs: Dict[str, float],
        sentiment: float,
        intensity: float,
    ) -> List[float]:
        pleasure = _clamp_signed(sentiment)
        arousal = _clamp(
            intensity * 0.75
            + probs["anger"] * 0.25
            + probs["fear"] * 0.2
            + probs["anxiety"] * 0.2
        )
        dominance = _clamp_signed(
            probs["confidence"] * 0.9
            + probs["relief"] * 0.25
            - probs["fear"] * 0.6
            - probs["anxiety"] * 0.45
            - probs["shame"] * 0.35
        )
        return [float(pleasure), float(arousal), float(dominance)]


class HeuristicContextEmotionDetector(BaseEmotionDetector):
    """带上下文启发式的轻量检测器。"""

    def analyze_text(
        self,
        text: str,
        overrides: Optional[Dict[str, object]] = None,
    ) -> EmotionAnalysis:
        overrides = overrides or {}
        lowered = (text or "").lower()
        tokens = [token.strip(".,!?;:\"'()[]{}") for token in lowered.split()]
        token_count = max(1, len(tokens))

        # 这些计数近似表达语气强度、不确定性和社会支持/威胁线索。
        exclamations = lowered.count("!")
        questions = lowered.count("?")
        negations = sum(1 for token in tokens if token in NEGATION_WORDS)
        intensifiers = sum(1 for token in tokens if token in INTENSIFIERS)
        uncertainty = sum(1 for token in tokens if token in UNCERTAINTY_WORDS)
        threat = sum(1 for token in tokens if token in THREAT_WORDS)
        support = sum(1 for token in tokens if token in SUPPORT_WORDS)

        sentiment = _clamp_signed(
            (support - threat) * 0.18
            - negations * 0.08
            - uncertainty * 0.06
            + exclamations * 0.03
        )
        arousal = _clamp(
            0.12
            + exclamations * 0.1
            + questions * 0.05
            + intensifiers * 0.08
            + threat * 0.06
            + uncertainty * 0.04
        )
        dominance = _clamp_signed(
            support * 0.12
            - uncertainty * 0.08
            - questions * 0.03
            + intensifiers * 0.03
        )
        intensity = _clamp(abs(sentiment) * 0.45 + arousal * 0.45 + min(0.2, token_count / 40))

        # 先给每个情绪一个很小的先验，再逐项叠加启发式增量。
        probs = {label: 0.02 for label in EMOTION_LABELS}
        probs["anger"] += max(0.0, threat * 0.08 + exclamations * 0.04 - support * 0.03)
        probs["frustration"] += max(0.0, negations * 0.06 + questions * 0.03)
        probs["anxiety"] += max(0.0, uncertainty * 0.1 + questions * 0.04)
        probs["fear"] += max(0.0, threat * 0.1 + uncertainty * 0.05)
        probs["guilt"] += max(0.0, 0.04 if "sorry" in lowered or "regret" in lowered else 0.0)
        probs["shame"] += max(0.0, 0.04 if "shame" in lowered or "embarrassed" in lowered else 0.0)
        probs["hope"] += max(0.0, support * 0.08 + max(0.0, sentiment) * 0.08)
        probs["confidence"] += max(0.0, dominance * 0.18 + support * 0.04)
        probs["relief"] += max(0.0, 0.06 if "finally" in lowered or "better" in lowered else 0.0)
        probs["calm"] += max(0.0, 0.2 - arousal * 0.12)
        probs = _normalize_probs(probs)

        dominant = max(probs, key=probs.get)
        pad = [float(sentiment), float(arousal), float(dominance)]
        latent = _project_latent(probs, pad, intensity)
        return _merge_with_overrides(
            EmotionAnalysis(
                emotion_probs=probs,
                dominant_emotion=dominant,
                intensity=float(intensity),
                sentiment=float(sentiment),
                pad=pad,
                emotion_latent=latent,
            ),
            overrides,
            trust_overrides=False,
        )


class CompositeEmotionDetector(BaseEmotionDetector):
    """融合文本情绪和内部信号的组合检测器。"""

    def __init__(
        self,
        rule_detector: Optional[BaseEmotionDetector] = None,
        heuristic_detector: Optional[BaseEmotionDetector] = None,
    ) -> None:
        self.rule_detector = rule_detector or RuleBasedEmotionDetector()
        self.heuristic_detector = heuristic_detector or HeuristicContextEmotionDetector()

    def analyze_text(
        self,
        text: str,
        overrides: Optional[Dict[str, object]] = None,
    ) -> EmotionAnalysis:
        overrides = overrides or {}
        internal_signal = overrides.get("internal_signal")

        rule_result = self.rule_detector.analyze_text(text).to_dict()
        try:
            heuristic_result = self.heuristic_detector.analyze_text(text).to_dict()
        except Exception:
            heuristic_result = rule_result

        # 先融合两个文本分析器，再视情况叠加 agent 内部信号。
        fused_text = self._blend_results(rule_result, heuristic_result, left_weight=0.45)
        final_result = fused_text

        normalized_internal = _normalize_internal_signal(internal_signal)
        if normalized_internal is not None:
            final_result = self._blend_results(fused_text, normalized_internal, left_weight=0.68)

        return _merge_with_overrides(
            EmotionAnalysis(
                emotion_probs=dict(final_result["emotion_probs"]),
                dominant_emotion=str(final_result["dominant_emotion"]),
                intensity=float(final_result["intensity"]),
                sentiment=float(final_result["sentiment"]),
                pad=[float(item) for item in final_result["pad"]],
                emotion_latent=[float(item) for item in final_result["emotion_latent"]],
            ),
            overrides,
            trust_overrides=False,
        )

    def _blend_results(
        self,
        left: Dict[str, object],
        right: Dict[str, object],
        left_weight: float,
    ) -> Dict[str, object]:
        right_weight = 1.0 - left_weight
        left_probs = _ensure_probs(left.get("emotion_probs", {}))
        right_probs = _ensure_probs(right.get("emotion_probs", {}))
        probs = {
            label: left_probs[label] * left_weight + right_probs[label] * right_weight
            for label in EMOTION_LABELS
        }
        probs = _normalize_probs(probs)
        sentiment = _clamp_signed(
            float(left.get("sentiment", 0.0)) * left_weight
            + float(right.get("sentiment", 0.0)) * right_weight
        )
        intensity = _clamp(
            float(left.get("intensity", 0.0)) * left_weight
            + float(right.get("intensity", 0.0)) * right_weight
        )
        left_pad = _ensure_pad(left.get("pad"))
        right_pad = _ensure_pad(right.get("pad"))
        pad = [
            _clamp_signed(left_pad[0] * left_weight + right_pad[0] * right_weight),
            _clamp(left_pad[1] * left_weight + right_pad[1] * right_weight),
            _clamp_signed(left_pad[2] * left_weight + right_pad[2] * right_weight),
        ]
        left_latent = _ensure_latent(left.get("emotion_latent"))
        right_latent = _ensure_latent(right.get("emotion_latent"))
        latent = [
            float(left_latent[index] * left_weight + right_latent[index] * right_weight)
            for index in range(LATENT_DIM)
        ]
        dominant = max(probs, key=probs.get)
        return {
            "emotion_probs": probs,
            "dominant_emotion": dominant,
            "intensity": intensity,
            "sentiment": sentiment,
            "pad": pad,
            "emotion_latent": latent,
        }


def _merge_with_overrides(
    analysis: EmotionAnalysis,
    overrides: Dict[str, object],
    trust_overrides: bool = False,
) -> EmotionAnalysis:
    """按需信任覆盖字段；默认不直接相信外部覆盖值。"""
    if not trust_overrides:
        return analysis

    payload = analysis.to_dict()
    if isinstance(overrides.get("emotion_probs"), dict):
        payload["emotion_probs"] = _ensure_probs(overrides["emotion_probs"])
    if isinstance(overrides.get("dominant_emotion"), str):
        payload["dominant_emotion"] = overrides["dominant_emotion"]
    if isinstance(overrides.get("emotion"), str):
        payload["dominant_emotion"] = overrides["emotion"]
    if isinstance(overrides.get("intensity"), (int, float)):
        payload["intensity"] = _clamp(float(overrides["intensity"]))
    if isinstance(overrides.get("sentiment"), (int, float)):
        payload["sentiment"] = _clamp_signed(float(overrides["sentiment"]))
    if isinstance(overrides.get("pad"), list) and len(overrides["pad"]) == 3:
        payload["pad"] = _ensure_pad(overrides["pad"])
    if isinstance(overrides.get("emotion_latent"), list):
        payload["emotion_latent"] = _ensure_latent(overrides["emotion_latent"])
    return EmotionAnalysis(
        emotion_probs=payload["emotion_probs"],
        dominant_emotion=payload["dominant_emotion"],
        intensity=payload["intensity"],
        sentiment=payload["sentiment"],
        pad=payload["pad"],
        emotion_latent=payload["emotion_latent"],
    )


def _normalize_internal_signal(signal: object) -> Optional[Dict[str, object]]:
    """把 agent 自报的内部情绪信号整理成统一格式。"""
    if not isinstance(signal, dict):
        return None

    sentiment = _clamp_signed(float(signal.get("sentiment", 0.0)))
    intensity = _clamp(float(signal.get("intensity", abs(sentiment))))
    dominant = signal.get("dominant_emotion") or signal.get("emotion") or _label_from_sentiment(sentiment)
    probs = signal.get("emotion_probs")
    if not isinstance(probs, dict) or not probs:
        probs = _seed_probs_from_signal(str(dominant), sentiment, intensity)
    else:
        probs = _ensure_probs(probs)
    pad = _ensure_pad(signal.get("pad"))
    latent = _ensure_latent(signal.get("emotion_latent"))
    if pad == [0.0, 0.0, 0.0]:
        pad = [
            sentiment,
            intensity,
            _clamp_signed((intensity * 0.5) if sentiment >= 0 else -(intensity * 0.35)),
        ]
    if latent == [0.0] * LATENT_DIM:
        latent = _project_latent(probs, pad, intensity)
    return {
        "emotion_probs": probs,
        "dominant_emotion": str(dominant),
        "intensity": intensity,
        "sentiment": sentiment,
        "pad": pad,
        "emotion_latent": latent,
    }


def _seed_probs_from_signal(dominant: str, sentiment: float, intensity: float) -> Dict[str, float]:
    probs = {label: 0.01 for label in EMOTION_LABELS}
    dominant = dominant if dominant in probs else _label_from_sentiment(sentiment)
    probs[dominant] = 0.55 + 0.25 * _clamp(intensity)
    if sentiment >= 0:
        probs["confidence"] += 0.07 * _clamp(intensity)
        probs["hope"] += 0.05 * _clamp(intensity)
        probs["relief"] += 0.03
    else:
        probs["fear"] += 0.08 * _clamp(intensity)
        probs["anxiety"] += 0.06 * _clamp(intensity)
        probs["anger"] += 0.04 * abs(sentiment)
    return _normalize_probs(probs)


def _ensure_probs(probs: object) -> Dict[str, float]:
    if not isinstance(probs, dict):
        calm = {label: 0.0 for label in EMOTION_LABELS}
        calm["calm"] = 1.0
        return calm
    normalized = {label: float(probs.get(label, 0.0)) for label in EMOTION_LABELS}
    return _normalize_probs(normalized)


def _normalize_probs(probs: Dict[str, float]) -> Dict[str, float]:
    clipped = {label: max(0.0, float(probs.get(label, 0.0))) for label in EMOTION_LABELS}
    total = sum(clipped.values())
    if total <= 1e-6:
        clipped = {label: 0.0 for label in EMOTION_LABELS}
        clipped["calm"] = 1.0
        return clipped
    return {label: float(clipped[label] / total) for label in EMOTION_LABELS}


def _ensure_pad(pad: object) -> List[float]:
    if not isinstance(pad, list) or len(pad) < 3:
        return [0.0, 0.0, 0.0]
    return [
        _clamp_signed(float(pad[0])),
        _clamp(float(pad[1])),
        _clamp_signed(float(pad[2])),
    ]


def _ensure_latent(latent: object) -> List[float]:
    if not isinstance(latent, list):
        return [0.0] * LATENT_DIM
    values = [float(item) for item in latent[:LATENT_DIM]]
    if len(values) < LATENT_DIM:
        values.extend([0.0] * (LATENT_DIM - len(values)))
    return values


def _project_latent(
    probs: Dict[str, float],
    pad: List[float],
    intensity: float,
) -> List[float]:
    """把情绪分布和 PAD 映射到固定长度 latent。"""
    positive_mass = probs["hope"] + probs["confidence"] + probs["relief"]
    negative_mass = (
        probs["anger"]
        + probs["frustration"]
        + probs["anxiety"]
        + probs["fear"]
        + probs["guilt"]
        + probs["shame"]
    )
    return [
        float(pad[0]),
        float(pad[1]),
        float(pad[2]),
        float(positive_mass),
        float(negative_mass),
        float(probs["confidence"] + probs["hope"]),
        float(probs["anger"] + probs["fear"] + probs["anxiety"]),
        float(_clamp(intensity)),
        float(_clamp_signed(pad[0])),
        float(_clamp(pad[1])),
        float(_clamp_signed(pad[2])),
        0.0,
        0.0,
        0.0,
        0.5,
        0.5,
    ]


def _label_from_sentiment(sentiment: float) -> str:
    if sentiment > 0.35:
        return "confidence"
    if sentiment > 0.1:
        return "hope"
    if sentiment < -0.5:
        return "fear"
    if sentiment < -0.2:
        return "anxiety"
    return "calm"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp_signed(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))
